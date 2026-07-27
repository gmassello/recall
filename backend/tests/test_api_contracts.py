from typing import get_protocol_members
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app import db, tickets
from app.config import Settings
from app.models import Diagnosis, GeneratedTicket
from app.tickets import MockTicketSource, TicketGenerator, TicketSource

ROW = {
    "id": "t1",
    "external_id": None,
    "title": "[payments-api] slow checkout",
    "description": "p99 latency at 4200ms",
    "service": "payments-api",
    "severity": "high",
    "status": "open",
    "source": "generated",
    "created_at": "2026-07-20T00:00:00Z",
}


def test_the_generated_ticket_has_the_shape_of_the_spec():
    generated = GeneratedTicket.from_row(ROW)

    assert set(generated.model_dump()) == {
        "id",
        "title",
        "symptom",
        "service",
        "severity",
        "source",
    }
    assert generated.symptom == "p99 latency at 4200ms"


def test_the_protocol_declares_everything_the_api_uses():
    used = {
        "query",
        "get",
        "ingest",
        "generate",
        "set_status",
        "update",
        "delete",
        "clear_open",
    }

    assert used <= get_protocol_members(TicketSource)
    assert isinstance(MockTicketSource(), TicketSource)


@pytest.mark.parametrize("value", [95, -0.5, 1.5])
def test_confidence_out_of_range_is_rejected(value):
    with pytest.raises(ValidationError):
        Diagnosis(root_cause="x", confidence=value)


def test_confidence_in_range_is_accepted():
    assert Diagnosis(root_cause="x", confidence=1.0).confidence == 1.0


@pytest.mark.parametrize(
    "value,expected",
    [
        ("http://localhost:5173", ["http://localhost:5173"]),
        ("https://a.com, https://b.com", ["https://a.com", "https://b.com"]),
        ("https://a.com,,", ["https://a.com"]),
    ],
    ids=["one", "several-with-spaces", "drops-empties"],
)
def test_the_cors_origins_are_parsed_from_the_env(value, expected):
    settings = Settings(database_url="postgresql://x", cors_origins=value)

    assert settings.cors_origin_list == expected


def test_reimporting_updates_the_fields_from_the_source(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        tickets, "fetch_one", lambda sql, params: captured.setdefault("sql", sql)
    )

    MockTicketSource().ingest(TicketGenerator(seed=1).generate())

    for field in ("title", "description", "service", "severity"):
        assert f"{field} = excluded.{field}" in captured["sql"]
    assert "status = excluded" not in captured["sql"]


def test_the_schema_is_sent_whole_in_a_single_execute(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(db.psycopg, "connect", lambda *a, **kw: connection)

    db.init_schema()

    statements = [call.args[0] for call in connection.execute.call_args_list]
    schema = [s for s in statements if "CREATE TABLE" in s]
    assert len(schema) == 1
    assert schema[0] == db.SCHEMA_PATH.read_text()
