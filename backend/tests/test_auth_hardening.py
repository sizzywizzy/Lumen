"""Sign-in and sign-up hold up under pressure: attempts are limited per client
address, the same email or production name landing twice at once cannot
corrupt the account tables, and a sign-up that fails half-way is undone."""
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from core import config
from core.auth import ratelimit, security
from core.auth.models import Production, User
from domains.auth import router as auth_router
from services import auth_store, supabase_client

SIGN_UP = {"email": "ava@neonnights.film", "password": "neon-nights-2026",
           "name": "Ava Reyes", "production_name": "Neon Nights"}


def _client():
    from main import app

    return TestClient(app)


def _request(peer: str, forwarded: str = "") -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_sign_ins_are_limited_per_address(state_dir, make_user, monkeypatch):
    make_user()
    monkeypatch.setattr(auth_router, "SIGN_INS", ratelimit.SlidingWindow(limit=3, window=600))
    client = _client()
    wrong = {"email": "ava@neonnights.film", "password": "not-the-password-1"}

    assert [client.post("/api/auth/login", json=wrong).status_code for _ in range(3)] == [401, 401, 401]
    blocked = client.post("/api/auth/login", json={**wrong, "password": "neon-nights-2026"})
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["retry-after"]) <= 600
    assert "Try again in" in blocked.json()["detail"]


def test_the_window_slides(monkeypatch):
    clock = iter([0.0, 1.0, 2.0, 61.0])
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: next(clock))
    window = ratelimit.SlidingWindow(limit=2, window=60)
    assert [window.retry_after("a") for _ in range(3)] == [0, 0, 59]
    assert window.retry_after("a") == 0, "the first attempt has aged out"


def test_the_client_address_trusts_only_the_configured_proxies(monkeypatch):
    spoofed = "6.6.6.6, 203.0.113.9"  # the client wrote the first entry, Render the second
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 0)
    assert ratelimit.client_address(_request("10.0.0.1", spoofed)) == "10.0.0.1"
    monkeypatch.setattr(config, "TRUSTED_PROXY_HOPS", 1)
    assert ratelimit.client_address(_request("10.0.0.1", spoofed)) == "203.0.113.9"
    assert ratelimit.client_address(_request("10.0.0.1")) == "10.0.0.1"


def test_sign_ups_are_limited_too(state_dir, monkeypatch):
    monkeypatch.setattr(auth_router, "SIGN_UPS", ratelimit.SlidingWindow(limit=1, window=3600))
    client = _client()
    assert client.post("/api/auth/register", json=SIGN_UP).status_code == 201
    other = {**SIGN_UP, "email": "sam@neonnights.film"}
    assert client.post("/api/auth/register", json=other).status_code == 429


def test_an_unknown_email_is_checked_against_one_cached_hash(state_dir, monkeypatch):
    auth_router._dummy_hash.cache_clear()
    made = []
    real = security.hash_password
    monkeypatch.setattr(security, "hash_password", lambda password: made.append(1) or real(password))
    client = _client()
    for _ in range(3):
        assert client.post("/api/auth/login", json={"email": "nobody@x.film", "password": "whatever-123"}).status_code == 401
    assert len(made) == 1


def _user(email="ava@neonnights.film", user_id=None):
    return User(id=user_id or security.new_id("usr"), email=email, name="Ava",
                password_hash="x", created_at=security.iso(security.now()))


def test_the_same_email_cannot_be_created_twice(state_dir):
    auth_store.create_user(_user())
    with pytest.raises(auth_store.AlreadyExists):
        auth_store.create_user(_user())
    assert len(auth_store._read("cn_users")) == 1


def test_a_sign_up_that_loses_the_race_for_its_email_gets_a_409(state_dir, monkeypatch):
    real = auth_store.get_user_by_email
    monkeypatch.setattr(auth_store, "get_user_by_email", lambda email: None)  # both passed the early check
    client = _client()
    assert client.post("/api/auth/register", json=SIGN_UP).status_code == 201
    second = client.post("/api/auth/register", json={**SIGN_UP, "production_name": "Other"})
    assert second.status_code == 409
    monkeypatch.setattr(auth_store, "get_user_by_email", real)
    assert len(auth_store._read("cn_users")) == 1 and len(auth_store._read("cn_productions")) == 1


def test_productions_with_the_same_name_get_their_own_ids(state_dir):
    now = security.iso(security.now())
    ids = [auth_store.create_production(Production(id="PROJ_NEON_NIGHTS", name="Neon Nights",
                                                   owner_id=f"usr_{n}", created_at=now)).id for n in range(3)]
    assert ids == ["PROJ_NEON_NIGHTS", "PROJ_NEON_NIGHTS_2", "PROJ_NEON_NIGHTS_3"]
    owners = {row["id"]: row["owner_id"] for row in auth_store._read("cn_productions")}
    assert owners == {"PROJ_NEON_NIGHTS": "usr_0", "PROJ_NEON_NIGHTS_2": "usr_1", "PROJ_NEON_NIGHTS_3": "usr_2"}


def test_a_sign_up_that_fails_half_way_is_undone(state_dir, monkeypatch):
    real_save = supabase_client.save_state

    def broken(state):
        raise RuntimeError("state table missing")

    monkeypatch.setattr(supabase_client, "save_state", broken)
    with pytest.raises(RuntimeError):
        _client().post("/api/auth/register", json=SIGN_UP)
    for table in ("cn_users", "cn_productions", "cn_memberships", "cn_sessions"):
        assert auth_store._read(table) == [], table
    # Put back only this patch: monkeypatch.undo() would also undo state_dir's
    # and send the next sign-up to the real backend/.state/.
    monkeypatch.setattr(supabase_client, "save_state", real_save)
    assert _client().post("/api/auth/register", json=SIGN_UP).status_code == 201, "the email is free again"


def test_redeeming_an_invite_cannot_duplicate_an_account(state_dir, make_user, make_production, monkeypatch):
    owner, _ = make_user(email="owner@neonnights.film")
    make_production(owner)
    client = _client()
    token = security.new_token()
    from core.auth.models import Invite

    auth_store.save_invite(Invite(
        id="inv_1", project_id="PROJ_NEON_NIGHTS", token_fingerprint=security.fingerprint(token),
        created_by=owner.id, created_at=security.iso(security.now()), expires_at=security.expires_in(1), max_uses=5,
    ))
    body = {"token": token, "email": "grip@neonnights.film", "password": "grip-grip-2026", "name": "Sam"}
    assert client.post("/api/auth/join", json=body).status_code == 200
    monkeypatch.setattr(auth_store, "get_user_by_email", lambda email: None)
    assert client.post("/api/auth/join", json=body).status_code == 409
