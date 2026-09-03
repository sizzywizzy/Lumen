<p align="center">
  <img src="assets/logo.svg" alt="CineNode" width="360" />
</p>

# 🎬 CineNode

> One multi-agent system that takes a film from **script → screen → social launch**.
> Built for **Agentic Cinema: The Blockbuster Hackathon** (Google Cloud · Replit Track).

CineNode is a network of specialized AI agents that run the entire film lifecycle as **six connected phases** — casting, scheduling, compliance, audience testing, and marketing — sharing **one orchestrator, one state object, and one agent-to-agent (A2A) messaging standard**. Scale follows the budget you enter at intake: casting caps, venue choices and territory reach all derive from it.

It is a true **Multi-Agent System (MAS)**: agents ask each other questions, get answers, and change their own behavior — humans only sign off at the top.

---

## The Problem

Turning a screenplay into a finished, marketed film is a two-week-per-step manual grind: breaking down scenes, vetting cast, solving the scheduling constraint puzzle, clearing rights for every territory, guessing at audience reaction, and building a campaign. Every step is a bottleneck, and they don't talk to each other.

## The Solution — Six Phases, One Brain

| Phase | Name | What it does |
|---|---|---|
| **I** | Pre-Casting Intelligence & Compliance | Turns script + brief into casting mandates; fail-fast filters applicants on PR/budget risk |
| **II** | Audition Analysis & Scorecard | Crushes tapes with FFmpeg/Whisper, grades performances, builds a leaderboard |
| **III** | Script → Schedule | Breaks down scenes, matches venues, builds the stripboard + burn-rate budget |
| **IV** | Compliance, Localization & Launch Prep | Clears rights, localizes/censors per territory, runs QC |
| **V** | Audience Simulation & Predictive Reviews | 200 synthetic viewers screen the cut → Tomatometer + fix suggestions |
| **VI** | Marketing, PR & Autonomous Social Launch | Auto-generates reels/memes/posters, PR-gates them, schedules the rollout |

Full spec: see [`MASTER_BLUEPRINT.md`](./MASTER_BLUEPRINT.md). Agent contracts: see [`AGENT.md`](./AGENT.md).

---

## Architecture

```
                        ┌─────────────────────────────┐
                        │  agent_director_orchestrator │   LangGraph DAG
                        │  (owns GlobalState, routing) │   + fail-fast edges
                        └──────────────┬──────────────┘
                                       │  reads/writes
                        ┌──────────────▼──────────────┐
                        │        GlobalState (JSON)     │  persisted in Supabase
                        └──────────────┬──────────────┘
                                       │
   PHASE I → PHASE II → PHASE III → PHASE IV → PHASE V → PHASE VI
   (each phase = a subgraph of agents; all speak the same A2A envelope)
                                       │
                        VI → I  PR-risk + telemetry loop back
```

- **Orchestration:** LangGraph state machine, exposed through **Google Cloud Agent Builder** (hackathon requirement).
- **Every agent** communicates via the standard A2A envelope (`sender`, `recipient`, `intent`, `payload`).
- **A "Live Agent Terminal"** in the UI streams these JSON messages in real time — the proof it's a real MAS.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Orchestration | **LangGraph** (internal) + **Google Cloud Agent Builder** (required wrapper) |
| Reasoning LLM | **Gemini 2.0 Flash** (bulk) / **Gemini 2.0 Pro** (heavy reasoning) |
| Multimodal | Gemini (audition tapes, scene stills) |
| Image generation | **Imagen 3** (posters, memes) |
| Music (optional) | Lyria |
| Video processing | **FFmpeg** (4K → 720p before any LLM) |
| Transcription | **Whisper API** |
| Web search | **Tavily** |
| Database + Auth | **Supabase** (Postgres) |
| Hosting | **Replit** (satisfies Replit-track integration) |
| Backend | **Python + FastAPI** |
| Frontend | **React + Tailwind + shadcn/ui + Recharts** |
| Secrets | Replit Secrets / Google Secret Manager |

---

## Repository Structure

```
cinenode/
├── README.md
├── AGENT.md                     # agent registry, A2A + GlobalState contracts
├── assets/                      # logo + brand (the o of Node is the camera)
├── skills/                      # SKILL.md procedures the advisor agents follow (skills/README.md)
├── contracts/                   # SACRED: shared JSON schemas — change only with team agreement
│   ├── a2a_envelope.json
│   └── global_state.json
├── backend/
│   ├── main.py                  # FastAPI entrypoint (mounts one router per domain)
│   ├── migrations/               # PostgreSQL/pgvector schema migrations
│   ├── run_demo.py              # CLI: full pipeline on mock data
│   ├── core/                    # THE BRAIN — shared by everyone
│   │   ├── config.py            # env vars, model tiers, guardrail constants
│   │   ├── orchestrator/
│   │   │   ├── graph.py         # phase DAG + fail-fast edges (LangGraph-shaped)
│   │   │   └── state.py         # GlobalState Pydantic models
│   │   └── messaging/
│   │       └── envelope.py      # A2A envelope helper (shared by ALL agents)
│   ├── services/                # gemini, supabase, mock_db, casting_kb
│   ├── mock_data/               # script, candidates, venues, censorship rules, personas
│   └── domains/                 # THE SANDBOXES — one per team member
│       ├── casting/             # ➔ Raymond (Phases I & II): router, agents/, prompts
│       ├── production/          # ➔ Shriya (Phases III & IV)
│       └── launch/              # ➔ Swati (Phases V & VI)
├── frontend/
│   └── src/
│       ├── shared/LiveAgentTerminal.jsx   # real-time A2A message scroller
│       ├── features/            # casting/ production/ launch/ — one dashboard each
│       └── lib/                 # api.js, utils.js
├── docker-compose.yml
└── .env.example
```

