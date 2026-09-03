# CineNode — API Inventory & Specifications

This document outlines all Application Programming Interfaces (APIs) utilized across the CineNode project, categorized into:
1. **External Third-Party APIs & Cloud Services**
2. **Internal Backend REST API Endpoints (FastAPI)**
3. **Frontend API Client Interface (`frontend/src/lib/api.js`)**
4. **Inter-Agent Messaging Protocol (A2A Envelopes)**

---

## 1. External Third-Party APIs & Cloud Services

| Service / Provider | Integration Point | Purpose & Role | Offline / Fallback Behavior |
|---|---|---|---|
| **Google Gemini API** (`google-genai`) | `backend/services/gemini_client.py` | Powers agent reasoning, script analysis, and synthetic audience personas (`gemini-3.6-flash`). | When `GEMINI_API_KEY` is missing, returns deterministic fallback mock data from `backend/mock_data/`. |
| **Tavily Search API** (`https://api.tavily.com/search`) | `backend/services/tavily_client.py` | Real-time web search for market certification rules and cultural sensitivity/censorship compliance. | When `TAVILY_API_KEY` is not configured, research is gracefully skipped without errors. |
| **Supabase PostgREST API** (`supabase-py`) | `backend/services/supabase_client.py`<br>`backend/services/auth_store.py`<br>`backend/services/simulation_store.py` | Cloud relational database for state (`global_state`), auth accounts (`users`, `sessions`, `invites`, `memberships`), and simulations. | When `SUPABASE_URL` / `SUPABASE_KEY` are not set, falls back to local disk persistence in `backend/.state/*.json`. |
| **OpenAI Whisper API** *(Planned / Configured)* | `.env` / `backend/requirements.txt` | Speech-to-text transcription for audition video tapes (Phase II). | Stubbed/mocked in `backend/domains/casting/agents/phase2_audition.py`. |
| **Google Imagen 3 API** *(Planned / Configured)* | `.env` / `AGENT.md` | Image generation for marketing posters, social memes, and promotional assets. | Mocked in `backend/domains/launch/agents/agent_visual.py`. |

---

## 2. Internal Backend REST API Endpoints (FastAPI)

All internal API routes are exposed by FastAPI under the `/api` prefix and mounted in `backend/main.py`.

### A. System & Orchestrator Pipeline (`backend/main.py`)

| Method | Endpoint | Access / Role | Description |
|---|---|---|---|
| `GET` | `/api/health` | Public | Health check; returns API status and registered orchestrator pipeline phases. |
| `POST` | `/api/pipeline/init` | Producer / Owner | Initializes or resets a project's `GlobalState` with an intake budget cap. |
| `POST` | `/api/pipeline/run` | Producer / Owner | Executes a full multi-agent pipeline run (Phases I through VI) on the project. |
| `GET` | `/api/projects` | Authenticated User | Lists all productions that the authenticated user belongs to. |
| `GET` | `/api/state/{project_id}` | Member | Retrieves current full `GlobalState` for the specified project. |
| `GET` | `/api/events/{project_id}` | Member | Polling endpoint for Live Agent Terminal event envelopes (supports `?since=index`). |

---

### B. Authentication & Team Management (`backend/domains/auth/router.py`)

| Method | Endpoint | Access / Role | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | Public | Registers a new producer account and creates their initial production. Returns session token. |
| `POST` | `/api/auth/login` | Public | Authenticates via email/password and mints a new session bearer token. |
| `POST` | `/api/auth/logout` | Authenticated User | Revokes the current session token server-side. |
| `GET` | `/api/auth/me` | Authenticated User | Retrieves current user profile and associated productions. |
| `POST` | `/api/auth/invites` | Producer / Owner | Generates a single-use, cryptographically signed team invitation token. |
| `GET` | `/api/auth/invites/{project_id}` | Producer / Owner | Lists pending/active invites for a production. |
| `DELETE` | `/api/auth/invites/{project_id}/{invite_id}` | Producer / Owner | Revokes an existing invitation. |
| `GET` | `/api/auth/invite-preview/{token}` | Public | Previews production details for an invite link before registration. |
| `POST` | `/api/auth/join` | Public | Redeems an invite token to create an account and join a production. |
| `GET` | `/api/auth/team/{project_id}` | Member | Lists all team members and their roles for a project. |
| `DELETE` | `/api/auth/team/{project_id}/{user_id}` | Producer / Owner | Removes a member from the production team. |

---

### C. Casting & Audition Endpoints (`backend/domains/casting/router.py`)

| Method | Endpoint | Access / Role | Description |
|---|---|---|---|
| `POST` | `/api/casting/run/{project_id}` | Producer / Owner | Triggers Phase I (pre-casting) and Phase II (audition analytics) agents. |
| `PATCH` | `/api/casting/candidates/{project_id}/{candidate_id}` | Producer / Owner | Updates candidate status (`LOCKED`, `SHORTLIST`, `DISQUALIFIED`) and logs reason. |
| `GET` | `/api/casting/leaderboard/{project_id}` | Member | Returns graded candidate rankings, scores, and audition statuses. |

---

### D. Production, Schedule & Script (`backend/domains/production/router.py`)

| Method | Endpoint | Access / Role | Description |
|---|---|---|---|
| `POST` | `/api/production/run/{project_id}` | Producer / Owner | Triggers Phase III (breakdown & shoot scheduling) agents. |
| `PUT` | `/api/production/settings/{project_id}` | Producer / Owner | Updates shooting parameters (concurrency, contingency reserve, overtime tolerance). |
| `POST` | `/api/production/expenses/{project_id}` | Producer / Owner | Records an expense against production contingency. |
| `POST` | `/api/production/shoot-day/{project_id}` | Producer / Owner | Updates day notes, call times, or scene progress for a shoot date. |
| `POST` | `/api/production/script/{project_id}` | Producer / Owner | Uploads and parses screenplays (`.pdf`, `.fdx`, `.fountain`, `.txt`). |
| `GET` | `/api/production/script/{project_id}` | Member | Retrieves stored screenplay metadata and parsed text summary. |

---

### E. Audience Simulation Domain (`backend/domains/audience/router.py`)

| Method | Endpoint | Access / Role | Description |
|---|---|---|---|
| `POST` | `/api/audience/simulations/{project_id}` | Producer / Owner | Starts a background audience simulation run with synthetic persona cohorts. |
| `GET` | `/api/audience/simulations/{project_id}` | Member | Lists historical simulation runs and summaries for the project. |
| `GET` | `/api/audience/simulations/{project_id}/{simulation_id}` | Member | Fetches full simulation status, sentiment scores, and cultural scan results. |
| `GET` | `/api/audience/simulations/{project_id}/{simulation_id}/panel` | Member | Fetches paginated synthetic persona profiles and individual reaction cards. |

---

### F. Launch & Marketing Domain (`backend/domains/launch/router.py`)

| Method | Endpoint | Access / Role | Description |
|---|---|---|---|
| `POST` | `/api/launch/run/{project_id}` | Producer / Owner | Triggers Phase IV (compliance) and Phase VI (autonomous social launch) agents. |

---

## 3. Frontend API Client Interface (`frontend/src/lib/api.js`)

The React frontend centralizes all HTTP calls into the `api` singleton. Dev traffic is proxied by Vite (`/api` → `http://localhost:8000`).

```javascript
// Session & Auth Management
api.login(email, password)
api.register(payload)
api.logout()
api.me()
api.listProjects()
api.previewInvite(token)
api.joinProduction(payload)

// Team Administration
api.team(projectId)
api.createInvite(payload)
api.listInvites(projectId)
api.revokeInvite(projectId, inviteId)
api.removeMember(projectId, userId)

// Pipeline Orchestration & State
api.health()
api.initPipeline(projectId, budgetUsd)
api.runPipeline(projectId, budgetUsd)
api.getState(projectId)
api.getEvents(projectId, since)

// Casting
api.setCandidateStatus(projectId, candidateId, status, reason)

// Script & Production Management
api.uploadScript(projectId, payload)
api.getScript(projectId)
api.updateProductionSettings(projectId, settings)
api.addExpense(projectId, expense)
api.updateShootDay(projectId, update)

// Phase V Audience Simulation
api.startSimulation(projectId, payload)
api.listSimulations(projectId)
api.getSimulation(projectId, simulationId)
api.getSimulationPanel(projectId, simulationId, offset, limit)
```

---

## 4. Agent-to-Agent (A2A) Messaging Protocol

Internal communication between CineNode autonomous agents adheres to the standard A2A Envelope schema (`contracts/a2a_envelope.json`):

```json
{
  "sender": "agent_breakdown",
  "recipient": "agent_director_orchestrator",
  "intent": "breakdown_ready",
  "timestamp": "2026-09-02T18:00:00Z",
  "in_reply_to": null,
  "payload": {
    "scene_count": 6,
    "cast_required": ["ROLE_LEAD", "ROLE_ANTAG"]
  }
}
```

These envelopes are persisted on `GlobalState.event_log` and polled in real-time by the frontend **Live Agent Terminal** via `/api/events/{project_id}`.
