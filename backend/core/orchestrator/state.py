"""GlobalState — the one JSON object passed through the entire pipeline.

Mirrors contracts/global_state.json (AGENT.md Section 3). If you change a field
here, change the contract file too, and get team agreement first.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, computed_field, model_validator

CastingStatus = Literal["SOURCING", "SCREENING", "LOCKED"]
CandidateStatus = Literal["SOURCING", "SCREENING", "LOCKED", "DISQUALIFIED", "FLAGGED_ACTION_REQUIRED"]
ComplianceStatus = Literal["CLEARED", "AWAITING_QC", "BLOCKED"]
AssetStatus = Literal["DRAFT", "PR_REVIEW", "BLOCKED", "APPROVED", "SCHEDULED", "POSTED"]


class Candidate(BaseModel):
    id: str
    name: str
    role_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    media_url: str = ""
    scores: dict[str, float] = Field(default_factory=dict)  # audition/hype/pr/budget/composite, 0-100
    status: CandidateStatus = "SOURCING"
    disqualify_reason: Optional[str] = None


class StripboardEntry(BaseModel):
    scene_id: str
    heading: str = ""  # screenplay slugline, e.g. "EXT. CITY STREET - NIGHT"
    title: str = ""  # short plain-English name, e.g. "The rooftop toast"
    summary: str = ""
    date: str
    venue: str
    location_type: str = ""
    int_ext: str = ""
    estimated_time_hours: float = 0.0
    characters_needed: list[str] = Field(default_factory=list)
    cost_per_day: float = 0.0
    status: Literal["PLANNED", "PARTIAL", "COMPLETED"] = "PLANNED"
    director_note: str = ""


class Schedule(BaseModel):
    stripboard: list[StripboardEntry] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    director_constraints: dict[str, Any] = Field(default_factory=dict)
    shoot_settings: dict[str, Any] = Field(default_factory=dict)
    shoot_notes: list[dict[str, Any]] = Field(default_factory=list)
    reshoots: list[dict[str, Any]] = Field(default_factory=list)


# Placeholder ledger rows every production used to be created with. Nobody
# spent this money, so a saved state that still starts with them loses them.
_SEEDED_EXPENSES = [
    {"category": "Cast", "description": "Cast deposits", "amount": 18000},
    {"category": "Equipment", "description": "Camera package", "amount": 7200},
    {"category": "Crew", "description": "Production crew payroll", "amount": 9500},
]


class BudgetState(BaseModel):
    """One budget: `cap`, the total entered at intake or in Settings. The cost
    ledger's total, spent and remaining are worked out from it and from the
    expenses the team logs, never stored as numbers of their own."""
    daily_burn: float = 0.0
    cap: float = 250_000.0  # total production budget (USD) from intake — drives casting caps, venues, reach
    alerts: list[str] = Field(default_factory=list)
    expenses: list[dict[str, Any]] = Field(default_factory=list)  # logged on the production page

    @model_validator(mode="before")
    @classmethod
    def _drop_seeded_ledger(cls, data: Any) -> Any:
        if isinstance(data, dict) and (data.get("expenses") or [])[:3] == _SEEDED_EXPENSES:
            data = {**data, "expenses": data["expenses"][3:]}
        return data

    @computed_field
    @property
    def total_budget(self) -> float:
        return self.cap

    @computed_field
    @property
    def spent(self) -> float:
        return round(sum(float(item.get("amount") or 0) for item in self.expenses), 2)

    @computed_field
    @property
    def remaining(self) -> float:
        return round(self.cap - self.spent, 2)


class AudienceReview(BaseModel):
    source: str  # the outlet, or a description of the test viewer
    kind: Literal["critic", "viewer"] = "critic"
    quote: str
    score: str = ""


class AudienceReport(BaseModel):
    tomatometer: float = 0.0
    audience_score: float = 0.0
    heatmap: dict[str, float] = Field(default_factory=dict)  # scene_id -> mean score
    weakest_scene_id: str = ""
    weakest_scene_title: str = ""
    scene_titles: dict[str, str] = Field(default_factory=dict)  # scene_id -> title
    viewer_count: int = 0
    verdict: Literal["", "fresh", "rotten"] = ""
    reviews: list[AudienceReview] = Field(default_factory=list)
    # Who scored the scenes: "live" (the model), "mixed", or "offline" (the stated rules).
    screening_source: Literal["", "live", "mixed", "offline"] = ""


class MarketingAsset(BaseModel):
    asset_id: str
    type: Literal["reel", "meme", "poster", "thumbnail", "copy", "press_release"]
    status: AssetStatus = "DRAFT"
    source_scene_id: str = ""
    content: dict[str, Any] = Field(default_factory=dict)


class HumanEscalation(BaseModel):
    queue_item: str
    reason: str


class GlobalState(BaseModel):
    project_id: str
    locality: str = "Los Angeles, CA"
    director_notes: str = ""
    script_context: dict[str, Any] = Field(default_factory=dict)
    role_requirements: dict[str, Any] = Field(default_factory=dict)
    scoring_weights: dict[str, float] = Field(
        default_factory=lambda: {"W_A": 0.4, "W_H": 0.2, "W_PR": 0.2, "W_B": 0.2}
    )
    candidates: list[Candidate] = Field(default_factory=list)
    casting_status: CastingStatus = "SOURCING"
    schedule: Schedule = Field(default_factory=Schedule)
    budget_state: BudgetState = Field(default_factory=BudgetState)
    compliance_state: dict[str, ComplianceStatus] = Field(default_factory=dict)
    audience_report: AudienceReport = Field(default_factory=AudienceReport)
    marketing_assets: list[MarketingAsset] = Field(default_factory=list)
    human_escalations: list[HumanEscalation] = Field(default_factory=list)
    event_log: list[dict[str, Any]] = Field(default_factory=list)  # A2A envelopes, in order

    def active_candidates(self) -> list[Candidate]:
        return [c for c in self.candidates if c.status != "DISQUALIFIED"]

    def escalate(self, queue_item: str, reason: str) -> None:
        self.human_escalations.append(HumanEscalation(queue_item=queue_item, reason=reason))

    def clear_escalations(self, *prefixes: str) -> None:
        """Drop the queue items a phase owns before it runs again, so a re-run
        replaces its escalations instead of stacking a second copy."""
        self.human_escalations = [
            e for e in self.human_escalations if not e.queue_item.startswith(prefixes)
        ]
