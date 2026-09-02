"""API endpoints for Phases III & IV (production). Mounted under /api/production."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from pydantic import BaseModel, Field

from core.auth.deps import require_member, require_producer
from core.orchestrator.graph import Orchestrator
from services import script_intake, supabase_client

router = APIRouter(prefix="/api/production", tags=["production"])


class ProductionSettings(BaseModel):
    country: str = "USA"
    excluded_states: list[str] = Field(default_factory=list)
    start_date: str = "2026-09-01"
    min_hours_per_day: float = 6
    max_hours_per_day: float = 10
    total_budget: float = 100000


class ExpenseInput(BaseModel):
    category: str
    description: str
    amount: float = Field(gt=0)


class ScriptUpload(BaseModel):
    """Screenplay from the intake dropzone. Send `text` for plain formats or
    `content_base64` for anything else (.pdf, .fdx)."""
    filename: str = Field(min_length=1, max_length=260)
    text: Optional[str] = Field(default=None, max_length=500_000)
    content_base64: Optional[str] = Field(default=None, max_length=12_000_000)


class ShootDayUpdate(BaseModel):
    date: str
    missed_scene_ids: list[str] = Field(default_factory=list)
    reshoot_date: str = ""
    note: str = ""


def _apply_budget(state):
    state.budget_state.spent = round(sum(item["amount"] for item in state.budget_state.expenses), 2)
    state.budget_state.remaining = round(state.budget_state.total_budget - state.budget_state.spent, 2)


@router.post("/run/{project_id}")
def run_production(project_id: str, _member=Depends(require_producer)):
    """Run Phase III (schedule) + Phase IV (compliance) on the stored state."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")
    state = Orchestrator().run(state, start="phase3", end="phase4")
    _apply_budget(state)
    supabase_client.save_state(state)
    return {
        "stripboard": [e.model_dump() for e in state.schedule.stripboard],
        "conflicts": state.schedule.conflicts,
        "budget_state": state.budget_state.model_dump(),
        "compliance_state": state.compliance_state,
        "event_log": state.event_log,
    }


@router.put("/settings/{project_id}")
def update_settings(project_id: str, settings: ProductionSettings, _member=Depends(require_producer)):
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    state.schedule.director_constraints = {"country": settings.country, "excluded_states": settings.excluded_states}
    state.schedule.shoot_settings = settings.model_dump(exclude={"country", "excluded_states", "total_budget"})
    state.budget_state.total_budget = settings.total_budget
    _apply_budget(state)
    supabase_client.save_state(state)
    return state.model_dump()


@router.post("/expenses/{project_id}")
def add_expense(project_id: str, expense: ExpenseInput, _member=Depends(require_producer)):
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    state.budget_state.expenses.append(expense.model_dump())
    _apply_budget(state)
    supabase_client.save_state(state)
    return state.budget_state.model_dump()


@router.post("/shoot-day/{project_id}")
def update_shoot_day(project_id: str, update: ShootDayUpdate, _member=Depends(require_producer)):
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    state.schedule.shoot_notes.append(update.model_dump())
    for entry in state.schedule.stripboard:
        if entry.date == update.date:
            entry.status = "PARTIAL" if entry.scene_id in update.missed_scene_ids else "COMPLETED"
            entry.director_note = update.note
    if update.missed_scene_ids and update.reshoot_date:
        for entry in state.schedule.stripboard:
            if entry.scene_id in update.missed_scene_ids:
                entry.date = update.reshoot_date
                entry.status = "PLANNED"
        state.schedule.reshoots.append({"from_date": update.date, "to_date": update.reshoot_date, "scene_ids": update.missed_scene_ids, "note": update.note})
    supabase_client.save_state(state)
    return state.model_dump()


@router.post("/script/{project_id}")
def upload_script(project_id: str, upload: ScriptUpload, _member=Depends(require_producer)):
    """Store the screenplay dropped at intake on the shared GlobalState.

    Everything downstream — most importantly the audience simulation — reads
    `script_context.raw_text`, so the whole team works from the same material.
    """
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")

    try:
        result = script_intake.extract(
            upload.filename, text=upload.text, content_base64=upload.content_base64
        )
    except script_intake.ScriptExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc

    state.script_context = {
        **(state.script_context or {}),
        "raw_text": result["text"],
        "source_filename": result["filename"],
        "source_format": result["format"],
        "char_count": result["char_count"],
        "truncated": result["truncated"],
        "fingerprint": result["fingerprint"],
    }
    supabase_client.save_state(state)
    return {k: v for k, v in result.items() if k != "text"} | {
        "excerpt": result["text"][:400],
        "project_id": project_id,
    }


@router.get("/script/{project_id}")
def get_script(project_id: str, _member=Depends(require_member)):
    """Metadata about the stored screenplay (not the full text)."""
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}.")
    context = state.script_context or {}
    raw = context.get("raw_text") or ""
    return {
        "has_script": bool(raw),
        "source_filename": context.get("source_filename"),
        "source_format": context.get("source_format"),
        "char_count": context.get("char_count", len(raw)),
        "truncated": context.get("truncated", False),
        "fingerprint": context.get("fingerprint"),
        "excerpt": raw[:400],
        "title": context.get("title"),
    }
