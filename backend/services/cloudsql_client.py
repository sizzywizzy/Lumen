"""Cloud SQL PostgreSQL client for GlobalState persistence.

This provides the same interface as supabase_client.py but uses Google Cloud SQL.
When Cloud SQL is configured, it takes precedence over Supabase; otherwise falls back
to the existing Supabase or local JSON file behavior.

Requires:
- google-cloud-sql>=3.0
- CLOUD_SQL_CONNECTION_NAME environment variable
- DB_USER, DB_PASS, DB_NAME environment variables
"""
import json
from typing import Optional

from core import config
from core.orchestrator.state import GlobalState

_cloudsql_pool = None


def _get_cloudsql_pool():
    """Get or create the Cloud SQL connection pool."""
    global _cloudsql_pool
    if _cloudsql_pool is None:
        try:
            import pymysql
            from google.cloud.sql.connector import Connector

            connector = Connector()

            def getconn():
                conn = connector.connect(
                    config.CLOUD_SQL_CONNECTION_NAME,
                    "pymysql",
                    user=config.DB_USER,
                    password=config.DB_PASS,
                    db=config.DB_NAME,
                )
                return conn

            _cloudsql_pool = pymysql.pool.Pool(
                getconn,
                pool_name="cinenode-pool",
                pool_size=5,
            )
        except ImportError:
            raise RuntimeError(
                "google-cloud-sql and pymysql required for Cloud SQL. "
                "Install: pip install google-cloud-sql>=3.0 pymysql"
            )
    return _cloudsql_pool


def has_cloudsql() -> bool:
    """Check if Cloud SQL is properly configured."""
    return bool(
        config.CLOUD_SQL_CONNECTION_NAME
        and config.DB_USER
        and config.DB_PASS
        and config.DB_NAME
    )


def save_state(state: GlobalState) -> None:
    """Save GlobalState to Cloud SQL."""
    if not has_cloudsql():
        # Fall back to existing behavior
        from services import supabase_client
        supabase_client.save_state(state)
        return

    pool = _get_cloudsql_pool()
    with pool.connection() as conn:
        with conn.cursor() as cursor:
            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS global_state (
                    project_id TEXT PRIMARY KEY,
                    state JSONB,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Upsert the state
            cursor.execute(
                """
                INSERT INTO global_state (project_id, state)
                VALUES (%s, %s)
                ON CONFLICT (project_id) DO UPDATE SET
                    state = EXCLUDED.state,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (state.project_id, json.dumps(state.model_dump()))
            )
        conn.commit()


def load_state(project_id: str) -> Optional[GlobalState]:
    """Load GlobalState from Cloud SQL."""
    if not has_cloudsql():
        # Fall back to existing behavior
        from services import supabase_client
        return supabase_client.load_state(project_id)

    pool = _get_cloudsql_pool()
    with pool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT state FROM global_state WHERE project_id = %s",
                (project_id,)
            )
            result = cursor.fetchone()
            if result:
                return GlobalState.model_validate(json.loads(result[0]))
            return None


def list_projects() -> list[str]:
    """List all project IDs from Cloud SQL."""
    if not has_cloudsql():
        # Fall back to existing behavior
        from services import supabase_client
        return supabase_client.list_projects()

    pool = _get_cloudsql_pool()
    with pool.connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT project_id FROM global_state ORDER BY updated_at DESC")
            return [row[0] for row in cursor.fetchall()]
