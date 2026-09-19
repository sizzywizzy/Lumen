"""Actor search recall: `resolve`, `build`, `score`, `report`.

    cd backend
    python -m eval.casting.run resolve   # briefs -> right answers, from TMDb
    python -m eval.casting.run build     # fetch the corpus, parts held out
    python -m eval.casting.run score     # rank every brief, three ways
    python -m eval.casting.run report

`resolve` and `build` need TMDB_API_KEY, which is free. `score` needs
sentence-transformers locally and nothing else — no model API, no quota, no
database. Steps are separate so the corpus cannot be rebuilt after seeing a
result, which is the door through which a sample gets tuned until it flatters.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

from core import config
from eval.casting import corpus, metrics, search
from eval.casting.labels import LABELS
from services import json_files

# What ships, so a report can say when it scored something else instead.
DEFAULT_MODEL = config.EMBEDDING_MODEL

# A Windows console defaults to cp1252, which cannot encode an actor's name or
# a film title with a diacritic in it — and an evaluation that crashes on
# "Yūsuke" would be one that quietly only works on some of its own data.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
QUERIES = HERE / "queries.json"
ACTORS = HERE / "actors.json"
RANKS = HERE / "ranks.json"
REPORT_JSON = HERE / "report.json"
REPORT_MD = HERE / "REPORT.md"

INDEXES = ("semantic", "semantic_roles_first", "lexical", "chance")
DEPTH = 50  # ranks deeper than this are recorded as "not found"


def _load(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


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


# ---------------------------------------------------------------- resolve --


def do_resolve(_args) -> int:
    queries, unresolved = corpus.resolve(LABELS, on_step=lambda m: print(f"  {m}", flush=True))
    _save(QUERIES, {
        "resolved_at": _now(),
        "labels_written": len(LABELS),
        "resolved": len(queries),
        "unresolved": unresolved,
        "queries": queries,
    })
    print(f"\n{len(queries)} of {len(LABELS)} briefs resolved to an actor. Written to {QUERIES.name}.")
    for problem in unresolved:
        print(f"  unresolved: {problem['film']} — {problem['why']}")
    return 0


# ------------------------------------------------------------------ build --


def do_build(args) -> int:
    resolved = _load(QUERIES)
    if not resolved:
        print(f"No {QUERIES.name}. Run `resolve` first.", file=sys.stderr)
        return 1
    built = corpus.build(
        resolved["queries"],
        distractor_pages=args.distractor_pages,
        on_step=lambda m: print(f"  {m}", flush=True),
    )
    _save(ACTORS, {
        "built_at": _now(),
        "corpus_size": len(built["actors"]),
        "answers": len(built["held_out"]),
        "distractor_pages": built["distractor_pages"],
        "skipped": built["skipped"],
        "held_out": built["held_out"],
        "actors": built["actors"],
    })
    print(f"\n{len(built['actors'])} actors, {len(built['held_out'])} of them an answer. "
          f"Written to {ACTORS.name}.")
    return 0


# ------------------------------------------------------------------ score --


def do_score(args) -> int:
    resolved, built = _load(QUERIES), _load(ACTORS)
    if not resolved or not built:
        print("Run `resolve` and `build` first.", file=sys.stderr)
        return 1

    actors = built["actors"]
    known = {int(a["actor_id"]) for a in actors}
    queries = [q for q in resolved["queries"] if q["answer"]["tmdb_id"] in known]
    missing = len(resolved["queries"]) - len(queries)

    if getattr(args, "embedding_model", None):
        # The product reads this setting for both the stored vectors and the
        # query, so overriding it here keeps the two sides in step — the one
        # thing that must never differ between them.
        config.EMBEDDING_MODEL = args.embedding_model
    model = corpus.embedder() if any("semantic" in k for k in args.index) else None
    suffix = "" if corpus.model_name() == DEFAULT_MODEL else f" ({corpus.model_name().split('/')[-1]})"
    ranks: dict[str, dict[str, Optional[int]]] = {}
    for kind in args.index:
        print(f"  building the {kind} index over {len(actors)} actors", flush=True)
        index = search.build(kind, actors, model)
        found = {}
        for query in queries:
            retrieved = index.rank(query["brief"], DEPTH)
            found[query["id"]] = metrics.rank_of(query["answer"]["tmdb_id"], retrieved)
        ranks[f"{kind}{suffix}" if "semantic" in kind else kind] = found
        hit = sum(1 for r in found.values() if r and r <= 10)
        print(f"    recall@10 {hit}/{len(queries)}", flush=True)

    existing = _load(RANKS, {}) or {}
    if existing.get("embedding_model") not in (None, corpus.model_name()):
        ranks = {**existing.get("ranks", {}), **ranks}  # keep both models' rows
    _save(RANKS, {
        "scored_at": _now(),
        "corpus_size": len(actors),
        "queries_scored": len(queries),
        "queries_without_an_actor_in_the_corpus": missing,
        "embedding_model": corpus.model_name(),
        "depth": DEPTH,
        "ranks": ranks,
    })
    print(f"\nWritten to {RANKS.name}. Now: python -m eval.casting.run report")
    return 0


# ----------------------------------------------------------------- report --


def do_report(_args) -> int:
    scored, resolved = _load(RANKS), _load(QUERIES)
    if not scored or not resolved:
        print("Run `score` first.", file=sys.stderr)
        return 1

    size = scored["corpus_size"]
    by_index: dict[str, Any] = {}
    for kind, found in scored["ranks"].items():
        ranks = list(found.values())
        total = len(ranks)
        by_index[kind] = {
            "queries": total,
            "recall@5": round(metrics.recall_at(ranks, 5), 4),
            "recall@10": round(metrics.recall_at(ranks, 10), 4),
            "recall@10_interval": [round(v, 4) for v in metrics.wilson_interval(
                sum(1 for r in ranks if r and r <= 10), total)],
            "mrr": round(metrics.mrr(ranks), 4),
            "median_rank_when_found": _median([r for r in ranks if r]),
            "never_found": sum(1 for r in ranks if r is None),
        }

    # Every semantic row against the two floors: an alternative model is only
    # interesting next to the thing it has to beat.
    contrasts = {}
    lexical = scored["ranks"].get("lexical")
    for name, found in scored["ranks"].items():
        if not name.startswith("semantic"):
            continue
        for other in ("lexical", "chance"):
            if other in scored["ranks"]:
                contrasts[f"{name} vs {other}"] = metrics.paired_bootstrap(
                    list(found.values()), list(scored["ranks"][other].values()), 10
                )

    payload = {
        "generated_at": _now(),
        "corpus_size": size,
        "queries": scored["queries_scored"],
        "embedding_model": scored["embedding_model"],
        "depth": scored["depth"],
        "chance_recall@5": round(metrics.chance_recall_at(5, size), 4),
        "chance_recall@10": round(metrics.chance_recall_at(10, size), 4),
        "indexes": by_index,
        "contrasts": contrasts,
    }
    _save(REPORT_JSON, payload)
    REPORT_MD.write_text(_markdown(payload, resolved), encoding="utf-8")
    print(f"Wrote {REPORT_JSON.name} and {REPORT_MD.name}\n")
    print(_markdown(payload, resolved))
    return 0


def _median(values: list[int]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return float(ordered[middle]) if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _percent(value: Optional[float]) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _markdown(payload: dict[str, Any], resolved: dict[str, Any]) -> str:
    rows = []
    ordered = [k for k in INDEXES if k in payload["indexes"]]
    ordered += [k for k in payload["indexes"] if k not in ordered]
    for kind in ordered:
        entry = payload["indexes"][kind]
        low, high = entry["recall@10_interval"]
        rows.append(
            f"| `{kind}` | {_percent(entry['recall@5'])} | {_percent(entry['recall@10'])} "
            f"({_percent(low)}–{_percent(high)}) | {entry['mrr']:.3f} | "
            f"{entry['median_rank_when_found'] or '—'} | {entry['never_found']} |"
        )

    out = [
        "# Actor search: does it find the right actor?",
        "",
        "Generated by `python -m eval.casting.run report`.",
        "",
        f"- **Briefs:** {payload['queries']} casting briefs, each written by hand from a real part "
        "and resolved to its actor through TMDb",
        f"- **Corpus:** {payload['corpus_size']} actors. The part each brief was drawn from is "
        "removed from that actor's record before anything is embedded",
        f"- **Model:** `{payload['embedding_model']}`, run locally",
        f"- **Ranked to depth {payload['depth']}**; anything below that counts as not found",
        "",
        "| index | recall@5 | recall@10 (95%) | MRR | median rank when found | never found |",
        "|---|---:|---:|---:|---:|---:|",
        *rows,
        "",
        f"Chance alone scores {_percent(payload['chance_recall@5'])} at 5 and "
        f"{_percent(payload['chance_recall@10'])} at 10 on a corpus this size. Any number near "
        "that line is evidence of nothing.",
        "",
    ]

    for name, contrast in payload["contrasts"].items():
        out += [
            f"**`{name}`:** recall@10 differs by {contrast['gap'] * 100:+.0f} points "
            f"(95% interval {contrast['low'] * 100:+.0f} to {contrast['high'] * 100:+.0f}, "
            f"p = {contrast['p']:.3f} that the first is not actually ahead).",
            "",
        ]
    out += [_verdict(payload), ""]

    if resolved.get("unresolved"):
        out += [
            "## Briefs that did not resolve",
            "",
            "Dropped rather than guessed at, since a wrong label is worse than a missing one:",
            "",
            *[f"- {p['film']} — {p['why']}" for p in resolved["unresolved"]],
            "",
        ]

    out += [
        "## What this cannot tell you",
        "",
        "- **A corpus of a few thousand is not a casting database.** Recall falls as the pool "
        "grows, so this is an upper bound on what the same search would do over every working "
        "actor.",
        "- **The distractors are famous people.** They come from TMDb's popular pages, so the "
        "pool is more uniform — and probably harder to separate — than a real roster of local "
        "actors with thin credits. Which way that biases the number is not obvious, and it is not "
        "measured here.",
        "- **One right answer per brief.** Several actors could play most of these parts well. A "
        "brief whose top five are all plausible is scored as a miss unless the one who actually "
        "got the part is among them, so recall here understates usefulness.",
        "- **The briefs are mine.** I wrote them after knowing who played the part, and no amount "
        "of care fully removes that. They name no actor, film or character — a test enforces all "
        "three — but a subtler echo of the performance is possible.",
        "- **Nothing here tests the age and gender filters** the product's search also applies. "
        "Ranking is measured unfiltered, and those filters could only help.",
        "",
    ]
    return "\n".join(out)


def _verdict(payload: dict[str, Any]) -> str:
    semantic = payload["indexes"].get("semantic")
    lexical = payload["indexes"].get("lexical")
    if not semantic:
        return "**The shipped index was not scored**, so there is nothing to conclude."

    chance = payload["chance_recall@10"]
    contrast = payload["contrasts"].get("semantic vs lexical", {})
    if semantic["recall@10"] <= chance * 2:
        return (
            f"**The search is not working.** recall@10 of {_percent(semantic['recall@10'])} against "
            f"{_percent(chance)} for a shuffle is not a retrieval system. Check that the briefs and "
            "the actor records are embedded with the same model before concluding anything else."
        )
    if lexical and contrast and contrast.get("high", 0) < 0:
        return (
            f"**Word overlap beats the embedding.** {_percent(semantic['recall@10'])} against "
            f"{_percent(lexical['recall@10'])} at 10, and the interval on the gap "
            f"({contrast['low'] * 100:+.0f} to {contrast['high'] * 100:+.0f} points) stays below "
            "zero, so this is not a quirk of the sample. On this task the sentence-transformer "
            "dependency is costing accuracy rather than buying it."
        )
    if lexical and contrast and contrast.get("low", 0) > 0:
        return (
            f"**The embedding earns its place.** recall@10 of {_percent(semantic['recall@10'])} "
            f"against {_percent(lexical['recall@10'])} for word overlap, and the interval on the "
            "gap stays above zero — so the difference is not just this sample."
        )
    if lexical and contrast:
        return (
            f"**The embedding does not clearly beat counting words.** "
            f"{_percent(semantic['recall@10'])} against {_percent(lexical['recall@10'])} at 10, with "
            f"the gap's interval running from {contrast['low'] * 100:+.0f} to "
            f"{contrast['high'] * 100:+.0f} points — it crosses zero, so on this sample the "
            "sentence-transformer dependency is not paying for itself. More briefs would narrow it."
        )
    return (
        f"**recall@10 is {_percent(semantic['recall@10'])}** against {_percent(chance)} for chance."
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.casting.run", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("resolve", help="turn the hand-written briefs into labelled queries")
    build = sub.add_parser("build", help="fetch the corpus from TMDb, parts held out")
    build.add_argument("--distractor-pages", type=int, default=25, help="20 people a page")
    score = sub.add_parser("score", help="rank every brief with each index")
    score.add_argument("--index", action="append", choices=INDEXES, default=None)
    score.add_argument("--embedding-model", default=None,
                       help="score with another sentence-transformers model instead of "
                            "EMBEDDING_MODEL, to tell a bad model from a bad approach")
    sub.add_parser("report", help="compute the metrics and write REPORT.md")

    args = parser.parse_args(argv)
    if getattr(args, "index", None) is None and args.command == "score":
        args.index = list(INDEXES)
    return {
        "resolve": do_resolve, "build": do_build, "score": do_score, "report": do_report,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
