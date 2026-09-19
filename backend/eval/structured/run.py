"""The structured-output experiment: `capture`, `run`, `report`.

    cd backend
    python -m eval.structured.run capture
    python -m eval.structured.run run --provider cerebras
    python -m eval.structured.run report

One variable. The same prompt, the same model, the same single attempt — asked
once for JSON and once for JSON matching a schema. Anything else that differed
would make the comparison worth nothing, so the run pins the provider and the
model, turns the fallback chain off, and allows one attempt per call.

`run` is resumable: each prompt's pair of results is written the moment it
lands, and a re-run only does the pairs that are missing.
"""
import argparse
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Optional

from core import config
from eval.structured import capture
from services import json_files, llm

# A Windows console defaults to cp1252, which cannot encode an actor's name or
# a film title with a diacritic in it — and an evaluation that crashes on
# "Yūsuke" would be one that quietly only works on some of its own data.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts.json"
RESULTS = HERE / "results.json"
REPORT_JSON = HERE / "report.json"
REPORT_MD = HERE / "REPORT.md"

ARMS = ("plain", "schema")


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: Any) -> None:
    """Atomically, because this is rewritten after every single call.

    A sweep is hundreds of calls over a couple of hours and rewrites the whole
    file each time, so an in-place write leaves a window — small, but entered
    hundreds of times — where a stop or a crash truncates the file and loses the
    run. The local stores already solved this: `json_files.write_text` renames a
    complete sibling over the target, which is atomic on Windows and on POSIX.
    """
    json_files.write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ------------------------------------------------------------------ capture --


def do_capture(_args) -> int:
    captured = capture.collect(on_step=lambda message: print(f"  {message}", flush=True))
    prompts = captured["prompts"]
    without = [p["id"] for p in prompts if not p["schema"]]
    payload = {
        "captured_at": _now(),
        "matrix": captured["matrix"],
        "calls_made": captured["calls"],
        "distinct_prompts": len(prompts),
        "without_a_schema": without,
        "prompts": prompts,
    }
    _save(PROMPTS, payload)
    print(
        f"\n{captured['calls']} calls over {captured['matrix']['productions']} productions and "
        f"{captured['matrix']['materials']} screenings -> {len(prompts)} distinct prompts, "
        f"{len(prompts) - len(without)} with a schema. Written to {PROMPTS.name}."
    )
    if len(prompts) < 200:
        print(
            f"Fewer than 200. Add rows to PRODUCTIONS or MATERIALS in capture.py to widen it; "
            f"the run works at any size but a rate below {1 / max(1, len(prompts)):.1%} "
            "cannot be distinguished from zero."
        )
    return 0


# ---------------------------------------------------------------------- run --


def _pin(provider: str, model: Optional[str]) -> str:
    """One provider, one model, no fallbacks — so a result is about that model.

    Returns the model actually pinned. Mutating `config` is how the rest of the
    codebase is steered, and this process does nothing else.
    """
    config.LLM_PROVIDERS = [provider]
    chosen = model or {
        "cerebras": config.CEREBRAS_FLASH_MODEL,
        "groq": config.GROQ_FLASH_MODEL,
        "gemini": config.GEMINI_FLASH_MODEL,
        "ollama": config.OLLAMA_FLASH_MODEL,
    }[provider]
    for name in ("CEREBRAS", "GROQ", "GEMINI", "OLLAMA"):
        setattr(config, f"{name}_FLASH_MODEL", chosen)
        setattr(config, f"{name}_PRO_MODEL", chosen)
    config.GEMINI_FALLBACK_MODELS = []
    return chosen


def _classify(error: str) -> str:
    """Why a call produced nothing usable. The first two are the experiment's
    subject; the rest are noise to be excluded from the comparison."""
    if "JSONDecodeError" in error:
        return "unparseable"
    if "HTTP 400" in error or "INVALID_ARGUMENT" in error:
        # The schema itself was refused: this model does not enforce one.
        return "schema_refused"
    if "429" in error or "RESOURCE_EXHAUSTED" in error:
        return "rate_limited"
    if "402" in error or "payment_required" in error:
        # The free allowance is spent and the provider wants a card. Its own
        # outcome because it is not a transient failure and not a model fault:
        # nothing about the run will change until a different provider is used.
        return "needs_payment"
    if "403" in error and "1010" in error:
        # Cloudflare refusing the client signature, which reads like an outage.
        return "blocked_by_cdn"
    return "call_failed"


def _retry_seconds(error: str, fallback: float = 20.0) -> float:
    """How long a rate-limited provider asked us to wait. Groq says it in the
    message body ("Please try again in 12.5s"); others just say no."""
    found = re.search(r"try again in ([\d.]+)\s*s", error)
    try:
        return min(90.0, float(found.group(1)) + 1.0) if found else fallback
    except (TypeError, ValueError):
        return fallback


