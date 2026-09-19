"""A2A envelope rules — AGENT.md Section 2, contracts/a2a_envelope.json.

The envelope is the one shape every agent shares, so these tests guard the
rules that keep the Live Agent Terminal replayable: a closed intent vocabulary,
a parseable message_id, and replies that actually link back to their request.
"""
import importlib
import json
import re
import time
from pathlib import Path

import pytest

from core.messaging.envelope import (
    ALL_INTENTS,
    ORCHESTRATOR,
    broadcast,
    log_event,
    make_envelope,
    make_reply,
)
from core.orchestrator.state import GlobalState

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "a2a_envelope.json"


def test_envelope_has_exactly_the_required_keys():
    env = make_envelope("agent_profiler", ORCHESTRATOR, "mandate_ready", {"roles": 2})
    assert set(env) == {"message_id", "sender", "recipient", "timestamp", "intent", "payload"}


def test_unknown_intent_is_rejected():
    with pytest.raises(ValueError, match="Unknown intent"):
        make_envelope("agent_profiler", ORCHESTRATOR, "vibe_check", {})


def test_message_id_matches_the_contract_pattern():
    pattern = json.loads(CONTRACT.read_text(encoding="utf-8"))["properties"]["message_id"]["pattern"]
    env = make_envelope("agent_pr_risk", ORCHESTRATOR, "pr_scored", {})
    assert re.match(pattern, env["message_id"])


def test_message_ids_are_unique_across_calls():
    ids = {make_envelope("agent_intake", ORCHESTRATOR, "candidate_ingested", {})["message_id"]
           for _ in range(50)}
    assert len(ids) == 50


def _seq(envelope: dict) -> int:
    return int(envelope["message_id"].rsplit("_", 1)[1])


def test_message_ids_keep_increasing_across_a_restart():
    """Event logs outlive the process: ids after a restart must not reuse old ones."""
    from core.messaging import envelope as module

    before = _seq(make_envelope("agent_intake", ORCHESTRATOR, "candidate_ingested", {}))
    assert before >= 1_700_000_000 * 1_000_000, "ids start from the clock, not from 1"
    time.sleep(0.001)
    importlib.reload(module)  # what a restart does to the counter
    after = _seq(module.make_envelope("agent_intake", ORCHESTRATOR, "candidate_ingested", {}))
    assert after > before


def test_reply_targets_the_original_sender_and_links_back():
    request = make_envelope("agent_visual", "agent_pr_risk", "verify_brand_safety", {"asset": "AST_MEME_0001"})
    reply = make_reply(request, "agent_pr_risk", "brand_safety_result", {"verdict": "BLOCKED"})

    assert reply["sender"] == "agent_pr_risk"
    assert reply["recipient"] == request["sender"]
    assert reply["in_reply_to"] == request["message_id"]


def test_broadcast_goes_to_the_orchestrator_with_no_reply_link():
    env = broadcast("agent_reel_cutter", "reel_ready", {"asset_id": "AST_REEL_0001"})
    assert env["recipient"] == ORCHESTRATOR
    assert "in_reply_to" not in env


def test_log_event_appends_in_order_and_returns_the_envelope():
    state = GlobalState(project_id="PROJ_TEST")
    first = log_event(state, broadcast("agent_intake", "candidate_ingested", {"n": 1}))
    second = log_event(state, broadcast("agent_intake", "candidate_ingested", {"n": 2}))

    assert state.event_log == [first, second]
    assert second["payload"]["n"] == 2


def test_intent_vocabulary_matches_the_sacred_contract():
    """contracts/ is shared across the team — code and contract must not drift."""
    enum = set(json.loads(CONTRACT.read_text(encoding="utf-8"))["properties"]["intent"]["enum"])
    assert ALL_INTENTS == enum


# ------------------------------------------------------- the phase stamp --


def test_log_event_stamps_the_running_phase():
    """The trace groups a run's traffic by phase, so the phase has to be on the
    record rather than guessed from agent names later."""
    from core.messaging.envelope import running_phase

    state = GlobalState(project_id="PROJ_T")
    with running_phase("phase3"):
        log_event(state, make_envelope("agent_scheduler_shoot", "agent_location",
                                       "check_venue_availability", {}))
    assert state.event_log[0]["phase"] == "phase3"


def test_an_event_logged_outside_a_phase_carries_none():
    """Advisors and standalone simulations log too, and they belong to no phase."""
    state = GlobalState(project_id="PROJ_T")
    log_event(state, broadcast("agent_profiler", "mandate_ready", {}))
    assert "phase" not in state.event_log[0]


def test_the_stamp_is_removed_when_the_phase_ends():
    from core.messaging.envelope import running_phase

    state = GlobalState(project_id="PROJ_T")
    with running_phase("phase1"):
        log_event(state, broadcast("agent_intake", "candidate_ingested", {}))
    log_event(state, broadcast("agent_intake", "candidate_ingested", {}))
    assert state.event_log[0]["phase"] == "phase1"
    assert "phase" not in state.event_log[1]


def test_the_stamp_never_changes_the_envelope_an_agent_built():
    """make_envelope stays exactly the six contract fields; the phase is added
    by the log, so a payload handed to an agent is not mutated underneath it."""
    from core.messaging.envelope import running_phase

    state = GlobalState(project_id="PROJ_T")
    built = make_envelope("agent_qc", ORCHESTRATOR, "qc_result", {})
    with running_phase("phase4"):
        logged = log_event(state, built)
    assert "phase" not in built
    assert logged["phase"] == "phase4"


def test_the_phase_stamp_matches_the_contract():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["properties"]["phase"]["pattern"] == "^phase[1-6]$"
    assert "phase" not in contract["required"]


def test_every_phase_the_orchestrator_runs_stamps_a_valid_key():
    """A phase key the contract's pattern rejects would make the log unparseable."""
    from core.orchestrator.graph import Orchestrator

    pattern = json.loads(CONTRACT.read_text(encoding="utf-8"))["properties"]["phase"]["pattern"]
    for key in Orchestrator().phase_keys():
        assert re.match(pattern, key), f"phase key {key} is not valid in the envelope contract"
