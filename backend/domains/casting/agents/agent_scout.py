"""Talent Scout Agent (agent_casting_scout).

Finds actors for the production that match:
1. Target Locality (local hire actors within the director's designated city/market)
2. Production Budget Cap (strictly vetting quotes against the per-role cap)
3. Director Notes (character traits, skills, specific casting preferences)

Everything it uses is free: Tavily's free plan searches the web, Gemini's free
tier reads the results and suggests only people they name, and TMDb adds a
headshot and credits. With no model or no results, a fixed offline cast stands
in, labelled as such.
"""
import math
import re
import unicodedata
from typing import Any, Optional

from core import config, llm_output
from core.messaging.envelope import broadcast, log_event, make_envelope
from core.orchestrator.state import Candidate, GlobalState
from domains.casting import prompts
from services import gemini_client, tavily_client
from services.casting_kb import tmdb

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
            "media_url": f"https://reels.lumen.internal/{locality.lower().replace(' ', '_').replace(',', '')}/{slug}_reel.mp4",
            "metadata": {
                "locality": locality,
                "agency": raw["agency"],
                "quote_usd": raw["quote_usd"],
                "followers": raw["followers"],
                "recent_press": raw["recent_press"],
                "director_match": raw["director_match"],
                "scouted_via": "Offline demo cast",
            },
        })
    return out


OFFLINE_REASONS = {
    "no_api_key": "no GEMINI_API_KEY",
    "no_search_key": "no TAVILY_API_KEY; set it to search the web for free",
    "no_web_results": "the web search found nothing; Tavily's free searches for the month may be used up",
    "nobody_found": "the web results named nobody suitable",
    "model_failed": "Gemini did not answer; its free daily limit may be used up",
}
NEUTRAL_FOLLOWERS = 10_000  # stands in for an unknown following (a middling hype score)
RESULT_CHARS = 700
_MONEY = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([km])?(?![a-z])", re.IGNORECASE)
_SCALE = {"k": 1_000, "m": 1_000_000}


