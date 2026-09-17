"""Orchestrator fail-fast edges.

A conditional edge returns a halt reason (string) to stop the pipeline, or None
to continue. The two live edges are the risk router after Phase I and the
all-territories-blocked check after Phase IV.
"""
import pytest

from core.orchestrator.graph import (
    Orchestrator,
    PhaseNode,
    _all_territories_blocked,
    _no_viable_candidates,
    build_graph,
)
from core.orchestrator.state import Candidate, GlobalState


def _state(**kwargs):
    return GlobalState(project_id="PROJ_TEST", **kwargs)


def _candidate(cid, status="SOURCING"):
    return Candidate(id=cid, name=cid.title(), status=status)


def _stub_orchestrator(nodes):
    orch = Orchestrator()
    orch.nodes = nodes
    return orch


# ------------------------------------------------------- Phase I risk router --


def test_every_candidate_disqualified_halts():
    state = _state(candidates=[_candidate("c1", "DISQUALIFIED"), _candidate("c2", "DISQUALIFIED")])
    assert "re-open sourcing" in _no_viable_candidates(state)


def test_one_survivor_is_enough_to_continue():
    state = _state(candidates=[_candidate("c1", "DISQUALIFIED"), _candidate("c2", "SCREENING")])
    assert _no_viable_candidates(state) is None


# --------------------------------------------------- Phase IV compliance edge --


def test_all_territories_blocked_halts():
    state = _state(compliance_state={"US": "BLOCKED", "UAE": "BLOCKED"})
    assert "launch prep halted" in _all_territories_blocked(state)


def test_one_cleared_territory_continues():
    state = _state(compliance_state={"US": "CLEARED", "UAE": "BLOCKED"})
    assert _all_territories_blocked(state) is None


def test_empty_compliance_state_does_not_halt():
    """Phase IV has not run yet — an empty dict must not read as 'all blocked'."""
    assert _all_territories_blocked(_state()) is None


# ------------------------------------------------------------- graph wiring --


def test_graph_is_six_phases_guarded_at_one_and_four():
    nodes = build_graph()
    assert [n.key for n in nodes] == ["phase1", "phase2", "phase3", "phase4", "phase5", "phase6"]
    assert {n.key for n in nodes if n.fail_fast is not None} == {"phase1", "phase4"}


# --------------------------------------------------------------- run() rules --


def test_run_halts_and_escalates_when_an_edge_returns_a_reason():
    ran = []
    nodes = [
        PhaseNode("phase1", "P1", lambda s: (ran.append("phase1"), s)[1], lambda s: "no candidates left"),
        PhaseNode("phase2", "P2", lambda s: (ran.append("phase2"), s)[1]),
    ]
    state = _stub_orchestrator(nodes).run(_state(), start="phase1", end="phase2")

    assert ran == ["phase1"], "phase2 must not run after a halt"
    assert len(state.human_escalations) == 1
    assert state.human_escalations[0].queue_item == "phase1_halt"
    assert state.human_escalations[0].reason == "no candidates left"


def test_run_continues_through_every_phase_when_no_edge_trips():
    ran = []
    nodes = [
        PhaseNode("phase1", "P1", lambda s: (ran.append("phase1"), s)[1], lambda s: None),
        PhaseNode("phase2", "P2", lambda s: (ran.append("phase2"), s)[1]),
    ]
    state = _stub_orchestrator(nodes).run(_state(), start="phase1", end="phase2")

    assert ran == ["phase1", "phase2"]
    assert state.human_escalations == []


@pytest.mark.parametrize("start, end", [("phase9", "phase6"), ("phase4", "phase2")])
def test_run_rejects_an_invalid_phase_range(start, end):
    with pytest.raises(ValueError, match="Invalid phase range"):
        Orchestrator().run(_state(), start=start, end=end)


# ------------------------------------------------- what each phase's calls were --


def test_a_run_records_the_model_calls_each_phase_made(offline):
    """The pages say which parts of a plan are Lumen's sample output, so a run
    counts the calls the model answered and the ones that fell back."""
    state = Orchestrator().run(_state(), start="phase1", end="phase3")

    assert list(state.model_use) == ["phase1", "phase2", "phase3"]
    assert all(use["live"] == 0 for use in state.model_use.values()), "no key, so no call was answered"
    assert state.model_use["phase1"]["sample"] > 0 and state.model_use["phase2"]["sample"] > 0
    assert {use["reason"] for use in state.model_use.values() if use["sample"]} == {"no_api_key"}


def test_an_unread_screenplay_is_recorded_as_the_sample_script(offline):
    """With no model, Phase I plans Lumen's sample film. A producer whose own
    screenplay is stored has to be told, or the plan reads as theirs."""
    theirs = _state(script_context={"raw_text": "INT. KITCHEN - DAY\nShe counts the tips again.\n" * 40})
    assert Orchestrator().run(theirs, start="phase1", end="phase1").model_use["phase1"]["sample_script"] is True

    demo_only = Orchestrator().run(_state(), start="phase1", end="phase1")
    assert "sample_script" not in demo_only.model_use["phase1"], "nothing of theirs went unread"