def _ask(prompt: dict[str, Any], arm: str, waits: int = 4) -> dict[str, Any]:
    """One prompt, one arm, one answer. Never raises.

    A rate limit is waited out rather than recorded, up to `waits` times. That
    does not soften the one-attempt rule the comparison depends on: a 429 never
    reached the model, so trying again is the same single attempt, not a second
    chance at getting the shape right. Free tiers are measured per minute and
    Lumen's prompts are long, so without this a sweep is mostly holes.
    """
    schema = prompt["schema"] if arm == "schema" else None
    started = time.time()
    for attempt in range(waits + 1):
        try:
            data, trace = llm.generate_json_traced(
                prompt["prompt"],
                tier=prompt["tier"],
                system=prompt["system"] or None,
                schema=schema,
                attempts_per_model=1,
            )
            break
        except llm.LLMUnavailable as exc:
            kind = _classify(str(exc))
            if kind == "rate_limited" and attempt < waits:
                time.sleep(_retry_seconds(str(exc)))
                continue
            return {
                "outcome": kind,
                "seconds": round(time.time() - started, 2),
                "error": str(exc)[:300],
            }
    problems = llm.violations(data, prompt["schema"])
    return {
        "outcome": "answered",
        "seconds": round(time.time() - started, 2),
        "model": trace.get("model"),
        "violations": problems[:10],
        "violation_count": len(problems),
    }


def do_run(args) -> int:
    captured = _load(PROMPTS, None)
    if not captured:
        print(f"No {PROMPTS.name}. Run `capture` first.", file=sys.stderr)
        return 1

    model = _pin(args.provider, args.model)
    if not config.configured_llm_providers():
        print(
            f"{args.provider} is not configured. Set its key (or OLLAMA_HOST) and try again.",
            file=sys.stderr,
        )
        return 1

    prompts = [p for p in captured["prompts"] if p["schema"]]
    if args.shuffle:
        # A partial run should be a fair sample of the prompt set, not its first
        # few phases, which would over-weight one agent.
        random.Random(args.seed).shuffle(prompts)
    if args.limit:
        prompts = prompts[: args.limit]

    results = _load(RESULTS, {})
    key = f"{args.provider}:{model}"
    per_model = results.setdefault(key, {})
    print(f"{len(prompts)} prompts x {len(ARMS)} arms on {key}\n")

    for index, prompt in enumerate(prompts, 1):
        record = per_model.setdefault(prompt["id"], {})
        for arm in ARMS:
            if record.get(arm, {}).get("outcome") == "answered":
                continue  # already scored live; a re-run retries only the failures
            record[arm] = _ask(prompt, arm)
            _save(RESULTS, results)  # after every call, so a stop loses nothing
            outcome = record[arm]["outcome"]
            mark = "ok" if outcome == "answered" else outcome
            count = record[arm].get("violation_count")
            detail = f" ({count} off-shape)" if count else ""
            print(f"  [{index}/{len(prompts)}] {prompt['id']} {arm:<7} {mark}{detail}", flush=True)
            if args.pause:
                time.sleep(args.pause)

    print(f"\nWritten to {RESULTS.name}. Now: python -m eval.structured.run report")
    return 0


# ------------------------------------------------------------------- report --


def _rates(records: list[dict[str, Any]]) -> dict[str, Any]:
    """One arm's numbers over the prompts that both arms managed to attempt.

    `malformed_rate` is the headline, and the only rate the verdict compares: the
    share of attempts that did not come back in the shape the agent asked for,
    whether because the reply was not JSON or because it was JSON of the wrong
    shape. One denominator, so the two failure modes cannot be traded off against
    each other by moving between them.
    """
    attempted = len(records)
    unparseable = sum(1 for r in records if r["outcome"] == "unparseable")
    answered = [r for r in records if r["outcome"] == "answered"]
    off_shape = [r for r in answered if r.get("violation_count")]
    return {
        "attempted": attempted,
        "answered": len(answered),
        "malformed": unparseable + len(off_shape),
        "malformed_rate": _share(unparseable + len(off_shape), attempted),
        "unparseable": unparseable,
        "parse_failure_rate": _share(unparseable, attempted),
        # Valid JSON, wrong shape: the failure a schema is meant to remove.
        "off_shape": len(off_shape),
        "violation_rate": _share(len(off_shape), len(answered)),
        "violations_per_answer": round(
            statistics.fmean([r.get("violation_count", 0) for r in answered]), 3
        ) if answered else None,
        # What the product would actually have done: fall back to sample output.
        "fallback_rate": _share(attempted - len(answered), attempted),
        "median_seconds": round(statistics.median([r["seconds"] for r in records]), 2) if records else None,
    }


