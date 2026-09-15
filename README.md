<p align="center">
  <img src="assets/logo.svg" alt="Lumen" width="360" />
</p>

<p align="center">
  <a href="https://github.com/sizzywizzy/Lumen/actions/workflows/ci.yml">
    <img src="https://github.com/sizzywizzy/Lumen/actions/workflows/ci.yml/badge.svg" alt="CI status" />
  </a>
</p>

# 🎬 Lumen

> **Lumen is an autonomous film studio in software.** Give it a screenplay and a
> budget, and six cooperating AI agents cast it, schedule the shoot, clear rights
> per territory, test-screen it with 200 synthetic viewers, and plan the launch,
> negotiating with each other over one shared protocol while humans only sign
> off at the top.
>
> Started as a three-person entry to **Agentic Cinema: The Blockbuster Hackathon**,
> now carried solo: FastAPI · React · Gemini · 19k lines · tested, with CI on
> every push.

Lumen is a network of specialized AI agents that run the entire film lifecycle as **six connected phases** — casting, auditions, scheduling, compliance, audience testing, and marketing — sharing **one orchestrator, one state object, and one agent-to-agent (A2A) messaging standard**. Scale follows the budget you enter at intake: casting caps, venue choices and territory reach all derive from it.

It is a true **Multi-Agent System (MAS)**: agents ask each other questions, get answers, and change their own behavior — humans only sign off at the top.

---

## See it

