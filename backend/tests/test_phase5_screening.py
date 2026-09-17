"""Phase V screens the cut with the Audience Analyst's panel and cohorts.

The panel models taste and viewing habits only, the model scores each scene
once per cohort, and a live reply that is missing scores or scenes degrades
to the stated offline rules for just those scores."""
from core.audience import personas as panel_lib
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from domains.launch import audience_prompts
from domains.launch.agents import phase5_audience
from services import gemini_client, mock_db


def _screen(state=None):
    return Orchestrator().run(state or GlobalState(project_id="PROJ_NEON_NIGHTS"), start="phase5", end="phase5")


def _screening_calls(monkeypatch, answer):
    """Route the scene-screening calls to `answer(prompt, mock)`; every other
    call gets its offline mock. Returns the list of prompts sent."""
    sent = []

    def traced(prompt, *, tier="flash", system=None, mock=None, attempts_per_model=2):
        if system == audience_prompts.SCENE_SCREENING_SYSTEM:
            sent.append(prompt)
            return answer(prompt, mock), {"source": "gemini", "model": "flash-model"}
        return mock, {"source": "mock"}

    monkeypatch.setattr(gemini_client.config, "has_gemini", lambda: True)
    monkeypatch.setattr(gemini_client, "generate_json_traced", traced)
    monkeypatch.setattr(gemini_client, "generate_json", lambda prompt, **kw: kw.get("mock"))
    return sent


def test_the_offline_screening_is_the_demo_beat_without_gender(offline):
    state = _screen()
    report = state.audience_report
    assert report.viewer_count == 200 and report.screening_source == "offline"
    assert report.weakest_scene_id == "SCN_004"
    recut = [e for e in state.human_escalations if e.queue_item == "recut:SCN_004"]
    assert recut and recut[0].reason.startswith('Viewers under 25 drift during "The rooftop toast"')
    requests = [e for e in state.event_log if e["intent"] == "diagnose_engagement_anomaly"]
    assert requests[0]["payload"]["segment"]["dimension"] == "age_band"
    assert "gender" not in str(requests[0]["payload"]).lower()


def test_the_same_screenplay_gets_the_same_screening(offline):
    first, second = _screen().audience_report, _screen().audience_report
    assert first.heatmap == second.heatmap and first.tomatometer == second.tomatometer


def test_the_panel_is_the_seeded_one_with_no_sensitive_attributes(offline, monkeypatch):
    built = {}
    real = panel_lib.build_panel

    def spy(**kwargs):
        built["panel"], resolved = real(**kwargs)
        return built["panel"], resolved

    monkeypatch.setattr(panel_lib, "build_panel", spy)
    _screen()
    assert len(built["panel"]) == 200
    assert {"gender", "ethnicity", "religion", "income"}.isdisjoint(built["panel"][0])


def test_live_scene_scores_drive_the_heatmap(offline, monkeypatch):
    def answer(prompt, mock):
        rows = [dict(row, scene_scores={**row["scene_scores"], "SCN_002": 1.0}) for row in mock["cohorts"]]
        return {"cohorts": rows}

    sent = _screening_calls(monkeypatch, answer)
    report = _screen().audience_report
    assert sent and all('"SCN_006"' in prompt for prompt in sent), "every call lists every scene"
    assert report.screening_source == "live"
    assert report.weakest_scene_id == "SCN_002"
    assert report.weakest_scene_title == "The passenger's confession"


def test_a_ragged_live_reply_falls_back_score_by_score(offline, monkeypatch):
    def answer(prompt, mock):
        rows = mock["cohorts"]
        ragged = [{"cohort_id": rows[0]["cohort_id"], "scene_scores": {"SCN_001": "great", "SCN_005": 42}},
                  "not a cohort"]
        return {"cohorts": ragged + [dict(row, scene_scores={**row["scene_scores"], "SCN_001": 2.0}) for row in rows[1:]]}

    _screening_calls(monkeypatch, answer)
    state = _screen()
    report = state.audience_report
    assert report.screening_source == "mixed"
    assert all(1.0 <= score <= 10.0 for score in report.heatmap.values())
    assert set(report.heatmap) == {s["scene_id"] for s in mock_db.load("script")["scenes"]}


def test_a_screening_with_no_cohort_reply_still_scores_everyone(offline, monkeypatch):
    _screening_calls(monkeypatch, lambda prompt, mock: {"cohorts": []})
    report = _screen().audience_report
    assert report.viewer_count == 200 and report.screening_source == "mixed"


def test_viewer_quotes_name_an_age_and_market_not_a_gender(offline):
    viewers = [r for r in _screen().audience_report.reviews if r.kind == "viewer"]
    assert len(viewers) == 2
    assert all(r.source.startswith("A viewer aged ") and " in " in r.source for r in viewers)


def test_no_segment_is_flagged_when_nobody_drifts(offline, monkeypatch):
    monkeypatch.setattr(audience_prompts, "MOCK_UNDER_25_EXPOSITION", 0.0)
    state = _screen()
    assert not any(e.queue_item.startswith("recut:") for e in state.human_escalations)
    assert phase5_audience.verdict_for(state.audience_report.tomatometer) == state.audience_report.verdict
