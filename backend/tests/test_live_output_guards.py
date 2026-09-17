"""A malformed live model reply degrades to the offline answer instead of
turning the run into a 500. Each test hands the phase agents replies of the
wrong shape and checks the phase completes with sane values."""
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from domains.casting import prompts as casting_prompts
from domains.launch import prompts as launch_prompts
from services import gemini_client


def _answer_with(monkeypatch, answers: dict):
    """Route each system prompt to a canned reply; every other call gets its mock."""
    def fake(prompt, *, tier="flash", system=None, mock=None):
        return answers.get(system, mock)
    monkeypatch.setattr(gemini_client, "generate_json", fake)


def _fresh():
    return GlobalState(project_id="PROJ_NEON_NIGHTS")


def test_phase1_normalises_a_ragged_mandate(offline, monkeypatch):
    _answer_with(monkeypatch, {casting_prompts.PROFILER_SYSTEM: {
        "role_requirements": {"role_lead": {"name": "", "description": "A weary ex-detective", "type": "Lead"},
                              "ROLE_VILLAIN": {"name": "Nobody"}},
        "scoring_weights": {"W_A": 50, "W_H": 20, "W_PR": 20, "W_B": 10},
    }})
    state = Orchestrator().run(_fresh(), start="phase1", end="phase1")
    assert set(state.role_requirements) == {"ROLE_LEAD", "ROLE_ANTAG"}
    lead = state.role_requirements["ROLE_LEAD"]
    assert (lead["name"], lead["type"], lead["description"]) == ("Mara Voss", "lead", "A weary ex-detective")
    assert state.scoring_weights == {"W_A": 0.5, "W_H": 0.2, "W_PR": 0.2, "W_B": 0.1}


def test_phase1_survives_replies_of_the_wrong_shape(offline, monkeypatch):
    _answer_with(monkeypatch, {
        casting_prompts.PROFILER_SYSTEM: ["not", "a", "mapping"],
        casting_prompts.PR_SHIELD_SYSTEM: {"pr_score": "high", "red_flag": "false", "reason": None},
    })
    state = Orchestrator().run(_fresh(), start="phase1", end="phase1")
    assert state.role_requirements["ROLE_ANTAG"]["name"] == "Silas Kade"
    assert state.scoring_weights == {"W_A": 0.4, "W_H": 0.2, "W_PR": 0.2, "W_B": 0.2}
    assert state.candidates and all(0 <= c.scores["pr"] <= 100 for c in state.candidates)
    assert not any(c.metadata.get("disqualify_code") == "pr_risk" for c in state.candidates)


def test_a_red_flag_spelt_as_a_string_still_disqualifies(offline, monkeypatch):
    _answer_with(monkeypatch, {casting_prompts.PR_SHIELD_SYSTEM: {
        "pr_score": 12, "red_flag": "true", "reason": "a live lawsuit"}})
    state = Orchestrator().run(_fresh(), start="phase1", end="phase1")
    assert all(c.metadata.get("disqualify_code") == "pr_risk" for c in state.candidates)
    assert "a live lawsuit" in state.candidates[0].disqualify_reason


def test_phase2_scores_with_a_broken_review_and_missing_weights(offline, monkeypatch):
    _answer_with(monkeypatch, {casting_prompts.AUDITION_SYSTEM: {
        "audition_score": "excellent", "qualitative_review": ["not", "prose"]}})
    state = Orchestrator().run(_fresh(), start="phase1", end="phase1")
    state.scoring_weights = {"W_A": "lots"}
    state = Orchestrator().run(state, start="phase2", end="phase2")
    scored = state.active_candidates()
    assert scored and all(0 <= c.scores["audition"] <= 100 and 0 <= c.scores["composite"] <= 100 for c in scored)
    assert all(c.metadata["qualitative_review"] for c in scored)
    assert any(c.status == "LOCKED" for c in scored)


def test_phase5_escalates_a_recut_even_when_the_diagnosis_is_junk(offline, monkeypatch):
    _answer_with(monkeypatch, {launch_prompts.RECUT_SYSTEM: {"root_cause": None, "predicted_lift": "big"}})
    state = Orchestrator().run(_fresh(), start="phase5", end="phase5")
    recut = [e for e in state.human_escalations if e.queue_item.startswith("recut:")]
    assert recut and "exposition overload" in recut[0].reason and "+6" in recut[0].reason


