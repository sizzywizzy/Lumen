"""FastAPI entrypoint for CineNode.

    cd backend
    uvicorn main:app --reload --port 8000

Mounts one router per team workspace plus shared pipeline/state/event endpoints
(the Live Agent Terminal polls /api/events).
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState, Mode
from domains.casting.router import router as casting_router
from domains.launch.router import router as launch_router
from domains.production.router import router as production_router
from services import supabase_client

app = FastAPI(title="CineNode", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon setting; tighten before any public deploy
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(casting_router)
app.include_router(production_router)
app.include_router(launch_router)


class InitRequest(BaseModel):
    project_id: str = "PROJ_NEON_NIGHTS"
    mode: Mode = "indie"


@app.get("/api/health")
def health():
    return {"status": "ok", "phases": Orchestrator().phase_keys()}


@app.post("/api/pipeline/init")
def init_pipeline(req: InitRequest):
    """Create (or reset) a project's GlobalState."""
    state = GlobalState(project_id=req.project_id, mode=req.mode)
    supabase_client.save_state(state)
    return {"project_id": state.project_id, "mode": state.mode}


@app.post("/api/pipeline/run")
def run_pipeline(req: InitRequest):
    """Full demo: fresh state through all six phases."""
    state = GlobalState(project_id=req.project_id, mode=req.mode)
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
def list_projects():
    return {"projects": supabase_client.list_projects()}


@app.get("/api/state/{project_id}")
def get_state(project_id: str):
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    return state.model_dump()


@app.get("/api/events/{project_id}")
def get_events(project_id: str, since: int = 0):
    """Live Agent Terminal feed: A2A envelopes from index `since` onward."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    return {"total": len(state.event_log), "events": state.event_log[since:]}
