"""Auth persistence — same dual-mode contract as services/supabase_client.py.

Supabase tables when SUPABASE_URL/KEY are configured, otherwise JSON files
under backend/.state/auth/ so the demo still runs with zero credentials.
See backend/schema_auth.sql for the table definitions.

Only derived secrets are ever written: password digests and SHA-256 token
fingerprints. Raw session/invite tokens exist only in the HTTP response that
mints them.
"""
import threading
from typing import Any, Optional

from core import config
from core.auth import security
from core.auth.models import Invite, Membership, Production, Session, User
from services import json_files

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


class AlreadyExists(ValueError):
    """An insert met a row that is already there: a taken email or production id."""


def _is_unique_violation(exc: Exception) -> bool:
    """PostgREST reports the Postgres SQLSTATE; 23505 is unique_violation."""
    return getattr(exc, "code", None) == "23505" or "23505" in str(exc) or "duplicate key" in str(exc)


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
    """Every row of a local JSON table. Local-only on purpose: the JSON store
    rewrites a whole file per change, but a Supabase lookup must filter in the
    database (see `_select`) rather than download the table."""
    if config.has_supabase():
        raise RuntimeError(f"_read({table!r}) is for the local JSON store; use _select on Supabase.")
    with _LOCK:  # a write renames over the file; never read half-way through one
        return json_files.read_json(_auth_dir() / f"{table}.json", [])


def _write(table: str, rows: list[dict[str, Any]]) -> None:
    if config.has_supabase():
        # Supabase rows are upserted individually by the callers below.
        return
    with _LOCK:
        json_files.write_json(_auth_dir() / f"{table}.json", rows, indent=2)


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


def _select(table: str, **match) -> list[dict[str, Any]]:
    """Rows whose columns equal `match`.

    On Supabase the filter runs in the database. Fetching the whole table and
    matching here used to download every session, user and membership on every
    request, and PostgREST caps an unfiltered select at its max-rows setting
    (1000 by default), so past that size a valid token silently stopped
    resolving.
    """
    if config.has_supabase():
        query = _get_supabase().table(table).select("*")
        for column, value in match.items():
            query = query.eq(column, value)
        return query.execute().data or []
    return [row for row in _read(table) if all(row.get(k) == v for k, v in match.items())]


def _find(table: str, **match) -> Optional[dict[str, Any]]:
    rows = _select(table, **match)
    return rows[0] if rows else None


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


def create_user(user: User) -> User:
    """Insert a new account; AlreadyExists when the email is taken.

    An insert, not an upsert: two sign-ups with one email landing at the same
    moment used to hit the unique constraint as a 500 on Supabase and write a
    second row for the same email on local JSON.
    """
    with _LOCK:
        if config.has_supabase():
            try:
                _get_supabase().table("cn_users").insert(user.model_dump()).execute()
            except Exception as exc:  # noqa: BLE001 — only the unique violation is ours to translate
                if _is_unique_violation(exc):
                    raise AlreadyExists(user.email) from exc
                raise
            return user
        rows = _read("cn_users")
        if any(row.get("email") == user.email or row.get("id") == user.id for row in rows):
            raise AlreadyExists(user.email)
        _write("cn_users", [*rows, user.model_dump()])
    return user


def delete_account(user_id: str) -> None:
    """Remove an account and everything that hangs off it: the productions it
    owns (with their members and invites), its memberships and its sessions.
    On Supabase the foreign keys cascade from the user row."""
    with _LOCK:
        if config.has_supabase():
            _get_supabase().table("cn_users").delete().eq("id", user_id).execute()
            return
        owned = {row["id"] for row in _read("cn_productions") if row.get("owner_id") == user_id}
        _write("cn_productions", [r for r in _read("cn_productions") if r.get("id") not in owned])
        _write("cn_memberships", [r for r in _read("cn_memberships")
                                  if r.get("user_id") != user_id and r.get("project_id") not in owned])
        _write("cn_invites", [r for r in _read("cn_invites")
                              if r.get("created_by") != user_id and r.get("project_id") not in owned])
        _write("cn_sessions", [r for r in _read("cn_sessions") if r.get("user_id") != user_id])
        _write("cn_users", [r for r in _read("cn_users") if r.get("id") != user_id])


# --------------------------------------------------------------- productions --


def get_production(project_id: str) -> Optional[Production]:
    row = _find("cn_productions", id=project_id)
    return Production.model_validate(row) if row else None


