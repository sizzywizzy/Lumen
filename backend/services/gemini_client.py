"""Gemini wrapper — the ONLY place LLM calls happen.

Guardrails (AGENT.md): Flash by default, Pro only for heavy reasoning, and
structured JSON output always (never parse prose). With no GEMINI_API_KEY the
caller gets its `mock` value back, so the whole pipeline demos offline.

Install `google-genai` (see requirements.txt) before setting a real key.

`generate_json` keeps its original signature so existing agents are unchanged.
`generate_json_traced` adds what the audience simulator needs: which model
actually served the call, whether it fell back, and whether the result is real
or mock — so the UI can never present mock output as a live model result.
"""
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, Optional

from core import config

_client = None
_client_lock = threading.Lock()

# Errors worth trying the next model / another attempt for.
_RETRYABLE = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL", "504", "DEADLINE")
_MODEL_GONE = ("404", "NOT_FOUND")


class GeminiUnavailable(RuntimeError):
    """Every candidate model failed. Carries the last error for reporting."""


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            from google import genai  # imported lazily so mock mode needs no install
            from google.genai import types

            if config.GEMINI_API_KEY:
                _client = genai.Client(
                    api_key=config.GEMINI_API_KEY,
                    http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_MS),
                )
            else:
                # Direct Google Cloud ADC via Vertex AI — no explicit API key needed
                _client = genai.Client(
                    vertexai=True,
                    project=config.GOOGLE_CLOUD_PROJECT,
                    location=config.GOOGLE_CLOUD_LOCATION,
                    http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_MS),
                )
    return _client


def _candidates(tier: str) -> list[str]:
    if config.GEMINI_API_KEY:
        preferred = config.GEMINI_FLASH_MODEL
        ordered = [preferred] + [m for m in config.GEMINI_FALLBACK_MODELS if m != preferred]
    else:
        # Vertex AI: enforce gemini-2.5-flash everywhere to conserve Google Cloud credits
        vertex_flash = getattr(config, "VERTEX_FLASH_MODEL", "gemini-2.5-flash")
        ordered = [vertex_flash]
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
                return _extract_json(response.text), {
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
                if any(code in text for code in _RETRYABLE) and attempt + 1 < attempts_per_model:
                    time.sleep(1.5 * (attempt + 1) + random.random())
                    continue
                break  # non-retryable (bad request, auth) — move to next model

    if mock is not None:
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


def generate_json_with_search(
    prompt: str,
    *,
    tier: str = "pro",
    system: Optional[str] = None,
    mock: Optional[dict[str, Any]] = None,
    attempts_per_model: int = 2,
) -> tuple[Any, dict[str, Any]]:
    """Run a prompt with Google Search grounding enabled via Google GenAI SDK.

    Uses types.Tool(google_search=types.GoogleSearch()) to allow the Google Cloud
    Gemini agent to crawl the web and ground talent discoveries in live web data.
    """
    if not config.has_gemini():
        if mock is not None:
            return mock, {"source": "mock", "model": None, "reason": "no_api_key"}
        raise GeminiUnavailable("GEMINI_API_KEY not set and no mock provided for this call.")

    from google.genai import types

    client = _get_client()
    models = _candidates(tier)
    last_error = ""
    total_attempts = 0
    search_tool = types.Tool(google_search=types.GoogleSearch())

    for model_index, model in enumerate(models):
        for attempt in range(attempts_per_model):
            total_attempts += 1
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        tools=[search_tool],
                    ),
                )
                return _extract_json(response.text), {
                    "source": "gemini_grounded",
                    "model": model,
                    "attempts": total_attempts,
                    "fell_back": model_index > 0,
                }
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                text = str(exc)
                if any(code in text for code in _MODEL_GONE):
                    break
                if any(code in text for code in _RETRYABLE) and attempt + 1 < attempts_per_model:
                    time.sleep(1.5 * (attempt + 1) + random.random())
                    continue
                break

    if mock is not None:
        reason = "adc_reauth_required" if "Reauthentication" in last_error else "all_models_failed"
        return mock, {"source": "mock", "model": None, "reason": reason, "error": last_error[:300]}
    raise GeminiUnavailable(last_error or "All Gemini models failed.")


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

    def guarded(item):
        try:
            return worker(item)
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller as a value
            return exc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(guarded, items))
