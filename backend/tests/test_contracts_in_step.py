"""Things that have to be changed in pairs, checked here instead of remembered.

The first two used to be entries on the TODO list, kept by hand:

1.  What a phase writes and what `PhaseNode.owns` says it writes. A finished
    background run copies exactly the declared fields onto the stored state
    (core/orchestrator/merge.py), so a field a phase writes but does not
    declare is computed and then silently dropped. The same goes for the
    escalations it raises: an undeclared queue item is never cleared, so a
    re-run stacks a second copy of it instead of replacing the first.

2.  An advisor's inputs, and what `skills.md` and AGENT.md Section 8 say they
    are. The run controls are what the dashboard offers and what the API
    accepts, so the three have to agree.

3.  How many agents there are. AGENT.md Section 4 is the roster, and the README
    quotes its size as a headline figure. Both are prose, so both drift — and a
    number nobody can check is worth nothing. The roster is pinned here to the
    agents that actually speak in an offline run, and the README to the roster.
"""
import re

import pytest

from core import config
from core.messaging import envelope
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from core.skills import registry
from domains.launch.agents import audience_sim
from domains.skills import agents
from domains.skills.router import SkillRunParams

# Fields no phase owns: the id never changes, and the run's traffic, model
# tally and escalations are merged by their own rules.
NOT_OWNED = {"project_id", "event_log", "model_use", "human_escalations"}

# The metadata keys AGENT.md Section 8 says every SKILL.md carries.
DOCUMENTED_METADATA = ("agent", "phase", "model", "owner", "reads", "writes", "intents", "version")


def _repo_file(name: str) -> str:
    return (config.BACKEND_DIR.parent / name).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """A Markdown section's body, up to the next heading of any level."""
    found = re.search(rf"^{re.escape(heading)}$(.*?)(?=^\#{{1,3}} |\Z)", text, re.S | re.M)
    return found.group(1) if found else ""


# ------------------------------------------------- what each phase declares --


def _changed_paths(before: dict, after: dict, declared: tuple[str, ...], prefix: str = "") -> set[str]:
    """The dotted paths that differ, descending into a field only as far as
    some declared path goes into it: `owns=("schedule.stripboard",)` compares
    the stripboard on its own, while `owns=("compliance_state",)` compares the
    whole map."""
    out = set()
    for key in set(before) | set(after):
        path = f"{prefix}{key}"
        if before.get(key) == after.get(key):
            continue
        goes_deeper = any(d.startswith(f"{path}.") for d in declared)
        if goes_deeper and isinstance(before.get(key), dict) and isinstance(after.get(key), dict):
            out |= _changed_paths(before[key], after[key], declared, f"{path}.")
        else:
            out.add(path)
    return out


def _covers(path: str, owns: tuple[str, ...]) -> bool:
    return any(path == owned or path.startswith(f"{owned}.") for owned in owns)


