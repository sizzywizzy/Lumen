"""The scheduler honours the cast's availability and pays for a venue day once.

The mock venue and actor calendars are weekly patterns from the first shoot
day (Sep 1, 2026 here): the lead is free on offsets 0, 1, 3 and 4 and the
antagonist on 2, 4, 5 and 6. The Neon Lounge, the cheaper nightclub, opens on
offsets 2 and 3, so a nightclub scene with the lead belongs on offset 3.
"""
from datetime import date

from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from domains.production.agents import phase3_schedule as p3
from services import mock_db

START = date(2026, 9, 1)


def _scene(scene_id, location_type, cast, hours=3.0, title=""):
    return {"scene_id": scene_id, "title": title or scene_id, "heading": "", "summary": "", "int_ext": "INT",
            "location_type": location_type, "characters_needed": cast, "estimated_time_hours": hours, "tags": []}


def _state():
    state = GlobalState(project_id="PROJ_T")
    state.role_requirements = {"ROLE_LEAD": {"name": "Mara Voss"}, "ROLE_ANTAG": {"name": "Silas Kade"}}
    return state


def _available(role, day):
    listed = mock_db.load("actor_availability").get(role)
    return listed is None or day in p3._weekly(listed, START, 90)


def test_a_counter_offer_prefers_a_day_the_cast_can_make():
    state = _state()
    p3._scheduler(state, [_scene("SCN_001", "nightclub", ["ROLE_LEAD"], title="First look")])
    entry = state.schedule.stripboard[0]
    assert (entry.date, entry.venue) == ("2026-09-04", "The Neon Lounge")
    assert [c["reason"] for c in state.schedule.conflicts] == ["venue_unavailable"]


def test_a_day_nobody_can_make_is_booked_but_put_in_front_of_a_person():
    state = _state()
    p3._scheduler(state, [_scene("SCN_003", "nightclub", ["ROLE_LEAD", "ROLE_ANTAG"], title="First look at Silas")])
    entry = state.schedule.stripboard[0]
    assert not _available("ROLE_LEAD", entry.date)
    conflict = state.schedule.conflicts[0]
    assert conflict["reason"] == "cast_unavailable"
    assert "Mara Voss is not listed as available" in conflict["resolution"]
    assert "First look at Silas" in conflict["resolution"]
    assert [e.queue_item for e in state.human_escalations] == ["schedule:cast"]


def test_the_demo_schedule_never_breaks_cast_availability_silently(offline):
    state = Orchestrator().run(GlobalState(project_id="PROJ_NEON_NIGHTS"), start="phase3", end="phase3")
    flagged = {c["scene_id"] for c in state.schedule.conflicts if c["reason"] == "cast_unavailable"}
    for entry in state.schedule.stripboard:
        for role in entry.characters_needed:
            if not _available(role, entry.date):
                assert entry.scene_id in flagged, f"{entry.scene_id} on {entry.date} needs {role}"


def test_a_venue_day_is_paid_once_however_many_scenes_share_it():
    state = _state()
    p3._scheduler(state, [_scene("SCN_001", "taxi_cab", [], 3.0), _scene("SCN_002", "taxi_cab", [], 3.0)])
    assert len({e.date for e in state.schedule.stripboard}) == 1
    assert state.budget_state.daily_burn == 900.0


def test_the_schedule_advisor_counts_a_venue_day_once_too():
    from domains.skills import agents

    state = _state()
    p3._scheduler(state, [_scene("SCN_001", "taxi_cab", [], 3.0), _scene("SCN_002", "taxi_cab", [], 3.0)])
    day = agents._scheduling_facts(state)["computed"]["day_load"][0]
    assert day["cost_usd"] == 900.0
    assert day["venues"] == ["Checker Cab Rig (process trailer)"]