def _share(part: int, whole: int) -> Optional[float]:
    return round(part / whole, 4) if whole else None


def do_report(_args) -> int:
    captured = _load(PROMPTS, None)
    results = _load(RESULTS, {})
    if not captured or not results:
        print("Nothing to report: run `capture` then `run` first.", file=sys.stderr)
        return 1

    by_model: dict[str, Any] = {}
    for key, per_prompt in results.items():
        # Paired only. A prompt whose arms did not both get a real attempt says
        # nothing about the schema — it says the quota ran out — and averaging it
        # in would let a rate limit look like a result.
        usable = {
            prompt_id: record
            for prompt_id, record in per_prompt.items()
            if all(
                record.get(arm, {}).get("outcome") in ("answered", "unparseable")
                for arm in ARMS
            )
        }
        excluded: dict[str, int] = {}
        for prompt_id, record in per_prompt.items():
            if prompt_id in usable:
                continue
            for arm in ARMS:
                outcome = record.get(arm, {}).get("outcome", "not attempted")
                if outcome not in ("answered", "unparseable"):
                    excluded[outcome] = excluded.get(outcome, 0) + 1

        arms = {arm: _rates([r[arm] for r in usable.values()]) for arm in ARMS}
        by_model[key] = {
            "paired_prompts": len(usable),
            "excluded": excluded,
            "arms": arms,
            "change": {
                "malformed": _delta(arms["plain"]["malformed_rate"], arms["schema"]["malformed_rate"]),
                "parse_failure": _delta(arms["plain"]["parse_failure_rate"], arms["schema"]["parse_failure_rate"]),
                "violation": _delta(arms["plain"]["violation_rate"], arms["schema"]["violation_rate"]),
                "fallback": _delta(arms["plain"]["fallback_rate"], arms["schema"]["fallback_rate"]),
            },
        }

    payload = {
        "generated_at": _now(),
        "prompts_captured_at": captured["captured_at"],
        "prompt_set": {
            "distinct": captured["distinct_prompts"],
            "with_a_schema": captured["distinct_prompts"] - len(captured["without_a_schema"]),
            "matrix": captured["matrix"],
        },
        "models": by_model,
    }
    _save(REPORT_JSON, payload)
    REPORT_MD.write_text(_markdown(payload), encoding="utf-8")
    print(f"Wrote {REPORT_JSON.name} and {REPORT_MD.name}\n")
    print(_markdown(payload))
    return 0


def _delta(plain: Optional[float], schema: Optional[float]) -> Optional[float]:
    if plain is None or schema is None:
        return None
    return round(schema - plain, 4)


def _percent(value: Optional[float]) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _figure(value: Optional[float]) -> str:
    """A plain number for the table, em-dash when there is nothing to show —
    never Python's `None`, which is not a thing a reader should have to see."""
    return "—" if value is None else f"{value:g}"


def _markdown(payload: dict[str, Any]) -> str:
    out = [
        "# Structured output: does enforcing a schema help?",
        "",
        "Generated by `python -m eval.structured.run report`.",
        "",
        f"- **Prompt set:** {payload['prompt_set']['distinct']} distinct prompts captured from "
        f"{payload['prompt_set']['matrix']['productions']} planned productions and "
        f"{payload['prompt_set']['matrix']['materials']} screenings, "
        f"{payload['prompt_set']['with_a_schema']} of them with a schema derived from the agent's "
        "own sample output",
        f"- **Captured:** {payload['prompts_captured_at']}",
        "- **Arms:** `plain` asks for JSON · `schema` asks for JSON matching the shape. Same "
        "prompt, same model, one attempt each",
        "",
    ]
    if not payload["models"]:
        out += ["No model has been run yet.", ""]
        return "\n".join(out)

    for key, model in payload["models"].items():
        plain, schema = model["arms"]["plain"], model["arms"]["schema"]
        out += [
            f"## {key}",
            "",
            f"{model['paired_prompts']} prompts where both arms got a real attempt.",
            "",
            "| | plain | schema enforced | change |",
            "|---|---:|---:|---:|",
            f"| **Not in the asked-for shape** | **{_percent(plain['malformed_rate'])}** | "
            f"**{_percent(schema['malformed_rate'])}** | **{_percent(model['change']['malformed'])}** |",
            f"| — unparseable reply | {_percent(plain['parse_failure_rate'])} | "
            f"{_percent(schema['parse_failure_rate'])} | {_percent(model['change']['parse_failure'])} |",
            f"| — valid JSON, wrong shape | {_percent(plain['violation_rate'])} | "
            f"{_percent(schema['violation_rate'])} | {_percent(model['change']['violation'])} |",
            f"| Agent would fall back | {_percent(plain['fallback_rate'])} | "
            f"{_percent(schema['fallback_rate'])} | {_percent(model['change']['fallback'])} |",
            f"| Off-shape fields per answer | {_figure(plain['violations_per_answer'])} | "
            f"{_figure(schema['violations_per_answer'])} | |",
            f"| Median seconds a call | {_figure(plain['median_seconds'])} | "
            f"{_figure(schema['median_seconds'])} | |",
            "",
        ]
        if model["excluded"]:
            reasons = ", ".join(f"{count} x {reason}" for reason, count in sorted(model["excluded"].items()))
            out += [
                f"Left out of the pairing: {reasons}. A prompt only counts when both arms got a "
                "real attempt, so a quota, a refused schema or a blocked request cannot be read "
                "as a result about the model.",
                "",
            ]
        out += [_verdict(model), ""]

    out += [
        "## What this cannot tell you",
        "",
        "- **The schemas are derived, not authored.** Each one comes from the `mock` its agent "
        "falls back to, so it describes that example rather than the agent's full intent: an empty "
        "list in the mock leaves the array unconstrained, a free-form map is read as a fixed set of "
        "keys, and a list's later items are assumed to match the first.",
        "- **A violation is not always a defect.** `additionalProperties: false` counts an extra "
        "field the agent would have ignored as a violation, because a strict schema forbids it.",
        "- **One model at a time.** A result on one model says nothing about another; the shape "
        "discipline of a 70B open model and of Gemini are different questions.",
        "- **Nothing here measures whether the answer is any good.** Only whether it arrived in the "
        "shape the agent asked for.",
        "",
    ]
    return "\n".join(out)


