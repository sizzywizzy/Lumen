"""Phase VI — Marketing, PR & Autonomous Social Launch.

agent_campaign_strategist -> agent_reel_cutter -> agent_visual <-> agent_pr_risk
(regenerate on rejection, max 2 tries) -> agent_copywriter <-> agent_pr_risk
-> agent_publisher.
"""
from core import config
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState, MarketingAsset
from domains.launch import prompts
from services import gemini_client


def _strategist(state: GlobalState) -> dict:
    request = log_event(state, make_envelope(
        "agent_campaign_strategist", "agent_aggregation", "request_audience_insights",
        {"title_id": state.project_id},
    ))
    log_event(state, make_reply(request, "agent_aggregation", "simulation_verdict_update",
                                state.audience_report.model_dump()))
    plan = gemini_client.generate_json(
        f"Audience report: {state.audience_report.model_dump()}. Budget: ${state.budget_state.cap:,.0f}.",
        system=prompts.STRATEGIST_SYSTEM,
        mock={"segments": [
            {"demographic": "18-24", "platform": "tiktok", "tone": "chaotic-ironic", "asset_types": ["meme", "reel"]},
            {"demographic": "25-34", "platform": "instagram", "tone": "sleek-noir", "asset_types": ["poster", "reel"]},
        ]},
    )
    log_event(state, broadcast("agent_campaign_strategist", "campaign_plan_ready", plan))
    return plan


def _best_scene(state: GlobalState) -> str:
    heatmap = state.audience_report.heatmap
    return max(heatmap, key=heatmap.get) if heatmap else "SCN_005"


def _reel_cutter(state: GlobalState) -> None:
    scene = _best_scene(state)
    asset = MarketingAsset(asset_id="AST_REEL_0001", type="reel", status="APPROVED",
                           source_scene_id=scene,
                           content={"format": "9x16 still-sequence", "duration_s": 22})
    state.marketing_assets.append(asset)
    log_event(state, broadcast("agent_reel_cutter", "reel_ready", {
        "asset_id": asset.asset_id, "source_scene_id": scene,
    }))


def _pr_risk_check(state: GlobalState, request: dict) -> dict:
    """agent_pr_risk: spoiler / cultural / tone / legal verdict on one asset draft."""
    caption = request["payload"]["caption"].lower()
    reasons = [f"spoiler_high:'{term}'" for term in prompts.SPOILER_TERMS if term in caption]
    verdict = {"status": "BLOCKED" if reasons else "APPROVED", "reasons": reasons}
    log_event(state, make_reply(request, "agent_pr_risk", "brand_safety_result", verdict))
    return verdict


def _visual(state: GlobalState) -> None:
    """Meme generation with the PR-gate loop: draft, verify, regenerate on rejection."""
    scene = _best_scene(state)
    asset = MarketingAsset(asset_id="AST_MEME_0001", type="meme", status="DRAFT", source_scene_id=scene)
    state.marketing_assets.append(asset)

    for attempt, mock_draft in zip(range(config.MAX_ASSET_REGENERATIONS), prompts.MOCK_MEME_DRAFTS):
        draft = gemini_client.generate_json(
            f"Meme for {state.script_context.get('title')} from scene {scene}, attempt {attempt + 1}. "
            f"Avoid: {asset.content.get('blocked_reasons', [])}",
            system=prompts.VISUAL_SYSTEM, mock=mock_draft,
        )
        asset.content = {**draft, "attempt": attempt + 1}
        asset.status = "PR_REVIEW"
        request = log_event(state, make_envelope(
            "agent_visual", "agent_pr_risk", "verify_brand_safety",
            {"asset_id": asset.asset_id, "caption": draft["caption"]},
        ))
        verdict = _pr_risk_check(state, request)
        if verdict["status"] == "APPROVED":
            asset.status = "APPROVED"
            break
        asset.status = "BLOCKED"
        asset.content["blocked_reasons"] = verdict["reasons"]
        log_event(state, broadcast("agent_visual", "asset_status_update", {
            "asset_id": asset.asset_id, "status": "BLOCKED",
            "blocker_details": {"blocked_by_agent": "agent_pr_risk",
                                "reasons": verdict["reasons"], "auto_retry": attempt + 1 < config.MAX_ASSET_REGENERATIONS},
        }))
    else:
        state.escalate(f"asset:{asset.asset_id}", "Meme still blocked after max regenerations")

    # Poster ships with copy merged into the same call (saves a call, per AGENT.md).
    poster = MarketingAsset(asset_id="AST_POSTER_0001", type="poster", status="APPROVED",
                            source_scene_id="SCN_001",
                            content={"tagline": "The city remembers everything.",
                                     "image_prompt": "rain-soaked street, lone cab, neon reflections"})
    state.marketing_assets.append(poster)
    log_event(state, broadcast("agent_visual", "asset_status_update", {
        "asset_id": poster.asset_id, "status": "APPROVED",
    }))


