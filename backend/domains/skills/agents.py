"""SKILL.md-driven advisor agents (see skills/README.md and AGENT.md Section 8).

Each runner gathers facts from GlobalState, runs the prerequisite phase agents
when the state is empty, then makes one synthesis call to Gemini with the
SKILL.md body as the system instruction and the facts as the prompt. With no
GEMINI_API_KEY the same facts feed a deterministic offline fallback, so every
skill completes without credentials and the run record says which path
produced the answer.

Every runner returns the envelope the AI Advisors page renders:
  summary, highlights[], findings[{title, detail, severity, ref}],
  next_actions[], confidence, data{}
"""
import json
from datetime import date
from typing import Any, Callable

from core import config
from core.audience import personas as panel_lib
from core.messaging.envelope import broadcast, log_event
from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from core.skills.registry import Skill
from domains.launch.agents import audience_sim
from services import gemini_client, mock_db, tavily_client

StageFn = Callable[..., None]  # stage(key, status, **detail)

SEVERITIES = ("LOW", "MEDIUM", "HIGH")
CONFIDENCE = ("low", "medium", "high")
MAX_PROMPT_CHARS = 24_000


class SkillInputError(ValueError):
    """The production is missing something the skill needs. Reported on the
    run record as a plain message rather than a traceback."""


# Stage checklist per skill, in execution order. The UI renders these.
STAGES: dict[str, list[tuple[str, str]]] = {
    "casting": [
        ("gather", "Gathered the candidate pool"),
        ("phases", "Ran the pre-casting and audition agents"),
        ("advise", "Wrote the casting recommendation"),
    ],
    "scheduling": [
        ("gather", "Read the stripboard and budget"),
        ("phases", "Ran the breakdown and scheduling agents"),
        ("advise", "Wrote the schedule review"),
    ],
    "audience-simulation": [
        ("material", "Loaded the screenplay"),
        ("analyse_material", "Analysed the material"),
        ("build_panel", "Generated the synthetic panel"),
        ("simulate_cohorts", "Simulated cohort responses"),
        ("derive_individuals", "Derived individual responses"),
        ("aggregate", "Aggregated the segments"),
        ("cultural_scan", "Market scan (left to the cultural-research skill)"),
        ("pr_recommendations", "Drafted strategist notes"),
        ("advise", "Wrote the audience brief"),
    ],
    "cultural-research": [
        ("material", "Loaded the screenplay"),
        ("analyse_material", "Analysed the material"),
        ("research", "Researched the markets and assessed sensitivities"),
        ("advise", "Wrote the localisation brief"),
    ],
}


def input_schema(skill: Skill) -> list[dict]:
    """The controls the dashboard shows before running a skill. Defaults come
    from the SKILL.md metadata; the router validates what comes back."""
    if skill.name == "audience-simulation":
        return [
            {"key": "panel_size", "label": "Panel size", "type": "number", "min": 20, "max": 1000,
             "default": skill.meta_int("panel_size", 200),
             "help": "Synthetic viewers to simulate. A bigger panel does not add model calls."},
            {"key": "seed", "label": "Seed (optional)", "type": "number", "min": 0, "max": 2**31 - 1,
             "default": None, "help": "Reuse a seed to reproduce the same panel."},
        ]
    if skill.name == "cultural-research":
        return [
            {"key": "markets", "label": "Release markets", "type": "multiselect", "min_selected": 1,
             "options": [{"value": code, "label": m["name"]} for code, m in panel_lib.MARKETS.items()],
             "default": [c for c in skill.meta_list("markets") if c in panel_lib.MARKETS],
             "help": ("Web research is on." if tavily_client.enabled() else
                      "Web research is off (no Tavily key), so findings are marked as AI interpretation.")},
        ]
    return []


# ------------------------------------------------------------------ shared --


