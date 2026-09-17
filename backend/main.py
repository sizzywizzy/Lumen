"""FastAPI entrypoint for Lumen.

    cd backend
    uvicorn main:app --reload --port 8000

Mounts one router per team workspace plus the shared pipeline, state and event
endpoints. Pipeline runs work in the background (poll /api/pipeline/status),
and the Live Agent Terminal pages through /api/events.
"""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from core import config
from core.auth.deps import current_user, membership_for, require_member
from core.auth.models import User, role_at_least
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import BudgetState, GlobalState
from core.responses import cached_json, public_state
from core.shoot_window import IsoDate, settings_problem, window_problem
from domains.audience.router import router as audience_router
from domains.auth.router import router as auth_router
from domains.casting.router import router as casting_router
from domains.launch import posters
from domains.launch.router import router as launch_router
from domains.pipeline import jobs
from domains.production.router import router as production_router
from domains.skills.router import router as skills_router
from services import auth_store, script_intake, supabase_client


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Refuse to start on a configuration error the host cannot heal.

    `config.has_supabase()` raises when LUMEN_STATE_BACKEND=supabase is set
    without credentials or without the `supabase` package. Both mean every
    request would 500, so the deploy should fail here and be reported as
    failed rather than go live and serve errors.

    Connectivity is deliberately not checked at boot: a Supabase blip would
    otherwise turn a restart into a crash loop. /api/health probes that on
    every call instead.
    """
    config.has_supabase()
    yield


app = FastAPI(title="Lumen", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,  # "*" unless LUMEN_CORS_ORIGINS names the deployed frontend
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)

app.include_router(auth_router)
app.include_router(audience_router)
app.include_router(casting_router)
app.include_router(production_router)
app.include_router(launch_router)
app.include_router(skills_router)

EVENT_PAGE_MAX = 500  # envelopes per /api/events page


class InitRequest(BaseModel):
    """Intake inputs. Anything left out keeps the production's saved value."""
    project_id: str = "PROJ_NEON_NIGHTS"
    budget_usd: Optional[float] = Field(default=None, gt=0)  # total production budget from the intake form
    locality: Optional[str] = Field(default=None, max_length=120)
    director_notes: Optional[str] = Field(default=None, max_length=4000)
    start_date: IsoDate = None  # first shoot day, YYYY-MM-DD
    end_date: IsoDate = None  # planned wrap, YYYY-MM-DD

    @model_validator(mode="after")
    def _check_window(self):
        problem = window_problem(self.start_date, self.end_date)
        if problem:
            raise ValueError(problem)
        return self


def _apply_inputs(req: InitRequest, state: GlobalState) -> None:
    """Write the inputs the request actually sent onto `state`."""
    if req.locality:
        state.locality = req.locality
        state.script_context["locality"] = req.locality
    if req.director_notes is not None:
        state.director_notes = req.director_notes
        state.script_context["director_notes"] = req.director_notes
    if req.budget_usd:
        state.budget_state.cap = req.budget_usd
    # Stored as ISO strings: the Supabase path saves JSON, which has no date type.
    if req.start_date:
        state.schedule.shoot_settings["start_date"] = req.start_date.isoformat()
    if req.end_date:
        state.schedule.shoot_settings["end_date"] = req.end_date.isoformat()


def _new_state(req: InitRequest, stored: Optional[GlobalState]) -> GlobalState:
    """A fresh pipeline state that keeps the production's inputs. Each input comes
    from the request, else from what was saved before, else the default; the
    screenplay, schedule rules and expenses carry over from the saved state."""
    loc = req.locality or (stored.locality if stored else "") or "Los Angeles, CA"
    notes = req.director_notes if req.director_notes is not None else (stored.director_notes if stored else "")
    cap = req.budget_usd or (stored.budget_state.cap if stored else 0) or config.DEFAULT_BUDGET_USD
    state = GlobalState(
        project_id=req.project_id,
        budget_state=BudgetState(cap=cap),
        locality=loc,
        director_notes=notes,
        script_context={"locality": loc, "director_notes": notes},
    )
    if stored is not None:
        state.script_context.update(
            {k: v for k, v in (stored.script_context or {}).items() if k in script_intake.INTAKE_KEYS}
        )
        state.schedule.shoot_settings = dict(stored.schedule.shoot_settings or {})
        state.schedule.director_constraints = dict(stored.schedule.director_constraints or {})
        state.budget_state.expenses = list(stored.budget_state.expenses)
    _apply_inputs(req, state)
    problem = settings_problem(state.schedule.shoot_settings)
    if problem:  # e.g. a new wrap date earlier than the saved first shoot day
        raise HTTPException(422, problem)
    return state


