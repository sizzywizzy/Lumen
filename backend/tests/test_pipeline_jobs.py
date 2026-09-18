"""Pipeline runs work in the background and merge onto the stored state.

The run routes answer 202 and the dashboard polls /api/pipeline/status. A run
works on its own copy of the state, so when it finishes only the fields its
phases own come from that copy: a decision, an expense, a new draft or another
worker's traffic saved while it ran is kept. Background threads run inline in
tests (conftest.py), and the edits below are made from inside the run.
"""
import threading

from fastapi.testclient import TestClient

from core.messaging.envelope import broadcast, log_event
from core.orchestrator import merge
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from domains.pipeline import jobs
from services import supabase_client

PROJECT = "PROJ_NEON_NIGHTS"
REAL_RUN = Orchestrator.run


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _client():
    from main import app

    return TestClient(app)


def _planned() -> GlobalState:
    return REAL_RUN(Orchestrator(), GlobalState(project_id=PROJECT))


def _edit_during_run(monkeypatch, edit):
    """Make every run call `edit` on the stored state once its phases are done
    but before it is merged, the moment a person could still be saving."""
    def run(self, state, start="phase1", end="phase6", on_phase=None):
        result = REAL_RUN(self, state, start, end, on_phase)
        supabase_client.update_state(PROJECT, edit)
        return result

    monkeypatch.setattr(Orchestrator, "run", run)


