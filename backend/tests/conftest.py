"""Shared fixtures.

The auth store reads and writes real JSON under `config.LOCAL_STATE_DIR`. Every
test that touches it gets its own tmp directory and an explicitly disabled
Supabase backend, so a developer's populated `.state/` (or a configured
SUPABASE_URL in their `.env`) can never leak into a test run or be written to.
"""
import pytest

from core import config
from core.auth import security
from core.auth.models import Membership, Production, Session, User


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Point every local-JSON store at a throwaway directory."""
    monkeypatch.setattr(config, "LOCAL_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "has_supabase", lambda: False)
    return tmp_path


@pytest.fixture
def make_user(state_dir):
    """Persist a user and return (user, plaintext_password)."""
    from services import auth_store

    def _make(email="ava@neonnights.film", name="Ava Reyes", password="neon-nights-2026"):
        user = User(
            id=security.new_id("usr"),
            email=email.lower(),
            name=name,
            password_hash=security.hash_password(password),
            created_at=security.iso(security.now()),
        )
        auth_store.save_user(user)
        return user, password

    return _make


@pytest.fixture
def signed_in(state_dir, make_user):
    """Persist a user plus a live session; return (user, raw_token)."""
    from services import auth_store

    def _sign_in(user=None, ttl_hours=security.SESSION_TTL_HOURS):
        if user is None:
            user, _ = make_user()
        token = security.new_token()
        auth_store.save_session(
            Session(
                token_fingerprint=security.fingerprint(token),
                user_id=user.id,
                created_at=security.iso(security.now()),
                expires_at=security.expires_in(ttl_hours),
            )
        )
        return user, token

    return _sign_in


@pytest.fixture
def make_production(state_dir):
    """Persist a production and grant one user a role on it."""
    from services import auth_store

    def _make(owner, project_id="PROJ_NEON_NIGHTS", role="owner"):
        auth_store.save_production(
            Production(
                id=project_id,
                name="Neon Nights",
                owner_id=owner.id,
                created_at=security.iso(security.now()),
            )
        )
        auth_store.save_membership(
            Membership(
                user_id=owner.id,
                project_id=project_id,
                role=role,
                created_at=security.iso(security.now()),
            )
        )
        return project_id

    return _make
