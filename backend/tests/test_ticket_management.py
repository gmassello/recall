from types import SimpleNamespace

import pytest

from app import tickets
from app.tickets import OPEN_SQL_FILTER, MockTicketSource
from seed import seed_memory


@pytest.fixture
def captured(monkeypatch):
    calls: list[tuple[str, list]] = []

    def fake_fetch_one(sql, params=None):
        calls.append((sql, list(params or [])))
        return {"id": "t1"}

    monkeypatch.setattr(tickets, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(
        tickets, "fetch", lambda sql, params=None: calls.append((sql, [])) or [{"id": 1}]
    )
    return calls


def test_editing_builds_the_update_only_with_the_changed_fields(captured):
    MockTicketSource().update("t1", {"title": "new", "severity": "sev1"})

    sql, params = captured[-1]
    assert "UPDATE tickets" in sql
    assert "title = %s" in sql
    assert "severity = %s" in sql
    assert "status = %s" not in sql
    assert params == ["new", "sev1", "t1"]


def test_editing_without_changes_emits_no_update(captured):
    MockTicketSource().update("t1", {})

    assert len(captured) == 1
    assert "SELECT" in captured[0][0]


def test_deleting_removes_by_id(captured):
    assert MockTicketSource().delete("t1") is True

    sql, params = captured[0]
    assert "DELETE FROM tickets WHERE id = %s" in sql
    assert params == ["t1"]


def test_seeding_tickets_reopens_them_so_they_return_to_the_queue(monkeypatch):
    states: list[tuple[str, str]] = []
    double = SimpleNamespace(
        ingest=lambda ticket: {"id": ticket.external_id},
        set_status=lambda tid, status: states.append((tid, status)),
    )
    monkeypatch.setattr(seed_memory.tickets, "source", double)

    seed_memory.seed_tickets()

    assert states == [("TKT-001", "open"), ("TKT-002", "open"), ("TKT-003", "open")]


def test_clearing_uses_the_same_filter_as_the_queue(captured):
    assert MockTicketSource().clear_open() == 1
    assert f"DELETE FROM tickets WHERE {OPEN_SQL_FILTER}" in captured[0][0]

    MockTicketSource().list_open()
    assert OPEN_SQL_FILTER in captured[-1][0]
