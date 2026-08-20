"""Phase III — Script -> Schedule.

agent_breakdown -> agent_scheduler_shoot <-> agent_location (negotiation, max 2 iterations)
-> stripboard + burn-rate budget.
"""
from core import config
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState, StripboardEntry
from services import mock_db


def _breakdown(state: GlobalState) -> list[dict]:
    scenes = mock_db.load("script")["scenes"]
    log_event(state, broadcast("agent_breakdown", "breakdown_ready", {
        "scene_count": len(scenes), "scenes": [s["scene_id"] for s in scenes],
    }))
    return scenes


def _location_offer(state: GlobalState, request: dict) -> dict:
    """agent_location: answer a check_venue_availability request with the best venue/date."""
    payload = request["payload"]
    venues = [v for v in mock_db.load("venues") if v["location_type"] == payload["location_type"]]
    if state.mode == "indie":
        venues = sorted(venues, key=lambda v: (not v["indie_friendly"], v["cost_per_day"]))
    else:
        venues = sorted(venues, key=lambda v: v["cost_per_day"])
    preferred_date = payload["preferred_date"]
    for venue in venues:
        date = preferred_date if preferred_date in venue["available_dates"] else venue["available_dates"][0]
        offer = {"venue_name": venue["venue_name"], "date": date,
                 "cost_per_day": venue["cost_per_day"],
                 "preferred_date_available": date == preferred_date}
        log_event(state, make_reply(request, "agent_location", "venue_offer", offer))
        return offer
    offer = {"venue_name": None, "date": None, "cost_per_day": 0, "preferred_date_available": False}
    log_event(state, make_reply(request, "agent_location", "venue_offer", offer))
    return offer


def _scheduler(state: GlobalState, scenes: list[dict]) -> None:
    """Stripboard builder. Negotiates each scene's venue with agent_location;
    if the preferred date is unavailable it accepts the counter-offer (1 retry max)."""
    stripboard: list[StripboardEntry] = []
    total_cost = 0.0
    shoot_dates = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
                   "2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08"]

    for i, scene in enumerate(scenes):
        preferred = shoot_dates[min(i, len(shoot_dates) - 1)]
        offer = None
        for _ in range(config.MAX_NEGOTIATION_ITERATIONS):  # never unbounded
            request = log_event(state, make_envelope(
                "agent_scheduler_shoot", "agent_location", "check_venue_availability",
                {"scene_id": scene["scene_id"], "location_type": scene["location_type"],
                 "preferred_date": preferred},
            ))
            offer = _location_offer(state, request)
            if offer["venue_name"] is None:
                break
            if offer["preferred_date_available"]:
                break
            # Counter-offer: reflow the stripboard to the venue's date and accept.
            state.schedule.conflicts.append({
                "scene_id": scene["scene_id"], "wanted": preferred, "moved_to": offer["date"],
                "resolution": f"accepted counter-offer from agent_location ({offer['venue_name']})",
            })
            preferred = offer["date"]

        if offer and offer["venue_name"]:
            stripboard.append(StripboardEntry(scene_id=scene["scene_id"], date=offer["date"], venue=offer["venue_name"]))
            total_cost += offer["cost_per_day"]
        else:
            state.escalate(f"venue:{scene['scene_id']}", f"No venue found for {scene['location_type']}")

    state.schedule.stripboard = sorted(stripboard, key=lambda e: e.date)
    shoot_days = max(len({e.date for e in stripboard}), 1)
    state.budget_state.daily_burn = round(total_cost / shoot_days, 2)
    burn_cap = 30_000 if state.mode == "enterprise" else 4_000
    if state.budget_state.daily_burn > burn_cap:
        state.budget_state.alerts.append(f"Daily burn {state.budget_state.daily_burn} exceeds cap {burn_cap}")
    log_event(state, broadcast("agent_scheduler_shoot", "schedule_updated", {
        "shoot_days": shoot_days, "daily_burn": state.budget_state.daily_burn,
        "conflicts_resolved": len(state.schedule.conflicts),
        "stripboard": [e.model_dump() for e in state.schedule.stripboard],
    }))


def run_phase3_schedule(state: GlobalState) -> GlobalState:
    scenes = _breakdown(state)
    _scheduler(state, scenes)
    return state
