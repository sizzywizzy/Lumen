"""Phase V — Audience Simulation & Predictive Reviews.

agent_persona_foundry -> agent_viewer (cohorts, batched) -> agent_aggregation
-> (anomaly) agent_recut_advisor -> agent_critic.

The screening uses the Audience Analyst's machinery rather than its own: a
seeded panel with no sensitive attributes (core/audience/personas.py), grouped
into cohorts that the model scores scene by scene in batched calls
(domains/launch/agents/audience_sim.py). Each viewer's scene scores are
derived from their cohort's, moved by their own traits. Without a model the
cohort scores come from stated offline rules, so the demo replays identically.
"""
import hashlib
import statistics
from typing import Callable

from core import config, llm_output
from core import scenes as scene_names
from core.audience import personas as panel_lib
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import AudienceReview, GlobalState
from domains.launch import prompts
from domains.launch.agents import audience_sim
from services import llm, mock_db

FRESH_THRESHOLD = 60.0  # a tomatometer at or above this reads as "fresh"
LIKED_SCORE = 6.0       # a viewer whose overall is at least this counts toward the tomatometer
CRITIC_REVIEWS = 3
ANOMALY_RATIO = 0.8     # a segment this far below everyone on the weakest scene gets a recut request

# Groups of viewers the aggregator compares on the weakest scene, each as
# (dimension, how to name a viewer's group). Taste, viewing habits, age band
# and region only: the panel models no sensitive attributes.
SEGMENTS: tuple[tuple[str, Callable[[dict], str]], ...] = (
    ("age_band", lambda p: {
        "under_25": "viewers under 25", "25_34": "viewers aged 25 to 34",
        "35_49": "viewers aged 35 to 49", "50_plus": "viewers aged 50 and over",
    }[panel_lib.AGE_BANDS.get(p["age_group"], "25_34")]),
    ("market_region", lambda p: "viewers in " + panel_lib.BLOC_NAMES.get(
        panel_lib.MARKET_BLOCS.get(p["market"], ""), p["market_name"])),
    ("genre_affinity", lambda p: "genre fans" if p["matches_film_genre"] else "viewers outside the genre"),
    ("pacing_tolerance", lambda p: f"viewers with {p['pacing_tolerance']} patience for slow pacing"),
    ("viewing_frequency", lambda p: {
        "low": "occasional filmgoers", "medium": "regular filmgoers", "high": "frequent filmgoers",
    }[p["viewing_frequency"]]),
)


def verdict_for(tomatometer: float) -> str:
    return "fresh" if tomatometer >= FRESH_THRESHOLD else "rotten"


def _scenes(state: GlobalState) -> list[dict]:
    return [scene_names.describe(s) for s in (state.script_context.get("scenes") or mock_db.load("script")["scenes"])]


def _seed(state: GlobalState) -> int:
    """The same screenplay on the same production always gets the same panel."""
    key = f"{state.project_id}:{(state.script_context or {}).get('fingerprint') or 'demo'}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _foundry(state: GlobalState, seed: int) -> tuple[list[dict], list[dict]]:
    """agent_persona_foundry: a seeded panel and the cohorts it screens in."""
    genre = str((state.script_context or {}).get("genre") or "")
    panel, distribution = panel_lib.build_panel(size=config.PERSONA_COUNT, seed=seed, film_genres=[genre])
    cohorts = panel_lib.build_cohorts(panel)
    log_event(state, broadcast("agent_persona_foundry", "personas_ready", {
        "count": len(panel), "cohorts": len(cohorts), "seed": seed,
        "distribution_fingerprint": panel_lib.distribution_fingerprint(distribution),
    }))
    return panel, cohorts


def _viewers(state: GlobalState, scenes: list[dict], cohorts: list[dict], panel: list[dict],
             seed: int) -> tuple[list[dict], dict[str, dict], str]:
    """agent_viewer: every cohort scores every scene; each viewer's scores follow."""
    context = state.script_context or {}
    film = {key: context.get(key) for key in ("title", "genre", "tone", "logline")}
    request = log_event(state, make_envelope(
        "agent_aggregation", "agent_viewer", "screen_film",
        {"title_id": state.project_id, "scenes": len(scenes), "cohorts": len(cohorts), "panel_size": len(panel)},
    ))
    trace: list[dict] = []
    verdicts, live, batches = audience_sim.screen_scenes(film, scenes, cohorts, trace)
    responses = audience_sim.derive_scene_responses(panel, cohorts, verdicts, scenes, seed)
    degraded = sum(1 for v in verdicts.values() if v.get("_degraded"))
    source = "offline" if not live else ("live" if live == batches and not degraded else "mixed")
    log_event(state, make_reply(request, "agent_viewer", "screen_film", {
        "cohorts_scored": len(verdicts), "batches": batches, "live_batches": live, "source": source,
        "mean_overall": round(statistics.fmean(r["overall_score"] for r in responses), 2) if responses else 0.0,
    }))
    return responses, verdicts, source


