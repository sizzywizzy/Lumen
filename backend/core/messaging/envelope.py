"""A2A envelope helper — shared by ALL agents (AGENT.md Section 2).

Never invent a message shape. Build every inter-agent message with
`make_envelope` / `make_reply` and record it with `log_event` so the
Live Agent Terminal can replay the whole conversation.
"""
import itertools
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from core.orchestrator.state import GlobalState

ORCHESTRATOR = "agent_director_orchestrator"

# The sequence starts at the process's start time in microseconds rather than
# at 1. Event logs outlive the process, and a counter that restarted at 1 after
# every deploy reused ids already in the stored log, which crossed the
# `in_reply_to` links and the Agent Log's keys. Starting from the clock keeps
# ids numeric (contracts/a2a_envelope.json) and increasing across restarts.
_seq = itertools.count(time.time_ns() // 1_000)

# Intent vocabulary (AGENT.md Section 5). Envelope creation validates against it.
REQUEST_REPLY_INTENTS = {
    "verify_regional_compliance", "compliance_result",
    "check_venue_availability", "venue_offer",
    "diagnose_engagement_anomaly", "diagnosis_result",
    "verify_brand_safety", "brand_safety_result",
    "score_candidate", "hype_scored", "pr_scored", "budget_scored",
    "review_audition", "audition_scored",
    "screen_film", "request_audience_insights",
    "scout_local_talent", "talent_scouted",
}
BROADCAST_INTENTS = {
    "mandate_ready", "candidate_ingested", "media_ready", "leaderboard_ready",
    "breakdown_ready", "schedule_updated", "task_status_update",
    "qc_result", "telemetry_update", "personas_ready", "reviews_ready",
    "simulation_verdict_update", "campaign_plan_ready", "reel_ready",
    "asset_scheduled", "asset_status_update", "disqualify",
    "crawl_locality_started", "crawl_locality_completed",
}
ALL_INTENTS = REQUEST_REPLY_INTENTS | BROADCAST_INTENTS


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short(agent_id: str) -> str:
    # agent_recut_advisor -> rec ; agent_pr_risk -> pr_risk stays readable as "pr"
    return agent_id.removeprefix("agent_")[:3]


def make_envelope(
    sender: str,
    recipient: str,
    intent: str,
    payload: dict[str, Any],
    in_reply_to: Optional[str] = None,
) -> dict[str, Any]:
    if intent not in ALL_INTENTS:
        raise ValueError(f"Unknown intent '{intent}'. Add it to AGENT.md Section 5 and contracts/a2a_envelope.json first.")
    envelope: dict[str, Any] = {
        "message_id": f"msg_{_short(sender)}_{next(_seq)}",
        "sender": sender,
        "recipient": recipient,
        "timestamp": _now_iso(),
        "intent": intent,
        "payload": payload,
    }
    if in_reply_to:
        envelope["in_reply_to"] = in_reply_to
    return envelope


def make_reply(original: dict[str, Any], sender: str, intent: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Reply to a request: recipient is the original sender, in_reply_to links the pair."""
    return make_envelope(
        sender=sender,
        recipient=original["sender"],
        intent=intent,
        payload=payload,
        in_reply_to=original["message_id"],
    )


def broadcast(sender: str, intent: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Broadcast to the orchestrator (no reply expected)."""
    return make_envelope(sender=sender, recipient=ORCHESTRATOR, intent=intent, payload=payload)


# Which phase is running, for `log_event` to stamp on what it records. A
# ContextVar rather than a field on GlobalState because it is a property of
# *when* a message was logged, not of the message or the production: the same
# agent logs under phase1 during casting and under phase5 during a screening.
# The orchestrator sets it (core/orchestrator/graph.py); anything logged
# outside a phase — an advisor, a standalone simulation — simply has no phase.
_phase: ContextVar[Optional[str]] = ContextVar("lumen_phase", default=None)


@contextmanager
def running_phase(key: Optional[str]) -> Iterator[None]:
    """Mark everything logged inside this block as belonging to `key`."""
    token = _phase.set(key)
    try:
        yield
    finally:
        _phase.reset(token)


def log_event(state: GlobalState, envelope: dict[str, Any]) -> dict[str, Any]:
    """Append an envelope to GlobalState.event_log and return it (chainable).

    Stamps the running phase so the Agent Log and the execution trace can group
    a run's traffic by the phase that produced it without re-deriving it from
    agent names — a mapping that would drift the moment an agent moved phase.
    `make_envelope` deliberately does not carry it: the envelope an agent builds
    stays exactly the six contract fields (contracts/a2a_envelope.json).
    """
    phase = _phase.get()
    if phase:
        envelope = {**envelope, "phase": phase}
    state.event_log.append(envelope)
    return envelope
