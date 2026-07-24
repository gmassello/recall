from fastapi import HTTPException

from app import tickets

TICKET_NO_ENCONTRADO = "Ticket inexistente"


def get_ticket_or_404(ticket_id: str) -> dict:
    ticket = tickets.source.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=TICKET_NO_ENCONTRADO)
    return ticket
