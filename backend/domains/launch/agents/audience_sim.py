"""Audience Simulation Agent (Phase V).

A staged agent workflow, not a chat wrapper:

  1. analyse_material   — one grounded read of the supplied script/synopsis
  2. build_panel        — N seeded personas from a configurable distribution
  3. simulate_cohorts   — batched LLM elicitation, one voice per cohort
  4. derive_individuals — expand cohort verdicts to N individual responses
  5. aggregate          — segment breakdowns, distribution, polarization
  6. cultural_scan      — per-market risk review (optionally web-grounded)
  7. pr_recommendations — synthesis for a human to weigh

HOW 500 RESPONSES ARE PRODUCED (see docstring of `_derive_individuals`):
the LLM reasons once per *cohort* (<=28 of them, ~6 batched calls), then each
persona's individual response is derived from its cohort's verdict plus a
deterministic, explainable adjustment computed from the traits that vary
*within* that cohort — pacing tolerance, story preference, openness, taste,
familiarity, content sensitivity — and a seeded per-persona jitter.

That is a documented hybrid, and it is labelled as such everywhere it surfaces.
It is emphatically not 500 copies of one answer: every persona carries its own
dimension vector, and the spread within a cohort is driven by its members'
distinct attributes.
"""
import hashlib
import json
import statistics
from typing import Any, Callable, Optional

from core import config
from core.audience import personas as panel_lib
from core.messaging.envelope import broadcast, log_event, make_envelope, make_reply
from core.orchestrator.state import GlobalState
from domains.launch import audience_prompts as P
from services import gemini_client, tavily_client

COHORTS_PER_CALL = 5

# Dimensions we can score, and how much each contributes to a viewer's overall.
DIMENSION_WEIGHTS = {
    "story": 0.20, "characters": 0.18, "pacing": 0.14, "emotional_impact": 0.12,
    "originality": 0.10, "entertainment": 0.12, "dialogue": 0.06,
    "ending": 0.04, "genre_satisfaction": 0.04, "acting_potential": 0.0,
}


