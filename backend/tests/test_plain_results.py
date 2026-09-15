"""The results a production team reads: scene titles, a schedule that honours the
shooting dates, stored audience reviews, and casting reasons in plain words.

Everything runs offline on the mock fallbacks.
"""
import re

import pytest
from pydantic import ValidationError

from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState


def _run(**settings) -> GlobalState:
    state = GlobalState(project_id="PROJ_NEON_NIGHTS")
    state.schedule.shoot_settings.update(settings)
    return Orchestrator().run(state)


def test_scenes_carry_titles_not_ids(offline):
    state = _run()
    board = state.schedule.stripboard
    assert board and all(entry.title and entry.heading for entry in board)
    assert not any(entry.title.upper().startswith("SCN") for entry in board)
    assert {e.scene_id: e.title for e in board}["SCN_004"] == "The rooftop toast"


def test_schedule_starts_on_the_first_shoot_day_and_never_overbooks(offline):
    state = _run(start_date="2027-03-01", end_date="2027-03-31")
    dates = [entry.date for entry in state.schedule.stripboard]
    assert dates[0] == "2027-03-01"
    assert all("2027-03-01" <= d <= "2027-03-31" for d in dates)
    for day in set(dates):
        on_day = [e for e in state.schedule.stripboard if e.date == day]
        assert len(on_day) <= 2
        assert sum(e.estimated_time_hours for e in on_day) <= 10


def test_old_states_without_dates_still_start_on_the_default_day(offline):
    assert _run().schedule.stripboard[0].date == "2026-09-01"


def test_schedule_changes_are_sentences_without_agent_ids(offline):
    conflicts = _run().schedule.conflicts
    assert conflicts
    for conflict in conflicts:
        assert "agent_" not in conflict["resolution"]
        assert conflict["title"] in conflict["resolution"]


def test_a_short_window_flags_scenes_that_run_past_wrap(offline):
    state = _run(start_date="2027-03-01", end_date="2027-03-02")
    late = [c for c in state.schedule.conflicts if c["reason"] == "past_wrap"]
    assert late and all("planned wrap" in c["resolution"] for c in late)
    assert any(e.queue_item == "schedule:past_wrap" for e in state.human_escalations)


def test_audience_report_stores_reviews_that_name_the_real_cast(offline):
    report = _run().audience_report
    assert report.viewer_count == 200
    assert report.verdict in {"fresh", "rotten"}
    assert report.weakest_scene_title == "The rooftop toast"
    assert set(report.scene_titles) == set(report.heatmap)
    assert {r.kind for r in report.reviews} == {"critic", "viewer"}
    assert 3 <= len(report.reviews) <= 5
    quotes = " ".join(r.quote for r in report.reviews)
    assert not re.search(r"\bLin\b", quotes)
    assert "Mara Voss" in quotes or "Silas Kade" in quotes


def test_rerunning_the_screening_does_not_duplicate_reviews(offline):
    state = _run()
    count = len(state.audience_report.reviews)
    state = Orchestrator().run(state, start="phase5", end="phase5")
    assert len(state.audience_report.reviews) == count


def test_casting_reasons_read_as_sentences(offline):
    state = _run()
    ruled_out = [c for c in state.candidates if c.status == "DISQUALIFIED"]
    assert ruled_out
    assert ruled_out[0].disqualify_reason.startswith("Asking fee of $33,800 is above the $25,000 limit")
    assert ruled_out[0].metadata["disqualify_code"] == "over_budget"
    auditions = {c.scores.get("audition") for c in state.candidates if c.status != "DISQUALIFIED"}
    assert len(auditions) > 1  # mock auditions differ, so the ranking means something


def test_intake_window_is_validated():
    import main

    with pytest.raises(ValidationError):
        main.InitRequest(project_id="PROJ_X", start_date="2027-03-10", end_date="2027-03-01")
    with pytest.raises(ValidationError):
        main.InitRequest(project_id="PROJ_X", start_date="03/01/2027")
    assert main.InitRequest(project_id="PROJ_X", start_date="").start_date is None


def test_a_run_after_reload_keeps_the_intake_inputs(offline, make_user, make_production):
    import main
    from services import supabase_client

    user, _ = make_user()
    project_id = make_production(user)
    main.init_pipeline(main.InitRequest(
        project_id=project_id, budget_usd=400000, locality="Atlanta, GA", director_notes="Night shoots only",
        start_date="2027-03-01", end_date="2027-03-31",
    ), user=user)
    # What a page reload sends: nothing but the production.
    main.run_pipeline(main.InitRequest(project_id=project_id), user=user)

    state = supabase_client.load_state(project_id)
    assert state.budget_state.cap == 400000
    assert state.locality == "Atlanta, GA"
    assert state.director_notes == "Night shoots only"
    assert state.schedule.shoot_settings["end_date"] == "2027-03-31"
    assert state.schedule.stripboard[0].date == "2027-03-01"


def test_legacy_saved_state_loads_with_defaults():
    legacy = {
        "project_id": "PROJ_OLD",
        "schedule": {"stripboard": [{"scene_id": "SCN_001", "date": "2026-09-01", "venue": "Pier 9 Warehouse"}]},
        "audience_report": {"tomatometer": 80, "audience_score": 70, "heatmap": {}, "weakest_scene_id": ""},
    }
    state = GlobalState.model_validate(legacy)
    assert state.schedule.stripboard[0].title == ""
    assert state.audience_report.reviews == []
    assert state.audience_report.verdict == ""
