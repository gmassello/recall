import random
from typing import Protocol, runtime_checkable

from app.config import settings
from app.db import execute, fetch, fetch_one
from app.models import TicketCreate

TICKET_COLUMNS = """
    id::STRING AS id, external_id, title, description, service,
    severity, status, source, created_at
"""

TEMPLATES = [
    ("payments-api", "latencia p99 subio a {ms}ms en checkout", "sev2"),
    ("payments-api", "{pct}% de 5xx en POST /charge", "sev1"),
    ("payments-api", "el pool de conexiones se agota con {n} requests concurrentes", "sev1"),
    ("auth-service", "picos de timeout al validar JWT ({ms}ms)", "sev3"),
    ("auth-service", "{pct}% de logins fallidos tras rotar la clave de firma", "sev2"),
    ("notifications", "cola de envios con {n} mensajes sin consumir", "sev3"),
    ("notifications", "los push tardan {ms}ms en salir desde que se encolan", "sev3"),
    ("search-indexer", "el indice quedo {n} documentos atras del primario", "sev2"),
]


@runtime_checkable
class TicketSource(Protocol):
    def list_open(self) -> list[dict]: ...

    def get(self, ticket_id: str) -> dict | None: ...

    def ingest(self, ticket: TicketCreate) -> dict: ...

    def generate(self, n: int = 1) -> list[dict]: ...

    def set_status(self, ticket_id: str, status: str) -> None: ...


class TicketGenerator:
    def __init__(self, seed: int | None = None) -> None:
        self.random = random.Random(seed if seed is not None else settings.mock_seed)

    def generate(self) -> TicketCreate:
        service, template, severity = self.random.choice(TEMPLATES)
        symptom = template.format(
            ms=self.random.randrange(800, 9000, 100),
            pct=self.random.randrange(5, 80, 5),
            n=self.random.randrange(500, 50000, 500),
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
            f"SELECT {TICKET_COLUMNS} FROM tickets WHERE status != 'resolved' "
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


source = MockTicketSource()
