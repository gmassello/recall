from app import memory, tickets
from app.models import ResolveResponse


def write_postmortem(
    ticket: dict, root_cause: str, resolution: str, supersedes: str | None = None
) -> ResolveResponse:
    incident_id = memory.store_incident(
        title=ticket["title"],
        symptom=ticket.get("description") or ticket["title"],
        root_cause=root_cause,
        resolution=resolution,
        service=ticket.get("service"),
        severity=ticket.get("severity"),
        source="manual",
    )

    superseded = bool(supersedes) and memory.supersede(supersedes, incident_id)

    tickets.source.set_status(ticket["id"], "resolved")
    return ResolveResponse(
        incident_id=incident_id, embedded=True, superseded=supersedes if superseded else None
    )
