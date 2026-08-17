# AGENT.md — The Autonomous Studio

**Canonical registry of every agent, the shared A2A protocol, and the GlobalState contract.**
This is the single source of truth. If you add or change an agent, update this file first.

---

## 1. Core Concepts

**Orchestrator.** One `agent_director_orchestrator` runs a LangGraph DAG (registered through Google Cloud Agent Builder). It owns `GlobalState`, routes work between phases, applies fail-fast edges, and holds the queue of items needing a human. Agents never call each other directly across phases — they emit A2A messages that the orchestrator routes.

**GlobalState.** One JSON object, persisted in Supabase, passed through the entire pipeline (Section 3).

**A2A envelope.** Every message between agents uses one shape (Section 2). All traffic is appended to `GlobalState.event_log` so the UI's Live Agent Terminal can replay it.

**Guardrails (apply to every agent):**
- `max_iterations` = 1–2 per negotiation loop. Never unbounded.
- **Fail-fast:** non-compliant items (PR liability, over budget, hard censorship block) are purged before expensive steps.
- **Model tiering:** Gemini 2.0 Flash by default; Gemini 2.0 Pro only for heavy reasoning (final synthesis, aggregation, recut).
- **Structured output:** every agent returns validated JSON (Gemini JSON mode). Never parse prose.
- **Cost:** compress before LLM (FFmpeg 720p, screening packets), batch where possible, cache reusable prompts.

---

## 2. The A2A Envelope

```json
{
  "message_id": "msg_<sender>_<seq>",
  "in_reply_to": "msg_... (optional, for replies)",
  "sender": "agent_...",
  "recipient": "agent_... | agent_director_orchestrator",
  "timestamp": "2026-08-17T11:20:05Z",
  "intent": "verb_noun",
  "payload": { }
}
```

Rules:
- `sender`/`recipient` are always agent IDs from this file.
- `intent` is from the vocabulary in Section 5.
- A **request** expects a reply (matching `in_reply_to`); a **broadcast** to the orchestrator does not.
- Every message is appended to `event_log`.

---

## 3. GlobalState Schema

```jsonc
{
  "project_id":       "PROJ_NEON_NIGHTS",
  "mode":             "enterprise | indie",
  "script_context":   "genre, tone, demographic targets, IP params",
  "role_requirements":{ /* machine-readable casting mandates */ },
  "scoring_weights":  { "W_A": 0.4, "W_H": 0.2, "W_PR": 0.2, "W_B": 0.2 },
  "candidates":       [ { "id", "name", "metadata", "media_url", "scores", "status" } ],
  "casting_status":   "SOURCING | SCREENING | LOCKED",
  "schedule":         { "stripboard": [ /* scene_id, date, venue */ ], "conflicts": [] },
  "budget_state":     { "daily_burn", "cap", "alerts": [] },
  "compliance_state": { "<territory>": "CLEARED | AWAITING_QC | BLOCKED" },
  "audience_report":  { "tomatometer", "audience_score", "heatmap", "weakest_scene_id" },
  "marketing_assets": [ { "asset_id", "type", "status", "source_scene_id" } ],
  "human_escalations":[ { "queue_item", "reason" } ],
  "event_log":        [ /* every A2A envelope, in order */ ]
}
```

Status enums used across phases:
`SOURCING · SCREENING · LOCKED · CLEARED · AWAITING_QC · BLOCKED · FLAGGED_ACTION_REQUIRED · DRAFT · PR_REVIEW · APPROVED · SCHEDULED · POSTED`

---

## 4. Agent Registry

Each entry: **ID** · role · model · inputs → outputs · intents it sends/handles.

### Phase I — Pre-Casting Intelligence & Compliance

**`agent_profiler`** — *Corporate Profiler / "Vibe Checker."*
Model: Gemini Pro. In: `script_context`, exec brief. Out: `role_requirements`, `scoring_weights`.
Intents: emits `mandate_ready`.

**`agent_intake`** — *Sourcing / Intake Gateway (webhook).*
Model: none (service). In: applicant links (Backstage/Actors Access/email). Out: appended `candidates[]`.
Intents: emits `candidate_ingested`.

**`agent_market_synergy`** — *Clout / Hype check.*
Model: Gemini Flash + Tavily. In: candidate. Out: normalized Hype score.
Intents: handles `score_candidate`, emits `hype_scored`.

**`agent_pr_shield`** — *Brand Safety & PR Shield / "Drama Filter."*
Model: Gemini Flash + safety settings + Tavily. In: candidate. Out: PR risk flag.
Intents: handles `score_candidate`, emits `pr_scored`; may emit `disqualify` on hard red flag.

