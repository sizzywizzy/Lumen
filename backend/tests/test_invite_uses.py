"""An invite hands out exactly `max_uses` places, however the redemptions land.

`join` used to read `uses`, check it against `max_uses`, and save `uses + 1`
much later — after hashing a password, which takes long enough that two people
opening the last place at the same moment both passed the check and both got
in. The count is now claimed in one step before anything is written, and given
back when the redemption it was claimed for fails.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from core import config
from core.auth import security
from core.auth.models import Invite
from services import auth_store

TOKEN_FINGERPRINT = "fingerprint_of_the_invite_token"


def _invite(invite_id="inv_1", *, max_uses=1, uses=0, project="PROJ_NEON_NIGHTS", fingerprint=TOKEN_FINGERPRINT):
    return Invite(
        id=invite_id,
        project_id=project,
        token_fingerprint=fingerprint,
        created_by="usr_owner",
        created_at=security.iso(security.now()),
        expires_at=security.expires_in(24),
        max_uses=max_uses,
        uses=uses,
    )


# ------------------------------------------------------ claiming a use, alone --


def test_a_claim_counts_one_use_and_the_last_one_runs_out(state_dir):
    auth_store.save_invite(_invite(max_uses=2))

    assert auth_store.consume_invite_use("inv_1").uses == 1
    assert auth_store.consume_invite_use("inv_1").uses == 2
    assert auth_store.consume_invite_use("inv_1") is None, "the invite is spent"
    assert auth_store.get_invite("inv_1").uses == 2


def test_a_revoked_or_expired_invite_gives_out_nothing(state_dir):
    revoked = _invite("inv_revoked")
    revoked.revoked = True
    expired = _invite("inv_expired", fingerprint="another")
    expired.expires_at = security.expires_in(-1)
    auth_store.save_invite(revoked)
    auth_store.save_invite(expired)

    assert auth_store.consume_invite_use("inv_revoked") is None
    assert auth_store.consume_invite_use("inv_expired") is None
    assert auth_store.consume_invite_use("inv_missing") is None


def test_a_released_use_goes_back_on_the_invite(state_dir):
    auth_store.save_invite(_invite(max_uses=1))
    assert auth_store.consume_invite_use("inv_1") is not None

    auth_store.release_invite_use("inv_1")

    assert auth_store.get_invite("inv_1").uses == 0
    assert auth_store.consume_invite_use("inv_1") is not None, "the place is open again"
    auth_store.release_invite_use("inv_1")
    auth_store.release_invite_use("inv_1")
    assert auth_store.get_invite("inv_1").uses == 0, "a release never counts below zero"


def test_claims_from_many_threads_never_overshoot(state_dir):
    auth_store.save_invite(_invite(max_uses=3))

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: auth_store.consume_invite_use("inv_1"), range(8)))

    assert sum(claim is not None for claim in claims) == 3
    assert auth_store.get_invite("inv_1").uses == 3


# ------------------------------------------------- two people, one last place --


def test_two_people_redeeming_the_last_place_at_once_leaves_one_out(state_dir, make_user, make_production, monkeypatch):
    """Both requests read the invite before either writes — the interleaving
    that used to let both of them join."""
    from main import app

    owner, _ = make_user(email="owner@neonnights.film")
    make_production(owner)
    token = security.new_token()
    auth_store.save_invite(_invite(max_uses=1, fingerprint=security.fingerprint(token)))

    read_by_both = threading.Barrier(2, timeout=30)
    real_lookup = auth_store.get_invite_by_token

    def lookup_then_wait(raw_token):
        invite = real_lookup(raw_token)
        read_by_both.wait()  # hold each request until the other has read the same count
        return invite

    monkeypatch.setattr(auth_store, "get_invite_by_token", lookup_then_wait)

    def redeem(who):
        with TestClient(app) as client:
            return client.post("/api/auth/join", json={
                "token": token, "email": f"{who}@neonnights.film",
                "password": "grip-grip-2026", "name": who.title(),
            }).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(redeem, ["sam", "ren"]))

    assert codes == [200, 410], "one joins, the other is told the invite is spent"
    assert auth_store.get_invite("inv_1").uses == 1
    members = auth_store.memberships_for_project("PROJ_NEON_NIGHTS")
    assert len(members) == 2, "the owner plus exactly one new member"


def test_a_redemption_that_fails_hands_its_place_back(state_dir, make_user, make_production, monkeypatch):
    from main import app

    owner, _ = make_user(email="owner@neonnights.film")
    make_production(owner)
    token = security.new_token()
    auth_store.save_invite(_invite(max_uses=1, fingerprint=security.fingerprint(token)))

    def refuse(_membership):
        raise RuntimeError("memberships table missing")

    monkeypatch.setattr(auth_store, "save_membership", refuse)
    body = {"token": token, "email": "sam@neonnights.film", "password": "grip-grip-2026", "name": "Sam"}
    with pytest.raises(RuntimeError):
        TestClient(app).post("/api/auth/join", json=body)

    assert auth_store.get_invite("inv_1").uses == 0, "nobody joined, so nobody spent the place"


def test_opening_the_link_again_as_a_member_costs_nothing(state_dir, make_user, make_production, signed_in):
    from main import app

    owner, _ = make_user(email="owner@neonnights.film")
    make_production(owner)
    _, owner_token = signed_in(owner)
    token = security.new_token()
    auth_store.save_invite(_invite(max_uses=1, fingerprint=security.fingerprint(token)))

    response = TestClient(app).post(
        "/api/auth/join", json={"token": token}, headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 200
    assert auth_store.get_invite("inv_1").uses == 0


# ------------------------------------------------------- the Supabase branch --


class _Rows:
    """The slice of PostgREST the store uses: select/update with eq filters.

    `on_read` runs after each select, which is where a competing redemption
    lands in the real race.
    """

    def __init__(self, rows, on_read=None):
        self.rows, self.on_read, self.updates = rows, on_read, 0

    def table(self, _name):
        return _Query(self)


class _Query:
    def __init__(self, store):
        self._store, self._filters, self._payload, self._mode = store, [], None, "select"

    def select(self, _columns="*"):
        self._mode = "select"
        return self

    def update(self, payload):
        self._mode, self._payload = "update", payload
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def _matches(self, row):
        return all(row.get(column) == value for column, value in self._filters)

    def execute(self):
        if self._mode == "select":
            found = [dict(row) for row in self._store.rows if self._matches(row)]
            if self._store.on_read:
                self._store.on_read()
            return _Result(found)
        changed = []
        for row in self._store.rows:
            if self._matches(row):
                row.update(self._payload)
                changed.append(dict(row))
        self._store.updates += 1
        return _Result(changed)


class _Result:
    def __init__(self, data):
        self.data = data


def _supabase_invite(**overrides):
    return {"id": "inv_1", "project_id": "PROJ_A", "token_fingerprint": TOKEN_FINGERPRINT, "role": "crew",
            "created_by": "usr_owner", "created_at": security.iso(security.now()),
            "expires_at": security.expires_in(24), "max_uses": 2, "uses": 0, "revoked": False, "label": "",
            **overrides}


def test_on_supabase_a_claim_that_loses_the_race_tries_again(monkeypatch):
    """The update carries the count it read, so the loser changes no row,
    reads the new count and claims the place that is actually left."""
    rows = [_supabase_invite(max_uses=2)]
    competitor = iter([1])  # one competing redemption, between this read and its update

    def someone_else_claims_one():
        if next(competitor, None) is not None:
            rows[0]["uses"] += 1

    store = _Rows(rows, on_read=someone_else_claims_one)
    monkeypatch.setattr(config, "has_supabase", lambda: True)
    monkeypatch.setattr(auth_store, "_get_supabase", lambda: store)

    claimed = auth_store.consume_invite_use("inv_1")

    assert claimed is not None and claimed.uses == 2
    assert rows[0]["uses"] == 2, "the two places went to two redemptions, not three"
    assert store.updates == 2, "the first update matched no row and was retried"


def test_on_supabase_the_last_place_runs_out(monkeypatch):
    rows = [_supabase_invite(max_uses=1, uses=1)]
    store = _Rows(rows)
    monkeypatch.setattr(config, "has_supabase", lambda: True)
    monkeypatch.setattr(auth_store, "_get_supabase", lambda: store)

    assert auth_store.consume_invite_use("inv_1") is None
    assert store.updates == 0, "a spent invite is not written to at all"
