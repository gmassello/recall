from types import SimpleNamespace

import pytest

from app import tickets
from app.tickets import OPEN_SQL_FILTER, QUEUE_LIMIT, MockTicketSource
from seed import seed_memory


@pytest.fixture
def captured(monkeypatch):
    calls: list[tuple[str, list]] = []

    def fake_fetch_one(sql, params=None):
        calls.append((sql, list(params or [])))
        return {"id": "t1"}

    def fake_fetch(sql, params=None):
        calls.append((sql, list(params or [])))
        return [{"id": 1}]

    monkeypatch.setattr(tickets, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(tickets, "fetch", fake_fetch)
    return calls


def test_editing_builds_the_update_only_with_the_changed_fields(captured):
    MockTicketSource().update("t1", {"title": "new", "severity": "critical"})

    sql, params = captured[-1]
    assert "UPDATE tickets" in sql
    assert "title = %s" in sql
    assert "severity = %s" in sql
    assert "status = %s" not in sql
    assert params == ["new", "critical", "t1"]


def test_editing_without_changes_emits_no_update(captured):
    MockTicketSource().update("t1", {})

    assert len(captured) == 1
    assert "SELECT" in captured[0][0]


def test_deleting_removes_by_id(captured):
    assert MockTicketSource().delete("t1") is True

    sql, params = captured[0]
    assert "DELETE FROM tickets WHERE id = %s" in sql
    assert params == ["t1"]


def test_seeding_tickets_applies_the_status_of_the_fixture(monkeypatch):
    states: list[tuple[str, str]] = []
    double = SimpleNamespace(
        ingest=lambda ticket: {"id": ticket.external_id},
        set_status=lambda tid, status: states.append((tid, status)),
    )
    monkeypatch.setattr(seed_memory.tickets, "source", double)

    seed_memory.seed_tickets()

    assert ("TKT-001", "open") in states
    assert ("TKT-011", "handling") in states
    assert {status for _, status in states} == {"open", "handling"}


def test_clearing_uses_the_same_filter_as_the_queue(captured):
    assert MockTicketSource().clear_open() == 1
    assert f"DELETE FROM tickets WHERE {OPEN_SQL_FILTER}" in captured[0][0]

    MockTicketSource().query()
    assert OPEN_SQL_FILTER in captured[-1][0]


def test_the_queue_without_filters_hides_resolved_and_sorts_newest_first(captured):
    MockTicketSource().query()

    sql, params = captured[-1]
    assert OPEN_SQL_FILTER in sql
    assert "ORDER BY created_at DESC" in sql
    assert params == [QUEUE_LIMIT]


def test_an_explicit_status_replaces_the_open_filter(captured):
    MockTicketSource().query(status="resolved")

    sql, params = captured[-1]
    assert "status = %s" in sql
    assert OPEN_SQL_FILTER not in sql
    assert params == ["resolved", QUEUE_LIMIT]


def test_searching_by_title_wraps_the_term_in_wildcards(captured):
    MockTicketSource().query(search="boot")

    sql, params = captured[-1]
    assert "title ILIKE %s" in sql
    assert params == ["%boot%", QUEUE_LIMIT]


def test_ascending_order_flips_only_the_direction(captured):
    MockTicketSource().query(asc=True)

    assert "ORDER BY created_at ASC" in captured[-1][0]


def test_filters_stack_and_keep_the_limit_last(captured):
    MockTicketSource().query(service="hardware-pc", severity="critical", search="led")

    sql, params = captured[-1]
    assert "service = %s" in sql
    assert "severity = %s" in sql
    assert params == ["hardware-pc", "critical", "%led%", QUEUE_LIMIT]
