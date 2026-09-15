"""Re-running a phase replaces its output instead of stacking a second copy.

/api/production/run, /api/launch/run, /api/casting/run and the advisor
preparers all run phases on the stored state again, so every phase must own
what it writes: candidates, conflicts, alerts, compliance verdicts, assets and
the escalations it raises. Only the event log is meant to keep growing.
"""
from core.orchestrator.graph import Orchestrator, PhaseNode
from core.orchestrator.state import GlobalState


def _shape(state: GlobalState) -> dict:
    return {
        "candidates": [c.id for c in state.candidates],
        "conflicts": len(state.schedule.conflicts),
        "alerts": len(state.budget_state.alerts),
        "compliance": dict(state.compliance_state),
        "assets": [a.asset_id for a in state.marketing_assets],
        "escalations": sorted(e.queue_item for e in state.human_escalations),
    }


def test_a_second_full_run_yields_the_same_state_shape(offline):
    state = Orchestrator().run(GlobalState(project_id="PROJ_NEON_NIGHTS"))
    first = _shape(state)
    events = len(state.event_log)
    assert first["escalations"] and first["conflicts"] and first["assets"] and first["candidates"]

    state = Orchestrator().run(state)
    assert _shape(state) == first
    assert len(state.event_log) > events, "the terminal log is the one thing that keeps growing"


def test_rerunning_a_phase_range_replaces_only_its_own_output(offline):
    state = Orchestrator().run(GlobalState(project_id="PROJ_NEON_NIGHTS"))
    first = _shape(state)
    for start, end in (("phase1", "phase2"), ("phase3", "phase4"), ("phase5", "phase6")):
        state = Orchestrator().run(state, start=start, end=end)
        assert _shape(state) == first, f"{start}..{end} changed the state shape on re-run"
    assert len(set(first["assets"])) == len(first["assets"])
    assert len(set(first["candidates"])) == len(first["candidates"])


def test_escalations_are_cleared_by_prefix_only():
    state = GlobalState(project_id="PROJ_T")
    state.escalate("venue:SCN_001", "no venue")
    state.escalate("schedule:past_wrap", "late")
    state.escalate("compliance:UAE", "blocked")
    state.clear_escalations("venue:", "schedule:")
    assert [e.queue_item for e in state.human_escalations] == ["compliance:UAE"]


def test_a_cleared_halt_does_not_linger_on_the_next_run():
    verdicts = iter(["no candidates left", None])
    orchestrator = Orchestrator()
    orchestrator.nodes = [PhaseNode("phase1", "P1", lambda s: s, lambda s: next(verdicts))]
    state = orchestrator.run(GlobalState(project_id="PROJ_T"), start="phase1", end="phase1")
    assert [e.queue_item for e in state.human_escalations] == ["phase1_halt"]
    state = orchestrator.run(state, start="phase1", end="phase1")
    assert state.human_escalations == []
