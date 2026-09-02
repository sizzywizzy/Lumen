"""TMDb client and normalization helpers for actor knowledge-base records."""
from typing import Any

import requests

from core import config

TMDB_BASE_URL = "https://api.themoviedb.org/3"


def _request(path: str, **params: Any) -> dict[str, Any]:
    if not config.TMDB_API_KEY:
        raise RuntimeError("TMDB_API_KEY is not configured")
    response = requests.get(
        f"{TMDB_BASE_URL}{path}",
        params={"api_key": config.TMDB_API_KEY, "language": config.TMDB_LANGUAGE, **params},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def search_people(query: str, page: int = 1) -> list[dict[str, Any]]:
    return _request("/search/person", query=query, page=page).get("results", [])


def fetch_person(person_id: int) -> dict[str, Any]:
    return _request(f"/person/{person_id}", append_to_response="combined_credits")


def extract_physical_traits(person: dict[str, Any]) -> list[str]:
    """Read explicitly supplied traits; TMDb itself normally supplies none."""
    traits: list[str] = []
    for key in ("height", "eye_color", "hair_color", "physical_traits"):
        value = person.get(key)
        if isinstance(value, list):
            traits.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            traits.append(str(value).strip())
    return sorted(set(traits))


def extract_actor_record(person: dict[str, Any], role_limit: int = 10) -> dict[str, Any]:
    credits = person.get("combined_credits", {}).get("cast", [])
    roles: list[str] = []
    for credit in sorted(credits, key=lambda item: item.get("popularity", 0), reverse=True):
        character = (credit.get("character") or "").strip()
        title = (credit.get("title") or credit.get("name") or "").strip()
        if character and title:
            roles.append(f"{character} in {title}")
        if len(roles) >= role_limit:
            break

    tags = extract_physical_traits(person)
    department = (person.get("known_for_department") or "").strip()
    if department:
        tags.append(department.lower())

    birthday = person.get("birthday") or ""
    birth_year = int(birthday[:4]) if len(birthday) >= 4 and birthday[:4].isdigit() else None
    return {
        "actor_id": int(person["id"]),
        "name": person.get("name", "").strip(),
        "gender": person.get("gender"),
        "birth_year": birth_year,
        "biography": (person.get("biography") or "").strip(),
        "tags": sorted(set(tags)),
        "past_roles": roles,
    }