"""API endpoints for Phases III & IV (production). Mounted under /api/production."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from core.auth.deps import require_member, require_producer
from core.auth.models import Membership
from core.responses import public_state
from core.shoot_window import IsoDate, settings_problem
from domains.pipeline import jobs
from services import script_intake, supabase_client

router = APIRouter(prefix="/api/production", tags=["production"])

MAX_SHOOT_HOURS = 24


class ProductionSettings(BaseModel):
    """The rules the schedule agent reads, and the production's total budget
    (GlobalState.budget_state.cap, the same number intake sets)."""
    country: str = Field(default="USA", min_length=1, max_length=60)
    excluded_states: list[str] = Field(default_factory=list, max_length=60)
    start_date: IsoDate = None
    end_date: IsoDate = None
    min_hours_per_day: float = Field(default=6, gt=0, le=MAX_SHOOT_HOURS)
    max_hours_per_day: float = Field(default=10, gt=0, le=MAX_SHOOT_HOURS)
    budget_usd: Optional[float] = Field(default=None, gt=0, le=10_000_000_000)

    @field_validator("excluded_states")
    @classmethod
    def _state_codes(cls, value: list[str]) -> list[str]:
        return [code.strip().upper()[:20] for code in value if code.strip()]

    @model_validator(mode="after")
    def _hours_in_order(self):
        if self.min_hours_per_day > self.max_hours_per_day:
            raise ValueError("The shortest shoot day can't be longer than the longest one.")
        return self


class ExpenseInput(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=10_000_000_000)


class ScriptUpload(BaseModel):
    """Screenplay from the intake dropzone. Send `text` for plain formats or
    `content_base64` for anything else (.pdf, .fdx)."""
    filename: str = Field(min_length=1, max_length=260)
    text: Optional[str] = Field(default=None, max_length=500_000)
    content_base64: Optional[str] = Field(default=None, max_length=12_000_000)


class ShootDayUpdate(BaseModel):
    """What happened on one shoot day: the scenes that were not finished, and
    the later day they move to."""
    date: IsoDate
    missed_scene_ids: list[str] = Field(default_factory=list, max_length=60)
    reshoot_date: IsoDate = None
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _dates_make_sense(self):
        if self.date is None:
            raise ValueError("Pick the shoot day this report is about.")
        if self.reshoot_date is not None and self.reshoot_date <= self.date:
            raise ValueError("Missed scenes can only move to a later day.")
        return self


def _update(project_id: str, change):
    try:
        return supabase_client.update_state(project_id, change)
    except supabase_client.StateMissing:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.") from None


def _production_summary(state) -> dict:
    return {
        "stripboard": [e.model_dump() for e in state.schedule.stripboard],
        "conflicts": state.schedule.conflicts,
        "budget_state": state.budget_state.model_dump(),
        "compliance_state": state.compliance_state,
    }


@router.post("/run/{project_id}", status_code=202)
def run_production(project_id: str, membership: Membership = Depends(require_producer)):
    """Run Phase III (schedule) + Phase IV (compliance) on the stored state, in
    the background. Poll /api/pipeline/status for progress."""
    if supabase_client.load_state(project_id) is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")
    try:
        return jobs.start(project_id, "production", started_by=membership.user_id, summary=_production_summary)
    except jobs.PipelineBusy:
        raise HTTPException(409, "Lumen is already working on this production. Wait for that run to finish.") from None


@router.put("/settings/{project_id}")
def update_settings(project_id: str, settings: ProductionSettings, _member=Depends(require_producer)):
    def change(state):
        # Merged, not replaced: saving these rules must keep the intake's shooting dates.
        merged = {
            **(state.schedule.shoot_settings or {}),
            **settings.model_dump(mode="json", exclude={"country", "excluded_states", "budget_usd"}, exclude_none=True),
        }
        problem = settings_problem(merged)
        if problem:
            raise HTTPException(422, problem)
        state.schedule.director_constraints = {"country": settings.country, "excluded_states": settings.excluded_states}
        state.schedule.shoot_settings = merged
        if settings.budget_usd:
            state.budget_state.cap = settings.budget_usd

    state, _ = _update(project_id, change)
    return public_state(state)


@router.post("/expenses/{project_id}")
def add_expense(project_id: str, expense: ExpenseInput, _member=Depends(require_producer)):
    state, _ = _update(project_id, lambda s: s.budget_state.expenses.append(expense.model_dump()))
    return state.budget_state.model_dump()


@router.post("/shoot-day/{project_id}")
def update_shoot_day(project_id: str, update: ShootDayUpdate, _member=Depends(require_producer)):
    report = update.model_dump(mode="json")

    def change(state):
        state.schedule.shoot_notes.append(report)
        for entry in state.schedule.stripboard:
            if entry.date == report["date"]:
                entry.status = "PARTIAL" if entry.scene_id in update.missed_scene_ids else "COMPLETED"
                entry.director_note = update.note
        if update.missed_scene_ids and report["reshoot_date"]:
            for entry in state.schedule.stripboard:
                if entry.scene_id in update.missed_scene_ids:
                    entry.date = report["reshoot_date"]
                    entry.status = "PLANNED"
            state.schedule.reshoots.append({
                "from_date": report["date"], "to_date": report["reshoot_date"],
                "scene_ids": update.missed_scene_ids, "note": update.note,
            })

    state, _ = _update(project_id, change)
    return public_state(state)


@router.post("/script/{project_id}")
def upload_script(project_id: str, upload: ScriptUpload, _member=Depends(require_producer)):
    """Store the screenplay dropped at intake on the shared GlobalState.

    Everything downstream — most importantly the audience simulation — reads
    `script_context.raw_text`, so the whole team works from the same material.
    """
    if supabase_client.load_state(project_id) is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")
    try:
        result = script_intake.extract(
            upload.filename, text=upload.text, content_base64=upload.content_base64
        )
    except script_intake.ScriptExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc

    def change(state):
        state.script_context = {
            **(state.script_context or {}),
            "raw_text": result["text"],
            "source_filename": result["filename"],
            "source_format": result["format"],
            "char_count": result["char_count"],
            "truncated": result["truncated"],
            "fingerprint": result["fingerprint"],
        }

    _update(project_id, change)
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
