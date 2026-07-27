from app.db import execute, fetch_one
from app.models import HandleResponse


def save(response: HandleResponse) -> None:
    execute(
        """
        INSERT INTO diagnoses (ticket_id, payload)
        VALUES (%s::UUID, %s::JSONB)
        ON CONFLICT (ticket_id) DO UPDATE SET
            payload = excluded.payload,
            created_at = now()
        """,
        (response.ticket_id, response.model_dump_json()),
    )


def get(ticket_id: str) -> HandleResponse | None:
    row = fetch_one(
        "SELECT payload FROM diagnoses WHERE ticket_id = %s::UUID", (ticket_id,)
    )
    return HandleResponse.model_validate(row["payload"]) if row else None