def test_a_run_answers_202_and_reports_each_phase(state_dir, offline, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    client = _client()
    assert client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()["status"] == "idle"

    started = client.post("/api/pipeline/run", json={"project_id": PROJECT}, headers=_auth(token))
    assert started.status_code == 202

    status = client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()
    assert status["job_id"] == started.json()["job_id"]
    assert status["status"] == "complete" and status["scope"] == "pipeline"
    assert [p["status"] for p in status["phases"]] == ["complete"] * 6
    assert status["log_start"] == 0
    assert status["summary"]["casting_status"] == "LOCKED"
    # The saved plan, then the poster that paints once it is saved.
    after_run = supabase_client.load_state(PROJECT).event_log[status["events"]:]
    assert after_run and {e["sender"] for e in after_run} <= {"agent_visual", "agent_pr_risk"}


def test_one_run_at_a_time_per_production(state_dir, offline, signed_in, make_production, monkeypatch):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(GlobalState(project_id=PROJECT))
    monkeypatch.setattr(jobs, "_spawn", lambda target, *args: None)  # the first run never finishes
    client = _client()

    assert client.post("/api/pipeline/run", json={"project_id": PROJECT}, headers=_auth(token)).status_code == 202
    for path, body in (("/api/pipeline/run", {"project_id": PROJECT}), (f"/api/casting/run/{PROJECT}", {}),
                       (f"/api/production/run/{PROJECT}", None), (f"/api/launch/run/{PROJECT}", None),
                       ("/api/pipeline/init", {"project_id": PROJECT})):
        assert client.post(path, json=body, headers=_auth(token)).status_code == 409, path
    assert client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()["status"] == "running"


def test_edits_saved_while_a_phase_run_works_survive_it(state_dir, offline, signed_in, make_production, monkeypatch):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(_planned())
    before = len(supabase_client.load_state(PROJECT).event_log)

    def edit(stored):
        stored.director_notes = "edited during the run"
        stored.budget_state.expenses.append({"category": "Crew", "description": "Grips", "amount": 900})
        stored.candidates[0].status = "DISQUALIFIED"
        log_event(stored, broadcast("agent_director_orchestrator", "task_status_update", {"source": "human_decision"}))

    _edit_during_run(monkeypatch, edit)
    client = _client()
    assert client.post(f"/api/production/run/{PROJECT}", headers=_auth(token)).status_code == 202

    stored = supabase_client.load_state(PROJECT)
    assert stored.director_notes == "edited during the run"
    assert stored.budget_state.spent == 900
    assert stored.candidates[0].status == "DISQUALIFIED", "casting was not part of this run"
    intents = [e["intent"] for e in stored.event_log[before:]]
    assert intents[0] == "task_status_update", "the edit's envelope stays, ahead of the run's own"
    assert {"schedule_updated", "compliance_result"} <= set(intents)
    assert stored.compliance_state["UAE"] == "BLOCKED"
    status = client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()
    assert status["log_start"] == before + 1


def test_a_draft_uploaded_during_a_casting_run_is_kept(state_dir, offline, signed_in, make_production, monkeypatch):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(_planned())

    def upload(stored):
        stored.script_context.update(raw_text="INT. DINER - DAY\nA new draft.", fingerprint="new-draft")

    _edit_during_run(monkeypatch, upload)
    response = _client().post(f"/api/casting/run/{PROJECT}", headers=_auth(token),
                              json={"locality": "Atlanta, GA", "director_notes": "Night shoots"})
    assert response.status_code == 202

    stored = supabase_client.load_state(PROJECT)
    context = stored.script_context
    assert (context["raw_text"], context["fingerprint"]) == ("INT. DINER - DAY\nA new draft.", "new-draft")
    assert context["title"] == "Neon Nights" and context["scenes"], "the profile is the run's, the breakdown stays"
    assert (stored.locality, stored.director_notes) == ("Atlanta, GA", "Night shoots")
    assert context["locality"] == "Atlanta, GA"


def test_a_full_run_keeps_the_material_and_other_workers_traffic(state_dir, offline, signed_in, make_production,
                                                                 monkeypatch):
    import main

    user, _ = signed_in()
    make_production(user)
    supabase_client.save_state(_planned())

    def edit(stored):
        stored.budget_state.expenses.append({"category": "Crew", "description": "Grips", "amount": 900})
        stored.schedule.shoot_settings["max_hours_per_day"] = 9
        log_event(stored, broadcast("agent_casting_advisor", "task_status_update", {"skill": "casting"}))

    _edit_during_run(monkeypatch, edit)
    main.run_pipeline(main.InitRequest(project_id=PROJECT, start_date="2027-03-01"), user=user)

    stored = supabase_client.load_state(PROJECT)
    assert stored.budget_state.spent == 900
    assert stored.schedule.shoot_settings == {"max_hours_per_day": 9, "start_date": "2027-03-01"}
    senders = [e["sender"] for e in stored.event_log]
    assert stored.event_log[0]["intent"] == "mandate_ready", "a full run starts a fresh log"
    assert senders.count("agent_casting_advisor") == 1, "traffic logged meanwhile is kept"
    assert senders.index("agent_casting_advisor") > senders.index("agent_publisher"), "after the run's own"
    assert stored.schedule.stripboard[0].date == "2027-03-01"


def test_a_failed_run_is_reported_and_leaves_the_state_alone(state_dir, offline, signed_in, make_production,
                                                            monkeypatch):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(_planned())
    before = supabase_client.load_state(PROJECT).model_dump()

    def broken(self, state, start="phase1", end="phase6", on_phase=None):
        on_phase(start, "running")
        raise RuntimeError("model down")

    monkeypatch.setattr(Orchestrator, "run", broken)
    client = _client()
    assert client.post(f"/api/launch/run/{PROJECT}", headers=_auth(token)).status_code == 202

    status = client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()
    assert status["status"] == "failed" and "model down" in status["error"]
    assert [p["status"] for p in status["phases"]] == ["failed", "pending"]
    assert supabase_client.load_state(PROJECT).model_dump() == before
    assert client.post(f"/api/launch/run/{PROJECT}", headers=_auth(token)).status_code == 202, "a failure frees the slot"


def test_a_phase_run_needs_a_stored_state(state_dir, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    assert _client().post(f"/api/production/run/{PROJECT}", headers=_auth(token)).status_code == 404


def test_merge_takes_only_what_the_phases_that_ran_own(offline):
    base = _planned()
    latest, run = base.model_copy(deep=True), base.model_copy(deep=True)
    nodes = {node.key: node for node in Orchestrator().nodes}

    run.compliance_state = {"US": "BLOCKED"}
    run.clear_escalations("compliance:")
    run.escalate("compliance:US", "blocked")
    run.audience_report.tomatometer = 1.0  # Phase V did not run, so this stays behind
    log_event(run, broadcast("agent_qc", "qc_result", {"verdict": "FAIL"}))
    latest.escalate("compliance:FR", "stale")
    latest.escalate("asset:AST_X", "someone else's")

    merged = merge.merge_run(latest, run, [nodes["phase4"]], len(base.event_log))

    assert merged.compliance_state == {"US": "BLOCKED"}
    assert merged.audience_report.tomatometer == latest.audience_report.tomatometer
    queue = [e.queue_item for e in merged.human_escalations]
    assert "compliance:US" in queue and "asset:AST_X" in queue
    assert not {"compliance:FR", "compliance:UAE"} & set(queue)
    assert merged.event_log[-1]["payload"] == {"verdict": "FAIL"}
    merged.compliance_state["US"] = "CLEARED"
    assert run.compliance_state["US"] == "BLOCKED", "the merge copies, it does not share"


def test_a_phase_run_reports_its_own_model_calls_and_leaves_the_rest(offline):
    """The plan's note on sample output has to follow a phase re-run, without
    forgetting what the phases that did not run reported."""
    base = _planned()
    latest, run = base.model_copy(deep=True), base.model_copy(deep=True)
    nodes = {node.key: node for node in Orchestrator().nodes}
    latest.model_use = {"phase1": {"live": 0, "sample": 6, "reason": "no_api_key"}, "phase4": {"live": 0, "sample": 1}}
    run.model_use = {"phase4": {"live": 3, "sample": 0}}

    merged = merge.merge_run(latest, run, [nodes["phase4"]], len(base.event_log))

    assert merged.model_use["phase4"] == {"live": 3, "sample": 0}
    assert merged.model_use["phase1"]["sample"] == 6, "Phase I did not run again"


def test_concurrent_edits_are_applied_one_after_another(state_dir):
    supabase_client.save_state(GlobalState(project_id=PROJECT))

    def add(n):
        supabase_client.update_state(PROJECT, lambda s: s.budget_state.expenses.append(
            {"category": "Crew", "description": f"#{n}", "amount": 1}))

    threads = [threading.Thread(target=add, args=(n,)) for n in range(24)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert supabase_client.load_state(PROJECT).budget_state.spent == 24


# ------------------------------------------------- a run outlives the process --


def _restart():
    """What a server restart leaves behind: the stored records, and a process
    that is running nothing."""
    jobs._ACTIVE.clear()


def test_the_last_run_is_still_there_after_a_restart(state_dir, offline, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    client = _client()
    started = client.post("/api/pipeline/run", json={"project_id": PROJECT}, headers=_auth(token)).json()

    _restart()

    status = client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()
    assert status["job_id"] == started["job_id"]
    assert status["status"] == "complete"
    assert status["summary"]["casting_status"] == "LOCKED"


def test_a_run_cut_short_by_a_restart_is_reported_as_failed(state_dir, offline, signed_in, make_production,
                                                            monkeypatch):
    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(GlobalState(project_id=PROJECT))
    # A run that gets as far as starting its first phase and is then killed.
    monkeypatch.setattr(jobs, "_spawn", lambda target, job, *rest: jobs._phase_status(job, "phase1", "running"))
    client = _client()
    started = client.post("/api/pipeline/run", json={"project_id": PROJECT}, headers=_auth(token)).json()
    assert started["status"] == "running"

    _restart()

    status = client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()
    assert status["job_id"] == started["job_id"], "the record survives; only the run was lost"
    assert status["status"] == "failed" and status["error"] == jobs.INTERRUPTED
    assert [p["status"] for p in status["phases"]] == ["failed"] + ["pending"] * 5
    assert client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()["status"] == "failed"
    assert client.post("/api/pipeline/run", json={"project_id": PROJECT},
                       headers=_auth(token)).status_code == 202, "the production is free to plan again"


def test_a_records_keys_all_have_a_column_to_land_in(state_dir, offline, signed_in, make_production):
    """PostgREST rejects a write naming a column the table lacks, so a key added
    to a run record without a matching column breaks every Supabase deploy."""
    import re

    from core import config
    from services import pipeline_store

    user, token = signed_in()
    make_production(user)
    _client().post("/api/pipeline/run", json={"project_id": PROJECT}, headers=_auth(token))
    record = pipeline_store.latest(PROJECT)

    sql = (config.BACKEND_DIR / "schema_state.sql").read_text(encoding="utf-8")
    body = re.search(r"create table if not exists cn_pipeline_runs \((.*?)\n\);", sql, re.S).group(1)
    columns = {line.strip().split()[0] for line in body.splitlines()
               if line.strip() and not line.strip().startswith("--")}

    assert set(record) <= columns, f"no column for {sorted(set(record) - columns)} in cn_pipeline_runs"


def test_a_store_that_cannot_be_written_does_not_stop_the_run(state_dir, offline, signed_in, make_production,
                                                              monkeypatch, capsys):
    """A database where schema_state.sql has not been run again has no
    cn_pipeline_runs table. That costs the history, not the plan."""
    from services import pipeline_store

    user, token = signed_in()
    make_production(user)
    monkeypatch.setattr(pipeline_store, "_complained", set())
    monkeypatch.setattr(pipeline_store, "save", lambda record: pipeline_store._shrug(
        "save", RuntimeError("relation cn_pipeline_runs does not exist")) or record)

    started = _client().post("/api/pipeline/run", json={"project_id": PROJECT}, headers=_auth(token))

    assert started.status_code == 202
    assert started.json()["job_id"], "the caller still gets a run to poll for"
    assert supabase_client.load_state(PROJECT).casting_status == "LOCKED", "the plan was still saved"
    assert "re-run backend/schema_state.sql" in capsys.readouterr().out
