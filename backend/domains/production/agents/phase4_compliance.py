"""Phase IV — Compliance, Localization & Launch Prep.

agent_localization <-> agent_rights_clearance per territory, then agent_qc and
agent_telemetry. Demo beat: UAE blocks on SCN_004's alcohol reference.
"""
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState
from services import mock_db


def _rights_clearance(state: GlobalState, request: dict) -> dict:
    """agent_rights_clearance: check censorship rules and asset regional rights."""
    payload = request["payload"]
    rules = mock_db.load("censorship_rules").get(payload["target_territory"], {})
    clearances = {item["asset_id"]: item for item in mock_db.load("clearance")}
    evaluations, flagged, cuts = [], [], []
    for element in payload["elements_to_check"]:
        for tag in element["tags"]:
            if tag in rules.get("blocked_tags", []):
                result = {"type": element["type"], "scene_id": element["scene_id"], "tags": [tag],
                          "status": "VIOLATION", "violation_code": f"{payload['target_territory']}_REG_09_SUBSTANCE",
                          "required_remediation": "replace_audio_track_clean_version"}
                flagged.append(result)
            elif tag in rules.get("requires_cuts", []):
                result = {"type": element["type"], "scene_id": element["scene_id"], "tags": [tag],
                          "status": "REQUIRES_CUT", "required_remediation": "edit_or_replace_scene_audio"}
                cuts.append(result)
            else:
                result = {"type": element["type"], "scene_id": element["scene_id"], "tags": [tag], "status": "CLEARED"}
            evaluations.append(result)
        asset_id = element.get("asset_id")
        if asset_id:
            asset = clearances.get(asset_id)
            status = "CLEARED" if asset and payload["target_territory"] in asset["cleared_regions"] else "VIOLATION"
            evaluations.append({"type": element["type"], "asset_id": asset_id, "status": status})
            if status != "CLEARED":
                flagged.append({"asset_id": asset_id, "status": status, "required_remediation": "secure_regional_license"})
    flagged_scene_id = next((item.get("scene_id") for item in flagged if item.get("scene_id")), None)
    verdict = {"title_id": payload["title_id"], "scene_id": flagged_scene_id or payload.get("scene_id"),
               "target_territory": payload["target_territory"],
               "overall_status": "FLAGGED_ACTION_REQUIRED" if flagged else ("REQUIRES_CUTS" if cuts else "CLEARED"),
               "status": "FLAGGED" if flagged else ("REQUIRES_CUTS" if cuts else "CLEARED"),
               "evaluations": evaluations, "flagged": flagged, "requires_cuts": cuts}
    log_event(state, make_reply(request, "agent_rights_clearance", "compliance_result", verdict))
    return verdict


def _localization(state: GlobalState) -> None:
    scenes = state.script_context.get("scenes") or mock_db.load("script")["scenes"]
    tagged = [{"type": "dialogue", "tags": s["tags"], "scene_id": s["scene_id"]}
              for s in scenes if s["tags"]]
    tagged.append({"type": "music", "tags": [], "scene_id": "SCN_004", "asset_id": "TRK_992_INDIE_ROCK"})
    # Every territory with a rule set is a target market.
    territories = list(mock_db.load("censorship_rules"))

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
            "task_id": f"tsk_{territory.lower()}_loc", "title_id": state.project_id,
            "territory": territory, "stage": "AUDIO_DUBBING", "status": state.compliance_state[territory],
            "blocker_details": ({
                "blocked_by_agent": "agent_rights_clearance",
                "reason": "Failed regional censorship check.",
                "resolution_needed": f"Awaiting clean dialogue stem for {verdict.get('scene_id') or 'flagged scene'}."
            } if state.compliance_state[territory] == "BLOCKED" else None),
        }))


def _qc(state: GlobalState) -> None:
    log_event(state, broadcast("agent_qc", "qc_result", {
        "resolution": "3840x2160", "audio_mix": "5.1 ok", "timeline_locked": True, "verdict": "PASS",
    }))


def _telemetry(state: GlobalState) -> None:
    log_event(state, broadcast("agent_telemetry", "telemetry_update", {
        "trailer_views_48h": 12_800,
        "watchlist_adds": 950,
    }))


def run_phase4_compliance(state: GlobalState) -> GlobalState:
    _localization(state)
    _qc(state)
    _telemetry(state)
    return state
