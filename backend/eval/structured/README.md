# Does enforcing a schema make the replies better formed?

Every agent in Lumen asks for JSON and then runs the answer through
[`core/llm_output.py`](../../core/llm_output.py) before touching it, because "asks
for JSON" and "gets the right JSON" are different claims. Sixty-five coercion
calls across the agents exist for replies that arrive valid but wrong.

Providers now offer something stronger than asking: an enforced schema. This
directory measures whether that is worth the coupling, or whether the prompting
was already good enough.

**The question.** Given the prompts Lumen actually sends, does asking a provider
to enforce the reply's shape reduce the share of replies that come back in the
wrong shape — and by enough to matter?

## The design

| | |
|---|---|
| **Prompt set** | 255 distinct prompts, captured from 12 planned productions and 7 screenings, committed in [`prompts.json`](prompts.json) |
| **Arms** | `plain` asks for JSON · `schema` asks for JSON matching the shape |
| **Held fixed** | Same prompt, same system instruction, same model, one attempt, no fallback chain |
| **Headline** | `malformed_rate`: the share of attempts not in the asked-for shape, whether unparseable or wrong-shaped |
| **Also reported** | The two halves of that rate separately, the fallback rate an agent would have suffered, off-shape fields per answer, median latency |

Four choices are doing the real work.

**The prompts are captured, not written.** Prompts invented for an experiment
measure the prompts you invented. Every model call in the product goes through
one function, so [`capture.py`](capture.py) stands in for it during offline runs
and records the real prompt, system instruction and tier. Because the stand-in
returns the sample output the agent would have used anyway, the runs complete
normally and later phases build their prompts from realistic state — so capturing
the set costs no key, no quota and no network. The matrix varies budget, locality
and material because prompts that don't vary the way real work varies are one
prompt repeated.

**The schemas are derived from the agents' own sample output.** Each agent
already passes a `mock`: the value it falls back to, which is by construction the
shape it expects. `llm.schema_from_example` turns that into a JSON Schema, so
there is one source of truth. Hand-writing a schema beside each prompt would
create a second one, and the two would drift — which is the failure the tests in
[`test_contracts_in_step.py`](../../tests/test_contracts_in_step.py) exist to
prevent elsewhere in this codebase.

**One variable.** The run pins the provider and the model, sets both tiers to it,
empties the fallback chain and allows a single attempt. Without that, a run that
quietly fell through to another model would be comparing two models as much as
two request shapes.

**Only paired prompts count.** A prompt whose arms did not both get a real
attempt is excluded and the reason is printed in the report. An exhausted quota
is a fact about the account, not about the model's shape discipline, and
averaging it in would let a rate limit read as a result. This is the same rule
the [audience evaluation](../README.md) keeps.

## Running it

```bash
cd backend

# 1. collect the prompts — offline, free, no key. Already committed; re-run only
#    to widen the matrix in capture.py.
python -m eval.structured.run capture

# 2. ask each one twice. 255 prompts x 2 arms = 510 calls.
python -m eval.structured.run run --provider cerebras

# 3. compute the rates and write REPORT.md
python -m eval.structured.run report
```

`run` is resumable: each result is written the moment it lands, and a re-run
retries only the pairs that failed. `--limit N` does a sample of N prompts
(shuffled, so a partial run is not just the first phase's prompts), and `--pause`
spaces the calls out for a tight per-minute limit.

## Three things that will bite you

**Not on Gemini.** 510 calls against a free tier that allows about 20 a day is
roughly a month of quota. This was tried on 19 September 2026 and every call came
back `429 RESOURCE_EXHAUSTED`, which is the demonstration rather than the
argument. Run the sweep on Cerebras or Groq, or on a local Ollama where calls are
free, and use Gemini only for a small `--limit` confirmation once a day.

**There is no one schema dialect.** An OpenAI-style `json_schema` with `strict`
*requires* `additionalProperties: false` on every object. Gemini's
`response_schema` is an OpenAPI subset with no such keyword and answers
`400 INVALID_ARGUMENT: Unknown name "additional_properties"` when it sees one.
`llm._schema_for` translates per provider, and this was found by a live call
rather than by reading — worth remembering when adding a fifth provider.

The consequence outlives the bug: on Gemini a schema can require the fields it
names but cannot forbid extra ones. Violation rates are comparable **between the
two arms on one provider**, and not between providers.

**A model may refuse the schema outright.** Not every model on Cerebras or Groq
enforces `json_schema` rather than merely returning valid JSON. One that does not
answers 400, which the report counts as `schema_refused` and excludes from the
pairing instead of scoring it as a success. If a whole run comes back that way,
the model is the finding: pick another with `--model`.

## The other measurement, from production

The experiment replays prompts outside the agents. The agents themselves keep a
record that no replay can give: how often a live reply needed repairing.

`llm_output.watching()` counts that for a block of work — fields checked, fields
that fell back to their default, numbers clamped into range, strings clipped to
their limit. It is the product's own malformed-reply rate, measured on the real
path with the real post-processing, and it costs one `ContextVar` read per
coercion when nobody is watching.

An offline run repairs nothing, by construction — the sample output is the shape
the agents expect, and
[`test_structured_output.py`](../../tests/test_structured_output.py) fails if that
stops being true. So a non-zero count means a live reply arrived wrong, which is
the number a schema would have to beat.

## What a result here cannot tell you

- **The schemas are derived, so they describe an example rather than an intent.**
  An empty list in a mock leaves that array unconstrained, a free-form map is
  read as a fixed set of keys, and a list's later items are assumed to match the
  first. `capture` reports how many prompts got a usable schema for this reason.
- **A violation is not always a defect.** Under `additionalProperties: false` an
  extra field the agent would have ignored counts as a violation, because a
  strict schema forbids it.
- **One model at a time.** The shape discipline of a 70B open model and of Gemini
  are separate questions with separate answers.
- **Nothing here judges the answer.** Only whether it arrived in the right shape.
  A schema cannot make a wrong score right, and if enforcement narrows what the
  model will say, this experiment would not see the cost.
- **A clean baseline is a real result.** If plain prompting is already at or near
  zero, the honest report is that any gain is smaller than this sample can
  resolve — not that the experiment failed. `report` says so in those words, and
  a test holds it to that.

## Files

| | |
|---|---|
| `capture.py` | the run matrix, and the stand-in that records prompts without sending them |
| `run.py` | the `capture` / `run` / `report` CLI |
| `prompts.json` | the committed prompt set, so a run is reproducible |
| `results.json` | per-prompt, per-arm outcomes; written as they land, so a run resumes |
| `REPORT.md` | the generated report, caveats included |
