"""Pipeline runs on a background thread, one per production at a time.

A live run makes dozens of model calls and can take minutes, so every route
that starts one (the full pipeline, casting, production, launch) answers 202
and the dashboard polls `status`, the way advisor runs, simulations and
posters already work. Progress and outcome are kept in this process's memory:
the API runs as one process (render.yaml), and a restart simply ends the run
and leaves the stored state as it was.

A finished run is merged onto the state stored at that moment, under the
production's lock (core/orchestrator/merge.py), so nothing a person saved
while it ran is lost.
"""
import copy
import threading
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException

from core.auth.security import new_id
from core.orchestrator import merge
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from services import script_intake, supabase_client

# Which phases each kind of run covers.
SCOPES: dict[str, tuple[str, str]] = {
    "pipeline": ("phase1", "phase6"),
    "casting": ("phase1", "phase2"),
    "production": ("phase3", "phase4"),
    "launch": ("phase5", "phase6"),
}

StateFn = Callable[[GlobalState], Any]

_ACTIVE: dict[str, dict[str, Any]] = {}  # project_id -> the run in flight
_LAST: dict[str, dict[str, Any]] = {}    # project_id -> the last finished run
_LOCK = threading.Lock()


class PipelineBusy(RuntimeError):
    """A pipeline run is already in flight for this production."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _spawn(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def _update(job: dict, **changes: Any) -> None:
    with _LOCK:
        job.update(changes)


def _phase_status(job: dict, key: str, status: str) -> None:
    with _LOCK:
        for phase in job["phases"]:
            if phase["key"] == key:
                phase["status"] = status


def _worker(job: dict, begin: StateFn, inputs: Optional[StateFn], after: Optional[StateFn],
            summary: Optional[Callable[[GlobalState], dict]]) -> None:
    project_id = job["project_id"]
    orchestrator = Orchestrator()
    nodes = {node.key: node for node in orchestrator.nodes}
    start, end = SCOPES[job["scope"]]
    ran = []

    def on_phase(key: str, status: str) -> None:
        _phase_status(job, key, status)
        if status in ("complete", "halted"):
            ran.append(nodes[key])

    merged = None
    try:
        stored = supabase_client.load_state(project_id)
        if stored is None:
            if job["scope"] != "pipeline":
                raise LookupError(f"No state for {project_id}. Drop in a script first.")
            stored = GlobalState(project_id=project_id)  # the full pipeline starts from scratch anyway
        stored_len = len(stored.event_log)
        state = orchestrator.run(begin(stored), start=start, end=end, on_phase=on_phase)
        fresh = job["scope"] == "pipeline"
        with supabase_client.project_lock(project_id):
            latest = supabase_client.load_state(project_id) or stored
            log_start = 0 if fresh else len(latest.event_log)
            merged = merge.merge_run(latest, state, ran, stored_len,
                                     keep_context=script_intake.INTAKE_KEYS, fresh=fresh)
            if inputs:
                inputs(merged)
            supabase_client.save_state(merged)
        _update(job, status="complete", log_start=log_start, events=len(merged.event_log),
                summary=summary(merged) if summary else {})
    except HTTPException as exc:
        _update(job, status="failed", error=str(exc.detail))
    except Exception as exc:  # noqa: BLE001 — recorded on the run, never swallowed
        print(f"[lumen] pipeline run {job['job_id']} failed:\n{traceback.format_exc()}", flush=True)
        _update(job, status="failed", error=f"{type(exc).__name__}: {exc}"[:500])
    finally:
        with _LOCK:
            if job["status"] == "running":
                job.update(status="failed", error="The run stopped unexpectedly.")
            for phase in job["phases"]:
                if phase["status"] == "running":
                    phase["status"] = "failed"
            job["finished_at"] = _now()
            _ACTIVE.pop(project_id, None)
            _LAST[project_id] = job
    if merged is not None and after is not None and job["status"] == "complete":
        try:
            after(merged)
        except Exception as exc:  # noqa: BLE001 — the plan is saved; a follow-up is best effort
            print(f"[lumen] after-run step for {project_id} failed: {exc}", flush=True)


def start(
    project_id: str,
    scope: str,
    *,
    started_by: Optional[str],
    begin: Optional[StateFn] = None,
    inputs: Optional[StateFn] = None,
    after: Optional[StateFn] = None,
    summary: Optional[Callable[[GlobalState], dict]] = None,
) -> dict[str, Any]:
    """Start a run of `scope`'s phases and return its record.

    begin(stored)  the state the phases start from; the stored copy by default
    inputs(state)  the run's own inputs (locality, dates, budget), applied again
                   to the merged result so a setting saved meanwhile cannot undo them
    after(state)   a follow-up once the result is saved (the poster)
    summary(state) what the finished record reports

    Raises PipelineBusy when a run is already in flight for the production.
    """
    first, last = SCOPES[scope]
    job = {
        "job_id": new_id("JOB").upper(),
        "project_id": project_id,
        "scope": scope,
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "started_by": started_by,
        "phases": [{"key": node.key, "title": node.title, "status": "pending"}
                   for node in Orchestrator().span(first, last)],
        "log_start": None,
        "events": None,
        "summary": None,
        "error": None,
    }
    with _LOCK:
        if project_id in _ACTIVE:
            raise PipelineBusy(project_id)
        _ACTIVE[project_id] = job
    _spawn(_worker, job, begin or (lambda stored: stored), inputs, after, summary)
    return status(project_id)


def status(project_id: str) -> dict[str, Any]:
    """The run in flight, else the last one to finish, else {"status": "idle"}."""
    with _LOCK:
        job = _ACTIVE.get(project_id) or _LAST.get(project_id)
        return copy.deepcopy(job) if job else {"project_id": project_id, "status": "idle"}


def busy(project_id: str) -> bool:
    with _LOCK:
        return project_id in _ACTIVE