def _clamp(value: float, low: float = 1.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def _jitter(persona_id: str, key: str, seed: int, spread: float) -> float:
    """Deterministic per-persona noise in [-spread, +spread]."""
    digest = hashlib.sha256(f"{seed}:{persona_id}:{key}".encode()).digest()
    unit = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF  # 0..1
    return (unit * 2 - 1) * spread


# ---------------------------------------------------------------- stage 1 --


def analyse_material(state: GlobalState, material: str, trace: list) -> dict:
    """Ground the whole simulation in what the material actually says."""
    request = log_event(state, make_envelope(
        "agent_persona_foundry", "agent_script_analyst", "screen_film",
        {"material_chars": len(material), "title_id": state.project_id},
    ))
    prompt = (
        "Analyse this film material for audience research.\n\n"
        f"--- MATERIAL START ---\n{material[:24000]}\n--- MATERIAL END ---"
    )
    analysis, meta = gemini_client.generate_json_traced(
        prompt, tier="pro", system=P.ANALYSIS_SYSTEM, mock=P.MOCK_ANALYSIS
    )
    trace.append({"stage": "analyse_material", **meta})
    log_event(state, make_reply(request, "agent_script_analyst", "screen_film", {
        "genre": analysis.get("genre"),
        "themes": analysis.get("themes", [])[:5],
        "content_flags": len(analysis.get("content_flags", [])),
        "source": meta.get("source"),
    }))
    return analysis


# ---------------------------------------------------------------- stage 3 --


def simulate_cohorts(
    state: GlobalState, analysis: dict, cohorts: list[dict], trace: list
) -> dict[str, dict]:
    """One batched LLM call per group of cohorts; each cohort gets its own voice."""
    dimensions = [d for d in analysis.get("evaluable_dimensions", []) if d in DIMENSION_WEIGHTS]
    if not dimensions:
        dimensions = ["story", "characters", "pacing", "entertainment"]

    material_summary = json.dumps({
        "genre": analysis.get("genre"), "logline": analysis.get("logline"),
        "tone": analysis.get("tone"), "setting": analysis.get("setting"),
        "pacing_read": analysis.get("pacing_read"), "themes": analysis.get("themes"),
        "main_characters": analysis.get("main_characters"),
        "major_conflicts": analysis.get("major_conflicts"),
        "content_flags": analysis.get("content_flags"),
        "potentially_polarizing": analysis.get("potentially_polarizing"),
        "material_quality": analysis.get("material_quality"),
    }, ensure_ascii=False)

    batches = [cohorts[i:i + COHORTS_PER_CALL] for i in range(0, len(cohorts), COHORTS_PER_CALL)]

    request = log_event(state, make_envelope(
        "agent_aggregation", "agent_viewer", "screen_film",
        {"cohorts": len(cohorts), "batches": len(batches), "panel_size": sum(c["size"] for c in cohorts)},
    ))

    def run_batch(batch: list[dict]):
        described = [
            {
                "cohort_id": c["cohort_id"], "size": c["size"],
                "age_band": c["age_band_name"], "markets": c["markets"][:4],
                "market_region": c["market_bloc_name"],
                "already_watches_this_genre": c["genre_affinity"] == "genre_fan",
                "common_genre_tastes": c["common_genres"],
                "taste_mix": c["taste_mix"], "pacing_tolerance_mix": c["pacing_mix"],
            }
            for c in batch
        ]
        prompt = (
            f"FILM MATERIAL ANALYSIS:\n{material_summary}\n\n"
            f"SCORE ONLY THESE DIMENSIONS: {dimensions}\n\n"
            f"AUDIENCE COHORTS:\n{json.dumps(described, ensure_ascii=False)}\n\n"
            "Give each cohort its own distinct verdict."
        )
        return gemini_client.generate_json_traced(
            prompt, tier="flash", system=P.COHORT_SYSTEM,
            mock={"cohorts": [{"cohort_id": c["cohort_id"], **P.MOCK_COHORT_VERDICT} for c in batch]},
        )

    results = gemini_client.map_concurrent(batches, run_batch)

    verdicts: dict[str, dict] = {}
    sources: list[str] = []
    for batch, result in zip(batches, results):
        if isinstance(result, Exception):
            trace.append({"stage": "simulate_cohorts", "source": "error", "error": str(result)[:200]})
            # a failed batch still needs verdicts, or those personas vanish
            for c in batch:
                verdicts[c["cohort_id"]] = {**P.MOCK_COHORT_VERDICT, "_degraded": True}
                sources.append("mock")
            continue
        payload, meta = result
        sources.append(meta.get("source", "unknown"))
        by_id = {c.get("cohort_id"): c for c in payload.get("cohorts", []) if isinstance(c, dict)}
        for c in batch:
            verdicts[c["cohort_id"]] = by_id.get(c["cohort_id"], {**P.MOCK_COHORT_VERDICT, "_degraded": True})

    live = sources.count("gemini")
    trace.append({
        "stage": "simulate_cohorts", "batches": len(batches),
        "source": "gemini" if live == len(batches) else ("mixed" if live else "mock"),
        "live_batches": live,
        "model": next((r[1].get("model") for r in results if not isinstance(r, Exception)), None),
    })

    log_event(state, make_reply(request, "agent_viewer", "screen_film", {
        "cohorts_scored": len(verdicts), "batches": len(batches), "live_batches": live,
    }))
    return verdicts


# ---------------------------------------------------------------- stage 4 --


def _derive_individuals(
    personas_list: list[dict], cohorts: list[dict], verdicts: dict[str, dict],
    dimensions: list[str], analysis: dict, seed: int,
) -> list[dict]:
    """Expand cohort verdicts into one response per persona.

    The adjustments below are the mechanism that makes 500 people 500 people.
    Each is a stated, auditable rule keyed to a trait the cohort did NOT encode,
    so two members of the same cohort diverge for a reason you can point at.
    """
    cohort_of = {pid: c for c in cohorts for pid in c["member_ids"]}
    flagged = {f.get("type"): f.get("level") for f in analysis.get("content_flags", [])}
    strong_flags = {t for t, lvl in flagged.items() if lvl in ("moderate", "strong")}

    responses = []
    for persona in personas_list:
        cohort = cohort_of[persona["persona_id"]]
        verdict = verdicts.get(cohort["cohort_id"], P.MOCK_COHORT_VERDICT)
        base = verdict.get("dimension_scores", {}) or {}

        scores: dict[str, float] = {}
        for dim in dimensions:
            value = float(base.get(dim, 6.5) or 6.5)

            if dim == "pacing":
                value += {"low": -1.6, "medium": 0.0, "high": 1.0}[persona["pacing_tolerance"]]
                if analysis.get("pacing_read", "").lower().startswith("deliberate"):
                    value += -0.5 if persona["pacing_tolerance"] == "low" else 0.2
            if dim == "characters" and persona["story_preference"] == "character-driven":
                value += 0.7
            if dim == "characters" and persona["story_preference"] == "plot-driven":
                value -= 0.4
            if dim == "story" and persona["story_preference"] == "plot-driven":
                value += 0.5
            if dim == "originality":
                value += {"low": -0.7, "medium": 0.0, "high": 0.9}[persona["experimental_openness"]]
                value += {"none": 0.4, "some": 0.0, "high": -0.6}[persona["prior_familiarity_with_similar"]]
            if dim == "entertainment":
                value += {"mainstream": 0.4, "balanced": 0.0, "niche": -0.3}[persona["taste_profile"]]
            if dim == "genre_satisfaction":
                value += {"low": -0.3, "medium": 0.0, "high": 0.5}[persona["genre_familiarity"]]

            value += _jitter(persona["persona_id"], dim, seed, 0.55)
            scores[dim] = round(_clamp(value), 2)

        # Content the viewer is averse to drags the whole experience down.
        penalty = 0.0
        for flag in strong_flags:
            axis = {
                "violence": "violence", "sexual_content": "sexual_content",
                "strong_language": "strong_language", "religious_reference": "religious_political",
                "political_reference": "religious_political",
            }.get(flag)
            if axis and persona["content_sensitivity"].get(axis) == "averse":
                penalty += 0.55

        weights = {d: DIMENSION_WEIGHTS.get(d, 0.1) for d in dimensions}
        total_weight = sum(weights.values()) or 1.0
        overall = sum(scores[d] * weights[d] for d in dimensions) / total_weight - penalty
        # Frequent viewers grade a little harder; occasional viewers a little softer.
        overall += {"high": -0.25, "medium": 0.0, "low": 0.2}[persona["viewing_frequency"]]
        overall = round(_clamp(overall), 2)

        watch_rate = float(verdict.get("would_watch_rate", 0.6) or 0.6)
        rec_rate = float(verdict.get("would_recommend_rate", 0.5) or 0.5)
        finish_rate = float(verdict.get("would_finish_rate", 0.75) or 0.75)
        # Convert cohort propensities into per-person decisions using the
        # person's own overall score and a stable pseudo-random draw.
        draw = (_jitter(persona["persona_id"], "decide", seed, 0.5) + 0.5)
        lift = (overall - 6.0) / 8.0
        responses.append({
            "persona_id": persona["persona_id"],
            "cohort_id": cohort["cohort_id"],
            "dimension_scores": scores,
            "overall_score": overall,
            "would_watch": draw < _clamp(watch_rate + lift, 0.02, 0.98),
            "would_recommend": draw < _clamp(rec_rate + lift, 0.02, 0.98),
            "would_finish": draw < _clamp(finish_rate + lift, 0.02, 0.99),
            "preferred_venue": persona["viewing_context"]
            if persona["viewing_context"] != "both" else verdict.get("preferred_venue", "streaming"),
            "sentiment": "positive" if overall >= 7.0 else ("mixed" if overall >= 5.5 else "negative"),
            "content_penalty": round(penalty, 2),
        })
    return responses


# ---------------------------------------------------------------- stage 5 --


# Human-readable prefix so a segment name is never ambiguous out of context
# ("low" alone could be pacing tolerance or viewing frequency).
SEGMENT_LABELS = {
    "age_group": "Age", "market_name": "Market", "viewing_frequency": "Watches films",
    "taste_profile": "Taste", "pacing_tolerance": "Tolerance for slow pacing",
    "viewing_context": "Watches via", "genre_affinity": "Genre",
}


def _segment(responses: list[dict], personas_by_id: dict, field: str, label_fn=None,
             dimension: str = "") -> list[dict]:
    buckets: dict[str, list[float]] = {}
    extras: dict[str, list[dict]] = {}
    for r in responses:
        persona = personas_by_id[r["persona_id"]]
        key = label_fn(persona) if label_fn else persona[field]
        buckets.setdefault(str(key), []).append(r["overall_score"])
        extras.setdefault(str(key), []).append(r)
    prefix = SEGMENT_LABELS.get(dimension or field, "")
    out = []
    for key, scores in buckets.items():
        rows = extras[key]
        out.append({
            "segment": key,
            "dimension": dimension or field,
            "label": f"{prefix}: {key}" if prefix and dimension not in ("genre_affinity",) else key,
            "n": len(scores),
            "mean_score": round(statistics.fmean(scores), 2),
            "would_watch_pct": round(100 * sum(r["would_watch"] for r in rows) / len(rows), 1),
            "would_recommend_pct": round(100 * sum(r["would_recommend"] for r in rows) / len(rows), 1),
            "spread": round(statistics.pstdev(scores), 2) if len(scores) > 1 else 0.0,
        })
    return sorted(out, key=lambda s: -s["mean_score"])


def aggregate(
    state: GlobalState, personas_list: list[dict], cohorts: list[dict],
    verdicts: dict[str, dict], responses: list[dict], dimensions: list[str],
) -> dict:
    personas_by_id = {p["persona_id"]: p for p in personas_list}
    overall_scores = [r["overall_score"] for r in responses]
    n = len(responses)

    histogram = {str(b): 0 for b in range(1, 11)}
    for score in overall_scores:
        histogram[str(max(1, min(10, int(round(score)))))] += 1

    dimension_means = {
        d: round(statistics.fmean([r["dimension_scores"][d] for r in responses]), 2)
        for d in dimensions
    }

    # Polarization: dimensions and cohorts where the panel genuinely splits.
    dimension_spread = {
        d: round(statistics.pstdev([r["dimension_scores"][d] for r in responses]), 2)
        for d in dimensions
    }
    cohort_by_id = {c["cohort_id"]: c for c in cohorts}
    cohort_rows = []
    for cid, cohort in cohort_by_id.items():
        rows = [r for r in responses if r["cohort_id"] == cid]
        if not rows:
            continue
        scores = [r["overall_score"] for r in rows]
        cohort_rows.append({
            "cohort_id": cid, "n": len(rows),
            "label": f"{cohort['age_band_name']} · {cohort['market_bloc_name']} · "
                     f"{'genre fans' if cohort['genre_affinity'] == 'genre_fan' else 'outside genre'}",
            "mean_score": round(statistics.fmean(scores), 2),
            "spread": round(statistics.pstdev(scores), 2) if len(scores) > 1 else 0.0,
            "would_watch_pct": round(100 * sum(r["would_watch"] for r in rows) / len(rows), 1),
            "reaction": (verdicts.get(cid) or {}).get("one_line_reaction", ""),
        })
    cohort_rows.sort(key=lambda c: -c["mean_score"])

    # Qualitative themes, weighted by how many people each cohort represents.
    def tally(field: str) -> list[dict]:
        counts: dict[str, int] = {}
        for cid, verdict in verdicts.items():
            weight = cohort_by_id.get(cid, {}).get("size", 0)
            for item in (verdict.get(field) or [])[:6]:
                if isinstance(item, str) and item.strip():
                    counts[item.strip()] = counts.get(item.strip(), 0) + weight
        return [
            {"point": k, "viewers": v, "share_pct": round(100 * v / max(1, n), 1)}
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:6]
        ]

    report = {
        "panel_size": n,
        "overall_score": round(statistics.fmean(overall_scores), 2),
        "median_score": round(statistics.median(overall_scores), 2),
        "score_spread": round(statistics.pstdev(overall_scores), 2),
        "would_watch_pct": round(100 * sum(r["would_watch"] for r in responses) / n, 1),
        "would_recommend_pct": round(100 * sum(r["would_recommend"] for r in responses) / n, 1),
        "would_finish_pct": round(100 * sum(r["would_finish"] for r in responses) / n, 1),
        "sentiment_split": {
            s: round(100 * sum(1 for r in responses if r["sentiment"] == s) / n, 1)
            for s in ("positive", "mixed", "negative")
        },
        "rating_histogram": histogram,
        "dimension_means": dimension_means,
        "dimension_spread": dimension_spread,
        "segments": {
            "age_group": _segment(responses, personas_by_id, "age_group", dimension="age_group"),
            "market": _segment(responses, personas_by_id, "market_name", dimension="market_name"),
            "genre_affinity": _segment(responses, personas_by_id, None,
                                       lambda p: "Genre enthusiasts" if p["matches_film_genre"] else "Outside the genre",
                                       dimension="genre_affinity"),
            "viewing_frequency": _segment(responses, personas_by_id, "viewing_frequency", dimension="viewing_frequency"),
            "taste_profile": _segment(responses, personas_by_id, "taste_profile", dimension="taste_profile"),
            "pacing_tolerance": _segment(responses, personas_by_id, "pacing_tolerance", dimension="pacing_tolerance"),
            "viewing_context": _segment(responses, personas_by_id, "viewing_context", dimension="viewing_context"),
        },
        "cohorts": cohort_rows,
        "strongest_segments": [],
        "weakest_segments": [],
        "liked": tally("liked"),
        "disliked": tally("disliked"),
        "polarizing": tally("polarizing_within_cohort"),
        "most_divisive_dimensions": sorted(
            [{"dimension": d, "spread": s, "mean": dimension_means[d]} for d, s in dimension_spread.items()],
            key=lambda x: -x["spread"],
        )[:3],
    }

    # Strongest / weakest are read off the computed segments, never invented.
    ranked = [s for group in report["segments"].values() for s in group if s["n"] >= max(8, n * 0.02)]
    ranked.sort(key=lambda s: -s["mean_score"])
    report["strongest_segments"] = ranked[:3]
    report["weakest_segments"] = list(reversed(ranked[-3:]))

    log_event(state, broadcast("agent_aggregation", "simulation_verdict_update", {
        "panel_size": n,
        "overall_score": report["overall_score"],
        "would_watch_pct": report["would_watch_pct"],
        "strongest": report["strongest_segments"][0]["segment"] if report["strongest_segments"] else None,
        "weakest": report["weakest_segments"][0]["segment"] if report["weakest_segments"] else None,
    }))
    return report


