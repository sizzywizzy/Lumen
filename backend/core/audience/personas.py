"""Audience panel construction.

Builds a panel of N distinct personas from a *configurable weighted
distribution*, not by cycling a handful of seeds. Generation is seeded, so the
same (seed, size, distribution) always yields byte-identical personas — that is
what makes a simulation reproducible and auditable.

Design notes:
  - No sensitive personal attributes are modelled. There is deliberately no
    gender, ethnicity, religion or income field: none of them are needed to
    estimate a directional reaction to a film, and inferring them would invite
    exactly the stereotyping this module is meant to avoid. Personas vary on
    *taste and viewing behaviour*, plus the market they watch in.
  - Dimensions are sampled with light, explicit conditioning (a market implies
    a plausible language mix; heavy viewers skew more genre-familiar) so the
    panel reads as coherent people rather than random attribute soup.
"""
import hashlib
import random
from typing import Any, Optional

# --------------------------------------------------------------------------
# Default distribution. Every weight is overridable per simulation, so a team
# can model "our film is being positioned for India + the Gulf" rather than
# being stuck with an even worldwide split.
# --------------------------------------------------------------------------

MARKETS: dict[str, dict[str, Any]] = {
    "US": {"name": "United States", "languages": {"English": 0.82, "Spanish": 0.18}},
    "IN": {"name": "India", "languages": {"Hindi": 0.45, "English": 0.30, "Tamil": 0.13, "Telugu": 0.12}},
    "GB": {"name": "United Kingdom", "languages": {"English": 1.0}},
    "JP": {"name": "Japan", "languages": {"Japanese": 0.94, "English": 0.06}},
    "KR": {"name": "South Korea", "languages": {"Korean": 0.93, "English": 0.07}},
    "FR": {"name": "France", "languages": {"French": 0.9, "English": 0.1}},
    "DE": {"name": "Germany", "languages": {"German": 0.88, "English": 0.12}},
    "BR": {"name": "Brazil", "languages": {"Portuguese": 0.93, "English": 0.07}},
    "MX": {"name": "Mexico", "languages": {"Spanish": 0.93, "English": 0.07}},
    "NG": {"name": "Nigeria", "languages": {"English": 0.72, "Yoruba": 0.16, "Hausa": 0.12}},
    "AE": {"name": "United Arab Emirates", "languages": {"Arabic": 0.6, "English": 0.4}},
    "AU": {"name": "Australia", "languages": {"English": 1.0}},
}

DEFAULT_DISTRIBUTION: dict[str, dict[str, float]] = {
    # Deliberately uneven — this is a plausible international release mix, not
    # an equal split. Teams override it per simulation.
    "market": {
        "US": 0.24, "IN": 0.18, "GB": 0.08, "JP": 0.07, "KR": 0.06, "FR": 0.06,
        "DE": 0.06, "BR": 0.07, "MX": 0.06, "NG": 0.04, "AE": 0.04, "AU": 0.04,
    },
    "age_group": {"13-17": 0.06, "18-24": 0.22, "25-34": 0.27, "35-49": 0.24, "50-64": 0.15, "65+": 0.06},
    "locale_context": {"urban": 0.52, "suburban": 0.33, "rural": 0.15},
    "viewing_frequency": {"low": 0.28, "medium": 0.44, "high": 0.28},
    "taste_profile": {"mainstream": 0.55, "balanced": 0.30, "niche": 0.15},
    "story_preference": {"character-driven": 0.38, "plot-driven": 0.40, "balanced": 0.22},
    "pacing_tolerance": {"low": 0.34, "medium": 0.44, "high": 0.22},
    "experimental_openness": {"low": 0.40, "medium": 0.40, "high": 0.20},
    "viewing_context": {"theatre": 0.28, "streaming": 0.46, "both": 0.26},
    "subtitle_comfort": {"low": 0.30, "medium": 0.40, "high": 0.30},
}

GENRES = [
    "action", "thriller", "drama", "comedy", "horror", "sci-fi", "romance",
    "documentary", "animation", "crime", "fantasy", "mystery",
]

# Sensitivity = how much a viewer minds seeing a thing, not a moral judgement.
SENSITIVITY_DIMENSIONS = ["violence", "sexual_content", "strong_language", "religious_political"]
SENSITIVITY_LEVELS = {"tolerant": 0.42, "moderate": 0.40, "averse": 0.18}


def _weighted(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[max(0.0, float(weights[k])) for k in keys], k=1)[0]


def _merge_distribution(overrides: Optional[dict]) -> dict[str, dict[str, float]]:
    """Shallow-merge caller overrides over the defaults, per dimension."""
    merged = {dim: dict(weights) for dim, weights in DEFAULT_DISTRIBUTION.items()}
    for dim, weights in (overrides or {}).items():
        if dim in merged and isinstance(weights, dict) and weights:
            cleaned = {k: float(v) for k, v in weights.items() if float(v) > 0}
            if cleaned:
                merged[dim] = cleaned
    return merged


