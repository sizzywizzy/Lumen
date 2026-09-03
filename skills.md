# CineNode skills

This is the catalogue of every skill the agents in [`AGENT.md`](AGENT.md) rely
on, kept in step with the code. It has two parts:

- **Part A: advisor skills.** Four user-facing skills, each a
  `skills/<name>/SKILL.md` procedure run by one advisor agent. The Markdown body
  of the file is the agent's system instruction; the frontmatter names the agent
  and its defaults. The dashboard calls these **AI Advisors**.
- **Part B: shared capabilities.** The tools the Phase I to VI pipeline agents
  and the advisors call. They live under `backend/services/` and `backend/core/`
  and are not exposed as buttons.

Part C maps every agent in the registry to the skills it uses. Part D says how
to add a skill.

Every skill runs with no credentials. A missing `GEMINI_API_KEY` switches the
model step to a deterministic offline fallback computed from the same facts,
and every result records which path produced it (`provenance.mode` is `live`,
`mixed` or `mock`).

---

## Part A: advisor skills

All four share one result envelope, so the dashboard renders any of them:

```jsonc
{
  "summary": "two or three sentences",
  "highlights": ["..."],
  "findings": [{"title": "", "detail": "", "severity": "LOW|MEDIUM|HIGH", "ref": "scene / candidate / date / market"}],
  "next_actions": ["..."],
  "confidence": "low|medium|high",
  "data": { /* skill-specific, shape fixed in the SKILL.md */ }
}
```

Shared plumbing for all four:

| | |
|---|---|
| Definition | `skills/<name>/SKILL.md`, parsed by `backend/core/skills/registry.py` |
| Runner | `backend/domains/skills/agents.py` (`RUNNERS[name]`) |
| API | `POST /api/skills/<name>/run/<project_id>` (producer or owner), `GET /api/skills/runs/<project_id>` (any member) |
| Persistence | `backend/services/skill_store.py`: `backend/.state/skills/<project_id>/RUN_*.json`, or Supabase `cn_skill_runs` (`backend/schema_skills.sql`) |
| Frontend | AI Advisors page, `frontend/src/features/advisors/AdvisorsPage.jsx`, plus shortcut buttons on the Casting, Schedule and Marketing pages |
| Common failures | `SkillInputError` for a production with no usable state or material (reported as a plain message on the run); one run per skill per production at a time (HTTP 409); a run left `running` by a server restart is reported as failed on the next listing |
| A2A | The advisor broadcasts `task_status_update` at start and finish; any phase agents it invokes log their own envelopes. No new intents. |

### casting

| | |
|---|---|
| Purpose | Recommend who to cast for each role from the scored candidate pool, name the trade-offs, list what needs sign-off. |
| Agent | `agent_casting_advisor` (Gemini Pro for the synthesis step) |
| Inputs | `GlobalState`: `script_context`, `role_requirements`, `scoring_weights`, `candidates` (scores, status, quote, press review), `budget_state.cap`. No user inputs. When the pool is empty, Phase I reads the uploaded screenplay for context and roles; the candidate pool itself is still the demo pool, since nothing sources real actors. |
| Outputs | Envelope; `data.roles[]` with `recommended`, `runners_up`, `disqualified` per role; `data.budget` with cap, per-role cap, total recommended quotes, `within_cap`. |
| Tools | Structured generation (B1); the Phase I and II agents via the orchestrator (B4) when the pool is empty. |
| Constraints | Uses the pool as ranked by `composite`; never re-ranks. Never recommends a DISQUALIFIED candidate. Reasons about scores and budget only, never about identity. Per-role cap is 10% of the budget (`CASTING_CAP_SHARE`). |
| Failure conditions | No project state (404 before the run starts). A role with no viable candidate is a HIGH finding, not an error. Phase I halting on "all candidates disqualified" escalates on the state and the advisor reports the empty roles. |
| Interactions | Reads what `agent_profiler`, `agent_intake`, `agent_market_synergy`, `agent_pr_shield`, `agent_finance`, `agent_audition_analytics` and `agent_synthesis` produced. Runs them (Phases I and II) only when `candidates` is empty, so it never duplicates the pool. |

### scheduling

