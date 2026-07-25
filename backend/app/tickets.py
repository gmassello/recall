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
    ("hardware-pc", "la notebook no enciende y no prende el led de carga", "sev1"),
    ("hardware-pc", "se apaga sola a los {n} minutos de uso y sopla fuerte el cooler", "sev2"),
    ("software-pc", "Windows entra en bucle de reinicio tras el ultimo update", "sev2"),
    ("software-pc", "tarda {n} minutos en arrancar y el disco queda al 100% de uso", "sev3"),
    ("hardware-celular", "el tactil no responde en el {pct}% de la pantalla", "sev2"),
    ("hardware-celular", "no carga salvo que quede el cable en cierta posicion", "sev3"),
    ("software-celular", "queda en el logo al arrancar desde hace {n} dias", "sev2"),
    ("software-celular", "se quedo sin espacio con {gb}GB en fotos y no actualiza", "sev4"),
]


@runtime_checkable
class TicketSource(Protocol):
    def list_open(self) -> list[dict]: ...

    def get(self, ticket_id: str) -> dict | None: ...

    def ingest(self, ticket: TicketCreate) -> dict: ...

    def generate(self, n: int = 1) -> list[dict]: ...

    def set_status(self, ticket_id: str, status: str) -> None: ...

    def update(self, ticket_id: str, cambios: dict) -> dict | None: ...

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

    def update(self, ticket_id: str, cambios: dict) -> dict | None:
        if not cambios:
            return self.get(ticket_id)

        sets = ", ".join(f"{campo} = %s" for campo in cambios)
        return fetch_one(
            f"UPDATE tickets SET {sets} WHERE id = %s::UUID RETURNING {TICKET_COLUMNS}",
            [*cambios.values(), ticket_id],
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
