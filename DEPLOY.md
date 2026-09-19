# Deploying Lumen

The instance built from these steps is live at
<https://lumen-beige-five.vercel.app>, with its API at
<https://lumen-api-mwip.onrender.com>.

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
                                        └──► Gemini · Tavily · TMDb (when keys are set)
```

The browser calls the API directly. Only the API holds keys or talks to
Supabase. Every setting the API reads is listed in [`.env.example`](.env.example).

## Why the API isn't on Vercel too

Vercel can host FastAPI, but only as request-scoped functions, and this
backend keeps working after the request ends:

- A pipeline run, an audience simulation or an advisor run answers `202`
  straight away, then runs on a background thread for minutes while the
  dashboard polls it. A Vercel function can be frozen as soon as its response
  is sent, and runs for at most 300 seconds on the Hobby plan.
- Runs in flight are tracked in the memory of the process that started them,
  so the polls have to reach that same process.
- Function filesystems are read-only, so the local-JSON fallback has nowhere to
  write.

Render runs the container as one long-lived process, which is what the code
expects. The same `Dockerfile` works on other container hosts (Railway,
Fly.io) as long as they keep one instance running with CPU between requests.

## 1. Supabase (database)

1. Create a project on [supabase.com](https://supabase.com). Pick a region near
   the Render one (`render.yaml` uses Oregon), because the API reads state from
   Supabase on almost every request.
2. In the **SQL Editor**, run `backend/schema_auth.sql`,
   `backend/schema_skills.sql` and `backend/schema_state.sql`. All three are
   safe to re-run, and an existing database needs them run again after a
   deploy that changed them: sign-up wants the `cn_register_producer` function
   from `schema_auth.sql`, and pipeline runs want the `cn_pipeline_runs` table
   from `schema_state.sql`. Sign-up still works without the function — it
   falls back to writing the rows one at a time — but it is not one
   transaction until the file has been run.
3. From the project's API settings, copy the **Project URL** and a **secret
   key** (`sb_secret_…`, or the legacy `service_role` key). The publishable
   (anon) key won't work: every table has row-level security switched on with no
   policies, so only a secret key can read them. It lives on the API only,
   never in the frontend.

## 2. Render (API)

1. In the [Render dashboard](https://dashboard.render.com), choose
   **New → Blueprint** and connect this repository. Render reads `render.yaml`
   and sets up a web service called `lumen-api`.
2. Fill in the variables it asks for: `SUPABASE_URL` and `SUPABASE_KEY` from
   step 1, plus `GEMINI_API_KEY`, `TAVILY_API_KEY` and `TMDB_API_KEY` if you have
   them. Free keys are enough; leave them blank to keep the offline fallbacks. Leave `LUMEN_CORS_ORIGINS` blank
   for now.
3. Once the deploy is live, open `https://<your-service>.onrender.com/api/health`.
   It reads the state store before answering, so it tells you whether step 1
   actually worked:

   | Response | Meaning |
   |---|---|
   | `200` · `{"status": "ok", "store": {"backend": "supabase", "reachable": true}}` | The API is up and Supabase answers. Go to step 3. |
   | `503` · `{"status": "degraded", "store": {"reachable": false, "detail": "…"}}` | The container is up but the database is not readable. `detail` says why — usually a wrong `SUPABASE_KEY` (use the secret key, not the anon one) or `backend/schema_*.sql` never run. |
   | Render shows the deploy as **failed** | `LUMEN_STATE_BACKEND=supabase` with `SUPABASE_URL`/`SUPABASE_KEY` blank. The API refuses to boot rather than go live and fail every request; the deploy log names the missing setting. |

`render.yaml` sets `LUMEN_STATE_BACKEND=supabase`, so Supabase settings that
are missing or wrong are caught at the door instead of quietly keeping
accounts on a disk that is wiped on every restart. Missing credentials stop
the boot, since nothing can fix that at runtime; an unreachable Supabase lets
the container start — so you can read its logs — and shows up as a `503` from
`/api/health`, which is also the path Render health-checks. From then on,
Render redeploys each push that touches `backend/`, `skills/` or the
`Dockerfile`, once GitHub Actions passes.

## 3. Vercel (frontend)

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

## 4. Restrict CORS to the frontend

In Render, set `LUMEN_CORS_ORIGINS` to your Vercel URL, for example
`https://lumen.vercel.app` (comma-separate several, such as a custom domain).
Until then the API accepts browser calls from any origin. That doesn't expose
accounts, because sessions are bearer tokens rather than cookies, but there is
no reason to leave it open. Vercel preview deployments get their own URLs, so
add those too if you use them.

## Limits to know

- **Everything here runs on free plans.** On Gemini, only its free tier (no
  Google Search grounding, image generation or Vertex AI), so keep billing off
  on the Google project behind your key; Google may use free-tier prompts to
  improve its products. Tavily's free plan allows 1,000 searches a month, and
  each pipeline run uses two.
- **Which provider you pick decides how many runs a day you get.** A full
  pipeline run makes about 25 model calls.
  - **Gemini's free tier allows about 20 requests per model per day**, so a run
    spills onto the fallback models part-way through
    (`GEMINI_FALLBACK_MODELS`), and once the day's quota is gone every later
    phase falls back to sample output: the plan keeps going, and the Overview
    and Audience pages say which parts are Lumen's sample film rather than a
    read of the screenplay. Expect roughly two full runs a day on one free key.
    The quota resets daily on Google's clock, not on first use.
  - **Cerebras and Groq allow far more**, which is why `LUMEN_LLM_PROVIDERS`
    puts them first. Setting `CEREBRAS_API_KEY` alongside `GEMINI_API_KEY` is
    the cheapest way to stop a demo falling back mid-run, and the only way the
    evaluation in `backend/eval` finishes in one sitting.
  - **Ollama costs nothing at all** but runs on your own machine, so it is for
    development rather than a deploy.
- **Free Render instances sleep** after 15 minutes without traffic, and the
  first request after that takes about a minute. Paid instances stay awake.
- **Run exactly one API instance.** Background runs live in that one process,
  and so do the per-production lock that keeps saves from overwriting each
  other and the sign-in rate limits (`numInstances: 1` in `render.yaml`).
- **A redeploy stops runs in flight.** An interrupted advisor run or audience
  simulation is marked failed. An interrupted pipeline run leaves the stored
  plan as it was, and the page says the run was interrupted. Start it again.
- **Sign-in attempts are rate-limited per client address.** `render.yaml` sets
  `LUMEN_TRUSTED_PROXY_HOPS=1` so the limit reads the address Render's proxy
  reports; see [`TODO.md`](TODO.md) for the check to do after the first
  deploy.
