"""GlobalState persistence.

Supabase (table `global_state`, columns: project_id text PK, state jsonb) when
configured; otherwise JSON files under backend/.state/ so local dev and the
demo need zero credentials. Same interface either way.
"""
import json
from typing import Optional

from core import config
from core.orchestrator.state import GlobalState

_supabase = None


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
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")


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


def list_projects() -> list[str]:
    if config.has_supabase():
        result = _get_supabase().table("global_state").select("project_id").execute()
        return [row["project_id"] for row in result.data]
    if not config.LOCAL_STATE_DIR.exists():
        return []
    return [p.stem for p in sorted(config.LOCAL_STATE_DIR.glob("PROJ_*.json"))]