def _verdict(model: dict[str, Any]) -> str:
    """Say what the numbers mean, including when they mean nothing.

    A regression is checked for before a clean baseline. Read the other way
    round, a run where plain prompting was spotless and the enforced arm was not
    would be reported as "nothing to fix" — which is the one wrong answer that
    would matter, because it hides the schema doing harm.
    """
    paired = model["paired_prompts"]
    plain, schema = model["arms"]["plain"], model["arms"]["schema"]
    if not paired:
        return "**No paired prompts**, so there is nothing to compare yet."

    floor = 1 / paired
    resolves = f"with {paired} prompts the smallest rate this sample can resolve is {floor:.1%}"
    gain = -(model["change"]["malformed"] or 0)  # positive: the schema arm was better

    if gain < -floor:
        return (
            f"**Enforcing the schema made things worse.** Replies not in the asked-for shape rose "
            f"from {_percent(plain['malformed_rate'])} to {_percent(schema['malformed_rate'])}. "
            "Check whether this model mangles the derived schema, or refuses part of it, before "
            "reading anything else into the run."
        )
    if gain > floor:
        return (
            f"**Enforcing the schema helped.** Replies not in the asked-for shape fell from "
            f"{_percent(plain['malformed_rate'])} to {_percent(schema['malformed_rate'])}, and the "
            f"share of calls an agent would have had to fall back on from "
            f"{_percent(plain['fallback_rate'])} to {_percent(schema['fallback_rate'])}."
        )
    if (plain["malformed_rate"] or 0) < floor:
        return (
            f"**The baseline was already clean.** Plain prompting put nothing wrong in "
            f"{paired} prompts, so a schema had nothing to fix here and this run cannot show a "
            f"gain. That is a real result and should be reported as one, not as a failed "
            f"experiment: {resolves}, so the honest claim is that any improvement is smaller "
            "than that."
        )
    return (
        f"**No difference worth acting on.** {_percent(plain['malformed_rate'])} malformed plain "
        f"against {_percent(schema['malformed_rate'])} enforced, on {paired} prompts — {resolves}."
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.structured.run", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("capture", help="collect the prompts Lumen sends (offline, free)")

    run = sub.add_parser("run", help="ask each prompt twice: plain, then schema-enforced")
    run.add_argument("--provider", required=True, choices=["cerebras", "groq", "gemini", "ollama"])
    run.add_argument("--model", default=None, help="override the provider's configured model")
    run.add_argument("--limit", type=int, default=None, help="only this many prompts (a confirmation run)")
    run.add_argument("--shuffle", action="store_true", default=True,
                     help="sample the prompt set rather than taking it in order (default)")
    run.add_argument("--in-order", dest="shuffle", action="store_false")
    run.add_argument("--seed", type=int, default=20260920)
    run.add_argument("--pause", type=float, default=0.0, help="seconds between calls, for tight rate limits")

    sub.add_parser("report", help="compute the rates and write REPORT.md")

    args = parser.parse_args(argv)
    return {"capture": do_capture, "run": do_run, "report": do_report}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
