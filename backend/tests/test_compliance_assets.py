"""Phase IV checks the licensed assets the scene breakdown lists, and only
those: a real screenplay no longer inherits the demo's music cue."""
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from domains.production import prompts
from services import gemini_client, mock_db


def _music_checked(state: GlobalState) -> list[dict]:
    requests = [e for e in state.event_log if e["intent"] == "verify_regional_compliance"]
    return [element for element in requests[0]["payload"]["elements_to_check"] if element["type"] == "music"]


def test_the_demo_breakdown_carries_its_track_to_compliance(offline):
    state = Orchestrator().run(GlobalState(project_id="PROJ_NEON_NIGHTS"), start="phase3", end="phase4")
    assert _music_checked(state) == [
        {"type": "music", "tags": [], "scene_id": "SCN_004", "asset_id": "TRK_992_INDIE_ROCK"}]


def test_a_real_screenplay_checks_only_its_own_cues(offline, monkeypatch):
    venue = mock_db.load("venues")[0]["location_type"]
    breakdown = {"scenes": [
        {"scene_id": "SCN_001", "location_type": venue, "tags": ["Night"], "characters_needed": ["ROLE_LEAD"],
         "assets": ["trk_992_indie_rock", "TRK_INVENTED_BY_A_MODEL", 7]},
        {"scene_id": "SCN_002", "location_type": venue, "tags": ["dialogue"]},
    ]}

    def fake(prompt, *, tier="flash", system=None, mock=None):
        return breakdown if system == prompts.BREAKDOWN_SYSTEM else mock

    monkeypatch.setattr(gemini_client, "generate_json", fake)
    state = GlobalState(project_id="PROJ_REAL", script_context={"raw_text": "INT. DINER - DAY"})
    state.role_requirements = {"ROLE_LEAD": {"name": "Jo"}}
    state = Orchestrator().run(state, start="phase3", end="phase4")

    scenes = state.script_context["scenes"]
    assert [s["assets"] for s in scenes] == [["TRK_992_INDIE_ROCK"], []]
    assert [e["scene_id"] for e in _music_checked(state)] == ["SCN_001"]


def test_a_breakdown_without_cues_checks_no_music(offline):
    scenes = [dict(s, assets=[]) for s in mock_db.load("script")["scenes"]]
    state = GlobalState(project_id="PROJ_REAL", script_context={"scenes": scenes})
    state = Orchestrator().run(state, start="phase4", end="phase4")
    assert _music_checked(state) == []


def test_a_blocked_territory_is_explained_in_a_sentence(offline):
    state = Orchestrator().run(GlobalState(project_id="PROJ_NEON_NIGHTS"), start="phase3", end="phase4")
    reason = next(e.reason for e in state.human_escalations if e.queue_item == "compliance:UAE")
    assert reason == ('Release in the UAE is blocked: "The rooftop toast" is flagged for alcohol reference, '
                      "which its rules do not allow. To clear it, replace the audio with a clean version.")
