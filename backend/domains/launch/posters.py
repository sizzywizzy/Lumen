"""Poster runs: one background thread per production at a time.

A poster's concept is a model call (two when PR review sends it back) and can
take a while, so it never holds up a request: the route answers 202 and the
Overview polls `status`, like advisor runs and audience simulations.

  start(project_id, user_id)        a new poster in a different random style
  start_if_missing(state, user_id)  after a pipeline run: makes one only when the
                                    stored poster was not made from this screenplay
  status(project_id)                what the Overview polls
"""
import threading
from typing import Any, Optional

from core.orchestrator.state import GlobalState
from domains.launch.agents import poster_artist
from services import poster_store, supabase_client

# Productions with a poster in progress, and each production's last failure
# until its next attempt. Kept in memory like advisor runs: the API runs as one
# process (render.yaml), and a restart just ends the attempt.
_ACTIVE: set[str] = set()
_FAILED: dict[str, str] = {}
_LOCK = threading.Lock()


class PosterBusy(RuntimeError):
    """A poster is already being made for this production."""


def run(project_id: str, user_id: Optional[str]) -> dict[str, Any]:
    """Make and store one poster now. The thread body; tests call it directly."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise LookupError(f"No project state for {project_id}.")
    current = poster_store.get(project_id) or {}
    baseline = len(state.event_log)
    record = poster_artist.paint(
        state, previous_style=(current.get("style") or {}).get("key", ""), started_by=user_id,
    )
    poster_store.save(record)
    # The model call took a while: merge the traffic onto whatever is stored
    # now instead of saving back the copy loaded before them.
    supabase_client.append_events(project_id, state.event_log[baseline:], state)
    return record


def _worker(project_id: str, user_id: Optional[str]) -> None:
    try:
        run(project_id, user_id)
    except Exception as exc:  # noqa: BLE001 — reported through status(), where the Overview shows it
        with _LOCK:
            _FAILED[project_id] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        with _LOCK:
            _ACTIVE.discard(project_id)


def _spawn(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def start(project_id: str, user_id: Optional[str]) -> None:
    """Make a new poster in the background. Raises PosterBusy if one is in progress."""
    with _LOCK:
        if project_id in _ACTIVE:
            raise PosterBusy(project_id)
        _ACTIVE.add(project_id)
        _FAILED.pop(project_id, None)
    _spawn(_worker, project_id, user_id)


def start_if_missing(state: GlobalState, user_id: Optional[str]) -> bool:
    """The automatic poster: one per screenplay. Returns whether one started."""
    fingerprint = str((state.script_context or {}).get("fingerprint") or "")
    current = poster_store.get(state.project_id)
    if current is not None and (current.get("script_fingerprint") or "") == fingerprint:
        return False
    try:
        start(state.project_id, user_id)
    except PosterBusy:
        return False
    return True


def public(record: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """What a member sees of a poster: no image bytes, prompts or model errors."""
    if not record:
        return None
    concept = record.get("concept") or {}
    trace = (record.get("provenance") or {}).get("concept") or {}
    written = trace.get("source") == "gemini"
    return {
        "poster_id": record.get("poster_id"),
        "created_at": record.get("created_at"),
        "style": record.get("style") or {},
        "tagline": concept.get("tagline", ""),
        "alt_text": concept.get("alt_text", ""),
        # the model that wrote the tagline and picked the colours from the script
        "written_by": trace.get("model") if written else None,
        # why the genre's tagline and colours stand in: no_api_key | all_models_failed | pr_blocked
        "fallback_reason": None if written else trace.get("reason") or "no_api_key",
        "script_fingerprint": record.get("script_fingerprint") or "",
    }


def status(project_id: str) -> dict[str, Any]:
    """none | painting | ready | failed, with the poster on the Overview (a
    failed attempt keeps the previous poster)."""
    record = poster_store.get(project_id)
    with _LOCK:
        painting = project_id in _ACTIVE
        error = None if painting else _FAILED.get(project_id)
    return {
        "status": "painting" if painting else "failed" if error else "ready" if record else "none",
        "error": error,
        "poster": public(record),
    }
