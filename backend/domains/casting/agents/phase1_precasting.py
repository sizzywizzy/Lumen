"""Phase I — Pre-Casting Intelligence & Compliance.

agent_profiler -> agent_intake -> (market_synergy | pr_shield | finance) -> risk router.
Fail-fast: red-flagged or over-budget candidates are DISQUALIFIED before any
expensive Phase II media work.
"""
import math

from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import Candidate, GlobalState
from domains.casting import prompts
from services import gemini_client, mock_db

PR_RED_FLAG_TERMS = ("lawsuit", "outburst", "scandal", "arrest")


def _profiler(state: GlobalState) -> None:
    script = mock_db.load("script")
    state.script_context = script["script_context"]
    if state.mode == "enterprise":
        weights = {"W_A": 0.35, "W_H": 0.2, "W_PR": 0.3, "W_B": 0.15}  # brand-safety weighted
    else:
        weights = {"W_A": 0.4, "W_H": 0.15, "W_PR": 0.15, "W_B": 0.3}  # cost weighted
    mandate = gemini_client.generate_json(
        f"Script context: {state.script_context}. Roles: {script['roles']}. Mode: {state.mode}.",
        tier="pro",
        system=prompts.PROFILER_SYSTEM,
        mock={
            "role_requirements": {r["role_id"]: {"name": r["name"], "description": r["description"], "type": r["type"]} for r in script["roles"]},
            "scoring_weights": weights,
        },
    )
    state.role_requirements = mandate["role_requirements"]
    state.scoring_weights = mandate["scoring_weights"]
    log_event(state, broadcast("agent_profiler", "mandate_ready", {
        "roles": list(state.role_requirements), "scoring_weights": state.scoring_weights,
    }))


def _intake(state: GlobalState) -> None:
    for raw in mock_db.load("candidates"):
        candidate = Candidate(**raw, status="SOURCING")
        state.candidates.append(candidate)
        log_event(state, broadcast("agent_intake", "candidate_ingested", {
            "candidate_id": candidate.id, "name": candidate.name, "role_id": candidate.role_id,
        }))


def _hype_score(followers: int) -> float:
    # log-scale 0 followers -> 0, 10M -> ~100
    return round(min(100.0, 14.3 * math.log10(max(followers, 1))), 1)


def _score_candidate(state: GlobalState, candidate: Candidate) -> None:
    """Fan out score_candidate to the three checkers; each replies, some can disqualify."""
    request = log_event(state, make_envelope(
        "agent_director_orchestrator", "agent_market_synergy", "score_candidate",
        {"candidate_id": candidate.id},
    ))

    # agent_market_synergy — Clout / Hype check
    candidate.scores["hype"] = _hype_score(candidate.metadata.get("followers", 0))
    log_event(state, make_reply(request, "agent_market_synergy", "hype_scored",
                                {"candidate_id": candidate.id, "hype": candidate.scores["hype"]}))

    # agent_pr_shield — Drama Filter (hard red flag -> disqualify)
    press = str(candidate.metadata.get("recent_press", "")).lower()
    red_flag = any(term in press for term in PR_RED_FLAG_TERMS)
    verdict = gemini_client.generate_json(
        f"Candidate press: {press}", system=prompts.PR_SHIELD_SYSTEM,
        mock={"pr_score": 20 if red_flag else 90, "red_flag": red_flag,
              "reason": "active litigation / viral incident" if red_flag else "clean record"},
    )
    candidate.scores["pr"] = float(verdict["pr_score"])
    log_event(state, make_reply(request, "agent_pr_shield", "pr_scored",
                                {"candidate_id": candidate.id, "pr": candidate.scores["pr"], "red_flag": verdict["red_flag"]}))
    if verdict["red_flag"]:
        candidate.status = "DISQUALIFIED"
        candidate.disqualify_reason = f"PR: {verdict['reason']}"
        log_event(state, broadcast("agent_pr_shield", "disqualify",
                                   {"candidate_id": candidate.id, "reason": candidate.disqualify_reason}))
        return

    # agent_finance — Wallet Check vs budget cap
    quote = float(candidate.metadata.get("quote_usd", 0))
    cap = state.budget_state.cap
    over_budget = quote > cap
    candidate.scores["budget"] = 0.0 if over_budget else round(100.0 * (1 - quote / cap), 1)
    log_event(state, make_reply(request, "agent_finance", "budget_scored",
                                {"candidate_id": candidate.id, "budget": candidate.scores["budget"], "quote_usd": quote}))
    if over_budget:
        candidate.status = "DISQUALIFIED"
        candidate.disqualify_reason = f"Budget: quote ${quote:,.0f} exceeds per-role cap ${cap:,.0f}"
        log_event(state, broadcast("agent_finance", "disqualify",
                                   {"candidate_id": candidate.id, "reason": candidate.disqualify_reason}))


def run_phase1_precasting(state: GlobalState) -> GlobalState:
    _profiler(state)
    # Per-role casting cap for the fail-fast wallet check.
    state.budget_state.cap = 500_000 if state.mode == "enterprise" else 25_000
    _intake(state)
    for candidate in state.candidates:
        _score_candidate(state, candidate)
    # Risk Router: survivors advance to screening.
    for candidate in state.active_candidates():
        candidate.status = "SCREENING"
    state.casting_status = "SCREENING"
    return state
