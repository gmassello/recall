from secrets import compare_digest

from fastapi import Header, HTTPException, Query

from app import tickets
from app.config import settings

TICKET_NOT_FOUND = "Ticket not found"
TICKET_ALREADY_RESOLVED = "This ticket is already resolved"
TICKET_NOT_CLAIMABLE = "A resolved ticket cannot be diagnosed again"
DIAGNOSIS_NOT_FOUND = "This ticket has no saved diagnosis"
API_KEY_REQUIRED = "This endpoint requires a valid X-API-Key header"
AGENT_STREAM_ERROR = "The agent failed while handling this ticket"


def require_api_key(x_api_key: str = Header(""), key: str = Query("")) -> None:
    if not settings.demo_api_key:
        return
    if not compare_digest(x_api_key or key, settings.demo_api_key):
        raise HTTPException(status_code=401, detail=API_KEY_REQUIRED)


def get_ticket_or_404(ticket_id: str) -> dict:
    ticket = tickets.source.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=TICKET_NOT_FOUND)
    return ticket
