"""GlobalState — the one JSON object passed through the entire pipeline.

Mirrors contracts/global_state.json (AGENT.md Section 3). If you change a field
here, change the contract file too, and get team agreement first.
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Mode = Literal["enterprise", "indie"]
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
    date: str
    venue: str


class Schedule(BaseModel):
    stripboard: list[StripboardEntry] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class BudgetState(BaseModel):
    daily_burn: float = 0.0
    cap: float = 0.0
    alerts: list[str] = Field(default_factory=list)


class AudienceReport(BaseModel):
    tomatometer: float = 0.0
    audience_score: float = 0.0
    heatmap: dict[str, float] = Field(default_factory=dict)  # scene_id -> mean score
    weakest_scene_id: str = ""


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
    mode: Mode = "indie"
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
