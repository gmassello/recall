from fastapi import HTTPException

from app import tickets

TICKET_NOT_FOUND = "Ticket not found"
DIAGNOSIS_NOT_FOUND = "This ticket has no saved diagnosis"


def get_ticket_or_404(ticket_id: str) -> dict:
    ticket = tickets.source.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=TICKET_NOT_FOUND)
    return ticket
