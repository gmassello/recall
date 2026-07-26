from unittest.mock import MagicMock

import pytest

from app import memory

ROW = {
    "id": "abc",
    "title": "slow checkout",
    "symptom": "high p99 latency",
    "root_cause": None,
    "resolution": None,
    "service": "payments-api",
    "severity": "sev2",
    "created_at": "2026-07-20T00:00:00Z",
    "resolved_at": None,
    "valid_until": None,
    "superseded_by": None,
    "quality_score": 0.0,
    "times_cited": 0,
    "times_helpful": 0,
    "source": "manual",
}


@pytest.fixture
def captured(monkeypatch):
    calls: list[tuple[str, list]] = []

    def fake_fetch_one(sql, params=None):
        calls.append((sql, list(params or [])))
        return dict(ROW)

    monkeypatch.setattr(memory, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(
        memory, "execute", lambda sql, params=None: calls.append((sql, list(params or [])))
    )
    monkeypatch.setattr(
        memory, "fetch", lambda sql, params=None: calls.append((sql, [])) or [{"id": 1}]
    )
    return calls


@pytest.fixture
def embedder(monkeypatch):
    fake = MagicMock()
    fake.embed.return_value = [0.1] * 4
    monkeypatch.setattr(memory, "get_embedder", lambda: fake)
    return fake


def test_editing_title_or_symptom_reembeds(captured, embedder):
    memory.update_incident("abc", {"title": "new title"})

    update_sql = captured[-1][0]
    embedder.embed.assert_called_once_with("new title high p99 latency")
    assert "embedding = %s" in update_sql
    assert "title = %s" in update_sql


def test_editing_the_title_to_the_same_value_does_not_reembed(captured, embedder):
    memory.update_incident("abc", {"title": "slow checkout"})

    embedder.embed.assert_not_called()
    assert "embedding" not in captured[-1][0]


def test_editing_only_root_cause_does_not_reembed(captured, embedder):
    memory.update_incident("abc", {"root_cause": "pool exhausted"})

    update_sql = captured[-1][0]
    embedder.embed.assert_not_called()
    assert "embedding" not in update_sql
    assert "root_cause = %s" in update_sql


def test_editing_without_changes_emits_no_update(captured, embedder):
    memory.update_incident("abc", {})

    assert len(captured) == 1
    assert "SELECT" in captured[0][0]


def test_deleting_clears_dangling_superseded_by(captured):
    assert memory.delete_incident("abc") is True

    cleanup_sql, delete_sql = captured[0][0], captured[1][0]
    assert "SET superseded_by = NULL" in cleanup_sql
    assert "WHERE superseded_by = %s" in cleanup_sql
    assert "DELETE FROM incidents WHERE id = %s" in delete_sql


def test_clearing_everything_returns_the_count(captured):
    assert memory.clear_memory() == 1
    assert "DELETE FROM incidents" in captured[0][0]
