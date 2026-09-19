"""The structured-output experiment, and the counter it reads.

Two halves. `core/llm_output.py` counts the repairs the agents already make to
live replies, which is the product's own record of how often a reply arrives in
the wrong shape. `eval/structured` takes the prompts Lumen really sends and asks
each one twice, plain and schema-enforced, on one model.

What is checked here is mostly that the harness cannot flatter itself: that a
rate-limited pair is excluded rather than averaged in, and that a clean baseline
is reported as a clean baseline instead of as a gain.
"""
import json

import pytest

from core import config, llm_output
from eval.structured import capture
from eval.structured import run as harness
from services import llm


# ------------------------------------------------ counting what gets repaired --


def test_nothing_is_counted_unless_someone_is_watching():
    """The counter runs in production on every coercion, so the cost outside an
    experiment has to be one ContextVar read and nothing else."""
    assert llm_output.tally() is None
    llm_output.number("not a number", 5)  # no error, no bookkeeping
    assert llm_output.tally() is None


def test_the_kinds_of_repair_are_counted_apart():
    """Falling back to a default, clamping a number and clipping a string are
    three different ways a reply can be wrong, and lumping them together would
    hide which one a schema could actually prevent."""
    with llm_output.watching() as repairs:
        llm_output.number("high", 50, 0, 100)           # nothing usable: default
        llm_output.number(140, 50, 0, 100)              # a number, out of range
        llm_output.text("x" * 300, "fallback", 200)      # a string, past its limit
        llm_output.mapping(["not", "a", "map"], {})      # the wrong container
        llm_output.listing([1, 2])                       # already right
        llm_output.boolean("yes")                        # a spelling it accepts
        llm_output.text("fine", "fallback", 200)          # already right
    assert repairs == {"checked": 7, "repaired": 2, "clamped": 1, "clipped": 1}


def test_a_field_read_as_words_is_one_field_not_two():
    """`words` is `text` plus a rename, and counting it twice would inflate the
    denominator of every rate in the report."""
    with llm_output.watching() as repairs:
        assert llm_output.words("EXPOSITION_OVERLOAD") == "exposition overload"
    assert repairs["checked"] == 1


def test_repairs_in_batched_work_are_counted_too(monkeypatch):
    """The audience simulator coerces inside worker threads, and a thread starts
    with an empty context — so the busiest path is the one that would silently
    count nothing."""
    with llm_output.watching() as repairs:
        llm.map_concurrent([1, 2, 3], lambda item: llm_output.number("bad", item))
    assert repairs == {"checked": 3, "repaired": 3, "clamped": 0, "clipped": 0}


def test_an_offline_run_repairs_nothing(offline):
    """The sample output is the shape the agents expect, by construction. If this
    ever fails, an agent and its own fallback have gone out of step."""
    from core.orchestrator.graph import Orchestrator
    from core.orchestrator.state import GlobalState

    with llm_output.watching() as repairs:
        orchestrator = Orchestrator()
        state = GlobalState(project_id="PROJ_REPAIRS")
        for node in orchestrator.nodes:
            state = orchestrator.run(state, start=node.key, end=node.key)

    assert repairs["checked"] > 100, "the run coerced almost nothing; is the counter wired up?"
    assert repairs["repaired"] == 0 and repairs["clamped"] == 0


# ------------------------------------------------------------ the prompt set --


def test_capturing_prompts_makes_no_model_call(monkeypatch):
    """The capture has to be free, or collecting the prompts costs the quota the
    experiment needs. Reaching a provider here would raise."""
    def forbidden(*_args, **_kwargs):
        raise AssertionError("the capture reached a live provider")

    monkeypatch.setattr(llm, "_call", forbidden)
    # One production and one screening: the shape of the thing, not its size.
    monkeypatch.setattr(capture, "PRODUCTIONS", [("PROJ_CAP", 250_000, "Lisbon, Portugal")])
    monkeypatch.setattr(capture, "MATERIALS", [("A diver stops surfacing on time.", 40, ["PT"])])

    captured = capture.collect()
    assert captured["calls"] > 10
    assert captured["prompts"] and len(captured["prompts"]) <= captured["calls"]
    for prompt in captured["prompts"]:
        assert prompt["prompt"] and prompt["tier"] in ("flash", "pro")
        assert prompt["schema"] is None or prompt["schema"]["type"] == "object"


