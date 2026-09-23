"""The evaluation sample: real films released after the model's training cutoff.

WHY THE SAMPLE IS A QUERY, NOT A LIST
A hand-picked list of films is unfalsifiable — the picker chooses, knowingly or
not, films the system happens to do well on, and nobody can tell from the
committed file. So the sample is defined by a TMDb query (released in a window,
at least `votes_floor` ratings, original language English, feature length) and
whatever the query returns is the sample. Changing the query changes a
recorded, reviewable line in the snapshot.

WHY POST-CUTOFF
Ask a model about a film released before it was trained and it can recall the
real score instead of predicting one. The whole evaluation would then measure
memory. `--released-after` sets the boundary and the snapshot records it; pick a
date you are confident is past the cutoff of whichever model will answer —
which is a property of the provider, so moving the window is part of switching
one (see `leakage` in run.py, which checks the assumption rather than trusting it).
`probe_leakage` checks the assumption instead of trusting it.

GROUND TRUTH, AND ITS LIMITS
TMDb's `vote_average` x 10 is the actual: a public audience rating on the same
0-100 scale as the simulator's `audience_score`. It is not the Rotten Tomatoes
audience score (different population, different prompt) and there is no free
critic-score API, so `tomatometer` is evaluated on ranking only. The votes
floor exists because `vote_average` over 11 ratings is noise; at a few hundred
it is stable to well under a point. All of this is in the report, because an
evaluation that hides its ground truth's weaknesses is advertising.
"""
import json
import time
from pathlib import Path
from typing import Any, Optional

from services.casting_kb import tmdb

SNAPSHOT = Path(__file__).parent / "films.json"

# A rating needs this many votes before it is stable enough to grade against.
DEFAULT_VOTES_FLOOR = 200
# Below this, an "overview" is a marketing tagline with nothing to simulate.
MIN_OVERVIEW_CHARS = 180
# Feature length. Shorts and TV specials answer a different question.
MIN_RUNTIME_MIN = 70
# Genres whose audience ratings are not comparable to a narrative feature's.
EXCLUDED_GENRES = {"Documentary"}


def _tmdb(path: str, **params: Any) -> dict[str, Any]:
    """A TMDb GET. Reuses the casting client so the alternate-host retry (some
    networks cannot reach every server behind api.themoviedb.org) is not
    reimplemented here."""
    return tmdb._request(path, **params)


def discover(
    *,
    released_after: str,
    released_before: str,
    votes_floor: int = DEFAULT_VOTES_FLOOR,
    want: int = 40,
    max_pages: int = 8,
) -> list[dict[str, Any]]:
    """Candidate films, most-rated first. Ordering by vote count rather than by
    rating matters: sorting by rating would hand back a sample of only
    well-reviewed films, and a predictor cannot be shown to rank anything if
    everything in the sample scored the same."""
    found: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        payload = _tmdb(
            "/discover/movie",
            sort_by="vote_count.desc",
            include_adult="false",
            include_video="false",
            with_original_language="en",
            page=page,
            **{
                "primary_release_date.gte": released_after,
                "primary_release_date.lte": released_before,
                "vote_count.gte": votes_floor,
            },
        )
        results = payload.get("results") or []
        found.extend(results)
        if not results or page >= int(payload.get("total_pages") or 1) or len(found) >= want * 3:
            break
    return found


def _detail(tmdb_id: int) -> dict[str, Any]:
    """Runtime and genre names, which /discover does not return."""
    return _tmdb(f"/movie/{tmdb_id}")


def _film(detail: dict[str, Any]) -> Optional[dict[str, Any]]:
    """One evaluation row, or None when the film fails an eligibility rule.

    Every rejection is a rule stated above, never a judgement about the film,
    so the sample stays reproducible from the snapshot's query.
    """
    overview = (detail.get("overview") or "").strip()
    genres = [g["name"] for g in (detail.get("genres") or []) if g.get("name")]
    runtime = int(detail.get("runtime") or 0)
    votes = int(detail.get("vote_count") or 0)
    average = float(detail.get("vote_average") or 0.0)

    if len(overview) < MIN_OVERVIEW_CHARS or runtime < MIN_RUNTIME_MIN:
        return None
    if set(genres) & EXCLUDED_GENRES or not genres or not votes or not average:
        return None

    return {
        "tmdb_id": detail["id"],
        "title": detail.get("title") or "",
        "release_date": detail.get("release_date") or "",
        "runtime_min": runtime,
        "genres": genres,
        "overview": overview,
        # Ground truth, on the simulator's own 0-100 scale.
        "actual_audience_score": round(average * 10, 1),
        "vote_count": votes,
        "tmdb_url": f"https://www.themoviedb.org/movie/{detail['id']}",
    }