def _copywriter(state: GlobalState, plan: dict) -> None:
    """agent_copywriter: platform-native copy per campaign segment plus a press
    release, in one Flash call. Every draft goes through agent_pr_risk like the
    memes do; a blocked draft is escalated rather than retried (bounded cost)."""
    segments = plan.get("segments", [])
    copy = gemini_client.generate_json(
        f"Title: {state.script_context.get('title')}. Campaign segments: {segments}. "
        f"Audience report: {state.audience_report.model_dump()}.",
        system=prompts.COPYWRITER_SYSTEM, mock=prompts.MOCK_COPY,
    )
    drafts = [
        ("copy", f"AST_COPY_{i + 1:04d}",
         {"platform": post.get("platform", ""), "demographic": post.get("demographic", ""),
          "caption": str(post.get("caption", "")), "hashtags": list(post.get("hashtags", []) or [])})
        for i, post in enumerate(copy.get("posts", []) or [])
    ]
    release = copy.get("press_release") or {}
    drafts.append(("press_release", "AST_PRESS_0001", {
        "headline": str(release.get("headline", "")), "body": str(release.get("body", "")),
        "caption": f"{release.get('headline', '')} {release.get('body', '')}".strip(),
    }))

    scene = _best_scene(state)
    for asset_type, asset_id, content in drafts:
        asset = MarketingAsset(asset_id=asset_id, type=asset_type, status="PR_REVIEW",
                               source_scene_id=scene, content=content)
        state.marketing_assets.append(asset)
        request = log_event(state, make_envelope(
            "agent_copywriter", "agent_pr_risk", "verify_brand_safety",
            {"asset_id": asset.asset_id, "caption": content["caption"]},
        ))
        verdict = _pr_risk_check(state, request)
        update = {"asset_id": asset.asset_id, "type": asset_type}
        if verdict["status"] == "APPROVED":
            asset.status = "APPROVED"
        else:
            asset.status = "BLOCKED"
            asset.content["blocked_reasons"] = verdict["reasons"]
            update["blocker_details"] = {"blocked_by_agent": "agent_pr_risk",
                                         "reasons": verdict["reasons"], "auto_retry": False}
            state.escalate(f"asset:{asset.asset_id}", f"Copy blocked by PR risk: {verdict['reasons']}")
        log_event(state, broadcast("agent_copywriter", "asset_status_update", {**update, "status": asset.status}))


def _publisher(state: GlobalState, plan: dict) -> None:
    """Mock social APIs: put every APPROVED asset on the campaign calendar."""
    slots = ["2026-09-20T17:00:00Z", "2026-09-21T17:00:00Z", "2026-09-22T17:00:00Z"]
    platforms = [seg["platform"] for seg in plan.get("segments", [])] or ["tiktok"]
    for i, asset in enumerate(a for a in state.marketing_assets if a.status == "APPROVED"):
        asset.status = "SCHEDULED"
        asset.content["scheduled_for"] = slots[i % len(slots)]
        asset.content["platform"] = platforms[i % len(platforms)]
        log_event(state, broadcast("agent_publisher", "asset_scheduled", {
            "asset_id": asset.asset_id, "platform": asset.content["platform"],
            "scheduled_for": asset.content["scheduled_for"],
        }))


def run_phase6_marketing(state: GlobalState) -> GlobalState:
    plan = _strategist(state)
    _reel_cutter(state)
    _visual(state)
    _copywriter(state, plan)
    _publisher(state, plan)
    return state
