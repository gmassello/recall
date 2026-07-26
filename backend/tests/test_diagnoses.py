import json

import pytest

from app import diagnoses
from app.models import Diagnosis, EvidenceStep, HandleResponse, RelevantIncident

RESPONSE = HandleResponse(
    ticket_id="t1",
    diagnosis=Diagnosis(root_cause="pool exhausted", confidence=0.7),
    most_relevant_incident=RelevantIncident(id="i1", title="past outage", score=0.31),
    evidence=[EvidenceStep(tool="search_memory", via="mcp", args={}, returned=[])],
)


@pytest.fixture
def captured(monkeypatch):
    calls: list[tuple[str, list]] = []
    monkeypatch.setattr(
        diagnoses, "execute", lambda sql, params=None: calls.append((sql, list(params)))
    )
    return calls


def test_saving_overwrites_the_previous_diagnosis_of_the_ticket(captured):
    diagnoses.save(RESPONSE)

    sql, params = captured[0]
    assert "INSERT INTO diagnoses" in sql
    assert "ON CONFLICT (ticket_id) DO UPDATE" in sql
    assert params[0] == "t1"
    assert json.loads(params[1])["diagnosis"]["root_cause"] == "pool exhausted"


def test_the_saved_payload_keeps_the_evidence(captured):
    diagnoses.save(RESPONSE)

    payload = json.loads(captured[0][1][1])
    assert [step["tool"] for step in payload["evidence"]] == ["search_memory"]


def test_reading_rebuilds_the_response_from_the_payload(monkeypatch):
    payload = RESPONSE.model_dump(mode="json")
    monkeypatch.setattr(diagnoses, "fetch_one", lambda sql, params: {"payload": payload})

    assert diagnoses.get("t1") == RESPONSE


def test_a_ticket_without_diagnosis_reads_as_none(monkeypatch):
    monkeypatch.setattr(diagnoses, "fetch_one", lambda sql, params: None)

    assert diagnoses.get("t1") is None
