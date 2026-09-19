"""Building the corpus the search is asked to rank, and holding out the answer.

Two jobs.

**Resolving the labels.** A brief in `labels.py` names a film and a character,
never an actor. This looks the film up on TMDb, finds that character in its cast
and records whoever TMDb says played them, so the right answers come from the
same public data the product ingests rather than from my memory. A label that
does not resolve is reported and dropped, never guessed at.

**Holding out the part.** An actor's stored record is name, biography and their
ten most popular credits as `Character in Title` — so if the part a brief
describes is among them, the search is being asked to find an actor from a record
that literally contains the answer, and the recall number would be a measure of
string matching. Every target's own credit for the film it was drawn from is
therefore removed from their record before anything is embedded. What is left is
the honest question: from an actor's *other* work, can the search tell they would
be right for this part?

The distractors are drawn from TMDb's popular-people pages. They are the reason a
number here means anything: recall@10 over a pool of fifty actors is nearly free,
and over a pool of a thousand it is a claim.
"""
import time
from typing import Any, Callable, Iterator, Optional

from core import config
from services.casting_kb import tmdb


def _search_film(title: str, year: int) -> Optional[dict[str, Any]]:
    """The TMDb film for a title and year, preferring an exact year match."""
    found = tmdb._request("/search/movie", query=title, year=year).get("results", [])
    for film in found:
        if str(film.get("release_date", ""))[:4] == str(year):
            return film
    return found[0] if found else None


def _norm(text: str) -> str:
    return tmdb._norm(text)


def resolve(
    labels: list[tuple[str, int, str, str]],
    on_step: Callable[[str], None] = lambda _m: None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Turn (title, year, character, brief) into queries with a right answer.

    Returns (queries, unresolved). A query carries the answer's TMDb id and the
    film id whose credit must be held out of that actor's record.
    """
    queries: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []

    for title, year, character, brief in labels:
        film = _search_film(title, year)
        if not film:
            unresolved.append({"film": f"{title} ({year})", "why": "no film by that title and year"})
            continue

        credits = tmdb._request(f"/movie/{film['id']}/credits")
        cast = credits.get("cast", [])
        matches = [c for c in cast if _norm(c.get("character")) == _norm(character)]
        if not matches:
            # TMDb sometimes carries a fuller spelling ("Det. Lt. Somerset").
            matches = [c for c in cast if _norm(character) and _norm(character) in _norm(c.get("character"))]
        if len(matches) != 1:
            unresolved.append({
                "film": f"{title} ({year})",
                "why": f"{len(matches)} cast entries match the character {character!r}",
            })
            continue

        answer = matches[0]
        queries.append({
            "id": f"{film['id']}:{answer['id']}",
            "brief": brief,
            # Metadata for auditing and for holding the part out. None of it is
            # given to the search, and a test checks it does not leak into `brief`.
            "film": {"tmdb_id": film["id"], "title": title, "year": year},
            "character": character,
            "answer": {"tmdb_id": answer["id"], "name": answer.get("name", "")},
        })
        on_step(f"{title} ({year}) / {character} -> {answer.get('name')}")
        time.sleep(0.05)  # TMDb is generous, but two calls a label adds up

    return queries, unresolved


def _people_pages(pages: int) -> Iterator[dict[str, Any]]:
    for page in range(1, pages + 1):
        for person in tmdb._request("/person/popular", page=page).get("results", []):
            yield person
        time.sleep(0.05)


def build(
    queries: list[dict[str, Any]],
    distractor_pages: int = 25,
    on_step: Callable[[str], None] = lambda _m: None,
) -> dict[str, Any]:
    """Fetch every answer plus a pool of distractors, with the parts held out.

    The answers are fetched first, so a pool that also happens to contain them
    does not turn into two records for one actor.
    """
    held_out: dict[int, set[int]] = {}
    for query in queries:
        held_out.setdefault(query["answer"]["tmdb_id"], set()).add(query["film"]["tmdb_id"])

    wanted: list[int] = list(held_out)
    on_step(f"fetching {len(wanted)} actors who are the answer to a brief")

    seen: set[int] = set()
    records: list[dict[str, Any]] = []
    for actor_id in wanted:
        records.append(_record(actor_id, held_out.get(actor_id, set())))
        seen.add(actor_id)
        time.sleep(0.05)

    on_step(f"fetching distractors from {distractor_pages} pages of popular people")
    skipped = 0
    for person in _people_pages(distractor_pages):
        actor_id = int(person["id"])
        if actor_id in seen:
            continue
        seen.add(actor_id)
        # Actors only, and only ones with something to match against. A record
        # that is a bare name is a distractor no search could ever rank highly,
        # and a corpus padded with them reports a recall that the real corpus —
        # where everyone has credits — would not reproduce.
        if (person.get("known_for_department") or "") != "Acting":
            skipped += 1
            continue
        record = _record(actor_id, set())
        if not record["biography"].strip() and len(record["past_roles"]) < 3:
            skipped += 1
            continue
        records.append(record)
        time.sleep(0.05)
    on_step(f"skipped {skipped} people who were not actors or had no material")

    return {
        "actors": records,
        "skipped": skipped,
        "held_out": {str(k): sorted(v) for k, v in held_out.items()},
        "distractor_pages": distractor_pages,
    }


def _record(actor_id: int, hide_films: set[int]) -> dict[str, Any]:
    """One actor as the product stores them, less any held-out credit.

    The description is built by `casting_kb.embeddings.actor_description`, the
    same function the product embeds with — not a copy of it, so the evaluation
    cannot drift into scoring a different text than the one that ships.
    """
    from services.casting_kb.embeddings import actor_description

    person = tmdb.fetch_person(actor_id)
    if hide_films:
        credits = person.get("combined_credits", {}).get("cast", [])
        person = {
            **person,
            "combined_credits": {
                "cast": [c for c in credits if int(c.get("id") or 0) not in hide_films]
            },
        }
    extracted = tmdb.extract_actor_record(person)
    return {
        "actor_id": extracted["actor_id"],
        "name": extracted["name"],
        "biography": extracted["biography"],
        "gender": extracted["gender"],
        "birth_year": extracted["birth_year"],
        "past_roles": extracted["past_roles"],
        "description": actor_description(
            extracted["name"], extracted["biography"], extracted["past_roles"]
        ),
    }


def embedder():
    """The same model the product uses, from the same setting."""
    from services.casting_kb.embeddings import _embedder

    return _embedder()


def model_name() -> str:
    return config.EMBEDDING_MODEL
