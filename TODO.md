# TODO

What is still open. Last checked against the working tree on 19 September
2026, when all 298 backend tests and all 33 frontend tests passed offline and
the frontend built cleanly.

Everything left needs an account, a key or a deploy — nothing in the code is
waiting on a decision.

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

## Done

The September 2026 audit is cleared. Since the last entry:

- The old intake form is gone. `/new` had replaced it; `/intake` was reachable
  by address only, so the page, its route, the context call only it made and
  its styles were removed.
- An invite hands out exactly `max_uses` places. The count is claimed in one
  step before an account or a membership is written, and handed back if the
  redemption then fails, so two people redeeming the last place at the same
  moment no longer both get in.
- A pipeline run's record outlives the process. It is written to
  `backend/services/pipeline_store.py` at every phase change, so a run cut
  short by a restart is reported as failed instead of vanishing. A store that
  cannot be written costs the record, never the run.
- Sign-up is one transaction. `cn_register_producer` (in
  `backend/schema_auth.sql`) commits the account, the production, the owner
  membership and the production's first state together. A database without the
  function falls back to the four writes with the account removed again on
  failure.
- The frontend has tests: `npm test` covers the background-run polling, the
  words the sign-off queue puts on screen and the paged log reader. CI runs
  them before the build.
- The two documentation chores are checks now, in
  `backend/tests/test_contracts_in_step.py`: one fails when a phase writes a
  `GlobalState` field its `owns` list does not declare (a background run would
  drop it) or raises an escalation it does not declare, the other when an
  advisor's run controls, `skills.md` and AGENT.md Section 8 disagree.

Before that: async runs polled at 202, saves merged under the production's
lock, slim state reads with ETags and a paged event log, one budget behind the
ledger, Phase V on a panel with no sensitive attributes, crash-safe local JSON,
sign-in rate limits, `defusedxml` for `.fdx` uploads, the agent layer back in
the menu with the sign-off queue on the Overview, a plan that says when it is
Lumen's sample output, and a setup that costs nothing — Tavily plus Gemini's
free tier for the scout, TMDb photos, and a poster Lumen draws itself.

## Not planned

Each of these is cut on purpose: it costs money or prep time and adds nothing
to the system's logic.

- Video, music and rendered campaign assets in Phase VI (Veo, Lyria).
  `agent_visual` and `agent_reel_cutter` produce art-direction specs that go
  through the PR gate; the production's poster is art Lumen draws itself (image
  generation is not in Gemini's free tier).
- Tape decoding and transcription in Phase II (FFmpeg, Whisper).
  `agent_media_proc` passes the tape reference through.
- A LangGraph or Google Cloud Agent Builder rewrite of the orchestrator. The
  explicit state machine in `backend/core/orchestrator/graph.py` stays.
- Billing, workspace transfers and further team administration: a second
  production, leaving one, role changes, ownership transfer, self-service
  password reset, expense editing. The invite flow that exists is complete
  and tested, and that is where it stops.
- A pipeline run history in the API or the dashboard. The records are kept, but
  nothing reads more than the production's last run, so there is no endpoint
  for them.
- Cloud Storage for media.
