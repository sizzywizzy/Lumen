"""LLM instructions for Phases V & VI, plus their offline mock outputs."""

VIEWER_SYSTEM = (
    "You are roleplaying a specific film viewer persona watching a screening packet. "
    "Stay in character. Respond with JSON: {scene_scores: {<scene_id>: 0-10}, "
    "overall_score: 0-10, sentiment, review_text, would_recommend: bool, drop_off_scene}."
)

RECUT_SYSTEM = (
    "You are a veteran editor diagnosing an engagement anomaly. Respond with JSON: "
    "{root_cause, action, predicted_lift: {segment_score, tomatometer}}."
)

CRITIC_SYSTEM = (
    "Write three short representative reviews of this film in the voices of named outlets, one "
    "sentence under 25 words each. Mention only characters and actors listed in CAST and never "
    "invent a name; refer to scenes by the titles given. "
    "Respond with JSON: {reviews: [{outlet, quote, score}]}."
)

STRATEGIST_SYSTEM = (
    "You are a film marketing strategist. From the audience report, produce a campaign "
    "plan. Respond with JSON: {segments: [{demographic, platform, tone, asset_types}]}."
)

VISUAL_SYSTEM = (
    "You art-direct a one-image social asset for this film. Respond with JSON: "
    "{caption, image_prompt, alt_text}."
)

COPYWRITER_SYSTEM = (
    "You are a film marketing copywriter. From the campaign plan and the audience "
    "report, write platform-native social copy for each campaign segment and one "
    "short press release. Never reveal plot twists, deaths or the ending. Respond "
    "with JSON: {posts: [{platform, demographic, caption, hashtags: [str]}], "
    "press_release: {headline, body}}."
)

# --- Mock outputs ------------------------------------------------------------

MOCK_RECUT_DIAGNOSIS = {
    "root_cause": "EXPOSITION_OVERLOAD",
    "action": "TRIM_AND_INTERCUT",
    "predicted_lift": {"segment_score": "+29", "tomatometer": "+6"},
}

def mock_critic_reviews(cast: list[dict], weakest_title: str) -> dict:
    """Offline critic reviews that only name the real characters and cast."""
    lead = next((c for c in cast if c.get("type") == "lead"), cast[0] if cast else None)
    villain = next((c for c in cast if c.get("type") == "antagonist"), None)
    if lead and lead.get("actor"):
        lead_line = f"A rain-slicked stunner. {lead['actor']} is a revelation as {lead['character']}."
    elif lead:
        lead_line = f"A rain-slicked stunner, carried by {lead['character']}."
    else:
        lead_line = "A rain-slicked stunner."
    return {
        "reviews": [
            {"outlet": "The Circuit", "quote": lead_line, "score": "4 out of 5"},
            {"outlet": "FrameRate Weekly",
             "quote": f'It idles during "{weakest_title}", but the finale detonates.' if weakest_title
             else "It idles in the middle, but the finale detonates.",
             "score": "7 out of 10"},
            {"outlet": "Neon Pulse",
             "quote": f"{villain['character']} is all charm and menace, the villain of the year." if villain
             else "The synth-noir we didn't know we needed.",
             "score": "B+"},
        ]
    }

# Draft 1 deliberately contains a finale spoiler so agent_pr_risk blocks it (demo beat).
MOCK_MEME_DRAFTS = [
    {"caption": "When Silas turns out to be the deepfake all along 💀", "image_prompt": "warehouse finale still, neon rim light", "alt_text": "finale twist meme"},
    {"caption": "POV: your cab driver has seen some things 🌧️", "image_prompt": "Mara in the cab, rain bokeh", "alt_text": "moody cab meme"},
]

# Spoiler-free on purpose: the copywriter's drafts go through the same PR gate
# as every other asset, so the offline output must pass it.
MOCK_COPY = {
    "posts": [
        {"platform": "tiktok", "demographic": "18-24",
         "caption": "POV: your cab driver has seen some things 🌧️", "hashtags": ["#NeonNights", "#neonoir"]},
        {"platform": "instagram", "demographic": "25-34",
         "caption": "The city remembers everything. Neon Nights, this fall.", "hashtags": ["#NeonNights"]},
    ],
    "press_release": {
        "headline": "Neon Nights brings synth-noir back to the big screen",
        "body": "An ex-detective turned cab driver hunts a deepfake blackmail ring through a "
                "rain-soaked city in Neon Nights, a neo-noir thriller shot on location this autumn.",
    },
}

SPOILER_TERMS = ("turns out", "all along", "twist", "dies", "killer is")