def test_a_capture_leaves_the_providers_as_it_found_them(monkeypatch):
    """It forces every provider off to guarantee the above, and a tool that left
    them off would silently disable the model for whatever ran next."""
    monkeypatch.setattr(config, "has_gemini", lambda: True)
    monkeypatch.setattr(capture, "PRODUCTIONS", [])
    monkeypatch.setattr(capture, "MATERIALS", [])
    capture.collect()
    assert config.has_gemini() is True


def test_the_committed_prompt_set_is_the_one_the_experiment_describes():
    """`prompts.json` is committed so a run is reproducible. Every prompt needs a
    schema, or the pair of arms is not a comparison."""
    payload = json.loads((harness.PROMPTS).read_text(encoding="utf-8"))
    assert payload["distinct_prompts"] == len(payload["prompts"]) >= 200
    assert payload["without_a_schema"] == []
    assert len({p["id"] for p in payload["prompts"]}) == len(payload["prompts"])


# ------------------------------------------------------------- the reporting --


@pytest.mark.parametrize(
    "error, kind",
    [
        ("_AttemptFailed: JSONDecodeError: Expecting value", "unparseable"),
        ('ClientError: 400 INVALID_ARGUMENT. Unknown name "additional_properties"', "schema_refused"),
        ("ClientError: 429 RESOURCE_EXHAUSTED. You exceeded your current quota", "rate_limited"),
        ("_AttemptFailed: HTTP 402: payment_required, param quota", "needs_payment"),
        ("_AttemptFailed: HTTP 403: error code: 1010", "blocked_by_cdn"),
        ("_AttemptFailed: HTTP 502: bad gateway", "call_failed"),
    ],
)
def test_a_failure_is_classified_by_what_it_says_about_the_model(error, kind):
    """Only the first two are about the model's output. A quota is about the
    account, and averaging it in would let a rate limit read as a result."""
    assert harness._classify(error) == kind


def _pair(plain, schema):
    return {"plain": plain, "schema": schema}


ANSWERED = {"outcome": "answered", "seconds": 1.0, "violation_count": 0, "violations": []}
OFF_SHAPE = {"outcome": "answered", "seconds": 1.0, "violation_count": 2, "violations": ["a: missing"]}
UNPARSEABLE = {"outcome": "unparseable", "seconds": 1.0, "error": "JSONDecodeError"}
LIMITED = {"outcome": "rate_limited", "seconds": 0.1, "error": "429"}


def _report(monkeypatch, tmp_path, pairs):
    monkeypatch.setattr(harness, "RESULTS", tmp_path / "results.json")
    monkeypatch.setattr(harness, "REPORT_JSON", tmp_path / "report.json")
    monkeypatch.setattr(harness, "REPORT_MD", tmp_path / "REPORT.md")
    harness._save(harness.RESULTS, {"ollama:m": pairs})
    assert harness.do_report(None) == 0
    return json.loads((tmp_path / "report.json").read_text(encoding="utf-8")), \
        (tmp_path / "REPORT.md").read_text(encoding="utf-8")


def test_a_pair_the_quota_cut_short_is_left_out(monkeypatch, tmp_path):
    """The discipline the audience evaluation already keeps: a prompt counts only
    when both arms got a real attempt."""
    payload, markdown = _report(monkeypatch, tmp_path, {
        "a": _pair(ANSWERED, ANSWERED),
        "b": _pair(OFF_SHAPE, ANSWERED),
        "c": _pair(LIMITED, ANSWERED),          # quota, not a result
        "d": _pair(ANSWERED, {"outcome": "schema_refused", "seconds": 0.1}),
    })
    model = payload["models"]["ollama:m"]
    assert model["paired_prompts"] == 2
    assert model["excluded"] == {"rate_limited": 1, "schema_refused": 1}
    assert "cannot be read as a result about the model" in markdown


def test_a_clean_baseline_is_reported_as_one_not_as_a_gain(monkeypatch, tmp_path):
    """The result the experiment is most likely to produce, and the one easiest
    to dress up. It has to say the floor this sample can resolve."""
    payload, markdown = _report(monkeypatch, tmp_path, {
        str(n): _pair(ANSWERED, ANSWERED) for n in range(20)
    })
    model = payload["models"]["ollama:m"]
    assert model["arms"]["plain"]["violation_rate"] == 0.0
    assert model["change"]["violation"] == 0.0
    assert "baseline was already clean" in markdown
    assert "5.0%" in markdown  # 1/20: the smallest rate 20 prompts can resolve


