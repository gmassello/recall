import logging
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from app import diagnoses, tickets
from app.agent.loop import handle, handle_events
from app.api.deps import (
    DIAGNOSIS_NOT_FOUND,
    TICKET_NOT_FOUND,
    get_ticket_or_404,
    require_api_key,
)
from app.models import (
    GeneratedTicket,
    HandleResponse,
    Severity,
    Ticket,
    TicketCreate,
    TicketStatus,
    TicketUpdate,
)
from seed.seed_memory import seed_incidents, seed_tickets

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])
protected = [Depends(require_api_key)]


@router.get("", response_model=list[Ticket])
def list_tickets(
    service: str | None = None,
    severity: Severity | None = None,
    status: TicketStatus | None = None,
    search: str | None = None,
    order: Literal["asc", "desc"] = "desc",
) -> list[dict]:
    return tickets.source.query(
        service=service, severity=severity, status=status, search=search, asc=order == "asc"
    )


@router.post("", response_model=Ticket, status_code=201)
def create_ticket(ticket: TicketCreate) -> dict:
    return tickets.source.ingest(ticket)


@router.post("/generate", status_code=201, dependencies=protected)
def generate_tickets(n: int = Query(1, ge=1, le=20)) -> dict:
    generated = [GeneratedTicket.from_row(row) for row in tickets.source.generate(n)]
    return {"generated": generated}


@router.post("/seed", status_code=204, dependencies=protected)
def seed_demo() -> None:
    seed_incidents()
    seed_tickets()


@router.delete("", dependencies=protected)
def clear_tickets() -> dict:
    return {"deleted": tickets.source.clear_open()}


@router.get("/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str) -> dict:
    return get_ticket_or_404(ticket_id)


@router.patch("/{ticket_id}", response_model=Ticket, dependencies=protected)
def edit_ticket(ticket_id: str, body: TicketUpdate) -> dict:
    row = tickets.source.update(ticket_id, body.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail=TICKET_NOT_FOUND)
    return row


@router.delete("/{ticket_id}", status_code=204, dependencies=protected)
def delete_ticket(ticket_id: str) -> None:
    if not tickets.source.delete(ticket_id):
        raise HTTPException(status_code=404, detail=TICKET_NOT_FOUND)


@router.get("/{ticket_id}/diagnosis", response_model=HandleResponse)
def get_diagnosis(ticket_id: str) -> HandleResponse:
    saved = diagnoses.get(ticket_id)
    if saved is None:
        raise HTTPException(status_code=404, detail=DIAGNOSIS_NOT_FOUND)
    return saved


@router.post("/{ticket_id}/handle", response_model=HandleResponse, dependencies=protected)
def handle_ticket(ticket_id: str) -> HandleResponse:
    ticket = get_ticket_or_404(ticket_id)
    tickets.source.set_status(ticket_id, "handling")
    try:
        response = handle(ticket)
        diagnoses.save(response)
    except Exception:
        tickets.source.set_status(ticket_id, "open")
        raise
    return response


@router.get("/{ticket_id}/handle/stream", dependencies=protected)
def handle_ticket_stream(ticket_id: str) -> EventSourceResponse:
    ticket = get_ticket_or_404(ticket_id)
    tickets.source.set_status(ticket_id, "handling")

    def events() -> Iterator[dict]:
        complete = False
        try:
            for kind, payload in handle_events(ticket):
                exclude = None
                if kind == "result":
                    diagnoses.save(payload)
                    complete = True
                    exclude = {"evidence"}
                yield {"event": kind, "data": payload.model_dump_json(exclude=exclude)}
        except Exception as exc:
            log.exception("The agent failed while streaming ticket %s", ticket_id)
            yield {"event": "agent_error", "data": str(exc)}
        finally:
            if not complete:
                tickets.source.set_status(ticket_id, "open")

    return EventSourceResponse(events())