| | |
|---|---|
| Purpose | Review the stripboard: day load, company moves, cast load, venue cost against the location allowance, negotiated conflicts, and propose moves. |
| Agent | `agent_schedule_advisor` (Gemini Flash) |
| Inputs | `schedule.stripboard`, `schedule.conflicts`, `schedule.shoot_settings`, `schedule.director_constraints`, `budget_state`. No user inputs. When the stripboard is empty, Phase III breaks the uploaded screenplay into scenes (up to 30, mapped to the venue types the location agent can offer). |
| Outputs | Envelope; `data.day_load[]` (`OK`, `OVER`, `UNDER` per date), `data.cost` (daily burn vs allowance), `data.proposed_moves[]`, `shoot_days`, `total_hours`. |
| Tools | Structured generation (B1); Phase III via the orchestrator (B4) when the stripboard is empty. |
| Constraints | Day arithmetic is computed in code and handed to the model as `computed`; the model may not recompute or invent dates, venues or costs. Allowance is 15% of the cap spread over shoot days (`LOCATIONS_SHARE`). |
| Failure conditions | No project state. An empty stripboard after Phase III (no venues at all) yields zero shoot days and an escalation already on the state. |
| Interactions | Reads `agent_breakdown`, `agent_location` and `agent_scheduler_shoot` output, including the counter-offers they negotiated. Director constraints set on the Settings page change what Phase III builds. |

### audience-simulation

| | |
|---|---|
| Purpose | Screen the stored screenplay with a synthetic panel and write the producer's brief: who responds, who drops off, what to test in a real screening. |
| Agent | `agent_audience_analyst` (Gemini Pro), on top of the Phase V staged simulator |
| Inputs | `script_context.raw_text` (the screenplay from Script Intake) or, failing that, a brief rendered from the project's script context. User inputs: `panel_size` (20 to 1000, default 200), optional `seed`. |
| Outputs | Envelope; `data` with panel size, overall score, would-watch and would-recommend rates, strongest and weakest segments, dimension means, polarizing elements, test-screening questions. |
| Tools | Audience panel builder (B6), staged simulator stages analyse, build_panel, simulate_cohorts, derive_individuals, aggregate, pr_recommendations (B1 for the model calls). The market scan is skipped here and belongs to cultural-research. |
| Constraints | The brief must say "the simulated panel", never predict box office, copy scores exactly, and treat segments as taste cohorts. A logline-only material sets confidence to low. About ten model calls when live; one to two minutes. |
| Failure conditions | No material at all raises `SkillInputError` with the instruction to upload a script. Individual cohort batches that fail are surfaced in the trace, not fatal. |
| Interactions | Emits the Phase V traffic (`screen_film`, `simulation_verdict_update`, `request_audience_insights`, `campaign_plan_ready`) through `agent_persona_foundry`, `agent_viewer`, `agent_aggregation` and `agent_campaign_strategist`. Independent of the Audience Simulation tab on the Marketing page, which keeps its own run history. |

### cultural-research

| | |
|---|---|
| Purpose | Research how the screenplay's content may land in each release market and brief the localisation team with findings that separate research from inference. |
| Agent | `agent_cultural_researcher` (Gemini Pro, plus Tavily when configured) |
| Inputs | The screenplay or project brief; `compliance_state` for context. User input: `markets` (one or more of the codes in `core/audience/personas.py`; default US, IN, GB, AE, JP). |
| Outputs | Envelope; `data.markets[]` with risk level, researched vs interpreted counts, top finding and remediation; `data.sources[]` (url per market); `data.verify_with_distributor[]` when research was off. |
| Tools | Structured generation (B1) for the material analysis and the brief; the Phase V sensitivity pass (`audience_sim.cultural_scan`); web research (B2). |
| Constraints | Never states that a culture holds one opinion. Every finding traces to `content_detected`. A market with nothing to flag is reported as "no notable concern", never invented. Unknown market codes are rejected with HTTP 422. |
| Failure conditions | No material. Tavily down or unconfigured is not an error: findings are marked `ai_interpretation` and confidence drops to low. |
| Interactions | Sends `verify_regional_compliance` from `agent_localization` and gets `compliance_result` from `agent_pr_risk`, the same pair Phase IV uses. |

---

## Part B: shared capabilities

### B1. Structured generation

