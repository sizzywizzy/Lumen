"""Distribution overrides are validated before a panel is built, so a bad
value is a 422 for the form rather than a KeyError minutes into a run."""
import pytest
from pydantic import ValidationError

from core.audience import personas as P
from core.orchestrator.state import GlobalState
from domains.audience.router import SimulationRequest
from domains.launch.agents import audience_sim


def test_unknown_values_and_dimensions_are_rejected_up_front():
    with pytest.raises(ValueError, match="pacing_tolerance value 'weird'"):
        P.build_panel(size=20, seed=1, distribution={"pacing_tolerance": {"weird": 1.0}})
    with pytest.raises(ValueError, match="dimension 'markets'"):
        P.build_panel(size=20, seed=1, distribution={"markets": {"US": 1.0}})
    with pytest.raises(ValueError, match="above zero"):
        P.build_panel(size=20, seed=1, distribution={"taste_profile": {"niche": 0.0}})
    with pytest.raises(ValueError, match="zero or more"):
        P.build_panel(size=20, seed=1, distribution={"taste_profile": {"niche": -1.0}})


def test_values_are_matched_regardless_of_case():
    cleaned = P.validate_distribution({"market": {"in": 0.7, "AE": 0.3}, "pacing_tolerance": {"HIGH": 1}})
    assert cleaned == {"market": {"IN": 0.7, "AE": 0.3}, "pacing_tolerance": {"high": 1.0}}


def test_the_request_model_reports_the_reason():
    with pytest.raises(ValidationError) as exc:
        SimulationRequest(distribution={"pacing_tolerance": {"weird": 1}})
    assert "weird" in str(exc.value) and "low, medium, high" in str(exc.value)
    assert SimulationRequest(distribution={}).distribution == {}
    assert SimulationRequest(distribution={"viewing_frequency": {"high": 2}}).distribution == {
        "viewing_frequency": {"high": 2.0}}


def test_a_valid_override_runs_end_to_end(offline):
    result = audience_sim.run_simulation(
        GlobalState(project_id="PROJ_T"), "A weary detective chases a blackmail ring.",
        panel_size=24, seed=3, markets=[], distribution={"viewing_frequency": {"high": 1.0}, "market": {"IN": 1.0}},
    )
    assert result["report"]["panel_size"] == 24
    assert {p["viewing_frequency"] for p in result["panel"]} == {"high"}
    assert {p["market"] for p in result["panel"]} == {"IN"}
