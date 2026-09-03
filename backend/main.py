"""FastAPI entrypoint for CineNode.

    cd backend
    uvicorn main:app --reload --port 8000

Mounts one router per team workspace plus shared pipeline/state/event endpoints
(the Live Agent Terminal polls /api/events).
"""
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core import config
from core.auth.deps import current_user, membership_for, require_member, require_producer
from core.auth.models import User, role_at_least
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import BudgetState, GlobalState
from domains.audience.router import router as audience_router
from domains.auth.router import router as auth_router
from domains.casting.router import router as casting_router
from domains.launch.router import router as launch_router
from domains.production.router import router as production_router
from domains.skills.router import router as skills_router
from services import auth_store, script_intake, supabase_client

app = FastAPI(title="CineNode", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon setting; tighten before any public deploy
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
    project_id: str = "PROJ_NEON_NIGHTS"
    budget_usd: float = config.DEFAULT_BUDGET_USD  # total production budget from the intake form
    locality: Optional[str] = "Los Angeles, CA"
    director_notes: Optional[str] = ""


def _new_state(req: InitRequest) -> GlobalState:
    loc = req.locality or "Los Angeles, CA"
    notes = req.director_notes or ""
    return GlobalState(
        project_id=req.project_id,
        budget_state=BudgetState(cap=req.budget_usd),
        locality=loc,
        director_notes=notes,
        script_context={
            "locality": loc,
            "director_notes": notes,
        },
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "phases": Orchestrator().phase_keys()}


@app.post("/api/pipeline/init")
def init_pipeline(req: InitRequest, user: User = Depends(current_user)):
    """Create (or reset) a project's GlobalState. Producer or owner only."""
    membership = membership_for(user, req.project_id)
    if not role_at_least(membership.role, "producer"):
        raise HTTPException(403, "Your role on this production is read-only.")
    state = _new_state(req)
    stored = supabase_client.load_state(req.project_id)
    if stored is not None:
        state.script_context = {
            **(state.script_context or {}),
            **{k: v for k, v in (stored.script_context or {}).items() if k in script_intake.INTAKE_KEYS},
        }
    supabase_client.save_state(state)
    return {"project_id": state.project_id, "budget_usd": state.budget_state.cap, "locality": state.locality}


@app.post("/api/pipeline/run")
def run_pipeline(req: InitRequest, user: User = Depends(current_user)):
    """Full demo: fresh state through all six phases. Producer or owner only."""
    membership = membership_for(user, req.project_id)
    if not role_at_least(membership.role, "producer"):
        raise HTTPException(403, "Your role on this production is read-only.")
    state = _new_state(req)
    # A run resets the pipeline's output, not the material: keep the screenplay
    # dropped at intake so every phase and advisor reads the real script.
    stored = supabase_client.load_state(req.project_id)
    if stored is not None:
        intake_context = {k: v for k, v in (stored.script_context or {}).items() if k in script_intake.INTAKE_KEYS}
        state.script_context = {**(state.script_context or {}), **intake_context}
        if not req.director_notes and stored.director_notes:
            state.director_notes = stored.director_notes
            state.script_context["director_notes"] = stored.director_notes
        if not req.locality and stored.locality:
            state.locality = stored.locality
            state.script_context["locality"] = stored.locality
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
