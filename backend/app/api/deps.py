from fastapi import HTTPException

from app import tickets


def get_ticket_or_404(ticket_id: str) -> dict:
    ticket = tickets.source.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket inexistente")
    return ticket
