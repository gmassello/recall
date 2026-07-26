import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import memory, tickets
from app.models import TicketCreate

log = logging.getLogger(__name__)

NOW = datetime.now(timezone.utc)

STATS = ("quality_score", "times_cited", "times_helpful")


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
    {
        "external_id": "INC-007",
        "title": "Dead laptop caused by a counterfeit charger",
        "symptom": "the laptop does not power up at all and no led lights up when plugged in",
        "root_cause": "A counterfeit charger delivered 12V instead of 19V and blew the input protection fuse of the board.",
        "resolution": "The input fuse was replaced and an original charger fitted; the machine has been stable since.",
        "service": "hardware-pc",
        "severity": "sev1",
        "created_at": days_ago(210),
        "quality_score": 0.8,
        "times_cited": 9,
        "times_helpful": 7,
    },
    {
        "external_id": "INC-008",
        "title": "Laptop with no signs of life, power button ribbon",
        "symptom": "nothing happens when the power button is pressed and there is no charging light",
        "root_cause": "The power button ribbon was disconnected from the board, so the press never reached the controller.",
        "resolution": "The ribbon was reconnected. The customer came back a week later with the same fault.",
        "service": "hardware-pc",
        "severity": "sev1",
        "created_at": days_ago(12),
        "quality_score": -0.6,
        "times_cited": 4,
    },
    {
        "external_id": "INC-009",
        "title": "Old desktop shutting down from dust buildup",
        "symptom": "the desktop powers off on its own under load and the fan spins loudly before it does",
        "root_cause": "Years of dust blocked the front intake and the case never exchanged air.",
        "resolution": "Full internal cleaning and two new case fans.",
        "service": "hardware-pc",
        "severity": "sev2",
        "created_at": days_ago(400),
        "quality_score": 0.3,
        "times_cited": 5,
        "times_helpful": 3,
    },
    {
        "external_id": "INC-010",
        "title": "Overheating from a thermal pad that came loose",
        "symptom": "it turns itself off after a few minutes of gaming and gets very hot near the hinge",
        "root_cause": "The GPU thermal pad had slipped out of place, so the die was not making contact with the heatsink.",
        "resolution": "New thermal pads and paste; the GPU now peaks at 71 degrees under load.",
        "service": "hardware-pc",
        "severity": "sev2",
        "created_at": days_ago(6),
    },
    {
        "external_id": "INC-011",
        "title": "Swollen battery pushing the trackpad up",
        "symptom": "the trackpad clicks by itself and the bottom case is bulging",
        "root_cause": "The battery had swollen after four years and was pressing against the trackpad from below.",
        "resolution": "The battery was replaced and the old one taken for safe disposal.",
        "service": "hardware-pc",
        "severity": "sev2",
        "created_at": days_ago(45),
    },
    {
        "external_id": "INC-012",
        "title": "Random freezes traced to a failing RAM stick",
        "symptom": "the machine freezes at random and needs a hard reset several times a day",
        "root_cause": "One of the two RAM modules failed memtest with thousands of errors in the first pass.",
        "resolution": "The faulty module was removed and later replaced with a matched pair.",
        "service": "hardware-pc",
        "severity": "sev2",
        "created_at": days_ago(120),
    },
    {
        "external_id": "INC-013",
        "title": "No video output after a power surge",
        "symptom": "the fans and lights turn on but the monitor stays black",
        "root_cause": "The surge killed the dedicated GPU; the board itself booted fine on integrated video.",
        "resolution": "The GPU was replaced and a surge protector added to the setup.",
        "service": "hardware-pc",
        "severity": "sev1",
        "created_at": days_ago(75),
    },
    {
        "external_id": "INC-015",
        "title": "Reboot loop after an update: current procedure",
        "symptom": "the PC restarts again and again after installing updates and never finishes booting",
        "root_cause": "The update database was corrupted, so every retry reapplied the same broken package.",
        "resolution": "Reset the update components before reapplying: uninstalling and reapplying the package alone reinstalls the same broken copy, which is why the old procedure kept coming back.",
        "service": "software-pc",
        "severity": "sev2",
        "created_at": days_ago(20),
        "supersedes": "INC-004",
        "quality_score": 0.5,
        "times_cited": 6,
        "times_helpful": 4,
    },
    {
        "external_id": "INC-016",
        "title": "Slow boot caused by too many startup apps",
        "symptom": "the computer takes several minutes to be usable after logging in",
        "root_cause": "Fourteen programs were set to launch at startup and all of them hit the disk at once.",
        "resolution": "Startup entries were trimmed to three. The customer reported no real improvement afterwards.",
        "service": "software-pc",
        "severity": "sev3",
        "created_at": days_ago(30),
        "quality_score": -0.4,
        "times_cited": 3,
    },
    {
        "external_id": "INC-017",
        "title": "Blue screens from an outdated graphics driver",
        "symptom": "it blue screens several times a day, mostly when watching video",
        "root_cause": "The graphics driver was three years old and incompatible with the current Windows build.",
        "resolution": "Clean driver uninstall and reinstall of the current version from the vendor.",
        "service": "software-pc",
        "severity": "sev2",
        "created_at": days_ago(52),
    },
    {
        "external_id": "INC-018",
        "title": "Windows deactivated after a motherboard swap",
        "symptom": "Windows says it is not activated after the motherboard was replaced",
        "root_cause": "The digital licence was tied to the old board's hardware id.",
        "resolution": "Reactivated by phone with the support agent reading out the installation id.",
        "service": "software-pc",
        "severity": "sev4",
        "created_at": days_ago(500),
        "valid_until": days_ago(120),
    },
    {
        "external_id": "INC-019",
        "title": "Everything slow because of browser adware",
        "symptom": "the browser opens ads on its own and the whole machine feels sluggish",
        "root_cause": "Two adware extensions and a scheduled task were reinstalling themselves at every boot.",
        "resolution": "Extensions and scheduled task removed, profile reset and a full antimalware scan.",
        "service": "software-pc",
        "severity": "sev3",
        "created_at": days_ago(18),
    },
    {
        "external_id": "INC-020",
        "title": "Files gone after an interrupted Windows upgrade",
        "symptom": "the user profile looks empty after an upgrade that was cut short",
        "root_cause": "The upgrade created a temporary profile because the original one failed to load.",
        "resolution": "The original profile was restored from the registry and the temporary one deleted.",
        "service": "software-pc",
        "severity": "sev1",
        "created_at": days_ago(88),
    },
    {
        "external_id": "INC-021",
        "title": "Unresponsive touch strip solved by a screen replacement",
        "symptom": "a horizontal band of the phone screen ignores every touch",
        "root_cause": "The digitizer layer itself was cracked under the glass, not just loose.",
        "resolution": "The screen assembly was replaced; reseating the flex had already been ruled out.",
        "service": "hardware-phone",
        "severity": "sev2",
        "created_at": days_ago(25),
        "quality_score": 0.6,
        "times_cited": 8,
        "times_helpful": 5,
    },
    {
        "external_id": "INC-022",
        "title": "Ghost touches while charging with a cheap adapter",
        "symptom": "the phone screen taps by itself and ignores real touches while it charges",
        "root_cause": "The unbranded adapter injected noise into the digitizer through the charging line.",
        "resolution": "Replaced the adapter with a certified one; the ghost touches stopped immediately.",
        "service": "hardware-phone",
        "severity": "sev3",
        "created_at": days_ago(40),
    },
    {
        "external_id": "INC-023",
        "title": "Phone overheating from a swollen battery",
        "symptom": "the phone gets very hot while charging and the back cover no longer sits flush",
        "root_cause": "The battery had swollen and was pressing against the frame.",
        "resolution": "Battery replaced and the adhesive frame renewed.",
        "service": "hardware-phone",
        "severity": "sev1",
        "created_at": days_ago(14),
    },
    {
        "external_id": "INC-024",
        "title": "Blurry camera after a drop",
        "symptom": "photos come out blurry and the camera rattles when the phone is shaken",
        "root_cause": "The optical stabilization module broke loose in the fall.",
        "resolution": "The rear camera module was replaced.",
        "service": "hardware-phone",
        "severity": "sev3",
        "created_at": days_ago(65),
    },
    {
        "external_id": "INC-025",
        "title": "Dead phone after water exposure",
        "symptom": "the phone stopped working after getting wet and does not respond to the charger",
        "root_cause": "Corrosion had bridged several pads around the charging controller.",
        "resolution": "Ultrasonic cleaning of the board and replacement of the charging controller; the data was recovered.",
        "service": "hardware-phone",
        "severity": "sev1",
        "created_at": days_ago(33),
    },
    {
        "external_id": "INC-026",
        "title": "No sound on calls with a blocked earpiece mesh",
        "symptom": "the other side cannot be heard on calls unless the speakerphone is on",
        "root_cause": "The earpiece mesh was packed with lint and dust.",
        "resolution": "The mesh was cleaned; no parts were needed.",
        "service": "hardware-phone",
        "severity": "sev3",
        "created_at": days_ago(150),
    },
]


def seed_incidents() -> None:
    known = memory.ids_by_external_id([i["external_id"] for i in INCIDENTS])
    for incident in INCIDENTS:
        external_id = incident["external_id"]
        if external_id in known:
            log.info("%s already exists, skipped", external_id)
            continue
        data = dict(incident)
        stats = {field: data.pop(field) for field in STATS if field in data}
        supersedes = data.pop("supersedes", None)
        known[external_id] = memory.store_incident(source="seed", **data)
        if stats:
            memory.update_incident(known[external_id], stats)
        if supersedes in known:
            memory.supersede(known[supersedes], known[external_id])
        log.info("Memory: %s", external_id)


def seed_tickets() -> None:
    path = Path(__file__).parent / "tickets_seed.json"
    for raw in json.loads(path.read_text()):
        ticket = dict(raw)
        status = ticket.pop("status", "open")
        row = tickets.source.ingest(TicketCreate(**ticket))
        tickets.source.set_status(row["id"], status)
        log.info("Ticket: %s", raw["external_id"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seed_incidents()
    seed_tickets()
