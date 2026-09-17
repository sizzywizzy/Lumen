"""Poster persistence — same dual-mode contract as the other stores.

Supabase table `cn_posters` when configured, otherwise one JSON file per
production under backend/.state/posters/. A production has one poster, the one
on its Overview, and a new poster replaces it only once it is ready, so a
failed attempt never leaves the production without one.

Kept apart from GlobalState on purpose: a pipeline run saves back the copy of
the state it loaded, which would drop a poster saved while it ran, and every
state read would carry the image. The image rides in the record base64-encoded
(an SVG of a few KB); status reads skip it and only the image route loads it.
"""
import threading
from typing import Any, Optional

from core import config
from services import json_files

_LOCK = threading.RLock()
_supabase = None

TABLE = "cn_posters"
# PostgREST rejects a write that names a column the table lacks, so every key
# here has a column in backend/schema_state.sql.
META_COLUMNS = (
    "project_id", "poster_id", "created_at", "started_by", "script_fingerprint",
    "title", "style", "concept", "provenance", "image_mime",
)
IMAGE_COLUMN = "image_base64"


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client

        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def _path(project_id: str):
    folder = config.LOCAL_STATE_DIR / "posters"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{project_id}.json"


def save(record: dict[str, Any]) -> dict[str, Any]:
    """Store the production's poster, replacing the one it had."""
    row = {key: record.get(key) for key in (*META_COLUMNS, IMAGE_COLUMN)}
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table(TABLE).upsert(row).execute()
            return row
        # Atomic, so a status poll never reads half a file.
        json_files.write_json(_path(row["project_id"]), row)
    return row


def get(project_id: str, *, with_image: bool = False) -> Optional[dict[str, Any]]:
    """The production's poster, without the image unless asked for."""
    if config.has_supabase():
        columns = ",".join((*META_COLUMNS, IMAGE_COLUMN) if with_image else META_COLUMNS)
        rows = _get_supabase().table(TABLE).select(columns).eq("project_id", project_id).execute().data
        return rows[0] if rows else None
    with _LOCK:
        row = json_files.read_json(_path(project_id))
    if row is None:
        return None
    if not with_image:
        row.pop(IMAGE_COLUMN, None)
    return row
