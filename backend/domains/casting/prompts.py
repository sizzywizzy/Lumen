"""LLM instructions for Phases I & II, plus their offline mock outputs.

Every prompt demands JSON (Gemini JSON mode) — never parse prose.
"""

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

# --- Mock outputs (used when GEMINI_API_KEY is unset) ------------------------

MOCK_AUDITION_REVIEWS = {
    "CAND_001": {"audition_score": 82, "qualitative_review": "Controlled intensity; owns the silences.", "standout_moment": "the cab monologue"},
    "CAND_004": {"audition_score": 78, "qualitative_review": "Magnetic menace, occasionally over-projects.", "standout_moment": "the rooftop toast"},
    "CAND_005": {"audition_score": 91, "qualitative_review": "Raw, precise, screen-native despite stage roots.", "standout_moment": "the harbor confession"},
}
MOCK_AUDITION_DEFAULT = {"audition_score": 65, "qualitative_review": "Serviceable read.", "standout_moment": "n/a"}
