from fastapi import APIRouter, Query

from app import tickets
from app.agent.loop import handle
from app.api.deps import get_ticket_or_404
from app.models import HandleResponse, Ticket, TicketCreate

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[Ticket])
def list_tickets() -> list[dict]:
    return tickets.source.list_open()


@router.post("", response_model=Ticket, status_code=201)
def create_ticket(ticket: TicketCreate) -> dict:
    return tickets.source.ingest(ticket)


@router.post("/generate", status_code=201)
def generate_tickets(n: int = Query(1, ge=1, le=20)) -> dict:
    return {"generated": tickets.source.generate(n)}


@router.get("/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str) -> dict:
    return get_ticket_or_404(ticket_id)


@router.post("/{ticket_id}/handle", response_model=HandleResponse)
def handle_ticket(ticket_id: str) -> HandleResponse:
    ticket = get_ticket_or_404(ticket_id)
    tickets.source.set_status(ticket_id, "handling")
    return handle(ticket)
