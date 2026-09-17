"""What state reads send back, and how they are cached.

A stored state holds the whole screenplay (up to 400k characters) and an event
log that grows with every run. The dashboard needs neither on every read, so
state responses leave the screenplay out and carry only the latest envelopes;
the Live Agent Terminal pages through /api/events for the rest.

Reads also carry an ETag, so a browser that already has the current copy gets
a bodiless 304 instead of the same document again.
"""
import hashlib
import json
from typing import Any

from fastapi import Request, Response

from core.orchestrator.state import GlobalState

STATE_EVENT_TAIL = 200  # envelopes a state read carries


def public_state(state: GlobalState) -> dict[str, Any]:
    """The state as the dashboard reads it."""
    body = state.model_dump(mode="json", exclude={"event_log"})
    body["script_context"].pop("raw_text", None)
    total = len(state.event_log)
    body["event_log"] = state.event_log[-STATE_EVENT_TAIL:]
    body["event_count"] = total
    body["event_offset"] = max(0, total - STATE_EVENT_TAIL)  # index of event_log[0] in the full log
    return body


def _tags(header: str) -> set[str]:
    return {tag.strip().removeprefix("W/") for tag in header.split(",") if tag.strip()}


def cached_json(request: Request, body: Any) -> Response:
    """`body` as JSON with an ETag; 304 when the caller already has it."""
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    etag = f'"{hashlib.sha256(payload).hexdigest()[:32]}"'
    # private: per member; no-cache: always revalidate, which the ETag makes cheap.
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if etag in _tags(request.headers.get("if-none-match", "")):
        return Response(status_code=304, headers=headers)
    return Response(payload, media_type="application/json", headers=headers)
