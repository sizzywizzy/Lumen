"""The production's poster.

agent_visual paints one per screenplay after a pipeline run, in a style drawn at
random, and a new poster on request never repeats the style it replaces. With
no model it is an SVG sketch that says so, a spoiler never reaches it, members
can see it and only producers can ask for another. Runs paint inline here
(conftest.posters_paint_inline), so each request below has finished when it returns.
"""
import base64
import io
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from core import config
from core.auth import security
from core.auth.models import Membership
from core.messaging.envelope import make_envelope
from core.orchestrator.state import GlobalState
from domains.launch import posters, prompts
from domains.launch.agents import poster_artist
from domains.launch.agents.phase6_marketing import pr_risk_check
from main import app
from services import auth_store, gemini_client, supabase_client

PROJECT = "PROJ_NEON_NIGHTS"
GENRES = ("neo-noir thriller", "horror", "sci-fi", "romance", "comedy", "western", "fantasy", "action", "drama", "")


def _seed(fingerprint="draft_one"):
    supabase_client.save_state(GlobalState(project_id=PROJECT, script_context={
        "title": "Neon Nights", "genre": "neo-noir thriller", "fingerprint": fingerprint,
    }))


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _join(user, role):
    auth_store.save_membership(Membership(
        user_id=user.id, project_id=PROJECT, role=role, created_at=security.iso(security.now()),
    ))


def test_an_offline_poster_is_a_sketch_that_says_so(state_dir, offline):
    _seed()
    record = posters.run(PROJECT, "usr_1")

    assert record["image_mime"] == "image/svg+xml"
    svg = ElementTree.fromstring(base64.b64decode(record["image_base64"]))
    # no lettering to misspell, and nothing in it that could run
    assert not [el for el in svg.iter() if el.tag.rsplit("}", 1)[-1] in ("text", "script", "foreignObject")]
    shown = posters.status(PROJECT)
    assert shown["status"] == "ready"
    assert shown["poster"]["painted_by"] is None
    assert shown["poster"]["sketch_reason"] == "no_api_key"
    assert shown["poster"]["tagline"] == "Every city keeps a secret."
    intents = [e["intent"] for e in supabase_client.load_state(PROJECT).event_log]
    assert intents == ["verify_brand_safety", "brand_safety_result", "asset_status_update"]


def test_a_new_poster_never_repeats_the_style_it_replaces(state_dir, offline):
    _seed()
    styles = [posters.run(PROJECT, "usr_1")["style"]["key"] for _ in range(12)]
    assert all(a != b for a, b in zip(styles, styles[1:]))
    assert len(set(styles)) > 2, "the style is drawn at random, not swapped between two"


@pytest.mark.parametrize("style", prompts.POSTER_STYLES, ids=lambda style: style["key"])
def test_every_offline_concept_clears_pr_review(style):
    """The offline concept is what stands in after a blocked draft, so it must pass."""
    state = GlobalState(project_id=PROJECT)
    for genre in GENRES:
        concept = poster_artist._offline_concept({"title": "Neon Nights", "genre": genre}, style)
        request = make_envelope("agent_visual", "agent_pr_risk", "verify_brand_safety", {
            "asset_id": poster_artist.ASSET_ID, "caption": f"{concept['tagline']} {concept['scene']}",
        })
        assert pr_risk_check(state, request)["status"] == "APPROVED", (genre, concept)


def test_a_spoiler_is_redrafted_and_never_reaches_the_poster(state_dir, offline, monkeypatch):
    _seed()
    prompts_sent = []

    def spoiler(prompt, **kwargs):
        prompts_sent.append(prompt)
        draft = {"tagline": "The detective dies at the end", "scene": "an open grave in the rain",
                 "alt_text": "a grave", "palette": ["#000000", "#333333", "#ffffff"]}
        return draft, {"source": "gemini", "model": "flash"}

    monkeypatch.setattr(gemini_client, "generate_json_traced", spoiler)
    record = posters.run(PROJECT, "usr_1")

    assert len(prompts_sent) == config.MAX_ASSET_REGENERATIONS
    assert "blocked your last draft" in prompts_sent[-1]
    assert record["concept"]["tagline"] == "Every city keeps a secret."
    assert record["provenance"]["concept"]["reason"] == "pr_blocked"
    intents = [e["intent"] for e in supabase_client.load_state(PROJECT).event_log]
    assert intents.count("brand_safety_result") == config.MAX_ASSET_REGENERATIONS


