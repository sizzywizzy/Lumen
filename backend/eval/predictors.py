"""The predictors under test, and the baselines they have to beat.

Every predictor takes the same `dataset.brief(film)` string and returns a
prediction on the same 0-100 scale, so the only thing that differs between
them is the machinery in the middle. That is the whole point of the exercise:

  lumen        the real Phase V pipeline — read the material, build a panel of
               personas, elicit a verdict per cohort, expand to individuals,
               average. Two to six model calls a film, depending on
               --analysis and how many cohorts the panel yields.
  single_call  one model call: "here is a film, rate it out of 100". The
               honest baseline, because it is what the whole panel machinery
               has to justify itself against. If the elaborate version cannot
               beat one prompt, the elaborate version is decoration.
  constant     always answers the sample's mean rating. Not a real predictor;
               it is the floor that makes an MAE a number rather than a vibe.
               It is deliberately given an unfair advantage (it is told the
               mean of the very films it is grading) so that beating it means
               something.

WHEN A CALL FAILS
Every agent in Lumen falls back to deterministic sample output when the model
is unavailable, which is right for the product and fatal for an evaluation: a
benchmark that quietly grades its own fallbacks reports the mock's accuracy
under the model's name. So each prediction carries `live` — whether every
model call behind it really reached a model — and `run.py` reports the count and
refuses to headline a number when too many films fell back.
"""
import statistics
from typing import Any, Optional

from core import config
from core.orchestrator.state import GlobalState
from core.audience import personas as panel_lib
from domains.launch.agents import audience_sim
from domains.launch.agents.phase5_audience import LIKED_SCORE
from eval import dataset
from services import llm

# The product's own panel size (config.PERSONA_COUNT), so the evaluation grades
# the shipped configuration rather than a shrunken stand-in. What actually sets
# the model spend is the cohort count, capped at 28 and batched five to a call;
# --panel-size trades panel resolution for quota when a run has to finish today.
EVAL_PANEL_SIZE = config.PERSONA_COUNT


def _scores(responses: list[dict]) -> dict[str, float]:
    """The two headline numbers, computed exactly as Phase V computes them."""
    overalls = [r["overall_score"] for r in responses]
    return {
        "audience_score": round(10 * statistics.fmean(overalls), 1),
        "tomatometer": round(100 * sum(1 for s in overalls if s >= LIKED_SCORE) / len(overalls), 1),
    }


# Runtime is the only pacing signal a TMDb record carries. Crude, and applied
# identically to every film, so it cannot flatter any one of them.
DELIBERATE_MIN = 140
BRISK_MAX = 95


def analysis_from_brief(film: dict[str, Any]) -> dict[str, Any]:
    """`analyse_material`'s output shape, derived from TMDb metadata instead.

    Why this exists: the model read costs one Pro call per film, and on a free
    tier that call is the difference between a 34-film run finishing today and
    finishing in a week. `--analysis model` restores the production path.

    Fields the metadata cannot support are left empty rather than invented — a
    fabricated theme list would feed the cohort prompt something the film does
    not contain, and the cohort verdicts are where the film-specific signal is
    supposed to enter.
    """
    runtime = film["runtime_min"]
    return {
        "genre": film["genres"],
        "logline": film["overview"],
        "tone": "",
        "setting": "",
        "pacing_read": ("deliberate" if runtime >= DELIBERATE_MIN
                        else ("brisk" if runtime <= BRISK_MAX else "steady")),
        "themes": [],
        "main_characters": [],
        "major_conflicts": [],
        # Empty, so no viewer's content aversion fires. The evaluation therefore
        # says nothing about that path, uniformly across every film.
        "content_flags": [],
        "potentially_polarizing": [],
        # "synopsis" exactly: it is the word the analysis vocabulary defines
        # (audience_prompts.ANALYSIS_SYSTEM), and the advisors test for it by
        # name when they decide whether material is too thin to lean on
        # (domains/skills/agents.py). A near-miss like "synopsis_only" reads
        # fine and silently fails that test.
        "material_quality": {
            "completeness": "synopsis",
            "limits": "Public synopsis only — no scenes, dialogue or ending.",
        },
        # A synopsis can support a read on premise, shape and appeal. It cannot
        # support one on dialogue, acting or the ending, so those are withheld.
        "evaluable_dimensions": ["story", "characters", "pacing", "entertainment", "originality"],
    }


