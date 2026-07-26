import pytest

from app.tickets import TEMPLATES, TicketGenerator
from seed.seed_memory import INCIDENTS

TEMPLATE_AREAS = {service for service, _, _ in TEMPLATES}
SEED_AREAS = {incident["service"] for incident in INCIDENTS}


@pytest.mark.parametrize("template", TEMPLATES, ids=[t[1][:30] for t in TEMPLATES])
def test_every_template_produces_a_valid_ticket(template, monkeypatch):
    monkeypatch.setattr("app.tickets.TEMPLATES", [template])

    ticket = TicketGenerator(seed=1).generate()

    assert ticket.service == template[0]
    assert "{" not in ticket.description


def test_the_seeded_memory_lives_in_areas_the_generator_covers():
    assert SEED_AREAS <= TEMPLATE_AREAS


def test_one_area_is_left_without_precedent_in_memory():
    assert TEMPLATE_AREAS - SEED_AREAS
