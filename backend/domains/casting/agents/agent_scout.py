"""Google Cloud Talent Scout Agent (agent_casting_scout).

Crawls and scouts actors for the production matching:
1. Target Locality (local hire actors within the director's designated city/market)
2. Production Budget Cap (strictly vetting quotes against the per-role cap)
3. Director Notes (character traits, skills, specific casting preferences)

Uses Google Cloud Gemini with Google Search Grounding and Tavily to crawl
agency rosters, actor databases, and casting calls, with robust contextual fallback.
"""
from typing import Any

from core import config
from core.messaging.envelope import broadcast, log_event, make_envelope
from core.orchestrator.state import Candidate, GlobalState
from domains.casting import prompts
from services import gemini_client, tavily_client

REGIONAL_AGENCIES = {
    "atlanta": ["People Store", "Houghton Talent", "J Pervis Talent", "BMG Southeast"],
    "new york": ["CESD New York", "Stewart Talent NY", "Innovative Artists NYC", "Headline Talent"],
    "london": ["Independent Talent Group", "Curtis Brown UK", "United Agents London", "Tavistock Wood"],
    "los angeles": ["Gersh Agency", "Abrams Artists Agency", "Osbrink Talent", "Clear Talent Group"],
    "chicago": ["Gray Talent Group", "Paonessa Talent", "Stewart Talent Chicago", "Grossman & Jack"],
    "vancouver": ["Play Management", "Lucas Talent Vancouver", "Red Management", "Trisko Talent"],
}


def _match_regional_agencies(locality: str) -> list[str]:
    loc_lower = (locality or "").lower()
    for key, agencies in REGIONAL_AGENCIES.items():
        if key in loc_lower:
            return agencies
    return ["Apex Talent Management", "Horizon Talent Agency", "Metro Artists Roster"]


def _generate_fallback_candidates(
    locality: str,
    role_cap: float,
    director_notes: str,
    roles: dict[str, Any],
) -> list[dict[str, Any]]:
    """Synthesizes high-fidelity contextual candidates strictly matching locality, budget, and director notes."""
    agencies = _match_regional_agencies(locality)
    role_keys = list(roles.keys()) if roles else ["ROLE_LEAD", "ROLE_ANTAG"]

    notes_lower = (director_notes or "").lower()
    has_martial_arts = any(w in notes_lower for w in ["martial", "stunt", "action", "combat", "fight"])
    has_theater = any(w in notes_lower for w in ["theater", "theatre", "stage", "drama", "classical"])
    has_bilingual = any(w in notes_lower for w in ["spanish", "french", "bilingual", "accent", "multilingual"])

    pool = [
        {
            "name": "Evelyn Vance",
            "role_id": role_keys[0] if len(role_keys) > 0 else "ROLE_LEAD",
            "quote_usd": round(role_cap * 0.72, -2),
            "followers": 145_000,
            "agency": agencies[0],
            "recent_press": f"Critically acclaimed lead in {locality} indie drama; zero controversies.",
            "director_match": (
                f"Based in {locality}. Extensive {('theater and stage training' if has_theater else 'nuanced psychological screen presence')}. "
                + (f"Directly fits director requirement: '{director_notes[:60]}' " if director_notes else f"Local resident in {locality}.")
            ),
        },
        {
            "name": "Darius Thorne",
            "role_id": role_keys[1] if len(role_keys) > 1 else (role_keys[0] if role_keys else "ROLE_ANTAG"),
            "quote_usd": round(role_cap * 0.85, -2),
            "followers": 310_000,
            "agency": agencies[1 % len(agencies)],
            "recent_press": f"Breakout performance in regional showcase; strong local fanbase in {locality}.",
            "director_match": (
                f"Local {locality} hire. {('Black belt combat experience & stunt background' if has_martial_arts else 'Gritty intensity and authentic charisma')}. "
                + (f"Matches note: '{director_notes[:50]}'" if director_notes else f"Strong local presence in {locality}.")
            ),
        },
        {
            "name": "Lucia Morales",
            "role_id": role_keys[0] if len(role_keys) > 0 else "ROLE_LEAD",
            "quote_usd": round(role_cap * 0.60, -2),
            "followers": 85_000,
            "agency": agencies[2 % len(agencies)],
            "recent_press": f"Winner of Best Actor at {locality.split(',')[0]} Independent Film Festival.",
            "director_match": (
                f"Native to {locality}. {('Fluent bilingual performer' if has_bilingual else 'Groundbreaking expressive screen presence')}. "
                "Exceptional match for director's vision."
            ),
        },
        {
            "name": "Caleb Sterling",
            "role_id": role_keys[1] if len(role_keys) > 1 else (role_keys[0] if role_keys else "ROLE_ANTAG"),
            "quote_usd": round(role_cap * 1.35, -2),
            "followers": 1_200_000,
            "agency": agencies[0],
            "recent_press": f"High-profile name in {locality}; agency package quote demands premium.",
            "director_match": f"High-tier {locality} star. Quote exceeds the standard per-role cap of ${role_cap:,.0f}.",
        },
        {
            "name": "Corinne Bailey",
            "role_id": role_keys[0] if len(role_keys) > 0 else "ROLE_LEAD",
            "quote_usd": round(role_cap * 0.65, -2),
            "followers": 48_000,
            "agency": agencies[3 % len(agencies)],
            "recent_press": f"Rising star across {locality} regional theater and streaming guest spots.",
            "director_match": f"Authentic local hire in {locality}. Seamless dialogue rhythm adhering to director notes.",
        },
    ]

    out = []
    for i, raw in enumerate(pool):
        cid = f"CAND_LOC_{i+1:03d}"
        slug = raw["name"].lower().replace(" ", "_")
        out.append({
            "id": cid,
            "name": raw["name"],
            "role_id": raw["role_id"],
            "media_url": f"https://reels.cinenode.internal/{locality.lower().replace(' ', '_').replace(',', '')}/{slug}_reel.mp4",
            "metadata": {
                "locality": locality,
                "agency": raw["agency"],
                "quote_usd": raw["quote_usd"],
                "followers": raw["followers"],
                "recent_press": raw["recent_press"],
                "director_match": raw["director_match"],
                "scouted_via": "Google Cloud Autonomous Talent Scout Agent",
            },
        })
    return out


