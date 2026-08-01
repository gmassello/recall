import random
from typing import Protocol, runtime_checkable

from app.config import settings
from app.db import execute, fetch, fetch_one
from app.models import TicketCreate, TicketStatus

TICKET_COLUMNS = """
    id::STRING AS id, external_id, title, description, service,
    severity, status, source, created_at
"""

OPEN_SQL_FILTER = "status != 'resolved'"
QUEUE_LIMIT = 100
UPDATABLE_COLUMNS = {"title", "description", "service", "severity", "status"}

TEMPLATES = [
    ("hardware-pc", "the laptop does not turn on and the charging led stays off", "critical"),
    ("hardware-pc", "it shuts down by itself after {n} minutes of use and the fan blows hard", "high"),
    ("software-pc", "Windows goes into a reboot loop after the last update", "high"),
    ("software-pc", "it takes {n} minutes to boot and the disk sits at 100% usage", "medium"),
    ("hardware-phone", "the touchscreen does not respond on {pct}% of the display", "high"),
    ("hardware-phone", "it only charges if the cable is held in a certain position", "medium"),
    ("software-phone", "it has been stuck on the logo at boot for {n} days", "high"),
    ("software-phone", "it ran out of space with {gb}GB of photos and will not update", "low"),
]


@runtime_checkable
class TicketSource(Protocol):
    def query(
        self,
        service: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        search: str | None = None,
        asc: bool = False,
    ) -> list[dict]: ...

    def get(self, ticket_id: str) -> dict | None: ...

    def ingest(self, ticket: TicketCreate) -> dict: ...

    def existing_external_ids(self, external_ids: list[str]) -> set[str]: ...

    def generate(self, n: int = 1) -> list[dict]: ...

    def set_status(self, ticket_id: str, status: TicketStatus) -> None: ...

    def claim(self, ticket_id: str) -> bool: ...

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

    def query(
        self,
        service: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        search: str | None = None,
        asc: bool = False,
    ) -> list[dict]:
        conditions, params = ([OPEN_SQL_FILTER], []) if status is None else (["status = %s"], [status])
        if service:
            conditions.append("service = %s")
            params.append(service)
        if severity:
            conditions.append("severity = %s")
            params.append(severity)
        if search:
            conditions.append("title ILIKE %s")
            params.append(f"%{search}%")
        params.append(QUEUE_LIMIT)
        return fetch(
            f"SELECT {TICKET_COLUMNS} FROM tickets "
            f"WHERE {' AND '.join(conditions)} "
            f"ORDER BY created_at {'ASC' if asc else 'DESC'} LIMIT %s",
            params,
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

    def existing_external_ids(self, external_ids: list[str]) -> set[str]:
        rows = fetch(
            "SELECT external_id FROM tickets WHERE external_id = ANY(%s)",
            (external_ids,),
        )
        return {row["external_id"] for row in rows}

    def generate(self, n: int = 1) -> list[dict]:
        return [self.ingest(self.generator.generate()) for _ in range(n)]

    def set_status(self, ticket_id: str, status: TicketStatus) -> None:
        execute(
            "UPDATE tickets SET status = %s WHERE id = %s::UUID", (status, ticket_id)
        )

    def claim(self, ticket_id: str) -> bool:
        row = fetch_one(
            "UPDATE tickets SET status = 'handling' "
            "WHERE id = %s::UUID AND status != 'resolved' RETURNING id::STRING AS id",
            (ticket_id,),
        )
        return row is not None

    def update(self, ticket_id: str, changes: dict) -> dict | None:
        if not changes:
            return self.get(ticket_id)

        unknown = set(changes) - UPDATABLE_COLUMNS
        if unknown:
            raise ValueError(f"Unknown ticket columns: {', '.join(sorted(unknown))}")

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
