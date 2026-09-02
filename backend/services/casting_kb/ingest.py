"""TMDb-to-PostgreSQL actor ingestion pipeline."""
from typing import Any, Iterable

from services.casting_kb.db import get_connection
from services.casting_kb.tmdb import extract_actor_record, fetch_person


def upsert_actor(connection: Any, actor: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO actors (actor_id, name, gender, birth_year, biography, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (actor_id) DO UPDATE SET
                name = EXCLUDED.name, gender = EXCLUDED.gender,
                birth_year = EXCLUDED.birth_year, biography = EXCLUDED.biography,
                updated_at = NOW()
            """,
            (actor["actor_id"], actor["name"], actor["gender"], actor["birth_year"], actor["biography"]),
        )
        cursor.execute("DELETE FROM actor_tags WHERE actor_id = %s", (actor["actor_id"],))
        cursor.executemany(
            "INSERT INTO actor_tags (actor_id, tag_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            [(actor["actor_id"], tag) for tag in actor["tags"]],
        )
        cursor.execute("DELETE FROM past_roles WHERE actor_id = %s", (actor["actor_id"],))
        cursor.executemany(
            """INSERT INTO past_roles (actor_id, character_description)
               VALUES (%s, %s) ON CONFLICT DO NOTHING""",
            [(actor["actor_id"], role) for role in actor["past_roles"]],
        )


def ingest_actor_ids(actor_ids: Iterable[int]) -> int:
    records = [extract_actor_record(fetch_person(actor_id)) for actor_id in actor_ids]
    with get_connection() as connection:
        for actor in records:
            upsert_actor(connection, actor)
    return len(records)