def _fee(value: Any) -> Optional[float]:
    """A fee the model wrote as 20000, "$20,000", "20k" or a range
    ("$15,000-25,000", "15-20k": the middle of it), or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) and value > 0 else None
    found = [(float(digits.replace(",", "")), unit.lower()) for digits, unit in _MONEY.findall(str(value or ""))]
    # "15-20k": the bare 15 takes the range's unit
    scale = next((_SCALE[unit] for _, unit in reversed(found) if unit), 1)
    amounts = [amount * (_SCALE[unit] if unit else scale if amount < 1000 else 1) for amount, unit in found]
    amounts = [amount for amount in amounts if amount > 0]
    return sum(amounts) / len(amounts) if amounts else None


def _plain(text: str) -> str:
    """Lower case, without accents, apostrophes or other punctuation, for
    matching names: "Ana Ruíz" is "ana ruiz", "M\u2019Cormack" is "mcormack"."""
    letters = unicodedata.normalize("NFKD", str(text or "").casefold())
    letters = "".join(ch for ch in letters if not unicodedata.combining(ch))
    letters = re.sub("['`\u2018\u2019]", "", letters)
    return " ".join(re.sub(r"[^\w\s]", " ", letters).split())


def _name_pattern(name: str) -> re.Pattern:
    """The whole name, not part of a longer one. Scripts written without spaces
    between words (Japanese, Chinese) can only be matched as a substring."""
    if name.isascii():
        return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
    return re.compile(re.escape(name))


def _web_results(queries: list[str]) -> list[dict[str, str]]:
    """Up to two Tavily searches, one credit each on the free plan."""
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for query in queries[:2]:
        found = tavily_client.search(query, max_results=5)
        if found.get("error"):
            print(f"[lumen] Tavily search failed: {found['error']}"[:300], flush=True)
        for item in found.get("results", []):
            url = str(item.get("url") or "")
            if url and url not in seen:
                seen.add(url)
                results.append(item)
    return results


def _results_block(results: list[dict[str, str]]) -> str:
    if not results:
        return ""
    lines = [f"[{i}] {r.get('title', '')} ({r.get('url', '')})\n{str(r.get('content') or '')[:RESULT_CHARS]}"
             for i, r in enumerate(results, 1)]
    return "WEB RESULTS:\n" + "\n\n".join(lines) + "\n\n"


def _rows(data: Any) -> list[dict]:
    rows = data.get("candidates") if isinstance(data, dict) else data
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _named_in_results(rows: list[dict], results: list[dict[str, str]]) -> list[dict]:
    """Keep the people the web results actually name, each with the url that
    names them. A name the model made up appears in no result and is dropped,
    and so is a reel link that is not one of the results."""
    texts = [_plain(f"{r.get('title', '')} {r.get('content', '')}") for r in results]
    urls = {r.get("url") for r in results if r.get("url")}
    kept = []
    for row in rows:
        # "Dee Walsh (actress)" is Dee Walsh; "Glover (Childish Gambino)" is only "Glover".
        written = " ".join(re.sub(r"\([^)]*\)", " ", str(row.get("name") or "")).split())
        name = _plain(written)
        # A first name alone ("Artemis") could be anyone, or a company.
        if not name or (name.isascii() and len(name.split()) < 2):
            continue
        whole_name = _name_pattern(name)
        hits = [i for i, text in enumerate(texts) if whole_name.search(text)]
        if not hits:
            continue
        cited = llm_output.number(row.get("source"), 0) - 1
        index = int(cited) if cited in hits else hits[0]
        row = {**row, "name": written, "source_url": results[index].get("url", "")}
        if row.get("media_url") not in urls:
            row.pop("media_url", None)
        kept.append(row)
    return kept


def _live_candidates(brief: str, results: list[dict[str, str]]) -> tuple[list[dict], dict[str, Any], str]:
    """(rows, trace, source): Gemini's picks from the Tavily results, with
    source "web_results", or no rows with source "offline" and trace["reason"]
    saying why.
    """
    if not config.has_gemini():
        return [], {"source": "mock", "reason": "no_api_key"}, "offline"
    if not results:
        reason = "no_web_results" if config.has_tavily() else "no_search_key"
        return [], {"source": "mock", "reason": reason}, "offline"
    data, trace = gemini_client.generate_json_traced(
        brief + _results_block(results) + "Suggest actors from these results only.",
        tier="flash", system=prompts.SCOUT_WEB_SYSTEM, mock={"candidates": []},
    )
    if trace.get("source") != "gemini":
        return [], {**trace, "reason": "model_failed"}, "offline"
    rows = _named_in_results(_rows(data), results)
    if not rows:
        return [], {**trace, "source": "mock", "reason": "nobody_found"}, "offline"
    return rows, trace, "web_results"


def _tmdb_enrich(meta: dict[str, Any], name: str) -> None:
    """A headshot, TMDb page and known-for credits when TMDb lists an actor by
    that name (free). Presented as a name match: TMDb cannot confirm it is the
    same person the web result meant."""
    try:
        profile = tmdb.profile_for(name)
    except Exception as exc:  # noqa: BLE001 — enrichment is a nicety; the candidate stands without it
        print(f"[lumen] TMDb lookup for {name!r} failed: {type(exc).__name__}", flush=True)
        return
    if not profile:
        meta["tmdb_match"] = "none"
        return
    meta.update({key: value for key, value in profile.items() if value})
    meta["tmdb_match"] = "name"


def scout_candidates(state: GlobalState) -> list[Candidate]:
    """Find actors near the filming locality, within the per-role budget cap,
    who suit the roles and the director's notes.

    Live suggestions come from Gemini reading web results fetched through
    Tavily's free plan. Only people those results name are kept, and TMDb
    (free) adds a headshot and credits where it lists them.
    With no model or no results, the offline demo cast stands in, labelled.
    """
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

    # 2. The searches: who works near the locality. The roles and the
    #    director's notes go to the model, not the search engine: genre words
    #    ("neo-noir") find articles about famous films and their stars.
    queries = [
        f"actors based in {locality} talent agency roster",
        f"{locality} based actors actresses local independent film",
    ]
    log_event(state, broadcast("agent_casting_scout", "crawl_locality_started", {
        "locality": locality,
        "queries": queries,
        "per_role_budget_cap_usd": role_cap,
        "director_notes": director_notes or "General role fit",
    }))

    # 3. Live suggestions, else the offline pool.
    results = _web_results(queries) if config.has_tavily() else []
    brief = (
        f"Production Target Locality: {locality}\n"
        f"Maximum Actor Quote Cap: ${role_cap:,.0f} USD per role (from total budget ${budget_cap:,.0f})\n"
        f"Director's Notes: {director_notes if director_notes else 'Open casting, authentic local hire'}\n"
        f"Roles to Cast:\n"
        + "\n".join(f"- {rid}: {info.get('name', rid)} ({info.get('description', '')})" for rid, info in roles.items())
        + "\n\n"
    )
    try:
        live_rows, trace, source = _live_candidates(brief, results)
    except Exception as exc:  # noqa: BLE001 — a failed live source still leaves the offline cast
        print(f"[lumen] live scouting failed: {type(exc).__name__}: {exc}"[:300], flush=True)
        live_rows, trace, source = [], {"source": "mock", "reason": "model_failed"}, "offline"
    is_live = source != "offline"
    raw_candidates = live_rows or _generate_fallback_candidates(locality, role_cap, director_notes, roles)
    if is_live:
        scouted_via_label = f"Gemini ({trace.get('model')}) reading web results from Tavily"
        ingest_source = "live_web_results"
    else:
        reason = trace.get("reason", "")
        scouted_via_label = f"Offline demo cast ({OFFLINE_REASONS.get(reason, reason or 'no live source')})"
        ingest_source = "offline_fallback"

    # 4. Candidates, checked field by field: a candidate for a role the script
    #    does not have would be locked by synthesis for a phantom part, so an
    #    unknown role id falls back to the round-robin pick, and quotes and
    #    follower counts must be numbers.
    role_ids = list(roles)
    agencies = _match_regional_agencies(locality)
    candidates: list[Candidate] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(raw_candidates):
        cid = llm_output.text(raw.get("id"), "", 40)
        if not cid or cid in seen_ids:
            cid = f"CAND_LOC_{idx+1:03d}"
        seen_ids.add(cid)
        name = llm_output.text(raw.get("name"), f"Local Talent #{idx+1}", 120)
        role_id = llm_output.text(raw.get("role_id")).upper()
        if role_id not in roles:
            role_id = role_ids[idx % len(role_ids)]
        meta = dict(llm_output.mapping(raw.get("metadata")))
        meta.setdefault("locality", locality)
        default_quote = round(role_cap * 0.75, -2)
        if is_live:
            meta["quote_usd"] = _fee(meta.get("quote_usd")) or default_quote
        else:
            meta["quote_usd"] = llm_output.number(meta.get("quote_usd"), default_quote, 0)
        if is_live:
            # Nobody publishes their fee or following; the model's numbers are estimates.
            meta["quote_is_estimate"] = True
            if llm_output.number(meta.get("followers"), -1) < 0:
                meta["followers"] = NEUTRAL_FOLLOWERS
                meta["followers_estimated"] = True
            for key in ("agency", "recent_press", "director_match"):
                meta[key] = llm_output.text(meta.get(key), "", 400)
            if raw.get("source_url"):
                meta["source_url"] = raw["source_url"]
        else:
            meta.setdefault("agency", agencies[idx % len(agencies)])
        meta["followers"] = int(llm_output.number(meta.get("followers"), 50000 + (idx * 25000), 0))
        meta.setdefault("recent_press", f"Active working actor in {locality}.")
        meta.setdefault("director_match", f"Scouted for '{locality}' match with director notes.")
        meta["scouted_via"] = scouted_via_label
        meta["is_live_scouted"] = is_live
        if is_live and config.has_tmdb():
            _tmdb_enrich(meta, name)

        media_url = llm_output.text(raw.get("media_url"), f"https://reels.lumen.internal/{cid.lower()}_audition.mp4", 500)

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
            "agency": meta.get("agency") or ("not stated" if is_live else "Direct Roster"),
            "quote_usd": meta.get("quote_usd", 0),
            "budget_cap_usd": role_cap,
            "director_match": meta.get("director_match", ""),
            "source": ingest_source,
            "source_url": meta.get("source_url"),
            "tmdb_match": meta.get("tmdb_match"),
        }))

    log_event(state, broadcast("agent_casting_scout", "crawl_locality_completed", {
        "locality": locality,
        "scouted_count": len(candidates),
        "per_role_budget_cap_usd": role_cap,
        "source": ingest_source,
        "web_results": len(results),
        "summary": f"Scouted {len(candidates)} actors for {locality}: {scouted_via_label}.",
    }))

    return candidates
