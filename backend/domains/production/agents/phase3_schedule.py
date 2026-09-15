"""Phase III — Script -> Schedule.

agent_breakdown -> agent_scheduler_shoot <-> agent_location (negotiation, max 2 iterations)
-> stripboard + burn-rate budget.
"""
import re
from datetime import date, timedelta
from core import config
from core import scenes as scene_names
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState, StripboardEntry
from core.shoot_window import read_window
from domains.production import prompts
from services import gemini_client, mock_db

MAX_SCENES = 30  # the venue database is small; more scenes than this cannot be placed sensibly
SCENE_ID_RE = re.compile(r"^SCN_[A-Z0-9_]{1,12}$")
MAX_SCENES_PER_DAY = 2
OPEN_ENDED_DAYS = 90  # how far ahead to look when no wrap date was given
OVERFLOW_DAYS = 28  # how far past the planned wrap a scene may still be placed
# The mock venue and actor calendars list one sample week starting on this day.
# They are read as a weekly pattern from the production's real first shoot day;
# drop this mapping once a real venue database with real dates is connected.
MOCK_WEEK_START = date(2026, 9, 1)


def _weekly(listed: list[str], start: date, days: int) -> list[str]:
    offsets = {(date.fromisoformat(d) - MOCK_WEEK_START).days % 7 for d in listed}
    return [(start + timedelta(days=i)).isoformat() for i in range(days) if i % 7 in offsets]


def _say(day: str) -> str:
    """'2027-03-05' -> 'Fri, Mar 5' (no %-d: Windows strftime lacks it)."""
    d = date.fromisoformat(day)
    return f"{d:%a}, {d:%b} {d.day}"


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
            "heading": str(scene.get("heading") or ""),
            "title": str(scene.get("title") or ""),
            "summary": str(scene.get("summary") or ""),
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
    # Copies with plain names filled in (mock_db.load is cached, so never mutate it).
    scenes = [scene_names.describe(s) for s in scenes]
    # Later phases (compliance tags, audience heatmap) read the same breakdown.
    state.script_context["scenes"] = scenes
    log_event(state, broadcast("agent_breakdown", "breakdown_ready", {
        "scene_count": len(scenes), "scenes": [s["scene_id"] for s in scenes], "source": source,
        "titles": scene_names.titles(scenes),
    }))
    return scenes


def _location_offer(state: GlobalState, request: dict, start: date, days: int) -> dict:
    """agent_location: answer a check_venue_availability request with the best venue/date.

    Cheapest venue first, but a day the cast can make beats a cheaper venue
    that only has days they cannot: the request lists the days that are
    already full and the days the scene's cast is unavailable. Only when no
    venue has a cast-free day does the offer fall back to any open day, and
    it says so, so the scheduler can put the booking in front of a person.
    """
    payload = request["payload"]
    constraints = state.schedule.director_constraints
    venues = [v for v in mock_db.load("venues") if v["location_type"] == payload["location_type"]]
    if constraints.get("country"):
        venues = [v for v in venues if v.get("country", "USA") == constraints["country"]]
    excluded = set(constraints.get("excluded_states", []))
    venues = [v for v in venues if v.get("state", "") not in excluded]
    venues = sorted(venues, key=lambda v: v["cost_per_day"])
    preferred_date = payload["preferred_date"]
    full = set(payload.get("full_dates", []))
    cast_unavailable = set(payload.get("cast_unavailable", []))
    with_room = [(v, [d for d in _weekly(v["available_dates"], start, days) if d not in full]) for v in venues]
    for cast_free_only in (True, False):
        for venue, open_days in with_room:
            days_ok = [d for d in open_days if d not in cast_unavailable] if cast_free_only else open_days
            if not days_ok:
                continue
            chosen = preferred_date if preferred_date in days_ok else days_ok[0]
            offer = {"venue_name": venue["venue_name"], "date": chosen,
                     "cost_per_day": venue["cost_per_day"],
                     "preferred_date_available": chosen == preferred_date,
                     "cast_available": chosen not in cast_unavailable}
            log_event(state, make_reply(request, "agent_location", "venue_offer", offer))
            return offer
    offer = {"venue_name": None, "date": None, "cost_per_day": 0,
             "preferred_date_available": False, "cast_available": False}
    log_event(state, make_reply(request, "agent_location", "venue_offer", offer))
    return offer


