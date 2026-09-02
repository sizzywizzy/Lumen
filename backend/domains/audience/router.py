"""Audience Simulation endpoints (Phase V). Mounted under /api/audience.

Runs are executed on a background thread and polled, because a live run makes
~8-12 Gemini calls and can take minutes — the dashboard shows real per-stage
progress rather than blocking an HTTP request.

Every route is scoped to the caller's production membership: starting a run
needs producer/owner, reading results needs any role.
"""
import hashlib
import threading
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.audience import personas as panel_lib
from core.auth.deps import require_member, require_producer
from core.auth.models import User
from core.auth.security import new_id
from domains.launch.agents import audience_sim
from services import mock_db, simulation_store, supabase_client, tavily_client

router = APIRouter(prefix="/api/audience", tags=["audience"])

STAGES = [
    ("analyse_material", "Analysed the material"),
    ("build_panel", "Generated the audience panel"),
    ("simulate_cohorts", "Simulated cohort responses"),
    ("derive_individuals", "Derived individual responses"),
    ("aggregate", "Aggregated audience segments"),
    ("cultural_scan", "Ran cultural sensitivity analysis"),
    ("pr_recommendations", "Generated PR recommendations"),
]

MAX_PANEL = 1000
MAX_MATERIAL_CHARS = 200_000

