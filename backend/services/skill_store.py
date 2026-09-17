"""Skill-run persistence, on the same dual-mode contract as the other stores.

Supabase table `cn_skill_runs` when configured, otherwise JSON files under
backend/.state/skills/<project_id>/. A run record holds the stage checklist,
the result envelope and the provenance of every model call, so a producer can
tell a live Gemini answer from the offline fallback.
"""
import json
import threading
from typing import Any, Optional

from core import config
from services import json_files

_LOCK = threading.RLock()
_supabase = None

TABLE = "cn_skill_runs"


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client

        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def _dir(project_id: str):
    path = config.LOCAL_STATE_DIR / "skills" / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(record: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table(TABLE).upsert(record).execute()
            return record
        # The worker saves after every stage while the dashboard polls; the
        # write is atomic so a reader never sees a half-written file.
        json_files.write_json(_dir(record["project_id"]) / f"{record['run_id']}.json", record, indent=2, default=str)
    return record


def get(project_id: str, run_id: str) -> Optional[dict[str, Any]]:
    if config.has_supabase():
        rows = (
            _get_supabase().table(TABLE).select("*")
            .eq("project_id", project_id).eq("run_id", run_id).execute().data
        )
        return rows[0] if rows else None
    with _LOCK:
        return json_files.read_json(_dir(project_id) / f"{run_id}.json")


def list_for_project(project_id: str) -> list[dict[str, Any]]:
    """Newest first."""
    if config.has_supabase():
        rows = (
            _get_supabase().table(TABLE).select("*")
            .eq("project_id", project_id).order("created_at", desc=True).execute().data
        )
        return rows or []
    rows = []
    with _LOCK:
        for path in _dir(project_id).glob("RUN_*.json"):
            try:
                rows.append(json_files.read_json(path))
            except (json.JSONDecodeError, FileNotFoundError):
                continue
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows
