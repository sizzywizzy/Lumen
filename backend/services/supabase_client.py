"""GlobalState persistence.

Supabase (table `global_state`, columns: project_id text PK, state jsonb) when
configured; otherwise JSON files under backend/.state/ so local dev and the
demo need zero credentials. Same interface either way.
"""
import json
import os
import threading
from typing import Any, Optional

from core import config
from core.orchestrator.state import GlobalState

_supabase = None

# One lock per production around every read-modify-write of its state, shared
# by every background worker in this process (advisor runs, audience
# simulations) so none of them overwrites another's save with a stale copy.
_PROJECT_LOCKS: dict[str, threading.Lock] = {}
_PROJECT_LOCKS_GUARD = threading.Lock()


def project_lock(project_id: str) -> threading.Lock:
    with _PROJECT_LOCKS_GUARD:
        return _PROJECT_LOCKS.setdefault(project_id, threading.Lock())


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client  # lazy: only needed when configured
        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def save_state(state: GlobalState) -> None:
    if config.has_supabase():
        _get_supabase().table("global_state").upsert(
            {"project_id": state.project_id, "state": state.model_dump()}
        ).execute()
        return
    config.LOCAL_STATE_DIR.mkdir(exist_ok=True)
    path = config.LOCAL_STATE_DIR / f"{state.project_id}.json"
    # Write beside the target and rename, so a concurrent reader never sees a
    # half-written file (advisor runs save while the dashboard polls /api/state).
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_state(project_id: str) -> Optional[GlobalState]:
    if config.has_supabase():
        result = (
            _get_supabase().table("global_state")
            .select("state").eq("project_id", project_id).execute()
        )
        if result.data:
            return GlobalState.model_validate(result.data[0]["state"])
        return None
    path = config.LOCAL_STATE_DIR / f"{project_id}.json"
    if path.exists():
        return GlobalState.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return None


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
