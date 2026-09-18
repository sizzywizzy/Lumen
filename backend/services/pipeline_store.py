"""Pipeline-run persistence, on the same dual-mode contract as the other stores.

Supabase table `cn_pipeline_runs` when configured, otherwise JSON files under
backend/.state/pipeline/<project_id>/. One record per run: the phase
checklist, what it merged and how it ended.

The record used to live only in the API process's memory, so a restart during
a run left no trace of it — the stored state was untouched and the page could
only say the run had vanished. It is written here at every phase change
instead, so after a restart the production's last run is still there to report.

Keeping the record is bookkeeping, never the job: a store that cannot be
written (a database where `backend/schema_state.sql` has not been run again
since `cn_pipeline_runs` was added, say) is reported once and then ignored, so
the run itself still finishes and still saves its plan.
"""
import json
import threading
from typing import Any, Optional

from core import config
from services import json_files

_LOCK = threading.RLock()
_supabase = None
_complained: set[str] = set()

TABLE = "cn_pipeline_runs"


def _shrug(what: str, exc: Exception) -> None:
    """Say once per process that the history is not being kept, and carry on."""
    if what not in _complained:
        _complained.add(what)
        print(f"[lumen] pipeline run history unavailable ({what}: {type(exc).__name__}: {exc}). "
              f"Runs still work; re-run backend/schema_state.sql to keep their records.", flush=True)


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client

        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def _dir(project_id: str):
    path = config.LOCAL_STATE_DIR / "pipeline" / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(record: dict[str, Any]) -> dict[str, Any]:
    try:
        with _LOCK:
            if config.has_supabase():
                _get_supabase().table(TABLE).upsert(record).execute()
                return record
            # Written after every phase while the dashboard polls; the write is
            # atomic so a reader never sees a half-written file.
            json_files.write_json(_dir(record["project_id"]) / f"{record['job_id']}.json",
                                  record, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001 — the run matters, its record does not
        _shrug("save", exc)
    return record


def latest(project_id: str) -> Optional[dict[str, Any]]:
    """The production's most recently started run, or None if it never ran (or
    if the store cannot be read, which reads the same as never having run)."""
    try:
        if config.has_supabase():
            rows = (
                _get_supabase().table(TABLE).select("*")
                .eq("project_id", project_id).order("started_at", desc=True).limit(1).execute().data
            )
            return rows[0] if rows else None
        with _LOCK:
            records = []
            for path in _dir(project_id).glob("JOB_*.json"):
                try:
                    records.append(json_files.read_json(path))
                except (json.JSONDecodeError, FileNotFoundError):
                    continue
    except Exception as exc:  # noqa: BLE001 — a missing history is not an error to the caller
        _shrug("read", exc)
        return None
    records = [r for r in records if r]
    return max(records, key=lambda r: r.get("started_at", ""), default=None)
