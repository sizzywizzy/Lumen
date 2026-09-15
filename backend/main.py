"""FastAPI entrypoint for Lumen.

    cd backend
    uvicorn main:app --reload --port 8000

Mounts one router per team workspace plus shared pipeline/state/event endpoints
(the Live Agent Terminal polls /api/events).
"""
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from core import config
from core.auth.deps import current_user, membership_for, require_member, require_producer
from core.auth.models import User, role_at_least
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import BudgetState, GlobalState
from core.shoot_window import IsoDate, settings_problem, window_problem
from domains.audience.router import router as audience_router
from domains.auth.router import router as auth_router
from domains.casting.router import router as casting_router
from domains.launch.router import router as launch_router
from domains.production.router import router as production_router
from domains.skills.router import router as skills_router
from services import auth_store, script_intake, supabase_client

app = FastAPI(title="Lumen", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,  # "*" unless LUMEN_CORS_ORIGINS names the deployed frontend
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(audience_router)
app.include_router(casting_router)
app.include_router(production_router)
app.include_router(launch_router)
app.include_router(skills_router)


class InitRequest(BaseModel):
    """Intake inputs. Anything left out keeps the production's saved value."""
    project_id: str = "PROJ_NEON_NIGHTS"
    budget_usd: Optional[float] = Field(default=None, gt=0)  # total production budget from the intake form
    locality: Optional[str] = None
    director_notes: Optional[str] = None
    start_date: IsoDate = None  # first shoot day, YYYY-MM-DD
    end_date: IsoDate = None  # planned wrap, YYYY-MM-DD

    @model_validator(mode="after")
    def _check_window(self):
        problem = window_problem(self.start_date, self.end_date)
        if problem:
            raise ValueError(problem)
        return self


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
        for key in ("expenses", "total_budget", "spent", "remaining"):
            setattr(state.budget_state, key, getattr(stored.budget_state, key))
    # Stored as ISO strings: the Supabase path saves with model_dump(), which leaves dates unencoded.
    if req.start_date:
        state.schedule.shoot_settings["start_date"] = req.start_date.isoformat()
    if req.end_date:
        state.schedule.shoot_settings["end_date"] = req.end_date.isoformat()
    problem = settings_problem(state.schedule.shoot_settings)
    if problem:  # e.g. a new wrap date earlier than the saved first shoot day
        raise HTTPException(422, problem)
    return state


@app.get("/api/health")
def health():
    return {"status": "ok", "phases": Orchestrator().phase_keys()}


@app.post("/api/pipeline/init")
def init_pipeline(req: InitRequest, user: User = Depends(current_user)):
    """Create (or reset) a project's GlobalState. Producer or owner only."""
    membership = membership_for(user, req.project_id)
    if not role_at_least(membership.role, "producer"):
        raise HTTPException(403, "Your role on this production is read-only.")
    state = _new_state(req, supabase_client.load_state(req.project_id))
    supabase_client.save_state(state)
    settings = state.schedule.shoot_settings
    return {
        "project_id": state.project_id, "budget_usd": state.budget_state.cap, "locality": state.locality,
        "director_notes": state.director_notes,
        "start_date": settings.get("start_date"), "end_date": settings.get("end_date"),
    }


@app.post("/api/pipeline/run")
def run_pipeline(req: InitRequest, user: User = Depends(current_user)):
    """Full demo: fresh state through all six phases. Producer or owner only."""
    membership = membership_for(user, req.project_id)
    if not role_at_least(membership.role, "producer"):
        raise HTTPException(403, "Your role on this production is read-only.")
    # A run resets the pipeline's output, not the material: the screenplay and
    # the intake inputs carry over, so a run after a page reload plans the same production.
    state = _new_state(req, supabase_client.load_state(req.project_id))
    state = Orchestrator().run(state)
    supabase_client.save_state(state)
    return {
        "project_id": state.project_id,
        "casting_status": state.casting_status,
        "tomatometer": state.audience_report.tomatometer,
        "events": len(state.event_log),
        "human_escalations": [e.model_dump() for e in state.human_escalations],
    }


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
def get_state(project_id: str, _member=Depends(require_member)):
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    return state.model_dump()


@app.get("/api/events/{project_id}")
def get_events(project_id: str, since: int = 0, _member=Depends(require_member)):
    """Live Agent Terminal feed: A2A envelopes from index `since` onward."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    return {"total": len(state.event_log), "events": state.event_log[since:]}
