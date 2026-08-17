# 🎬 The Autonomous Studio

> One multi-agent system that takes a film from **script → screen → social launch**.
> Built for **Agentic Cinema: The Blockbuster Hackathon** (Google Cloud · Replit Track).

The Autonomous Studio is a network of specialized AI agents that run the entire film lifecycle as **six connected phases** — casting, scheduling, compliance, audience testing, and marketing — sharing **one orchestrator, one state object, and one agent-to-agent (A2A) messaging standard**. It runs in two modes: **Big Dawgs** (major-studio scale) and **Indies** (bootstrapped scale).

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
autonomous-studio/
├── README.md
├── MASTER_BLUEPRINT.md          # full product spec, all 6 phases
├── AGENT.md                     # agent registry, A2A + GlobalState contracts
├── backend/
│   ├── main.py                  # FastAPI entrypoint
│   ├── orchestrator/            # LangGraph graph, GlobalState, routing
│   │   ├── graph.py
│   │   ├── state.py             # GlobalState schema
│   │   └── envelope.py          # A2A envelope helper (shared by ALL agents)
│   ├── agents/
│   │   ├── phase1_casting/
│   │   ├── phase2_audition/
│   │   ├── phase3_schedule/
│   │   ├── phase4_compliance/
│   │   ├── phase5_audience/
│   │   └── phase6_marketing/
│   ├── services/                # gemini, imagen, ffmpeg, whisper, tavily, supabase
│   └── mock_data/               # mock DBs (personas, venues, censorship rules...)
├── frontend/
│   ├── src/
│   │   ├── components/          # dashboards, LiveAgentTerminal, charts
│   │   └── pages/               # one view per phase
│   └── ...
└── .env.example
```

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
GEMINI_API_KEY=...
SUPABASE_URL=...
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
python backend/run_demo.py --project PROJ_NEON_NIGHTS --mode indie
```

---

## Modes: Big Dawgs vs. Indies

Set `mode` in `GlobalState` (or `--mode` on the demo runner):

- `enterprise` → 200+ personas, 50+ territories, union rules, managed vendors, brand-safety-weighted scoring.
- `indie` → 20–100 personas, 2–3 languages, condensed shoot, free-tier vendors, cost-weighted scoring.

Same code, two customers — proves real-world scalability to judges.

---

## 3-Minute Trailer Script (demo beats)

1. **Upload** a script for `PROJ_NEON_NIGHTS` (Indie mode).
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
- **Potential Impact:** addresses the real, expensive bottlenecks of film production at both studio and indie scale.
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
