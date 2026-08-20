"""API endpoints for Phases I & II (casting). Mounted under /api/casting."""
from fastapi import APIRouter, HTTPException

from core.orchestrator.graph import Orchestrator
from services import supabase_client

router = APIRouter(prefix="/api/casting", tags=["casting"])


@router.post("/run/{project_id}")
def run_casting(project_id: str):
    """Run Phase I (pre-casting) + Phase II (auditions) on the stored state."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")
    state = Orchestrator().run(state, start="phase1", end="phase2")
    supabase_client.save_state(state)
    return {
        "casting_status": state.casting_status,
        "leaderboard": [
            {"id": c.id, "name": c.name, "role_id": c.role_id, "scores": c.scores, "status": c.status}
            for c in sorted(state.candidates, key=lambda c: c.scores.get("composite", -1), reverse=True)
        ],
        "disqualified": [
            {"id": c.id, "name": c.name, "reason": c.disqualify_reason}
            for c in state.candidates if c.status == "DISQUALIFIED"
        ],
    }
