"""Auth persistence — same dual-mode contract as services/supabase_client.py.

Supabase tables when SUPABASE_URL/KEY are configured, otherwise JSON files
under backend/.state/auth/ so the demo still runs with zero credentials.
See backend/schema_auth.sql for the table definitions.

Only derived secrets are ever written: password digests and SHA-256 token
fingerprints. Raw session/invite tokens exist only in the HTTP response that
mints them.
"""
import json
import threading
from typing import Any, Optional

from core import config
from core.auth import security
from core.auth.models import Invite, Membership, Production, Session, User

_LOCK = threading.RLock()
_supabase = None

# table name -> pydantic model
_TABLES = {
    "cn_users": User,
    "cn_productions": Production,
    "cn_memberships": Membership,
    "cn_invites": Invite,
    "cn_sessions": Session,
}


def _auth_dir():
    path = config.LOCAL_STATE_DIR / "auth"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_supabase():
    global _supabase
    if _supabase is None:
        from supabase import create_client  # lazy: only needed when configured

        _supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    return _supabase


def _read(table: str) -> list[dict[str, Any]]:
    if config.has_supabase():
        return _get_supabase().table(table).select("*").execute().data or []
    path = _auth_dir() / f"{table}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write(table: str, rows: list[dict[str, Any]]) -> None:
    if config.has_supabase():
        # Supabase rows are upserted individually by the callers below.
        return
    (_auth_dir() / f"{table}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _upsert(table: str, row: dict[str, Any], key: str) -> None:
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table(table).upsert(row).execute()
            return
        rows = _read(table)
        for i, existing in enumerate(rows):
            if existing.get(key) == row.get(key):
                rows[i] = row
                break
        else:
            rows.append(row)
        _write(table, rows)


def _delete(table: str, key: str, value: str) -> None:
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table(table).delete().eq(key, value).execute()
            return
        _write(table, [r for r in _read(table) if r.get(key) != value])


def _find(table: str, **match) -> Optional[dict[str, Any]]:
    for row in _read(table):
        if all(row.get(k) == v for k, v in match.items()):
            return row
    return None


# --------------------------------------------------------------------- users --


def get_user_by_email(email: str) -> Optional[User]:
    row = _find("cn_users", email=email.strip().lower())
    return User.model_validate(row) if row else None


def get_user(user_id: str) -> Optional[User]:
    row = _find("cn_users", id=user_id)
    return User.model_validate(row) if row else None


def save_user(user: User) -> User:
    _upsert("cn_users", user.model_dump(), "id")
    return user


# --------------------------------------------------------------- productions --


def get_production(project_id: str) -> Optional[Production]:
    row = _find("cn_productions", id=project_id)
    return Production.model_validate(row) if row else None


def save_production(production: Production) -> Production:
    _upsert("cn_productions", production.model_dump(), "id")
    return production


def unique_project_id(base: str) -> str:
    """Keep a readable project_id, disambiguating only on collision."""
    candidate = base
    suffix = 2
    while get_production(candidate) is not None:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


# --------------------------------------------------------------- memberships --


def get_membership(user_id: str, project_id: str) -> Optional[Membership]:
    row = _find("cn_memberships", user_id=user_id, project_id=project_id)
    return Membership.model_validate(row) if row else None


def save_membership(membership: Membership) -> Membership:
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table("cn_memberships").upsert(
                membership.model_dump(), on_conflict="user_id,project_id"
            ).execute()
            return membership
        rows = _read("cn_memberships")
        for i, row in enumerate(rows):
            if row.get("user_id") == membership.user_id and row.get("project_id") == membership.project_id:
                rows[i] = membership.model_dump()
                break
        else:
            rows.append(membership.model_dump())
        _write("cn_memberships", rows)
    return membership


def delete_membership(user_id: str, project_id: str) -> None:
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table("cn_memberships").delete().eq("user_id", user_id).eq(
                "project_id", project_id
            ).execute()
            return
        _write(
            "cn_memberships",
            [
                r
                for r in _read("cn_memberships")
                if not (r.get("user_id") == user_id and r.get("project_id") == project_id)
            ],
        )


def memberships_for_user(user_id: str) -> list[Membership]:
    return [Membership.model_validate(r) for r in _read("cn_memberships") if r.get("user_id") == user_id]


def memberships_for_project(project_id: str) -> list[Membership]:
    return [Membership.model_validate(r) for r in _read("cn_memberships") if r.get("project_id") == project_id]


# ------------------------------------------------------------------- invites --


def save_invite(invite: Invite) -> Invite:
    _upsert("cn_invites", invite.model_dump(), "id")
    return invite


def get_invite(invite_id: str) -> Optional[Invite]:
    row = _find("cn_invites", id=invite_id)
    return Invite.model_validate(row) if row else None


def get_invite_by_token(token: str) -> Optional[Invite]:
    """Lookup by fingerprint — the raw token is never stored, so a database
    reader cannot redeem an invite they did not receive out of band."""
    row = _find("cn_invites", token_fingerprint=security.fingerprint(token))
    return Invite.model_validate(row) if row else None


def invites_for_project(project_id: str) -> list[Invite]:
    return [Invite.model_validate(r) for r in _read("cn_invites") if r.get("project_id") == project_id]


# ------------------------------------------------------------------ sessions --


def save_session(session: Session) -> Session:
    _upsert("cn_sessions", session.model_dump(), "token_fingerprint")
    return session


def get_session(token: str) -> Optional[Session]:
    row = _find("cn_sessions", token_fingerprint=security.fingerprint(token))
    return Session.model_validate(row) if row else None


def delete_session(token: str) -> None:
    _delete("cn_sessions", "token_fingerprint", security.fingerprint(token))


def purge_expired_sessions() -> None:
    """Cheap housekeeping on the local-file backend; Supabase can use a cron."""
    if config.has_supabase():
        return
    with _LOCK:
        rows = [r for r in _read("cn_sessions") if not security.is_expired(r.get("expires_at", ""))]
        _write("cn_sessions", rows)
