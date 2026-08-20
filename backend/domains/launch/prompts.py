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
    "Write short representative reviews of this film in the voices of named outlets. "
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

# --- Mock outputs ------------------------------------------------------------

MOCK_RECUT_DIAGNOSIS = {
    "root_cause": "EXPOSITION_OVERLOAD",
    "action": "TRIM_AND_INTERCUT",
    "predicted_lift": {"segment_score": "+29", "tomatometer": "+6"},
}

MOCK_CRITIC_REVIEWS = {
    "reviews": [
        {"outlet": "The Circuit", "quote": "A rain-slicked stunner — Lin is a revelation.", "score": "4/5"},
        {"outlet": "FrameRate Weekly", "quote": "Act two idles, but the finale detonates.", "score": "7/10"},
        {"outlet": "Neon Pulse", "quote": "The synth-noir we didn't know we needed.", "score": "B+"},
    ]
}

# Draft 1 deliberately contains a finale spoiler so agent_pr_risk blocks it (demo beat).
MOCK_MEME_DRAFTS = [
    {"caption": "When Silas turns out to be the deepfake all along 💀", "image_prompt": "warehouse finale still, neon rim light", "alt_text": "finale twist meme"},
    {"caption": "POV: your cab driver has seen some things 🌧️", "image_prompt": "Mara in the cab, rain bokeh", "alt_text": "moody cab meme"},
]

SPOILER_TERMS = ("turns out", "all along", "twist", "dies", "killer is")
