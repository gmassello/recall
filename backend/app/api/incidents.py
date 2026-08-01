from fastapi import APIRouter, Depends, HTTPException

from app import memory
from app.api.deps import get_ticket_or_404, require_api_key
from app.models import (
    FeedbackRequest,
    FeedbackResponse,
    ResolveRequest,
    ResolveResponse,
)
from app.postmortem import write_postmortem

router = APIRouter(prefix="/incidents", tags=["incidents"])
protected = [Depends(require_api_key)]


@router.post("/{ticket_id}/resolve", response_model=ResolveResponse, status_code=201, dependencies=protected)
def resolve(ticket_id: str, body: ResolveRequest) -> ResolveResponse:
    return write_postmortem(
        get_ticket_or_404(ticket_id), body.root_cause, body.resolution, body.supersedes
    )


@router.post("/{ticket_id}/feedback", response_model=FeedbackResponse, dependencies=protected)
def feedback(ticket_id: str, body: FeedbackRequest) -> dict:
    get_ticket_or_404(ticket_id)
    updated = memory.apply_feedback(body.incident_id, body.helpful)
    if updated is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return updated
