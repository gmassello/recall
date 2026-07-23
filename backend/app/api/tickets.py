import logging
from collections.abc import Iterator

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from app import tickets
from app.agent.loop import handle, handle_events
from app.api.deps import get_ticket_or_404
from app.models import GeneratedTicket, HandleResponse, Ticket, TicketCreate

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[Ticket])
def list_tickets() -> list[dict]:
    return tickets.source.list_open()


@router.post("", response_model=Ticket, status_code=201)
def create_ticket(ticket: TicketCreate) -> dict:
    return tickets.source.ingest(ticket)


@router.post("/generate", status_code=201)
def generate_tickets(n: int = Query(1, ge=1, le=20)) -> dict:
    generados = [GeneratedTicket.from_row(row) for row in tickets.source.generate(n)]
    return {"generated": generados}


@router.get("/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str) -> dict:
    return get_ticket_or_404(ticket_id)


@router.post("/{ticket_id}/handle", response_model=HandleResponse)
def handle_ticket(ticket_id: str) -> HandleResponse:
    ticket = get_ticket_or_404(ticket_id)
    tickets.source.set_status(ticket_id, "handling")
    try:
        return handle(ticket)
    except Exception:
        tickets.source.set_status(ticket_id, "open")
        raise


@router.get("/{ticket_id}/handle/stream")
def handle_ticket_stream(ticket_id: str) -> EventSourceResponse:
    ticket = get_ticket_or_404(ticket_id)
    tickets.source.set_status(ticket_id, "handling")

    def eventos() -> Iterator[dict]:
        completo = False
        try:
            for kind, payload in handle_events(ticket):
                exclude = {"evidence"} if kind == "result" else None
                completo = completo or kind == "result"
                yield {"event": kind, "data": payload.model_dump_json(exclude=exclude)}
        except Exception as exc:
            log.exception("Fallo el agente durante el stream del ticket %s", ticket_id)
            yield {"event": "agent_error", "data": str(exc)}
        finally:
            if not completo:
                tickets.source.set_status(ticket_id, "open")

    return EventSourceResponse(eventos())
