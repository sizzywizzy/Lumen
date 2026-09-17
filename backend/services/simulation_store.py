"""Audience-simulation persistence — same dual-mode contract as the other stores.

Supabase table `cn_simulations` when configured, otherwise JSON files under
backend/.state/simulations/<project_id>/. Records are immutable once complete,
so two runs can be compared after a script revision.

The full 500-persona panel and the 500 individual responses are kept in a
sidecar file rather than the summary record: the dashboard only ever needs the
aggregates, but an auditor needs the raw rows.
"""
import json
import threading
from typing import Any, Optional

from core import config
from services import json_files

_LOCK = threading.RLock()
_supabase = None

TABLE = "cn_simulations"


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client

        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def _dir(project_id: str):
    path = config.LOCAL_STATE_DIR / "simulations" / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(record: dict[str, Any]) -> dict[str, Any]:
    """Upsert the summary record (no panel/response rows)."""
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table(TABLE).upsert(record).execute()
            return record
        json_files.write_json(_dir(record["project_id"]) / f"{record['simulation_id']}.json", record, indent=2)
    return record


def get(project_id: str, simulation_id: str) -> Optional[dict[str, Any]]:
    if config.has_supabase():
        rows = (
            _get_supabase().table(TABLE).select("*")
            .eq("project_id", project_id).eq("simulation_id", simulation_id).execute().data
        )
        return rows[0] if rows else None
    with _LOCK:
        return json_files.read_json(_dir(project_id) / f"{simulation_id}.json")


def list_for_project(project_id: str) -> list[dict[str, Any]]:
    """Newest first. Trimmed to what the history list needs."""
    if config.has_supabase():
        rows = (
            _get_supabase().table(TABLE).select("*")
            .eq("project_id", project_id).order("created_at", desc=True).execute().data
        )
    else:
        rows = []
        with _LOCK:
            for path in _dir(project_id).glob("SIM_*.json"):
                if path.name.endswith(".panel.json"):
                    continue
                try:
                    rows.append(json_files.read_json(path))
                except (json.JSONDecodeError, FileNotFoundError):
                    continue
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return rows


def save_panel(project_id: str, simulation_id: str, panel: dict[str, Any]) -> None:
    """Sidecar holding the personas and individual responses (audit trail)."""
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table(TABLE + "_panel").upsert(
                {"project_id": project_id, "simulation_id": simulation_id, "panel": panel}
            ).execute()
            return
        json_files.write_json(_dir(project_id) / f"{simulation_id}.panel.json", panel)


def get_panel(project_id: str, simulation_id: str) -> Optional[dict[str, Any]]:
    if config.has_supabase():
        rows = (
            _get_supabase().table(TABLE + "_panel").select("panel")
            .eq("project_id", project_id).eq("simulation_id", simulation_id).execute().data
        )
        return rows[0]["panel"] if rows else None
    with _LOCK:
        return json_files.read_json(_dir(project_id) / f"{simulation_id}.panel.json")
