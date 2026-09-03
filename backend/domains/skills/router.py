"""Agent-skill endpoints. Mounted under /api/skills.

  GET  /api/skills                         every SKILL.md, with its input controls
  GET  /api/skills/{name}                  one skill with its instructions
  POST /api/skills/{name}/run/{project_id} start a run (producer/owner)
  GET  /api/skills/runs/{project_id}       run history, newest first (any role)
  GET  /api/skills/runs/{project_id}/{run_id}

Runs execute on a background thread and are polled, like audience simulations:
a live run can make several Gemini calls and take a minute or more, so the
dashboard shows real per-stage progress instead of blocking a request.
"""
import threading
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.audience import personas as panel_lib
from core.auth.deps import current_user, require_member, require_producer
from core.auth.models import Membership, User
from core.auth.security import new_id
from core.skills import registry
from core.skills.registry import Skill, SkillNotFound
from domains.skills import agents
from services import skill_store, supabase_client

router = APIRouter(prefix="/api/skills", tags=["skills"])

# (project_id, skill) pairs with a thread running right now. One run per skill
# per production at a time; anything stored as "running" that is not in here
# was interrupted by a restart and is reported as such.
_ACTIVE: set[tuple[str, str]] = set()
_ACTIVE_RUNS: set[str] = set()
_LOCK = threading.Lock()
# One lock per production around every read-modify-write of its GlobalState,
# so two advisors (or an advisor and a producer's edit) cannot overwrite each
# other's changes. The slow model step runs outside it.
_PROJECT_LOCKS: dict[str, threading.Lock] = {}

STATUSES = ("pending", "running", "complete", "failed")


class SkillRunParams(BaseModel):
    """Per-run overrides. Everything is optional; SKILL.md metadata supplies the
    defaults. Unknown keys are rejected so a typo cannot silently do nothing."""
    model_config = ConfigDict(extra="forbid")

    panel_size: Optional[int] = Field(default=None, ge=20, le=1000)
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    markets: Optional[list[str]] = Field(default=None, max_length=12)

    @field_validator("markets")
    @classmethod
    def known_market_codes(cls, value):
        if value is None:
            return value
        codes = [str(code).strip().upper() for code in value if str(code).strip()]
        unknown = [code for code in codes if code not in panel_lib.MARKETS]
        if unknown:
            raise ValueError(f"Unknown market code(s): {', '.join(unknown)}.")
        if not codes:
            raise ValueError("Pick at least one market.")
        return codes


class SkillRunRequest(BaseModel):
    params: SkillRunParams = Field(default_factory=SkillRunParams)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _public_run(record: dict[str, Any]) -> dict[str, Any]:
    """What the API returns: the stored record minus the server traceback."""
    return {k: v for k, v in record.items() if k != "traceback"}


def _public_skill(skill: Skill) -> dict[str, Any]:
    return {
        **skill.public(),
        "inputs": agents.input_schema(skill),
        "runnable": skill.name in agents.RUNNERS,
        "stages": [{"key": k, "label": l} for k, l in agents.STAGES.get(skill.name, [])],
    }


def _project_lock(project_id: str) -> threading.Lock:
    with _LOCK:
        return _PROJECT_LOCKS.setdefault(project_id, threading.Lock())


def _skeleton(skill: Skill, project_id: str, params: dict, started_by: str) -> dict[str, Any]:
    return {
        "run_id": new_id("RUN").upper(),
        "project_id": project_id,
        "skill": skill.name,
        "title": skill.title,
        "agent": skill.agent,
        "status": "running",
        "created_at": _now(),
        "completed_at": None,
        "started_by": started_by,
        "params": params,
        "skill_version": skill.version,
        "skill_fingerprint": skill.fingerprint,
        "stages": [
            {"key": key, "label": label, "status": "pending", "detail": {}}
            for key, label in agents.STAGES.get(skill.name, [("advise", "Ran the skill")])
        ],
        "result": None,
        "provenance": None,
        "error": None,
    }


