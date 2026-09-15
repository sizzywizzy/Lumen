# TODO

Open bugs and the feature backlog, roughly in priority order. Paths and line
numbers were last checked against the working tree on 16 September 2026,
when all 139 backend tests passed offline and the frontend built cleanly.
The first ten items from the September 2026 backend audit are fixed and
covered by tests: Supabase auth lookups, lost simulation writes,
unauthenticated actor-KB routes, the missing `.dockerignore`, phase re-runs,
cast-aware scheduling, venue-day costing, distribution validation, the model
tier, and guards on malformed model output.

## Bugs

### Correctness

- [ ] **Scout accepts any role id from a live model.**
  `backend/domains/casting/agents/agent_scout.py:234` keeps whatever `role_id`
  the reply contains, so a candidate on a phantom role gets locked by synthesis.
  Validate against `state.role_requirements` and fall back to the round-robin pick.
- [ ] **Message ids restart at 1 per process.**
  `backend/core/messaging/envelope.py:15` counts from 1 while the event log is
  persisted, so runs after a restart reuse ids, which breaks `in_reply_to`
  links and the React keys in the Agent Log. Use a uuid or a per-state sequence.
- [ ] **A seed of 0 is silently replaced.**
  `backend/domains/skills/agents.py:598` uses `or`; test for `None` instead.
- [ ] **Two sources of truth for the budget.**
  `backend/core/orchestrator/state.py:56` seeds every production with a 100k
  `total_budget` and three placeholder expenses ($34,700) beside the real
  `cap`, and `backend/domains/auth/router.py:102` writes that ledger for every
  new account. The Settings page edits the ledger rather than the cap
  (`frontend/src/features/production/DirectorControls.jsx:20` and
  `backend/domains/production/router.py:22` both default it to 100k), while
  the Overview works out what is left from `cap`, so the two pages disagree.
  Derive `total_budget` from `cap`, start the expense list empty, and have
  Settings edit the cap.
- [ ] **Phase IV injects the demo music asset for real scripts.**
  `backend/domains/production/agents/phase4_compliance.py:52` hardcodes
  `TRK_992_INDIE_ROCK` on `SCN_004`. Take cleared assets from the breakdown.
- [ ] **Phase V viewers are hash-seeded and segmented by gender.**
  `backend/domains/launch/agents/phase5_audience.py:18` hardcodes an 18-24 male
  anomaly on hash-seeded scores, and line 30 reads `mock_data/personas.json`,
  which contradicts the no-sensitive-attributes rule the persona tests enforce.
  Only the recut diagnosis and the critic reviews call Gemini. Reuse
  `core/audience/personas.py` and the cohort simulator in `audience_sim.py`.
- [ ] **Interrupted audience simulations stay "running" forever, and a run can be double-started.**
  `start_simulation` at `backend/domains/audience/router.py:226` has no
  active-run set and no 409 guard; mirror `_ACTIVE` and `_ACTIVE_RUNS` from
  `backend/domains/skills/router.py:35`.
- [ ] **Saves overwrite each other.**
  The per-production lock in `backend/services/supabase_client.py:24` covers
  background workers only. Candidate status
  (`backend/domains/casting/router.py:132`) and settings, expenses, shoot-day
  edits and script upload (`backend/domains/production/router.py:70`, `:91`,
  `:102`, `:122`) each load, modify and save without it, so two producers
  editing at once can lose an edit. The phase-run endpoints are worse:
  `casting/router.py:59`, `production/router.py:54` and
  `backend/domains/launch/router.py:14` hold their copy for the whole run and
  save it back, dropping every edit and every advisor or simulation envelope
  saved in the meantime. Wrap the handlers in `project_lock`, and merge run
  output onto the stored state the way `append_events` does.

### Robustness and operations

- [ ] **Every state read ships the full screenplay and event log.**
  `backend/main.py:152` returns the whole model, including `raw_text` of up to
  400k characters and a log that grows about 100 KB per run. The settings and
  shoot-day routes return it too (`backend/domains/production/router.py:87`,
  `:118`), and the casting routes return the whole log. The dashboard fetches
  state on load and after every pipeline or advisor run; nothing polls it on a
  timer any more, and nothing calls the paged `/api/events` route
  (`frontend/src/lib/api.js:136`). Strip `raw_text` from these responses and
  page or cap the event log.
