import json

import pytest
from fastapi.testclient import TestClient

from app.api import tickets as api_tickets
from app.config import settings
from app.main import app

TICKET = {"id": "t1", "title": "something", "service": "software-pc", "severity": "high"}


class FakePayload:
    def __init__(self, data: dict) -> None:
        self.data = data

    def model_dump_json(self, exclude=None) -> str:
        return json.dumps({k: v for k, v in self.data.items() if not exclude or k not in exclude})


def sse_events(text: str) -> list[dict]:
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        event = {}
        for line in block.splitlines():
            key, _, value = line.partition(": ")
            event[key] = value
        if "event" in event:
            events.append(event)
    return events


class FakeSource:
    def __init__(self) -> None:
        self.states: list[str] = []

    def get(self, ticket_id: str) -> dict:
        return TICKET

    def set_status(self, ticket_id: str, status: str) -> None:
        self.states.append(status)


@pytest.fixture
def source(monkeypatch):
    fake = FakeSource()
    monkeypatch.setattr(api_tickets.tickets, "source", fake)
    return fake


@pytest.fixture
def saved(monkeypatch):
    responses: list = []
    monkeypatch.setattr(api_tickets.diagnoses, "save", responses.append)
    return responses


def test_the_ticket_goes_back_to_open_if_the_agent_fails(source, saved, monkeypatch):
    def raises(ticket):
        raise RuntimeError("Bedrock is not responding")

    monkeypatch.setattr(api_tickets, "handle", raises)

    with pytest.raises(RuntimeError):
        api_tickets.handle_ticket("t1")

    assert source.states == ["handling", "open"]
    assert saved == []


def test_the_ticket_stays_in_handling_if_the_agent_responds(source, saved, monkeypatch):
    monkeypatch.setattr(api_tickets, "handle", lambda ticket: "response")

    assert api_tickets.handle_ticket("t1") == "response"
    assert source.states == ["handling"]
    assert saved == ["response"]


def test_the_ticket_goes_back_to_open_if_saving_the_diagnosis_fails(source, monkeypatch):
    def failing_save(payload):
        raise RuntimeError("the diagnoses table is unreachable")

    monkeypatch.setattr(api_tickets, "handle", lambda ticket: "response")
    monkeypatch.setattr(api_tickets.diagnoses, "save", failing_save)

    with pytest.raises(RuntimeError):
        api_tickets.handle_ticket("t1")

    assert source.states == ["handling", "open"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "demo_api_key", "")
    return TestClient(app)


def test_the_stream_rolls_the_ticket_back_when_the_agent_fails(source, saved, monkeypatch, client):
    def failing_events(ticket):
        raise RuntimeError("Bedrock is not responding")
        yield

    monkeypatch.setattr(api_tickets, "handle_events", failing_events)

    events = sse_events(client.get("/tickets/t1/handle/stream").text)

    assert [e["event"] for e in events] == ["agent_error"]
    assert source.states == ["handling", "open"]
    assert saved == []


def test_the_stream_saves_the_result_and_keeps_handling(source, saved, monkeypatch, client):
    result = FakePayload({"diagnosis": "d", "evidence": ["step"]})

    def fake_events(ticket):
        yield "evidence", FakePayload({"tool": "search_memory"})
        yield "result", result

    monkeypatch.setattr(api_tickets, "handle_events", fake_events)

    events = sse_events(client.get("/tickets/t1/handle/stream").text)

    assert [e["event"] for e in events] == ["evidence", "result"]
    assert "evidence" not in json.loads(events[-1]["data"])
    assert saved == [result]
    assert source.states == ["handling"]


def test_the_stream_rolls_back_when_saving_the_diagnosis_fails(source, monkeypatch, client):
    def failing_save(payload):
        raise RuntimeError("the diagnoses table is unreachable")

    def fake_events(ticket):
        yield "result", FakePayload({"diagnosis": "d"})

    monkeypatch.setattr(api_tickets, "handle_events", fake_events)
    monkeypatch.setattr(api_tickets.diagnoses, "save", failing_save)

    events = sse_events(client.get("/tickets/t1/handle/stream").text)

    assert [e["event"] for e in events] == ["agent_error"]
    assert source.states == ["handling", "open"]
