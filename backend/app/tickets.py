import random
from typing import Protocol, runtime_checkable

from app.config import settings
from app.db import execute, fetch, fetch_one
from app.models import TicketCreate

TICKET_COLUMNS = """
    id::STRING AS id, external_id, title, description, service,
    severity, status, source, created_at
"""

OPEN_SQL_FILTER = "status != 'resolved'"

TEMPLATES = [
    ("hardware-pc", "the laptop does not turn on and the charging led stays off", "sev1"),
    ("hardware-pc", "it shuts down by itself after {n} minutes of use and the fan blows hard", "sev2"),
    ("software-pc", "Windows goes into a reboot loop after the last update", "sev2"),
    ("software-pc", "it takes {n} minutes to boot and the disk sits at 100% usage", "sev3"),
    ("hardware-phone", "the touchscreen does not respond on {pct}% of the display", "sev2"),
    ("hardware-phone", "it only charges if the cable is held in a certain position", "sev3"),
    ("software-phone", "it has been stuck on the logo at boot for {n} days", "sev2"),
    ("software-phone", "it ran out of space with {gb}GB of photos and will not update", "sev4"),
]


@runtime_checkable
class TicketSource(Protocol):
    def list_open(self) -> list[dict]: ...

    def get(self, ticket_id: str) -> dict | None: ...

    def ingest(self, ticket: TicketCreate) -> dict: ...

    def generate(self, n: int = 1) -> list[dict]: ...

    def set_status(self, ticket_id: str, status: str) -> None: ...

    def update(self, ticket_id: str, changes: dict) -> dict | None: ...

    def delete(self, ticket_id: str) -> bool: ...

    def clear_open(self) -> int: ...


class TicketGenerator:
    def __init__(self, seed: int | None = None) -> None:
        self.random = random.Random(seed if seed is not None else settings.mock_seed)

    def generate(self) -> TicketCreate:
        service, template, severity = self.random.choice(TEMPLATES)
        symptom = template.format(
            pct=self.random.randrange(10, 95, 5),
            n=self.random.randrange(2, 60),
            gb=self.random.randrange(8, 512, 8),
        )
        return TicketCreate(
            title=f"[{service}] {symptom}",
            description=symptom,
            service=service,
            severity=severity,
            source="generated",
        )


class MockTicketSource:
    def __init__(self, generator: TicketGenerator | None = None) -> None:
        self.generator = generator or TicketGenerator()

    def list_open(self) -> list[dict]:
        return fetch(
            f"SELECT {TICKET_COLUMNS} FROM tickets WHERE {OPEN_SQL_FILTER} "
            "ORDER BY created_at DESC LIMIT 100"
        )

    def get(self, ticket_id: str) -> dict | None:
        return fetch_one(
            f"SELECT {TICKET_COLUMNS} FROM tickets WHERE id = %s::UUID", (ticket_id,)
        )

    def ingest(self, ticket: TicketCreate) -> dict:
        return fetch_one(
            f"""
            INSERT INTO tickets (external_id, title, description, service, severity, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (external_id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                service = excluded.service,
                severity = excluded.severity
            RETURNING {TICKET_COLUMNS}
            """,
            (
                ticket.external_id,
                ticket.title,
                ticket.description,
                ticket.service,
                ticket.severity,
                ticket.source,
            ),
        )

    def generate(self, n: int = 1) -> list[dict]:
        return [self.ingest(self.generator.generate()) for _ in range(n)]

    def set_status(self, ticket_id: str, status: str) -> None:
        execute(
            "UPDATE tickets SET status = %s WHERE id = %s::UUID", (status, ticket_id)
        )

    def update(self, ticket_id: str, changes: dict) -> dict | None:
        if not changes:
            return self.get(ticket_id)

        sets = ", ".join(f"{field} = %s" for field in changes)
        return fetch_one(
            f"UPDATE tickets SET {sets} WHERE id = %s::UUID RETURNING {TICKET_COLUMNS}",
            [*changes.values(), ticket_id],
        )

    def delete(self, ticket_id: str) -> bool:
        row = fetch_one(
            "DELETE FROM tickets WHERE id = %s::UUID RETURNING id::STRING AS id",
            (ticket_id,),
        )
        return row is not None

    def clear_open(self) -> int:
        rows = fetch(f"DELETE FROM tickets WHERE {OPEN_SQL_FILTER} RETURNING id")
        return len(rows)


source = MockTicketSource()
