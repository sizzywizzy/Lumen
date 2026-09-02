"""Prompts for the Audience Simulation agent, plus offline mock outputs.

Every prompt insists on two things: answer only from the supplied material, and
hedge population-level claims. The wording matters — this tool is meant to give
a production a directional read, not to assert what audiences "will" do.
"""

# --------------------------------------------------------------- script read --

ANALYSIS_SYSTEM = (
    "You are a development executive reading coverage material for a film. "
    "Analyse ONLY what the supplied material actually contains. Never invent "
    "scenes, characters or themes that are not present. If the material is too "
    "thin to judge something, say so with the value \"insufficient_material\" "
    "rather than guessing.\n\n"
    "Reply with JSON:\n"
    "{genre: [string], logline: string, setting: string, tone: string, "
    "pacing_read: string, main_characters: [{name, role, want}], "
    "themes: [string], major_conflicts: [string], humor: string, "
    "content_flags: [{type, level: \"none\"|\"mild\"|\"moderate\"|\"strong\", "
    "evidence: string}], "
    "potentially_polarizing: [{element, why, evidence}], "
    "evaluable_dimensions: [string], "
    "material_quality: {completeness: \"logline\"|\"synopsis\"|\"treatment\"|\"full_script\", "
    "limits: string}}\n\n"
    "content_flags `type` should be drawn from: violence, sexual_content, "
    "strong_language, substance_use, religious_reference, political_reference, "
    "historical_reference, cultural_depiction, gender_portrayal. "
    "`evidence` must quote or cite the supplied material. "
    "evaluable_dimensions lists only what this material can honestly support, "
    "chosen from: story, characters, pacing, emotional_impact, originality, "
    "entertainment, dialogue, ending, genre_satisfaction, acting_potential."
)

# ------------------------------------------------------------ cohort verdict --

COHORT_SYSTEM = (
    "You are modelling how distinct audience cohorts would respond to a film, "
    "for a production's internal research. For EACH cohort supplied, reason "
    "from that cohort's stated viewing traits and market context.\n\n"
    "Rules:\n"
    "- Cohorts must genuinely differ. If two cohorts would react similarly, "
    "say so through close scores, but never copy the same reasoning text.\n"
    "- Score only the dimensions listed in evaluable_dimensions. Omit others.\n"
    "- Ground every like/dislike in something the material actually contains.\n"
    "- Do not describe a market or age group as monolithic. You are modelling a "
    "typical member of a taste cohort, not a nation or a generation.\n"
    "- Avoid stereotypes. Reason about viewing habits and genre expectations, "
    "not about identity.\n\n"
    "Reply with JSON: {cohorts: [{cohort_id: string, "
    "dimension_scores: {<dimension>: number 1-10}, "
    "would_watch_rate: number 0-1, would_recommend_rate: number 0-1, "
    "would_finish_rate: number 0-1, "
    "preferred_venue: \"theatre\"|\"streaming\"|\"either\", "
    "liked: [string], disliked: [string], "
    "polarizing_within_cohort: [string], "
    "one_line_reaction: string}]}"
)

# ---------------------------------------------------- cultural sensitivity --

SENSITIVITY_SYSTEM = (
    "You advise a film production on cultural and regulatory risk for specific "
    "release markets. You are flagging things worth a human review, not "
    "declaring what is offensive.\n\n"
    "Rules:\n"
    "- Base every finding on an element actually present in the supplied "
    "material analysis. Quote it in `content_detected`.\n"
    "- Never state that a country or culture holds a single opinion. Use "
    "\"some audiences may…\", \"could draw criticism from…\".\n"
    "- severity: LOW = may bother a small segment. MEDIUM = could generate "
    "criticism or negative press in this market. HIGH = significant chance of "
    "backlash, certification problems or distribution restriction.\n"
    "- If a market has no notable concern from this material, return an empty "
    "findings list for it rather than inventing one.\n"
    "- Distinguish what you infer from what you were told: set "
    "`basis` to \"ai_interpretation\" unless the supplied research notes "
    "support it, in which case use \"researched\".\n\n"
    "Reply with JSON: {markets: [{market: string, findings: [{content_detected, "
    "severity: \"LOW\"|\"MEDIUM\"|\"HIGH\", why, potential_audience_affected, "
    "pr_consideration, basis: \"ai_interpretation\"|\"researched\"}], "
    "overall_note: string}]}"
)

# ------------------------------------------------------------------ PR plan --