> **Captures pending.** Save the files at the paths below and uncomment the
> embeds — no other edit needed. Delete this note once they're in.
> No hosted demo link yet: add one here once the [Deploy](#deploy) steps are
> done. Until then, run it locally with [Getting Started](#getting-started)
> (works with an empty `.env`).

| Slot | Save as | Should show |
|---|---|---|
| Screenshot 1 | `assets/screenshots/01-intake.png` | **New script** (`/new`) — screenplay dropped, budget and shooting dates filled in |
| Screenshot 2 | `assets/screenshots/02-pipeline.png` | The results after a run — the **Overview** or the day-by-day **Schedule** |
| Screenshot 3 | `assets/screenshots/03-terminal.png` | Live Agent Terminal (`/logs`) scrolling the A2A envelopes |
| GIF | `assets/screenshots/pipeline.gif` | ~10s of `run_demo.py` streaming all six phases (see recipe below) |

<!-- Uncomment once the files above exist:
![New script — screenplay, budget and shooting dates](assets/screenshots/01-intake.png)
![The results of a run](assets/screenshots/02-pipeline.png)
![Live Agent Terminal streaming A2A envelopes](assets/screenshots/03-terminal.png)
![The six-phase pipeline running end to end](assets/screenshots/pipeline.gif)
-->

<details>
<summary>Recording the pipeline GIF</summary>

The terminal run is the clearest proof it's a real MAS — 150 A2A messages
across six phases, no keys required:

```bash
cd backend
python -u run_demo.py --project PROJ_NEON_NIGHTS --budget 250000 --verbose
```

Record that with any terminal recorder (`asciinema rec` + `agg`, `vhs`, or a
screen capture) and save the result as `assets/screenshots/pipeline.gif`.
Keep it under ~10s and start at `[PHASE1]` so the phase banners are the first
thing on screen.
</details>

---

## The Problem

Turning a screenplay into a finished, marketed film is a two-week-per-step manual grind: breaking down scenes, vetting cast, solving the scheduling constraint puzzle, clearing rights for every territory, guessing at audience reaction, and building a campaign. Every step is a bottleneck, and they don't talk to each other.

## The Solution — Six Phases, One Brain

| Phase | Name | What it does |
|---|---|---|
| **I** | Pre-Casting Intelligence & Compliance | Turns script + brief into casting mandates; fail-fast filters applicants on PR/budget risk |
| **II** | Audition Analysis & Scorecard | Grades performances into a composite leaderboard (no tape decoding: auditions are judged from the role brief and the tape reference) |
| **III** | Script → Schedule | Breaks down scenes, matches venues, builds the stripboard + burn-rate budget |
| **IV** | Compliance, Localization & Launch Prep | Clears rights, localizes/censors per territory, runs QC |
| **V** | Audience Simulation & Predictive Reviews | 200 synthetic viewers screen the cut → Tomatometer + fix suggestions (verdicts are hash-seeded; the Audience Analyst advisor is the Gemini-backed simulator) |
| **VI** | Marketing, PR & Autonomous Social Launch | Plans reels/memes/posters + copy, PR-gates each one, schedules the rollout (assets are art-direction specs by design, not rendered media) |

Full spec and agent contracts: see [`AGENT.md`](./AGENT.md). Shared schemas live in [`contracts/`](./contracts); advisor procedures in [`skills.md`](./skills.md).

---

## Architecture

```
                        ┌─────────────────────────────┐
                        │  agent_director_orchestrator │   phase DAG runner
                        │  (owns GlobalState, routing) │   + fail-fast edges
                        └──────────────┬──────────────┘
                                       │  reads/writes
                        ┌──────────────▼──────────────┐
                        │        GlobalState (JSON)     │  local .state/ or Supabase
                        └──────────────┬──────────────┘
                                       │
   PHASE I → PHASE II → PHASE III → PHASE IV → PHASE V → PHASE VI
   (each phase = a subgraph of agents; all speak the same A2A envelope)
```

- **Orchestration:** an explicit state machine in `backend/core/orchestrator/graph.py`, written from scratch rather than on a framework: every phase is a node, a conditional edge after a phase can halt the run with a human escalation, each phase owns and resets its own output so a re-run replaces rather than stacks, and all of it is unit-tested without a model call.
- **Every agent** communicates via the standard A2A envelope (`sender`, `recipient`, `intent`, `payload`).
- **A "Live Agent Terminal"** in the UI (`/logs`) lists every one of these JSON messages, filterable by agent and payload — the proof it's a real MAS. Since the site redesign it has no menu entry (see [`TODO.md`](./TODO.md)).

---

## Tech Stack

Everything below is wired into code today. Where a key is absent the pipeline
falls back to a deterministic mock, so the whole thing runs with an empty `.env`.

| Layer | Choice | Where it lives |
|---|---|---|
| Orchestration | Plain-Python phase DAG with fail-fast edges | `backend/core/orchestrator/graph.py` |
| Reasoning LLM | **Gemini** via `google-genai` — `gemini-3.6-flash` by default, a separate Pro model for the heavy-reasoning steps, and a fallback chain | `backend/services/gemini_client.py` |
| Web search | **Tavily** REST (no SDK — `urllib`); optional, skipped when unset | `backend/services/tavily_client.py` |
| Actor knowledge base | **TMDb** ingest → **PostgreSQL + pgvector**, `sentence-transformers` embeddings (optional extra) | `backend/services/casting_kb/` |
| Script intake | **pypdf** for the PDF branch (`.txt`/`.fountain`/`.fdx` need no package) | `backend/services/script_intake.py` |
| Persistence + Auth | **Supabase** (Postgres) when `SUPABASE_URL`/`KEY` are set, else local JSON under `backend/.state/` | `backend/services/{supabase_client,auth_store,simulation_store,skill_store}.py`, `backend/schema_*.sql` |
| Backend | **Python 3.10+ · FastAPI · Pydantic v2 · Uvicorn** | `backend/main.py` |
| Frontend | **React 18 · React Router · Vite**, hand-rolled CSS design system (custom properties, `data-theme` light/dark) | `frontend/src/` |
| Hosting | **Vercel** serves the React build · **Render** runs the API container · **Supabase** holds the data | `frontend/vercel.json`, `render.yaml`, `Dockerfile` |
| Secrets | `.env` locally · Render environment variables when deployed; the frontend holds none | `.env.example`, `render.yaml` |

**Deliberately out of scope.** Rendered media and third-party orchestration
add cost without adding to the system's logic, so they are not planned: no
image, video or music generation (`agent_visual` and `agent_reel_cutter`
produce art-direction specs that go through the PR gate), no tape decoding
or transcription (`agent_media_proc` passes the tape reference through), and
no LangGraph or Google Cloud Agent Builder (the orchestrator is an explicit
state machine, see Architecture). Still open is live viewers inside the
pipeline's Phase V: `agent_viewer` verdicts are hash-seeded today, while the
Audience Analyst advisor already runs the Gemini-backed simulator. Open bugs
and the feature backlog are tracked in [`TODO.md`](./TODO.md).

---

## Repository Structure

```
lumen/
├── README.md
├── TODO.md                      # open bugs and the feature backlog
├── AGENT.md                     # agent registry, A2A + GlobalState contracts
├── skills.md                    # advisor catalogue + agent-to-skill map
├── assets/                      # logo + brand
│   └── screenshots/             # README captures + pipeline GIF
├── design/                      # design-canvas prototype of the cover → Phase I flow
├── skills/                      # SKILL.md procedures the advisor agents follow (skills/README.md)
├── contracts/                   # shared JSON schemas every agent depends on — change with care
│   ├── a2a_envelope.json
│   └── global_state.json
├── .github/workflows/ci.yml     # tests + frontend build on every push
├── backend/
│   ├── main.py                  # FastAPI entrypoint (mounts one router per domain)
│   ├── run_demo.py              # CLI: full pipeline on mock data
│   ├── schema_*.sql             # Supabase tables: auth, advisor runs, state + simulations
│   ├── tests/                   # pytest, offline: contracts, phases, stores, workers, auth
│   ├── migrations/              # PostgreSQL/pgvector schema (actor KB)
│   ├── scripts/                 # one-off maintenance scripts
│   ├── core/                    # THE BRAIN — shared by every domain
│   │   ├── config.py            # env vars, model tiers, guardrail constants
│   │   ├── llm_output.py        # coerces model replies; a bad field falls back to the mock
│   │   ├── scenes.py            # plain-language scene headings, titles and summaries
│   │   ├── shoot_window.py      # shooting-window checks shared by intake and the scheduler
│   │   ├── orchestrator/
│   │   │   ├── graph.py         # phase DAG + fail-fast edges
│   │   │   └── state.py         # GlobalState Pydantic models
│   │   ├── messaging/envelope.py  # A2A envelope helper (shared by ALL agents)
│   │   ├── audience/            # synthetic-viewer simulation engine
│   │   ├── auth/                # sessions, invites, memberships
│   │   └── skills/              # SKILL.md loader + runner
│   ├── services/                # gemini_client, tavily_client, supabase_client,
│   │                            #   auth_store, simulation_store, skill_store,
│   │                            #   script_intake, mock_db, casting_kb/
│   ├── mock_data/               # script, candidates, venues, censorship rules, personas
│   └── domains/                 # THE SANDBOXES — one per product area
│       ├── casting/             # Phases I & II: router, agents/, prompts
│       ├── production/          # Phases III & IV
│       ├── launch/              # Phases V & VI
│       └── audience/ auth/ skills/   # cross-cutting routers
├── frontend/
│   ├── vercel.json              # Vercel: every route falls back to index.html
│   ├── Dockerfile, nginx.conf   # static image for the older Cloud Run path
│   └── src/
│       ├── App.jsx              # routes: public site, results pages, older tools
│       ├── features/
│       │   ├── site/            # public homepage, drawn from the built-in sample production
│       │   ├── intake/          # New script (/new): upload, budget, shooting dates → full run
│       │   ├── results/         # Overview · Schedule · Cast · Audience (the menu)
│       │   ├── auth/ team/ settings/
│       │   └── casting/ production/ launch/ advisors/ logs/
│       │                        #   older tools: routed by address, not in the menu
│       ├── shared/              # site layout, LiveAgentTerminal + AgentLog, UI parts
│       ├── theme/               # light/dark token provider
│       └── lib/                 # api.js (VITE_API_URL), production.js (results selectors),
│                                #   sample.js, utils.js
├── Dockerfile                   # API image; Render builds it from render.yaml
├── .dockerignore                # keeps .state/, .env and caches out of the image
├── render.yaml                  # Render Blueprint for the API
├── docker-compose.yml
├── Makefile                     # install, build, dev servers, API docs
├── GCP_DEPLOYMENT.md            # older Cloud Run path with cloudbuild.yaml and
│                                #   deploy-*.sh; out of date (see TODO.md)
└── .env.example
```

**Zero-key dev loop:** every agent has a mock fallback, so the entire six-phase
pipeline runs before any API key exists — `python backend/run_demo.py` just works.

---

## Getting Started

### Prerequisites
- Python 3.10+, Node 20+ (React Router 7's minimum)
- Nothing else. Every key below is optional — with an empty `.env` the full
  six-phase pipeline still runs on mock fallbacks.

### 1. Configure environment
Copy `.env.example` to `.env`. All of these are optional:

```bash
GEMINI_API_KEY=...         # live agent reasoning; mock fallbacks work without it
TAVILY_API_KEY=...         # web-grounded cultural/censorship research; skipped when unset
SUPABASE_URL=...           # shared persistence; without it state goes to backend/.state/
SUPABASE_KEY=...           #   required once deployed (see Deploy)
DATABASE_URL=...           # Phase I actor KB only (PostgreSQL + pgvector)
TMDB_API_KEY=...           # Phase I actor KB only
GEMINI_PRO_MODEL=...       # optional: model for the heavy-reasoning steps; defaults to the flash model
```

> Never commit `.env`. Once deployed, the API reads the same variables from
> Render's environment settings instead; see [Deploy](#deploy).

### 2. Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

In dev, Vite proxies `/api` to `localhost:8000`, so there is nothing to configure.
Open `http://localhost:5173`, create a production, and follow the
[Demo Walkthrough](#demo-walkthrough).

### 4. Run a full pipeline (demo)
```bash
# kicks off PROJ_NEON_NIGHTS through all six phases with mock data
python backend/run_demo.py --project PROJ_NEON_NIGHTS --budget 250000
```

### 5. Run the tests
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Runs offline against the mock fallbacks and covers the A2A envelope rules,
the orchestrator's fail-fast edges and phase re-runs, seeded persona
generation and distribution validation, the scheduler's cast and venue
constraints, password hashing, the auth 401/403/404 guards and the sign-in the
actor-KB routes require, the Supabase query filters, the background workers'
state merge, model-tier selection, the plain-language results (scene titles,
schedule changes, reviews), and how each phase copes with a malformed model
reply.
No keys and no database: every test that touches a store gets its own tmp
directory, so your `backend/.state/` is never read or written, and Gemini is
forced to its mock even on a machine that has a key.
GitHub Actions runs this plus the frontend build on every push
(`.github/workflows/ci.yml`).

### Actor knowledge base (Phase I)

The actor KB connection code is in `backend/services/casting_kb/` and its
schema is `backend/migrations/001_actor_knowledge_base.sql`. Run the migration
against a PostgreSQL database with pgvector enabled, then install the backend
requirements and set `DATABASE_URL`, `TMDB_API_KEY`, and optionally
`EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS`.

Populate and search it through the casting API. The knowledge base is shared
across productions, so these routes are not scoped to one, but they do need a
signed-in account: sign in first and send the session token as a bearer.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"your-password"}' \
  | python -c 'import json, sys; print(json.load(sys.stdin)["token"])')
curl -X POST http://localhost:8000/api/casting/actors/ingest \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"actor_ids":[6193,500]}'
curl -X POST http://localhost:8000/api/casting/actors/embeddings \
  -H "Authorization: Bearer $TOKEN"
curl -H "Authorization: Bearer $TOKEN" \
  'http://localhost:8000/api/casting/actors/search?character_description=cunning%20detective%20in%20her%20forties&gender=1&min_age=35&max_age=49'
```

TMDb does not normally provide physical measurements or appearance traits, so
the ingestion code stores only explicitly supplied trait fields and does not
infer sensitive attributes from photos or names.

### Agent skills

`skills/<name>/SKILL.md` files (casting, scheduling, audience-simulation,
cultural-research) are procedures the advisor agents follow: the Markdown body
is the agent's system instruction. Open **AI Advisors** at `/advisors` (it has
no menu entry since the site redesign) and press **Run** on a card, or call
`POST /api/skills/<name>/run/<project_id>`. Runs work offline on a
deterministic fallback and go live once `GEMINI_API_KEY` is set. See
`skills.md` for the full catalogue, `skills/README.md` for the file format,
and `AGENT.md` Section 8.

---

## Deploy

Three hosts, each with a free tier:

| Piece | Host | Config in this repo |
|---|---|---|
| React frontend (static build) | **Vercel** | `frontend/vercel.json` |
| FastAPI backend (Docker container) | **Render** | `render.yaml`, `Dockerfile` |
| Accounts, pipeline state, simulations, advisor runs | **Supabase** (Postgres) | `backend/schema_*.sql` |

```
 browser ── loads the app ─────────► Vercel   (static React build)
    │
    └──── calls VITE_API_URL/api ──► Render   (FastAPI container) ──► Supabase (Postgres)
                                        │
                                        └──► Gemini · Tavily (when keys are set)
```

The browser calls the API directly. Only the API holds keys or talks to
Supabase.

### Why the API isn't on Vercel too

Vercel can host FastAPI, but only as request-scoped functions, and this
backend keeps working after the request ends:

- An audience simulation or advisor run answers `202` straight away, then runs
  on a background thread for minutes while the dashboard polls it. A Vercel
  function can be frozen as soon as its response is sent, and runs for at most
  300 seconds on the Hobby plan.
- Runs in flight are tracked in the memory of the process that started them,
  so the polls have to reach that same process.
- Function filesystems are read-only, so the local-JSON fallback has nowhere to
  write.

Render runs the container as one long-lived process, which is what the code
expects. The same `Dockerfile` works on other container hosts (Railway,
Fly.io, Google Cloud Run) as long as they keep one instance running with CPU
between requests. The Cloud Run files in the repo (`GCP_DEPLOYMENT.md`,
`cloudbuild.yaml`, `deploy-*.sh`) predate this setup and do neither: they
scale to ten instances and to zero, and the frontend image never learns the
API's URL. Don't deploy with them as they stand (see [`TODO.md`](./TODO.md)).

### 1. Supabase (database)

1. Create a project on [supabase.com](https://supabase.com). Pick a region near
   the Render one (`render.yaml` uses Oregon), because the API reads state from
   Supabase on almost every request.
2. In the **SQL Editor**, run `backend/schema_auth.sql`,
   `backend/schema_skills.sql` and `backend/schema_state.sql`. All three are
   safe to re-run.
3. From the project's API settings, copy the **Project URL** and a **secret
   key** (`sb_secret_…`, or the legacy `service_role` key). The publishable
   (anon) key won't work: every table has row-level security switched on with no
   policies, so only a secret key can read them. It lives on the API only,
   never in the frontend.

### 2. Render (API)

1. In the [Render dashboard](https://dashboard.render.com), choose
   **New → Blueprint** and connect this repository. Render reads `render.yaml`
   and sets up a web service called `lumen-api`.
2. Fill in the variables it asks for: `SUPABASE_URL` and `SUPABASE_KEY` from
   step 1, plus `GEMINI_API_KEY` and `TAVILY_API_KEY` if you have them (leave
   them blank to keep the offline fallbacks). Leave `LUMEN_CORS_ORIGINS` blank
   for now.
3. Once the deploy is live, open `https://<your-service>.onrender.com/api/health`.
   It should return `{"status": "ok", ...}`. That only proves the container is
   up; creating a production once the frontend is live proves the database
   works.

`render.yaml` sets `LUMEN_STATE_BACKEND=supabase`, so a missing Supabase setting
fails loudly instead of quietly keeping accounts on a disk that is wiped on
every restart. From then on, Render redeploys each push that touches
`backend/`, `skills/` or the `Dockerfile`, once GitHub Actions passes.

### 3. Vercel (frontend)

1. [Import the repository into Vercel](https://vercel.com/new) and set
   **Root Directory** to `frontend`. Vercel detects Vite; keep its build
   settings.
2. Add the environment variable `VITE_API_URL` with your Render URL, for
   example `https://lumen-api.onrender.com`. Use the origin only, without `/api`.
3. Deploy, open the site and create a production. If that works, the whole
   chain (Vercel → Render → Supabase) is up.

`VITE_API_URL` is compiled into the bundle, so redeploy the frontend after
changing it. `frontend/vercel.json` sends every path to `index.html`, so a
refresh on `/overview` or an invite link (`/join/…`) still loads the app.

### 4. Restrict CORS to the frontend

In Render, set `LUMEN_CORS_ORIGINS` to your Vercel URL, for example
`https://lumen.vercel.app` (comma-separate several, such as a custom domain).
Until then the API accepts browser calls from any origin. That doesn't expose
accounts, because sessions are bearer tokens rather than cookies, but there is
no reason to leave it open. Vercel preview deployments get their own URLs, so
add those too if you use them.

### Limits to know

- **Free Render instances sleep** after 15 minutes without traffic, and the
  first request after that takes about a minute. Paid instances stay awake.
- **Run exactly one API instance.** Background runs live in that one process,
  and so does the per-production lock that keeps their saves from overwriting
  each other (`numInstances: 1` in `render.yaml`).
- **A redeploy stops runs in flight.** An interrupted advisor run is marked
  failed; an interrupted audience simulation stays `running` in the history, so
  start a new one (an open item in [`TODO.md`](./TODO.md)).

---

## Budget-driven scale

There are no tiers or modes. The total budget from the New script page lands in `GlobalState.budget_state.cap` and every downstream limit is derived from it (shares live in `backend/core/config.py`):

- **Casting** — a single role may cost at most 10% of the budget; pricier quotes are purged by the fail-fast wallet check.
- **Locations** — venues are picked cheapest-first among the days the whole cast can make, and a scene no day suits is still booked but sent to the sign-off queue; 15% of the budget spread over the shoot days is the daily burn allowance, and a venue day is paid once however many scenes share it.
- **Reach** — every territory with a rule set is cleared; the same code scales from a bootstrapped short to a studio slate.

---

## Demo Walkthrough

Create a production, then follow the beats below. With no `GEMINI_API_KEY`
the built-in Neon Nights script stands in for whatever screenplay you drop,
so these are exactly what you'll see; with a key, Lumen reads your own script.

1. **Drop the script** on **New script** (`/new`) with a $250k budget and a shooting window, and press **Plan my production**. All six phases run, then the Overview opens.
2. **Phase I/II — Cast** (`/cast`): an over-budget applicant is ruled out with the reason spelled out; each role shows its top pick and runners-up.
3. **Phase III — Schedule** (`/schedule`): **Changes Lumen made** lists the venue conflict the Scheduler and Location Agent negotiated, and the two scenes no day suits the whole cast. Those are booked anyway and sent to the sign-off queue, which no page shows yet.
4. **Phase V — Audience** (`/audience`): 200 synthetic viewers produce the Tomatometer, scene-by-scene scores and reviews, and the Overview names the scene where viewers drifted.

The rest of the demo lives on the older screens, which lost their menu entries in the site redesign, so open them by address:

5. **Phase IV** (`/production`): the UAE cut hits a compliance block, and the UAE card in the compliance matrix shows blocked.
6. **Phase VI** (`/marketing`): a meme is drafted, rejected by PR Risk for a spoiler, redrafted clean, and scheduled — cut from Phase V's top scene.
7. **Close** (`/logs`): the Live Agent Terminal shows the whole A2A conversation, including the Recut Advisor's +6 lift prediction — *150 messages, no human in the loop until the sign-off queue.*

---

## Origins and Authorship

Lumen started life as **CineNode**, a three-person hackathon project by Raymond Thomas Roshy,
Shriya Soni, and Swati Kumari; the original repo is
[Shriya-Soni/CineNode](https://github.com/Shriya-Soni/CineNode). After the
hackathon deadline, I (Swati) continued development solo in this repo.

The hackathon plan split ownership by phase:

| Phases | Planned owner |
|---|---|
| Casting | Raymond |
| Schedule & Compliance | Shriya |
| Audience & Marketing | Swati |

What actually shipped, measured at the fork point with `git blame` over the
tree (excluding mock data and lockfiles):

| Author | Surviving lines | Share |
|---|---|---|
| Swati | 14,913 | 88% |
| Raymond | 1,439 | 8% |
| Shriya | 613 | 4% |

Raymond wrote the initial GCP deployment config, the Gemini client, and the
scout agent. Shriya wrote the actor knowledge-base service and parts of the
production routing. The rest of the tree is mine: the six-phase agent pipeline,
authentication, the agent skills system, the advisor UI, the launch and
marketing phases, and the test suite and CI. Every commit after the fork is mine.

To reproduce the numbers:

```bash
git ls-files | grep -v -E 'mock_data/|package-lock|\.(png|svg|ico|lock)$' \
  | while read f; do git blame --line-porcelain -w HEAD -- "$f"; done \
  | grep '^author-mail' | sort | uniq -c | sort -rn
```

---

## License

Open-source under the **MIT License** (see [`LICENSE`](./LICENSE)).
