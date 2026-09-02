"""API endpoints for Phases I & II (casting). Mounted under /api/casting."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException

from core.auth.deps import require_member, require_producer
from core.auth.models import CandidateStatusRequest
from core.messaging.envelope import broadcast, log_event
from core.orchestrator.graph import Orchestrator
from services import supabase_client

router = APIRouter(prefix="/api/casting", tags=["casting"])


class ActorIngestRequest(BaseModel):
    actor_ids: list[int] = Field(min_length=1, max_length=100)


class EmbeddingRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1, le=10000)

# A cast decision is LOCKED only when every role has someone attached; the
# board stays SCREENING while auditions are still being weighed.
_TERMINAL = {"LOCKED", "DISQUALIFIED"}


def _leaderboard(state):
    return [
        {"id": c.id, "name": c.name, "role_id": c.role_id, "scores": c.scores, "status": c.status}
        for c in sorted(state.candidates, key=lambda c: c.scores.get("composite", -1), reverse=True)
    ]


def _recompute_casting_status(state) -> None:
    """Keep GlobalState.casting_status consistent with the candidate rows."""
    roles = {c.role_id for c in state.candidates if c.role_id}
    if roles and all(
        any(c.role_id == role and c.status == "LOCKED" for c in state.candidates) for role in roles
    ):
        state.casting_status = "LOCKED"
    elif any(c.status in ("SCREENING", "LOCKED") for c in state.candidates):
        state.casting_status = "SCREENING"
    else:
        state.casting_status = "SOURCING"


@router.post("/run/{project_id}")
def run_casting(project_id: str, _member=Depends(require_producer)):
    """Run Phase I (pre-casting) + Phase II (auditions) on the stored state."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")
    state = Orchestrator().run(state, start="phase1", end="phase2")
    supabase_client.save_state(state)
    return {
        "casting_status": state.casting_status,
        "leaderboard": _leaderboard(state),
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


@router.patch("/candidates/{project_id}/{candidate_id}")
def set_candidate_status(
    project_id: str,
    candidate_id: str,
    req: CandidateStatusRequest,
    membership=Depends(require_producer),
):
    """Move a candidate along the casting funnel.

    Producer/owner only — crew see the board read-only. The change is written
    to the shared GlobalState, so every other team member sees it too, and it
    is logged as an A2A envelope so the decision shows up in the agent
    terminal alongside the automated ones.
    """
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}.")

    candidate = next((c for c in state.candidates if c.id == candidate_id), None)
    if candidate is None:
        raise HTTPException(404, f"No candidate '{candidate_id}' on this production.")

    previous = candidate.status
    candidate.status = req.status
    if req.status == "DISQUALIFIED":
        candidate.disqualify_reason = req.reason or "Disqualified by the production team."
    elif previous == "DISQUALIFIED":
        # Reinstating clears the old reason so the risk panel stays truthful.
        candidate.disqualify_reason = None

    _recompute_casting_status(state)

    log_event(
        state,
        broadcast(
            sender="agent_director_orchestrator",
            intent="task_status_update",
            payload={
                "candidate_id": candidate.id,
                "name": candidate.name,
                "role_id": candidate.role_id,
                "from": previous,
                "to": candidate.status,
                "changed_by": membership.user_id,
                "reason": req.reason or None,
                "source": "human_decision",
            },
        ),
    )
    supabase_client.save_state(state)

    return {
        "candidate": candidate.model_dump(),
        "casting_status": state.casting_status,
        "event_log": state.event_log,
    }


@router.get("/leaderboard/{project_id}")
def leaderboard(project_id: str, _member=Depends(require_member)):
    """Read-only board — available to every role on the production."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}.")
    return {"casting_status": state.casting_status, "leaderboard": _leaderboard(state)}
