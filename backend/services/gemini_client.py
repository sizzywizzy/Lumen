"""Gemini wrapper — the ONLY place LLM calls happen.

Guardrails (AGENT.md): Flash by default, Pro only for heavy reasoning, and
structured JSON output always (never parse prose). With no GEMINI_API_KEY (and
no Vertex opt-in, see core/config.py) the caller gets its `mock` value back,
so the whole pipeline demos offline.

Install `google-genai` (see requirements.txt) before setting a real key.

`generate_json` keeps its original signature so existing agents are unchanged.
`generate_json_traced` adds what the audience simulator needs: which model
actually served the call, whether it fell back, and whether the result is real
or mock — so the UI can never present mock output as a live model result.
`generate_image_traced` paints the production's poster with the same trace.
"""
import base64
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
            elif config.has_vertex():
                # Vertex AI on Google Cloud credentials, switched on explicitly
                # with GOOGLE_GENAI_USE_VERTEXAI and GOOGLE_CLOUD_PROJECT.
                _client = genai.Client(
                    vertexai=True,
                    project=config.GOOGLE_CLOUD_PROJECT,
                    location=config.GOOGLE_CLOUD_LOCATION,
                    http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_MS),
                )
            else:
                raise GeminiUnavailable(
                    "No Gemini access: set GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=true "
                    "with GOOGLE_CLOUD_PROJECT and gcloud credentials."
                )
    return _client


def _candidates(tier: str) -> list[str]:
    """Models to try, in order, for a tier: the tier's configured model first,
    then the fallback chain, so a retired or overloaded model degrades the run
    instead of ending it (AGENT.md: Flash by default, Pro for heavy reasoning)."""
    if config.GEMINI_API_KEY:
        preferred = config.GEMINI_PRO_MODEL if tier == "pro" else config.GEMINI_FLASH_MODEL
        chain = [preferred, config.GEMINI_FLASH_MODEL, *config.GEMINI_FALLBACK_MODELS]
    else:
        # Vertex AI via ADC: the VERTEX_* settings default to Flash to conserve credits.
        preferred = config.VERTEX_PRO_MODEL if tier == "pro" else config.VERTEX_FLASH_MODEL
        chain = [preferred, config.VERTEX_FLASH_MODEL]
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


def _image_candidates() -> list[str]:
    """Image models to try, in order: the configured one, then its fallbacks."""
    if config.GEMINI_API_KEY:
        chain = [config.GEMINI_IMAGE_MODEL, *config.GEMINI_IMAGE_FALLBACK_MODELS]
    else:
        chain = [config.VERTEX_IMAGE_MODEL]
    return list(dict.fromkeys(model for model in chain if model))


def _first_image(response: Any) -> tuple[Optional[bytes], str, str]:
    """(bytes, mime_type, why_not) for the first inline image in a reply. A reply
    without one says why when it can: a blocked prompt or a finish reason such
    as IMAGE_SAFETY."""
    why = ""
    block = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
    if block:
        why = f"prompt blocked ({getattr(block, 'value', block)})"
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            blob = getattr(part, "inline_data", None)
            data = getattr(blob, "data", None)
            mime = str(getattr(blob, "mime_type", "") or "")
            if data and mime.startswith("image/"):
                return (base64.b64decode(data) if isinstance(data, str) else bytes(data)), mime, ""
        reason = getattr(candidate, "finish_reason", None)
        if reason and not why:
            why = f"finished with {getattr(reason, 'value', reason)}"
    return None, "", why or "the reply held no image"


def generate_image_traced(
    prompt: str,
    *,
    aspect_ratio: str = "2:3",
    attempts_per_model: int = 2,
) -> tuple[Optional[bytes], str, dict[str, Any]]:
    """Paint one image and return (image_bytes, mime_type, trace).

    The bytes are None when no model is configured or every image model failed;
    the trace says which, so the caller can draw its own stand-in and label it
    as one. trace = {source: "gemini"|"mock", model, attempts, fell_back, reason, error}
    """
    if not config.has_gemini():
        return None, "", {"source": "mock", "model": None, "reason": "no_api_key"}

    from google.genai import types

    client = _get_client()
    last_error = ""
    total_attempts = 0
    image_config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
    )

    for model_index, model in enumerate(_image_candidates()):
        for attempt in range(attempts_per_model):
            total_attempts += 1
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=image_config)
            except Exception as exc:  # noqa: BLE001 — classified by message, like the JSON calls
                last_error = f"{type(exc).__name__}: {exc}"
                text = str(exc)
                if any(code in text for code in _MODEL_GONE):
                    break
                if any(code in text for code in _RETRYABLE) and attempt + 1 < attempts_per_model:
                    time.sleep(1.5 * (attempt + 1) + random.random())
                    continue
                break
            data, mime, why = _first_image(response)
            if data is not None:
                return data, mime, {
                    "source": "gemini",
                    "model": model,
                    "attempts": total_attempts,
                    "fell_back": model_index > 0,
                }
            # A safety block or a text-only reply: the same model rarely paints
            # on a second ask, so the next model gets the prompt instead.
            last_error = f"{model}: {why}"
            break

    return None, "", {"source": "mock", "model": None, "reason": "all_models_failed", "error": last_error[:300]}


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
