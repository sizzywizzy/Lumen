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
