"""API endpoints for Phases V & VI (launch). Mounted under /api/launch."""
from fastapi import APIRouter, HTTPException

from core.orchestrator.graph import Orchestrator
from services import supabase_client

router = APIRouter(prefix="/api/launch", tags=["launch"])


@router.post("/run/{project_id}")
def run_launch(project_id: str):
    """Run Phase V (audience sim) + Phase VI (marketing) on the stored state."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")
    state = Orchestrator().run(state, start="phase5", end="phase6")
    supabase_client.save_state(state)
    return {
        "audience_report": state.audience_report.model_dump(),
        "marketing_assets": [a.model_dump() for a in state.marketing_assets],
    }