**Zero-key dev loop:** every agent has a mock fallback, so the entire six-phase
pipeline runs before any API key exists — `python backend/run_demo.py` just works.

---

## Getting Started

### Prerequisites
- Python 3.10+, Node 18+
- A Google AI / Vertex API key (request the **$100 GCP credit** via the hackathon form)
- A Supabase project (free tier)
- FFmpeg installed (`apt-get install ffmpeg` / bundled on Replit)

### 1. Configure environment
Copy `.env.example` to `.env` and fill in:

```bash
GEMINI_API_KEY=...         # all agent reasoning; mock fallbacks work without it
SUPABASE_URL=...           # shared persistence; required for any deployment
SUPABASE_KEY=...
TAVILY_API_KEY=...
WHISPER_API_KEY=...        # or use local whisper
IMAGEN_API_KEY=...         # same Google project
```

> On Replit, put these in **Secrets**, not in the repo.

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

### 4. Run a full pipeline (demo)
```bash
# kicks off PROJ_NEON_NIGHTS through all six phases with mock data
python backend/run_demo.py --project PROJ_NEON_NIGHTS --budget 250000
```

### Actor knowledge base (Phase I)

The actor KB connection code is in `backend/services/casting_kb/` and its
schema is `backend/migrations/001_actor_knowledge_base.sql`. Run the migration
against a PostgreSQL database with pgvector enabled, then install the backend
requirements and set `DATABASE_URL`, `TMDB_API_KEY`, and optionally
`EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS`.

Populate and search it through the casting API:

```bash
curl -X POST http://localhost:8000/api/casting/actors/ingest \
  -H 'Content-Type: application/json' \
  -d '{"actor_ids":[6193,500]}'
curl -X POST http://localhost:8000/api/casting/actors/embeddings
curl 'http://localhost:8000/api/casting/actors/search?character_description= cunning detective in her forties&gender=1&min_age=35&max_age=49'
```

TMDb does not normally provide physical measurements or appearance traits, so
the ingestion code stores only explicitly supplied trait fields and does not
infer sensitive attributes from photos or names.

### Agent skills

`skills/<name>/SKILL.md` files (casting, scheduling, audience-simulation,
cultural-research) are procedures the advisor agents follow: the Markdown body
is the agent's system instruction. Open **Agent Skills** in the dashboard and
press **Run** on a card, or call `POST /api/skills/<name>/run/<project_id>`.
Runs work offline on a deterministic fallback and go live once `GEMINI_API_KEY`
is set. The dashboard calls them **AI Advisors**. See `skills.md` for the full
catalogue, `skills/README.md` for the file format, and `AGENT.md` Section 8.

---

## Budget-driven scale

There are no tiers or modes. The total budget from the intake cover page lands in `GlobalState.budget_state.cap` and every downstream limit is derived from it (shares live in `backend/core/config.py`):

- **Casting** — a single role may cost at most 10% of the budget; pricier quotes are purged by the fail-fast wallet check.
- **Locations** — venues are picked cheapest-first, and 15% of the budget spread over the shoot days is the daily burn allowance.
- **Reach** — every territory with a rule set is cleared; the same code scales from a bootstrapped short to a studio slate.

---

## 3-Minute Trailer Script (demo beats)

1. **Drop the script** for `PROJ_NEON_NIGHTS` on the cover page with a $250k budget and a shooting window.
2. **Phase I/II:** watch an over-budget applicant auto-rejected; a leaderboard builds itself.
3. **Phase III:** Scheduler ↔ Location Agent negotiate a venue conflict live in the terminal; the Gantt reflows.
4. **Phase IV:** the UAE cut hits a compliance block; the world map turns that territory red.
5. **Phase V:** 200 synthetic viewers stream verdicts; the Tomatometer ticks up; Aggregation flags Act 2 and the Recut Advisor predicts a +6 lift.
6. **Phase VI:** a meme is generated, rejected by PR Risk for a spoiler, regenerated clean, and scheduled — cut from Phase V's top scene.
7. **Close:** the Live Agent Terminal scrolls the whole A2A conversation — *no human in the loop.*

---

## How It Maps to Judging Criteria

- **Technological Implementation:** genuine A2A MAS with a shared protocol + fail-fast orchestration.
- **Design:** one coherent product across six phases, with live dashboards.
- **Potential Impact:** addresses the real, expensive bottlenecks of film production at any budget, from a bootstrapped short to a studio slate.
- **Quality of Idea:** agents that negotiate and self-correct, not a chatbot with buttons.

---

## Team & Phase Ownership

| Phases | Owner |
|---|---|
| I & II — Casting | **Raymond** |
| III & IV — Schedule & Compliance | **Shriya** |
| V & VI — Audience & Marketing | **Swati** |

---

## License

Open-source under the **MIT License** (see `LICENSE`). Required for hackathon submission.
