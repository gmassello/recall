import pytest

from app.tickets import TEMPLATES, TicketGenerator
from seed.seed_memory import INCIDENTS

AREAS_TEMPLATES = {service for service, _, _ in TEMPLATES}
AREAS_SEED = {incident["service"] for incident in INCIDENTS}


@pytest.mark.parametrize("template", TEMPLATES, ids=[t[1][:30] for t in TEMPLATES])
def test_cada_plantilla_produce_un_ticket_valido(template, monkeypatch):
    monkeypatch.setattr("app.tickets.TEMPLATES", [template])

    ticket = TicketGenerator(seed=1).generate()

    assert ticket.service == template[0]
    assert "{" not in ticket.description


def test_la_memoria_sembrada_vive_en_areas_que_el_generador_cubre():
    assert AREAS_SEED <= AREAS_TEMPLATES


def test_queda_un_area_sin_antecedentes_en_memoria():
    assert AREAS_TEMPLATES - AREAS_SEED