| | |
|---|---|
| Code | `backend/services/gemini_client.py` (`generate_json`, `generate_json_traced`, `map_concurrent`) |
| Purpose | The only place model calls happen. Gemini JSON mode, Flash by default, Pro for heavy reasoning, fallback models on 404/429/503, bounded concurrency. |
| Used by | Every agent with a model tier in `AGENT.md`; all four advisors. |
| Inputs | Prompt, optional system instruction, tier, a `mock` value. |
| Outputs | Parsed JSON, plus a trace (`source`, `model`, `attempts`, `fell_back`). |
| Dependencies | `google-genai`, `GEMINI_API_KEY`, `GEMINI_FLASH_MODEL`, `GEMINI_PRO_MODEL`, `GEMINI_FALLBACK_MODELS`, `GEMINI_TIMEOUT_MS`, `GEMINI_MAX_CONCURRENCY`. |
| Constraints | Never parse prose (AGENT.md guardrail). Callers supply a mock so the zero-key demo runs. |
| Failure | With no key: the mock is returned and labelled `source: mock`. With a key and every model failing: the mock if one exists, else `GeminiUnavailable`. |

### B2. Web research

| | |
|---|---|
| Code | `backend/services/tavily_client.py` (`search`, `research_market`) |
| Purpose | Ground the cultural sensitivity pass in fetched sources with URLs. |
| Used by | `agent_cultural_researcher`; the Phase V cultural scan inside audience simulations. |
| Inputs | Market name and genre hint. |
| Outputs | `{query, results: [{title, url, content}]}`. |
| Dependencies | `TAVILY_API_KEY`; urllib only, no package. |
| Failure | Never raises. Unconfigured or failed lookups return an empty result set and the agents label their findings as interpretation. |

### B3. A2A messaging

| | |
|---|---|
| Code | `backend/core/messaging/envelope.py` (`make_envelope`, `make_reply`, `broadcast`, `log_event`) |
| Purpose | The one message shape every agent uses, validated against the intent vocabulary in `AGENT.md` Section 5 and `contracts/a2a_envelope.json`. |
| Used by | Every agent, including the advisors. |
| Constraints | An unknown intent raises; adding one requires a contract change agreed by the team. |
| Interactions | Everything logged lands in `GlobalState.event_log`, which the Live Agent Terminal replays. |

### B4. Orchestration

| | |
|---|---|
| Code | `backend/core/orchestrator/graph.py` (`Orchestrator`, `PhaseNode`) |
| Purpose | Runs phases in order with fail-fast edges; the advisors call it for a single phase range when their inputs are empty. |
| Used by | `agent_director_orchestrator`; `POST /api/pipeline/run`; `/api/casting/run`, `/api/production/run`, `/api/launch/run`; casting and scheduling advisors. |
| Failure | A fail-fast edge halts the range and pushes a `human_escalations` item instead of raising. |

### B5. State persistence

| | |
|---|---|
| Code | `backend/services/supabase_client.py` (`save_state`, `load_state`, `list_projects`) |
| Purpose | One `GlobalState` per production; Supabase `global_state` or `backend/.state/PROJ_*.json`. |
| Used by | Every router and every advisor run (load at start, save at end). |
| Constraints | `CINENODE_STATE_BACKEND` = `auto`, `supabase` or `local`. Membership is checked by the routers before any load. |

### B6. Audience panel building

| | |
|---|---|
| Code | `backend/core/audience/personas.py` (`build_panel`, `build_cohorts`, `MARKETS`) |
| Purpose | Seeded synthetic personas from a configurable distribution, grouped into cohorts; also the list of release markets the UI offers. |
| Used by | `agent_persona_foundry`, `agent_viewer`, `agent_aggregation`; the audience analyst and cultural researcher (market list). |
| Constraints | Deterministic per seed so runs can be compared after a script revision. |

### B7. Mock databases

| | |
|---|---|
| Code | `backend/services/mock_db.py` over `backend/mock_data/*.json` |
| Purpose | Script breakdown, candidates, venues, actor availability, censorship rules, clearances and persona seeds for the zero-key demo. |
| Used by | `agent_profiler`, `agent_intake`, `agent_breakdown`, `agent_location`, `agent_scheduler_shoot`, `agent_rights_clearance`, `agent_localization`, `agent_persona_foundry`. |
| Constraints | Read-only, cached per process. |

### B8. Screenplay intake

| | |
|---|---|
| Code | `backend/services/script_intake.py`, `POST /api/production/script/<project_id>` |
| Purpose | Extract text from .txt, .fountain, .fdx or .pdf into `script_context.raw_text`. |
| Used by | Audience analyst, cultural researcher, the Phase V simulator. |
| Dependencies | `pypdf` for PDFs only. `SCRIPT_ANALYSIS_MAX_CHARS` (default 120,000) bounds how much of the text each model read receives. A pipeline run keeps the uploaded text; only a new upload replaces it. |
| Failure | `ScriptExtractionError` becomes HTTP 422 at upload time. |