def distribution_fingerprint(distribution: dict) -> str:
    """Stable hash of the config, so a stored simulation records exactly which
    distribution produced its panel."""
    blob = repr(sorted((d, sorted(w.items())) for d, w in distribution.items()))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def normalise_genres(raw: Optional[list[str]]) -> list[str]:
    """Map free-text genre labels onto the taste vocabulary personas use.

    A model legitimately answers "neo-noir thriller" or "sci-fi horror"; without
    tokenising, none of those match GENRES and every persona ends up flagged as
    outside the genre, which silently flattens the genre-affinity segment.
    """
    found: list[str] = []
    for label in raw or []:
        text = str(label).lower()
        for genre in GENRES:
            if genre in text and genre not in found:
                found.append(genre)
        # a few common labels that do not contain their base word
        for alias, genre in (("noir", "crime"), ("suspense", "thriller"),
                             ("comedic", "comedy"), ("doc", "documentary"),
                             ("animated", "animation"), ("scifi", "sci-fi")):
            if alias in text and genre not in found:
                found.append(genre)
    return found


def build_panel(
    size: int = 500,
    seed: int = 20260902,
    distribution: Optional[dict] = None,
    film_genres: Optional[list[str]] = None,
) -> tuple[list[dict], dict]:
    """Return (personas, resolved_distribution).

    `film_genres` only nudges how many viewers happen to like this kind of film;
    it never forces agreement — a panel with no genre sceptics would be useless.
    """
    dist = _merge_distribution(distribution)
    rng = random.Random(seed)
    film_genres = normalise_genres(film_genres)

    personas: list[dict] = []
    for index in range(size):
        market = _weighted(rng, dist["market"])
        market_meta = MARKETS.get(market, {"name": market, "languages": {"English": 1.0}})
        age_group = _weighted(rng, dist["age_group"])
        viewing_frequency = _weighted(rng, dist["viewing_frequency"])
        taste = _weighted(rng, dist["taste_profile"])

        # Genre preferences: 2-3 picks. Viewers matching the film's genre are
        # over-represented but capped, so roughly a third to a half of the panel
        # is genre-adjacent and the rest are not.
        pool = list(GENRES)
        picks: list[str] = []
        if film_genres and rng.random() < 0.45:
            candidates = [g for g in film_genres if g in pool] or [rng.choice(pool)]
            picks.append(rng.choice(candidates))
        while len(picks) < rng.choice([2, 2, 3]):
            pick = rng.choice(pool)
            if pick not in picks:
                picks.append(pick)

        matches_film = bool(film_genres) and any(g in film_genres for g in picks)
        # Heavy viewers and genre fans know the genre's conventions better.
        familiarity_weights = {
            "low": 1.0 + (1.5 if viewing_frequency == "low" else 0),
            "medium": 2.0,
            "high": 1.0 + (1.6 if viewing_frequency == "high" else 0) + (1.4 if matches_film else 0),
        }
        genre_familiarity = _weighted(rng, familiarity_weights)

        # Niche tastes correlate with tolerance for slower, stranger films.
        openness_weights = dict(dist["experimental_openness"])
        if taste == "niche":
            openness_weights = {"low": 0.12, "medium": 0.33, "high": 0.55}
        elif taste == "mainstream":
            openness_weights = {"low": 0.55, "medium": 0.34, "high": 0.11}
        pacing_weights = dict(dist["pacing_tolerance"])
        if taste == "niche":
            pacing_weights = {"low": 0.16, "medium": 0.40, "high": 0.44}

        personas.append(
            {
                "persona_id": f"AUD_{index:04d}",
                "age_group": age_group,
                "market": market,
                "market_name": market_meta["name"],
                "locale_context": _weighted(rng, dist["locale_context"]),
                "language_preference": _weighted(rng, market_meta["languages"]),
                "subtitle_comfort": _weighted(rng, dist["subtitle_comfort"]),
                "genre_preferences": picks,
                "genre_familiarity": genre_familiarity,
                "matches_film_genre": matches_film,
                "viewing_frequency": viewing_frequency,
                "taste_profile": taste,
                "story_preference": _weighted(rng, dist["story_preference"]),
                "pacing_tolerance": _weighted(rng, pacing_weights),
                "experimental_openness": _weighted(rng, openness_weights),
                "prior_familiarity_with_similar": _weighted(
                    rng, {"none": 0.30, "some": 0.45, "high": 0.25} if not matches_film
                    else {"none": 0.12, "some": 0.40, "high": 0.48}
                ),
                "viewing_context": _weighted(rng, dist["viewing_context"]),
                "content_sensitivity": {
                    dim: _weighted(rng, SENSITIVITY_LEVELS) for dim in SENSITIVITY_DIMENSIONS
                },
            }
        )

    return personas, dist


