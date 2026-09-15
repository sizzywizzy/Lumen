"""LLM instructions for Phases I & II, plus their offline mock outputs.

Every prompt demands JSON (Gemini JSON mode) — never parse prose.
"""
import hashlib

PROFILER_SYSTEM = (
    "You are the Corporate Profiler for a film studio. From the script context and "
    "executive brief, produce machine-readable casting mandates per role and the "
    "scoring weights. Respond with JSON: {role_requirements: {<role_id>: {...}}, "
    "scoring_weights: {W_A, W_H, W_PR, W_B}} where the weights sum to 1.0."
)

SCRIPT_READ_SYSTEM = (
    "You are a development executive reading a screenplay for casting. From the text, "
    "extract the production context and the speaking roles worth casting. Respond with JSON: "
    "{script_context: {title, genre, tone, logline, demographic_targets: [str]}, "
    "roles: [{role_id, name, type, description}]}. Use role_id ROLE_LEAD for the protagonist, "
    "ROLE_ANTAG for the main antagonist, and ROLE_SUPP_1, ROLE_SUPP_2... for up to six supporting "
    "roles; type is lead, antagonist or supporting. Describe a role by age range, temperament and "
    "function in the story, never by ethnicity or appearance. Use only what the text contains."
)

AUDITION_SYSTEM = (
    "You are an AI Co-Director reviewing an audition tape (720p clip + transcript) "
    "against the role requirements. Respond with JSON: "
    "{audition_score: 0-100, qualitative_review: str, standout_moment: str}."
)

PR_SHIELD_SYSTEM = (
    "You are a Brand Safety / PR analyst. Given a candidate's recent press, flag PR "
    "risk. Respond with JSON: {pr_score: 0-100, red_flag: bool, reason: str}. "
    "A red_flag means hard disqualification."
)

SCOUT_SYSTEM = (
    "You are an autonomous Google Cloud Talent Scout Agent (agent_casting_scout) for Lumen. "
    "Your mission is to crawl and scout working/emerging actors residing in the designated locality "
    "who match the production roles, respect the per-role budget cap, and fulfill the director's notes. "
    "Respond with JSON format: {\"candidates\": [{\"name\": str, \"role_id\": str, \"media_url\": str, "
    "\"metadata\": {\"locality\": str, \"agency\": str, \"quote_usd\": float, \"followers\": int, "
    "\"recent_press\": str, \"director_match\": str}}]}."
)

# --- Mock outputs (used when GEMINI_API_KEY is unset) ------------------------

# Keyed by the offline scout's candidate names, which stay stable when ids or
# pool order change. {character} is the role's character name.
MOCK_AUDITION_REVIEWS = {
    "Lucia Morales": (91, "Raw and precise; finds {character}'s weariness without losing the edge."),
    "Evelyn Vance": (84, "Controlled intensity that owns the silences as {character}."),
    "Caleb Sterling": (87, "A star turn as {character}, in complete command of the room."),
    "Darius Thorne": (80, "Magnetic menace as {character}, though a touch over-projected at times."),
    "Corinne Bailey": (76, "An easy, natural rhythm; {character} needs a little more steel."),
}


def mock_audition_review(name: str, character: str) -> dict:
    """Offline audition review: the curated line for known names, a steady seeded one otherwise."""
    who = character or "the role"
    if name in MOCK_AUDITION_REVIEWS:
        score, review = MOCK_AUDITION_REVIEWS[name]
    else:
        score = 60 + int(hashlib.md5(name.encode()).hexdigest(), 16) % 26
        review = "A grounded, believable read of {character}."
    return {"audition_score": score, "qualitative_review": review.format(character=who), "standout_moment": ""}