def test_a_painted_poster_is_shrunk_and_credited_to_its_model(state_dir, offline, monkeypatch):
    image_lib = pytest.importorskip("PIL.Image")
    _seed()
    canvas = io.BytesIO()
    image_lib.effect_noise((1100, 1650), 48).convert("RGB").save(canvas, "PNG")  # a model-sized PNG, over MAX_EDGE
    prompts_sent = []

    def painted(prompt, **kwargs):
        prompts_sent.append(prompt)
        return canvas.getvalue(), "image/png", {"source": "gemini", "model": "gemini-3.1-flash-image"}

    monkeypatch.setattr(gemini_client, "generate_image_traced", painted)
    record = posters.run(PROJECT, "usr_1")

    assert record["image_mime"] == "image/jpeg"
    with image_lib.open(io.BytesIO(base64.b64decode(record["image_base64"]))) as stored:
        assert max(stored.size) == poster_artist.MAX_EDGE
    assert posters.status(PROJECT)["poster"]["painted_by"] == "gemini-3.1-flash-image"
    assert "No text of any kind" in prompts_sent[0]
    assert "real or recognisable person" in prompts_sent[0]


def test_a_pipeline_run_paints_one_poster_per_screenplay(state_dir, offline, signed_in, make_production):
    user, token = signed_in()
    make_production(user)
    client = TestClient(app)

    def run():
        assert client.post("/api/pipeline/run", json={"project_id": PROJECT}, headers=_auth(token)).status_code == 202
        return client.get(f"/api/launch/poster/{PROJECT}", headers=_auth(token)).json()

    def drop(text):
        response = client.post(f"/api/production/script/{PROJECT}", headers=_auth(token),
                               json={"filename": "neon-nights.fountain", "text": text})
        assert response.status_code == 200

    client.post("/api/pipeline/init", json={"project_id": PROJECT}, headers=_auth(token))
    drop("INT. CAB - NIGHT\nMara drives through the rain.")
    first = run()
    assert first["status"] == "ready"
    image = client.get(f"/api/launch/poster/{PROJECT}/image", headers=_auth(token))
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/svg+xml")
    assert image.headers["x-content-type-options"] == "nosniff"

    assert run()["poster"]["poster_id"] == first["poster"]["poster_id"], "a re-run keeps the draft's poster"
    drop("INT. DINER - DAY\nA second draft.")
    assert run()["poster"]["poster_id"] != first["poster"]["poster_id"], "a new draft gets its own poster"


def test_members_see_the_poster_and_only_producers_ask_for_another(state_dir, offline, signed_in, make_user, make_production):
    owner, owner_token = signed_in()
    make_production(owner)
    crew, _ = make_user(email="grip@neonnights.film", name="Sam Grip")
    _join(crew, "crew")
    _, crew_token = signed_in(crew)
    outsider, _ = make_user(email="someone@elsewhere.film", name="Someone Else")
    _, outsider_token = signed_in(outsider)
    _seed()
    client = TestClient(app)

    assert client.post(f"/api/launch/poster/{PROJECT}", headers=_auth(owner_token)).status_code == 202
    first = client.get(f"/api/launch/poster/{PROJECT}", headers=_auth(crew_token)).json()["poster"]
    assert client.get(f"/api/launch/poster/{PROJECT}/image", headers=_auth(crew_token)).status_code == 200
    assert client.post(f"/api/launch/poster/{PROJECT}", headers=_auth(crew_token)).status_code == 403
    assert client.get(f"/api/launch/poster/{PROJECT}", headers=_auth(outsider_token)).status_code == 404
    assert client.get(f"/api/launch/poster/{PROJECT}/image", headers=_auth(outsider_token)).status_code == 404

    again = client.post(f"/api/launch/poster/{PROJECT}", headers=_auth(owner_token)).json()["poster"]
    assert again["poster_id"] != first["poster_id"]
    assert again["style"]["key"] != first["style"]["key"]


def test_one_poster_paints_at_a_time_and_a_failure_is_reported(state_dir, offline, signed_in, make_production, monkeypatch):
    user, token = signed_in()
    make_production(user)
    _seed()
    client = TestClient(app)

    posters._ACTIVE.add(PROJECT)
    assert client.post(f"/api/launch/poster/{PROJECT}", headers=_auth(token)).status_code == 409
    assert client.get(f"/api/launch/poster/{PROJECT}", headers=_auth(token)).json()["status"] == "painting"
    posters._ACTIVE.discard(PROJECT)

    def broken(*args, **kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(poster_artist, "paint", broken)
    assert client.post(f"/api/launch/poster/{PROJECT}", headers=_auth(token)).status_code == 202
    shown = client.get(f"/api/launch/poster/{PROJECT}", headers=_auth(token)).json()
    assert shown["status"] == "failed"
    assert "model down" in shown["error"]
    assert shown["poster"] is None


def test_a_poster_problem_never_fails_the_pipeline_run(state_dir, offline, signed_in, make_production, monkeypatch):
    user, token = signed_in()
    make_production(user)

    def missing_table(*args, **kwargs):
        raise RuntimeError('relation "cn_posters" does not exist')

    monkeypatch.setattr(posters.poster_store, "get", missing_table)
    client = TestClient(app)
    response = client.post("/api/pipeline/run", json={"project_id": PROJECT}, headers=_auth(token))
    assert response.status_code == 202
    assert client.get(f"/api/pipeline/status/{PROJECT}", headers=_auth(token)).json()["status"] == "complete"
    assert supabase_client.load_state(PROJECT).candidates
