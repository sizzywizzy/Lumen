"""Authentication and production-team endpoints. Mounted under /api/auth.

Flow:
  1. POST /register  — a producer creates their account *and* the production.
  2. POST /invites   — owner/producer mints a single-use, expiring invite token.
                       The raw token is returned exactly once, never stored.
  3. POST /join      — a team member redeems the token and gets their own
                       account and session. No shared password, ever.
  4. Everything else — resolved through the caller's membership row.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from core.auth import security
from core.auth.deps import current_user, membership_for, optional_user
from core.auth.models import (
    Invite,
    InviteRequest,
    JoinRequest,
    LoginRequest,
    Membership,
    Production,
    RegisterRequest,
    Session,
    User,
    role_at_least,
)
from core.orchestrator.state import BudgetState, GlobalState
from services import auth_store, supabase_client

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "created_at": user.created_at}


def _mint_session(user: User) -> str:
    auth_store.purge_expired_sessions()
    token = security.new_token()
    auth_store.save_session(
        Session(
            token_fingerprint=security.fingerprint(token),
            user_id=user.id,
            created_at=security.iso(security.now()),
            expires_at=security.expires_in(security.SESSION_TTL_HOURS),
        )
    )
    return token


def _productions_for(user: User) -> list[dict]:
    out = []
    for membership in auth_store.memberships_for_user(user.id):
        production = auth_store.get_production(membership.project_id)
        if production:
            out.append(
                {
                    "project_id": production.id,
                    "name": production.name,
                    "role": membership.role,
                    "joined_at": membership.created_at,
                }
            )
    return sorted(out, key=lambda p: p["joined_at"])


def _session_payload(user: User, token: str) -> dict:
    return {"token": token, "user": _public_user(user), "productions": _productions_for(user)}


@router.post("/register", status_code=201)
def register(req: RegisterRequest):
    """Step 1 — create the production account. The creator becomes its owner."""
    if auth_store.get_user_by_email(req.email):
        raise HTTPException(409, "An account with that email already exists. Sign in instead.")

    now = security.iso(security.now())
    user = auth_store.save_user(
        User(
            id=security.new_id("usr"),
            email=req.email,
            name=req.name.strip(),
            password_hash=security.hash_password(req.password),
            created_at=now,
        )
    )

    project_id = auth_store.unique_project_id(security.project_id_from_name(req.production_name))
    auth_store.save_production(
        Production(id=project_id, name=req.production_name.strip(), owner_id=user.id, created_at=now)
    )
    auth_store.save_membership(
        Membership(user_id=user.id, project_id=project_id, role="owner", created_at=now)
    )

    # Seed the GlobalState this production's dashboard reads, unless one is
    # already on disk for this id (so an existing demo project is adopted).
    if supabase_client.load_state(project_id) is None:
        supabase_client.save_state(
            GlobalState(project_id=project_id, budget_state=BudgetState())
        )

    return _session_payload(user, _mint_session(user))


@router.post("/login")
def login(req: LoginRequest):
    user = auth_store.get_user_by_email(req.email)
    # Verify against a dummy hash when the user is unknown so that a wrong
    # email and a wrong password take the same time to answer.
    encoded = user.password_hash if user else security.hash_password("timing-equaliser")
    if not security.verify_password(req.password, encoded) or user is None:
        raise HTTPException(401, "Email or password is incorrect.")
    return _session_payload(user, _mint_session(user))


@router.post("/logout", status_code=204)
def logout(authorization: Optional[str] = Header(default=None)):
    """Revoke the presented session. Other devices stay signed in.

    Always answers 204 so a stale or already-revoked token cannot be probed.
    """
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        auth_store.delete_session(token.strip())
    return None


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"user": _public_user(user), "productions": _productions_for(user)}


# ------------------------------------------------------------------- invites --


@router.post("/invites", status_code=201)
def create_invite(req: InviteRequest, user: User = Depends(current_user)):
    """Step 2 — mint a secure invite. Producer or owner only.

    The token is 256 bits of `secrets` randomness and is returned here and
    nowhere else; only its SHA-256 fingerprint is persisted.
    """
    membership = membership_for(user, req.project_id)
    if not role_at_least(membership.role, "producer"):
        raise HTTPException(403, "Only producers and owners can invite team members.")
    if req.role == "owner":
        raise HTTPException(400, "A production has a single owner; invite as producer or crew.")

    token = security.new_token()
    invite = auth_store.save_invite(
        Invite(
            id=security.new_id("inv"),
            project_id=req.project_id,
            token_fingerprint=security.fingerprint(token),
            role=req.role,
            created_by=user.id,
            created_at=security.iso(security.now()),
            expires_at=security.expires_in(req.ttl_hours),
            max_uses=req.max_uses,
            label=req.label.strip(),
        )
    )
    return {"invite": _public_invite(invite), "token": token}


def _public_invite(invite: Invite) -> dict:
    """Never includes the token or its fingerprint."""
    remaining = max(0, invite.max_uses - invite.uses)
    return {
        "id": invite.id,
        "project_id": invite.project_id,
        "role": invite.role,
        "label": invite.label,
        "created_at": invite.created_at,
        "expires_at": invite.expires_at,
        "max_uses": invite.max_uses,
        "uses": invite.uses,
        "revoked": invite.revoked,
        "expired": security.is_expired(invite.expires_at),
        "active": not invite.revoked and remaining > 0 and not security.is_expired(invite.expires_at),
    }


@router.get("/invites/{project_id}")
def list_invites(project_id: str, user: User = Depends(current_user)):
    membership = membership_for(user, project_id)
    if not role_at_least(membership.role, "producer"):
        raise HTTPException(403, "Only producers and owners can view invites.")
    return {"invites": [_public_invite(i) for i in auth_store.invites_for_project(project_id)]}


@router.delete("/invites/{project_id}/{invite_id}")
def revoke_invite(project_id: str, invite_id: str, user: User = Depends(current_user)):
    membership = membership_for(user, project_id)
    if not role_at_least(membership.role, "producer"):
        raise HTTPException(403, "Only producers and owners can revoke invites.")
    invite = auth_store.get_invite(invite_id)
    if invite is None or invite.project_id != project_id:
        raise HTTPException(404, "Invite not found.")
    invite.revoked = True
    auth_store.save_invite(invite)
    return {"invite": _public_invite(invite)}


@router.get("/invite-preview/{token}")
def preview_invite(token: str, user: Optional[User] = Depends(optional_user)):
    """What the join screen shows before asking for credentials. Reachable only
    by someone already holding the token, which is the secret."""
    invite = auth_store.get_invite_by_token(token)
    if invite is None:
        raise HTTPException(404, "This invite link is not valid.")
    production = auth_store.get_production(invite.project_id)
    return {
        "production_name": production.name if production else invite.project_id,
        "project_id": invite.project_id,
        "role": invite.role,
        "active": _public_invite(invite)["active"],
        "expires_at": invite.expires_at,
        "already_member": bool(user and auth_store.get_membership(user.id, invite.project_id)),
        "signed_in_as": user.email if user else None,
    }


@router.post("/join")
def join(req: JoinRequest, user: Optional[User] = Depends(optional_user)):
    """Step 3 — redeem an invite.

    Signed in: the production is added to the existing account.
    Signed out: credentials in the body create a brand-new account, so every
    member ends up with their own login rather than a shared one.
    """
    invite = auth_store.get_invite_by_token(req.token)
    if invite is None:
        raise HTTPException(404, "This invite link is not valid.")
    if invite.revoked:
        raise HTTPException(410, "This invite has been revoked.")
    if security.is_expired(invite.expires_at):
        raise HTTPException(410, "This invite has expired. Ask the producer for a new one.")
    if invite.uses >= invite.max_uses:
        raise HTTPException(410, "This invite has already been used.")

    now = security.iso(security.now())

    if user is None:
        if not (req.email and req.password and req.name):
            raise HTTPException(400, "Provide a name, email and password to create your account.")
        if auth_store.get_user_by_email(req.email):
            raise HTTPException(409, "An account with that email already exists. Sign in, then open the invite link again.")
        _check_password_strength(req.password)
        user = auth_store.save_user(
            User(
                id=security.new_id("usr"),
                email=req.email,
                name=req.name.strip(),
                password_hash=security.hash_password(req.password),
                created_at=now,
            )
        )

    if auth_store.get_membership(user.id, invite.project_id) is None:
        auth_store.save_membership(
            Membership(user_id=user.id, project_id=invite.project_id, role=invite.role, created_at=now)
        )
        # Only a redemption that actually added a member consumes a use.
        invite.uses += 1
        auth_store.save_invite(invite)

    return _session_payload(user, _mint_session(user))


def _check_password_strength(password: str) -> None:
    """Apply the same strength rule the register endpoint enforces."""
    problem = security.password_problem(password)
    if problem:
        raise HTTPException(422, problem)


# --------------------------------------------------------------------- team --


@router.get("/team/{project_id}")
def team(project_id: str, user: User = Depends(current_user)):
    membership = membership_for(user, project_id)
    production = auth_store.get_production(project_id)
    members = []
    for m in auth_store.memberships_for_project(project_id):
        member_user = auth_store.get_user(m.user_id)
        if member_user:
            members.append(
                {
                    "user_id": member_user.id,
                    "name": member_user.name,
                    "email": member_user.email,
                    "role": m.role,
                    "joined_at": m.created_at,
                    "is_you": member_user.id == user.id,
                }
            )
    return {
        "production": {"project_id": project_id, "name": production.name if production else project_id},
        "your_role": membership.role,
        "members": sorted(members, key=lambda m: m["joined_at"]),
    }


@router.delete("/team/{project_id}/{user_id}")
def remove_member(project_id: str, user_id: str, user: User = Depends(current_user)):
    membership = membership_for(user, project_id)
    if not role_at_least(membership.role, "owner"):
        raise HTTPException(403, "Only the production owner can remove team members.")
    target = auth_store.get_membership(user_id, project_id)
    if target is None:
        raise HTTPException(404, "That person is not on this production.")
    if target.role == "owner":
        raise HTTPException(400, "The owner cannot be removed from their own production.")
    auth_store.delete_membership(user_id, project_id)
    return {"removed": user_id}
