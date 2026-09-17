"""Merging a finished background run onto the state stored now.

A pipeline run works on its own copy of the state for minutes. Saving that
copy back would drop whatever was saved in the meantime: a candidate decision,
an expense, shoot-day notes, a screenplay upload, advisor and simulation
traffic. So a finished run is merged instead. Each phase that ran contributes
the fields it owns (PhaseNode.owns) and the escalations it raises; everything
else stays as stored.

A fresh run (the full pipeline) starts from a reset state, so there the run's
copy is the base, and the stored state gives back what a person can change
while it runs: the expenses, the schedule rules and the screenplay.
"""
import copy
from typing import Any, Iterable

from core.orchestrator.graph import PhaseNode
from core.orchestrator.state import GlobalState


def _get(obj: Any, path: str) -> Any:
    for part in path.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else getattr(obj, part)
    return obj


def _set(obj: Any, path: str, value: Any) -> None:
    *parents, leaf = path.split(".")
    for part in parents:
        obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
    if isinstance(obj, dict):
        if value is None:
            obj.pop(leaf, None)
        else:
            obj[leaf] = value
    else:
        setattr(obj, leaf, value)


def _stored_context(context: dict, stored: dict, keep: tuple[str, ...]) -> dict:
    """`context` with the `keep` keys as they are in `stored`."""
    out = {k: v for k, v in context.items() if k not in keep}
    out.update({k: copy.deepcopy(stored[k]) for k in keep if k in stored})
    return out


def merge_run(
    latest: GlobalState,
    run: GlobalState,
    ran: Iterable[PhaseNode],
    stored_log_len: int,
    *,
    keep_context: tuple[str, ...] = (),
    fresh: bool = False,
) -> GlobalState:
    """The state to save once `run` has finished.

    latest          what is stored now
    run             the run's own copy, after its phases
    ran             the phases that actually ran (a halt stops the rest)
    stored_log_len  how long the stored event log was when the run started
    keep_context    script_context keys a run never owns (the screenplay)
    fresh           the run started from a reset state (the full pipeline)
    """
    ran = list(ran)
    if fresh:
        merged = run.model_copy(deep=True)
        merged.budget_state.expenses = copy.deepcopy(latest.budget_state.expenses)
        merged.schedule.director_constraints = copy.deepcopy(latest.schedule.director_constraints)
        merged.schedule.shoot_settings = copy.deepcopy(latest.schedule.shoot_settings)
        merged.script_context = _stored_context(merged.script_context, latest.script_context, keep_context)
        # The run's traffic, then anything other workers logged while it ran.
        merged.event_log = run.event_log + latest.event_log[stored_log_len:]
        return merged

    merged = latest.model_copy(deep=True)
    for node in ran:
        for path in node.owns:
            if path == "script_context":
                # The profiler rewrites the brief but never the screenplay or
                # the scene breakdown; those stay as stored.
                merged.script_context = _stored_context(
                    copy.deepcopy(run.script_context), latest.script_context, (*keep_context, "scenes"))
            else:
                _set(merged, path, copy.deepcopy(_get(run, path)))
    prefixes = tuple(p for node in ran for p in (*node.escalations, f"{node.key}_halt"))
    if prefixes:
        merged.human_escalations = [
            e for e in merged.human_escalations if not e.queue_item.startswith(prefixes)
        ] + [e.model_copy() for e in run.human_escalations if e.queue_item.startswith(prefixes)]
    merged.event_log.extend(copy.deepcopy(run.event_log[stored_log_len:]))
    return merged
