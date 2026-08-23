"""Phase V — Audience Simulation & Predictive Reviews.

agent_persona_foundry -> agent_viewer (batched) -> agent_aggregation
-> (anomaly) agent_recut_advisor -> agent_critic.
Viewer verdicts are deterministic pseudo-random (hash-seeded) so the demo
replays identically; swap for real Gemini calls per batch later.
"""
import hashlib

from core import config
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState
from domains.launch import prompts
from services import gemini_client, mock_db

VIEWER_BATCH_SIZE = 10
ANOMALY_SEGMENT = {"age_bracket": "18-24", "gender": "M"}
ANOMALY_SCENE = "SCN_004"  # act-two exposition scene


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


def _viewers(state: GlobalState, personas: list[dict]) -> list[dict]:
    scenes = [s["scene_id"] for s in mock_db.load("script")["scenes"]]
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
            if persona["age_bracket"] == ANOMALY_SEGMENT["age_bracket"] and persona["gender"] == ANOMALY_SEGMENT["gender"]:
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
    report = state.audience_report
    report.tomatometer = round(100 * sum(1 for v in verdicts if v["overall_score"] >= 6.0) / len(verdicts), 1)
    report.audience_score = round(10 * sum(v["overall_score"] for v in verdicts) / len(verdicts), 1)
    report.heatmap = heatmap
    report.weakest_scene_id = weakest

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
            diagnosis = gemini_client.generate_json(
                f"Segment {ANOMALY_SEGMENT} scores {seg_score:.1f} on {weakest} vs population {heatmap[weakest]}.",
                tier="pro", system=prompts.RECUT_SYSTEM, mock=prompts.MOCK_RECUT_DIAGNOSIS,
            )
            log_event(state, make_reply(request, "agent_recut_advisor", "diagnosis_result", diagnosis))
            state.escalate(f"recut:{weakest}",
                           f"{diagnosis['root_cause']} -> {diagnosis['action']} (predicted tomatometer {diagnosis['predicted_lift']['tomatometer']})")

    log_event(state, broadcast("agent_aggregation", "simulation_verdict_update", {
        "tomatometer": report.tomatometer, "audience_score": report.audience_score,
        "weakest_scene_id": weakest, "viewers": len(verdicts),
    }))


def _critic(state: GlobalState) -> None:
    reviews = gemini_client.generate_json(
        f"Film: {state.script_context.get('title')}. Audience report: {state.audience_report.model_dump()}.",
        system=prompts.CRITIC_SYSTEM, mock=prompts.MOCK_CRITIC_REVIEWS,
    )
    log_event(state, broadcast("agent_critic", "reviews_ready", reviews))


def run_phase5_audience(state: GlobalState) -> GlobalState:
    personas = _foundry(state)
    verdicts = _viewers(state, personas)
    _aggregation(state, verdicts)
    _critic(state)
    return state
