import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import memory, tickets
from app.db import fetch_one
from app.models import TicketCreate

log = logging.getLogger(__name__)

NOW = datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


INCIDENTS = [
    {
        "external_id": "INC-001",
        "title": "Agotamiento del pool de conexiones en payments-api",
        "symptom": "latencia p99 de checkout por encima de 4000ms bajo carga alta",
        "root_cause": "El pool de conexiones a Postgres quedo en 50 y el trafico de la promo lo agoto; las requests esperaban conexion.",
        "resolution": "Se subio max_connections a 200 y se agrego pgbouncer delante del primario.",
        "service": "payments-api",
        "severity": "sev2",
        "created_at": days_ago(45),
    },
    {
        "external_id": "INC-002",
        "title": "5xx masivos en POST /charge por timeout del proveedor",
        "symptom": "40% de respuestas 5xx en el endpoint de cobro",
        "root_cause": "El timeout al gateway de pagos era de 30s y saturo los workers cuando el proveedor se degrado.",
        "resolution": "Timeout bajado a 5s con circuit breaker y reintento con backoff.",
        "service": "payments-api",
        "severity": "sev1",
        "created_at": days_ago(120),
    },
    {
        "external_id": "INC-003",
        "title": "Reintentos de checkout resueltos escalando replicas",
        "symptom": "latencia alta en checkout durante picos de trafico",
        "root_cause": "Falta de replicas en horario pico.",
        "resolution": "Se escalo a mano de 3 a 8 replicas.",
        "service": "payments-api",
        "severity": "sev3",
        "created_at": days_ago(400),
        "valid_until": days_ago(200),
    },
    {
        "external_id": "INC-004",
        "title": "Timeouts al validar JWT por cache de JWKS fria",
        "symptom": "picos de latencia de varios segundos validando tokens JWT",
        "root_cause": "La cache de JWKS expiraba cada 60s y cada refresh bloqueaba a todas las requests en vuelo.",
        "resolution": "TTL de la cache subido a 1h con refresh en background.",
        "service": "auth-service",
        "severity": "sev3",
        "created_at": days_ago(20),
    },
    {
        "external_id": "INC-005",
        "title": "Logins fallidos tras rotar la clave de firma",
        "symptom": "porcentaje alto de logins rechazados despues de un deploy",
        "root_cause": "La rotacion de clave no respeto el periodo de solapamiento y los tokens vigentes quedaron invalidos.",
        "resolution": "Se restauro la clave anterior y se documento la rotacion con solapamiento de 24h.",
        "service": "auth-service",
        "severity": "sev2",
        "created_at": days_ago(75),
    },
    {
        "external_id": "INC-006",
        "title": "Cola de notificaciones sin consumir por worker muerto",
        "symptom": "acumulacion de decenas de miles de mensajes sin procesar",
        "root_cause": "El consumidor quedo colgado en un socket sin timeout y no se reinicio porque el liveness probe solo miraba el puerto HTTP.",
        "resolution": "Timeout en el socket y liveness probe basado en el lag de la cola.",
        "service": "notifications",
        "severity": "sev3",
        "created_at": days_ago(10),
    },
]


def _exists(external_id: str) -> bool:
    return fetch_one(
        "SELECT 1 FROM incidents WHERE external_id = %s", (external_id,)
    ) is not None


def seed_incidents() -> None:
    for incident in INCIDENTS:
        if _exists(incident["external_id"]):
            log.info("%s ya existe, se omite", incident["external_id"])
            continue
        memory.store_incident(source="seed", **incident)
        log.info("Memoria: %s", incident["external_id"])


def seed_tickets() -> None:
    path = Path(__file__).parent / "tickets_seed.json"
    for raw in json.loads(path.read_text()):
        tickets.source.ingest(TicketCreate(**raw))
        log.info("Ticket: %s", raw["external_id"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seed_incidents()
    seed_tickets()