def lumen(
    film: dict[str, Any],
    *,
    panel_size: int = EVAL_PANEL_SIZE,
    seed: int = 20260902,
    analysis_mode: str = "brief",
) -> dict[str, Any]:
    """The product's audience simulator, scoring a film from its brief alone.

    Runs the stages that produce the score — analyse, panel, cohorts, expand.
    The cultural scan and PR synthesis are skipped: they cost two model calls a
    film and cannot move `audience_score`, and spending a free-tier quota on
    calls that do not affect the number under test would shrink the sample for
    nothing.
    """
    state = GlobalState(project_id=f"PROJ_EVAL_{film['tmdb_id']}")
    trace: list[dict] = []

    if analysis_mode == "model":
        analysis = audience_sim.analyse_material(state, dataset.brief(film), trace)
    else:
        analysis = analysis_from_brief(film)

    panel, _dist = panel_lib.build_panel(
        size=panel_size, seed=seed, film_genres=analysis.get("genre", []),
    )
    cohorts = panel_lib.build_cohorts(panel)
    verdicts = audience_sim.simulate_cohorts(state, analysis, cohorts, trace)
    dimensions = audience_sim.evaluable_dimensions(analysis)
    responses = audience_sim.derive_individuals(panel, cohorts, verdicts, dimensions, analysis, seed)

    live = sum(1 for t in trace if llm.is_live(t))
    # A cohort marked `_degraded` took its offline verdict because the reply
    # failed or skipped it. All of them degraded means the simulation carries no
    # model signal at all, and run.py drops the film rather than grading it.
    degraded = sum(1 for v in verdicts.values() if v.get("_degraded"))
    return {
        **_scores(responses),
        "live": live == len(trace) and bool(trace) and not degraded,
        "stages": len(trace),
        "live_stages": live,
        # Real calls, not stages: the cohort stage is one trace entry covering
        # several batched calls.
        "llm_calls": sum(int(t.get("batches") or 1) for t in trace),
        # Which model actually answered. The client falls back down a chain
        # when one is rate-limited, so without this a report could average a
        # film scored by one model with a film scored by another and call the
        # result a single system's accuracy.
        "models": sorted({t["model"] for t in trace if t.get("model")}),
        "panel_size": len(responses),
        "cohorts": len(cohorts),
        "degraded_cohorts": degraded,
        "genre_read": analysis.get("genre", []),
        "analysis_mode": analysis_mode,
    }


SINGLE_CALL_SYSTEM = (
    "You forecast how general audiences will rate a film, from its premise alone. "
    'Answer JSON: {"audience_score": number 0-100, "percent_who_would_like_it": number 0-100}. '
    "audience_score is the average rating the public would give it out of 100. "
    "percent_who_would_like_it is the share of viewers rating it 6/10 or better. "
    "Most films land between 55 and 80; use the full range only when the material "
    "warrants it."
)


def single_call(film: dict[str, Any]) -> dict[str, Any]:
    """One prompt, one answer, no panel. The baseline that matters.

    `mock` is deliberately not supplied: a failed call must raise so the film is
    recorded as unscored rather than silently graded against a canned number.
    """
    try:
        payload, meta = llm.generate_json_traced(
            dataset.brief(film), tier="flash", system=SINGLE_CALL_SYSTEM, mock=None,
        )
    except llm.LLMUnavailable as exc:
        return {"audience_score": None, "tomatometer": None, "live": False, "error": str(exc)[:200]}

    def number(value, low=0.0, high=100.0) -> Optional[float]:
        try:
            return max(low, min(high, float(value)))
        except (TypeError, ValueError):
            return None

    payload = payload if isinstance(payload, dict) else {}
    return {
        "audience_score": number(payload.get("audience_score")),
        "tomatometer": number(payload.get("percent_who_would_like_it")),
        "live": llm.is_live(meta),
        "llm_calls": 1,
        "live_stages": 1 if llm.is_live(meta) else 0,
        "models": [meta["model"]] if meta.get("model") else [],
    }


def constant(value: float) -> Any:
    """A predictor that ignores the film and always answers `value`."""
    def predict(_film: dict[str, Any]) -> dict[str, Any]:
        return {"audience_score": value, "tomatometer": None, "live": True, "llm_calls": 0}
    return predict


REGISTRY = {"lumen": lumen, "single_call": single_call}