def build(
    *,
    released_after: str,
    released_before: str,
    votes_floor: int = DEFAULT_VOTES_FLOOR,
    want: int = 40,
) -> dict[str, Any]:
    """Fetch the sample and return a snapshot, query included."""
    candidates = discover(
        released_after=released_after, released_before=released_before,
        votes_floor=votes_floor, want=want,
    )
    films: list[dict[str, Any]] = []
    skipped = 0
    for candidate in candidates:
        if len(films) >= want:
            break
        row = _film(_detail(candidate["id"]))
        if row is None:
            skipped += 1
            continue
        films.append(row)

    return {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "TMDb /discover/movie + /movie/{id}",
        "ground_truth": "TMDb vote_average x 10 (public audience rating, 0-100)",
        "query": {
            "primary_release_date.gte": released_after,
            "primary_release_date.lte": released_before,
            "vote_count.gte": votes_floor,
            "with_original_language": "en",
            "sort_by": "vote_count.desc",
        },
        "eligibility": {
            "min_overview_chars": MIN_OVERVIEW_CHARS,
            "min_runtime_min": MIN_RUNTIME_MIN,
            "excluded_genres": sorted(EXCLUDED_GENRES),
        },
        "candidates_seen": len(candidates),
        "skipped_ineligible": skipped,
        "films": films,
    }


def save(snapshot: dict[str, Any], path: Path = SNAPSHOT) -> Path:
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load(path: Optional[Path] = None) -> dict[str, Any]:
    """The committed snapshot. `path` is resolved at call time rather than bound
    at import, so a test can point the loader at a fixture."""
    path = path or SNAPSHOT
    if not path.exists():
        raise FileNotFoundError(
            f"No film snapshot at {path}. Build one first:\n"
            "  python -m eval.run build --released-after 2026-01-01 --released-before 2026-09-19"
        )
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- brief --


def brief(film: dict[str, Any]) -> str:
    """What every predictor is told about a film — identical for all of them.

    The title is withheld on purpose. Both predictors are asked to judge
    material, not to recognise a release; leaving the title in would let a model
    that has seen the film recall its reception, and the resulting numbers would
    look excellent and mean nothing. Everything here is intrinsic to the film
    (premise, genre, length, year) and none of it reveals how it was received.
    """
    return (
        f"GENRE: {', '.join(film['genres'])}\n"
        f"RUNTIME: {film['runtime_min']} minutes\n"
        f"RELEASE YEAR: {(film.get('release_date') or '????')[:4]}\n"
        f"SYNOPSIS: {film['overview']}"
    )


def probe_leakage(film: dict[str, Any]) -> dict[str, Any]:
    """Ask the model outright whether it knows this film's reception.

    Checks the post-cutoff assumption rather than asserting it. A model that
    names the film and reports a rating close to the real one has memorised it,
    and `run.py --leakage-probe` drops it from the sample. Costs one call per
    film, which is why it is opt-in on a free tier.
    """
    from services import llm

    payload, meta = llm.generate_json_traced(
        f"Film: \"{film['title']}\" ({(film.get('release_date') or '')[:4]}).",
        tier="flash",
        system=(
            "You are auditing your own training data. For the film named, answer JSON: "
            '{"recognise": true|false, "audience_rating_out_of_100": number|null, '
            '"confidence": "none"|"vague"|"specific"}. '
            "Answer null and \"none\" unless you genuinely recall this specific film's "
            "reception. Do not guess from the title."
        ),
        mock={"recognise": False, "audience_rating_out_of_100": None, "confidence": "none"},
    )
    recalled = payload.get("audience_rating_out_of_100") if isinstance(payload, dict) else None
    gap = (
        abs(float(recalled) - film["actual_audience_score"])
        if isinstance(recalled, (int, float))
        else None
    )
    return {
        "tmdb_id": film["tmdb_id"],
        "recognise": bool(isinstance(payload, dict) and payload.get("recognise")),
        "confidence": (payload or {}).get("confidence", "none"),
        "recalled_rating": recalled,
        "gap_to_actual": round(gap, 1) if gap is not None else None,
        # Recalling the film AND landing within 10 points is the signal that the
        # score came from memory rather than from the synopsis.
        "leaked": bool(gap is not None and gap <= 10.0),
        "source": meta.get("source"),
        # Which model was asked. Without it a finished file cannot be told apart
        # from one the fallback chain answered with two.
        "provider": meta.get("provider"),
        "model": meta.get("model"),
    }
