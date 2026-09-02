"""FastAPI dependencies for authentication and per-production authorization.

The rule this enforces: knowing a project_id grants nothing. Every
project-scoped endpoint resolves the caller's membership row for that exact
project, so one production can never read or write another's dashboard.
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException, Path

from core.auth import security
from core.auth.models import Membership, User, role_at_least
from services import auth_store


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def current_user(authorization: Optional[str] = Header(default=None)) -> User:
    """Resolve the bearer session token to a user, or 401."""
    token = _bearer(authorization)
    if not token:
        raise HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})

    session = auth_store.get_session(token)
    if session is None:
        raise HTTPException(401, "Session not recognised. Sign in again.")
    if security.is_expired(session.expires_at):
        auth_store.delete_session(token)
        raise HTTPException(401, "Session expired. Sign in again.")

    user = auth_store.get_user(session.user_id)
    if user is None:
        auth_store.delete_session(token)
        raise HTTPException(401, "Account no longer exists.")
    return user


def optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[User]:
    """Same as current_user but returns None instead of raising — used by the
    invite-preview endpoint, which works signed in or signed out."""
    try:
        return current_user(authorization)
    except HTTPException:
        return None


def membership_for(user: User, project_id: str) -> Membership:
    membership = auth_store.get_membership(user.id, project_id)
    if membership is None:
        # 404 rather than 403: a non-member should not be able to distinguish
        # "this production exists" from "it does not".
        raise HTTPException(404, f"No production '{project_id}' available to this account.")
    return membership


def require_member(
    project_id: str = Path(...), user: User = Depends(current_user)
) -> Membership:
    """Read access — any role on the production."""
    return membership_for(user, project_id)


def require_producer(
    project_id: str = Path(...), user: User = Depends(current_user)
) -> Membership:
    """Write access — producer or owner. Crew are read-only."""
    membership = membership_for(user, project_id)
    if not role_at_least(membership.role, "producer"):
        raise HTTPException(403, "Your role on this production is read-only.")
    return membership


def require_owner(
    project_id: str = Path(...), user: User = Depends(current_user)
) -> Membership:
    membership = membership_for(user, project_id)
    if not role_at_least(membership.role, "owner"):
        raise HTTPException(403, "Only the production owner can do that.")
    return membership