**`agent_finance`** — *Finance & ROI / "Wallet Check."*
Model: Gemini Flash. In: candidate quote vs `budget_state`. Out: budget verdict.
Intents: handles `score_candidate`, emits `budget_scored`; may emit `disqualify`.

**Risk Router** — orchestrator conditional edge. Purges candidates with `disqualify`; advances the rest to Phase II.

### Phase II — Audition Analysis & Scorecard

**`agent_media_proc`** — *Media Processing / "Cruncher."*
Model: none (FFmpeg + Whisper). In: 4K tape. Out: 720p clip + transcript.
Intents: emits `media_ready`.

**`agent_audition_analytics`** — *Multimodal Analytics / "AI Co-Director."*
Model: Gemini Pro (multimodal). In: 720p clip + transcript + `role_requirements`. Out: qualitative review + Audition score.
Intents: handles `review_audition`, emits `audition_scored`.

**`agent_synthesis`** — *Final Scorecard.*
Model: Gemini Pro (or plain Python). In: all sub-scores + `scoring_weights`. Out: leaderboard via
`Composite = Audition·W_A + Hype·W_H + PR·W_PR + Budget·W_B`.
Intents: emits `leaderboard_ready`; pushes top-N to `human_escalations`.

### Phase III — Script → Schedule

**`agent_breakdown`** — In: `Script_DB(scene_id, INT/EXT, location_type, characters_needed, estimated_time)`. Out: structured scene requirements. Emits `breakdown_ready`.

**`agent_location`** — In: scene reqs + `Venue_DB(venue_name, cost_per_day, available_dates, indie_friendly)`. Out: venue matches/permits. Handles `check_venue_availability`, emits `venue_offer`.

**`agent_scheduler_shoot`** — *Stripboard.* In: breakdown + venues + cast availability. Out: `schedule.stripboard`, budget burn. Sends `check_venue_availability`; emits `schedule_updated`.
**Demo A2A:** `agent_scheduler_shoot` → `check_venue_availability` (Scene 12, Tue) → `agent_location` replies `venue_offer` (Wed) → scheduler rebuilds stripboard → broadcasts `schedule_updated`.

### Phase IV — Compliance, Localization & Launch Prep

**`agent_rights_clearance`** — In: assets + `Clearance_DB`, `Censorship_Rules_DB`. Out: per-asset clearance verdict. Handles `verify_regional_compliance`, emits `compliance_result`.

**`agent_localization`** — In: cut + target territory. Out: subs/dubs plan; sets `compliance_state[territory]`. Sends `verify_regional_compliance`; broadcasts `task_status_update` (BLOCKED/CLEARED).

**`agent_qc`** — In: cut. Out: technical pass/fail (resolution, audio mix, timeline lock). Emits `qc_result`.

**`agent_telemetry`** — In: pre-launch/early-screening metrics. Out: telemetry summary. Emits `telemetry_update`.
**Demo A2A:** `agent_localization` → `verify_regional_compliance` (UAE, SCN_004) → `agent_rights_clearance` replies `compliance_result` (FLAGGED, alcohol) → localization broadcasts `task_status_update` (BLOCKED) → UAE turns red.

### Phase V — Audience Simulation & Predictive Reviews

**`agent_persona_foundry`** — Model: Gemini Flash (ADK loop). Out: `Persona_DB(persona_id, age_bracket, gender, region, genre_affinities[], viewer_type, attention_span, cultural_flags[])`. Emits `personas_ready`.

**`agent_viewer`** — Model: Gemini Flash (batched 10/call). In: screening packet + persona. Out: `Screening_DB(persona_id, title_id, scene_scores[], overall_score, sentiment, review_text, would_recommend, drop_off_scene)`. Handles `screen_film`.

**`agent_aggregation`** — *Tallyman.* Model: Python + Gemini Pro. In: all verdicts. Out: `Aggregate_DB(title_id, tomatometer, audience_score, imdb_weighted, score_distribution, demographic_breakdown, weakest_scene_id)` → `audience_report`. Detects anomalies; sends `diagnose_engagement_anomaly`; broadcasts `simulation_verdict_update`.

**`agent_critic`** — Model: Gemini Flash. Out: representative reviews in outlet voices. Emits `reviews_ready`.

**`agent_recut_advisor`** — Model: Gemini Pro. In: anomaly. Out: root cause + remediation + predicted lift. Handles `diagnose_engagement_anomaly`, emits `diagnosis_result`.
**Demo A2A:** `agent_aggregation` → `diagnose_engagement_anomaly` (18–24M, Act 2) → `agent_recut_advisor` replies `diagnosis_result` (trim & intercut, +6) → aggregation broadcasts `simulation_verdict_update`.

