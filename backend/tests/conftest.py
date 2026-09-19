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


# Every model provider, so that adding one to .env can never quietly send the
# test suite to a live endpoint. `configured_llm_providers` reads these by name
# at call time, so denying them here denies the whole chain.
NO_PROVIDER = ("has_gemini", "has_cerebras", "has_groq", "has_ollama")


@pytest.fixture(scope="session", autouse=True)
def never_real_state_or_live_models(tmp_path_factory):
    """The floor under every test, whatever it patches or undoes: the stores
    fall back to a throwaway folder, never to backend/.state/ or Supabase, and
    every model, search and TMDb call gets its mock even when .env holds real
    keys. Tests that need a live path patch it on for themselves."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(config, "LOCAL_STATE_DIR", tmp_path_factory.mktemp("state"))
        patch.setattr(config, "has_supabase", lambda: False)
        for check in NO_PROVIDER:
            patch.setattr(config, check, lambda: False)
        patch.setattr(config, "has_tavily", lambda: False)
        patch.setattr(config, "has_tmdb", lambda: False)
        yield


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Point every local-JSON store at a throwaway directory."""
    monkeypatch.setattr(config, "LOCAL_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "has_supabase", lambda: False)
    return tmp_path


@pytest.fixture(autouse=True)
def background_work_runs_inline(monkeypatch):
    """Pipeline runs (domains/pipeline/jobs.py) and the production's poster
    (domains/launch/posters.py) work on background threads. A thread like that
    outlives its test, and once the test's patches are undone it reads and
    writes the real `.state/` (or Supabase), so in tests both run inline, and
    no run's bookkeeping carries over to the next test."""
    from domains.launch import posters
    from domains.pipeline import jobs

    monkeypatch.setattr(posters, "_spawn", lambda target, *args: target(*args))
    monkeypatch.setattr(posters, "_ACTIVE", set())
    monkeypatch.setattr(posters, "_FAILED", {})
    monkeypatch.setattr(jobs, "_spawn", lambda target, *args: target(*args))
    monkeypatch.setattr(jobs, "_ACTIVE", {})


@pytest.fixture(autouse=True)
def rate_limits_start_empty():
    """The sign-in limits count per address in memory; every test starts clean."""
    from domains.auth import router as auth_router

    auth_router.SIGN_INS.clear()
    auth_router.SIGN_UPS.clear()


@pytest.fixture
def offline(monkeypatch):
    """Force the mock fallbacks, even on a machine with model credentials."""
    for check in NO_PROVIDER:
        monkeypatch.setattr(config, check, lambda: False)
    monkeypatch.setattr(config, "has_tavily", lambda: False)


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
