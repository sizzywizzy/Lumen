# TODO

What is still open, roughly in priority order. Last checked against the
working tree on 17 September 2026, when all 231 backend tests passed offline
and the frontend built cleanly.

Everything else from the September 2026 audit is done, including:

- Scout role ids checked against the script's roles.
- Message ids that stay unique across restarts.
- One budget (the cap) behind the ledger and Settings.
- Phase IV checks only the assets the breakdown lists.
- Phase V screens with the Gemini cohort simulator on a panel with no
  sensitive attributes.
- One audience simulation at a time, with restarted runs reported as failed.
- Every save under the production's lock, and background runs merged onto
  the stored state.
- Slim state reads with ETags, and a paged event log.
- Pipeline runs that answer 202 and are polled.
- Vertex only on explicit opt-in.
- Crash-safe local JSON files.
- Sign-in rate limits.
- `defusedxml` for `.fdx` uploads.
- The small fixes.
- The agent layer back in the menu, with the sign-off queue on the Overview.
- README captures.
- `AGENT.md` synced with the code.

## Needs a decision

- [ ] **Delete the Cloud Run path, or fix it.** The README documents Render
  and Vercel; `GCP_DEPLOYMENT.md`, `cloudbuild.yaml`, `deploy-cloudrun.sh`,
  `deploy-frontend.sh`, `frontend/Dockerfile` and `frontend/nginx.conf` are
  still the older Cloud Run setup. They do not work as they stand:
  - They allow ten instances and scale to zero with CPU throttled between
    requests. That splits background runs, the project lock and the sign-in
    rate limit across processes, and stalls runs after the 202.
  - `deploy-cloudrun.sh:32` escapes `\$GEMINI_API_KEY` and the other keys, so
    the service receives the literal text.
  - Neither script sets `LUMEN_STATE_BACKEND=supabase`, `LUMEN_CORS_ORIGINS`
    or `LUMEN_TRUSTED_PROXY_HOPS`.
  - The frontend image is built without `VITE_API_URL`, and its `/api` proxy
    is commented out (`frontend/nginx.conf:16`).
  - The image uses `node:18-alpine` (`frontend/Dockerfile:4`), below React
    Router 7's Node 20 minimum.
  - There is no `frontend/.dockerignore`, so `node_modules` goes into the
    build context.
  - `GCP_DEPLOYMENT.md:136` checks `/health` (the route is `/api/health`), and
    line 79 names only one of the three schemas.

  Fixing it means one always-on instance
  (`--min-instances=1 --max-instances=1 --no-cpu-throttling`), real env
  values (or Secret Manager), and a frontend build that knows the API's URL.
- [ ] **Drop the old intake form?** `/intake` (`frontend/src/features/intake/IntakePage.jsx`)
  is reachable only by address; `/new` replaced it and is the page the menu
  links. Every other older screen is now in the Agents menu.

## Needs your accounts

- [ ] **Hosted demo.**
  1. Create the Supabase project and run the three `backend/schema_*.sql`
     files.
  2. Deploy the API to Render from `render.yaml`.
  3. Deploy the frontend to Vercel with `VITE_API_URL`.
  4. Set `LUMEN_CORS_ORIGINS`.
  5. Link the result from the README ("See it").
- [ ] **Check the rate limit's client address on Render.** `render.yaml` sets
  `LUMEN_TRUSTED_PROXY_HOPS=1`, on the assumption that Render's proxy
  appends the caller's address to `X-Forwarded-For`. After the first deploy,
  confirm the key differs between two networks. If it doesn't, every sign-in
  shares one limit.
- [ ] **Recapture with a live model.** The README screenshots and
  `assets/screenshots/pipeline.gif` come from the offline demo (no keys). Once
  `.env` holds a Gemini key, redo them with a real screenplay so the cast,
  scenes and reviews are the model's.

## Bugs

- [ ] **An invite can be redeemed past its `max_uses`.**
  `backend/domains/auth/router.py` (`join`) checks `uses` and saves
  `uses + 1` in two steps, so two people redeeming the last use at the same
  moment both get in. Count the use with a conditional update (Supabase:
  `update ... where uses < max_uses`), under the auth store's lock on local
  JSON.
- [ ] **A server restart loses the pipeline run's record.** Run status lives
  in memory (`backend/domains/pipeline/jobs.py`). A restart mid-run leaves
  the stored state untouched, and the page says the run was interrupted, but
  there is no history of runs. Store the record, as advisor runs are
  (`cn_skill_runs`), if a history is wanted.

## Features and tasks

- [ ] **Registration as one database transaction.** Sign-up now inserts the
  account and the production, claiming the email and the id, and deletes the
  account again if a later write fails. That is all-or-nothing on failure,
  but it is not one transaction. A Postgres function called through
  PostgREST (`rpc`) would make it one; it needs a schema change.
- [ ] **Frontend tests.** CI only builds the frontend. The background-run
  polling (`frontend/src/shared/ProjectContext.jsx`), the sign-off queue
  wording (`signOffs` in `frontend/src/lib/production.js`) and the paged
  Logs page have no automated checks.

### Not planned

Each of these is cut on purpose: it costs money or prep time and adds nothing
to the system's logic.

- Video, music and rendered campaign assets in Phase VI (Veo, Lyria).
  `agent_visual` and `agent_reel_cutter` produce art-direction specs that go
  through the PR gate; the production's poster is the one image Lumen paints.
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

- [ ] Keep `skills.md` and `AGENT.md` Section 8 in step when advisor inputs change.
- [ ] Keep the "owns" lists in `backend/core/orchestrator/graph.py` in step
  with what each phase writes. A background run copies exactly those fields
  onto the stored state, so a field a phase writes but does not list is lost.
