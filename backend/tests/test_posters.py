"""The production's poster.

agent_visual makes one per screenplay after a pipeline run: Gemini writes the
tagline and picks the colours, and Lumen draws the art as an SVG in a style
drawn at random. A new poster on request never repeats the style it replaces,
the page says where the tagline came from, a spoiler never reaches it, members
can see it and only producers can ask for another. Runs work inline here
(conftest.background_work_runs_inline), so each request below has finished
when it returns.
"""
import base64
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
from services import auth_store, llm, supabase_client

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


def _unsafe(svg):
    """Lettering to misspell, or anything in the art that could run."""
    return [el for el in svg.iter() if el.tag.rsplit("}", 1)[-1] in ("text", "script", "foreignObject")]


def test_an_offline_poster_says_where_its_tagline_came_from(state_dir, offline):
    _seed()
    record = posters.run(PROJECT, "usr_1")

    assert record["image_mime"] == "image/svg+xml"
    assert not _unsafe(ElementTree.fromstring(base64.b64decode(record["image_base64"])))
    shown = posters.status(PROJECT)
    assert shown["status"] == "ready"
    assert shown["poster"]["written_by"] is None
    assert shown["poster"]["fallback_reason"] == "no_api_key"
    assert shown["poster"]["tagline"] == "Every city keeps a secret."
    intents = [e["intent"] for e in supabase_client.load_state(PROJECT).event_log]
    assert intents == ["verify_brand_safety", "brand_safety_result", "asset_status_update"]


def test_a_new_poster_never_repeats_the_style_it_replaces(state_dir, offline):
    _seed()
    styles = [posters.run(PROJECT, "usr_1")["style"]["key"] for _ in range(12)]
    assert all(a != b for a, b in zip(styles, styles[1:]))
    assert len(set(styles)) > 2, "the style is drawn at random, not swapped between two"


@pytest.mark.parametrize("style", prompts.POSTER_STYLES, ids=lambda style: style["key"])
def test_every_style_draws_clean_art(style):
    art = poster_artist.sketch_svg(["#101820", "#2b4a6f", "#f2c14e"], style["sketch"], seed=7)
    assert not _unsafe(ElementTree.fromstring(art))


def test_every_offline_concept_clears_pr_review():
    """The offline concept is what stands in after a blocked draft, so it must pass."""
    state = GlobalState(project_id=PROJECT)
    for genre in GENRES:
        concept = poster_artist._offline_concept({"title": "Neon Nights", "genre": genre})
        request = make_envelope("agent_visual", "agent_pr_risk", "verify_brand_safety", {
            "asset_id": poster_artist.ASSET_ID, "caption": concept["tagline"],
        })
        assert pr_risk_check(state, request)["status"] == "APPROVED", (genre, concept)


def test_a_spoiler_is_redrafted_and_never_reaches_the_poster(state_dir, offline, monkeypatch):
    _seed()
    prompts_sent = []

    def spoiler(prompt, **kwargs):
        prompts_sent.append(prompt)
        draft = {"tagline": "The detective dies at the end", "scene": "an open grave in the rain",
                 "alt_text": "a grave", "palette": ["#000000", "#333333", "#ffffff"]}
        return draft, {"live": True, "source": "gemini", "model": "flash"}

    monkeypatch.setattr(llm, "generate_json_traced", spoiler)
    record = posters.run(PROJECT, "usr_1")

    assert len(prompts_sent) == config.MAX_ASSET_REGENERATIONS
    assert "blocked your last draft" in prompts_sent[-1]
    assert record["concept"]["tagline"] == "Every city keeps a secret."
    assert record["provenance"]["concept"]["reason"] == "pr_blocked"
    intents = [e["intent"] for e in supabase_client.load_state(PROJECT).event_log]
    assert intents.count("brand_safety_result") == config.MAX_ASSET_REGENERATIONS


def test_a_written_concept_colours_the_art_and_is_credited(state_dir, offline, monkeypatch):
    _seed()
    systems = []

    def drafted(prompt, **kwargs):
        systems.append(kwargs.get("system"))
        return ({"tagline": "The city never forgets.", "palette": ["#101820", "#2b4a6f", "#f2c14e"]},
                {"live": True, "source": "gemini", "model": "gemini-3.6-flash"})

    monkeypatch.setattr(llm, "generate_json_traced", drafted)
    record = posters.run(PROJECT, "usr_1")

    assert systems == [prompts.POSTER_SYSTEM], "one text request, and nothing else"
    assert record["image_mime"] == "image/svg+xml"
    assert "#f2c14e" in base64.b64decode(record["image_base64"]).decode("utf-8")
    shown = posters.status(PROJECT)["poster"]
    assert shown["tagline"] == "The city never forgets."
    assert shown["written_by"] == "gemini-3.6-flash" and shown["fallback_reason"] is None


def test_a_pipeline_run_makes_one_poster_per_screenplay(state_dir, offline, signed_in, make_production):
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


def test_one_poster_at_a_time_and_a_failure_is_reported(state_dir, offline, signed_in, make_production, monkeypatch):
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
