"""Gemini wrapper — the ONLY place LLM calls happen.

Guardrails (AGENT.md): Flash by default, Pro only for heavy reasoning, and
structured JSON output always (never parse prose). With no GEMINI_API_KEY the
caller gets its `mock` value back, so the whole pipeline demos offline.

Lumen stays on Gemini's free tier: every call is a JSON text request made with
an API key. Nothing here uses the paid-only features (Google Search grounding,
image generation) or Vertex AI.

Install `google-genai` (see requirements.txt) before setting a real key.

`generate_json` keeps its original signature so existing agents are unchanged.
`generate_json_traced` adds what the audience simulator needs: which model
actually served the call, whether it fell back, and whether the result is real
or mock — so the UI can never present mock output as a live model result.
`recording()` counts both kinds for a block of work, which is how a plan can
say which of its parts came from Lumen's sample output.
"""
import contextvars
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator, Optional

from core import config

_client = None
_client_lock = threading.Lock()

# The count kept for the block of work running now, or None when nobody asked.
_tally: contextvars.ContextVar[Optional[dict[str, Any]]] = contextvars.ContextVar("gemini_tally", default=None)
_tally_lock = threading.Lock()

# Errors worth another attempt on the same model. Anything else, including a
# 504 DEADLINE_EXCEEDED (the model already took the whole timeout, so a retry
# would likely wait that long again), moves straight on to the next model.
_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL")
_MODEL_GONE = ("404", "NOT_FOUND")
# A rate-limited reply can say how long to wait (RetryInfo). Longer waits than
# this are better spent on the next model in the chain, whose quota is its own.
MAX_RETRY_WAIT_S = 20.0


class GeminiUnavailable(RuntimeError):
    """Every candidate model failed. Carries the last error for reporting."""


@contextmanager
def recording() -> Iterator[dict[str, Any]]:
    """Count the calls made inside the block: {live, sample, reasons}.

    The orchestrator opens one per phase, so a plan can say which of its parts
    the model wrote and which fell back to an agent's sample output.
    """
    tally: dict[str, Any] = {"live": 0, "sample": 0, "reasons": []}
    token = _tally.set(tally)
    try:
        yield tally
    finally:
        _tally.reset(token)


def _record(live: bool, reason: str = "") -> None:
    tally = _tally.get()
    if tally is None:
        return
    with _tally_lock:  # batched agent work counts from several threads
        tally["live" if live else "sample"] += 1
        if reason and reason not in tally["reasons"]:
            tally["reasons"].append(reason)


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            if not config.GEMINI_API_KEY:
                raise GeminiUnavailable("No Gemini access: set GEMINI_API_KEY.")
            from google import genai  # imported lazily so mock mode needs no install
            from google.genai import types

            _client = genai.Client(
                api_key=config.GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_MS),
            )
    return _client


def _retry_after(exc: Exception) -> Optional[float]:
    """The wait a 429 asks for, in seconds, when the reply carries one."""
    details = getattr(exc, "details", None)
    error = details.get("error", details) if isinstance(details, dict) else {}
    for item in (error.get("details") or []) if isinstance(error, dict) else []:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("RetryInfo"):
            try:
                return float(str(item.get("retryDelay", "")).rstrip("s"))
            except ValueError:
                return None
    return None


def _backoff(exc: Exception, attempt: int) -> Optional[float]:
    """Seconds to wait before trying the same model again, or None to move on
    to the next model. Free-tier keys are rate-limited per minute, and Google
    says how long to wait; waiting that long beats burning the retry at once."""
    asked = _retry_after(exc)
    if asked is None:
        return 1.5 * (attempt + 1) + random.random()
    return asked + random.random() / 2 if asked <= MAX_RETRY_WAIT_S else None