def test_a_real_improvement_is_stated_with_both_rates(monkeypatch, tmp_path):
    pairs = {str(n): _pair(OFF_SHAPE, ANSWERED) for n in range(8)}
    pairs.update({f"u{n}": _pair(UNPARSEABLE, ANSWERED) for n in range(2)})
    payload, markdown = _report(monkeypatch, tmp_path, pairs)
    model = payload["models"]["ollama:m"]
    assert model["arms"]["plain"]["parse_failure_rate"] == 0.2
    assert model["arms"]["plain"]["violation_rate"] == 1.0
    assert model["arms"]["schema"]["violation_rate"] == 0.0
    assert model["arms"]["plain"]["fallback_rate"] == 0.2  # an agent would fall back
    assert "Enforcing the schema helped" in markdown


def test_a_schema_that_makes_things_worse_is_not_buried(monkeypatch, tmp_path):
    _payload, markdown = _report(monkeypatch, tmp_path, {
        str(n): _pair(ANSWERED, OFF_SHAPE) for n in range(10)
    })
    assert "made things worse" in markdown


def test_the_report_keeps_saying_what_it_cannot_tell_you(monkeypatch, tmp_path):
    """Derived schemas over-constrain in three known ways, and a report that
    dropped the caveats would read as stronger than the method allows."""
    _payload, markdown = _report(monkeypatch, tmp_path, {"a": _pair(ANSWERED, ANSWERED)})
    assert "What this cannot tell you" in markdown
    assert "derived, not authored" in markdown
    assert "not always a defect" in markdown


def test_pinning_a_model_turns_the_fallback_chain_off(monkeypatch):
    """One variable. A run that quietly fell through to another model would be
    comparing two models as much as two request shapes."""
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODELS", ["another", "and-another"])
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "k")
    monkeypatch.setattr(config, "has_cerebras", lambda: True)
    chosen = harness._pin("cerebras", "pinned-model")

    assert chosen == "pinned-model"
    assert config.LLM_PROVIDERS == ["cerebras"]
    assert config.GEMINI_FALLBACK_MODELS == []
    # Both tiers, so a `pro` prompt is not served by a different model than a
    # `flash` one and then compared with it.
    assert llm._candidates("flash") == llm._candidates("pro") == [("cerebras", "pinned-model")]


def test_a_truncated_reply_is_a_result_not_an_exclusion(monkeypatch, tmp_path):
    """Found mid-sweep: a model that runs out of output budget while satisfying
    a schema returns 400, and the provider sends nothing rather than partial
    JSON. Excluding those pairs would hide enforcement's own most interesting
    failure and flatter the schema arm."""
    truncated = {
        "outcome": "schema_refused",  # what the old rule recorded
        "seconds": 2.0,
        "error": "HTTP 400: max completion tokens reached before generating a valid document",
    }
    assert harness._classify(truncated["error"]) == "truncated"
    assert harness._outcome(truncated) == "truncated", "a stored result is reclassified on read"

    payload, markdown = _report(monkeypatch, tmp_path, {
        **{str(n): _pair(ANSWERED, ANSWERED) for n in range(9)},
        "t": _pair(ANSWERED, truncated),
    })
    model = payload["models"]["ollama:m"]
    assert model["paired_prompts"] == 10, "the truncated pair was excluded from the comparison"
    assert model["arms"]["schema"]["truncation_rate"] == 0.1
    # It counts against the arm twice over, as it should: the shape never
    # arrived, and the agent would have fallen back to its sample output.
    assert model["arms"]["schema"]["malformed_rate"] == 0.1
    assert model["arms"]["schema"]["fallback_rate"] == 0.1
    assert "ran out of output budget" in markdown


def test_a_quota_is_still_excluded_after_that_change(monkeypatch, tmp_path):
    payload, _markdown = _report(monkeypatch, tmp_path, {
        "a": _pair(ANSWERED, ANSWERED),
        "b": _pair(LIMITED, ANSWERED),
    })
    assert payload["models"]["ollama:m"]["paired_prompts"] == 1