# ---------------------------------------------------------------- stage 6 --


def cultural_scan(
    state: GlobalState, analysis: dict, markets: list[str], trace: list
) -> dict:
    """Per-market risk review. Web-grounded only when Tavily is configured."""
    if not markets:
        return {"markets": [], "research_enabled": tavily_client.enabled(), "sources": []}

    market_names = [panel_lib.MARKETS.get(m, {}).get("name", m) for m in markets]
    request = log_event(state, make_envelope(
        "agent_localization", "agent_pr_risk", "verify_regional_compliance",
        {"markets": markets, "research_enabled": tavily_client.enabled()},
    ))

    research: list[dict] = []
    if tavily_client.enabled():
        genre_hint = " ".join(analysis.get("genre", [])[:2])
        found = gemini_client.map_concurrent(
            market_names, lambda name: tavily_client.research_market(name, genre_hint), max_workers=3
        )
        for name, result in zip(market_names, found):
            if isinstance(result, Exception) or not result.get("results"):
                continue
            research.append({"market": name, "results": result["results"]})

    research_block = (
        f"\n\nRESEARCH NOTES (externally fetched, cite these for `researched` findings):\n"
        f"{json.dumps(research, ensure_ascii=False)[:8000]}"
        if research else
        "\n\nNo external research was available. Every finding must be marked "
        "basis=\"ai_interpretation\"."
    )

    prompt = (
        "MATERIAL ANALYSIS:\n"
        f"{json.dumps({k: analysis.get(k) for k in ('genre', 'logline', 'themes', 'content_flags', 'potentially_polarizing', 'main_characters')}, ensure_ascii=False)}\n\n"
        f"TARGET MARKETS: {market_names}"
        f"{research_block}"
    )
    payload, meta = gemini_client.generate_json_traced(
        prompt, tier="pro", system=P.SENSITIVITY_SYSTEM, mock=P.MOCK_SENSITIVITY
    )
    trace.append({"stage": "cultural_scan", **meta, "research_enabled": tavily_client.enabled()})

    findings = payload.get("markets", []) if isinstance(payload, dict) else []
    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for market in findings:
        for finding in market.get("findings", []):
            counts[finding.get("severity", "LOW")] = counts.get(finding.get("severity", "LOW"), 0) + 1

    log_event(state, make_reply(request, "agent_pr_risk", "compliance_result", {
        "markets_reviewed": len(findings), "severity_counts": counts,
        "research_enabled": tavily_client.enabled(),
    }))
    return {
        "markets": findings,
        "severity_counts": counts,
        "research_enabled": tavily_client.enabled(),
        "sources": [
            {"market": r["market"], "url": item["url"], "title": item["title"]}
            for r in research for item in r["results"]
        ],
    }


