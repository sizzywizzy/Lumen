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

POSTER_SYSTEM = (
    "You art-direct the theatrical one-sheet for a film from its screenplay, in the style "
    "you are given. Write a tagline of at most ten words that gives nothing away: no twists, "
    "deaths, secret identities or the ending, and never name an actor. Pick three to five "
    "colours that suit the film and the style. Respond with JSON: {tagline, "
    "palette: [three to five colours as #rrggbb]}."
)

# Every poster draws one of these at random, never the style of the poster it
# replaces. `direction` art-directs the concept (tagline and palette); `sketch`
# is the motif the art is drawn in. Movements and eras only, never a living
# artist's name.
POSTER_STYLES = (
    {"key": "classic", "label": "Classic one-sheet", "sketch": "ridges",
     "direction": "a lush hand-painted illustration in oils and gouache, dramatic rim light and a "
                  "sweeping low-angle composition, like a classic 1980s adventure one-sheet"},
    {"key": "minimal", "label": "Minimal symbol", "sketch": "disc",
     "direction": "one bold symbolic object on a flat field of colour, Swiss modernist restraint, "
                  "generous negative space and crisp graphic edges"},
    {"key": "neon-noir", "label": "Neon noir", "sketch": "skyline",
     "direction": "a cinematic night photograph: rain-slick streets, neon reflections, anamorphic "
                  "lens flare, deep shadows and shallow depth of field"},
    {"key": "cut-paper", "label": "Cut-paper silhouettes", "sketch": "ridges",
     "direction": "mid-century cut-paper collage in two or three flat inks, jagged silhouettes and "
                  "bold graphic shapes with a faint paper texture"},
    {"key": "risograph", "label": "Risograph duotone", "sketch": "halftone",
     "direction": "a two-ink risograph print with coarse halftone grain, slight misregistration and "
                  "one punchy fluorescent ink over a deep base colour"},
    {"key": "double-exposure", "label": "Double exposure", "sketch": "skyline",
     "direction": "a photographic double exposure: the silhouette of the main character filled with "
                  "the world of the film, on a clean ground"},
    {"key": "surreal", "label": "Surrealist metaphor", "sketch": "disc",
     "direction": "a surreal painted visual metaphor in the spirit of mid-century Polish film posters: "
                  "one uncanny central image, muted colour and expressive brushwork"},
    {"key": "art-deco", "label": "Art deco", "sketch": "rays",
     "direction": "art deco geometry: a symmetrical sunburst, stepped forms, fine metallic linework "
                  "and elegant symmetry"},
    {"key": "woodblock", "label": "Woodblock print", "sketch": "ridges",
     "direction": "a woodblock print in the ukiyo-e tradition: bold outlines, flat colour, patterned "
                  "waves and clouds, and washi paper grain"},
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

# The offline poster concept by genre: a tagline (spoiler-free, since it passes
# the same PR gate) and a palette ordered sky, horizon, light, ink. The first
# match wins, in the same order as the Overview's painted title card.
POSTER_GENRES = (
    (("noir", "thriller", "crime", "mystery", "heist"), "Every city keeps a secret.",
     ["#0e1633", "#4a1f6e", "#ff4fa3", "#07060d"]),
    (("horror", "slasher", "ghost", "haunt"), "Some doors should stay shut.",
     ["#160707", "#5a0f12", "#ff5a3c", "#050202"]),
    (("sci-fi", "science fiction", "space", "cyber", "future", "robot"), "Tomorrow is already watching.",
     ["#07131f", "#0f4a5c", "#7ff2ff", "#02070b"]),
    (("romance", "rom-com", "love"), "Some nights only happen once.",
     ["#2a0f1e", "#7a2a4c", "#ffb3c7", "#0d0409"]),
    (("comedy", "satire", "family", "animated"), "What could possibly go wrong?",
     ["#2a1c05", "#8a5a12", "#ffe680", "#0c0802"]),
    (("western", "frontier"), "The frontier forgives no one.",
     ["#2a1a0c", "#7a4a1c", "#ffc76b", "#0c0703"]),
    (("fantasy", "myth", "magic", "epic"), "Every legend starts with a choice.",
     ["#101a2e", "#3a2c6e", "#c7a8ff", "#05070d"]),
    (("action", "war", "adventure", "spy"), "No way back.",
     ["#1a0f0a", "#6a2f14", "#ff9a3c", "#070403"]),
)
POSTER_DEFAULT = ("Everything changes after tonight.", ["#1c140c", "#5c4632", "#f6a121", "#0a0806"])
