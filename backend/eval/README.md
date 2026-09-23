# Does the audience simulator actually work?

Lumen screens a film with 200 synthetic viewers and reports a Tomatometer and an
audience score. That is a claim about the real world, so it should be checkable
against the real world. This directory checks it.

**The question.** Given only a film's synopsis, genre, runtime and year, can the
cohort simulator predict how audiences actually rated it — and does the panel
machinery beat simply asking a model the same question once?

The second half is the part that matters. A 200-persona panel, cohort batching
and a per-persona expansion layer is a lot of apparatus. If one prompt does as
well, the apparatus is decoration, and the honest thing is to know that.

## The design

| | |
|---|---|
| **Sample** | 31 English-language features released 2026-06-01 to 2026-09-19 with at least 100 TMDb ratings — whatever the query returns, fixed in [`films.json`](films.json) |
| **Actual** | TMDb `vote_average` × 10, a public audience rating on the simulator's own 0–100 scale |
| **Input** | Genre, runtime, release year, synopsis. **The title is withheld** |
| **Predictors** | `lumen` (the shipped simulator) · `single_call` (one prompt) · `constant` (always answer the sample mean) |
| **Metrics** | MAE, RMSE, bias · Spearman ρ with a 10,000-round permutation p · paired bootstrap on the MAE gap |

Four choices are doing the real work here:

**The sample is a query, not a list.** A hand-picked set of films is
unfalsifiable — the picker chooses, knowingly or not, films the system does well
on, and nobody can tell afterwards. So the sample is defined by a TMDb discover
query recorded in the snapshot, and every eligibility rule (feature length, a
synopsis over 180 characters, no documentaries, a votes floor) is a stated rule
rather than a judgement about a film. Candidates are ordered by vote count, not
by rating: sorting by rating would return only well-reviewed films, and you
cannot demonstrate ranking on a sample where everything scored the same.

**The films are post-cutoff.** Ask a model about a film it was trained on and it
recalls the reception instead of predicting it — the evaluation would measure
memory. Every film here was released after the model's training cutoff, and
`python -m eval.run leakage` checks the assumption rather than asserting it: it
asks the model outright which films it knows, and any film whose recalled rating
lands within 10 points of the real one is dropped and named in the report.

**The title is withheld.** The same leak arrives through the front door if you
name the film, so both predictors see only the material.

**`constant` is in the comparison.** The sample's ratings cluster at 71.7 with a
spread of 9.6, so answering "71.7" every time scores an MAE near 8 and knows
nothing whatsoever about films. Any MAE in that region is evidence of nothing.
`constant` is even given the mean of the very films it is graded on — an
advantage no real predictor has — because it is the floor to clear, not a rival.
Most published model evaluations omit this baseline, and it is usually the one
that would have changed the conclusion.

## Running it

```bash
cd backend

# 1. build the sample — needs TMDB_API_KEY (free). Already committed; rebuild
#    only to move the window.
python -m eval.run build --released-after 2026-06-01 --released-before 2026-09-19

# 2. optional: drop any film the model turns out to remember
python -m eval.run leakage

# 3. score it — needs a model provider (CEREBRAS_API_KEY, GROQ_API_KEY,
#    GEMINI_API_KEY or OLLAMA_HOST). Resumable; see below.
python -m eval.run predict --predictor single_call --predictor lumen

# 4. compute the metrics and write REPORT.md
python -m eval.run report
```

`build` and `predict` are separate commands on purpose. Rebuilding the sample
after seeing the results would let the query be tuned until the numbers improve,
which is the exact failure the committed snapshot prevents.

## Two things that will bite you

**Pin the provider, and pin the same one twice.** `leakage` asks a model which
films it already knows and `predict` asks it to score them, so both have to be
the same model — otherwise the sample is filtered by one model's memory and
graded by another's guesses. Without `--provider` each uses the configured
chain, which falls through to the next provider on a rate limit; a leakage run
was caught answering from two at once. `leakage` now refuses to extend a file
written against a different model, and every probe records which one answered.

**A day's budget is not a minute's.** Both arrive as 429 and they need opposite
responses. Groq's free tier allows 8,000 tokens a minute *and* 200,000 a day:
the first clears while you wait, the second refills at a trickle — eleven
minutes offered for the next 1,840 tokens — so a run that waits it out sleeps
for hours and still grades its own fallbacks. `predict` now stops when the day's
budget is gone rather than filling the store with rows that look like
predictions and are not. Budget the day before starting: a 31-film sweep at the
shipped panel size is about 186 calls, and it cannot share a day with the
510-call sweep in `eval/structured`.

