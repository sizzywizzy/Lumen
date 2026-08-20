"""Phase II — Audition Analysis & Scorecard.

agent_media_proc (FFmpeg/Whisper stub) -> agent_audition_analytics -> agent_synthesis.
Composite = Audition*W_A + Hype*W_H + PR*W_PR + Budget*W_B  (AGENT.md Phase II).
"""
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState
from domains.casting import prompts
from services import gemini_client


def _media_proc(state: GlobalState) -> None:
    """Cruncher: compress 4K -> 720p and transcribe BEFORE any LLM sees the tape.
    Real implementation lives in services/media (FFmpeg + Whisper); mocked for now."""
    for candidate in state.active_candidates():
        log_event(state, broadcast("agent_media_proc", "media_ready", {
            "candidate_id": candidate.id,
            "clip_720p": candidate.media_url.replace("_4k", "_720p"),
            "transcript": f"mock://transcripts/{candidate.id}.txt",
        }))


def _audition_analytics(state: GlobalState) -> None:
    for candidate in state.active_candidates():
        request = log_event(state, make_envelope(
            "agent_director_orchestrator", "agent_audition_analytics", "review_audition",
            {"candidate_id": candidate.id, "role_id": candidate.role_id},
        ))
        review = gemini_client.generate_json(
            f"Role requirements: {state.role_requirements.get(candidate.role_id)}. "
            f"Clip: {candidate.media_url}. Transcript attached.",
            tier="pro",
            system=prompts.AUDITION_SYSTEM,
            mock=prompts.MOCK_AUDITION_REVIEWS.get(candidate.id, prompts.MOCK_AUDITION_DEFAULT),
        )
        candidate.scores["audition"] = float(review["audition_score"])
        candidate.metadata["qualitative_review"] = review["qualitative_review"]
        log_event(state, make_reply(request, "agent_audition_analytics", "audition_scored", {
            "candidate_id": candidate.id, "audition": candidate.scores["audition"],
            "review": review["qualitative_review"],
        }))


def _synthesis(state: GlobalState) -> None:
    weights = state.scoring_weights
    for candidate in state.active_candidates():
        scores = candidate.scores
        scores["composite"] = round(
            scores.get("audition", 0) * weights["W_A"]
            + scores.get("hype", 0) * weights["W_H"]
            + scores.get("pr", 0) * weights["W_PR"]
            + scores.get("budget", 0) * weights["W_B"],
            1,
        )
    leaderboard = sorted(state.active_candidates(), key=lambda c: c.scores["composite"], reverse=True)
    # Lock the top candidate per role; escalate the pick for human sign-off.
    locked_roles: set[str] = set()
    for candidate in leaderboard:
        if candidate.role_id not in locked_roles:
            candidate.status = "LOCKED"
            locked_roles.add(candidate.role_id)
            state.escalate(
                queue_item=f"cast_signoff:{candidate.role_id}",
                reason=f"Confirm {candidate.name} for {candidate.role_id} (composite {candidate.scores['composite']})",
            )
    log_event(state, broadcast("agent_synthesis", "leaderboard_ready", {
        "leaderboard": [{"candidate_id": c.id, "name": c.name, "role_id": c.role_id,
                         "composite": c.scores["composite"], "status": c.status} for c in leaderboard],
    }))
    state.casting_status = "LOCKED"


def run_phase2_audition(state: GlobalState) -> GlobalState:
    _media_proc(state)
    _audition_analytics(state)
    _synthesis(state)
    return state
