"""State reads stay small: no screenplay text, only the latest envelopes, and
a bodiless 304 when nothing changed. The Live Agent Terminal pages through
/api/events for the full log."""
from fastapi.testclient import TestClient

from core.messaging.envelope import broadcast, log_event
from core.orchestrator.state import Candidate, GlobalState
from core.responses import STATE_EVENT_TAIL
from services import supabase_client

PROJECT = "PROJ_NEON_NIGHTS"


def _auth(token, **extra):
    return {"Authorization": f"Bearer {token}", **extra}


def _client():
    from main import app

    return TestClient(app)


def _busy_state(envelopes: int) -> GlobalState:
    state = GlobalState(project_id=PROJECT, script_context={"title": "Neon Nights", "raw_text": "FADE IN. " * 5000})
    for n in range(envelopes):
        log_event(state, broadcast("agent_intake", "candidate_ingested", {"n": n}))
    return state


def test_a_state_read_leaves_out_the_screenplay_and_the_old_traffic(state_dir, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(_busy_state(STATE_EVENT_TAIL + 50))

    body = _client().get(f"/api/state/{PROJECT}", headers=_auth(token)).json()
    assert "raw_text" not in body["script_context"]
    assert body["script_context"]["title"] == "Neon Nights"
    assert len(body["event_log"]) == STATE_EVENT_TAIL
    assert (body["event_count"], body["event_offset"]) == (STATE_EVENT_TAIL + 50, 50)
    assert body["event_log"][0]["payload"] == {"n": 50}


def test_an_unchanged_state_answers_304(state_dir, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(_busy_state(3))
    client = _client()

    first = client.get(f"/api/state/{PROJECT}", headers=_auth(token))
    etag = first.headers["etag"]
    again = client.get(f"/api/state/{PROJECT}", headers=_auth(token, **{"If-None-Match": etag}))
    assert again.status_code == 304 and again.content == b""
    assert again.headers["etag"] == etag

    supabase_client.update_state(PROJECT, lambda s: setattr(s, "director_notes", "changed"))
    changed = client.get(f"/api/state/{PROJECT}", headers=_auth(token, **{"If-None-Match": etag}))
    assert changed.status_code == 200 and changed.json()["director_notes"] == "changed"


def test_the_terminal_pages_through_the_whole_log(state_dir, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(_busy_state(620))
    client = _client()

    first = client.get(f"/api/events/{PROJECT}", headers=_auth(token)).json()
    assert (first["total"], first["offset"], len(first["events"])) == (620, 0, 500)
    rest = client.get(f"/api/events/{PROJECT}?since=500&limit=500", headers=_auth(token)).json()
    assert [e["payload"]["n"] for e in rest["events"]] == list(range(500, 620))
    assert client.get(f"/api/events/{PROJECT}?limit=501", headers=_auth(token)).status_code == 422


def test_a_casting_decision_returns_its_own_envelope_not_the_log(state_dir, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    state = _busy_state(40)
    state.candidates = [Candidate(id="CAND_1", name="Lucia Morales", role_id="ROLE_LEAD", status="SCREENING")]
    supabase_client.save_state(state)

    body = _client().patch(f"/api/casting/candidates/{PROJECT}/CAND_1", headers=_auth(token),
                           json={"status": "LOCKED"}).json()
    assert body["candidate"]["status"] == "LOCKED" and body["casting_status"] == "LOCKED"
    assert body["event"]["payload"]["to"] == "LOCKED" and "event_log" not in body
    stored = supabase_client.load_state(PROJECT)
    assert stored.event_log[-1] == body["event"] and len(stored.event_log) == 41


def test_shoot_day_reports_and_settings_are_checked(state_dir, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(GlobalState(project_id=PROJECT))
    client = _client()

    def settings(**body):
        return client.put(f"/api/production/settings/{PROJECT}", headers=_auth(token), json=body)

    assert settings(min_hours_per_day=0).status_code == 422
    assert settings(max_hours_per_day=30).status_code == 422
    assert settings(min_hours_per_day=11, max_hours_per_day=10).status_code == 422
    saved = settings(min_hours_per_day=4, max_hours_per_day=12, excluded_states=[" nv", ""])
    assert saved.status_code == 200
    assert saved.json()["schedule"]["director_constraints"]["excluded_states"] == ["NV"]

    def report(**body):
        return client.post(f"/api/production/shoot-day/{PROJECT}", headers=_auth(token), json=body)

    assert report(date="03/01/2027").status_code == 422
    assert report(date="").status_code == 422
    assert report(date="2027-03-02", missed_scene_ids=["SCN_001"], reshoot_date="2027-03-01").status_code == 422
    ok = report(date="2027-03-02", missed_scene_ids=["SCN_001"], reshoot_date="2027-03-05", note="Rain")
    assert ok.status_code == 200
    assert ok.json()["schedule"]["reshoots"][0]["to_date"] == "2027-03-05"