# ---------------------------------------------------------------- stage 7 --


def pr_recommendations(state: GlobalState, report: dict, sensitivity: dict, trace: list) -> dict:
    request = log_event(state, make_envelope(
        "agent_aggregation", "agent_campaign_strategist", "request_audience_insights",
        {"panel_size": report["panel_size"], "overall_score": report["overall_score"]},
    ))
    prompt = (
        "SIMULATED PANEL RESULTS:\n"
        f"{json.dumps({k: report[k] for k in ('panel_size', 'overall_score', 'would_watch_pct', 'would_recommend_pct', 'sentiment_split', 'dimension_means', 'strongest_segments', 'weakest_segments', 'liked', 'disliked', 'polarizing', 'most_divisive_dimensions')}, ensure_ascii=False)}\n\n"
        "MARKET RISK FINDINGS:\n"
        f"{json.dumps(sensitivity.get('markets', []), ensure_ascii=False)[:6000]}"
    )
    payload, meta = gemini_client.generate_json_traced(
        prompt, tier="pro", system=P.PR_SYSTEM, mock=P.MOCK_PR
    )
    trace.append({"stage": "pr_recommendations", **meta})
    log_event(state, make_reply(request, "agent_campaign_strategist", "campaign_plan_ready", {
        "positioning": payload.get("positioning", "")[:120], "source": meta.get("source"),
    }))
    return payload


