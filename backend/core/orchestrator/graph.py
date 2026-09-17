"""The Director Orchestrator — one DAG that owns GlobalState and routes the six phases.

An explicit state machine, written without an orchestration framework on
purpose: every phase is a node `(GlobalState) -> GlobalState`, a fail-fast
check after a phase is a conditional edge that can halt the run with a human
escalation, and each phase resets its own output before it runs so a re-run
replaces rather than stacks. Nothing here imports LangGraph, and that is the
design, not a placeholder.

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
# Progress hook: (phase key, "running" | "complete" | "halted").
ProgressFn = Callable[[str, str], None]


@dataclass
class PhaseNode:
    key: str            # "phase1" ... "phase6"
    title: str
    run: PhaseFn
    fail_fast: Optional[EdgeFn] = None
    # What the phase writes: dotted GlobalState paths and the queue-item
    # prefixes of the escalations it raises. A finished background run copies
    # exactly these onto the stored state (core/orchestrator/merge.py).
    owns: tuple[str, ...] = ()
    escalations: tuple[str, ...] = ()


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
        PhaseNode("phase1", "Pre-Casting Intelligence & Compliance", run_phase1_precasting, _no_viable_candidates,
                  owns=("script_context", "role_requirements", "scoring_weights", "candidates", "casting_status"),
                  escalations=("cast_signoff:",)),
        PhaseNode("phase2", "Audition Analysis & Scorecard", run_phase2_audition,
                  owns=("candidates", "casting_status"), escalations=("cast_signoff:",)),
        PhaseNode("phase3", "Script → Schedule", run_phase3_schedule,
                  owns=("script_context.scenes", "schedule.stripboard", "schedule.conflicts",
                        "budget_state.daily_burn", "budget_state.alerts"),
                  escalations=("venue:", "schedule:")),
        PhaseNode("phase4", "Compliance, Localization & Launch Prep", run_phase4_compliance, _all_territories_blocked,
                  owns=("compliance_state",), escalations=("compliance:",)),
        PhaseNode("phase5", "Audience Simulation & Predictive Reviews", run_phase5_audience,
                  owns=("audience_report",), escalations=("recut:",)),
        PhaseNode("phase6", "Marketing, PR & Autonomous Social Launch", run_phase6_marketing,
                  owns=("marketing_assets",), escalations=("asset:",)),
    ]


class Orchestrator:
    """agent_director_orchestrator: runs phases in order, applies fail-fast edges,
    and queues human escalations on halt."""

    def __init__(self) -> None:
        self.nodes = build_graph()

    def phase_keys(self) -> list[str]:
        return [n.key for n in self.nodes]

    def span(self, start: str = "phase1", end: str = "phase6") -> list[PhaseNode]:
        """The nodes from `start` to `end`, inclusive."""
        keys = self.phase_keys()
        if start not in keys or end not in keys or keys.index(start) > keys.index(end):
            raise ValueError(f"Invalid phase range {start}..{end}. Valid: {keys}")
        return self.nodes[keys.index(start): keys.index(end) + 1]

    def run(
        self, state: GlobalState, start: str = "phase1", end: str = "phase6",
        on_phase: Optional[ProgressFn] = None,
    ) -> GlobalState:
        report = on_phase or (lambda key, status: None)
        for node in self.span(start, end):
            report(node.key, "running")
            # A re-run replaces an earlier halt on this phase rather than stacking it.
            state.clear_escalations(f"{node.key}_halt")
            state = node.run(state)
            halt_reason = node.fail_fast(state) if node.fail_fast else None
            if halt_reason:
                state.escalate(queue_item=f"{node.key}_halt", reason=halt_reason)
                report(node.key, "halted")
                break
            report(node.key, "complete")
        return state
