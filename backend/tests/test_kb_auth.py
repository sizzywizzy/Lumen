"""The actor knowledge-base routes are shared across productions, so they are
not membership-scoped, but they must still require a signed-in account."""
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.mark.parametrize("method, path, body", [
    ("POST", "/api/casting/actors/ingest", {"actor_ids": [6193]}),
    ("POST", "/api/casting/actors/embeddings", {}),
    ("GET", "/api/casting/actors/search?character_description=weary%20detective", None),
])
def test_actor_kb_routes_reject_anonymous_callers(state_dir, method, path, body):
    response = TestClient(app).request(method, path, json=body)
    assert response.status_code == 401


def test_actor_search_runs_for_a_signed_in_user(state_dir, signed_in, monkeypatch):
    monkeypatch.setattr("services.casting_kb.matching.match_actors", lambda *args, **kwargs: [])
    _, token = signed_in()
    response = TestClient(app).get(
        "/api/casting/actors/search",
        params={"character_description": "weary detective"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"matches": []}