def test_phase6_builds_a_campaign_from_replies_of_the_wrong_shape(offline, monkeypatch):
    _answer_with(monkeypatch, {
        launch_prompts.STRATEGIST_SYSTEM: "no plan",
        launch_prompts.VISUAL_SYSTEM: {},
        launch_prompts.COPYWRITER_SYSTEM: {"posts": "none", "press_release": None},
    })
    state = Orchestrator().run(_fresh(), start="phase6", end="phase6")
    assert [a.asset_id for a in state.marketing_assets] == ["AST_REEL_0001", "AST_MEME_0001", "AST_POSTER_0001"]
    assert all(a.status == "SCHEDULED" for a in state.marketing_assets)
    meme = next(a for a in state.marketing_assets if a.asset_id == "AST_MEME_0001")
    assert meme.content["caption"] and meme.content["attempt"] == 2


def test_copy_without_a_caption_is_dropped_and_the_release_kept(offline, monkeypatch):
    _answer_with(monkeypatch, {launch_prompts.COPYWRITER_SYSTEM: {
        "posts": [{"platform": "tiktok", "caption": ""},
                  {"platform": "x", "caption": "The city remembers.", "hashtags": ["#Neon", 7, ""]},
                  "junk"],
        "press_release": {"headline": "Neon Nights announced", "body": 42},
    }})
    state = Orchestrator().run(_fresh(), start="phase6", end="phase6")
    copy = [a for a in state.marketing_assets if a.type == "copy"]
    assert [a.content["caption"] for a in copy] == ["The city remembers."]
    assert copy[0].content["hashtags"] == ["#Neon", "7"]
    press = next(a for a in state.marketing_assets if a.type == "press_release")
    assert (press.content["headline"], press.content["body"]) == ("Neon Nights announced", "42")


def test_scouted_candidates_are_held_to_the_scripts_roles(offline, monkeypatch):
    """A live scout may name a role the script does not have, or give its
    numbers as prose; neither may reach synthesis as a phantom lock or a crash."""
    from core import config
    from services import tavily_client

    reply = {"candidates": [
        {"name": "Ada Phantom", "role_id": "ROLE_SIDEKICK", "source": 1,
         "metadata": {"quote_usd": "$20,000", "followers": "lots"}},
        {"name": "Lower Case", "role_id": "role_antag", "metadata": {"quote_usd": 9000, "followers": 1200}},
        {"id": "DUP", "name": "First Dup"}, {"id": "DUP", "name": "Second Dup"},
        "not a candidate",
    ]}
    page = {"title": "Local talent", "url": "https://example.org/roster",
            "content": "Ada Phantom, Lower Case, First Dup and Second Dup are on the roster."}
    monkeypatch.setattr(config, "has_gemini", lambda: True)
    monkeypatch.setattr(config, "has_tavily", lambda: True)
    monkeypatch.setattr(tavily_client, "search", lambda query, max_results=4: {"results": [page]})
    monkeypatch.setattr(gemini_client, "generate_json", lambda prompt, **kwargs: kwargs.get("mock"))
    monkeypatch.setattr(gemini_client, "generate_json_traced",
                        lambda prompt, **kwargs: (reply, {"source": "gemini", "model": "flash"}))
    state = Orchestrator().run(_fresh(), start="phase1", end="phase2")

    roles = set(state.role_requirements)
    assert {c.role_id for c in state.candidates} <= roles
    by_name = {c.name: c for c in state.candidates}
    assert set(by_name) == {"Ada Phantom", "Lower Case", "First Dup", "Second Dup"}
    assert by_name["Lower Case"].role_id == "ROLE_ANTAG"
    assert by_name["Ada Phantom"].metadata["followers_estimated"] is True
    assert by_name["Ada Phantom"].metadata["quote_usd"] == 20000.0, "a fee written as \"$20,000\" is read"
    assert len({c.id for c in state.candidates}) == 4, "duplicate ids are renumbered"
    locked = [e.queue_item for e in state.human_escalations if e.queue_item.startswith("cast_signoff:")]
    assert {item.split(":", 1)[1] for item in locked} <= roles


def test_a_zero_budget_rules_everyone_out_instead_of_crashing(offline):
    from core.orchestrator.state import BudgetState

    state = _fresh()
    state.budget_state = BudgetState(cap=0)
    state = Orchestrator().run(state, start="phase1", end="phase1")
    assert state.candidates and all(c.scores["budget"] == 0 for c in state.candidates)
