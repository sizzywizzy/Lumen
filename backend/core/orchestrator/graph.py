"""The Director Orchestrator — one DAG that owns GlobalState and routes the six phases.

Kept LangGraph-shaped but dependency-free for now: every phase is a node
`(GlobalState) -> GlobalState`, and fail-fast checks are conditional edges.
Swapping this runner for a real LangGraph StateGraph (wrapped in Google Cloud
Agent Builder) is a drop-in change because the node signature already matches.

Agents never call each other across phases — they emit A2A envelopes and the
orchestrator decides what runs next.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from core.orchestrator.state import GlobalState

PhaseFn = Callable[[GlobalState], GlobalState]
# A conditional edge inspects state after a phase; returning a string halts the
# pipeline with that reason, returning None continues to the next phase.
EdgeFn = Callable[[GlobalState], Optional[str]]


@dataclass
class PhaseNode:
    key: str            # "phase1" ... "phase6"
    title: str
    run: PhaseFn
    fail_fast: Optional[EdgeFn] = None


def _no_viable_candidates(state: GlobalState) -> Optional[str]:
    """Risk Router (Phase I): purge disqualified, halt if nobody survives."""
    if not state.active_candidates():
        return "All candidates disqualified by risk router — re-open sourcing."
    return None


def _all_territories_blocked(state: GlobalState) -> Optional[str]:
    """Phase IV fail-fast: no territory cleared means nothing to launch."""
    if state.compliance_state and all(v == "BLOCKED" for v in state.compliance_state.values()):
        return "Every territory BLOCKED in compliance — launch prep halted."
    return None


def build_graph() -> list[PhaseNode]:
    # Imported here so `core` stays importable without the domains, and because
    # the graph definition is the composition root that wires them together.
    from domains.casting.agents import run_phase1_precasting, run_phase2_audition
    from domains.production.agents import run_phase3_schedule, run_phase4_compliance
    from domains.launch.agents import run_phase5_audience, run_phase6_marketing

    return [
        PhaseNode("phase1", "Pre-Casting Intelligence & Compliance", run_phase1_precasting, _no_viable_candidates),
        PhaseNode("phase2", "Audition Analysis & Scorecard", run_phase2_audition),
        PhaseNode("phase3", "Script → Schedule", run_phase3_schedule),
        PhaseNode("phase4", "Compliance, Localization & Launch Prep", run_phase4_compliance, _all_territories_blocked),
        PhaseNode("phase5", "Audience Simulation & Predictive Reviews", run_phase5_audience),
        PhaseNode("phase6", "Marketing, PR & Autonomous Social Launch", run_phase6_marketing),
    ]


class Orchestrator:
    """agent_director_orchestrator: runs phases in order, applies fail-fast edges,
    and queues human escalations on halt."""

    def __init__(self) -> None:
        self.nodes = build_graph()

    def phase_keys(self) -> list[str]:
        return [n.key for n in self.nodes]

    def run(self, state: GlobalState, start: str = "phase1", end: str = "phase6") -> GlobalState:
        keys = self.phase_keys()
        if start not in keys or end not in keys or keys.index(start) > keys.index(end):
            raise ValueError(f"Invalid phase range {start}..{end}. Valid: {keys}")

        for node in self.nodes[keys.index(start): keys.index(end) + 1]:
            state = node.run(state)
            if node.fail_fast:
                halt_reason = node.fail_fast(state)
                if halt_reason:
                    state.escalate(queue_item=f"{node.key}_halt", reason=halt_reason)
                    break
        return state