def _clip(text: str, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _coerce_result(payload: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """Accept whatever the model returned, but never hand the UI a malformed
    envelope: every missing or broken field comes from the offline fallback."""
    if not isinstance(payload, dict):
        return fallback
    out = dict(fallback)
    for key in ("summary", "confidence"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    for key in ("highlights", "next_actions"):
        value = payload.get(key)
        if isinstance(value, list):
            out[key] = [str(v).strip() for v in value if str(v).strip()][:8]
    if isinstance(payload.get("findings"), list):
        findings = []
        for item in payload["findings"]:
            if not isinstance(item, dict):
                continue
            severity = str(item.get("severity", "LOW")).upper()
            findings.append({
                "title": _clip(item.get("title", ""), 120),
                "detail": _clip(item.get("detail", ""), 600),
                "severity": severity if severity in SEVERITIES else "LOW",
                "ref": _clip(item.get("ref", ""), 60),
            })
        out["findings"] = findings[:12]
    if isinstance(payload.get("data"), dict):
        out["data"] = {**(fallback.get("data") or {}), **payload["data"]}
    if out.get("confidence") not in CONFIDENCE:
        out["confidence"] = fallback.get("confidence", "medium")
    return out


def _synthesise(skill: Skill, facts: dict, fallback: dict, trace: list, stage: StageFn) -> dict:
    """The one LLM step every skill shares: SKILL.md body as system prompt,
    facts as the user prompt, JSON back. Offline, the fallback is the answer."""
    prompt = (
        f"Production {facts.get('project_id', '')}. Facts for this run as JSON; use only these.\n\n"
        + json.dumps(facts, ensure_ascii=False, default=str)[:MAX_PROMPT_CHARS]
    )
    stage("advise", "running", model=skill.model)
    payload, meta = gemini_client.generate_json_traced(
        prompt, tier=skill.model, system=skill.instructions, mock=fallback
    )
    trace.append({"stage": "advise", **meta})
    result = _coerce_result(payload, fallback)
    stage("advise", "complete", source=meta.get("source"), model=meta.get("model") or "offline")
    return result


def _material(state: GlobalState) -> tuple[str, str]:
    """What the screenplay-reading skills analyse: the uploaded script, else a
    brief rendered from the project's script context (same order the audience
    router uses)."""
    context = state.script_context or {}
    raw = (context.get("raw_text") or "").strip()
    if raw:
        return raw, context.get("source_filename") or "uploaded script"
    if context:
        script = mock_db.load("script") if context.get("title") else {}
        lines = [
            f"TITLE: {context.get('title', state.project_id)}",
            f"GENRE: {context.get('genre', '')}",
            f"TONE: {context.get('tone', '')}",
            f"LOGLINE: {context.get('logline', '')}",
        ]
        roles = script.get("roles", [])
        if roles:
            lines.append("CHARACTERS:")
            lines += [f"  - {r['name']} ({r['type']}): {r['description']}" for r in roles]
        scenes = script.get("scenes", [])
        if scenes:
            lines.append("SCENES:")
            lines += [
                f"  - {s['scene_id']} {s.get('int_ext', '')} {s.get('location_type', '')} "
                f"[{', '.join(s.get('tags', []))}]"
                for s in scenes
            ]
        return "\n".join(lines), f"{context.get('title', state.project_id)} project brief"
    raise SkillInputError(
        "No material to analyse. Drop a screenplay on Script Intake, or run the "
        "pipeline once so the project has a script context."
    )


# ----------------------------------------------------------------- casting --


def _weakest(scores: dict) -> tuple[Any, Any]:
    dims = {k: v for k, v in (scores or {}).items()
            if k in ("audition", "hype", "pr", "budget") and isinstance(v, (int, float))}
    if not dims:
        return None, None
    key = min(dims, key=dims.get)
    return key, dims[key]


def _casting_facts(state: GlobalState) -> dict:
    role_cap = round(state.budget_state.cap * config.CASTING_CAP_SHARE, 2)
    roles = state.role_requirements or {}
    by_role: dict[str, list] = {}
    for c in state.candidates:
        by_role.setdefault(c.role_id or "UNASSIGNED", []).append(c)
    order = list(roles) + [r for r in by_role if r not in roles]
    computed = []
    for role_id in order:
        pool = sorted(by_role.get(role_id, []), key=lambda c: c.scores.get("composite", -1), reverse=True)
        req = roles.get(role_id) if isinstance(roles.get(role_id), dict) else {}
        computed.append({
            "role_id": role_id,
            "role_name": req.get("name", role_id),
            "ranked": [
                {"candidate_id": c.id, "name": c.name, "status": c.status,
                 "composite": c.scores.get("composite"), "scores": c.scores,
                 "quote_usd": c.metadata.get("quote_usd")}
                for c in pool if c.status != "DISQUALIFIED"
            ],
            "disqualified": [
                {"candidate_id": c.id, "name": c.name, "reason": c.disqualify_reason or "disqualified"}
                for c in pool if c.status == "DISQUALIFIED"
            ],
        })
    context = state.script_context or {}
    return {
        "project_id": state.project_id,
        "production": {k: context.get(k) for k in ("title", "genre", "tone", "demographic_targets")
                       if context.get(k) is not None},
        "roles": [{"role_id": rid, **(req if isinstance(req, dict) else {"description": str(req)})}
                  for rid, req in roles.items()],
        "scoring_weights": state.scoring_weights,
        "candidates": [
            {"id": c.id, "name": c.name, "role_id": c.role_id, "status": c.status, "scores": c.scores,
             "disqualify_reason": c.disqualify_reason, "quote_usd": c.metadata.get("quote_usd"),
             "followers": c.metadata.get("followers"),
             "review": _clip(c.metadata.get("qualitative_review", ""), 200)}
            for c in state.candidates
        ],
        "budget": {"cap_usd": state.budget_state.cap, "role_cap_usd": role_cap},
        "computed": computed,
    }


def _casting_fallback(facts: dict) -> dict:
    cap = facts["budget"]["cap_usd"]
    role_cap = facts["budget"]["role_cap_usd"]
    roles_out, findings, actions, highlights = [], [], [], []
    total_quotes, picks = 0.0, 0
    for role in facts["computed"]:
        ranked, name = role["ranked"], role["role_name"]
        pick = None
        if ranked:
            top = ranked[0]
            picks += 1
            quote = float(top.get("quote_usd") or 0)
            total_quotes += quote
            dim, val = _weakest(top.get("scores") or {})
            pick = {
                "candidate_id": top["candidate_id"], "name": top["name"], "composite": top.get("composite"),
                "rationale": f"Highest composite for {name} at {top.get('composite')} under the current weights.",
                "watch": f"Lowest score is {dim} at {val}." if dim else "Not fully scored.",
            }
            highlights.append(f"{name}: {top['name']} leads on composite {top.get('composite')}.")
            if len(ranked) > 1 and (top.get("composite") or 0) - (ranked[1].get("composite") or 0) <= 5:
                findings.append({
                    "title": f"Close call for {name}",
                    "detail": f"{top['name']} and {ranked[1]['name']} are within 5 composite points; "
                              f"a producer should decide on {dim or 'the role brief'}.",
                    "severity": "MEDIUM", "ref": role["role_id"],
                })
            if quote > role_cap:
                findings.append({
                    "title": "Quote over the per-role cap",
                    "detail": f"{top['name']} quotes ${quote:,.0f} against a ${role_cap:,.0f} cap.",
                    "severity": "HIGH", "ref": top["candidate_id"],
                })
            elif dim == "pr" and (val or 0) < 60:
                findings.append({
                    "title": f"PR exposure on {top['name']}",
                    "detail": f"PR score {val} is below the 60 comfort line; brief the PR shield before announcing.",
                    "severity": "MEDIUM", "ref": top["candidate_id"],
                })
            actions.append(f"Confirm {top['name']} for {name} (composite {top.get('composite')}).")
        else:
            findings.append({
                "title": f"No viable candidate for {name}",
                "detail": "Every candidate for this role was disqualified, or none was sourced.",
                "severity": "HIGH", "ref": role["role_id"],
            })
            actions.append(f"Reopen sourcing for {name}.")
        roles_out.append({
            "role_id": role["role_id"], "role_name": name, "recommended": pick,
            "runners_up": [{"candidate_id": r["candidate_id"], "name": r["name"], "composite": r.get("composite")}
                           for r in ranked[1:3]],
            "disqualified": role["disqualified"],
        })
    n_roles = len(facts["computed"])
    n_cands = len(facts["candidates"])
    n_dq = sum(1 for c in facts["candidates"] if c["status"] == "DISQUALIFIED")
    high = any(f["severity"] == "HIGH" for f in findings)
    strong = picks and all(((r["recommended"] or {}).get("composite") or 0) > 70 for r in roles_out)
    return {
        "summary": (f"{picks} of {n_roles} roles have a recommended pick from {n_cands} candidates "
                    f"({n_dq} disqualified). Recommended quotes total ${total_quotes:,.0f} "
                    f"against a ${cap:,.0f} budget."),
        "highlights": highlights[:6],
        "findings": findings,
        "next_actions": actions[:6],
        "confidence": "low" if high or not picks else ("high" if strong else "medium"),
        "data": {
            "roles": roles_out,
            "budget": {"cap_usd": cap, "role_cap_usd": role_cap,
                       "recommended_quotes_usd": round(total_quotes, 2),
                       "within_cap": total_quotes <= cap and not high},
        },
    }


def prepare_casting(skill: Skill, state: GlobalState, params: dict, stage: StageFn) -> bool:
    """Seed the pool through Phases I-II when it is empty. Returns True when
    the state changed and must be persisted before the slow advisory step."""
    stage("gather", "running")
    if state.candidates:
        stage("gather", "complete", candidates=len(state.candidates), roles=len(state.role_requirements))
        stage("phases", "complete", skipped="pool already scored")
        return False
    stage("gather", "complete", candidates=0)
    stage("phases", "running")
    Orchestrator().run(state, start="phase1", end="phase2")
    stage("phases", "complete", candidates=len(state.candidates), events=len(state.event_log))
    return True


def run_casting(skill: Skill, state: GlobalState, params: dict, stage: StageFn, trace: list) -> dict:
    facts = _casting_facts(state)
    return _synthesise(skill, facts, _casting_fallback(facts), trace, stage)


# -------------------------------------------------------------- scheduling --


def _longest_streak(dates: list[str]) -> tuple[int, str, str]:
    """Longest run of consecutive calendar days in a sorted ISO-date list."""
    best = (0, "", "")
    run_start, run_len, previous = None, 0, None
    for iso in dates:
        try:
            current = date.fromisoformat(iso)
        except ValueError:
            continue
        if previous is not None and (current - previous).days == 1:
            run_len += 1
        else:
            run_start, run_len = iso, 1
        if run_len > best[0]:
            best = (run_len, run_start, iso)
        previous = current
    return best


def _scheduling_facts(state: GlobalState) -> dict:
    sched = state.schedule
    settings = sched.shoot_settings or {}
    constraints = sched.director_constraints or {}
    max_h = float(settings.get("max_hours_per_day", 10))
    min_h = float(settings.get("min_hours_per_day", 6))
    entries = [e.model_dump() for e in sched.stripboard]

    days: dict[str, dict] = {}
    for e in entries:
        d = days.setdefault(e["date"], {"date": e["date"], "scenes": [], "hours": 0.0, "venues": [], "cost_usd": 0.0})
        d["scenes"].append(e["scene_id"])
        d["hours"] += float(e.get("estimated_time_hours") or 0)
        if e["venue"] not in d["venues"]:
            d["venues"].append(e["venue"])
        d["cost_usd"] += float(e.get("cost_per_day") or 0)
    day_load = []
    for d in sorted(days.values(), key=lambda x: x["date"]):
        d["hours"] = round(d["hours"], 1)
        d["cost_usd"] = round(d["cost_usd"], 2)
        d["status"] = "OVER" if d["hours"] > max_h else ("UNDER" if d["hours"] < min_h else "OK")
        day_load.append(d)

    character_days: dict[str, list[str]] = {}
    for e in entries:
        for ch in e.get("characters_needed") or []:
            bucket = character_days.setdefault(ch, [])
            if e["date"] not in bucket:
                bucket.append(e["date"])
    for bucket in character_days.values():
        bucket.sort()

    shoot_days = len(day_load)
    cap = state.budget_state.cap
    allowance = round(cap * config.LOCATIONS_SHARE / max(shoot_days, 1), 2)
    return {
        "project_id": state.project_id,
        "stripboard": entries,
        "conflicts": sched.conflicts,
        "settings": {"start_date": settings.get("start_date"), "min_hours_per_day": min_h,
                     "max_hours_per_day": max_h, "country": constraints.get("country"),
                     "excluded_states": constraints.get("excluded_states", [])},
        "budget": {"cap_usd": cap, "daily_burn_usd": state.budget_state.daily_burn,
                   "allowance_per_day_usd": allowance, "alerts": state.budget_state.alerts},
        "computed": {
            "shoot_days": shoot_days,
            "total_hours": round(sum(d["hours"] for d in day_load), 1),
            "day_load": day_load,
            "character_days": character_days,
            "costliest_days": sorted(day_load, key=lambda d: d["cost_usd"], reverse=True)[:2],
        },
    }


def _scheduling_fallback(facts: dict) -> dict:
    computed, budget, settings = facts["computed"], facts["budget"], facts["settings"]
    findings, highlights, actions, moves = [], [], [], []
    for d in computed["day_load"]:
        if d["status"] == "OVER":
            findings.append({"title": "Day over the hours cap",
                             "detail": f"{d['hours']}h scheduled against a {settings['max_hours_per_day']}h day "
                                       f"across {', '.join(d['scenes'])}.",
                             "severity": "HIGH", "ref": d["date"]})
        elif d["status"] == "UNDER":
            findings.append({"title": "Underused day",
                             "detail": f"Only {d['hours']}h scheduled; the minimum day is {settings['min_hours_per_day']}h.",
                             "severity": "LOW", "ref": d["date"]})
        if len(d["venues"]) > 1:
            findings.append({"title": "Company move within a day",
                             "detail": f"{len(d['venues'])} venues on one day: {', '.join(d['venues'])}.",
                             "severity": "MEDIUM", "ref": d["date"]})
    for character, dates in computed["character_days"].items():
        streak, start, end = _longest_streak(dates)
        if streak > 5:
            findings.append({"title": f"{character} on set {streak} days straight",
                             "detail": f"Consecutive days from {start} to {end}; plan a rest day.",
                             "severity": "LOW", "ref": f"{start}..{end}"})
    within = budget["daily_burn_usd"] <= budget["allowance_per_day_usd"]
    if within:
        highlights.append(f"Daily burn ${budget['daily_burn_usd']:,.0f} sits inside the "
                          f"${budget['allowance_per_day_usd']:,.0f}/day location allowance.")
    else:
        findings.append({"title": "Daily burn above the location allowance",
                         "detail": f"${budget['daily_burn_usd']:,.0f}/day against a "
                                   f"${budget['allowance_per_day_usd']:,.0f}/day allowance.",
                         "severity": "HIGH", "ref": "budget"})
    for d in computed["costliest_days"]:
        highlights.append(f"{d['date']} is the costliest day at ${d['cost_usd']:,.0f} ({', '.join(d['venues'])}).")
    for conflict in facts["conflicts"][:4]:
        highlights.append(f"{conflict.get('scene_id')} moved from {conflict.get('wanted')} to "
                          f"{conflict.get('moved_to')}: {conflict.get('resolution')}.")

    spare = [d for d in computed["day_load"] if d["status"] != "OVER"]
    for d in [d for d in computed["day_load"] if d["status"] == "OVER"]:
        scenes = [e for e in facts["stripboard"] if e["date"] == d["date"]]
        if not scenes or not spare:
            break
        scene = min(scenes, key=lambda e: e["estimated_time_hours"])
        target = min(spare, key=lambda x: x["hours"])
        if target["hours"] + scene["estimated_time_hours"] <= settings["max_hours_per_day"]:
            moves.append({"scene_id": scene["scene_id"], "from": d["date"], "to": target["date"],
                          "why": f"Brings {d['date']} under {settings['max_hours_per_day']}h; {target['date']} has room."})
            actions.append(f"Move {scene['scene_id']} from {d['date']} to {target['date']} if {scene['venue']} is free.")
    if not actions:
        actions.append("Lock the schedule and circulate the stripboard to department heads.")

    over = sum(1 for d in computed["day_load"] if d["status"] == "OVER")
    high = any(f["severity"] == "HIGH" for f in findings)
    return {
        "summary": (f"{len(facts['stripboard'])} scenes over {computed['shoot_days']} shoot days "
                    f"({computed['total_hours']}h). {over} day(s) over the hours cap; "
                    f"{len(facts['conflicts'])} venue conflict(s) resolved by negotiation."),
        "highlights": highlights[:6],
        "findings": findings,
        "next_actions": actions[:6],
        "confidence": "medium" if high else "high",
        "data": {
            "shoot_days": computed["shoot_days"],
            "total_hours": computed["total_hours"],
            "day_load": [{k: d[k] for k in ("date", "scenes", "hours", "venues", "status")} for d in computed["day_load"]],
            "cost": {"daily_burn_usd": budget["daily_burn_usd"],
                     "allowance_per_day_usd": budget["allowance_per_day_usd"],
                     "within_allowance": within},
            "proposed_moves": moves,
        },
    }


def prepare_scheduling(skill: Skill, state: GlobalState, params: dict, stage: StageFn) -> bool:
    """Build the stripboard through Phase III when it is empty."""
    stage("gather", "running")
    if state.schedule.stripboard:
        stage("gather", "complete", scenes=len(state.schedule.stripboard))
        stage("phases", "complete", skipped="stripboard already built")
        return False
    stage("gather", "complete", scenes=0)
    stage("phases", "running")
    Orchestrator().run(state, start="phase3", end="phase3")
    stage("phases", "complete", scenes=len(state.schedule.stripboard), events=len(state.event_log))
    return True


def run_scheduling(skill: Skill, state: GlobalState, params: dict, stage: StageFn, trace: list) -> dict:
    facts = _scheduling_facts(state)
    return _synthesise(skill, facts, _scheduling_fallback(facts), trace, stage)


# --------------------------------------------------------------- audience --


def _segments(rows: list[dict]) -> list[dict]:
    return [{"segment": r.get("segment"), "score": r.get("mean_score"), "n": r.get("n")} for r in rows or []]


def _audience_facts(state: GlobalState, result: dict) -> dict:
    report, analysis = result["report"], result["analysis"]
    keep = ("panel_size", "overall_score", "median_score", "would_watch_pct", "would_recommend_pct",
            "would_finish_pct", "sentiment_split", "dimension_means", "liked", "disliked", "polarizing",
            "most_divisive_dimensions")
    return {
        "project_id": state.project_id,
        "analysis": {k: analysis.get(k) for k in ("genre", "logline", "themes", "content_flags",
                                                  "potentially_polarizing", "material_quality",
                                                  "evaluable_dimensions")},
        "report": {**{k: report.get(k) for k in keep},
                   "strongest_segments": _segments(report.get("strongest_segments")),
                   "weakest_segments": _segments(report.get("weakest_segments"))},
        "recommendations": result.get("recommendations"),
        "provenance": {"mode": result["provenance"]["mode"], "models_used": result["provenance"]["models_used"]},
    }


def _audience_fallback(facts: dict) -> dict:
    report, analysis = facts["report"], facts["analysis"] or {}
    means = report.get("dimension_means") or {}
    findings, highlights = [], []
    if means:
        low, high = min(means, key=means.get), max(means, key=means.get)
        severity = "HIGH" if means[low] < 5 else ("MEDIUM" if means[low] < 6.5 else "LOW")
        disliked = ((report.get("disliked") or [{}])[0]).get("point", "")
        liked = ((report.get("liked") or [{}])[0]).get("point", "")
        findings.append({"title": f"Weakest dimension: {low}",
                         "detail": f"Mean {means[low]}/10 in the simulated panel"
                                   + (f"; most cited dislike: {disliked}." if disliked else "."),
                         "severity": severity, "ref": low})
        highlights.append(f"Strongest dimension is {high} at {means[high]}/10"
                          + (f"; most cited like: {liked}." if liked else "."))
    for seg in (report.get("strongest_segments") or [])[:2]:
        highlights.append(f"Responds best: {seg['segment']} ({seg['score']}/10).")
    for seg in (report.get("weakest_segments") or [])[:2]:
        findings.append({"title": f"Soft segment: {seg['segment']}",
                         "detail": f"Mean {seg['score']}/10 versus {report.get('overall_score')} overall.",
                         "severity": "MEDIUM" if (seg.get("score") or 0) < 6 else "LOW",
                         "ref": str(seg["segment"])})
    polarizing = [p.get("point") for p in (report.get("polarizing") or [])[:4] if p.get("point")]
    questions = ["Which moment made you want to stop watching?",
                 "How would you describe the pacing of the first act?"]
    questions += [f"How did you react to: {p}?" for p in polarizing[:2]]
    completeness = (analysis.get("material_quality") or {}).get("completeness") or ""
    thin = completeness in ("logline", "synopsis")
    mode = facts["provenance"]["mode"]
    summary = (f"The simulated panel of {report.get('panel_size')} synthetic viewers scored the material "
               f"{report.get('overall_score')}/10; {report.get('would_watch_pct')}% would watch and "
               f"{report.get('would_recommend_pct')}% would recommend.")
    if thin:
        summary += " The read is thin because only a logline or synopsis was available."
    if mode != "live":
        summary += " These numbers come from the offline fallback, not a live model."
    return {
        "summary": summary,
        "highlights": highlights[:6],
        "findings": findings[:8],
        "next_actions": ["Take the weakest-dimension finding into the next director notes session.",
                         "Put the test-screening questions in front of a real audience before locking picture."],
        "confidence": "low" if thin or mode != "live" else "medium",
        "data": {
            "panel_size": report.get("panel_size"),
            "overall_score": report.get("overall_score"),
            "would_watch_pct": report.get("would_watch_pct"),
            "would_recommend_pct": report.get("would_recommend_pct"),
            "strongest_segments": [{"segment": s["segment"], "score": s["score"]}
                                   for s in (report.get("strongest_segments") or [])[:3]],
            "weakest_segments": [{"segment": s["segment"], "score": s["score"]}
                                 for s in (report.get("weakest_segments") or [])[:3]],
            "dimension_means": means,
            "polarizing": polarizing,
            "test_screening_questions": questions,
        },
    }


def run_audience(skill: Skill, state: GlobalState, params: dict, stage: StageFn, trace: list) -> dict:
    stage("material", "running")
    material, label = _material(state)
    stage("material", "complete", source=label, chars=len(material))
    panel_size = max(20, min(1000, int(params.get("panel_size") or skill.meta_int("panel_size", 200))))
    seed = int(params.get("seed") or 20260903)
    # The Phase V staged simulator does the screening; the market scan is the
    # cultural-research skill's job, so no markets are passed here.
    result = audience_sim.run_simulation(
        state, material, panel_size=panel_size, seed=seed, markets=[],
        on_stage=lambda name, status, detail: stage(name, status, **(detail or {})),
    )
    trace.extend(result["provenance"]["trace"])
    facts = _audience_facts(state, result)
    return _synthesise(skill, facts, _audience_fallback(facts), trace, stage)


# ------------------------------------------------------- cultural research --


def _cultural_facts(state: GlobalState, analysis: dict, codes: list[str], sensitivity: dict) -> dict:
    return {
        "project_id": state.project_id,
        "analysis": {k: analysis.get(k) for k in ("genre", "logline", "themes", "content_flags",
                                                  "potentially_polarizing", "main_characters")},
        "markets": [{"code": c, "name": panel_lib.MARKETS[c]["name"]} for c in codes],
        "sensitivity": sensitivity.get("markets", []),
        "sources": sensitivity.get("sources", []),
        "research_enabled": bool(sensitivity.get("research_enabled", False)),
        "severity_counts": sensitivity.get("severity_counts", {}),
        "compliance_state": state.compliance_state,
    }


def _cultural_fallback(facts: dict) -> dict:
    rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    by_market: dict[str, list] = {}
    for market in facts["sensitivity"]:
        if isinstance(market, dict):
            by_market[str(market.get("market", ""))] = market.get("findings", []) or []
    markets_out, findings, actions = [], [], []
    for m in facts["markets"]:
        rows = by_market.get(m["code"]) or by_market.get(m["name"]) or []
        rows = sorted(rows, key=lambda f: rank.get(str(f.get("severity", "LOW")).upper(), 1), reverse=True)
        researched = sum(1 for f in rows if f.get("basis") == "researched")
        top = rows[0] if rows else None
        risk = str(top.get("severity", "LOW")).upper() if top else "NONE"
        risk = risk if risk in SEVERITIES else "NONE"
        remediation = {"HIGH": ["certification consultation", "alternate audio or cut"],
                       "MEDIUM": ["alternate edit for broadcast", "subtitle note"],
                       "LOW": ["note for the local marketing team"]}.get(risk, [])
        markets_out.append({
            "market": m["code"], "name": m["name"], "risk": risk,
            "researched_findings": researched, "interpreted_findings": len(rows) - researched,
            "top_finding": top.get("content_detected", "") if top else "no notable concern from this material",
            "remediation": remediation,
        })
        for f in rows[:3]:
            severity = str(f.get("severity", "LOW")).upper()
            findings.append({
                "title": f"{m['code']}: {_clip(f.get('content_detected', 'finding'), 60)}",
                "detail": " ".join(part for part in (
                    str(f.get("why", "")).strip(),
                    f"Basis: {f.get('basis', 'ai_interpretation')}.",
                    str(f.get("pr_consideration", "")).strip(),
                ) if part),
                "severity": severity if severity in SEVERITIES else "LOW",
                "ref": m["code"],
            })
        actions.append(f"{m['code']}: " + (
            f"review '{_clip(top.get('content_detected', ''), 50)}' with the local distributor."
            if top else "no action from this material; confirm the certification category."))

    enabled = facts["research_enabled"]
    counts = facts.get("severity_counts") or {}
    highlights = [f"{len(facts['markets'])} markets reviewed: {counts.get('HIGH', 0)} high, "
                  f"{counts.get('MEDIUM', 0)} medium, {counts.get('LOW', 0)} low findings."]
    if facts["sources"]:
        highlights.append(f"{len(facts['sources'])} web sources fetched and cited where used.")
    themes = ", ".join((facts["analysis"].get("themes") or [])[:2]) or "the film's themes"
    verify = [] if enabled else [
        f"{m['code']}: current certification rules and any recent controversies around {themes}."
        for m in facts["markets"]
    ]
    genre = ", ".join(facts["analysis"].get("genre") or []) or "this film"
    summary = f"Reviewed {len(facts['markets'])} markets for {genre}. " + (
        "Findings marked researched are grounded in fetched sources."
        if enabled else
        "Web research was not enabled, so every finding is an AI interpretation to verify with local distributors."
    )
    high = any(f["severity"] == "HIGH" for f in findings)
    return {
        "summary": summary,
        "highlights": highlights,
        "findings": findings[:12],
        "next_actions": actions[:6],
        "confidence": "high" if enabled and not high else ("medium" if enabled else "low"),
        "data": {"markets": markets_out, "research_enabled": enabled,
                 "sources": facts["sources"], "verify_with_distributor": verify},
    }


def run_cultural(skill: Skill, state: GlobalState, params: dict, stage: StageFn, trace: list) -> dict:
    stage("material", "running")
    material, label = _material(state)
    stage("material", "complete", source=label, chars=len(material))
    stage("analyse_material", "running")
    analysis = audience_sim.analyse_material(state, material, trace)
    stage("analyse_material", "complete", genres=analysis.get("genre", []))
    requested = [str(m).upper() for m in (params.get("markets") or skill.meta_list("markets"))]
    codes = [m for m in requested if m in panel_lib.MARKETS] or ["US"]
    stage("research", "running", markets=len(codes), web="on" if tavily_client.enabled() else "off")
    sensitivity = audience_sim.cultural_scan(state, analysis, codes, trace)
    stage("research", "complete", findings=sensitivity.get("severity_counts", {}))
    facts = _cultural_facts(state, analysis, codes, sensitivity)
    return _synthesise(skill, facts, _cultural_fallback(facts), trace, stage)


# ---------------------------------------------------------------- registry --

RUNNERS: dict[str, Callable[[Skill, GlobalState, dict, StageFn, list], dict]] = {
    "casting": run_casting,
    "scheduling": run_scheduling,
    "audience-simulation": run_audience,
    "cultural-research": run_cultural,
}

# Skills whose inputs may have to be produced by phase agents first. Preparation
# changes state fields (candidates, stripboard), so the router runs it under the
# project lock and persists it before the slow advisory step begins.
PREPARERS: dict[str, Callable[[Skill, GlobalState, dict, StageFn], bool]] = {
    "casting": prepare_casting,
    "scheduling": prepare_scheduling,
}


def prepare_skill(skill: Skill, state: GlobalState, params: dict, stage: StageFn) -> bool:
    """Bring the state up to what the skill needs. Returns True when phase
    agents ran and the state must be saved."""
    preparer = PREPARERS.get(skill.name)
    return bool(preparer(skill, state, params or {}, stage)) if preparer else False


def run_skill(skill: Skill, state: GlobalState, params: dict, stage: StageFn, *, prepared: bool = False) -> dict:
    """Execute a skill on a project's state. Returns {result, provenance}.

    After `prepare_skill`, this step only appends A2A envelopes (the skill
    agent's own broadcasts plus whatever agents it consulted) to
    state.event_log; the caller merges them onto the stored state.
    """
    runner = RUNNERS.get(skill.name)
    if runner is None:
        raise SkillInputError(
            f"No agent implements the '{skill.name}' skill yet. Add a runner in domains/skills/agents.py."
        )
    if not prepared:
        prepare_skill(skill, state, params, stage)
    trace: list[dict] = []
    log_event(state, broadcast(skill.agent, "task_status_update", {
        "skill": skill.name, "status": "running", "skill_version": skill.version,
    }))
    result = runner(skill, state, params or {}, stage, trace)
    log_event(state, broadcast(skill.agent, "task_status_update", {
        "skill": skill.name, "status": "complete", "confidence": result.get("confidence"),
        "findings": len(result.get("findings", [])), "summary": _clip(result.get("summary", ""), 200),
    }))
    live = sum(1 for t in trace if t.get("source") == "gemini")
    provenance = {
        "trace": trace,
        "live_llm_calls": live,
        "total_llm_calls": len(trace),
        "mode": "live" if trace and live == len(trace) else ("mixed" if live else "mock"),
        "models_used": sorted({t.get("model") for t in trace if t.get("model")}),
        "skill_fingerprint": skill.fingerprint,
        "skill_version": skill.version,
    }
    return {"result": result, "provenance": provenance}