@pytest.fixture(scope="module")
def phase_by_phase(request):
    """One offline pipeline run, kept as (node, before, after) per phase."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(config, "has_llm", lambda: False)
        patch.setattr(config, "has_tavily", lambda: False)
        orchestrator = Orchestrator()
        state = GlobalState(project_id="PROJ_CONTRACTS")
        steps = []
        for node in orchestrator.nodes:
            before = state.model_dump(mode="json")
            state = orchestrator.run(state, start=node.key, end=node.key)
            steps.append((node, before, state.model_dump(mode="json")))
        return steps


def test_every_field_a_phase_writes_is_a_field_it_owns(phase_by_phase):
    undeclared = {}
    for node, before, after in phase_by_phase:
        changed = _changed_paths(before, after, node.owns) - NOT_OWNED
        missing = sorted(path for path in changed if not _covers(path, node.owns))
        if missing:
            undeclared[node.key] = missing

    assert not undeclared, (
        f"these phases write fields their `owns` does not list, so a background run drops them: {undeclared}. "
        "Add the path in core/orchestrator/graph.py, or stop writing it."
    )


def _resolves_on_state(path: str) -> bool:
    """Whether merge could follow this path. A free-form map (script_context)
    ends the walk: any key in it is a legitimate thing to own."""
    here = GlobalState(project_id="PROJ_CONTRACTS")
    for part in path.split("."):
        if isinstance(here, dict):
            return True
        if not hasattr(here, part):
            return False
        here = getattr(here, part)
    return True


def test_every_phase_owns_something_that_exists(phase_by_phase):
    """A renamed field left behind in an `owns` list would raise mid-merge,
    after the phases had already done their work."""
    for node, _, _ in phase_by_phase:
        unknown = [path for path in node.owns if not _resolves_on_state(path)]
        assert not unknown, f"{node.key} owns {unknown}, which GlobalState no longer has"


def test_every_escalation_a_phase_raises_is_one_it_declares(phase_by_phase):
    """An undeclared queue item survives a re-run of the phase that raised it,
    so the Overview would show the old decision next to the new one."""
    stray = {}
    for node, before, after in phase_by_phase:
        raised = [e["queue_item"] for e in after["human_escalations"]][len(before["human_escalations"]):]
        prefixes = (*node.escalations, f"{node.key}_halt")
        undeclared = sorted({item for item in raised if not item.startswith(prefixes)})
        if undeclared:
            stray[node.key] = undeclared

    assert not stray, f"escalations raised under a prefix the phase does not declare: {stray}"


# ------------------------------------------------------- the advisor skills --


@pytest.mark.parametrize("skill", registry.load_all(), ids=lambda s: s.name)
def test_every_skill_has_a_runner_and_a_page_in_skills_md(skill):
    assert skill.name in agents.RUNNERS, f"no runner in domains/skills/agents.py for {skill.name}"
    assert _section(_repo_file("skills.md"), f"### {skill.name}"), \
        f"skills.md Part A has no '### {skill.name}' section"


@pytest.mark.parametrize("skill", registry.load_all(), ids=lambda s: s.name)
def test_every_skill_carries_the_metadata_agent_md_promises(skill):
    missing = [key for key in DOCUMENTED_METADATA if key not in skill.metadata]
    assert not missing, f"{skill.name} SKILL.md is missing {missing}, which AGENT.md Section 8 says it carries"


@pytest.mark.parametrize("skill", registry.load_all(), ids=lambda s: s.name)
def test_a_skills_run_controls_are_the_inputs_skills_md_lists(skill):
    """The Inputs row names every control the dashboard shows, or says there
    are none."""
    body = _section(_repo_file("skills.md"), f"### {skill.name}")
    row = next((line for line in body.splitlines() if line.startswith("| Inputs")), "")
    assert row, f"skills.md has no Inputs row for {skill.name}"

    controls = [control["key"] for control in agents.input_schema(skill)]
    if not controls:
        assert "No user inputs" in row, f"{skill.name} takes no run inputs; say so in its skills.md Inputs row"
        return
    undocumented = [key for key in controls if f"`{key}`" not in row]
    assert not undocumented, f"{skill.name} takes {undocumented}, which its skills.md Inputs row does not mention"


@pytest.mark.parametrize("skill", registry.load_all(), ids=lambda s: s.name)
def test_a_skills_intents_are_in_the_shared_vocabulary(skill):
    """Adding a skill never adds an intent (AGENT.md Section 8)."""
    vocabulary = _section(_repo_file("AGENT.md"), "## 5. Intent Vocabulary")
    unknown = [intent for intent in skill.meta_list("intents") if f"`{intent}`" not in vocabulary]
    assert not unknown, f"{skill.name} declares {unknown}, which AGENT.md Section 5 does not list"


def test_the_api_accepts_exactly_the_controls_the_skills_offer():
    """`SkillRunParams` forbids unknown keys, so a control it has no field for
    is rejected the moment someone uses it."""
    offered = {control["key"] for skill in registry.load_all() for control in agents.input_schema(skill)}
    accepted = set(SkillRunParams.model_fields)

    assert offered - accepted == set(), f"the dashboard offers {sorted(offered - accepted)}; the API rejects them"
    assert accepted - offered == set(), f"the API accepts {sorted(accepted - offered)}, which no skill offers"


# --------------------------------------------------------- the agent roster --


def _registry_entries() -> dict[str, str]:
    """Every agent AGENT.md Section 4 registers, mapped to the group it sits
    under ("Phase III — Script -> Schedule", "Skills — ...").

    Section 4 *is* the roster: one bold `**`agent_x`**` entry per agent,
    grouped by phase. `_section` stops at the first `###`, so this reads the
    whole section, to the next `##`.
    """
    found = re.search(r"^## 4\. Agent Registry\s*$(.*?)(?=^## )", _repo_file("AGENT.md"), re.S | re.M)
    assert found, "AGENT.md no longer has a '## 4. Agent Registry' section for the roster to come from"

    entries: dict[str, str] = {}
    group = ""
    for line in found.group(1).splitlines():
        if line.startswith("### "):
            group = line[4:].strip()
        named = re.match(r"\*\*`(agent_[a-z0-9_]+)`\*\*", line)
        if named:
            entries[named.group(1)] = group
    return entries


@pytest.fixture(scope="module")
def agents_at_work(phase_by_phase):
    """Every agent the running system actually has, derived rather than listed.

    Two sources, because agents work in two places: senders in an offline run
    of all six phases, plus senders in a standalone simulation — which is where
    `agent_script_analyst` reads the material, Phase V having the Phase I brief
    already. The four advisors answer one request at a time on their own
    threads, and running each one here would mean running its prerequisite
    phases again, so they are taken from the `agent` key in their SKILL.md
    (AGENT.md Section 8) rather than from a run.
    """
    spoke = {event["sender"] for _, _, after in phase_by_phase for event in after["event_log"]}

    state = GlobalState(project_id="PROJ_CONTRACTS_SIM")
    audience_sim.run_simulation(
        state,
        "A retired cartographer walks a drowned coastline, mapping what the sea took. " * 12,
        panel_size=40,
        markets=["US", "IN"],
    )
    spoke |= {event["sender"] for event in state.event_log}
    return spoke | {skill.agent for skill in registry.load_all()}


def test_every_agent_at_work_is_in_the_registry(agents_at_work):
    """An agent in the code but not in Section 4 is invisible to everything that
    reads the roster: the count the README quotes, the checklist in Section 7,
    and anyone trying to find out who does what. The orchestrator is left out on
    purpose — it is Section 1 infrastructure, not one of the specialists."""
    undocumented = sorted(agents_at_work - set(_registry_entries()) - {envelope.ORCHESTRATOR})
    assert not undocumented, (
        f"these agents are at work but AGENT.md Section 4 does not register them: {undocumented}. "
        "Add an entry there — Section 7 is the checklist — or stop sending under that id."
    )


def test_every_registered_agent_is_still_at_work(agents_at_work):
    """The other direction. An entry left behind after an agent was renamed or
    removed inflates the number the README quotes, which is the drift this pair
    of tests exists to stop."""
    retired = sorted(set(_registry_entries()) - agents_at_work)
    assert not retired, (
        f"AGENT.md Section 4 registers {retired}, which nothing at work sends as. "
        "Remove the entry, or correct the id."
    )


def test_the_readme_quotes_the_number_of_agents_the_registry_holds():
    """The README's one figure that can go stale in silence, and the reason the
    two tests above exist: with the roster pinned to what runs, this number is
    checkable rather than remembered. The same figure is in the repository's
    GitHub description, which no test here can read — so change both."""
    count = len(_registry_entries())
    claim = f"{count} specialist agents"
    assert claim in _repo_file("README.md"), (
        f"the README does not say '{claim}'. AGENT.md Section 4 registers {count} agents, "
        "the orchestrator aside. Update README.md and the repository's GitHub description together."
    )


def test_the_registry_groups_agents_by_every_phase_that_runs():
    """Section 4 groups the agents by phase, so a seventh phase added to the
    graph without a group of its own would carry undocumented agents."""
    grouped = {group for group in _registry_entries().values() if group.startswith("Phase ")}
    running = Orchestrator().phase_keys()
    assert len(grouped) == len(running), (
        f"the orchestrator runs {len(running)} phases but AGENT.md Section 4 groups agents "
        f"under {len(grouped)}: {sorted(grouped)}. Give the new phase its own group."
    )
