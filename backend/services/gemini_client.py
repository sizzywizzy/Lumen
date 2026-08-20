"""Gemini wrapper — the ONLY place LLM calls happen.

Guardrails (AGENT.md): Flash by default, Pro only for heavy reasoning, and
structured JSON output always (never parse prose). With no GEMINI_API_KEY the
caller gets its `mock` value back, so the whole pipeline demos offline.

Install `google-genai` (see requirements.txt) before setting a real key.
"""
import json
from typing import Any, Optional

from core import config

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai  # imported lazily so mock mode needs no install
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def generate_json(
    prompt: str,
    *,
    tier: str = "flash",
    system: Optional[str] = None,
    mock: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run a prompt and return parsed JSON.

    tier: "flash" (default, bulk work) or "pro" (final synthesis, aggregation, recut).
    mock: returned as-is when no API key is configured — every agent must provide one
          so the demo runs without credentials.
    """
    if not config.has_gemini():
        if mock is not None:
            return mock
        raise RuntimeError("GEMINI_API_KEY not set and no mock provided for this call.")

    model = config.GEMINI_PRO_MODEL if tier == "pro" else config.GEMINI_FLASH_MODEL
    client = _get_client()
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={
            "system_instruction": system,
            "response_mime_type": "application/json",
        },
    )
    return json.loads(response.text)
