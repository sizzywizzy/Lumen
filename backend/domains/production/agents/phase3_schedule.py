"""Phase III — Script -> Schedule.

agent_breakdown -> agent_scheduler_shoot <-> agent_location (negotiation, max 2 iterations)
-> stripboard + burn-rate budget.
"""
import re
from datetime import date, timedelta
from core import config
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState, StripboardEntry
from domains.production import prompts
from services import gemini_client, mock_db

MAX_SCENES = 30  # the venue database is small; more scenes than this cannot be placed sensibly
SCENE_ID_RE = re.compile(r"^SCN_[A-Z0-9_]{1,12}$")


def _valid_scenes(scenes, venue_types: set[str], role_ids: set[str]) -> list[dict]:
    """Keep only scenes a venue can host and the cast can be called for."""
    out, seen = [], set()
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, dict):
            continue
        location = str(scene.get("location_type", "")).strip().lower()
        if location not in venue_types:
            continue
        scene_id = str(scene.get("scene_id") or "").strip().upper()
        if not SCENE_ID_RE.match(scene_id) or scene_id in seen:
            scene_id = f"SCN_{len(out) + 1:03d}"
            while scene_id in seen:
                scene_id += "_B"
        try:
            hours = float(scene.get("estimated_time_hours", 3))
        except (TypeError, ValueError):
            hours = 3.0
        characters = [str(c).strip().upper() for c in (scene.get("characters_needed") or [])
                      if str(c).strip().upper() in role_ids]
        tags = [re.sub(r"[^a-z0-9]+", "_", str(t).strip().lower()).strip("_")
                for t in (scene.get("tags") or []) if str(t).strip()][:8]
        out.append({
            "scene_id": scene_id,
            "int_ext": "EXT" if str(scene.get("int_ext", "INT")).strip().upper().startswith("EXT") else "INT",
            "location_type": location,
            "characters_needed": characters,
            "estimated_time_hours": round(max(1.0, min(10.0, hours)), 1),
            "tags": [t for t in tags if t],
        })
        seen.add(scene_id)
        if len(out) >= MAX_SCENES:
            break
    return out


def _breakdown(state: GlobalState) -> list[dict]:
    """agent_breakdown: scenes from the screenplay dropped at intake, constrained
    to venue types the location agent can actually offer. Demo scenes otherwise."""
    demo = mock_db.load("script")["scenes"]
    scenes, source = demo, "demo"
    raw = ((state.script_context or {}).get("raw_text") or "").strip()
    if raw:
        venue_types = sorted({v["location_type"] for v in mock_db.load("venues")})
        role_ids = list(state.role_requirements) or [r["role_id"] for r in mock_db.load("script")["roles"]]
        limit = config.SCRIPT_ANALYSIS_MAX_CHARS
        read = gemini_client.generate_json(
            f"AVAILABLE VENUE TYPES: {venue_types}\nROLE IDS: {role_ids}\nMAX SCENES: {MAX_SCENES}\n\n"
            f"SCREENPLAY (first {min(len(raw), limit):,} characters):\n{raw[:limit]}",
            tier="pro", system=prompts.BREAKDOWN_SYSTEM, mock={"scenes": demo, "source": "demo"},
        )
        if isinstance(read, dict) and read.get("source") != "demo":
            extracted = _valid_scenes(read.get("scenes"), set(venue_types), set(role_ids))
            if extracted:
                scenes, source = extracted, "script"
    # Later phases (compliance tags, audience heatmap) read the same breakdown.
    state.script_context["scenes"] = scenes
    log_event(state, broadcast("agent_breakdown", "breakdown_ready", {
        "scene_count": len(scenes), "scenes": [s["scene_id"] for s in scenes], "source": source,
    }))
    return scenes


def _location_offer(state: GlobalState, request: dict) -> dict:
    """agent_location: answer a check_venue_availability request with the best venue/date."""
    payload = request["payload"]
    constraints = state.schedule.director_constraints
    venues = [v for v in mock_db.load("venues") if v["location_type"] == payload["location_type"]]
    if constraints.get("country"):
        venues = [v for v in venues if v.get("country", "USA") == constraints["country"]]
    excluded = set(constraints.get("excluded_states", []))
    venues = [v for v in venues if v.get("state", "") not in excluded]
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
    settings = state.schedule.shoot_settings
    constraints = state.schedule.director_constraints
    start = date.fromisoformat(settings.get("start_date", "2026-09-01"))
    max_hours = float(settings.get("max_hours_per_day", 10))
    shoot_dates = [(start + timedelta(days=i)).isoformat() for i in range(90)]
    availability = mock_db.load("actor_availability")
    actor_dates = {role: set(values) for role, values in availability.items()}
    hours_by_date: dict[str, float] = {}

    for i, scene in enumerate(scenes):
        preferred = next((day for day in shoot_dates if hours_by_date.get(day, 0) + scene["estimated_time_hours"] <= max_hours and sum(1 for entry in stripboard if entry.date == day) < 2 and all(day in actor_dates.get(role, set(shoot_dates)) for role in scene["characters_needed"])), shoot_dates[-1])
        offer = None
        for _ in range(config.MAX_NEGOTIATION_ITERATIONS):  # never unbounded
            request = log_event(state, make_envelope(
                "agent_scheduler_shoot", "agent_location", "check_venue_availability",
                {"scene_id": scene["scene_id"], "location_type": scene["location_type"],
                 "preferred_date": preferred, "director_constraints": constraints},
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
            stripboard.append(StripboardEntry(
                scene_id=scene["scene_id"], date=offer["date"], venue=offer["venue_name"],
                location_type=scene["location_type"], int_ext=scene["int_ext"],
                estimated_time_hours=scene["estimated_time_hours"],
                characters_needed=scene["characters_needed"], cost_per_day=offer["cost_per_day"],
            ))
            hours_by_date[offer["date"]] = hours_by_date.get(offer["date"], 0) + scene["estimated_time_hours"]
            total_cost += offer["cost_per_day"]
        else:
            state.escalate(f"venue:{scene['scene_id']}", f"No venue found for {scene['location_type']}")

    state.schedule.stripboard = sorted(stripboard, key=lambda e: e.date)
    shoot_days = max(len({e.date for e in stripboard}), 1)
    state.budget_state.daily_burn = round(total_cost / shoot_days, 2)
    # Venues may spend a fixed share of the total budget, spread over the shoot days.
    burn_cap = round(state.budget_state.cap * config.LOCATIONS_SHARE / shoot_days, 2)
    if state.budget_state.daily_burn > burn_cap:
        state.budget_state.alerts.append(
            f"Daily burn ${state.budget_state.daily_burn:,.0f} exceeds the ${burn_cap:,.0f}/day location allowance"
        )
    log_event(state, broadcast("agent_scheduler_shoot", "schedule_updated", {
        "shoot_days": shoot_days, "daily_burn": state.budget_state.daily_burn,
        "conflicts_resolved": len(state.schedule.conflicts),
        "stripboard": [e.model_dump() for e in state.schedule.stripboard],
    }))


def run_phase3_schedule(state: GlobalState) -> GlobalState:
    scenes = _breakdown(state)
    _scheduler(state, scenes)
    return state