**Free-tier quota — pick the provider before shrinking the panel.** At the
production panel size of 200 the simulator needs about 5 cohort calls a film, so
a full 31-film sweep is around 150 calls plus 31 for the baseline. On Gemini's
free tier, which allows roughly 20 requests per model per day, that is several
days of quota; on Cerebras or Groq it is one sitting. Set `CEREBRAS_API_KEY` and
run the sweep there, and the two knobs below stop being necessary at all.

`predict` is resumable either way: every film's prediction is written the moment
it lands, and a re-run skips films already scored live and retries the ones that
fell back, so finishing across three days is supported rather than a workaround.

Whichever you use, **the report names the provider and model that answered each
film**, and switching provider invalidates the leakage check — a different model
has a different training cutoff, so `python -m eval.run leakage` has to be re-run
before the numbers mean anything. That is the one cost of moving off Gemini.

Two knobs trade fidelity for quota, and both are recorded in the report:

- `--analysis brief` (the default) derives the material analysis from TMDb
  metadata instead of spending a Pro call per film on `analyse_material`.
  `--analysis model` restores the production path.
- `--panel-size` shrinks the panel, which shrinks the cohort count and so the
  call count. The default is the product's own 200.

What that second knob actually costs, for this 31-film sample:

| `--panel-size` | Cohorts | Calls a film | Calls in total | Days of free quota |
|---:|---:|---:|---:|---:|
| 200 (shipped) | 25 | 5 | 186 | ~10 |
| 120 | 13 | 3 | 124 | ~7 |
| 80 | 4 | 1 | 62 | ~4 |
| 40 | 1 | 1 | 62 | ~4 |

Below about 80 the panel collapses to a handful of cohorts and then to a single
one, at which point the run is no longer testing the thing the product does —
it is one voice with extra steps, and its number should not be reported as the
simulator's. 80 is the floor worth running; 200 is the only one that grades
what ships.

**Offline fallbacks.** Every agent in Lumen falls back to deterministic sample
output when the model is unavailable. That is right for the product and fatal
for an evaluation: a benchmark that grades its own fallbacks reports the mock's
accuracy under the model's name. So each prediction records whether every call
behind it truly reached a model, a film any predictor fell back on leaves the
paired comparison entirely, and below a 90% live share the report withholds its
headline numbers and says why. Offline, the simulator returns about 69.4 for
every film in the sample — which is exactly what a report must never present as
a result.

## What a result here cannot tell you

- **A synopsis is not a screenplay.** The product reads a whole script; this
  reads a paragraph. Read these numbers as a floor on the simulator's accuracy,
  not a measurement of it at full input.
- **TMDb ratings are not Rotten Tomatoes.** Different population, different
  prompt. People who chose to rate a film they chose to watch are not a test
  screening, and the simulator is not validated against RT.
- **There is no critic actual.** No free critic-score API exists, so
  `tomatometer` is checked only on whether it orders films the way audience
  ratings do. Its MAE is not meaningful and is not reported as such.
- **The content-sensitivity path is untested here.** TMDb supplies no content
  flags, so no viewer's aversion ever fires in these runs.
- **The scene heatmap and the recut suggestion are not evaluated at all.**
  Nothing public grades them.
- **n = 31.** Enough to detect a large effect, not a subtle one. That is why
  every ρ carries a permutation p-value and every comparison a confidence
  interval — a one- or two-point MAE difference on this sample is noise.

## Files

| | |
|---|---|
| `dataset.py` | builds the sample from TMDb; `brief()` is the identical input every predictor sees |
| `predictors.py` | `lumen`, `single_call`, `constant` |
| `metrics.py` | MAE, RMSE, bias, Spearman, Pearson, permutation test, paired bootstrap — stdlib only |
| `run.py` | the `build` / `leakage` / `predict` / `report` CLI |
| `films.json` | the committed sample. Fixed, so the actuals do not drift as TMDb's live ratings move |
| `REPORT.md` | the generated report, caveats included |

The harness is tested in [`../tests/test_eval.py`](../tests/test_eval.py): the
metrics against hand-computed answers, and the rules that decide which films
count. Those tests run offline with the rest of the suite.