def save_production(production: Production) -> Production:
    _upsert("cn_productions", production.model_dump(), "id")
    return production


MAX_ID_SUFFIX = 1000


def create_production(production: Production) -> Production:
    """Insert a production under the first free id in PROJ_X, PROJ_X_2, ...

    The id is claimed by the insert itself, so two sign-ups for productions
    with the same name cannot both pick PROJ_X and have the second overwrite
    the first. Returns the production as stored, with the id it got.
    """
    for suffix in range(1, MAX_ID_SUFFIX):
        row = production.model_copy(update={"id": production.id if suffix == 1 else f"{production.id}_{suffix}"})
        with _LOCK:
            if config.has_supabase():
                try:
                    _get_supabase().table("cn_productions").insert(row.model_dump()).execute()
                except Exception as exc:  # noqa: BLE001 — a taken id moves on to the next suffix
                    if _is_unique_violation(exc):
                        continue
                    raise
                return row
            rows = _read("cn_productions")
            if any(existing.get("id") == row.id for existing in rows):
                continue
            _write("cn_productions", [*rows, row.model_dump()])
            return row
    raise AlreadyExists(production.id)


REGISTER_FUNCTION = "cn_register_producer"


def _function_missing(exc: Exception) -> bool:
    """PostgREST could not find the function: this database predates it."""
    detail = f"{getattr(exc, 'code', '')} {exc}"
    return "PGRST202" in detail or "Could not find the function" in detail


def register_producer(user: User, production: Production, state: dict[str, Any]) -> Production:
    """Create an account, its production, its owner membership and the
    production's first state — all of them or none of them.

    On Supabase that is one Postgres function (`cn_register_producer`, in
    schema_auth.sql) called through PostgREST, which runs it in a single
    transaction. A database that has not had the new schema file run yet has
    no such function, so the four writes are made one by one instead and the
    account is deleted again if a later one fails.

    Local JSON has no transactions at all: everything that can be checked is
    checked first, the writes happen under the store's lock, and the account
    is removed again if one of them fails.

    Raises AlreadyExists when the email is taken. Returns the production as
    stored, with the id it got.
    """
    if config.has_supabase():
        try:
            answer = _get_supabase().rpc(REGISTER_FUNCTION, {
                "p_user": user.model_dump(),
                "p_project_id": production.id,
                "p_name": production.name,
                "p_created_at": production.created_at,
                "p_state": state,
            }).execute()
        except Exception as exc:  # noqa: BLE001 — a taken email and a missing function are ours to handle
            if _is_unique_violation(exc):
                raise AlreadyExists(user.email) from exc
            if not _function_missing(exc):
                raise
            print(f"[lumen] {REGISTER_FUNCTION} is missing — run backend/schema_auth.sql to make "
                  f"sign-up one transaction. Falling back to step-by-step writes.", flush=True)
            return _register_step_by_step(user, production, state)
        project_id = (answer.data or {}).get("project_id", production.id)
        return production.model_copy(update={"id": project_id})

    with _LOCK:
        return _register_step_by_step(user, production, state)


def _register_step_by_step(user: User, production: Production, state: dict[str, Any]) -> Production:
    """The four writes on their own, with the account removed again if a later
    one fails. Used on local JSON, and on a database without the function."""
    from core.orchestrator.state import GlobalState  # imported here: only this path needs the state store
    from services import supabase_client

    create_user(user)
    try:
        stored = create_production(production)
        save_membership(
            Membership(user_id=user.id, project_id=stored.id, role="owner", created_at=production.created_at)
        )
        # Unless a state is already stored for this id, in which case the
        # production adopts it (an existing demo project).
        with supabase_client.project_lock(stored.id):
            if supabase_client.load_state(stored.id) is None:
                supabase_client.save_state(GlobalState.model_validate({**state, "project_id": stored.id}))
        return stored
    except Exception:
        delete_account(user.id)
        raise


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
    return [Membership.model_validate(r) for r in _select("cn_memberships", user_id=user_id)]


def memberships_for_project(project_id: str) -> list[Membership]:
    return [Membership.model_validate(r) for r in _select("cn_memberships", project_id=project_id)]


# ------------------------------------------------------------------- invites --


def save_invite(invite: Invite) -> Invite:
    _upsert("cn_invites", invite.model_dump(), "id")
    return invite


