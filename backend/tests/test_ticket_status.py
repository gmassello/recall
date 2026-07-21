import pytest

from app.api import tickets as api_tickets

TICKET = {"id": "t1", "title": "algo", "service": "payments-api", "severity": "sev2"}


class FakeSource:
    def __init__(self) -> None:
        self.estados: list[str] = []

    def get(self, ticket_id: str) -> dict:
        return TICKET

    def set_status(self, ticket_id: str, status: str) -> None:
        self.estados.append(status)


@pytest.fixture
def source(monkeypatch):
    fake = FakeSource()
    monkeypatch.setattr(api_tickets.tickets, "source", fake)
    return fake


def test_el_ticket_vuelve_a_open_si_el_agente_falla(source, monkeypatch):
    def explota(ticket):
        raise RuntimeError("Bedrock no responde")

    monkeypatch.setattr(api_tickets, "handle", explota)

    with pytest.raises(RuntimeError):
        api_tickets.handle_ticket("t1")

    assert source.estados == ["handling", "open"]


def test_el_ticket_queda_en_handling_si_el_agente_responde(source, monkeypatch):
    monkeypatch.setattr(api_tickets, "handle", lambda ticket: "respuesta")

    assert api_tickets.handle_ticket("t1") == "respuesta"
    assert source.estados == ["handling"]