def _require_producer(user: User, project_id: str) -> None:
    if not role_at_least(membership_for(user, project_id).role, "producer"):
        raise HTTPException(403, "Your role on this production is read-only.")


def _pipeline_summary(state: GlobalState) -> dict:
    return {
        "project_id": state.project_id,
        "casting_status": state.casting_status,
        "tomatometer": state.audience_report.tomatometer,
        "events": len(state.event_log),
        "human_escalations": [e.model_dump() for e in state.human_escalations],
    }


@app.get("/api/health")
def health(response: Response):
    """Liveness plus the state store, because this is the host's health gate.

    503 when the configured store cannot be read, so a deploy with the wrong
    Supabase key — or one where backend/schema_*.sql was never run — is caught
    here instead of by the first producer who tries to sign up.
    """
    store = supabase_client.store_status()
    if not store["reachable"]:
        response.status_code = 503
    return {
        "status": "ok" if store["reachable"] else "degraded",
        "phases": Orchestrator().phase_keys(),
        "store": store,
    }


@app.post("/api/pipeline/init")
def init_pipeline(req: InitRequest, user: User = Depends(current_user)):
    """Create (or reset) a project's GlobalState. Producer or owner only."""
    _require_producer(user, req.project_id)
    if jobs.busy(req.project_id):
        raise HTTPException(409, "Lumen is still planning this production. Wait for that run to finish.")
    with supabase_client.project_lock(req.project_id):
        state = _new_state(req, supabase_client.load_state(req.project_id))
        supabase_client.save_state(state)
    settings = state.schedule.shoot_settings
    return {
        "project_id": state.project_id, "budget_usd": state.budget_state.cap, "locality": state.locality,
        "director_notes": state.director_notes,
        "start_date": settings.get("start_date"), "end_date": settings.get("end_date"),
    }


@app.post("/api/pipeline/run", status_code=202)
def run_pipeline(req: InitRequest, user: User = Depends(current_user)):
    """Plan the whole production: a fresh state through all six phases, on a
    background thread. Producer or owner only. Poll /api/pipeline/status.

    A run resets the pipeline's output, not the material: the screenplay and
    the intake inputs carry over, so a run after a page reload plans the same
    production. Once the plan is saved, the screenplay's poster is made in the
    background (re-running the same screenplay keeps its poster).
    """
    _require_producer(user, req.project_id)
    _new_state(req, supabase_client.load_state(req.project_id))  # a bad window fails now, not minutes later

    def after(state: GlobalState) -> None:
        posters.start_if_missing(state, user.id)

    try:
        return jobs.start(
            req.project_id, "pipeline", started_by=user.id,
            begin=lambda stored: _new_state(req, stored),
            inputs=lambda state: _apply_inputs(req, state),
            after=after,
            summary=_pipeline_summary,
        )
    except jobs.PipelineBusy:
        raise HTTPException(409, "Lumen is already planning this production. Wait for that run to finish.") from None


@app.get("/api/pipeline/status/{project_id}")
def pipeline_status(project_id: str, _member=Depends(require_member)):
    """The pipeline run in flight (phase by phase), else the last one to finish."""
    return jobs.status(project_id)


@app.get("/api/projects")
def list_projects(user: User = Depends(current_user)):
    """Only the productions this account is a member of."""
    out = []
    for membership in auth_store.memberships_for_user(user.id):
        production = auth_store.get_production(membership.project_id)
        if production:
            out.append({"project_id": production.id, "name": production.name, "role": membership.role})
    return {"projects": out}


@app.get("/api/state/{project_id}")
def get_state(project_id: str, request: Request, _member=Depends(require_member)):
    """The production's state without the screenplay text, carrying only the
    latest envelopes (/api/events has the rest). Answers 304 when unchanged."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    return cached_json(request, public_state(state))


@app.get("/api/events/{project_id}")
def get_events(
    project_id: str,
    request: Request,
    since: int = Query(0, ge=0),
    limit: int = Query(EVENT_PAGE_MAX, ge=1, le=EVENT_PAGE_MAX),
    _member=Depends(require_member),
):
    """Live Agent Terminal feed: A2A envelopes from index `since`, a page at a time."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    return cached_json(request, {
        "total": len(state.event_log),
        "offset": since,
        "events": state.event_log[since: since + limit],
    })
