"""Small PostgreSQL adapter for the actor knowledge base.

The driver is imported lazily so the mock pipeline still works without DB
dependencies or credentials.
"""
from contextlib import contextmanager
from typing import Iterator

from core import config


def _connection_string() -> str:
    if config.DATABASE_URL:
        return config.DATABASE_URL
    if config.has_cloudsql():
        return (
            f"host={config.CLOUD_SQL_CONNECTION_NAME} user={config.DB_USER} "
            f"password={config.DB_PASS} dbname={config.DB_NAME}"
        )
    raise RuntimeError("DATABASE_URL is not configured")


@contextmanager
def get_connection() -> Iterator[object]:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install psycopg[binary] to use the actor KB") from exc
    connection = psycopg.connect(_connection_string())
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()