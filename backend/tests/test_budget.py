"""One budget: the cap entered at intake or in Settings. The cost ledger's
total, spent and remaining are worked out from it and from the expenses the
team logs, so the Overview and the production page can never disagree."""
from fastapi.testclient import TestClient

from core.orchestrator.state import BudgetState, GlobalState
from services import supabase_client

PROJECT = "PROJ_NEON_NIGHTS"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_the_ledger_is_worked_out_from_the_cap_and_the_expenses():
    budget = BudgetState(cap=400_000, expenses=[{"category": "Crew", "description": "Grips", "amount": 1250.5}])
    dumped = budget.model_dump()
    assert (dumped["total_budget"], dumped["spent"], dumped["remaining"]) == (400_000, 1250.5, 398_749.5)
    budget.cap = 300_000
    assert budget.remaining == 298_749.5


def test_a_new_production_starts_with_an_empty_ledger():
    budget = GlobalState(project_id="PROJ_T").budget_state
    assert budget.expenses == [] and budget.spent == 0 and budget.remaining == budget.cap


def test_a_saved_state_loses_the_placeholder_rows_but_keeps_real_ones():
    legacy = {
        "cap": 250_000, "total_budget": 100_000, "spent": 36_700, "remaining": 63_300,
        "expenses": [
            {"category": "Cast", "description": "Cast deposits", "amount": 18000},
            {"category": "Equipment", "description": "Camera package", "amount": 7200},
            {"category": "Crew", "description": "Production crew payroll", "amount": 9500},
            {"category": "Location", "description": "Pier permit", "amount": 2000},
        ],
    }
    budget = BudgetState.model_validate(legacy)
    assert [e["description"] for e in budget.expenses] == ["Pier permit"]
    assert (budget.total_budget, budget.spent, budget.remaining) == (250_000, 2000, 248_000)


def test_registration_seeds_a_state_with_no_invented_spend(state_dir):
    from main import app

    response = TestClient(app).post("/api/auth/register", json={
        "email": "ava@neonnights.film", "password": "neon-nights-2026",
        "name": "Ava Reyes", "production_name": "Neon Nights",
    })
    assert response.status_code == 201
    project_id = response.json()["productions"][0]["project_id"]
    assert supabase_client.load_state(project_id).budget_state.expenses == []


def test_settings_edit_the_cap_that_the_whole_plan_reads(state_dir, signed_in, make_production):
    from main import app

    user, token = signed_in()
    make_production(user)
    supabase_client.save_state(GlobalState(project_id=PROJECT, budget_state=BudgetState(cap=250_000)))
    client = TestClient(app)

    body = client.put(f"/api/production/settings/{PROJECT}", headers=_auth(token),
                      json={"budget_usd": 400_000, "min_hours_per_day": 5, "max_hours_per_day": 9}).json()
    assert body["budget_state"]["cap"] == body["budget_state"]["total_budget"] == 400_000
    assert supabase_client.load_state(PROJECT).budget_state.cap == 400_000

    # Leaving the budget out keeps it.
    client.put(f"/api/production/settings/{PROJECT}", headers=_auth(token), json={"country": "USA"})
    assert supabase_client.load_state(PROJECT).budget_state.cap == 400_000

    ledger = client.post(f"/api/production/expenses/{PROJECT}", headers=_auth(token),
                         json={"category": "Crew", "description": "Grips", "amount": 1000}).json()
    assert (ledger["spent"], ledger["remaining"]) == (1000, 399_000)


def test_a_pipeline_run_keeps_the_teams_expenses(state_dir, offline, signed_in, make_production):
    import main

    user, _ = signed_in()
    make_production(user)
    state = GlobalState(project_id=PROJECT)
    state.budget_state.expenses.append({"category": "Crew", "description": "Grips", "amount": 1000})
    supabase_client.save_state(state)

    main.run_pipeline(main.InitRequest(project_id=PROJECT, budget_usd=300_000), user=user)
    budget = supabase_client.load_state(PROJECT).budget_state
    assert (budget.cap, budget.spent, budget.remaining) == (300_000, 1000, 299_000)
