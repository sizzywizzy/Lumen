"""Phase I — Pre-Casting Intelligence & Compliance.

agent_profiler -> agent_intake -> (market_synergy | pr_shield | finance) -> risk router.
Fail-fast: red-flagged or over-budget candidates are DISQUALIFIED before any
expensive Phase II media work.
"""
import math
import re

from core import config
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import Candidate, GlobalState
from domains.casting import prompts
from services import gemini_client, mock_db, script_intake

PR_RED_FLAG_TERMS = ("lawsuit", "outburst", "scandal", "arrest")

ROLE_ID_RE = re.compile(r"^ROLE_[A-Z0-9_]{1,30}$")
ROLE_TYPES = ("lead", "antagonist", "supporting")
MAX_ROLES = 8
# What the profiler must keep when it rewrites script_context: the screenplay
# dropped at intake, and the scene breakdown Phase III derives from it.
PRESERVED_CONTEXT_KEYS = script_intake.INTAKE_KEYS + ("scenes",)


def _valid_roles(roles) -> list[dict]:
    out, seen = [], set()
    for role in roles if isinstance(roles, list) else []:
        if not isinstance(role, dict):
            continue
        role_id = str(role.get("role_id", "")).strip().upper()
        name = str(role.get("name", "")).strip()
        if not ROLE_ID_RE.match(role_id) or not name or role_id in seen:
            continue
        kind = str(role.get("type", "supporting")).strip().lower()
        out.append({"role_id": role_id, "name": name, "type": kind if kind in ROLE_TYPES else "supporting",
                    "description": str(role.get("description", "")).strip()[:300]})
        seen.add(role_id)
        if len(out) >= MAX_ROLES:
            break
    return out


def _read_script(state: GlobalState) -> dict:
    """Context and roles from the screenplay dropped at intake. With no
    screenplay, or with no model key, the demo script stands in (the mock
    carries a `source` marker so the fallback is recognisable)."""
    demo = mock_db.load("script")
    fallback = {"script_context": dict(demo["script_context"]), "roles": demo["roles"], "source": "demo"}
    raw = ((state.script_context or {}).get("raw_text") or "").strip()
    if not raw:
        return fallback
    limit = config.SCRIPT_ANALYSIS_MAX_CHARS
    read = gemini_client.generate_json(
        f"SCREENPLAY (first {min(len(raw), limit):,} characters):\n{raw[:limit]}",
        tier="pro", system=prompts.SCRIPT_READ_SYSTEM, mock=fallback,
    )
    roles = _valid_roles(read.get("roles")) if isinstance(read, dict) else []
    context = read.get("script_context") if isinstance(read, dict) and isinstance(read.get("script_context"), dict) else {}
    if not roles or read.get("source") == "demo":
        return fallback
    targets = context.get("demographic_targets")
    return {
        "script_context": {
            "title": str(context.get("title") or state.script_context.get("source_filename") or "Untitled"),
            "genre": str(context.get("genre", "")),
            "tone": str(context.get("tone", "")),
            "logline": str(context.get("logline", "")),
            "demographic_targets": [str(t) for t in targets] if isinstance(targets, list) else [],
        },
        "roles": roles,
        "source": "script",
    }


def _profiler(state: GlobalState) -> None:
    script = _read_script(state)
    preserved = {k: v for k, v in (state.script_context or {}).items() if k in PRESERVED_CONTEXT_KEYS}
    state.script_context = {**script["script_context"], **preserved}
    brief = {k: v for k, v in state.script_context.items() if k not in PRESERVED_CONTEXT_KEYS}
    mandate = gemini_client.generate_json(
        f"Script context: {brief}. Roles: {script['roles']}. "
        f"Total budget: ${state.budget_state.cap:,.0f}.",
        tier="pro",
        system=prompts.PROFILER_SYSTEM,
        mock={
            "role_requirements": {r["role_id"]: {"name": r["name"], "description": r["description"], "type": r["type"]} for r in script["roles"]},
            "scoring_weights": {"W_A": 0.4, "W_H": 0.2, "W_PR": 0.2, "W_B": 0.2},  # AGENT.md defaults
        },
    )
    state.role_requirements = mandate["role_requirements"]
    # A live mandate may omit a role or its name; the read of the script is the
    # source of truth for who the roles are, so fill any gaps from it.
    for role in script["roles"]:
        entry = state.role_requirements.setdefault(role["role_id"], {})
        if isinstance(entry, dict):
            for key in ("name", "type", "description"):
                entry.setdefault(key, role[key])
    state.scoring_weights = mandate["scoring_weights"]
    log_event(state, broadcast("agent_profiler", "mandate_ready", {
        "roles": list(state.role_requirements), "scoring_weights": state.scoring_weights,
        "source": script["source"],
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

    # agent_finance — Wallet Check: a single role may take at most a fixed share of the total budget
    quote = float(candidate.metadata.get("quote_usd", 0))
    role_cap = state.budget_state.cap * config.CASTING_CAP_SHARE
    over_budget = quote > role_cap
    candidate.scores["budget"] = 0.0 if over_budget else round(100.0 * (1 - quote / role_cap), 1)
    log_event(state, make_reply(request, "agent_finance", "budget_scored",
                                {"candidate_id": candidate.id, "budget": candidate.scores["budget"],
                                 "quote_usd": quote, "role_cap_usd": role_cap}))
    if over_budget:
        candidate.status = "DISQUALIFIED"
        candidate.disqualify_reason = (
            f"Budget: quote ${quote:,.0f} exceeds per-role cap ${role_cap:,.0f} "
            f"({config.CASTING_CAP_SHARE:.0%} of the ${state.budget_state.cap:,.0f} budget)"
        )
        log_event(state, broadcast("agent_finance", "disqualify",
                                   {"candidate_id": candidate.id, "reason": candidate.disqualify_reason}))


def run_phase1_precasting(state: GlobalState) -> GlobalState:
    _profiler(state)
    _intake(state)
    for candidate in state.candidates:
        _score_candidate(state, candidate)
    # Risk Router: survivors advance to screening.
    for candidate in state.active_candidates():
        candidate.status = "SCREENING"
    state.casting_status = "SCREENING"
    return state