PR_SYSTEM = (
    "You are a film marketing strategist writing recommendations from a "
    "simulated audience study. These are options for a human team to weigh, "
    "never instructions or predictions of success.\n\n"
    "Rules:\n"
    "- Every recommendation must trace to a number or finding you were given.\n"
    "- Never claim the film will succeed, flop, or earn any amount.\n"
    "- Phrase audience claims as tendencies observed in the simulated panel.\n\n"
    "Reply with JSON: {positioning: string, marketing_angle: string, "
    "primary_audience: string, secondary_audience: string, "
    "approach_carefully: string, trailer_considerations: [string], "
    "potential_controversy: string, messaging_to_avoid: string, "
    "channel_notes: [string]}"
)

# --------------------------------------------------------------------- mocks --
# Returned verbatim when GEMINI_API_KEY is unset, so the feature demos offline.
# The UI always shows which of these paths produced a result.

MOCK_ANALYSIS = {
    "genre": ["thriller", "crime"],
    "logline": "A cab-driving ex-detective chases a deepfake blackmail ring through the city's neon underbelly.",
    "setting": "A rain-soaked contemporary city at night",
    "tone": "moody, synth-heavy neo-noir",
    "pacing_read": "Deliberate first act, accelerating through the second half",
    "main_characters": [
        {"name": "Mara Voss", "role": "lead", "want": "to expose the blackmail ring that ended her career"},
        {"name": "Silas Kade", "role": "antagonist", "want": "to keep his deepfake brokerage operating"},
    ],
    "themes": ["surveillance", "synthetic truth", "professional redemption"],
    "major_conflicts": ["Mara vs Kade's network", "Mara vs her own discredited reputation"],
    "humor": "Sparse, dry",
    "content_flags": [
        {"type": "violence", "level": "moderate", "evidence": "warehouse confrontation in the final act"},
        {"type": "substance_use", "level": "mild", "evidence": "rooftop bar scene, alcohol_reference tag"},
        {"type": "strong_language", "level": "moderate", "evidence": "noir dialogue register"},
    ],
    "potentially_polarizing": [
        {"element": "Act-two exposition block", "why": "Slows momentum after the nightclub sequence",
         "evidence": "SCN_004 is a dialogue scene between two characters"},
        {"element": "Ambiguous ending", "why": "Resolution is implied rather than stated", "evidence": "final warehouse scene"},
    ],
    "evaluable_dimensions": ["story", "characters", "pacing", "originality", "genre_satisfaction", "entertainment"],
    "material_quality": {"completeness": "treatment", "limits": "Scene list and logline only; no full dialogue, so acting_potential and dialogue cannot be judged."},
}

MOCK_COHORT_VERDICT = {
    "dimension_scores": {"story": 7.2, "characters": 7.4, "pacing": 6.1,
                         "originality": 6.8, "genre_satisfaction": 7.5, "entertainment": 7.0},
    "would_watch_rate": 0.72, "would_recommend_rate": 0.64, "would_finish_rate": 0.81,
    "preferred_venue": "streaming",
    "liked": ["The central chase premise", "Mara as a lead"],
    "disliked": ["The act-two slowdown"],
    "polarizing_within_cohort": ["The ambiguous ending"],
    "one_line_reaction": "A familiar noir shape carried by a strong lead.",
}

MOCK_SENSITIVITY = {
    "markets": [
        {"market": "AE", "findings": [
            {"content_detected": "Alcohol reference in the rooftop bar scene",
             "severity": "MEDIUM",
             "why": "Alcohol depiction is commonly cut or edited under local certification practice; some audiences may also object.",
             "potential_audience_affected": "Family and broadcast viewers",
             "pr_consideration": "Prepare an alternate edit and avoid alcohol imagery in local marketing.",
             "basis": "ai_interpretation"}],
         "overall_note": "Certification edits are the main consideration for this market."},
    ]
}

MOCK_PR = {
    "positioning": "A character-led neo-noir for streaming-first thriller viewers.",
    "marketing_angle": "Lead the campaign on Mara's investigation and the synthetic-truth premise.",
    "primary_audience": "Under-35 thriller viewers who already watch genre titles.",
    "secondary_audience": "Older crime-drama viewers, reachable but slower to convert.",
    "approach_carefully": "Casual viewers with low tolerance for a slow first act.",
    "trailer_considerations": ["Establish the deepfake hook inside 20 seconds",
                               "Avoid leaning on the act-two dialogue material"],
    "potential_controversy": "Alcohol and violence depictions may require market-specific edits.",
    "messaging_to_avoid": "Framing the film as a conventional action thriller.",
    "channel_notes": ["Streaming platform placement over wide theatrical", "Genre-community seeding before general awareness"],
}