# ------------------------------------------------------------ orchestration --


def run_simulation(
    state: GlobalState,
    material: str,
    *,
    panel_size: int = 500,
    seed: int = 20260902,
    markets: Optional[list[str]] = None,
    distribution: Optional[dict] = None,
    on_stage: Optional[Callable[[str, str, dict], None]] = None,
) -> dict:
    """Run every stage and return the finished simulation payload.

    `on_stage(stage_name, status, detail)` is called as each stage starts and
    finishes so the dashboard can show real progress, not a fake spinner.
    """
    trace: list[dict] = []
    markets = markets or []

    def stage(name: str, status: str, **detail):
        if on_stage:
            on_stage(name, status, detail)

    stage("analyse_material", "running")
    analysis = analyse_material(state, material, trace)
    stage("analyse_material", "complete",
          genres=analysis.get("genre", []),
          completeness=(analysis.get("material_quality") or {}).get("completeness"))

    stage("build_panel", "running")
    panel, resolved_dist = panel_lib.build_panel(
        size=panel_size, seed=seed, distribution=distribution,
        film_genres=analysis.get("genre", []),
    )
    cohorts = panel_lib.build_cohorts(panel)
    stage("build_panel", "complete", personas=len(panel), cohorts=len(cohorts))

    stage("simulate_cohorts", "running", cohorts=len(cohorts))
    verdicts = simulate_cohorts(state, analysis, cohorts, trace)
    stage("simulate_cohorts", "complete", cohorts_scored=len(verdicts))

    dimensions = [d for d in analysis.get("evaluable_dimensions", []) if d in DIMENSION_WEIGHTS]
    if not dimensions:
        dimensions = ["story", "characters", "pacing", "entertainment"]

    stage("derive_individuals", "running")
    responses = _derive_individuals(panel, cohorts, verdicts, dimensions, analysis, seed)
    stage("derive_individuals", "complete", responses=len(responses))

    stage("aggregate", "running")
    report = aggregate(state, panel, cohorts, verdicts, responses, dimensions)
    stage("aggregate", "complete", overall_score=report["overall_score"])

    stage("cultural_scan", "running", markets=len(markets))
    sensitivity = cultural_scan(state, analysis, markets, trace)
    stage("cultural_scan", "complete", findings=sensitivity.get("severity_counts", {}))

    stage("pr_recommendations", "running")
    recommendations = pr_recommendations(state, report, sensitivity, trace)
    stage("pr_recommendations", "complete")

    live_stages = sum(1 for t in trace if t.get("source") == "gemini")
    return {
        "analysis": analysis,
        "report": report,
        "sensitivity": sensitivity,
        "recommendations": recommendations,
        "dimensions": dimensions,
        "cohorts": cohorts,
        "panel": panel,
        "responses": responses,
        "distribution": resolved_dist,
        "distribution_fingerprint": panel_lib.distribution_fingerprint(resolved_dist),
        "provenance": {
            "trace": trace,
            "live_llm_stages": live_stages,
            "total_llm_stages": len(trace),
            "mode": "live" if live_stages == len(trace) and trace else ("mixed" if live_stages else "mock"),
            "models_used": sorted({t.get("model") for t in trace if t.get("model")}),
            "research_enabled": sensitivity.get("research_enabled", False),
        },
    }