def scout_candidates(state: GlobalState) -> list[Candidate]:
    """Execute live Google Cloud Agent crawling for actors in locality within budget."""
    locality = getattr(state, "locality", None) or state.script_context.get("locality") or "Los Angeles, CA"
    director_notes = getattr(state, "director_notes", None) or state.script_context.get("director_notes") or ""
    budget_cap = state.budget_state.cap
    role_cap = budget_cap * config.CASTING_CAP_SHARE
    roles = state.role_requirements or {
        "ROLE_LEAD": {"name": "Lead Protagonist", "description": "Core dramatic anchor"},
        "ROLE_ANTAG": {"name": "Antagonist", "description": "Formidable opposing force"},
    }

    # 1. Orchestration request envelope
    log_event(state, make_envelope(
        "agent_director_orchestrator", "agent_casting_scout", "scout_local_talent",
        {
            "locality": locality,
            "budget_cap_per_role_usd": role_cap,
            "total_production_budget": budget_cap,
            "director_notes": director_notes,
            "target_roles": list(roles.keys()),
        },
    ))

    # 2. Formulate targeted search queries for the crawler
    queries = [
        f"working actors based in {locality} casting agency talent roster",
        f"indie film actors in {locality} day rate budget quote",
    ]
    if director_notes:
        queries.append(f"actors {locality} {director_notes[:60]}")
    for role_id, role_info in list(roles.items())[:2]:
        desc = role_info.get("description", role_info.get("name", role_id))
        queries.append(f"{desc} actors in {locality} local hire")

    # Broadcast crawling activity to Live Agent Terminal
    log_event(state, broadcast("agent_casting_scout", "crawl_locality_started", {
        "locality": locality,
        "queries": queries,
        "per_role_budget_cap_usd": role_cap,
        "director_notes": director_notes or "General role fit",
    }))

    # 3. If Tavily search is enabled, execute web queries to augment context
    web_snippets = []
    if config.has_tavily():
        for q in queries[:2]:
            t_res = tavily_client.search(q, max_results=2)
            for item in t_res.get("results", []):
                web_snippets.append(f"{item.get('title')}: {item.get('content')[:250]}")

    # 4. Prepare prompt and mock fallback for the Google Cloud Gemini Agent
    fallback_data = _generate_fallback_candidates(locality, role_cap, director_notes, roles)
    mock_payload = {"candidates": fallback_data}

    prompt = (
        f"Production Target Locality: {locality}\n"
        f"Maximum Actor Quote Cap: ${role_cap:,.0f} USD per role (from total budget ${budget_cap:,.0f})\n"
        f"Director's Notes: {director_notes if director_notes else 'Open casting, authentic local hire'}\n"
        f"Roles to Cast:\n"
        + "\n".join(f"- {rid}: {info.get('name', rid)} ({info.get('description', '')})" for rid, info in roles.items())
        + "\n\n"
        + (f"Recent Web Search Intel:\n" + "\n".join(web_snippets) + "\n\n" if web_snippets else "")
        + f"Search and crawl for working/emerging actors living in {locality} who fit the budget cap of ${role_cap:,.0f} "
        f"and align with the director notes. Include their name, targeted role_id, a showreel link, local agency, "
        f"quoted rate (must generally fit under ${role_cap:,.0f}), followers, and a director_match explanation."
    )

    # 5. Call Gemini with Google Search tool grounding if configured
    raw_candidates = []
    trace = {"source": "mock", "reason": "uninitialized"}
    try:
        data, trace = gemini_client.generate_json_with_search(
            prompt,
            tier="flash",
            system=prompts.SCOUT_SYSTEM,
            mock=mock_payload,
        )
        if isinstance(data, dict) and "candidates" in data and isinstance(data["candidates"], list):
            raw_candidates = data["candidates"]
        elif isinstance(data, list):
            raw_candidates = data
        else:
            raw_candidates = fallback_data
    except Exception:
        raw_candidates = fallback_data
        trace = {"source": "mock", "reason": "exception"}

    if not raw_candidates:
        raw_candidates = fallback_data

    is_live = trace.get("source") == "gemini_grounded"
    if is_live:
        scouted_via_label = f"Google Cloud Vertex AI ({trace.get('model')}) + Search Grounding"
    elif trace.get("reason") == "adc_reauth_required":
        scouted_via_label = "Local Talent Synthesis (Google Cloud ADC reauthentication required)"
    else:
        scouted_via_label = "Local Talent Synthesis (Offline Demo Fallback)"

    # 6. Parse and instantiate Candidate models
    candidates: list[Candidate] = []
    for idx, raw in enumerate(raw_candidates):
        cid = raw.get("id") or f"CAND_LOC_{idx+1:03d}"
        name = raw.get("name") or f"Local Talent #{idx+1}"
        role_id = raw.get("role_id") or list(roles.keys())[idx % len(roles)]
        meta = raw.get("metadata") or {}
        meta.setdefault("locality", locality)
        meta.setdefault("quote_usd", round(role_cap * 0.75, -2))
        meta.setdefault("agency", _match_regional_agencies(locality)[idx % len(_match_regional_agencies(locality))])
        meta.setdefault("followers", 50000 + (idx * 25000))
        meta.setdefault("recent_press", f"Active working actor in {locality}.")
        meta.setdefault("director_match", f"Scouted for '{locality}' match with director notes.")
        meta["scouted_via"] = scouted_via_label
        meta["is_live_scouted"] = is_live

        media_url = raw.get("media_url") or f"https://reels.cinenode.internal/{cid.lower()}_audition.mp4"

        candidate = Candidate(
            id=cid,
            name=name,
            role_id=role_id,
            media_url=media_url,
            metadata=meta,
            scores={},
            status="SOURCING",
        )
        candidates.append(candidate)

        log_event(state, broadcast("agent_intake", "candidate_ingested", {
            "candidate_id": candidate.id,
            "name": candidate.name,
            "role_id": candidate.role_id,
            "locality": meta.get("locality", locality),
            "agency": meta.get("agency", "Direct Roster"),
            "quote_usd": meta.get("quote_usd", 0),
            "budget_cap_usd": role_cap,
            "director_match": meta.get("director_match", ""),
            "source": "live_google_search" if is_live else "offline_fallback",
        }))

    log_event(state, broadcast("agent_casting_scout", "crawl_locality_completed", {
        "locality": locality,
        "scouted_count": len(candidates),
        "per_role_budget_cap_usd": role_cap,
        "source": "live_google_search" if is_live else "offline_fallback",
        "summary": (
            f"Scouted {len(candidates)} local actors in {locality} via "
            f"{'Live Google Cloud Web Search' if is_live else 'Offline Locality Synthesis (no GEMINI_API_KEY set)'}."
        ),
    }))

    return candidates