- [ ] **Synchronous pipeline endpoints.**
  `backend/main.py:125`, `backend/domains/casting/router.py:70`,
  `backend/domains/production/router.py:57` and
  `backend/domains/launch/router.py:17` run every model call inside the
  request, so a live run is a multi-minute HTTP call with no timeout handling.
  The New script page waits on the whole pipeline in one request
  (`frontend/src/shared/ProjectContext.jsx:181`). Run them like advisor runs:
  answer 202 and poll.
- [ ] **Hardcoded GCP project and a silent Vertex path.**
  `backend/core/config.py:101` ships a project id, and `has_gemini` at line 122
  is true whenever gcloud credentials exist, so the "zero-key" run makes Vertex
  calls (`backend/services/gemini_client.py:48`) and only falls back after they
  fail. `docker-compose.yml:9` mounts the host's gcloud folder, so compose does
  the same. Require an explicit opt-in and drop the default project id. The
  `.env` loader at `config.py:20` also keeps quotes around values.
- [ ] **The Cloud Run deploy path is broken and fights the single-instance design.**
  The README documents Render + Vercel; the older GCP files contradict it.
  `cloudbuild.yaml:35` and `deploy-cloudrun.sh:32` allow ten instances and
  scale to zero with CPU throttled between requests, which splits background
  runs and the project lock across processes and stalls them after the 202.
  `deploy-cloudrun.sh:35` escapes `\$GEMINI_API_KEY` and the other keys, so the
  service receives the literal text instead of the values. Neither sets
  `LUMEN_STATE_BACKEND=supabase` or `LUMEN_CORS_ORIGINS`. The frontend image
  is built without `VITE_API_URL` and its `/api` proxy is commented out
  (`frontend/nginx.conf:16`), so the deployed site cannot reach the API. Its
  `node:18-alpine` base (`frontend/Dockerfile:4`) is below React Router 7's
  Node 20 minimum, and with no `frontend/.dockerignore` the build uploads
  `node_modules` as context.
  `GCP_DEPLOYMENT.md:136` checks `/health` (the route is `/api/health`), and
  line 79 names only `schema_auth.sql` of the three schemas. Delete the GCP
  path, or fix it to run one always-on instance.
- [ ] **Local JSON stores are not crash-safe.**
  `backend/services/auth_store.py:63` and `backend/services/simulation_store.py:45`
  (and `:91` for panels) write in place, and reads skip the lock; use the
  write-then-rename pattern that `supabase_client.save_state` already uses.
- [ ] **Compose never mounts `skills/`.**
  `docker-compose.yml:8` mounts only `backend`, so the Advisors page is empty
  under compose. Mount `./skills:/skills` or set `LUMEN_SKILLS_DIR`.
- [ ] **`generate_actor_embeddings.py` cannot run directly.**
  `backend/scripts/generate_actor_embeddings.py:4` needs the `sys.path` shim
  that `reset_password.py` has.
- [ ] **Small validation gaps.** `ProductionSettings` accepts any hours per day
  (`backend/domains/production/router.py:20`); shoot-day dates are unvalidated
  strings (`:40`); the audience route rejects lowercase market codes
  (`backend/domains/audience/router.py:235`) while the skills route uppercases
  them; registering the same email twice at the same moment fails on the
  Supabase unique constraint with a 500 instead of a 409, and writes a
  duplicate user row on local JSON.

### Security

- [ ] **No rate limiting on sign-in.** Each attempt costs a 600k-iteration
  PBKDF2 hash, and `backend/domains/auth/router.py:113` computes an extra
  throwaway hash for unknown emails. Add a per-IP limiter and cache the dummy hash.
- [ ] **Harden `.fdx` parsing.** `backend/services/script_intake.py:43` parses
  untrusted uploads with stdlib ElementTree. Expat 2.4.1 and later already
  stops billion-laughs expansion, so this is defence in depth: parse with
  `defusedxml` to refuse DTDs outright.

### Small

- [ ] Dead code after `return True` in `backend/core/config.py:168`.
- [ ] `run_demo.py --budget 0` raises `ZeroDivisionError` at
  `backend/domains/casting/agents/phase1_precasting.py:195`; the API already rejects it.
- [ ] `backend/domains/casting/router.py:69` clears candidates before Phase I,
  which Phase I now does itself (`phase1_precasting.py:214`).
- [ ] `make test` never runs the test suite. `Makefile:35` compiles the backend
  and runs the demo, which overwrites the stored `PROJ_NEON_NIGHTS` state (in
  Supabase, when `.env` points there), and `make install` skips
  `requirements-dev.txt`. Run `pytest` instead.
