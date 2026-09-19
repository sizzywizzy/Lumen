"""Collect the prompts Lumen actually sends, without sending any of them.

Every model call in the product goes through `llm.generate_json_traced`, so
standing in for that function during an offline run records the real prompt, the
real system instruction, the real tier and the `mock` the agent would have fallen
back to — and hands the mock straight back, which is exactly what the offline
run would have done anyway. So capturing the prompt set costs nothing: no key, no
quota, no network.

A prompt is worth capturing only if it varies the way real work varies, so the
matrix below runs the pipeline over several budgets, localities and scripts, and
the simulator over several materials, panel sizes and market sets. Identical
prompts are dropped afterwards: three hundred copies of one prompt is one prompt.
"""
import hashlib
from typing import Any, Callable, Iterator

from contextlib import contextmanager

from core import config
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from domains.launch.agents import audience_sim
from services import llm

# Productions to plan: (project_id, budget, locality). The budget sets every
# casting and venue cap and the locality steers the scout, so each of these
# reaches the agents as different material.
PRODUCTIONS = [
    ("PROJ_SO_A", 250_000, "Los Angeles, CA"),
    ("PROJ_SO_B", 900_000, "Mumbai, India"),
    ("PROJ_SO_C", 75_000, "Lagos, Nigeria"),
    ("PROJ_SO_D", 3_000_000, "London, United Kingdom"),
    ("PROJ_SO_E", 420_000, "Seoul, South Korea"),
    ("PROJ_SO_F", 1_500_000, "Mexico City, Mexico"),
    ("PROJ_SO_G", 180_000, "Reykjavik, Iceland"),
    ("PROJ_SO_H", 640_000, "Sao Paulo, Brazil"),
    ("PROJ_SO_I", 55_000, "Wellington, New Zealand"),
    ("PROJ_SO_J", 2_200_000, "Berlin, Germany"),
    ("PROJ_SO_K", 310_000, "Cairo, Egypt"),
    ("PROJ_SO_L", 1_100_000, "Toronto, Canada"),
]

# Materials to screen: (logline seed, panel size, markets). Different genres and
# content pull different analyses, cohorts and sensitivity findings.
MATERIALS = [
    ("A lighthouse keeper inherits a debt she cannot name, and the sea starts "
     "returning what the town threw away.", 200, ["US", "IN", "FR"]),
    ("Two rival street cartographers in a monsoon city discover their maps "
     "disagree about a neighbourhood that no longer exists.", 200, ["IN", "GB"]),
    ("A retired arms inspector takes a job verifying wedding cakes, and finds "
     "the same forgery techniques she spent thirty years chasing.", 120, ["US", "DE", "JP"]),
    ("On a generation ship, the only crime is wasting water, and the ship's "
     "gardener has been lying about the harvest for eleven years.", 200, ["US"]),
    ("A stand-up comedian loses the ability to remember anything funny and "
     "keeps performing anyway, to smaller and kinder rooms.", 80, ["GB", "AU", "CA"]),
    ("A border guard and a smuggler share a thermos every night for a decade "
     "without once discussing the crate between them.", 200, ["DE", "TR", "US"]),
    ("The last fax machine repairman in the country is summoned to a hospital "
     "that has been receiving pages from a ward it demolished.", 160, ["JP", "US"]),
]


def fingerprint(tier: str, system: str, prompt: str) -> str:
    """One prompt's identity: the three things that decide what comes back."""
    return hashlib.sha256(f"{tier}\x00{system}\x00{prompt}".encode("utf-8")).hexdigest()[:16]


@contextmanager
def recording(into: list[dict[str, Any]]) -> Iterator[None]:
    """Stand in for the one function that makes model calls, for this block."""
    original = llm.generate_json_traced

    def record(prompt, *, tier="flash", system=None, mock=None, schema=None, attempts_per_model=2):
        into.append({
            "tier": tier,
            "system": system or "",
            "prompt": prompt,
            "mock": mock,
        })
        # What the offline run would have returned, so the run carries on and the
        # later phases get realistic state to build their own prompts from.
        if mock is None:
            raise llm.LLMUnavailable("captured a call with no sample output")
        return mock, {"live": False, "source": llm.MOCK, "provider": None, "model": None}

    llm.generate_json_traced = record
    try:
        yield
    finally:
        llm.generate_json_traced = original


def _plan(project_id: str, budget: float, locality: str) -> None:
    orchestrator = Orchestrator()
    state = GlobalState(project_id=project_id)
    state.locality = locality
    state.budget_state.cap = budget
    for node in orchestrator.nodes:
        state = orchestrator.run(state, start=node.key, end=node.key)


def _screen(index: int, logline: str, panel_size: int, markets: list[str]) -> None:
    state = GlobalState(project_id=f"PROJ_SO_SIM{index}")
    # Long enough that the analysis prompt sees a real body of material.
    audience_sim.run_simulation(
        state, (logline + " ") * 30, panel_size=panel_size, markets=markets
    )


def collect(on_step: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Run the matrix and return the distinct prompts, with a schema for each.

    Forces every provider off first: a capture run that reached a live model
    would spend quota to collect prompts it already knows.
    """
    calls: list[dict[str, Any]] = []
    denied = ("has_gemini", "has_cerebras", "has_groq", "has_ollama", "has_tavily")
    restore = {check: getattr(config, check) for check in denied}
    try:
        for check in denied:
            setattr(config, check, lambda: False)
        with recording(calls):
            for project_id, budget, locality in PRODUCTIONS:
                on_step(f"planning {project_id} (${budget:,.0f}, {locality})")
                _plan(project_id, budget, locality)
            for index, (logline, panel, markets) in enumerate(MATERIALS):
                on_step(f"screening material {index + 1} (panel {panel}, {'/'.join(markets)})")
                _screen(index, logline, panel, markets)
    finally:
        for check, was in restore.items():
            setattr(config, check, was)

    prompts: dict[str, dict[str, Any]] = {}
    for call in calls:
        key = fingerprint(call["tier"], call["system"], call["prompt"])
        if key in prompts:
            prompts[key]["seen"] += 1
            continue
        prompts[key] = {
            "id": key,
            "tier": call["tier"],
            "system": call["system"],
            "prompt": call["prompt"],
            # The shape the agent expects, derived from what it falls back to.
            "schema": llm.schema_from_example(call["mock"]),
            "seen": 1,
        }

    return {
        "matrix": {
            "productions": len(PRODUCTIONS),
            "materials": len(MATERIALS),
        },
        "calls": len(calls),
        "prompts": sorted(prompts.values(), key=lambda p: (p["tier"], p["id"])),
    }
