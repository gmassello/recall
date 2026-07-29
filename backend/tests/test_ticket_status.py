import pytest

from app.api import tickets as api_tickets

TICKET = {"id": "t1", "title": "something", "service": "software-pc", "severity": "high"}


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
