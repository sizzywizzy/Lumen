# TODO

What is still open. Last checked against the working tree on 20 September
2026, when all 346 backend tests and all 50 frontend tests passed offline and
the frontend built cleanly.

Everything left needs an account, a key or a deploy — nothing in the code is
waiting on a decision.

## Needs your accounts

- [ ] **A model provider with quota left.** Three were tried on 20 September 2026
  and each said something different:

  - **Cerebras** answers `402 payment_required` with `param: quota` — the free
    allowance on this account is spent and it wants a card. Out, under the
    free-plans-only rule.
  - **Groq** works. `openai/gpt-oss-20b` and `openai/gpt-oss-120b` are what this
    account has; `llama-3.3-70b-versatile` is not available. The free tier allows
    8,000 tokens a minute, which a 510-call sweep takes about two hours to spend,
    so `eval.structured.run` waits out a 429 rather than recording it.
  - **Gemini** is still the ~20-requests-a-day tier that started all of this.

  Two bugs came out of trying them, both fixed: urllib's default agent is
  refused by Cloudflare with `403 error code: 1010`, and Groq rejects
  `json_object` unless the word "json" appears in the messages — which would
  have made *every* Lumen agent call fail on Groq, not just the evaluation.

- [ ] **A free Cerebras key, which unblocks two things at once.** Agents now run
  on whichever provider is configured — Cerebras, Groq, Gemini or a local Ollama,
  in the order `LUMEN_LLM_PROVIDERS` gives (`backend/services/llm.py`). Nothing
  else is needed in the code.

  Gemini's roughly 20 requests per model per day is what stopped both the live
  recapture below and the audience evaluation in `backend/eval`, which still
  reports 0 of 31 films graded. Cerebras's free tier is wide enough for a full
  31-film sweep in one sitting. Set `CEREBRAS_API_KEY` and both become possible.

  One thing to do first: `python -m eval.run leakage` has to be re-run after
  switching. It asks the model which films it already knows, and a different
  model has a different training cutoff, so the answer does not carry over.

- [ ] **Decide what to do about the actor search.** The evaluation is finished
  and run (`backend/eval/casting`, 52 briefs, 1,159 actors): the shipped
  embedding model scores recall@10 of 19% against 35% for a dependency-free
  TF-IDF ranking, and the interval on that gap does not cross zero.
  `bge-small-en-v1.5` closes almost all of it (33%) and is a 384-dimension
  drop-in, so the change is `EMBEDDING_MODEL` plus a re-run of
  `scripts/generate_actor_embeddings.py` — no migration.

  Not done here because it needs a database to re-embed against, and this one is
  paused. `match_actors` now refuses a model mismatch rather than returning
  nonsense, so the swap is safe whenever the database is back.

- [ ] **Run the structured-output experiment.** The harness is finished and
  tested (`backend/eval/structured`), and its 255-prompt set is captured and
  committed — collecting prompts needs no key, so that part is done. The sweep
  itself is 510 calls, which is about a month of Gemini's free tier: it was
  attempted on 19 September 2026 and every call came back 429.

  To finish: `python -m eval.structured.run run --provider cerebras`, then
  `report`. One finding is already in hand and documented — Gemini's
  `response_schema` refuses the `additionalProperties` that OpenAI-style strict
  mode requires, so schemas are translated per provider.

- [ ] **Recapture with a live model.** The README screenshots and
  `assets/screenshots/pipeline.gif` still come from the offline demo, so the
  cast, scenes and reviews in them are Lumen's sample film.

  Attempted on 19 September 2026 and stopped by Gemini's daily quota, not by
  anything in the code — which is what the provider chain above is for. A capture run seeded a production from an original screenplay through
  the real API against a local store, and Phases I and II answered live
  (9 and 5 model calls). The free tier then hit its ceiling of 20 requests per
  model per day, so Phase III's scene breakdown and part of Phase V fell back
  to sample output. Publishing that would put the sample film's scenes beside
  a real cast, which is worse than the current images, so nothing was
  replaced.

  To finish: wait for the daily quota to reset, re-run Phase III and Phase V
  on the seeded production (`POST /api/production/run/<id>` and
  `POST /api/launch/run/<id>`, about eight calls between them), confirm every
  entry in `model_use` reports `live`, then capture the six stills in headless
  Chrome at 1440x900. The GIF needs a terminal recorder (asciinema with agg,
  or vhs); none is installed.

## Done

The September 2026 audit is cleared. Since the last entry:

- The hosted demo is up: <https://lumen-beige-five.vercel.app>, API at
  <https://lumen-api-mwip.onrender.com>, state in Supabase, cross-origin
  access restricted to the Vercel address, all three optional keys set.
  Linked from the README.
- The sign-in rate limit counts per network on Render, as
  `LUMEN_TRUSTED_PROXY_HOPS=1` assumed. Checked on the live deploy: an address
  driven past the limit gets 429 while a second network still gets the plain
  "incorrect password" answer, so one network cannot lock out another.
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
