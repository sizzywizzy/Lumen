"""Phase IV — Compliance, Localization & Launch Prep.

agent_localization <-> agent_rights_clearance per territory, then agent_qc and
agent_telemetry. Demo beat: UAE blocks on SCN_004's alcohol reference.
"""
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState
from services import mock_db

INDIE_TERRITORIES = ["US", "FR", "UAE"]
ENTERPRISE_TERRITORIES = ["US", "FR", "IN", "UAE", "JP"]


def _rights_clearance(state: GlobalState, request: dict) -> dict:
    """agent_rights_clearance: check flagged elements against Censorship_Rules_DB."""
    payload = request["payload"]
    rules = mock_db.load("censorship_rules").get(payload["target_territory"], {})
    flagged, cuts = [], []
    for element in payload["elements_to_check"]:
        for tag in element["tags"]:
            if tag in rules.get("blocked_tags", []):
                flagged.append({"scene_id": element["scene_id"], "tag": tag})
            elif tag in rules.get("requires_cuts", []):
                cuts.append({"scene_id": element["scene_id"], "tag": tag})
    verdict = {"territory": payload["target_territory"],
               "status": "FLAGGED" if flagged else ("REQUIRES_CUTS" if cuts else "CLEARED"),
               "flagged": flagged, "requires_cuts": cuts}
    log_event(state, make_reply(request, "agent_rights_clearance", "compliance_result", verdict))
    return verdict


def _localization(state: GlobalState) -> None:
    scenes = mock_db.load("script")["scenes"]
    tagged = [{"type": "dialogue", "tags": s["tags"], "scene_id": s["scene_id"]}
              for s in scenes if s["tags"]]
    territories = INDIE_TERRITORIES if state.mode == "indie" else ENTERPRISE_TERRITORIES

    for territory in territories:
        request = log_event(state, make_envelope(
            "agent_localization", "agent_rights_clearance", "verify_regional_compliance",
            {"task_id": f"tsk_{territory.lower()}_loc", "title_id": state.project_id,
             "target_territory": territory, "elements_to_check": tagged},
        ))
        verdict = _rights_clearance(state, request)
        if verdict["status"] == "FLAGGED":
            state.compliance_state[territory] = "BLOCKED"
            state.escalate(f"compliance:{territory}",
                           f"Hard censorship block in {territory}: {verdict['flagged']}")
        elif verdict["status"] == "REQUIRES_CUTS":
            state.compliance_state[territory] = "AWAITING_QC"
        else:
            state.compliance_state[territory] = "CLEARED"
        log_event(state, broadcast("agent_localization", "task_status_update", {
            "territory": territory, "status": state.compliance_state[territory],
        }))


def _qc(state: GlobalState) -> None:
    log_event(state, broadcast("agent_qc", "qc_result", {
        "resolution": "3840x2160", "audio_mix": "5.1 ok", "timeline_locked": True, "verdict": "PASS",
    }))


def _telemetry(state: GlobalState) -> None:
    log_event(state, broadcast("agent_telemetry", "telemetry_update", {
        "trailer_views_48h": 12800 if state.mode == "indie" else 2_400_000,
        "watchlist_adds": 950 if state.mode == "indie" else 88_000,
    }))


def run_phase4_compliance(state: GlobalState) -> GlobalState:
    _localization(state)
    _qc(state)
    _telemetry(state)
    return state