### Phase VI — Marketing, PR & Autonomous Social Launch

**`agent_campaign_strategist`** — Model: Gemini Flash. In: `audience_report`. Out: campaign plan (segment→platform→tone). Sends `request_audience_insights`; emits `campaign_plan_ready`.

**`agent_reel_cutter`** — In: `weakest/strongest` scene scores. Out: reel from top-scored scene (still-sequence if no Veo). Emits `reel_ready`.

**`agent_visual`** — Model: Imagen 3. Out: posters/memes/thumbnails. Sends `verify_brand_safety`; on rejection regenerates (≤2 tries).

**`agent_copywriter`** — Model: Gemini Flash. Out: platform-native copy / press release. (Often merged into the visual call to save calls.)

**`agent_pr_risk`** — Model: Gemini Flash + safety settings + rules JSON. In: asset. Out: spoiler/cultural/tone/legal verdict. Handles `verify_brand_safety`, emits `brand_safety_result`.

**`agent_publisher`** — Model: none (mock APIs). In: approved assets. Out: `Campaign_Calendar` entries + mock `Social_Metrics_DB`. Emits `asset_scheduled`.
**Demo A2A:** `agent_visual` → `verify_brand_safety` (meme) → `agent_pr_risk` replies `brand_safety_result` (BLOCKED: spoiler + gesture) → visual regenerates → `agent_publisher` schedules; visual broadcasts `asset_status_update`.

---

## 5. Intent Vocabulary

Requests/replies: `verify_regional_compliance` / `compliance_result`, `check_venue_availability` / `venue_offer`, `diagnose_engagement_anomaly` / `diagnosis_result`, `verify_brand_safety` / `brand_safety_result`, `score_candidate` / `*_scored`, `review_audition` / `audition_scored`, `screen_film`, `request_audience_insights`.

Broadcasts (to orchestrator): `mandate_ready`, `candidate_ingested`, `media_ready`, `leaderboard_ready`, `breakdown_ready`, `schedule_updated`, `task_status_update`, `qc_result`, `telemetry_update`, `personas_ready`, `reviews_ready`, `simulation_verdict_update`, `campaign_plan_ready`, `reel_ready`, `asset_scheduled`, `asset_status_update`, `disqualify`.

---

## 6. Canonical Message Examples

**Request (Phase IV):**
```json
{ "message_id": "msg_loc_req_89234", "sender": "agent_localization",
  "recipient": "agent_rights_clearance", "timestamp": "2026-08-16T15:45:12Z",
  "intent": "verify_regional_compliance",
  "payload": { "task_id": "tsk_uae_dub_04", "title_id": "PROJ_NEON_NIGHTS",
    "scene_id": "SCN_004", "target_territory": "UAE",
    "elements_to_check": [ { "type": "dialogue", "tags": ["alcohol_reference"] } ] } }
```

**Reply (Phase V):**
```json
{ "message_id": "msg_rec_res_44121", "in_reply_to": "msg_agg_req_44120",
  "sender": "agent_recut_advisor", "recipient": "agent_aggregation",
  "timestamp": "2026-08-17T11:20:08Z", "intent": "diagnosis_result",
  "payload": { "root_cause": "EXPOSITION_OVERLOAD", "action": "TRIM_AND_INTERCUT",
    "predicted_lift": { "segment_score": "+29", "tomatometer": "+6" } } }
```

**Broadcast (Phase VI):**
```json
{ "message_id": "msg_vis_upd_77312", "sender": "agent_visual",
  "recipient": "agent_director_orchestrator", "timestamp": "2026-08-17T14:02:44Z",
  "intent": "asset_status_update",
  "payload": { "asset_id": "AST_MEME_0091", "status": "BLOCKED",
    "blocker_details": { "blocked_by_agent": "agent_pr_risk",
      "reasons": ["spoiler_high", "cultural_gesture_med"], "auto_retry": true } } }
```

---

## 7. Adding a New Agent (checklist)

1. Give it an `agent_<name>` ID and add it to Section 4 under its phase.
2. Declare its model tier, inputs, outputs, and the intents it sends/handles.
3. Reuse the shared `envelope.py` helper — never invent a message shape.
4. Return structured JSON only.
5. Add a fail-fast / `max_iterations` guard.
6. Append all its traffic to `event_log` so it shows in the Live Agent Terminal.
