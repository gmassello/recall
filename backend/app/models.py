from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    title: str
    description: str | None = None
    service: str | None = None
    severity: Literal["sev1", "sev2", "sev3", "sev4"] = "sev3"
    external_id: str | None = None
    source: str = "manual"


class Ticket(BaseModel):
    id: str
    external_id: str | None = None
    title: str
    description: str | None = None
    service: str | None = None
    severity: str | None = None
    status: str
    source: str
    created_at: datetime


class MemoryHit(BaseModel):
    id: str
    title: str
    symptom: str
    root_cause: str | None = None
    resolution: str | None = None
    service: str | None = None
    severity: str | None = None
    created_at: datetime
    quality_score: float
    times_cited: int
    times_helpful: int
    distance: float
    score: float


class Incident(BaseModel):
    id: str
    title: str
    symptom: str
    root_cause: str | None = None
    resolution: str | None = None
    service: str | None = None
    severity: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    valid_until: datetime | None = None
    superseded_by: str | None = None
    quality_score: float
    times_cited: int
    times_helpful: int
    source: str


class Diagnosis(BaseModel):
    root_cause: str
    mitigation_steps: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class RelevantIncident(BaseModel):
    id: str
    title: str
    score: float


class EvidenceStep(BaseModel):
    tool: str
    via: str
    args: dict[str, Any]
    returned: Any


class HandleResponse(BaseModel):
    ticket_id: str
    diagnosis: Diagnosis
    most_relevant_incident: RelevantIncident | None = None
    evidence: list[EvidenceStep] = Field(default_factory=list)


class ResolveRequest(BaseModel):
    root_cause: str
    resolution: str
    supersedes: str | None = None


class ResolveResponse(BaseModel):
    incident_id: str
    embedded: bool
    superseded: str | None = None


class FeedbackRequest(BaseModel):
    incident_id: str
    helpful: bool


class FeedbackResponse(BaseModel):
    incident_id: str
    quality_score: float
    times_helpful: int