def _anomaly(panel: list[dict], responses: list[dict], scene_id: str, population: float) -> dict | None:
    """The group of viewers furthest below everyone else on `scene_id`, if any
    group is far enough below to be worth a recut."""
    people = {p["persona_id"]: p for p in panel}
    floor = max(8, round(0.05 * len(responses)))
    worst = None
    for dimension, name in SEGMENTS:
        groups: dict[str, list[float]] = {}
        for response in responses:
            groups.setdefault(name(people[response["persona_id"]]), []).append(response["scene_scores"][scene_id])
        for label, scores in groups.items():
            if len(scores) < floor or population <= 0:
                continue
            mean = statistics.fmean(scores)
            if worst is None or mean / population < worst["ratio"]:
                worst = {"dimension": dimension, "label": label, "viewers": len(scores),
                         "segment_score": round(mean, 2), "ratio": mean / population}
    return worst if worst and worst["ratio"] < ANOMALY_RATIO else None


def _aggregation(state: GlobalState, scenes: list[dict], panel: list[dict], responses: list[dict], source: str) -> None:
    by_id = {s["scene_id"]: s for s in scenes}
    heatmap = {sid: round(statistics.fmean(r["scene_scores"][sid] for r in responses), 2) for sid in by_id}
    weakest = min(heatmap, key=heatmap.get)
    titles = scene_names.titles(scenes)
    report = state.audience_report
    report.tomatometer = round(100 * sum(1 for r in responses if r["overall_score"] >= LIKED_SCORE) / len(responses), 1)
    report.audience_score = round(10 * statistics.fmean(r["overall_score"] for r in responses), 1)
    report.heatmap = heatmap
    report.weakest_scene_id = weakest
    report.viewer_count = len(responses)
    report.verdict = verdict_for(report.tomatometer)
    report.scene_titles = {sid: titles.get(sid, sid) for sid in heatmap}
    report.weakest_scene_title = titles.get(weakest, "")
    report.screening_source = source

    # Anomaly detection: is one group of viewers cratering on the weakest scene?
    segment = _anomaly(panel, responses, weakest, heatmap[weakest])
    if segment:
        payload = {k: segment[k] for k in ("dimension", "label", "viewers", "segment_score")}
        request = log_event(state, make_envelope(
            "agent_aggregation", "agent_recut_advisor", "diagnose_engagement_anomaly",
            {"segment": payload, "scene_id": weakest, "scene_title": report.weakest_scene_title,
             "population_score": heatmap[weakest]},
        ))
        scene = by_id[weakest]
        fallback = prompts.MOCK_RECUT_DIAGNOSIS
        raw = llm_output.mapping(llm.generate_json(
            f"Segment: {segment['label']} ({segment['viewers']} of {len(responses)} viewers) score "
            f"{segment['segment_score']:.1f} on \"{report.weakest_scene_title}\" ({weakest}) against "
            f"{heatmap[weakest]:.1f} for the whole panel.\nScene: {scene.get('summary', '')}\n"
            f"Tags: {', '.join(scene.get('tags') or []) or 'none'}",
            tier="pro", system=prompts.RECUT_SYSTEM, mock=fallback,
        ), fallback)
        # Field by field, so a diagnosis missing a key or with a lift that
        # is not a mapping still yields a readable recut request.
        lift = llm_output.mapping(raw.get("predicted_lift"), fallback["predicted_lift"])
        diagnosis = {
            "root_cause": llm_output.text(raw.get("root_cause"), fallback["root_cause"], 80),
            "action": llm_output.text(raw.get("action"), fallback["action"], 80),
            "predicted_lift": {
                "segment_score": llm_output.text(lift.get("segment_score"), fallback["predicted_lift"]["segment_score"], 20),
                "tomatometer": llm_output.text(lift.get("tomatometer"), fallback["predicted_lift"]["tomatometer"], 20),
            },
        }
        log_event(state, make_reply(request, "agent_recut_advisor", "diagnosis_result", diagnosis))
        state.escalate(
            f"recut:{weakest}",
            f'{segment["label"][:1].upper()}{segment["label"][1:]} drift during "{report.weakest_scene_title}" '
            f"({llm_output.words(diagnosis['root_cause'])}). Suggested fix: {llm_output.words(diagnosis['action'])} "
            f"(predicted tomatometer {diagnosis['predicted_lift']['tomatometer']}).",
        )

    log_event(state, broadcast("agent_aggregation", "simulation_verdict_update", {
        "tomatometer": report.tomatometer, "audience_score": report.audience_score, "verdict": report.verdict,
        "weakest_scene_id": weakest, "weakest_scene_title": report.weakest_scene_title,
        "viewers": len(responses), "source": source,
    }))