DISCLAIMER = (
    "Simulated Audience Feedback. These results come from an AI-generated panel of "
    "synthetic personas, not from real viewers. Treat them as a directional research "
    "signal for discussion — they are not a statistically representative audience "
    "study and do not predict real-world reception or box office."
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SimulationRequest(BaseModel):
    material: Optional[str] = Field(default=None, max_length=MAX_MATERIAL_CHARS)
    material_label: str = Field(default="", max_length=200)
    panel_size: int = Field(default=500, ge=20, le=MAX_PANEL)
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    markets: list[str] = Field(default_factory=lambda: ["US", "IN", "GB"])
    distribution: Optional[dict[str, dict[str, float]]] = None


def _fallback_material(project_id: str) -> tuple[str, str]:
    """Material to analyse when nothing was pasted into the form.

    Preference order:
      1. the screenplay uploaded at intake (script_context.raw_text)
      2. the project's structured script context, rendered as a brief
    The first is what a production actually wants analysed; the second is a
    thin fallback the analyst stage will correctly report as just a logline.
    """
    state = supabase_client.load_state(project_id)
    context = (state.script_context if state else {}) or {}

    raw = (context.get("raw_text") or "").strip()
    if raw:
        name = context.get("source_filename") or "uploaded script"
        return raw, f"{name} ({context.get('char_count', len(raw)):,} chars)"

    if context:
        scenes = mock_db.load("script").get("scenes", []) if context.get("title") else []
        lines = [
            f"TITLE: {context.get('title', project_id)}",
            f"GENRE: {context.get('genre', '')}",
            f"TONE: {context.get('tone', '')}",
            f"LOGLINE: {context.get('logline', '')}",
        ]
        roles = mock_db.load("script").get("roles", [])
        if roles:
            lines.append("CHARACTERS:")
            lines += [f"  - {r['name']} ({r['type']}): {r['description']}" for r in roles]
        if scenes:
            lines.append("SCENES:")
            lines += [
                f"  - {s['scene_id']} {s.get('int_ext','')} {s.get('location_type','')} "
                f"[{', '.join(s.get('tags', []))}]"
                for s in scenes
            ]
        return chr(10).join(lines), f"{context.get('title', project_id)} - project script context"

    raise HTTPException(
        400,
        "No material to analyse. Drop a screenplay on the Script Intake page, "
        "paste a synopsis here, or run the pipeline to seed script context.",
    )


def _skeleton(project_id: str, req: SimulationRequest, material: str, label: str, seed: int) -> dict[str, Any]:
    return {
        "simulation_id": new_id("SIM").upper(),
        "project_id": project_id,
        "status": "running",
        "created_at": _now(),
        "completed_at": None,
        "disclaimer": DISCLAIMER,
        "config": {
            "panel_size": req.panel_size,
            "seed": seed,
            "markets": req.markets,
            "material_label": label,
            "material_chars": len(material),
            "material_fingerprint": hashlib.sha256(material.encode()).hexdigest()[:16],
            "distribution_overrides": req.distribution or {},
        },
        "stages": [
            {"key": key, "label": label_text, "status": "pending", "detail": {}}
            for key, label_text in STAGES
        ],
        "report": None,
        "analysis": None,
        "sensitivity": None,
        "recommendations": None,
        "provenance": None,
        "error": None,
    }


def _run_in_background(record: dict, material: str, seed: int, req: SimulationRequest) -> None:
    project_id = record["project_id"]

    def on_stage(name: str, status: str, detail: dict):
        for stage in record["stages"]:
            if stage["key"] == name:
                stage["status"] = status
                if detail:
                    stage["detail"] = detail
                if status == "running":
                    stage["started_at"] = _now()
                else:
                    stage["finished_at"] = _now()
        simulation_store.save({**record, "report": record.get("report")})

    def worker():
        state = supabase_client.load_state(project_id)
        if state is None:
            record["status"] = "failed"
            record["error"] = f"No project state for {project_id}."
            simulation_store.save(record)
            return
        try:
            result = audience_sim.run_simulation(
                state,
                material,
                panel_size=req.panel_size,
                seed=seed,
                markets=req.markets,
                distribution=req.distribution,
                on_stage=on_stage,
            )
            record.update({
                "status": "complete",
                "completed_at": _now(),
                "analysis": result["analysis"],
                "report": result["report"],
                "sensitivity": result["sensitivity"],
                "recommendations": result["recommendations"],
                "provenance": result["provenance"],
                "dimensions": result["dimensions"],
                "distribution_fingerprint": result["distribution_fingerprint"],
                "cohort_summary": [
                    {k: c[k] for k in ("cohort_id", "size", "age_band_name", "market_bloc_name", "genre_affinity")}
                    for c in result["cohorts"]
                ],
            })
            # The agents log A2A envelopes onto GlobalState; persist them so the
            # Live Agent Terminal shows this run alongside the pipeline's own.
            supabase_client.save_state(state)
            simulation_store.save_panel(project_id, record["simulation_id"], {
                "personas": result["panel"],
                "responses": result["responses"],
                "cohorts": result["cohorts"],
                "distribution": result["distribution"],
            })
        except Exception as exc:  # noqa: BLE001 — recorded on the run, never swallowed
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"[:500]
            record["traceback"] = traceback.format_exc()[-1500:]
            for stage in record["stages"]:
                if stage["status"] == "running":
                    stage["status"] = "failed"
        simulation_store.save(record)

    threading.Thread(target=worker, name=f"audience-sim-{record['simulation_id']}", daemon=True).start()


@router.post("/simulations/{project_id}", status_code=202)
def start_simulation(project_id: str, req: SimulationRequest, membership=Depends(require_producer)):
    """Kick off a run. Returns immediately; poll the detail route for progress."""
    material = (req.material or "").strip()
    label = req.material_label.strip()
    if not material:
        material, label = _fallback_material(project_id)
    elif not label:
        label = "Pasted material"

    unknown = [m for m in req.markets if m not in panel_lib.MARKETS]
    if unknown:
        raise HTTPException(400, f"Unknown market codes: {unknown}. Known: {sorted(panel_lib.MARKETS)}")

    seed = req.seed if req.seed is not None else int(datetime.now().timestamp())
    record = _skeleton(project_id, req, material, label, seed)
    simulation_store.save(record)
    _run_in_background(record, material, seed, req)
    return {"simulation_id": record["simulation_id"], "status": "running", "stages": record["stages"]}


def _stored_material_meta(project_id: str) -> dict:
    """What the form shows as the default source when the box is left blank."""
    state = supabase_client.load_state(project_id)
    context = (state.script_context if state else {}) or {}
    raw = (context.get("raw_text") or "").strip()
    if raw:
        return {
            "kind": "uploaded_script",
            "filename": context.get("source_filename"),
            "format": context.get("source_format"),
            "char_count": context.get("char_count", len(raw)),
            "truncated": context.get("truncated", False),
            "excerpt": raw[:280],
        }
    if context:
        return {"kind": "script_context", "title": context.get("title"),
                "note": "Only the project's logline and scene list - upload a screenplay for a fuller read."}
    return {"kind": "none"}


@router.get("/simulations/{project_id}")
def list_simulations(project_id: str, _member=Depends(require_member)):
    """History, newest first — this is what makes v1 vs v2 comparison possible."""
    rows = simulation_store.list_for_project(project_id)
    return {
        "simulations": [
            {
                "simulation_id": r["simulation_id"],
                "status": r["status"],
                "created_at": r["created_at"],
                "completed_at": r.get("completed_at"),
                "panel_size": r.get("config", {}).get("panel_size"),
                "material_label": r.get("config", {}).get("material_label"),
                "material_fingerprint": r.get("config", {}).get("material_fingerprint"),
                "seed": r.get("config", {}).get("seed"),
                "overall_score": (r.get("report") or {}).get("overall_score"),
                "would_watch_pct": (r.get("report") or {}).get("would_watch_pct"),
                "mode": (r.get("provenance") or {}).get("mode"),
            }
            for r in rows
        ],
        "source_material": _stored_material_meta(project_id),
        "capabilities": {
            "research_enabled": tavily_client.enabled(),
            "markets": [{"code": c, "name": m["name"]} for c, m in sorted(panel_lib.MARKETS.items())],
            "max_panel_size": MAX_PANEL,
        },
        "disclaimer": DISCLAIMER,
    }


@router.get("/simulations/{project_id}/{simulation_id}")
def get_simulation(project_id: str, simulation_id: str, _member=Depends(require_member)):
    record = simulation_store.get(project_id, simulation_id)
    if record is None:
        raise HTTPException(404, "No such simulation for this production.")
    return record


@router.get("/simulations/{project_id}/{simulation_id}/panel")
def get_panel(
    project_id: str,
    simulation_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    _member=Depends(require_member),
):
    """The audit trail: individual personas paired with their own responses."""
    panel = simulation_store.get_panel(project_id, simulation_id)
    if panel is None:
        raise HTTPException(404, "No stored panel for this simulation.")
    responses = {r["persona_id"]: r for r in panel.get("responses", [])}
    people = panel.get("personas", [])
    window = people[offset: offset + limit]
    return {
        "total": len(people),
        "offset": offset,
        "limit": limit,
        "members": [{"persona": p, "response": responses.get(p["persona_id"])} for p in window],
    }
