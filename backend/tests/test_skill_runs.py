"""Advisor runs: a seed of 0 is a seed, and when an advisor has to run phase
agents first, their output is merged onto the stored state instead of
replacing it, so a producer's edit made meanwhile is kept."""
from core.messaging.envelope import broadcast, log_event
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from core.skills import registry
from domains.skills import agents
from domains.skills import router as skills_router
from services import skill_store, supabase_client

PROJECT = "PROJ_NEON_NIGHTS"


def _stage(*args, **kwargs):
    return None


def test_a_seed_of_zero_reaches_the_simulator(offline, monkeypatch):
    seeds = []
    real = agents.audience_sim.run_simulation

    def spy(state, material, **kwargs):
        seeds.append(kwargs["seed"])
        return real(state, material, **kwargs)

    monkeypatch.setattr(agents.audience_sim, "run_simulation", spy)
    skill = registry.get("audience-simulation")
    state = Orchestrator().run(GlobalState(project_id=PROJECT), start="phase1", end="phase1")
    agents.run_audience(skill, state, {"seed": 0}, _stage, [])
    agents.run_audience(skill, state, {}, _stage, [])
    assert seeds == [0, 20260903]


def test_an_edit_made_while_an_advisor_prepares_is_kept(state_dir, offline, monkeypatch):
    supabase_client.save_state(GlobalState(project_id=PROJECT, director_notes="before"))
    real_prepare = agents.prepare_skill

    def prepare_then_edit(skill, state, params, stage):
        changed = real_prepare(skill, state, params, stage)

        def edit(stored):
            stored.director_notes = "edited while the advisor worked"
            log_event(stored, broadcast("agent_director_orchestrator", "task_status_update", {"n": 1}))

        supabase_client.update_state(PROJECT, edit)
        return changed

    monkeypatch.setattr(agents, "prepare_skill", prepare_then_edit)
    skill = registry.get("casting")
    record = skills_router._skeleton(skill, PROJECT, {}, "usr_1")
    skills_router._worker(record, skill, {})

    assert record["status"] == "complete", record.get("error")
    stored = supabase_client.load_state(PROJECT)
    assert stored.director_notes == "edited while the advisor worked"
    assert stored.candidates and stored.casting_status == "LOCKED", "the seeded pool is saved too"
    intents = [e["intent"] for e in stored.event_log]
    assert intents.count("task_status_update") >= 3, "the edit's envelope and the advisor's own"
    assert skill_store.get(PROJECT, record["run_id"])["status"] == "complete"
