"""One audience simulation per production at a time, and a run that a restart
cut off is reported as failed instead of staying "running" forever."""
from fastapi.testclient import TestClient

from core.orchestrator.state import GlobalState
from domains.audience import router as audience_router
from services import simulation_store, supabase_client

PROJECT = "PROJ_NEON_NIGHTS"
URL = f"/api/audience/simulations/{PROJECT}"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _client():
    from main import app

    return TestClient(app)


def _seeded(signed_in, make_production, monkeypatch):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(GlobalState(project_id=PROJECT))
    monkeypatch.setattr(audience_router, "_ACTIVE", set())
    monkeypatch.setattr(audience_router, "_ACTIVE_RUNS", set())
    # The thread is never started here, so the first run stays in flight.
    monkeypatch.setattr(audience_router, "_run_in_background", lambda *args: None)
    return token


def test_a_second_simulation_waits_for_the_first(state_dir, signed_in, make_production, monkeypatch):
    token = _seeded(signed_in, make_production, monkeypatch)
    client = _client()
    body = {"material": "A cab driver chases a deepfake ring.", "panel_size": 20, "markets": ["us"]}

    first = client.post(URL, headers=_auth(token), json=body)
    assert first.status_code == 202
    assert simulation_store.get(PROJECT, first.json()["simulation_id"])["config"]["markets"] == ["US"]
    second = client.post(URL, headers=_auth(token), json=body)
    assert second.status_code == 409
    listed = client.get(URL, headers=_auth(token)).json()["simulations"]
    assert [s["status"] for s in listed] == ["running"], "a run this process owns is still running"


def test_an_unknown_market_is_refused_with_the_code_named(state_dir, signed_in, make_production, monkeypatch):
    token = _seeded(signed_in, make_production, monkeypatch)
    response = _client().post(URL, headers=_auth(token), json={"material": "x", "markets": ["us", "zz"]})
    assert response.status_code == 422
    assert "ZZ" in response.json()["detail"][0]["msg"]


def test_a_run_cut_off_by_a_restart_reads_as_failed(state_dir, signed_in, make_production, monkeypatch):
    token = _seeded(signed_in, make_production, monkeypatch)
    req = audience_router.SimulationRequest(panel_size=20, markets=[])
    record = audience_router._skeleton(PROJECT, req, "material", "label", seed=1)
    record["stages"][0]["status"] = "running"
    record["traceback"] = "server-side detail"
    simulation_store.save(record)  # stored as running, but no thread here owns it
    client = _client()

    detail = client.get(f"{URL}/{record['simulation_id']}", headers=_auth(token)).json()
    assert detail["status"] == "failed" and "restart" in detail["error"]
    assert detail["stages"][0]["status"] == "failed" and "traceback" not in detail
    assert simulation_store.get(PROJECT, record["simulation_id"])["status"] == "failed", "and it is stored so"
    assert client.get(URL, headers=_auth(token)).json()["simulations"][0]["status"] == "failed"
    assert client.post(URL, headers=_auth(token), json={"material": "x", "markets": []}).status_code == 202


def test_a_finished_run_frees_the_production(state_dir, monkeypatch):
    supabase_client.save_state(GlobalState(project_id=PROJECT))
    req = audience_router.SimulationRequest(panel_size=20, markets=[])
    record = audience_router._skeleton(PROJECT, req, "material", "label", seed=1)
    monkeypatch.setattr(audience_router, "_ACTIVE", {PROJECT})
    monkeypatch.setattr(audience_router, "_ACTIVE_RUNS", {record["simulation_id"]})

    def broken(*args, **kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(audience_router.audience_sim, "run_simulation", broken)
    audience_router._execute(record, "material", 1, req)
    assert record["status"] == "failed"
    assert audience_router._ACTIVE == set() and audience_router._ACTIVE_RUNS == set()