def _worker(record: dict, skill: Skill, params: dict) -> None:
    project_id = record["project_id"]

    def stage(key: str, status: str, **detail: Any) -> None:
        for item in record["stages"]:
            if item["key"] == key:
                item["status"] = status if status in STATUSES else "complete"
                if detail:
                    item["detail"] = detail
                item["started_at" if status == "running" else "finished_at"] = _now()
        skill_store.save(record)

    lock = _project_lock(project_id)
    try:
        # 1. Under the project lock: read the state and, when the skill needs
        #    phase output that is not there yet, run those phase agents and
        #    persist the result at once, so two runs never seed the same pool.
        with lock:
            state = supabase_client.load_state(project_id)
            if state is None:
                raise agents.SkillInputError(f"No project state for {project_id}.")
            if agents.prepare_skill(skill, state, params, stage):
                supabase_client.save_state(state)
            baseline = len(state.event_log)

        # 2. Outside the lock: the slow advisory step. It only appends envelopes.
        outcome = agents.run_skill(skill, state, params, stage, prepared=True)

        # 3. Under the lock again: merge this run's envelopes onto whatever the
        #    stored state is now (another advisor or a producer may have saved
        #    in the meantime) rather than overwriting it with our stale copy.
        with lock:
            latest = supabase_client.load_state(project_id) or state
            latest.event_log.extend(state.event_log[baseline:])
            supabase_client.save_state(latest)
        record.update({
            "status": "complete",
            "completed_at": _now(),
            "result": outcome["result"],
            "provenance": outcome["provenance"],
        })
    except agents.SkillInputError as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 — recorded on the run, never swallowed
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"[:500]
        record["traceback"] = traceback.format_exc()[-1500:]
    finally:
        for item in record["stages"]:
            if item["status"] == "running":
                item["status"] = "failed"
        if record["status"] != "complete":
            record["completed_at"] = _now()
        skill_store.save(record)
        with _LOCK:
            _ACTIVE.discard((project_id, skill.name))
            _ACTIVE_RUNS.discard(record["run_id"])


# ------------------------------------------------------------------ routes --


@router.get("")
def list_skills(_user: User = Depends(current_user)):
    return {"skills": [_public_skill(s) for s in registry.load_all()]}


@router.get("/runs/{project_id}")
def list_runs(project_id: str, _member: Membership = Depends(require_member)):
    runs = skill_store.list_for_project(project_id)
    with _LOCK:
        active_runs = set(_ACTIVE_RUNS)
    for run in runs:
        if run.get("status") == "running" and run["run_id"] not in active_runs:
            run["status"] = "failed"
            run["error"] = "Interrupted by a server restart. Run the advisor again."
            run["completed_at"] = run.get("completed_at") or _now()
            for item in run.get("stages", []):
                if item["status"] == "running":
                    item["status"] = "failed"
            skill_store.save(run)
    return {"runs": [_public_run(r) for r in runs]}


@router.get("/runs/{project_id}/{run_id}")
def get_run(project_id: str, run_id: str, _member: Membership = Depends(require_member)):
    record = skill_store.get(project_id, run_id)
    if record is None:
        raise HTTPException(404, "No such advisor run on this production.")
    return _public_run(record)


@router.get("/{name}")
def get_skill(name: str, _user: User = Depends(current_user)):
    try:
        return {"skill": _public_skill(registry.get(name))}
    except SkillNotFound:
        raise HTTPException(404, f"No skill named '{name}'.") from None


@router.post("/{name}/run/{project_id}", status_code=202)
def run_skill(
    name: str,
    project_id: str,
    req: SkillRunRequest = SkillRunRequest(),
    membership: Membership = Depends(require_producer),
):
    try:
        skill = registry.get(name)
    except SkillNotFound:
        raise HTTPException(404, f"No skill named '{name}'.") from None
    if skill.name not in agents.RUNNERS:
        raise HTTPException(501, f"No agent implements the '{skill.name}' skill yet.")
    if supabase_client.load_state(project_id) is None:
        raise HTTPException(404, f"No state for {project_id}. Start the production on Script Intake first.")

    params = req.params.model_dump(exclude_none=True)
    with _LOCK:
        if (project_id, skill.name) in _ACTIVE:
            raise HTTPException(409, f"{skill.title} is already working on this production.")
        record = _skeleton(skill, project_id, params, membership.user_id)
        _ACTIVE.add((project_id, skill.name))
        _ACTIVE_RUNS.add(record["run_id"])
    skill_store.save(record)
    threading.Thread(target=_worker, args=(record, skill, params), daemon=True).start()
    return _public_run(record)
