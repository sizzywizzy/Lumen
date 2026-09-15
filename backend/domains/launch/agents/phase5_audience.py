"""Phase V — Audience Simulation & Predictive Reviews.

agent_persona_foundry -> agent_viewer (batched) -> agent_aggregation
-> (anomaly) agent_recut_advisor -> agent_critic.
Viewer verdicts are deterministic pseudo-random (hash-seeded) so the demo
replays identically; swap for real Gemini calls per batch later.
"""
import hashlib

from core import config, llm_output
from core import scenes as scene_names
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import AudienceReview, GlobalState
from domains.launch import prompts
from services import gemini_client, mock_db

VIEWER_BATCH_SIZE = 10
ANOMALY_SEGMENT = {"age_bracket": "18-24", "gender": "M"}
ANOMALY_SCENE = "SCN_004"  # act-two exposition scene
FRESH_THRESHOLD = 60.0  # a tomatometer at or above this reads as "fresh"
CRITIC_REVIEWS = 3


def verdict_for(tomatometer: float) -> str:
    return "fresh" if tomatometer >= FRESH_THRESHOLD else "rotten"


def _foundry(state: GlobalState) -> list[dict]:
    """Expand the seed personas into a full Persona_DB."""
    seeds = mock_db.load("personas")
    personas = []
    for i in range(config.PERSONA_COUNT):
        seed = seeds[i % len(seeds)]
        personas.append({**seed, "persona_id": f"PER_{i:03d}"})
    log_event(state, broadcast("agent_persona_foundry", "personas_ready", {
        "count": len(personas),
    }))
    return personas


def _seeded_score(persona_id: str, scene_id: str) -> float:
    """Deterministic 4.0-9.5 stand-in for a Gemini viewer verdict."""
    digest = hashlib.md5(f"{persona_id}:{scene_id}".encode()).digest()
    return round(4.0 + (digest[0] / 255) * 5.5, 1)


def _scenes(state: GlobalState) -> list[dict]:
    return state.script_context.get("scenes") or mock_db.load("script")["scenes"]


def _viewers(state: GlobalState, personas: list[dict]) -> list[dict]:
    scenes = [s["scene_id"] for s in _scenes(state)]
    verdicts = []
    for start in range(0, len(personas), VIEWER_BATCH_SIZE):
        batch = personas[start:start + VIEWER_BATCH_SIZE]
        request = log_event(state, make_envelope(
            "agent_aggregation", "agent_viewer", "screen_film",
            {"title_id": state.project_id, "batch": [p["persona_id"] for p in batch]},
        ))
        for persona in batch:
            scene_scores = {sc: _seeded_score(persona["persona_id"], sc) for sc in scenes}
            # The anomaly: young male viewers check out during the act-two exposition.
            if (persona["age_bracket"] == ANOMALY_SEGMENT["age_bracket"] and persona["gender"] == ANOMALY_SEGMENT["gender"]
                    and ANOMALY_SCENE in scene_scores):
                scene_scores[ANOMALY_SCENE] = round(scene_scores[ANOMALY_SCENE] * 0.45, 1)
            overall = round(sum(scene_scores.values()) / len(scene_scores), 2)
            verdicts.append({
                "persona_id": persona["persona_id"], "title_id": state.project_id,
                "scene_scores": scene_scores, "overall_score": overall,
                "sentiment": "positive" if overall >= 6.5 else ("mixed" if overall >= 5.5 else "negative"),
                "would_recommend": overall >= 6.5,
                "drop_off_scene": min(scene_scores, key=scene_scores.get),
                "demographic": {"age_bracket": persona["age_bracket"], "gender": persona["gender"], "region": persona["region"]},
            })
        # One reply summarizes the batch (keeps the event log readable).
        log_event(state, make_reply(request, "agent_viewer", "screen_film", {
            "batch_size": len(batch),
            "mean_overall": round(sum(v["overall_score"] for v in verdicts[-len(batch):]) / len(batch), 2),
        }))
    return verdicts