def _cast(state: GlobalState) -> list[dict]:
    """Characters with the actor currently picked for each, for the reviews."""
    picks = {c.role_id: c.name for c in state.candidates if c.status == "LOCKED"}
    return [
        {"character": role["name"], "actor": picks.get(role_id, ""), "type": role.get("type", "")}
        for role_id, role in (state.role_requirements or {}).items()
        if isinstance(role, dict) and role.get("name")
    ]


def _viewer_label(persona: dict) -> str:
    age = str(persona.get("age_group") or "")
    age = "65 and over" if age == "65+" else age.replace("-", " to ")
    where = persona.get("market_name")
    if not age:
        return "A test viewer"
    return f"A viewer aged {age}" + (f" in {where}" if where else "")


def _viewer_reviews(state: GlobalState, panel: list[dict], responses: list[dict], cast: list[dict]) -> list[AudienceReview]:
    """Two comments built from the simulated responses: the happiest viewer and the least happy."""
    if not responses:
        return []
    people = {p["persona_id"]: p for p in panel}
    titles = state.audience_report.scene_titles
    lead = next((c["character"] for c in cast if c["type"] == "lead"), cast[0]["character"] if cast else "The lead")
    best = max(responses, key=lambda r: r["overall_score"])
    worst = min(responses, key=lambda r: r["overall_score"])
    favourite = max(best["scene_scores"], key=best["scene_scores"].get)
    return [
        AudienceReview(source=_viewer_label(people[best["persona_id"]]), kind="viewer",
                       score=f"{best['overall_score']:.1f} out of 10",
                       quote=f'{lead} carries the whole film, and "{titles.get(favourite, "the finale")}" is the scene I keep thinking about.'),
        AudienceReview(source=_viewer_label(people[worst["persona_id"]]), kind="viewer",
                       score=f"{worst['overall_score']:.1f} out of 10",
                       quote=f'"{titles.get(worst["drop_off_scene"], "One scene")}" dragged for me, and I never really got back into it.'),
    ]


def _critic(state: GlobalState, panel: list[dict], responses: list[dict]) -> None:
    report = state.audience_report
    cast = _cast(state)
    mock = prompts.mock_critic_reviews(cast, report.weakest_scene_title)
    raw = llm.generate_json(
        f"FILM: {state.script_context.get('title')}\nLOGLINE: {state.script_context.get('logline')}\n"
        f"CAST: {cast}\nTOMATOMETER: {report.tomatometer}\nWEAKEST SCENE: {report.weakest_scene_title}",
        system=prompts.CRITIC_SYSTEM, mock=mock,
    )
    critics = []
    for item in ((raw.get("reviews") if isinstance(raw, dict) else None) or []):
        if isinstance(item, dict) and str(item.get("quote") or "").strip():
            critics.append(AudienceReview(
                source=str(item.get("outlet") or item.get("source") or "A critic").strip()[:60],
                quote=str(item["quote"]).strip()[:240], score=str(item.get("score") or "").strip()[:20],
            ))
        if len(critics) == CRITIC_REVIEWS:
            break
    if not critics:
        critics = [AudienceReview(source=r["outlet"], quote=r["quote"], score=r["score"]) for r in mock["reviews"]]
    # Assigned, not appended, so re-running the phase never duplicates reviews.
    report.reviews = critics + _viewer_reviews(state, panel, responses, cast)
    log_event(state, broadcast("agent_critic", "reviews_ready", {"reviews": [r.model_dump() for r in report.reviews]}))


def run_phase5_audience(state: GlobalState) -> GlobalState:
    # The recut request belongs to this screening; an earlier run's is dropped.
    state.clear_escalations("recut:")
    scenes = _scenes(state)
    seed = _seed(state)
    panel, cohorts = _foundry(state, seed)
    responses, _verdicts, source = _viewers(state, scenes, cohorts, panel, seed)
    _aggregation(state, scenes, panel, responses, source)
    _critic(state, panel, responses)
    return state
