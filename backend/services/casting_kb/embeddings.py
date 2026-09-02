"""Embedding generation for actor biographies and credited roles."""
from typing import Any

from core import config
from services.casting_kb.db import get_connection


def actor_description(name: str, biography: str, roles: list[str]) -> str:
    role_text = "; ".join(roles)
    return f"Actor: {name}. Biography: {biography}. Past roles: {role_text}".strip()


def _embedder() -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Install sentence-transformers to generate actor embeddings") from exc
    return SentenceTransformer(config.EMBEDDING_MODEL)


def generate_actor_embeddings(limit: int | None = None) -> int:
    model = _embedder()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            query = """
                SELECT a.actor_id, a.name, a.biography,
                       COALESCE(array_agg(pr.character_description)
                                FILTER (WHERE pr.character_description IS NOT NULL), '{}')
                FROM actors a
                LEFT JOIN past_roles pr ON pr.actor_id = a.actor_id
                GROUP BY a.actor_id, a.name, a.biography
                ORDER BY a.actor_id
            """
            if limit is not None:
                query += " LIMIT %s"
                cursor.execute(query, (limit,))
            else:
                cursor.execute(query)
            rows = cursor.fetchall()

        descriptions = [actor_description(row[1], row[2], list(row[3])) for row in rows]
        if not descriptions:
            return 0
        vectors = model.encode(descriptions, normalize_embeddings=True)
        if any(len(vector) != config.EMBEDDING_DIMENSIONS for vector in vectors):
            actual_dimensions = len(vectors[0])
            raise ValueError(
                f"Embedding model returned {actual_dimensions} dimensions; "
                f"schema expects {config.EMBEDDING_DIMENSIONS}"
            )
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO actor_embeddings (actor_id, embedding, model_name, updated_at)
                VALUES (%s, %s::vector, %s, NOW())
                ON CONFLICT (actor_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding, model_name = EXCLUDED.model_name,
                    updated_at = NOW()
                """,
                [
                    (row[0], "[" + ",".join(str(float(value)) for value in vector) + "]", config.EMBEDDING_MODEL)
                    for row, vector in zip(rows, vectors)
                ],
            )
    return len(rows)


def embed_text(text: str) -> list[float]:
    vector = _embedder().encode([text], normalize_embeddings=True)[0]
    values = [float(value) for value in vector]
    if len(values) != config.EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embedding model returned {len(values)} dimensions; "
            f"schema expects {config.EMBEDDING_DIMENSIONS}"
        )
    return values