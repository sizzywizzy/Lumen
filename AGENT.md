# AGENT.md — Lumen

**Canonical registry of every agent, the shared A2A protocol, and the GlobalState contract.**
This is the single source of truth. If you add or change an agent, update this file first.

---

## 1. Core Concepts

**Orchestrator.** One `agent_director_orchestrator` runs an explicit, framework-free state machine (`backend/core/orchestrator/graph.py`). It owns `GlobalState`, routes work between phases, applies fail-fast edges, resets each phase's own output before that phase runs again, and holds the queue of items needing a human. Agents never call each other directly across phases — they emit A2A messages that the orchestrator routes.

**Runs.** A pipeline run (all six phases, or a range) works in the background (`backend/domains/pipeline/jobs.py`): the route answers `202`, the dashboard polls `GET /api/pipeline/status/<project_id>`, and one run per production goes at a time. Each `PhaseNode` declares the `GlobalState` fields and escalation prefixes it `owns`; a finished run copies exactly those onto the state stored at that moment (`backend/core/orchestrator/merge.py`), so edits saved while it ran are kept. A full run starts from a reset state and keeps only the material: the screenplay, the schedule rules and the expenses.

**GlobalState.** One JSON object, persisted in Supabase, passed through the entire pipeline (Section 3).

**A2A envelope.** Every message between agents uses one shape (Section 2). All traffic is appended to `GlobalState.event_log` so the UI's Live Agent Terminal can replay it.

**Guardrails (apply to every agent):**
- `max_iterations` = 1–2 per negotiation loop. Never unbounded.
- **Fail-fast:** non-compliant items (PR liability, over budget, hard censorship block) are purged before expensive steps.
- **Model tiering:** the Flash tier (`GEMINI_FLASH_MODEL`) by default; the Pro tier (`GEMINI_PRO_MODEL`) only for heavy reasoning (script reads, final synthesis, recut). Both default to `gemini-3.6-flash` (`backend/core/config.py`), each followed by a fallback chain. Vertex AI stands in for a key only on explicit opt-in (`GOOGLE_GENAI_USE_VERTEXAI` plus `GOOGLE_CLOUD_PROJECT`).
- **Structured output:** every agent returns validated JSON (Gemini JSON mode). Never parse prose.
- **Cost:** keep model inputs small (clipped script reads, screening packets), batch where possible, cache reusable prompts.

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
- `message_id` ends in a number that only goes up: the sequence starts from the process's start time in microseconds, so ids stay unique in an event log that outlives a restart.
- `sender`/`recipient` are always agent IDs from this file.
- `intent` is from the vocabulary in Section 5.
- A **request** expects a reply (matching `in_reply_to`); a **broadcast** to the orchestrator does not.
- Every message is appended to `event_log`.

---

## 3. GlobalState Schema

