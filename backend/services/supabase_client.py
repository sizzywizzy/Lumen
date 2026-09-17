"""GlobalState persistence.

Supabase (table `global_state`, columns: project_id text PK, state jsonb) when
configured; otherwise JSON files under backend/.state/ so local dev and the
demo need zero credentials. Same interface either way.
"""
import threading
from typing import Any, Callable, Optional, TypeVar

from core import config
from core.orchestrator.state import GlobalState
from services import json_files

_supabase = None
_FILES = threading.RLock()  # local JSON: reads wait for a write's rename

# One lock per production around every read-modify-write of its state, shared
# by every request handler and background worker in this process (pipeline
# runs, advisor runs, audience simulations, posters) so none of them
# overwrites another's save with a stale copy.
_PROJECT_LOCKS: dict[str, threading.RLock] = {}
_PROJECT_LOCKS_GUARD = threading.Lock()

T = TypeVar("T")


def project_lock(project_id: str) -> threading.RLock:
    with _PROJECT_LOCKS_GUARD:
        return _PROJECT_LOCKS.setdefault(project_id, threading.RLock())


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client  # lazy: only needed when configured
        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def _path(project_id: str):
    return config.LOCAL_STATE_DIR / f"{project_id}.json"


def save_state(state: GlobalState) -> None:
    if config.has_supabase():
        _get_supabase().table("global_state").upsert(
            {"project_id": state.project_id, "state": state.model_dump(mode="json")}
        ).execute()
        return
    with _FILES:
        json_files.write_text(_path(state.project_id), state.model_dump_json(indent=2))


def load_state(project_id: str) -> Optional[GlobalState]:
    if config.has_supabase():
        result = (
            _get_supabase().table("global_state")
            .select("state").eq("project_id", project_id).execute()
        )
        if result.data:
            return GlobalState.model_validate(result.data[0]["state"])
        return None
    with _FILES:
        raw = json_files.read_json(_path(project_id))
    return GlobalState.model_validate(raw) if raw is not None else None


class StateMissing(LookupError):
    """The production has no stored state."""


def update_state(project_id: str, change: Callable[[GlobalState], T]) -> tuple[GlobalState, T]:
    """Load, change and save a production's state under its lock.

    Every request that edits the state goes through here, so two producers
    saving at once (a candidate decision and an expense, say) each apply their
    edit to the other's result instead of the last save winning. `change`
    edits the state in place and may raise to abort without saving. Returns
    the saved state and whatever `change` returned.
    """
    with project_lock(project_id):
        state = load_state(project_id)
        if state is None:
            raise StateMissing(project_id)
        outcome = change(state)
        save_state(state)
    return state, outcome


def append_events(project_id: str, envelopes: list[dict[str, Any]], fallback: GlobalState) -> GlobalState:
    """Merge a background run's A2A envelopes onto the stored state.

    A long run works on a copy of the state loaded minutes earlier and only
    appends to its event log. Saving that copy back would overwrite anything
    saved in the meantime (a candidate decision, an expense, a script upload),
    so under the project lock the current state is reloaded, the envelopes are
    appended to it and that is saved. `fallback` is used only when nothing is
    stored any more.
    """
    with project_lock(project_id):
        latest = load_state(project_id) or fallback
        latest.event_log.extend(envelopes)
        save_state(latest)
    return latest


def list_projects() -> list[str]:
    if config.has_supabase():
        result = _get_supabase().table("global_state").select("project_id").execute()
        return [row["project_id"] for row in result.data]
    if not config.LOCAL_STATE_DIR.exists():
        return []
    return [p.stem for p in sorted(config.LOCAL_STATE_DIR.glob("PROJ_*.json"))]
