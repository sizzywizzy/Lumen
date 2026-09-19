"""Semantic actor matching against the pgvector-backed knowledge base."""
from datetime import date
from typing import Any

from core import config
from services.casting_kb.db import get_connection
from services.casting_kb.embeddings import embed_text


def _refuse_a_mismatched_model(connection: Any) -> None:
    """Fail loudly when the stored vectors came from a different model.

    `actor_embeddings.model_name` has always recorded which model wrote each
    vector, and nothing ever read it. Two models of the same width — and 384 is a
    common width, shared by all-MiniLM-L6-v2 and bge-small-en-v1.5 — put their
    vectors in unrelated coordinate systems, so a swapped EMBEDDING_MODEL passes
    every dimension check and returns confident nonsense for every search.
    `backend/eval/casting` measures which model to prefer; this is what makes
    changing to it safe.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT model_name FROM actor_embeddings WHERE model_name IS NOT NULL"
        )
        stored = {row[0] for row in cursor.fetchall()}
    stale = stored - {config.EMBEDDING_MODEL}
    if stale:
        raise RuntimeError(
            f"The actor vectors were written by {sorted(stale)} but EMBEDDING_MODEL is now "
            f"{config.EMBEDDING_MODEL!r}. Vectors from different models are not comparable, "
            "whatever their width. Re-run scripts/generate_actor_embeddings.py."
        )


def match_actors(
    character_description: str,
    *,
    gender: int | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not character_description.strip():
        raise ValueError("character_description must not be empty")
    if min_age is not None and max_age is not None and min_age > max_age:
        raise ValueError("min_age must be less than or equal to max_age")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    vector = "[" + ",".join(str(value) for value in embed_text(character_description)) + "]"
    current_year = date.today().year
    clauses = ["ae.embedding IS NOT NULL"]
    parameters: list[Any] = [vector]
    if gender is not None:
        clauses.append("a.gender = %s")
        parameters.append(gender)
    if min_age is not None:
        clauses.append("a.birth_year IS NOT NULL AND a.birth_year <= %s")
        parameters.append(current_year - min_age)
    if max_age is not None:
        clauses.append("a.birth_year IS NOT NULL AND a.birth_year >= %s")
        parameters.append(current_year - max_age)

    query = f"""
        SELECT a.actor_id, a.name, a.gender, a.birth_year, a.biography,
               1 - (ae.embedding <=> %s::vector) AS similarity
        FROM actors a
        JOIN actor_embeddings ae ON ae.actor_id = a.actor_id
        WHERE {' AND '.join(clauses)}
        ORDER BY ae.embedding <=> %s::vector
        LIMIT %s
    """
    parameters.extend([vector, limit])
    with get_connection() as connection:
        _refuse_a_mismatched_model(connection)
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()
    return [
        {
            "actor_id": row[0],
            "name": row[1],
            "gender": row[2],
            "birth_year": row[3],
            "biography": row[4],
            "similarity": float(row[5]),
        }
        for row in rows
    ]