"""Skill-run persistence, on the same dual-mode contract as the other stores.

Supabase table `cn_skill_runs` when configured, otherwise JSON files under
backend/.state/skills/<project_id>/. A run record holds the stage checklist,
the result envelope and the provenance of every model call, so a producer can
tell a live Gemini answer from the offline fallback.
"""
import json
import os
import threading
from typing import Any, Optional

from core import config

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
        path = _dir(record["project_id"]) / f"{record['run_id']}.json"
        # The worker saves after every stage while the dashboard polls; write
        # to a sibling and rename so a reader never sees a half-written file.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
    return record


def get(project_id: str, run_id: str) -> Optional[dict[str, Any]]:
    if config.has_supabase():
        rows = (
            _get_supabase().table(TABLE).select("*")
            .eq("project_id", project_id).eq("run_id", run_id).execute().data
        )
        return rows[0] if rows else None
    path = _dir(project_id) / f"{run_id}.json"
    with _LOCK:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


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
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows
