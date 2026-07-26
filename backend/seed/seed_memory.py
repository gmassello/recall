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
        "title": "Notebook que no enciende por fuente quemada",
        "symptom": "la notebook no da senales de vida y no prende el led de carga",
        "root_cause": "El cargador entregaba tension pero el jack de alimentacion de la placa estaba frio por una soldadura partida; no llegaba corriente al circuito de carga.",
        "resolution": "Se resoldo el jack de alimentacion y se reemplazo el cargador generico por uno del voltaje correcto.",
        "service": "hardware-pc",
        "severity": "sev1",
        "created_at": days_ago(38),
    },
    {
        "external_id": "INC-002",
        "title": "Apagones por sobrecalentamiento con el cooler tapado",
        "symptom": "se apaga sola a los pocos minutos de uso y el cooler sopla muy fuerte",
        "root_cause": "El disipador estaba tapado de pelusa y la pasta termica seca; el CPU llegaba a 100 grados y cortaba por proteccion.",
        "resolution": "Limpieza del disipador, cambio de pasta termica y prueba de estres por 40 minutos sin superar 78 grados.",
        "service": "hardware-pc",
        "severity": "sev2",
        "created_at": days_ago(95),
    },
    {
        "external_id": "INC-003",
        "title": "Lentitud de la PC resuelta agregando memoria RAM",
        "symptom": "la maquina va muy lenta al abrir varios programas a la vez",
        "root_cause": "Tenia 4GB de RAM y el sistema paginaba contra el disco todo el tiempo.",
        "resolution": "Se agrego un modulo de 8GB.",
        "service": "hardware-pc",
        "severity": "sev3",
        "created_at": days_ago(400),
        "valid_until": days_ago(200),
    },
    {
        "external_id": "INC-004",
        "title": "Bucle de reinicio de Windows tras una actualizacion",
        "symptom": "Windows reinicia una y otra vez despues del ultimo update, sin llegar al escritorio",
        "root_cause": "La actualizacion acumulativa quedo a medio instalar por un corte de luz y dejo el arranque inconsistente.",
        "resolution": "Se desinstalo la actualizacion desde el entorno de recuperacion, se reparo el arranque y se volvio a aplicar el update completo.",
        "service": "software-pc",
        "severity": "sev2",
        "created_at": days_ago(15),
    },
    {
        "external_id": "INC-005",
        "title": "Arranque eterno con el disco al 100 por ciento",
        "symptom": "tarda muchisimo en arrancar y el disco queda al 100% de uso sin hacer nada",
        "root_cause": "El disco mecanico tenia sectores reasignados y reintentaba cada lectura; el SMART ya marcaba alerta.",
        "resolution": "Se clono el sistema a un SSD y se recuperaron los datos del usuario antes de que el disco terminara de fallar.",
        "service": "software-pc",
        "severity": "sev2",
        "created_at": days_ago(60),
    },
    {
        "external_id": "INC-006",
        "title": "Tactil sin respuesta en media pantalla tras un golpe",
        "symptom": "el tactil no responde en una franja de la pantalla del celular",
        "root_cause": "El golpe desplazo el conector flex del digitalizador; el panel estaba sano pero el contacto era intermitente.",
        "resolution": "Se reasento el flex del digitalizador y se cambio el marco adhesivo para que no se vuelva a mover.",
        "service": "hardware-celular",
        "severity": "sev2",
        "created_at": days_ago(8),
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
        fila = tickets.source.ingest(TicketCreate(**raw))
        tickets.source.set_status(fila["id"], "open")
        log.info("Ticket: %s", raw["external_id"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seed_incidents()
    seed_tickets()
