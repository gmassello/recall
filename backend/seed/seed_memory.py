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
        "title": "Laptop that would not turn on: cracked power jack solder",
        "symptom": "the laptop shows no sign of life and the charging led stays off",
        "root_cause": "The charger was delivering voltage but the board power jack was dead from a cracked solder joint; no current reached the charging circuit.",
        "resolution": "The power jack was resoldered and the generic charger replaced with one of the correct voltage.",
        "service": "hardware-pc",
        "severity": "sev1",
        "created_at": days_ago(38),
    },
    {
        "external_id": "INC-002",
        "title": "Shutdowns from overheating with a clogged cooler",
        "symptom": "it shuts down by itself after a few minutes of use and the fan blows very hard",
        "root_cause": "The heatsink was clogged with dust and the thermal paste was dry; the CPU hit 100 degrees and cut off for protection.",
        "resolution": "Heatsink cleaning, thermal paste replacement and a 40 minute stress test that never went above 78 degrees.",
        "service": "hardware-pc",
        "severity": "sev2",
        "created_at": days_ago(95),
    },
    {
        "external_id": "INC-003",
        "title": "PC slowness solved by adding RAM",
        "symptom": "the machine is very slow when opening several programs at once",
        "root_cause": "It had 4GB of RAM and the system was paging against the disk all the time.",
        "resolution": "An 8GB module was added.",
        "service": "hardware-pc",
        "severity": "sev3",
        "created_at": days_ago(400),
        "valid_until": days_ago(200),
    },
    {
        "external_id": "INC-004",
        "title": "Windows reboot loop after an update",
        "symptom": "Windows reboots over and over after the last update and never reaches the desktop",
        "root_cause": "The cumulative update was left half installed by a power outage and made the boot inconsistent.",
        "resolution": "The update was uninstalled from the recovery environment, the boot was repaired and the full update applied again.",
        "service": "software-pc",
        "severity": "sev2",
        "created_at": days_ago(15),
    },
    {
        "external_id": "INC-005",
        "title": "Endless boot with the disk at 100 percent",
        "symptom": "it takes forever to boot and the disk sits at 100% usage while doing nothing",
        "root_cause": "The mechanical disk had reallocated sectors and retried every read; SMART was already raising an alert.",
        "resolution": "The system was cloned to an SSD and the user data recovered before the disk failed completely.",
        "service": "software-pc",
        "severity": "sev2",
        "created_at": days_ago(60),
    },
    {
        "external_id": "INC-006",
        "title": "Touchscreen dead on half the display after a drop",
        "symptom": "the touchscreen does not respond on a strip of the phone display",
        "root_cause": "The drop shifted the digitizer flex connector; the panel was fine but the contact was intermittent.",
        "resolution": "The digitizer flex was reseated and the adhesive frame replaced so it would not move again.",
        "service": "hardware-phone",
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
            log.info("%s already exists, skipped", incident["external_id"])
            continue
        memory.store_incident(source="seed", **incident)
        log.info("Memory: %s", incident["external_id"])


def seed_tickets() -> None:
    path = Path(__file__).parent / "tickets_seed.json"
    for raw in json.loads(path.read_text()):
        row = tickets.source.ingest(TicketCreate(**raw))
        tickets.source.set_status(row["id"], "open")
        log.info("Ticket: %s", raw["external_id"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seed_incidents()
    seed_tickets()
