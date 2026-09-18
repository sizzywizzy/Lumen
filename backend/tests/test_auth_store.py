"""The auth store's Supabase branch filters in the database.

Every lookup used to select("*") the whole table and match rows in Python, so
each request downloaded all sessions, users and memberships, and past
PostgREST's max-rows cap (1000 by default) a valid token stopped resolving.
The fake client below records the filters each query carried.
"""
import pytest

from core import config
from core.auth import security
from services import auth_store


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows, table, log):
        self._rows, self._table, self._log, self._filters = rows, table, log, []

    def select(self, columns="*"):
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def execute(self):
        self._log.append((self._table, list(self._filters)))
        return _Result([r for r in self._rows if all(r.get(c) == v for c, v in self._filters)])


class _Client:
    def __init__(self, tables):
        self.tables, self.log = tables, []

    def table(self, name):
        return _Query(self.tables.get(name, []), name, self.log)


NOW = "2026-09-15T00:00:00Z"


@pytest.fixture
def supabase(monkeypatch):
    token = security.new_token()
    client = _Client({
        "cn_users": [
            {"id": "usr_1", "email": "ava@neonnights.film", "name": "Ava", "password_hash": "x", "created_at": NOW},
            {"id": "usr_2", "email": "kai@neonnights.film", "name": "Kai", "password_hash": "x", "created_at": NOW},
        ],
        "cn_sessions": [
            {"token_fingerprint": security.fingerprint(token), "user_id": "usr_1",
             "created_at": NOW, "expires_at": security.expires_in(1)},
        ],
        "cn_memberships": [
            {"user_id": "usr_1", "project_id": "PROJ_A", "role": "owner", "created_at": NOW},
            {"user_id": "usr_2", "project_id": "PROJ_A", "role": "crew", "created_at": NOW},
            {"user_id": "usr_1", "project_id": "PROJ_B", "role": "producer", "created_at": NOW},
        ],
        "cn_invites": [
            {"id": "inv_1", "project_id": "PROJ_A", "token_fingerprint": "f1", "role": "crew",
             "created_by": "usr_1", "created_at": NOW, "expires_at": security.expires_in(1)},
            {"id": "inv_2", "project_id": "PROJ_B", "token_fingerprint": "f2", "role": "crew",
             "created_by": "usr_1", "created_at": NOW, "expires_at": security.expires_in(1)},
        ],
    })
    monkeypatch.setattr(config, "has_supabase", lambda: True)
    monkeypatch.setattr(auth_store, "_get_supabase", lambda: client)
    return client, token


def test_session_lookup_filters_by_fingerprint(supabase):
    client, token = supabase
    assert auth_store.get_session(token).user_id == "usr_1"
    assert client.log == [("cn_sessions", [("token_fingerprint", security.fingerprint(token))])]


def test_user_lookups_filter_by_id_and_normalised_email(supabase):
    client, _ = supabase
    assert auth_store.get_user("usr_2").name == "Kai"
    assert auth_store.get_user_by_email("  Ava@NeonNights.film ").id == "usr_1"
    assert auth_store.get_user_by_email("nobody@example.com") is None
    assert client.log[0] == ("cn_users", [("id", "usr_2")])
    assert client.log[1] == ("cn_users", [("email", "ava@neonnights.film")])


def test_membership_lookup_filters_on_both_keys(supabase):
    client, _ = supabase
    assert auth_store.get_membership("usr_1", "PROJ_B").role == "producer"
    assert auth_store.get_membership("usr_2", "PROJ_B") is None
    assert client.log[0] == ("cn_memberships", [("user_id", "usr_1"), ("project_id", "PROJ_B")])


def test_list_queries_filter_too(supabase):
    client, _ = supabase
    assert {m.project_id for m in auth_store.memberships_for_user("usr_1")} == {"PROJ_A", "PROJ_B"}
    assert {m.user_id for m in auth_store.memberships_for_project("PROJ_A")} == {"usr_1", "usr_2"}
    assert [i.id for i in auth_store.invites_for_project("PROJ_B")] == ["inv_2"]
    assert all(filters for _, filters in client.log), "an unfiltered query would download the table"


def test_whole_table_reads_are_local_only(supabase):
    with pytest.raises(RuntimeError):
        auth_store._read("cn_sessions")


# ----------------------------------------------- sign-up as one transaction --


class _Rpc:
    """`rpc(name, params)` on the fake client, recording what it was called with."""

    def __init__(self, raises=None, project_id="PROJ_NEON_NIGHTS"):
        self.calls, self._raises, self._project_id = [], raises, project_id

    def rpc(self, name, params):
        self.calls.append((name, params))
        if self._raises:
            raise self._raises
        return self

    def execute(self):
        return _Result({"project_id": self._project_id})


def _producer():
    from core.auth.models import Production, User

    user = User(id="usr_new", email="ava@neonnights.film", name="Ava",
                password_hash="digest", created_at=NOW)
    production = Production(id="PROJ_NEON_NIGHTS", name="Neon Nights", owner_id=user.id, created_at=NOW)
    return user, production


def test_a_sign_up_is_one_call_to_one_function(monkeypatch):
    """The account, production, membership and first state commit together."""
    client = _Rpc(project_id="PROJ_NEON_NIGHTS_2")
    monkeypatch.setattr(config, "has_supabase", lambda: True)
    monkeypatch.setattr(auth_store, "_get_supabase", lambda: client)
    user, production = _producer()

    stored = auth_store.register_producer(user, production, {"project_id": "PROJ_NEON_NIGHTS"})

    name, params = client.calls[0]
    assert name == auth_store.REGISTER_FUNCTION
    assert params["p_user"]["email"] == "ava@neonnights.film"
    assert params["p_project_id"] == "PROJ_NEON_NIGHTS" and params["p_name"] == "Neon Nights"
    assert stored.id == "PROJ_NEON_NIGHTS_2", "the function picked the free id and said which"


def test_a_taken_email_inside_the_function_reads_as_already_exists(monkeypatch):
    taken = RuntimeError('duplicate key value violates unique constraint "cn_users_email_key" (23505)')
    monkeypatch.setattr(config, "has_supabase", lambda: True)
    monkeypatch.setattr(auth_store, "_get_supabase", lambda: _Rpc(raises=taken))
    user, production = _producer()

    with pytest.raises(auth_store.AlreadyExists):
        auth_store.register_producer(user, production, {})


def test_a_database_without_the_function_still_signs_people_up(monkeypatch):
    """A deploy whose schema_auth.sql predates the function falls back to the
    four writes with the account removed again on failure, rather than 500."""
    missing = RuntimeError("PGRST202: Could not find the function public.cn_register_producer")
    monkeypatch.setattr(config, "has_supabase", lambda: True)
    monkeypatch.setattr(auth_store, "_get_supabase", lambda: _Rpc(raises=missing))
    user, production = _producer()
    fallback = []
    monkeypatch.setattr(auth_store, "_register_step_by_step",
                        lambda u, p, s: fallback.append(u.id) or p)

    assert auth_store.register_producer(user, production, {}).id == "PROJ_NEON_NIGHTS"
    assert fallback == ["usr_new"]


def test_any_other_database_error_is_not_swallowed(monkeypatch):
    monkeypatch.setattr(config, "has_supabase", lambda: True)
    monkeypatch.setattr(auth_store, "_get_supabase", lambda: _Rpc(raises=RuntimeError("connection refused")))
    user, production = _producer()

    with pytest.raises(RuntimeError, match="connection refused"):
        auth_store.register_producer(user, production, {})
