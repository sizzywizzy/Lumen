"""API endpoints for Phases III & IV (production). Mounted under /api/production."""
from fastapi import APIRouter, HTTPException

from core.orchestrator.graph import Orchestrator
from services import supabase_client

router = APIRouter(prefix="/api/production", tags=["production"])


@router.post("/run/{project_id}")
def run_production(project_id: str):
    """Run Phase III (schedule) + Phase IV (compliance) on the stored state."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")
    state = Orchestrator().run(state, start="phase3", end="phase4")
    supabase_client.save_state(state)
    return {
        "stripboard": [e.model_dump() for e in state.schedule.stripboard],
        "conflicts": state.schedule.conflicts,
        "budget_state": state.budget_state.model_dump(),
        "compliance_state": state.compliance_state,
    }