```jsonc
{
  "project_id":       "PROJ_NEON_NIGHTS",
  "script_context":   "genre, tone, demographic targets, IP params",
  "role_requirements":{ /* machine-readable casting mandates */ },
  "scoring_weights":  { "W_A": 0.4, "W_H": 0.2, "W_PR": 0.2, "W_B": 0.2 },
  "candidates":       [ { "id", "name", "metadata", "media_url", "scores", "status" } ],
  "casting_status":   "SOURCING | SCREENING | LOCKED",
  "schedule":         { "stripboard": [ /* scene_id, date, venue */ ], "conflicts": [] },
  "budget_state":     { "daily_burn", "cap" /* total budget from intake or Settings — sets every downstream cap */, "alerts": [],
                        "expenses": [] /* logged by the team */, "total_budget", "spent", "remaining" /* derived from cap and expenses */ },
  "compliance_state": { "<territory>": "CLEARED | AWAITING_QC | BLOCKED" },
  "audience_report":  { "tomatometer", "audience_score", "heatmap", "weakest_scene_id", "screening_source" /* live | mixed | offline */ },
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
Model: Gemini Pro. In: `script_context`, exec brief; reads the screenplay dropped at intake when one is stored (`script_context.raw_text`), the demo script otherwise. Out: `role_requirements`, `scoring_weights`.
Intents: emits `mandate_ready`.

**`agent_casting_scout`** — *Talent Scout.*
Model: Gemini Flash with Google Search grounding, plus Tavily when configured; an offline pool of local actors otherwise. In: `locality`, `director_notes`, `role_requirements`, the per-role cap. Out: scouted candidates for `agent_intake`. A candidate the model files under a role the script does not have goes to one of the script's roles instead, and quotes and follower counts must be numbers.
Intents: handles `scout_local_talent`; broadcasts `crawl_locality_started` and `crawl_locality_completed`.

**`agent_intake`** — *Sourcing / Intake Gateway.*
Model: none (service). In: the scout's candidates. Out: `candidates[]`, rebuilt on every Phase I run.
Intents: emits `candidate_ingested`.

**`agent_market_synergy`** — *Clout / Hype check.*
Model: none (a log scale over follower counts). In: candidate. Out: normalized Hype score.
Intents: handles `score_candidate`, emits `hype_scored`.

**`agent_pr_shield`** — *Brand Safety & PR Shield / "Drama Filter."*
Model: Gemini Flash. In: the candidate's recent press. Out: PR score and risk flag (a live answer is coerced field by field, so a red flag spelt as text still counts).
Intents: handles `score_candidate`, emits `pr_scored`; may emit `disqualify` on hard red flag.

**`agent_finance`** — *Finance & ROI / "Wallet Check."*
Model: none (arithmetic). In: candidate quote vs the per-role cap (10% of `budget_state.cap`). Out: budget score; a quote over the cap disqualifies.
Intents: handles `score_candidate`, emits `budget_scored`; may emit `disqualify`.

**Risk Router** — orchestrator conditional edge. Purges candidates with `disqualify`; advances the rest to Phase II.

### Phase II — Audition Analysis & Scorecard

**`agent_media_proc`** — *Media Processing / "Cruncher."*
Model: none. In: the tape reference. Out: the same reference, announced to the reviewer. Decoding and transcription are out of scope by design, so auditions are judged from the role brief and the tape link.
Intents: emits `media_ready`.

**`agent_audition_analytics`** — *Multimodal Analytics / "AI Co-Director."*
Model: Gemini Pro. In: the role brief (`role_requirements`) and the tape reference (no decoding, by design). Out: qualitative review + Audition score.
Intents: handles `review_audition`, emits `audition_scored`.

**`agent_synthesis`** — *Final Scorecard.*
Model: Gemini Pro (or plain Python). In: all sub-scores + `scoring_weights`. Out: leaderboard via
`Composite = Audition·W_A + Hype·W_H + PR·W_PR + Budget·W_B`.
Intents: emits `leaderboard_ready`; pushes top-N to `human_escalations`.

### Phase III — Script → Schedule

**`agent_breakdown`** — Model: Gemini Pro when a screenplay is stored, else none. In: the uploaded screenplay (scenes constrained to venue types in `Venue_DB` and to the profiler's role ids, capped at 30) or `Script_DB(scene_id, INT/EXT, location_type, characters_needed, estimated_time_hours, tags, assets)`. Out: structured scene requirements, also kept on `script_context.scenes` for Phases IV and V. A scene's `assets` (licensed music cues) keep only ids `Clearance_DB` knows. Emits `breakdown_ready`.

**`agent_location`** — In: scene reqs + `Venue_DB(venue_name, cost_per_day, available_dates)`. Out: venue matches/permits. Handles `check_venue_availability`, emits `venue_offer`.

**`agent_scheduler_shoot`** — *Stripboard.* In: breakdown + venues + cast availability. Out: `schedule.stripboard`, `schedule.conflicts` (reason `venue_unavailable`, `past_wrap` or `cast_unavailable`), budget burn. A scene no venue can host goes to the queue as `venue:<scene>`, a shoot past the wrap date as `schedule:past_wrap`, and scenes booked on a day their cast is away as `schedule:cast`. Sends `check_venue_availability`; emits `schedule_updated`.
**Demo A2A:** `agent_scheduler_shoot` → `check_venue_availability` (Scene 12, Tue) → `agent_location` replies `venue_offer` (Wed) → scheduler rebuilds stripboard → broadcasts `schedule_updated`.

### Phase IV — Compliance, Localization & Launch Prep

**`agent_rights_clearance`** — In: each scene's content tags and the assets the breakdown lists, against `Clearance_DB` and `Censorship_Rules_DB`. Out: per-element clearance verdict. Handles `verify_regional_compliance`, emits `compliance_result`.

**`agent_localization`** — In: cut + target territory. Out: subs/dubs plan; sets `compliance_state[territory]`, and queues `compliance:<territory>` with a plain sentence when a territory blocks. Sends `verify_regional_compliance`; broadcasts `task_status_update` (BLOCKED/CLEARED).

**`agent_qc`** — In: cut. Out: technical pass/fail (resolution, audio mix, timeline lock). Emits `qc_result`.

**`agent_telemetry`** — In: pre-launch/early-screening metrics. Out: telemetry summary. Emits `telemetry_update`.
**Demo A2A:** `agent_localization` → `verify_regional_compliance` (UAE, SCN_004) → `agent_rights_clearance` replies `compliance_result` (FLAGGED, alcohol) → localization broadcasts `task_status_update` (BLOCKED) → UAE turns red.

### Phase V — Audience Simulation & Predictive Reviews

**`agent_persona_foundry`** — Model: none (seeded). Out: a panel of 200 personas from `core/audience/personas.py`, seeded by the production and its screenplay, grouped into at most 28 cohorts (age band × market region × genre affinity). Personas carry taste and viewing habits, the market they watch in and an age group — never gender, ethnicity, religion or income. Emits `personas_ready`.

**`agent_viewer`** — Model: Gemini Flash, five cohorts to a call, the calls concurrent (`audience_sim.screen_scenes`, the same machinery as the Audience Analyst). In: the film's brief, every scene (title, summary, tags) and the cohorts. Out: a score per scene per cohort; each viewer's scene scores follow from their cohort's, moved by their own pacing tolerance, story preference, content sensitivity, viewing frequency and a seeded jitter. A reply that skips a scene, or scores it with something that is not a number, falls back to the stated offline rules for that score. Handles `screen_film`.

**`agent_aggregation`** — *Tallyman.* Model: Python + Gemini Pro. In: all viewers' scores. Out: `audience_report` (tomatometer, audience score, per-scene heatmap, weakest scene, `screening_source`). Compares groups of viewers (age band, market region, genre affinity, pacing tolerance, viewing frequency) on the weakest scene, and sends `diagnose_engagement_anomaly` for the group furthest below everyone (under 80%); broadcasts `simulation_verdict_update`.

**`agent_critic`** — Model: Gemini Flash. Out: representative reviews in outlet voices. Emits `reviews_ready`.

**`agent_recut_advisor`** — Model: Gemini Pro. In: anomaly. Out: root cause + remediation + predicted lift, queued as `recut:<scene>`. Handles `diagnose_engagement_anomaly`, emits `diagnosis_result`.
**Demo A2A:** `agent_aggregation` → `diagnose_engagement_anomaly` (viewers under 25, the act-two exposition scene) → `agent_recut_advisor` replies `diagnosis_result` (trim & intercut, +6) → aggregation broadcasts `simulation_verdict_update`.

**`agent_script_analyst`** — *Material read for the audience simulator.* Model: Gemini Pro. In: the screenplay or synopsis. Out: genre, tone, themes, content flags and the dimensions the material can support. Used by the Audience Analyst and Cultural Researcher advisors and the Marketing page's simulations, not by the pipeline's Phase V (which reads the Phase I brief and the Phase III breakdown). Handles `screen_film` from `agent_persona_foundry`.

### Phase VI — Marketing, PR & Autonomous Social Launch

**`agent_campaign_strategist`** — Model: Gemini Flash. In: `audience_report`. Out: campaign plan (segment→platform→tone). Sends `request_audience_insights`; emits `campaign_plan_ready`.

**`agent_reel_cutter`** — In: `weakest/strongest` scene scores. Out: a still-sequence reel spec cut from the top-scored scene; no video generation by design. Emits `reel_ready`.

**`agent_visual`** — Model: Gemini Flash, plus a Gemini image model for the poster. Out: art-direction specs for memes/thumbnails (caption, image prompt, alt text), and the production's poster. After a pipeline run on a screenplay without one, or on request from the Overview, the poster takes a style drawn at random (never the previous poster's), a concept (tagline, scene, palette) that goes through `agent_pr_risk`, and portrait art painted with no lettering, or an SVG sketch without a key. Posters run in the background (`domains/launch/posters.py`) and live in `cn_posters`, outside GlobalState. Sends `verify_brand_safety`; on rejection regenerates (≤2 tries).

**`agent_copywriter`** — Model: Gemini Flash. Out: platform-native copy / press release. (Often merged into the visual call to save calls.)

**`agent_pr_risk`** — Model: Gemini Flash + safety settings + rules JSON. In: asset. Out: spoiler/cultural/tone/legal verdict. Handles `verify_brand_safety`, emits `brand_safety_result`.

**`agent_publisher`** — Model: none (mock APIs). In: approved assets. Out: `Campaign_Calendar` entries + mock `Social_Metrics_DB`. Emits `asset_scheduled`.
**Demo A2A:** `agent_visual` → `verify_brand_safety` (meme) → `agent_pr_risk` replies `brand_safety_result` (BLOCKED: spoiler + gesture) → visual regenerates → `agent_publisher` schedules; visual broadcasts `asset_status_update`.

### Skills — SKILL.md-driven advisors (cross-phase)

Each advisor runs the procedure written in `skills/<name>/SKILL.md` (Section 8): it gathers facts from `GlobalState`, runs the prerequisite phase agents above when the state is empty, then makes one Gemini call with the SKILL.md body as its system instruction. All four return the same envelope (`summary`, `highlights`, `findings`, `next_actions`, `confidence`, `data`) and run on a background thread behind `POST /api/skills/<name>/run/<project_id>`.

**`agent_casting_advisor`** — *skill `casting`.* Model: Gemini Pro. In: `role_requirements`, `scoring_weights`, `candidates`, `budget_state.cap`. Out: per-role recommendation, runners-up, budget check. Runs Phases I–II first if the pool is empty. Broadcasts `task_status_update`.

**`agent_schedule_advisor`** — *skill `scheduling`.* Model: Gemini Flash. In: `schedule.*`, `budget_state`. Out: day-load, company-move and cast-load findings, proposed moves. Runs Phase III first if the stripboard is empty. Broadcasts `task_status_update`.

**`agent_audience_analyst`** — *skill `audience-simulation`.* Model: Gemini Pro. In: `script_context.raw_text`. Out: producer's brief over the simulated panel; reuses the Phase V staged simulator (`screen_film`, `simulation_verdict_update`). Broadcasts `task_status_update`.

**`agent_cultural_researcher`** — *skill `cultural-research`.* Model: Gemini Pro + Tavily (optional). In: `script_context.raw_text`, target markets. Out: per-market risk, sourced findings, remediation. Goes through the sensitivity pass (`verify_regional_compliance` / `compliance_result`). Broadcasts `task_status_update`.

---

## 5. Intent Vocabulary

Requests/replies: `verify_regional_compliance` / `compliance_result`, `check_venue_availability` / `venue_offer`, `diagnose_engagement_anomaly` / `diagnosis_result`, `verify_brand_safety` / `brand_safety_result`, `score_candidate` / `*_scored`, `review_audition` / `audition_scored`, `scout_local_talent` / `talent_scouted`, `screen_film`, `request_audience_insights`.

Broadcasts (to orchestrator): `mandate_ready`, `candidate_ingested`, `crawl_locality_started`, `crawl_locality_completed`, `media_ready`, `leaderboard_ready`, `breakdown_ready`, `schedule_updated`, `task_status_update`, `qc_result`, `telemetry_update`, `personas_ready`, `reviews_ready`, `simulation_verdict_update`, `campaign_plan_ready`, `reel_ready`, `asset_scheduled`, `asset_status_update`, `disqualify`.

`contracts/a2a_envelope.json` and `core/messaging/envelope.py` hold the same list; a test keeps them equal.

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
7. If it writes a new `GlobalState` field or raises a new kind of escalation, add them to its phase's `owns` / `escalations` in `graph.py`, or a background run will not carry them onto the stored state.

---

## 8. Skills (SKILL.md)

A skill is a procedure an agent follows, stored at `skills/<name>/SKILL.md` in the repo root (next to `backend/`). Frontmatter: `name`, `description` (when to use it), and `metadata` (`agent`, `phase`, `model`, `owner`, `reads`, `writes`, `intents`, `version`, plus skill-specific defaults such as `panel_size` or `markets`). The Markdown body is the agent's system instruction and ends with the exact JSON shape it returns.

- Registry: `backend/core/skills/registry.py` — parsed fresh on every run, so edits need no restart.
- Runners: `backend/domains/skills/agents.py`, one per skill, keyed by `name`; every runner has an offline fallback so the zero-key demo still works. When a skill needs phase output that is not there yet (`PREPARED_PHASES`), those phase agents run on the advisor's copy and their output is merged onto the stored state before the advisory step, the same way pipeline runs merge.
- API: `GET /api/skills`, `POST /api/skills/<name>/run/<project_id>` (producer or owner), `GET /api/skills/runs/<project_id>`.
- Every run records the SKILL.md fingerprint and whether each model call was live or the fallback.
- Skill agents reuse the intent vocabulary in Section 5; adding a skill never adds an intent.
- The catalogue of every skill and shared capability, with inputs, outputs, failure modes and which agents use them, is `skills.md` at the repo root.