### B9. Actor knowledge base

| | |
|---|---|
| Code | `backend/services/casting_kb/` (`ingest`, `embeddings`, `matching`), `backend/migrations/001_actor_knowledge_base.sql` |
| Purpose | TMDb ingestion and semantic search over actors for Phase I sourcing. |
| Used by | Casting endpoints `/api/casting/actors/*`; not required by the advisors. |
| Dependencies | `DATABASE_URL` or Cloud SQL variables, `TMDB_API_KEY`, `sentence-transformers`, `psycopg`. |
| Failure | Endpoints answer 503 when the database is not configured. |

### B10. Run stores

| | |
|---|---|
| Code | `backend/services/skill_store.py` (advisor runs), `backend/services/simulation_store.py` (audience simulations) |
| Purpose | Immutable-once-complete run records with stage progress and provenance. |
| Constraints | Local saves are atomic (write then rename) because the dashboard polls while the worker writes. |

### B11. PR gate

| | |
|---|---|
| Code | `_pr_risk_check` in `backend/domains/launch/agents/phase6_marketing.py` |
| Purpose | Spoiler and brand-safety verdict on a single asset draft. |
| Used by | `agent_visual` (memes, with regeneration) and `agent_copywriter` (copy and press release, escalated on block). |
| Constraints | Bounded retries (`MAX_ASSET_REGENERATIONS`). |

---

## Part C: agent to skill map

| Agent | Skills and capabilities |
|---|---|
| `agent_director_orchestrator` | B4, B3, B5 |
| `agent_profiler` | B1 (Pro), B7 |
| `agent_intake` | B7, B3 |
| `agent_market_synergy` | B3 (hype from follower count) |
| `agent_pr_shield` | B1 (Flash), B3 |
| `agent_finance` | B3 (per-role cap from `budget_state.cap`) |
| `agent_media_proc` | stub: emits `media_ready` with 720p and transcript pointers; FFmpeg and Whisper are not wired |
| `agent_audition_analytics` | B1 (Pro) |
| `agent_synthesis` | composite scoring, B3 |
| `agent_breakdown` | B7, B3 |
| `agent_location` | B7, B3 (`venue_offer`) |
| `agent_scheduler_shoot` | B7, B3, bounded negotiation (`MAX_NEGOTIATION_ITERATIONS`) |
| `agent_rights_clearance` | B7 (censorship rules, clearances), B3 |
| `agent_localization` | B3; also the sender of the advisors' market scan |
| `agent_qc` | stub: fixed PASS verdict |
| `agent_telemetry` | stub: fixed pre-launch metrics |
| `agent_persona_foundry` | B6, B7 |
| `agent_viewer` | B1 (Flash, batched) or seeded scores in the pipeline demo |
| `agent_aggregation` | aggregation in code, B1 (Pro) for the recut diagnosis request |
| `agent_critic` | B1 (Flash) |
| `agent_recut_advisor` | B1 (Pro) |
| `agent_campaign_strategist` | B1 (Flash) |
| `agent_reel_cutter` | picks the top-scored scene; still-sequence stub |
| `agent_visual` | B1 (Flash), B11 |
| `agent_copywriter` | B1 (Flash), B11 |
| `agent_pr_risk` | B11; B1 (Pro) in the sensitivity pass |
| `agent_publisher` | mock social APIs, B3 |
| `agent_casting_advisor` | A: casting |
| `agent_schedule_advisor` | A: scheduling |
| `agent_audience_analyst` | A: audience-simulation |
| `agent_cultural_researcher` | A: cultural-research |

The three stubs are deliberate: `AGENT.md` lists no model for them and the demo
runs with no media pipeline. Replacing them means implementing the service, not
changing the agent contract.

---

## Part D: adding a skill

1. Create `skills/<name>/SKILL.md` with `name`, `description`, `metadata`
   (`title`, `cta`, `agent`, `phase`, `model`, `owner`, `reads`, `writes`,
   `intents`, `version`, any defaults) and a body that ends with the exact
   JSON the agent returns, using the shared envelope above.
2. Add a runner in `backend/domains/skills/agents.py` and register it in
   `RUNNERS`; add its stage list to `STAGES`; declare any user inputs in
   `input_schema` and validate them in `SkillRunParams` in the router.
3. Give the runner an offline fallback built from the same facts.
4. Register the agent id in `AGENT.md` Section 4 and add a row to Part C here.
5. The AI Advisors page picks the new skill up from `GET /api/skills` with no
   frontend change.
