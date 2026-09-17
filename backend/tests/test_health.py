"""/api/health is the host's health gate (healthCheckPath in render.yaml).

A container whose Supabase settings are wrong boots fine, so health has to
report the state store rather than only that the process is up — otherwise a
broken deploy goes live and 500s on every real request.
"""
import pytest
from fastapi.testclient import TestClient

import main
from core import config
from services import supabase_client


@pytest.fixture
def client(state_dir):
    return TestClient(main.app)


def test_health_ok_when_the_store_is_readable(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["phases"] == ["phase1", "phase2", "phase3", "phase4", "phase5", "phase6"]
    assert body["store"] == {"backend": "local", "reachable": True}


def test_health_is_503_when_the_store_cannot_be_read(client, monkeypatch):
    monkeypatch.setattr(
        supabase_client, "store_status",
        lambda: {"backend": "supabase", "reachable": False, "detail": "APIError: relation does not exist"},
    )
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["store"]["detail"].startswith("APIError")


def test_store_status_reports_a_supabase_misconfiguration(monkeypatch, tmp_path):
    """LUMEN_STATE_BACKEND=supabase with no credentials — what render.yaml sets
    when SUPABASE_URL is left blank. config.has_supabase() raises; health says so."""
    monkeypatch.setattr(config, "LOCAL_STATE_DIR", tmp_path)
    monkeypatch.setattr(
        config, "has_supabase",
        lambda: (_ for _ in ()).throw(RuntimeError("LUMEN_STATE_BACKEND=supabase but SUPABASE_URL/SUPABASE_KEY are not set.")),
    )
    status = supabase_client.store_status()
    assert status["reachable"] is False
    assert status["backend"] == "supabase"
    assert "SUPABASE_URL" in status["detail"]


def test_store_status_reports_an_unreachable_supabase(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "has_supabase", lambda: True)

    class Boom:
        def table(self, _name):
            raise ConnectionError("getaddrinfo failed")

    monkeypatch.setattr(supabase_client, "_get_supabase", lambda: Boom())
    status = supabase_client.store_status()
    assert status == {"backend": "supabase", "reachable": False,
                      "detail": "ConnectionError: getaddrinfo failed"}


def test_store_status_probes_a_readable_supabase(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_STATE_DIR", tmp_path)
    monkeypatch.setattr(config, "has_supabase", lambda: True)
    seen = {}

    class Table:
        def select(self, columns):
            seen["columns"] = columns
            return self

        def limit(self, count):
            seen["limit"] = count
            return self

        def execute(self):
            return type("Result", (), {"data": []})()

    class Ok:
        def table(self, name):
            seen["table"] = name
            return Table()

    monkeypatch.setattr(supabase_client, "_get_supabase", lambda: Ok())
    assert supabase_client.store_status() == {"backend": "supabase", "reachable": True}
    # The cheapest read the store allows: one indexed column, at most one row.
    assert seen == {"table": "global_state", "columns": "project_id", "limit": 1}


def test_store_status_reports_an_unwritable_local_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "has_supabase", lambda: False)
    monkeypatch.setattr(config, "LOCAL_STATE_DIR", tmp_path / "nope")
    monkeypatch.setattr(
        type(tmp_path), "mkdir",
        lambda *a, **k: (_ for _ in ()).throw(PermissionError("read-only file system")),
    )
    status = supabase_client.store_status()
    assert status["reachable"] is False
    assert status["backend"] == "local"
    assert "PermissionError" in status["detail"]


def test_boot_fails_on_a_supabase_misconfiguration(monkeypatch):
    """The lifespan gate: uvicorn runs it, so the deploy fails loudly instead
    of going live and returning 500 on every request."""
    monkeypatch.setattr(
        config, "has_supabase",
        lambda: (_ for _ in ()).throw(RuntimeError("LUMEN_STATE_BACKEND=supabase but SUPABASE_URL/SUPABASE_KEY are not set.")),
    )
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        with TestClient(main.app):
            pass


def test_boot_succeeds_when_configuration_is_sound(state_dir):
    with TestClient(main.app) as client:
        assert client.get("/api/health").status_code == 200
