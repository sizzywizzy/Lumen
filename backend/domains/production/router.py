"""API endpoints for Phases III & IV (production). Mounted under /api/production."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.orchestrator.graph import Orchestrator
from services import supabase_client

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


class ShootDayUpdate(BaseModel):
    date: str
    missed_scene_ids: list[str] = Field(default_factory=list)
    reshoot_date: str = ""
    note: str = ""


def _apply_budget(state):
    state.budget_state.spent = round(sum(item["amount"] for item in state.budget_state.expenses), 2)
    state.budget_state.remaining = round(state.budget_state.total_budget - state.budget_state.spent, 2)


@router.post("/run/{project_id}")
def run_production(project_id: str):
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
def update_settings(project_id: str, settings: ProductionSettings):
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
def add_expense(project_id: str, expense: ExpenseInput):
    state = supabase_client.load_state(project_id)
    if state is None:
        raise HTTPException(404, f"No state for {project_id}")
    state.budget_state.expenses.append(expense.model_dump())
    _apply_budget(state)
    supabase_client.save_state(state)
    return state.budget_state.model_dump()


@router.post("/shoot-day/{project_id}")
def update_shoot_day(project_id: str, update: ShootDayUpdate):
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