- [ ] Dead frontend code: nothing imports `frontend/src/shared/AppShell.jsx`, so
  `Sidebar.jsx` (used only by AppShell) is dead too, as is `api.getEvents`, and
  the header of `shared/navigation.js` still says it drives the sidebar and the
  route table. Take the sign-off queue markup from `AppShell.jsx:131` first
  (see the agent-layer feature below).
- [ ] Stale comments: `backend/main.py:6` says the terminal polls `/api/events`;
  `backend/core/config.py:6` says only Gemini and Supabase are read (TMDb,
  Postgres and Vertex are too); `config.py:53` says Cloud SQL takes precedence
  over Supabase, but it only backs the actor KB (`services/casting_kb/db.py:15`).

## Features and tasks

### Promised by the README

- [ ] **Captures.** `assets/screenshots/` holds only `.gitkeep`: add
  `01-intake.png` (New script), `02-pipeline.png` (Overview or Schedule),
  `03-terminal.png` (`/logs`) and `pipeline.gif`, uncomment the embeds, and
  delete the "captures pending" note.
- [ ] **Hosted demo.** Create the Supabase project and run the three
  `backend/schema_*.sql` files, deploy the API to Render from `render.yaml`,
  deploy the frontend to Vercel with `VITE_API_URL`, set `LUMEN_CORS_ORIGINS`,
  then link the result from the README.

### Features

- [ ] **Put the agent layer back into the redesigned site.** The menu
  (`frontend/src/shared/AppLayout.jsx:9`) has Overview, Schedule, Cast and
  Audience. Everything that shows the agents at work is reachable only by
  typing its address: the Live Agent Terminal (`/logs`), the compliance matrix
  (`/production`), the marketing assets and the Gemini-backed audience
  simulator (`/marketing`), and the AI Advisors (`/advisors`). No reachable
  page shows the sign-off queue (`human_escalations`); the only component
  that rendered it is the unused `AppShell.jsx`. The README's pitch ("humans
  only sign off at the top") and half of its demo walkthrough depend on these
  screens. Link them from the menu or the results pages, show the queue, and
  delete whichever older tools are no longer wanted.
- [ ] **Phase V live viewers.** `agent_viewer` verdicts are hash-seeded (see the
  bug above); the Audience Analyst advisor already runs the Gemini-backed
  cohort simulator in `backend/domains/launch/agents/audience_sim.py`, so the
  pipeline phase should reuse it rather than grow its own.
- [ ] **The backend fundamentals the bugs above already ask for:** registration
  as one transaction (three writes plus the state seed today), every save under
  the project lock, ETag or delta responses for the state and event reads, and
  202-plus-poll for the pipeline endpoints.

### Not planned

Cut on purpose: each costs money or prep time and adds nothing to the
system's logic.

- Rendered media in Phase VI (Imagen, Veo, Lyria). `agent_visual` and
  `agent_reel_cutter` produce art-direction specs that go through the PR gate.
- Tape decoding and transcription in Phase II (FFmpeg, Whisper).
  `agent_media_proc` passes the tape reference through.
- A LangGraph or Google Cloud Agent Builder rewrite of the orchestrator. The
  explicit state machine in `backend/core/orchestrator/graph.py` stays.
- Billing, workspace transfers and further team administration: a second
  production, leaving one, role changes, ownership transfer, self-service
  password reset, expense editing. The invite flow that exists is complete
  and tested, and that is where it stops.
- Cloud Storage for media.

### Documentation

- [ ] **Bring `AGENT.md` up to date with the code.**
  - Section 4: register `agent_casting_scout` (Phase I) and
    `agent_script_analyst` (the audience simulator), and add the
    `cast_unavailable` conflict reason and the `schedule:cast` queue item to
    Phase III.
  - Section 5: add `scout_local_talent` / `talent_scouted`,
    `crawl_locality_started` and `crawl_locality_completed`, which
    `contracts/a2a_envelope.json` and `envelope.py` already accept.
  - Line 19 still names Gemini 2.0 Flash and Pro; both tiers default to
    `gemini-3.6-flash` (`backend/core/config.py:70`).
  - `agent_audition_analytics` (line 107) still takes a "720p clip +
    transcript", which no longer exists, and `agent_persona_foundry` and
    `agent_viewer` (lines 137 and 139) are listed as Gemini Flash though both
    are seeded today.
- [ ] Keep `skills.md` and `AGENT.md` Section 8 in step when advisor inputs change.
