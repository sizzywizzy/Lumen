"""Auth domain models.

A "production" is the team container around one GlobalState (project_id).
Membership is what grants access — knowing a project_id is never enough.
"""
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Pydantic's EmailStr needs the email-validator package; this project keeps its
# dependency list to fastapi/uvicorn/pydantic, so we validate with a plain rule.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def _clean_email(value: str) -> str:
    email = str(value).strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise ValueError("Enter a valid email address.")
    return email

# owner    — created the production; full control, cannot be removed
# producer — can edit production data and invite others
# crew     — read-only access to the dashboard
Role = Literal["owner", "producer", "crew"]

ROLE_RANK: dict[str, int] = {"crew": 1, "producer": 2, "owner": 3}


def role_at_least(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(minimum, 99)


class User(BaseModel):
    id: str
    email: str  # stored lowercased
    name: str
    password_hash: str
    created_at: str


class Production(BaseModel):
    id: str  # == GlobalState.project_id
    name: str
    owner_id: str
    created_at: str


class Membership(BaseModel):
    user_id: str
    project_id: str
    role: Role = "crew"
    created_at: str


class Invite(BaseModel):
    id: str
    project_id: str
    token_fingerprint: str  # SHA-256 of the token; the token itself is shown once
    role: Role = "crew"
    created_by: str
    created_at: str
    expires_at: str
    max_uses: int = 1
    uses: int = 0
    revoked: bool = False
    label: str = ""


class Session(BaseModel):
    token_fingerprint: str
    user_id: str
    created_at: str
    expires_at: str


# ----------------------------------------------------------------- requests --


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=120)
    production_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return _clean_email(v)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if v.strip() != v:
            raise ValueError("Password must not start or end with whitespace.")
        if v.isdigit() or v.isalpha():
            raise ValueError("Password must mix letters with numbers or symbols.")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    _norm_email = field_validator("email")(classmethod(lambda cls, v: _clean_email(v)))


class InviteRequest(BaseModel):
    project_id: str
    role: Role = "crew"
    max_uses: int = Field(default=1, ge=1, le=50)
    ttl_hours: int = Field(default=72, ge=1, le=720)
    label: str = Field(default="", max_length=120)


class JoinRequest(BaseModel):
    """Redeem an invite. Supply credentials to create an account, or send an
    existing session's bearer token to add the production to that account."""
    token: str
    email: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=10, max_length=200)
    name: Optional[str] = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v):
        return _clean_email(v) if v else v


class CandidateStatusRequest(BaseModel):
    status: Literal["SOURCING", "SCREENING", "LOCKED", "DISQUALIFIED", "FLAGGED_ACTION_REQUIRED"]
    reason: str = Field(default="", max_length=300)
