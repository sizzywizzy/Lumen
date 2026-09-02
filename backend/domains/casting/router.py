"""API endpoints for Phases I & II (casting). Mounted under /api/casting."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.orchestrator.graph import Orchestrator
from services import supabase_client

router = APIRouter(prefix="/api/casting", tags=["casting"])


class ActorIngestRequest(BaseModel):
    actor_ids: list[int] = Field(min_length=1, max_length=100)


class EmbeddingRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=10000)


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


@router.post("/actors/ingest")
def ingest_actors(request: ActorIngestRequest):
    """Fetch people and their known-for roles from TMDb into the actor KB."""
    try:
        from services.casting_kb.ingest import ingest_actor_ids
        return {"ingested": ingest_actor_ids(request.actor_ids)}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/actors/embeddings")
def generate_embeddings(request: EmbeddingRequest = EmbeddingRequest()):
    """Generate or refresh embeddings for actors in the KB."""
    try:
        from services.casting_kb.embeddings import generate_actor_embeddings
        return {"embedded": generate_actor_embeddings(request.limit)}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/actors/search")
def search_actors(
    character_description: str = Query(min_length=1),
    gender: int | None = Query(default=None),
    min_age: int | None = Query(default=None, ge=0, le=120),
    max_age: int | None = Query(default=None, ge=0, le=120),
    limit: int = Query(default=5, ge=1, le=100),
):
    """Return semantically similar actors satisfying hard constraints."""
    try:
        from services.casting_kb.matching import match_actors
        return {
            "matches": match_actors(
                character_description,
                gender=gender,
                min_age=min_age,
                max_age=max_age,
                limit=limit,
            )
        }
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc
