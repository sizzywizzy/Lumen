# CineNode on Replit

Context for Replit Agent. **Read this before changing anything.** This is a
working application, not a scaffold — do not rewrite it, do not re-scaffold the
frontend, and do not change API route paths.

## What this is

A multi-agent film production system. Six pipeline phases (pre-casting →
audition → schedule → compliance → audience simulation → marketing) run as
agents that talk to each other over a fixed A2A message envelope. The headline
feature is a **500-persona Audience Simulation Agent** in Phase V.

## Architecture

```
frontend/          React 18 + Vite 5 + react-router-dom 7, vanilla-CSS design tokens
  src/features/    one folder per screen (intake, casting, production, launch, logs, team, settings)
  src/shared/      AppShell, Sidebar, ProjectContext, AuthContext, UI primitives
  dist/            production build output (gitignored)

backend/           FastAPI
  main.py          app entry; mounts every router; /api/health, /api/state, /api/pipeline
  core/            config, auth (PBKDF2 + bearer sessions), audience persona engine, A2A envelope
  domains/         one package per phase — casting, production, launch, audience, auth
  services/        gemini_client, supabase_client, auth_store, simulation_store,
                   tavily_client, script_intake
  .state/          local JSON persistence fallback (gitignored, EPHEMERAL)
```

**Frontend ↔ backend:** the frontend calls **relative** `/api/...` paths only.
In dev, Vite proxies `/api` to `localhost:8000`. There is no hardcoded backend
URL anywhere, so serving both from one origin works without frontend changes.

## Running it

Two processes locally:

```bash
make backend     # uvicorn on :8000
make frontend    # vite on :5173
```

**On Replit this must become one process** — see "Known gaps" below.

## Secrets

Set these in Replit **Secrets** (never in the repo — `.env` is gitignored):

| Secret | Purpose | Required? |
|---|---|---|
| `GEMINI_API_KEY` | All agent reasoning. 14 calls per pipeline run, 9 per simulation | Yes for live AI |
| `SUPABASE_URL` / `SUPABASE_KEY` | Shared persistence for state, accounts, simulations | **Yes for deployment** |
| `TAVILY_API_KEY` | Optional web grounding for cultural research | No |
| `CINENODE_STATE_BACKEND` | `auto` (default) / `supabase` / `local` | No |

Every key is read server-side in `backend/core/config.py`. None reaches the
browser. **Do not add any `VITE_`-prefixed secret** — Vite inlines those into
the public bundle.

Without `GEMINI_API_KEY` the app still runs end to end: every LLM call site has
a mock fallback, and the UI labels results as "offline fallback" rather than
passing them off as live model output.

## Known gaps to close for Replit

1. **Single port.** Replit exposes one HTTP port. FastAPI must serve
   `frontend/dist` as static files *and* keep `/api`, with a catch-all that
   returns `index.html` for non-`/api` paths — client-side routes like
   `/casting` and `/logs` must survive a hard refresh. Bind `0.0.0.0:$PORT`.

2. **Ephemeral filesystem.** `backend/.state/` holds users, sessions, invites,
   GlobalState and simulations. It does not survive a redeploy and is not
   shared across instances. `services/supabase_client.py`, `auth_store.py` and
   `simulation_store.py` already have a Supabase branch that activates when the
   credentials are set and the `supabase` package is installed (it is in
   `requirements.txt`). Apply `backend/schema_auth.sql`, then add equivalent
   tables for `global_state` and `cn_simulations`.

3. **Long background jobs.** An audience simulation runs on a
   `threading.Thread` for several minutes after the request returns `202`. If
   the instance is recycled mid-run the record is stuck at `status: "running"`
   forever. Prefer a **Reserved VM** deployment, and mark orphaned runs
   `failed` on startup.

## Rules

- Do not change API route paths or the frontend's relative `/api` fetch calls.
- Do not replace the auth system. It is PBKDF2-SHA256 with opaque bearer
  sessions and per-production membership checks on every route.
- Do not "fix" the audience simulation algorithm. How 500 responses are derived
  from batched cohort calls is documented in
  `backend/domains/launch/agents/audience_sim.py` and is deliberate.
- Keep the mock fallbacks working — the demo must run without credentials.
