"""The audience-simulation worker merges its envelopes onto the stored state
instead of saving back the copy it loaded when the run began, so a decision a
producer saves while a run is going is not lost when the run finishes."""
from core.messaging.envelope import broadcast, log_event
from core.orchestrator.state import GlobalState
from domains.audience import router as audience_router
from domains.launch.agents import audience_sim
from services import simulation_store, supabase_client

PROJECT = "PROJ_T"


def _result():
    return {
        "analysis": {}, "report": {"overall_score": 7.0}, "sensitivity": {}, "recommendations": {},
        "provenance": {"mode": "mock"}, "dimensions": [], "distribution_fingerprint": "abc",
        "cohorts": [], "panel": [], "responses": [], "distribution": {},
    }


def _start(monkeypatch, run):
    monkeypatch.setattr(audience_sim, "run_simulation", run)
    req = audience_router.SimulationRequest(panel_size=20, markets=[])
    record = audience_router._skeleton(PROJECT, req, "material", "label", seed=1)
    audience_router._execute(record, "material", 1, req)
    return record


def test_edits_made_during_a_run_survive_it(state_dir, monkeypatch):
    supabase_client.save_state(GlobalState(project_id=PROJECT, director_notes="original"))

    def fake_run(state, material, **kwargs):
        log_event(state, broadcast("agent_aggregation", "simulation_verdict_update", {"panel_size": 20}))
        # A producer saves a decision while the simulation is still running.
        edited = supabase_client.load_state(PROJECT)
        edited.director_notes = "edited during the run"
        log_event(edited, broadcast("agent_director_orchestrator", "task_status_update", {"source": "human_decision"}))
        supabase_client.save_state(edited)
        return _result()

    record = _start(monkeypatch, fake_run)

    assert record["status"] == "complete", record.get("error")
    stored = supabase_client.load_state(PROJECT)
    assert stored.director_notes == "edited during the run"
    assert [e["intent"] for e in stored.event_log] == ["task_status_update", "simulation_verdict_update"]
    assert simulation_store.get(PROJECT, record["simulation_id"])["status"] == "complete"


def test_a_failed_run_is_recorded_and_leaves_the_state_alone(state_dir, monkeypatch):
    supabase_client.save_state(GlobalState(project_id=PROJECT))

    def broken_run(state, material, **kwargs):
        raise RuntimeError("model down")

    record = _start(monkeypatch, broken_run)

    assert record["status"] == "failed"
    assert "model down" in record["error"]
    assert supabase_client.load_state(PROJECT).event_log == []


def test_a_run_for_a_missing_production_fails_cleanly(state_dir, monkeypatch):
    record = _start(monkeypatch, lambda *a, **k: _result())
    assert record["status"] == "failed"
    assert "No project state" in record["error"]