# --------------------------------------------------------------------------
# Cohorts — how the panel is presented to the model.
# --------------------------------------------------------------------------

# A cohort is a group the model reasons about as one voice. The key is
# deliberately coarse — age band x market bloc x genre affinity — because those
# are the traits that most change a reaction. Everything else (pacing tolerance,
# taste profile, openness, prior familiarity) varies *within* a cohort and is
# applied afterwards as an explainable per-person adjustment, which is what
# keeps 500 individual responses from collapsing into N identical ones.
MAX_COHORTS = 28  # hard ceiling on LLM fan-out, independent of panel size
MIN_COHORT_SIZE = 4

AGE_BANDS = {
    "13-17": "under_25", "18-24": "under_25",
    "25-34": "25_34",
    "35-49": "35_49",
    "50-64": "50_plus", "65+": "50_plus",
}
AGE_BAND_NAMES = {
    "under_25": "Under 25", "25_34": "25-34", "35_49": "35-49", "50_plus": "50+",
}

# Grouping markets into blocs keeps the cohort count tractable while preserving
# the distinctions that actually change a reaction (censorship regime, dubbing
# and subtitle norms, local genre traditions).
MARKET_BLOCS = {
    "US": "north_america", "MX": "latin_america", "BR": "latin_america",
    "GB": "western_europe", "FR": "western_europe", "DE": "western_europe",
    "IN": "south_asia", "AE": "middle_east", "NG": "africa",
    "JP": "east_asia", "KR": "east_asia", "AU": "oceania",
}

BLOC_NAMES = {
    "north_america": "North America", "latin_america": "Latin America",
    "western_europe": "Western Europe", "south_asia": "South Asia",
    "middle_east": "Middle East", "africa": "Africa",
    "east_asia": "East Asia", "oceania": "Oceania",
}


def cohort_key(persona: dict) -> tuple:
    return (
        AGE_BANDS.get(persona["age_group"], "25_34"),
        MARKET_BLOCS.get(persona["market"], "other"),
        "genre_fan" if persona["matches_film_genre"] else "outside_genre",
    )


def _similarity(a: tuple, b: tuple) -> int:
    """How good a merge target `b` is for orphaned cohort `a` (higher = closer)."""
    return sum(3 * (a[i] == b[i]) for i in range(len(a))) + (2 if a[1] == b[1] else 0)


def build_cohorts(personas: list[dict]) -> list[dict]:
    """Group the panel into at most MAX_COHORTS cohorts and describe each one.

    Cohorts below MIN_COHORT_SIZE, and any beyond the cap, are folded into their
    most similar surviving cohort so that every persona is represented exactly
    once and the number of model calls stays bounded whatever distribution the
    production configures.
    """
    buckets: dict[tuple, list[dict]] = {}
    for persona in personas:
        buckets.setdefault(cohort_key(persona), []).append(persona)

    ranked = sorted(buckets.items(), key=lambda kv: -len(kv[1]))
    keep = [k for k, members in ranked if len(members) >= MIN_COHORT_SIZE][:MAX_COHORTS]
    if not keep:  # tiny panel — keep the largest bucket so nothing is dropped
        keep = [ranked[0][0]]

    merged: dict[tuple, list[dict]] = {k: list(buckets[k]) for k in keep}
    for key, members in ranked:
        if key in merged:
            continue
        target = max(keep, key=lambda k: _similarity(key, k))
        merged[target].extend(members)

    cohorts = []
    for index, key in enumerate(sorted(merged, key=lambda k: -len(merged[k]))):
        members = merged[key]
        band, bloc, affinity = key
        cohorts.append(
            {
                "cohort_id": f"COH_{index:02d}",
                "size": len(members),
                "age_band": band,
                "age_band_name": AGE_BAND_NAMES.get(band, band),
                "market_bloc": bloc,
                "market_bloc_name": BLOC_NAMES.get(bloc, bloc),
                "markets": sorted({m["market_name"] for m in members}),
                "genre_affinity": affinity,
                "common_genres": _top_genres(members),
                # the spread the per-persona step will vary across
                "taste_mix": _mix(members, "taste_profile"),
                "pacing_mix": _mix(members, "pacing_tolerance"),
                "member_ids": [m["persona_id"] for m in members],
            }
        )
    return cohorts


def _top_genres(members: list[dict], limit: int = 5) -> list[str]:
    counts: dict[str, int] = {}
    for m in members:
        for g in m["genre_preferences"]:
            counts[g] = counts.get(g, 0) + 1
    return [g for g, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def _mix(members: list[dict], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in members:
        counts[m[field]] = counts.get(m[field], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