def _scheduler(state: GlobalState, scenes: list[dict]) -> None:
    """Stripboard builder. Negotiates each scene's venue with agent_location;
    if the preferred date is unavailable it accepts the counter-offer (1 retry max)."""
    stripboard: list[StripboardEntry] = []
    total_cost = 0.0
    settings = state.schedule.shoot_settings
    constraints = state.schedule.director_constraints
    start, wrap = read_window(settings)
    max_hours = float(settings.get("max_hours_per_day", 10))
    days = (wrap - start).days + 1 + OVERFLOW_DAYS if wrap else OPEN_ENDED_DAYS
    shoot_dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    availability = mock_db.load("actor_availability")
    actor_dates = {role: set(_weekly(values, start, days)) for role, values in availability.items()}
    hours_by_date: dict[str, float] = {}
    scenes_by_date: dict[str, int] = {}

    def has_room(day: str, hours: float) -> bool:
        return scenes_by_date.get(day, 0) < MAX_SCENES_PER_DAY and hours_by_date.get(day, 0) + hours <= max_hours

    def role_name(role_id: str) -> str:
        role = (state.role_requirements or {}).get(role_id)
        return (role.get("name") or role_id) if isinstance(role, dict) else role_id

    all_days = set(shoot_dates)
    late_scenes, cast_conflicts = 0, []
    venue_days: set[tuple[str, str]] = set()
    for scene in scenes:
        hours = scene["estimated_time_hours"]
        title = scene.get("title") or scene["scene_id"]
        cast = scene["characters_needed"]
        cast_free = {day for day in shoot_dates if all(day in actor_dates.get(role, all_days) for role in cast)}
        # The day asked for: the first with room that the whole cast can make,
        # else the first with room at all (the cast conflict is then reported).
        wanted = next((day for day in shoot_dates if day in cast_free and has_room(day, hours)),
                      next((day for day in shoot_dates if has_room(day, hours)), shoot_dates[-1]))
        full = [day for day in shoot_dates if not has_room(day, hours)]
        cast_unavailable = [day for day in shoot_dates if day not in cast_free]
        preferred, offer = wanted, None
        for _ in range(config.MAX_NEGOTIATION_ITERATIONS):  # never unbounded
            request = log_event(state, make_envelope(
                "agent_scheduler_shoot", "agent_location", "check_venue_availability",
                {"scene_id": scene["scene_id"], "location_type": scene["location_type"],
                 "preferred_date": preferred, "full_dates": full, "cast_unavailable": cast_unavailable,
                 "window": {"start": start.isoformat(), "wrap": wrap.isoformat() if wrap else None},
                 "director_constraints": constraints},
            ))
            offer = _location_offer(state, request, start, days)
            if offer["venue_name"] is None or offer["preferred_date_available"]:
                break
            preferred = offer["date"]  # counter-offer: accept the venue's day and ask again

        if offer and offer["venue_name"]:
            placed = offer["date"]
            days_late = max((date.fromisoformat(placed) - wrap).days, 0) if wrap else 0
            missing = [role_name(role) for role in cast if placed not in actor_dates.get(role, all_days)]
            sentences = []
            if placed != wanted:
                sentence = f'{offer["venue_name"]} isn\'t free on {_say(wanted)}, so "{title}" moves to {_say(placed)}.'
                if days_late:
                    sentence += f" That is {days_late} {'day' if days_late == 1 else 'days'} after the planned wrap on {_say(wrap.isoformat())}."
                sentences.append(sentence)
            elif days_late:
                sentences.append(f"No day before the planned wrap ({_say(wrap.isoformat())}) had the cast and a venue free, "
                                 f'so "{title}" is set for {_say(placed)} ({days_late} {"day" if days_late == 1 else "days"} late).')
            if missing:
                # No venue had a day this cast can make, so the scene is booked
                # anyway and the clash is put in front of a person.
                who = " and ".join(missing) if len(missing) < 3 else ", ".join(missing[:-1]) + " and " + missing[-1]
                sentences.append(f'{who} {"is" if len(missing) == 1 else "are"} not listed as available for "{title}" '
                                 f"on {_say(placed)}; confirm the booking or move the scene.")
                cast_conflicts.append(title)
            if sentences:
                state.schedule.conflicts.append({
                    "scene_id": scene["scene_id"], "title": title, "wanted": wanted, "moved_to": placed,
                    "venue": offer["venue_name"],
                    "reason": "cast_unavailable" if missing else ("past_wrap" if days_late else "venue_unavailable"),
                    "days_past_wrap": days_late, "resolution": " ".join(sentences),
                })
                late_scenes += 1 if days_late else 0
            stripboard.append(StripboardEntry(
                scene_id=scene["scene_id"], heading=scene.get("heading", ""), title=scene.get("title", ""),
                summary=scene.get("summary", ""), date=placed, venue=offer["venue_name"],
                location_type=scene["location_type"], int_ext=scene["int_ext"],
                estimated_time_hours=hours,
                characters_needed=scene["characters_needed"], cost_per_day=offer["cost_per_day"],
            ))
            hours_by_date[placed] = hours_by_date.get(placed, 0) + hours
            scenes_by_date[placed] = scenes_by_date.get(placed, 0) + 1
            if (offer["venue_name"], placed) not in venue_days:  # a venue day is paid once, however many scenes share it
                venue_days.add((offer["venue_name"], placed))
                total_cost += offer["cost_per_day"]
        else:
            state.escalate(f"venue:{scene['scene_id']}", f'No venue could be found for "{title}".')

    state.schedule.stripboard = sorted(stripboard, key=lambda e: e.date)
    if late_scenes and wrap:
        last = state.schedule.stripboard[-1].date
        state.escalate("schedule:past_wrap",
                       f"{late_scenes} {'scene runs' if late_scenes == 1 else 'scenes run'} past the planned wrap on "
                       f"{_say(wrap.isoformat())}; the last shoot day is {_say(last)}.")
    if cast_conflicts:
        listed = ", ".join(f'"{t}"' for t in cast_conflicts)
        state.escalate("schedule:cast",
                       f"{len(cast_conflicts)} {'scene is' if len(cast_conflicts) == 1 else 'scenes are'} booked on a day "
                       f"{'its' if len(cast_conflicts) == 1 else 'their'} cast is not listed as available: {listed}. "
                       "Confirm the bookings or move the scenes.")
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
        "conflicts_resolved": len(state.schedule.conflicts), "cast_conflicts": len(cast_conflicts),
        "venue_days": len(venue_days),
        "first_day": state.schedule.stripboard[0].date if stripboard else None,
        "last_day": state.schedule.stripboard[-1].date if stripboard else None,
        "wrap_date": wrap.isoformat() if wrap else None,
        "stripboard": [e.model_dump() for e in state.schedule.stripboard],
    }))


def run_phase3_schedule(state: GlobalState) -> GlobalState:
    # Phase III owns the stripboard, its conflicts, the burn alert and the
    # venue and wrap escalations: a re-run replaces them rather than stacking.
    state.schedule.conflicts = []
    state.budget_state.alerts = []
    state.clear_escalations("venue:", "schedule:")
    scenes = _breakdown(state)
    _scheduler(state, scenes)
    return state
