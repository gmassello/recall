import pytest
from fastapi import HTTPException

from app import postmortem
from app.api import incidents as api_incidents
from app.models import ResolveRequest

TID = "0f7a26a2-93a3-4bfb-9b09-e6e9175bf0a4"
OLD = "45d2fc2e-4cea-4ffe-aed9-406b23e8afd4"
TICKET = {
    "id": TID,
    "title": "endless reboot loop",
    "description": "restarts right after the logo",
    "service": "software-pc",
    "severity": "high",
    "status": "handling",
}


@pytest.fixture
def calls(monkeypatch):
    recorded: list[tuple] = []

    def store(**kwargs):
        recorded.append(("store", kwargs))
        return "new-id"

    monkeypatch.setattr(postmortem.memory, "store_incident", store)
    monkeypatch.setattr(
        postmortem.memory,
        "supersede",
        lambda old, new: recorded.append(("supersede", old, new)) or True,
    )
    monkeypatch.setattr(
        postmortem.tickets,
        "source",
        type("S", (), {"set_status": lambda self, tid, status: recorded.append(("status", tid, status))})(),
    )
    return recorded


def test_the_postmortem_stores_then_supersedes_then_resolves(calls):
    response = postmortem.write_postmortem(TICKET, "root", "fix", OLD)

    assert [c[0] for c in calls] == ["store", "supersede", "status"]
    assert calls[1] == ("supersede", OLD, "new-id")
    assert calls[2] == ("status", TID, "resolved")
    assert response.incident_id == "new-id"
    assert response.superseded == OLD


def test_the_symptom_falls_back_to_the_title(calls):
    ticket = dict(TICKET, description=None)

    postmortem.write_postmortem(ticket, "root", "fix")

    stored = calls[0][1]
    assert stored["symptom"] == ticket["title"]
    assert [c[0] for c in calls] == ["store", "status"]


def test_a_failed_supersede_is_not_reported(calls, monkeypatch):
    monkeypatch.setattr(postmortem.memory, "supersede", lambda old, new: False)

    response = postmortem.write_postmortem(TICKET, "root", "fix", OLD)

    assert response.superseded is None


def test_resolving_a_resolved_ticket_conflicts(monkeypatch):
    resolved = dict(TICKET, status="resolved")
    monkeypatch.setattr(api_incidents, "get_ticket_or_404", lambda tid: resolved)

    with pytest.raises(HTTPException) as raised:
        api_incidents.resolve(TID, ResolveRequest(root_cause="r", resolution="f"))

    assert raised.value.status_code == 409
