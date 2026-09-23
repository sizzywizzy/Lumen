"""The evaluation CLI. Run from `backend/`:

    python -m eval.run build   --released-after 2026-06-01 --released-before 2026-09-19
    python -m eval.run leakage                      # optional, one call a film
    python -m eval.run predict --predictor lumen --predictor single_call
    python -m eval.run report

Each step writes its output to `eval/` and the next step reads it, so a run
that dies on a rate limit is resumed by repeating the same command: films
already scored are skipped. That is not a convenience — an evaluation you
cannot finish on a free-tier quota is an evaluation nobody re-runs, and a
number nobody can re-run is a claim, not a measurement.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from core import config
from domains.launch.agents import audience_sim
from eval import dataset, metrics, predictors
from services import llm

HERE = Path(__file__).parent
PREDICTIONS = HERE / "predictions.json"
LEAKAGE = HERE / "leakage.json"
REPORT_JSON = HERE / "report.json"
REPORT_MD = HERE / "REPORT.md"

# Below this share of live model calls, the headline numbers are withheld:
# they would be grading the offline fallbacks, not the model.
MIN_LIVE_SHARE = 0.9


def _load(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _save(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ build --


def cmd_build(args: argparse.Namespace) -> int:
    if not config.has_tmdb():
        print("TMDB_API_KEY is not set — the film sample is built from TMDb.", file=sys.stderr)
        return 2
    snapshot = dataset.build(
        released_after=args.released_after, released_before=args.released_before,
        votes_floor=args.votes_floor, want=args.want,
    )
    dataset.save(snapshot)
    films = snapshot["films"]
    print(f"{len(films)} films from {snapshot['candidates_seen']} candidates "
          f"({snapshot['skipped_ineligible']} ineligible) -> {dataset.SNAPSHOT}")
    if films:
        actuals = [f["actual_audience_score"] for f in films]
        print(f"  ground truth: mean {statistics.fmean(actuals):.1f}, "
              f"spread {statistics.pstdev(actuals):.1f}, "
              f"range {min(actuals):.0f}-{max(actuals):.0f}")
    if len(films) < 30:
        print("  WARNING: under 30 films. Widen the window or lower --votes-floor.")
    return 0


# ------------------------------------------------------------------- model --


def pin(args: argparse.Namespace) -> str:
    """One provider, one model, no fallback chain. Returns what was pinned.

    Without this, a run uses the configured chain — and a chain is exactly wrong
    here. Under load Groq answers 429, the call falls through to Gemini, and half
    the films get audited or scored by a model the other half never saw. Both
    numbers this directory reports are about *a* model's behaviour, so a run that
    silently mixes two measures nothing. Found by watching a leakage run print
    the google-genai SDK's warning while it was meant to be on Groq.

    A leakage check is the sharper case: a training cutoff is a property of one
    model, so the answer does not carry from one to another at all.
    """
    provider = getattr(args, "provider", None)
    if not provider:
        return ""
    config.LLM_PROVIDERS = [provider]
    chosen = getattr(args, "model", None) or {
        "cerebras": config.CEREBRAS_FLASH_MODEL,
        "groq": config.GROQ_FLASH_MODEL,
        "gemini": config.GEMINI_FLASH_MODEL,
        "ollama": config.OLLAMA_FLASH_MODEL,
    }[provider]
    for name in ("CEREBRAS", "GROQ", "GEMINI", "OLLAMA"):
        setattr(config, f"{name}_FLASH_MODEL", chosen)
        setattr(config, f"{name}_PRO_MODEL", chosen)
    config.GEMINI_FALLBACK_MODELS = []
    if not config.configured_llm_providers():
        raise SystemExit(f"{provider} is not configured. Set its key (or OLLAMA_HOST) first.")
    return f"{provider}:{chosen}"


def add_model_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=["cerebras", "groq", "gemini", "ollama"],
                        help="pin every call to this provider instead of using the fallback "
                             "chain, so one model answers the whole run")
    parser.add_argument("--model", default=None, help="override that provider's configured model")


# ---------------------------------------------------------------- leakage --


def cmd_leakage(args: argparse.Namespace) -> int:
    films = dataset.load()["films"]
    pinned = pin(args)
    stored = _load(LEAKAGE, {})
    audited_by = stored.pop("audited_by", None) if isinstance(stored, dict) else None
    results = {k: v for k, v in stored.items() if isinstance(v, dict) and "leaked" in v}

    if pinned and audited_by and audited_by != pinned:
        # Whose memory was checked is the whole content of this file. Mixing two
        # models' answers gives a sample filtered by neither.
        raise SystemExit(
            f"{LEAKAGE.name} was written against {audited_by} and this run is {pinned}. "
            "A training cutoff belongs to one model, so the two cannot be merged: delete "
            f"{LEAKAGE.name} and re-run, or pass --provider to match."
        )
    print(f"auditing with {pinned or 'the configured provider chain — pass --provider to pin one'}\n")

    for index, film in enumerate(films, 1):
        key = str(film["tmdb_id"])
        if key in results and not args.force:
            continue
        results[key] = dataset.probe_leakage(film)
        _save(LEAKAGE, {"audited_by": pinned or audited_by, **results})
        flag = "LEAKED" if results[key]["leaked"] else "ok"
        print(f"  [{index}/{len(films)}] {film['title'][:40]:<40} {flag}")
        time.sleep(args.delay)
    leaked = [r for r in results.values() if r["leaked"]]
    answered = {r.get("model") for r in results.values() if r.get("model")}
    print(f"{len(leaked)} of {len(results)} films recalled with a rating within 10 points.")
    if len(answered) > 1:
        print(
            f"  WARNING: {sorted(answered)} each answered part of this. A training cutoff is one "
            f"model's, so this file is not a usable check. Delete {LEAKAGE.name} and re-run "
            "with --provider."
        )
    return 0


# ---------------------------------------------------------------- predict --


def _bind(name: str, args: argparse.Namespace):
    """The predictor as a one-argument callable, with its run options applied.

    Only `lumen` takes options; the baseline has none to take, which is rather
    the point of it.
    """
    if name == "lumen":
        return lambda film: predictors.lumen(
            film, panel_size=args.panel_size, analysis_mode=args.analysis)
    return predictors.REGISTRY[name]


_exhausted = False


def _watch_for_a_spent_budget() -> None:
    """Stop the run when the day's tokens are gone rather than scoring mocks.

    A film scored after the budget runs out is scored entirely by the
    simulator's offline fallbacks, and a sweep that keeps going fills the store
    with rows that look like predictions and are not.
    """
    global _exhausted
    original = llm.generate_json_traced

    def watched(prompt, **kwargs):
        global _exhausted
        data, meta = original(prompt, **kwargs)
        if meta.get("error") and llm.is_daily_limit(str(meta["error"])):
            _exhausted = True
        return data, meta

    llm.generate_json_traced = watched
    audience_sim.llm.generate_json_traced = watched


def cmd_predict(args: argparse.Namespace) -> int:
    global _exhausted
    _exhausted = False
    films = dataset.load()["films"]
    pinned = pin(args)
    _watch_for_a_spent_budget()
    # A free tier is the binding constraint, not the model. One call at a time
    # and a long wait is the difference between scoring the simulator and
    # scoring its offline fallbacks.
    config.LLM_MAX_CONCURRENCY = max(1, args.concurrency)
    config.LLM_MAX_RETRY_WAIT_S = args.patience
    print(f"  {config.LLM_MAX_CONCURRENCY} call(s) at a time, waiting up to "
          f"{config.LLM_MAX_RETRY_WAIT_S:.0f}s on a rate limit")
    print(f"scoring with {pinned or 'the configured provider chain — pass --provider to pin one'}")
    store = _load(PREDICTIONS, {})
    for name in args.predictor:
        predict = _bind(name, args)
        rows = store.setdefault(name, {})
        print(f"\n{name}:")
        # Films still owed a live score. Counted up front so --limit can cut a
        # run to what a daily quota affords: the next run picks up the rest.
        todo = [f for f in films
                if args.force or not ((rows.get(str(f["tmdb_id"])) or {}).get("live"))]
        if args.limit:
            todo = todo[:args.limit]
        skipped = len(films) - len(todo)
        if skipped:
            print(f"  ({skipped} already scored live, skipping)")
        for index, film in enumerate(todo, 1):
            key = str(film["tmdb_id"])
            if _exhausted:
                print("  stopping: the provider's daily token budget is spent.")
                break
            try:
                rows[key] = predict(film)
            except Exception as exc:  # noqa: BLE001 — one bad film must not lose the rest
                rows[key] = {"audience_score": None, "live": False,
                             "error": f"{type(exc).__name__}: {exc}"[:200]}
            _save(PREDICTIONS, store)
            row = rows[key]
            got = row.get("audience_score")
            shown = got if got is not None else "--"
            note = "" if row.get("live") else "(FELL BACK)"
            print(f"  [{index}/{len(todo)}] {film['title'][:38]:<38} "
                  f"pred {shown:>6} actual {film['actual_audience_score']:>5} {note}")
            time.sleep(args.delay)
    return 0


# ----------------------------------------------------------------- report --


def _pairs(films: list[dict], rows: dict, field: str = "audience_score") -> list[tuple[float, float]]:
    out = []
    for film in films:
        row = rows.get(str(film["tmdb_id"])) or {}
        if row.get(field) is not None:
            out.append((float(row[field]), float(film["actual_audience_score"])))
    return out


def _usable(films: list[dict], store: dict, names: list[str]) -> list[dict]:
    """Films every named predictor scored on a fully live run.

    The comparison is paired, so it can only use films both predictors saw; and
    a film one of them fell back on is dropped rather than compared, because the
    fallback is a fixed number that has nothing to do with the film.
    """
    keep = []
    for film in films:
        rows = [(store.get(name) or {}).get(str(film["tmdb_id"])) or {} for name in names]
        if all(r.get("audience_score") is not None and r.get("live") for r in rows):
            keep.append(film)
    return keep


def cmd_report(args: argparse.Namespace) -> int:
    snapshot = dataset.load()
    films = snapshot["films"]
    store = _load(PREDICTIONS, {})
    leakage = _load(LEAKAGE, {})

    names = [n for n in args.predictor if n in store]
    if not names:
        print("No predictions yet. Run `python -m eval.run predict` first.", file=sys.stderr)
        return 1

    dropped_leaked = []
    if leakage and not args.keep_leaked:
        leaked_ids = {k for k, v in leakage.items() if v.get("leaked")}
        dropped_leaked = [f["title"] for f in films if str(f["tmdb_id"]) in leaked_ids]
        films = [f for f in films if str(f["tmdb_id"]) not in leaked_ids]

    graded = _usable(films, store, names)
    attempted = {n: len(store.get(n) or {}) for n in names}
    # Why films failed, most common first. Without this the report can only say
    # "nothing was graded", and the reader goes looking for a missing key when
    # the real answer was a spent quota.
    reasons: dict[str, int] = {}
    for name in names:
        for row in (store.get(name) or {}).values():
            if row.get("audience_score") is None or not row.get("live"):
                reason = str(row.get("error") or "fell back to offline sample output")[:120]
                reasons[reason] = reasons.get(reason, 0) + 1
    failure_reasons = dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:5])
    live_share = (len(graded) / len(films)) if films else 0.0

    actuals = [f["actual_audience_score"] for f in graded]
    constant_value = round(statistics.fmean(actuals), 1) if actuals else 0.0

    # A run stopped by a spent quota can leave nothing gradeable at all. That is
    # a reportable state, not a crash: the report still has to say what was
    # attempted and why it is withholding.
    results: dict[str, Any] = {}
    contrasts: dict[str, Any] = {}
    tomatometer_rho = None
    if graded:
        for name in names:
            results[name] = metrics.score(_pairs(graded, store[name]))
        results["constant"] = metrics.score([(constant_value, a) for a in actuals])

    if "lumen" in results:
        lumen_pairs = _pairs(graded, store["lumen"])
        if "single_call" in results:
            contrasts["lumen_vs_single_call"] = metrics.paired_bootstrap_mae(
                lumen_pairs, _pairs(graded, store["single_call"]))
        contrasts["lumen_vs_constant"] = metrics.paired_bootstrap_mae(
            lumen_pairs, [(constant_value, a) for a in actuals])

    # The tomatometer has no ground truth of its own (no free critic-score API),
    # so it is graded on ordering against the audience rating only.
    if graded and "lumen" in store:
        tm = _pairs(graded, store["lumen"], field="tomatometer")
        if len(tm) >= 3:
            tomatometer_rho = {"spearman": round(metrics.spearman(tm), 3),
                               "spearman_p": round(metrics.permutation_p(tm), 4),
                               "n": len(tm)}

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshot": {k: snapshot[k] for k in ("fetched_at", "query", "eligibility", "ground_truth")},
        "films_in_snapshot": len(snapshot["films"]),
        "films_graded": len(graded),
        "films_attempted": attempted,
        "live_share": round(live_share, 3),
        "withheld": live_share < MIN_LIVE_SHARE,
        # Which models actually answered. The client falls back down a chain on
        # a rate limit, so more than one name here means the column is an
        # average over two different systems and should be read as such.
        "models_used": {
            name: sorted({
                model
                for row in (store.get(name) or {}).values()
                for model in (row.get("models") or [])
            })
            for name in names
        },
        "dropped_for_leakage": dropped_leaked,
        "failure_reasons": failure_reasons,
        "constant_baseline_value": constant_value,
        "results": results,
        "contrasts": contrasts,
        "tomatometer_ordering": tomatometer_rho,
    }
    _save(REPORT_JSON, payload)
    REPORT_MD.write_text(render_markdown(payload), encoding="utf-8")
    print(render_markdown(payload))
    print(f"\n-> {REPORT_MD}\n-> {REPORT_JSON}")
    return 0


LABELS = {
    "lumen": "Lumen audience simulator",
    "single_call": "One LLM call",
}


def render_markdown(p: dict) -> str:
    q = p["snapshot"]["query"]
    rows = p["results"]
    order = [n for n in ("lumen", "single_call", "constant") if n in rows]
    labels = dict(LABELS, constant=f"Always answer {p['constant_baseline_value']}")

    lines = [
        "# Audience simulator: evaluation",
        "",
        "Generated by `python -m eval.run report`. Numbers, caveats and all.",
        "",
        f"- **Films graded:** {p['films_graded']} of {p['films_in_snapshot']} in the snapshot",
        f"- **Ground truth:** {p['snapshot']['ground_truth']}",
        "- **Sample:** every English-language feature on TMDb released "
        f"{q['primary_release_date.gte']} to {q['primary_release_date.lte']} with at least "
        f"{q['vote_count.gte']} ratings, most-rated first",
        f"- **Snapshot taken:** {p['snapshot']['fetched_at']}",
        "- **Models that answered:** "
        + (", ".join(
            f"{name} — {', '.join(models) if models else 'none (no live call)'}"
            for name, models in (p.get("models_used") or {}).items()
        ) or "none recorded"),
        "",
    ]
    if p["withheld"]:
        lines += [
            f"> **Incomplete run.** Only {p['live_share']:.0%} of films were scored by a live "
            "model; the rest fell back to offline sample output. These numbers grade the "
            "fallbacks as much as the model. Re-run `predict` before quoting them.",
            "",
        ]

    if not order:
        lines += [
            "## Results",
            "",
            "No films were graded, so there is nothing to report: every film either went "
            "unscored or fell back to offline sample output. What the calls returned:",
            "",
        ]
        for reason, count in (p.get("failure_reasons") or {}).items():
            lines.append(f"- {count} x `{reason}`")
        lines += [
            "",
            f"Attempted: {p['films_attempted']}. Fix the cause above, then re-run "
            "`python -m eval.run predict` — films already scored live are skipped, so a run "
            "stopped by a quota resumes rather than starting over.",
            "",
        ]
        return "\n".join(lines)

    lines += [
        "## Results",
        "",
        "| Predictor | n | MAE | RMSE | Bias | Spearman rho | p | Mean | Spread |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in order:
        r = rows[name]
        lines.append(
            f"| {labels[name]} | {r['n']} | **{r['mae']}** | {r['rmse']} | {r['bias']:+} | "
            f"{r['spearman']} | {r['spearman_p']} | {r['predicted_mean']} | {r['predicted_spread']} |"
        )
    reference = rows[order[0]]
    lines += [
        "",
        f"The films themselves: mean {reference['actual_mean']}, spread "
        f"{reference['actual_spread']}.",
        "",
        "MAE and RMSE are in points of a 0-100 rating. Bias is the mean signed error — "
        "positive means the predictor is too generous. Spearman is rank correlation, and "
        "`p` is a 10,000-round permutation test: how often shuffling the answers produces "
        "a correlation at least this strong by chance.",
        "",
    ]

    if p["contrasts"]:
        lines += ["## Does the panel earn its keep?", ""]
        for key, c in p["contrasts"].items():
            against = key.replace("lumen_vs_", "").replace("_", " ")
            lines.append(
                f"- **vs {against}:** MAE gap {c['mae_gap']:+} points "
                f"(95% CI {c['ci95_low']:+} to {c['ci95_high']:+}) — {c['verdict']}."
            )
        lines += [
            "",
            "A negative gap means Lumen has the lower error. Paired bootstrap over films, "
            "10,000 resamples: an interval straddling zero means this sample cannot tell "
            "the two apart.",
            "",
        ]

    if p["tomatometer_ordering"]:
        t = p["tomatometer_ordering"]
        lines += [
            "## Tomatometer",
            "",
            "No free critic-score API exists, so the tomatometer has no ground truth to be "
            "scored against. All that can be checked is whether it orders films the way "
            f"audience ratings do: Spearman rho {t['spearman']} (p {t['spearman_p']}, "
            f"n {t['n']}). It is not validated against Rotten Tomatoes and should not be "
            "read as a prediction of one.",
            "",
        ]

    lines += [
        "## What this does and does not show",
        "",
        "- **Synopses, not screenplays.** Each predictor sees a few hundred words: genre, "
        "runtime, year, synopsis. The product reads a whole screenplay, which is far more "
        "to go on. This is the harder version of the task, so read these numbers as a floor.",
        "- **Titles are withheld.** A model that recognises a film can recall its reception "
        "instead of predicting it. Only the synopsis is shown, and the sample is restricted "
        "to films released after the model's training cutoff.",
    ]
    if p["dropped_for_leakage"]:
        lines.append(
            "- **Leakage check.** `run.py leakage` asked the model outright which films it "
            f"knew; {len(p['dropped_for_leakage'])} recalled a rating within 10 points of "
            f"the real one and were dropped: {', '.join(p['dropped_for_leakage'])}."
        )
    lines += [
        "- **TMDb ratings are not Rotten Tomatoes.** Different population, different prompt, "
        "different scale habits. The simulator is graded here against public ratings from "
        "people who chose to rate a film they chose to watch, which is not a test screening.",
        f"- **Small sample.** {p['films_graded']} films. A difference of a point or two in "
        "MAE is noise; that is what the confidence intervals above are for.",
        "- **No per-scene validation.** The scene heatmap and the recut suggestion are not "
        "evaluated here. Nothing public grades them.",
        "",
        "Reproduce: `cd backend && python -m eval.run report`. Raw numbers in "
        "`eval/report.json`, per-film predictions in `eval/predictions.json`.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="fetch the film sample from TMDb")
    build.add_argument("--released-after", required=True)
    build.add_argument("--released-before", required=True)
    build.add_argument("--votes-floor", type=int, default=dataset.DEFAULT_VOTES_FLOOR)
    build.add_argument("--want", type=int, default=40)
    build.set_defaults(func=cmd_build)

    leak = sub.add_parser("leakage", help="ask the model which films it already knows")
    leak.add_argument("--delay", type=float, default=1.0)
    leak.add_argument("--force", action="store_true")
    add_model_arguments(leak)
    leak.set_defaults(func=cmd_leakage)

    pred = sub.add_parser("predict", help="score every film with each predictor")
    pred.add_argument("--predictor", action="append", choices=sorted(predictors.REGISTRY))
    add_model_arguments(pred)
    pred.add_argument("--concurrency", type=int, default=1,
                      help="cohort calls in flight at once (default 1). The product uses 3; on a "
                           "free tier three large prompts at once blow a per-minute token limit "
                           "and every batch falls back, which grades the fallbacks")
    pred.add_argument("--patience", type=float, default=90.0,
                      help="seconds to wait out a rate limit before giving up on a model "
                           "(default 90; the product waits 20, which is right for a web request "
                           "and wrong for an overnight run)")
    pred.add_argument("--delay", type=float, default=1.0)
    pred.add_argument("--force", action="store_true")
    pred.add_argument("--limit", type=int, default=0,
                      help="score at most this many films this run (0 = all). The free "
                           "tier allows 20 calls a day per model, so a full sample takes "
                           "several days; each run resumes where the last stopped.")
    pred.add_argument("--panel-size", type=int, default=predictors.EVAL_PANEL_SIZE,
                      help=f"personas per film (default {predictors.EVAL_PANEL_SIZE}, the product's own)")
    pred.add_argument("--analysis", choices=("brief", "model"), default="brief",
                      help="'brief' derives the material analysis from TMDb metadata (free); "
                           "'model' runs the production read, about one extra call per film")
    pred.set_defaults(func=cmd_predict)

    rep = sub.add_parser("report", help="compute the metrics and write REPORT.md")
    rep.add_argument("--predictor", action="append")
    rep.add_argument("--keep-leaked", action="store_true")
    rep.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    if getattr(args, "predictor", None) is None:
        args.predictor = sorted(predictors.REGISTRY)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