def get_invite(invite_id: str) -> Optional[Invite]:
    row = _find("cn_invites", id=invite_id)
    return Invite.model_validate(row) if row else None


INVITE_CLAIM_ATTEMPTS = 5


def _claimable(invite: Invite) -> bool:
    """Whether the invite still has a use to give out right now."""
    return not invite.revoked and invite.uses < invite.max_uses and not security.is_expired(invite.expires_at)


def _swap_invite_uses(invite_id: str, expected: int, value: int) -> Optional[Invite]:
    """Set `uses` to `value`, but only while it is still `expected`.

    PostgREST answers with the rows it changed, so an empty answer means
    another redemption moved the count first and the caller should look again.
    """
    updated = (
        _get_supabase().table("cn_invites")
        .update({"uses": value})
        .eq("id", invite_id).eq("uses", expected).execute().data
    )
    return Invite.model_validate(updated[0]) if updated else None


def consume_invite_use(invite_id: str) -> Optional[Invite]:
    """Claim one use of an invite, or None when there is none left to claim.

    Reading `uses` and writing `uses + 1` as two steps let two people redeem
    the last use of an invite at the same moment and both get in. Here the
    check and the increment are a single step: on Supabase the update carries
    the count it read, so a redemption that lost the race changes no row and
    tries again against the new count; on local JSON the whole
    read-modify-write happens under the store's lock.
    """
    if not config.has_supabase():
        with _LOCK:
            rows = _read("cn_invites")
            for i, row in enumerate(rows):
                if row.get("id") != invite_id:
                    continue
                invite = Invite.model_validate(row)
                if not _claimable(invite):
                    return None
                invite.uses += 1
                rows[i] = invite.model_dump()
                _write("cn_invites", rows)
                return invite
            return None

    for _ in range(INVITE_CLAIM_ATTEMPTS):
        row = _find("cn_invites", id=invite_id)
        if row is None:
            return None
        invite = Invite.model_validate(row)
        if not _claimable(invite):
            return None
        claimed = _swap_invite_uses(invite_id, invite.uses, invite.uses + 1)
        if claimed:
            return claimed
    return None


def release_invite_use(invite_id: str) -> None:
    """Give back a use claimed for a redemption that then failed, so a sign-up
    that could not be completed does not spend someone else's place."""
    if not config.has_supabase():
        with _LOCK:
            rows = _read("cn_invites")
            for i, row in enumerate(rows):
                if row.get("id") == invite_id and int(row.get("uses") or 0) > 0:
                    rows[i] = {**row, "uses": int(row["uses"]) - 1}
                    _write("cn_invites", rows)
                    return
        return

    for _ in range(INVITE_CLAIM_ATTEMPTS):
        row = _find("cn_invites", id=invite_id)
        if row is None or int(row.get("uses") or 0) <= 0:
            return
        if _swap_invite_uses(invite_id, int(row["uses"]), int(row["uses"]) - 1):
            return


def get_invite_by_token(token: str) -> Optional[Invite]:
    """Lookup by fingerprint — the raw token is never stored, so a database
    reader cannot redeem an invite they did not receive out of band."""
    row = _find("cn_invites", token_fingerprint=security.fingerprint(token))
    return Invite.model_validate(row) if row else None


def invites_for_project(project_id: str) -> list[Invite]:
    return [Invite.model_validate(r) for r in _select("cn_invites", project_id=project_id)]


# ------------------------------------------------------------------ sessions --


def save_session(session: Session) -> Session:
    _upsert("cn_sessions", session.model_dump(), "token_fingerprint")
    return session


def get_session(token: str) -> Optional[Session]:
    row = _find("cn_sessions", token_fingerprint=security.fingerprint(token))
    return Session.model_validate(row) if row else None


def delete_session(token: str) -> None:
    _delete("cn_sessions", "token_fingerprint", security.fingerprint(token))


def delete_sessions_for_user(user_id: str) -> None:
    """Sign an account out everywhere, e.g. after a password reset."""
    _delete("cn_sessions", "user_id", user_id)


def purge_expired_sessions() -> None:
    """Cheap housekeeping on the local-file backend; Supabase can use a cron."""
    if config.has_supabase():
        return
    with _LOCK:
        rows = [r for r in _read("cn_sessions") if not security.is_expired(r.get("expires_at", ""))]
        _write("cn_sessions", rows)
