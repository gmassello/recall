from typing import get_protocol_members
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app import db
from app.models import Diagnosis, GeneratedTicket
from app.tickets import MockTicketSource, TicketSource

FILA = {
    "id": "t1",
    "external_id": None,
    "title": "[payments-api] checkout lento",
    "description": "latencia p99 en 4200ms",
    "service": "payments-api",
    "severity": "sev2",
    "status": "open",
    "source": "generated",
    "created_at": "2026-07-20T00:00:00Z",
}


def test_el_ticket_generado_tiene_la_forma_del_spec():
    generado = GeneratedTicket.from_row(FILA)

    assert set(generado.model_dump()) == {
        "id",
        "title",
        "symptom",
        "service",
        "severity",
        "source",
    }
    assert generado.symptom == "latencia p99 en 4200ms"


def test_el_protocol_declara_todo_lo_que_la_api_usa():
    usados = {"list_open", "get", "ingest", "generate", "set_status"}

    assert usados <= get_protocol_members(TicketSource)
    assert isinstance(MockTicketSource(), TicketSource)


@pytest.mark.parametrize("valor", [95, -0.5, 1.5])
def test_confidence_fuera_de_rango_se_rechaza(valor):
    with pytest.raises(ValidationError):
        Diagnosis(root_cause="x", confidence=valor)


def test_confidence_en_rango_se_acepta():
    assert Diagnosis(root_cause="x", confidence=1.0).confidence == 1.0


def test_el_schema_se_manda_entero_en_un_solo_execute(monkeypatch):
    conexion = MagicMock()
    conexion.__enter__.return_value = conexion
    monkeypatch.setattr(db.psycopg, "connect", lambda *a, **kw: conexion)

    db.init_schema()

    sentencias = [call.args[0] for call in conexion.execute.call_args_list]
    schema = [s for s in sentencias if "CREATE TABLE" in s]
    assert len(schema) == 1
    assert schema[0] == db.SCHEMA_PATH.read_text()