def _candidates(tier: str) -> list[str]:
    """Models to try, in order, for a tier: the tier's configured model first,
    then the fallback chain, so a retired or overloaded model degrades the run
    instead of ending it (AGENT.md: Flash by default, Pro for heavy reasoning)."""
    preferred = config.GEMINI_PRO_MODEL if tier == "pro" else config.GEMINI_FLASH_MODEL
    chain = [preferred, config.GEMINI_FLASH_MODEL, *config.GEMINI_FALLBACK_MODELS]
    ordered: list[str] = []
    for model in chain:
        if model and model not in ordered:
            ordered.append(model)
    return ordered


def _extract_json(text: str) -> Any:
    """Models occasionally wrap JSON in a fence or preamble despite the mime type."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    try:
        return json.loads(cleaned)
    except Exception:
        # If response has reasoning prose or markdown, isolate the first JSON structure
        first_brace = cleaned.find("{")
        first_bracket = cleaned.find("[")
        if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
            last_brace = cleaned.rfind("}")
            if last_brace > first_brace:
                return json.loads(cleaned[first_brace : last_brace + 1])
        elif first_bracket != -1:
            last_bracket = cleaned.rfind("]")
            if last_bracket > first_bracket:
                return json.loads(cleaned[first_bracket : last_bracket + 1])
        raise


def generate_json_traced(
    prompt: str,
    *,
    tier: str = "flash",
    system: Optional[str] = None,
    mock: Optional[dict[str, Any]] = None,
    attempts_per_model: int = 2,
) -> tuple[Any, dict[str, Any]]:
    """Run a prompt and return (parsed_json, trace).

    trace = {source: "gemini"|"mock", model, attempts, fell_back, error}
    """
    if not config.has_gemini():
        if mock is not None:
            _record(False, "no_api_key")
            return mock, {"source": "mock", "model": None, "reason": "no_api_key"}
        raise GeminiUnavailable("GEMINI_API_KEY not set and no mock provided for this call.")

    client = _get_client()
    models = _candidates(tier)
    last_error = ""
    total_attempts = 0

    for model_index, model in enumerate(models):
        for attempt in range(attempts_per_model):
            total_attempts += 1
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "system_instruction": system,
                        "response_mime_type": "application/json",
                    },
                )
                data = _extract_json(response.text)
                _record(True)
                return data, {
                    "source": "gemini",
                    "model": model,
                    "attempts": total_attempts,
                    "fell_back": model_index > 0,
                }
            except Exception as exc:  # noqa: BLE001 — classify by message, SDK raises many types
                last_error = f"{type(exc).__name__}: {exc}"
                text = str(exc)
                if any(code in text for code in _MODEL_GONE):
                    break  # this model is gone; try the next one immediately
                wait = _backoff(exc, attempt) if any(code in text for code in _RETRYABLE) else None
                if wait is not None and attempt + 1 < attempts_per_model:
                    time.sleep(wait)
                    continue
                break  # non-retryable (bad request, auth) — move to next model

    if mock is not None:
        _record(False, "all_models_failed")
        return mock, {"source": "mock", "model": None, "reason": "all_models_failed", "error": last_error[:300]}
    raise GeminiUnavailable(last_error or "All Gemini models failed.")


def generate_json(
    prompt: str,
    *,
    tier: str = "flash",
    system: Optional[str] = None,
    mock: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Original contract, unchanged for existing agents."""
    data, _trace = generate_json_traced(prompt, tier=tier, system=system, mock=mock)
    return data


def map_concurrent(items: Iterable, worker: Callable, max_workers: Optional[int] = None) -> list:
    """Run `worker` over `items` with bounded concurrency, preserving order.

    Used by the audience simulator to fan cohort batches out without tripping
    the free-tier rate limit. Exceptions are returned in place, so one bad
    batch cannot abort the whole simulation.
    """
    items = list(items)
    if not items:
        return []
    workers = max(1, min(max_workers or config.GEMINI_MAX_CONCURRENCY, len(items)))
    tally = _tally.get()  # a worker thread starts with an empty context

    def guarded(item):
        token = _tally.set(tally) if tally is not None else None
        try:
            return worker(item)
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller as a value
            return exc
        finally:
            if token is not None:
                _tally.reset(token)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(guarded, items))