def _aggregation(state: GlobalState, verdicts: list[dict]) -> None:
    scenes = list(verdicts[0]["scene_scores"])
    heatmap = {sc: round(sum(v["scene_scores"][sc] for v in verdicts) / len(verdicts), 2) for sc in scenes}
    weakest = min(heatmap, key=heatmap.get)
    titles = scene_names.titles(_scenes(state))
    report = state.audience_report
    report.tomatometer = round(100 * sum(1 for v in verdicts if v["overall_score"] >= 6.0) / len(verdicts), 1)
    report.audience_score = round(10 * sum(v["overall_score"] for v in verdicts) / len(verdicts), 1)
    report.heatmap = heatmap
    report.weakest_scene_id = weakest
    report.viewer_count = len(verdicts)
    report.verdict = verdict_for(report.tomatometer)
    report.scene_titles = {sc: titles.get(sc, sc) for sc in heatmap}
    report.weakest_scene_title = titles.get(weakest, "")

    # Anomaly detection: is one demographic segment cratering on one scene?
    segment = [v for v in verdicts
               if v["demographic"]["age_bracket"] == ANOMALY_SEGMENT["age_bracket"]
               and v["demographic"]["gender"] == ANOMALY_SEGMENT["gender"]]
    if segment:
        seg_score = sum(v["scene_scores"][weakest] for v in segment) / len(segment)
        if seg_score < heatmap[weakest] * 0.8:
            request = log_event(state, make_envelope(
                "agent_aggregation", "agent_recut_advisor", "diagnose_engagement_anomaly",
                {"segment": ANOMALY_SEGMENT, "scene_id": weakest,
                 "segment_score": round(seg_score, 2), "population_score": heatmap[weakest]},
            ))
            fallback = prompts.MOCK_RECUT_DIAGNOSIS
            raw = llm_output.mapping(gemini_client.generate_json(
                f"Segment {ANOMALY_SEGMENT} scores {seg_score:.1f} on {weakest} vs population {heatmap[weakest]}.",
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
            state.escalate(f"recut:{weakest}",
                           f"{diagnosis['root_cause']} -> {diagnosis['action']} (predicted tomatometer {diagnosis['predicted_lift']['tomatometer']})")

    log_event(state, broadcast("agent_aggregation", "simulation_verdict_update", {
        "tomatometer": report.tomatometer, "audience_score": report.audience_score, "verdict": report.verdict,
        "weakest_scene_id": weakest, "weakest_scene_title": report.weakest_scene_title, "viewers": len(verdicts),
    }))


def _cast(state: GlobalState) -> list[dict]:
    """Characters with the actor currently picked for each, for the reviews."""
    picks = {c.role_id: c.name for c in state.candidates if c.status == "LOCKED"}
    return [
        {"character": role["name"], "actor": picks.get(role_id, ""), "type": role.get("type", "")}
        for role_id, role in (state.role_requirements or {}).items()
        if isinstance(role, dict) and role.get("name")
    ]


def _viewer_label(verdict: dict) -> str:
    age = str(verdict.get("demographic", {}).get("age_bracket") or "").replace("-", " to ")
    return f"A viewer aged {age}" if age else "A test viewer"


def _viewer_reviews(state: GlobalState, verdicts: list[dict], cast: list[dict]) -> list[AudienceReview]:
    """Two comments built from the simulated verdicts: the happiest viewer and the least happy."""
    if not verdicts:
        return []
    titles = state.audience_report.scene_titles
    lead = next((c["character"] for c in cast if c["type"] == "lead"), cast[0]["character"] if cast else "The lead")
    best = max(verdicts, key=lambda v: v["overall_score"])
    worst = min(verdicts, key=lambda v: v["overall_score"])
    favourite = max(best["scene_scores"], key=best["scene_scores"].get)
    return [
        AudienceReview(source=_viewer_label(best), kind="viewer", score=f"{best['overall_score']:.1f} out of 10",
                       quote=f'{lead} carries the whole film, and "{titles.get(favourite, "the finale")}" is the scene I keep thinking about.'),
        AudienceReview(source=_viewer_label(worst), kind="viewer", score=f"{worst['overall_score']:.1f} out of 10",
                       quote=f'"{titles.get(worst["drop_off_scene"], "One scene")}" dragged for me, and I never really got back into it.'),
    ]


def _critic(state: GlobalState, verdicts: list[dict]) -> None:
    report = state.audience_report
    cast = _cast(state)
    mock = prompts.mock_critic_reviews(cast, report.weakest_scene_title)
    raw = gemini_client.generate_json(
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
    report.reviews = critics + _viewer_reviews(state, verdicts, cast)
    log_event(state, broadcast("agent_critic", "reviews_ready", {"reviews": [r.model_dump() for r in report.reviews]}))


def run_phase5_audience(state: GlobalState) -> GlobalState:
    # The recut request belongs to this screening; an earlier run's is dropped.
    state.clear_escalations("recut:")
    personas = _foundry(state)
    verdicts = _viewers(state, personas)
    _aggregation(state, verdicts)
    _critic(state, verdicts)
    return state
