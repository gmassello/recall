from unittest.mock import MagicMock

import pytest

from app import memory
from seed import seed_memory

ROW = {
    "id": "abc",
    "title": "endless reboot loop",
    "symptom": "restarts right after the logo",
    "root_cause": None,
    "resolution": None,
    "service": "software-pc",
    "severity": "high",
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
    embedder.embed.assert_called_once_with("new title restarts right after the logo")
    assert "embedding = %s" in update_sql
    assert "title = %s" in update_sql


def test_editing_the_title_to_the_same_value_does_not_reembed(captured, embedder):
    memory.update_incident("abc", {"title": "endless reboot loop"})

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


def test_seeding_applies_the_stats_and_the_chain_outside_store_incident(monkeypatch):
    store = MagicMock(return_value="id-new")
    update, chain = MagicMock(), MagicMock()
    monkeypatch.setattr(
        seed_memory.memory, "ids_by_external_id", lambda ids: {"INC-old": "id-old"}
    )
    monkeypatch.setattr(seed_memory.memory, "store_incident", store)
    monkeypatch.setattr(seed_memory.memory, "update_incident", update)
    monkeypatch.setattr(seed_memory.memory, "supersede", chain)
    monkeypatch.setattr(
        seed_memory,
        "INCIDENTS",
        [
            {
                "external_id": "INC-new",
                "title": "t",
                "symptom": "s",
                "quality_score": 0.5,
                "times_cited": 3,
                "supersedes": "INC-old",
            }
        ],
    )

    seed_memory.seed_incidents()

    store.assert_called_once_with(
        source="seed", external_id="INC-new", title="t", symptom="s"
    )
    update.assert_called_once_with("id-new", {"quality_score": 0.5, "times_cited": 3})
    chain.assert_called_once_with("id-old", "id-new")


def test_clearing_everything_returns_the_count(captured):
    assert memory.clear_memory() == 1
    assert "DELETE FROM incidents" in captured[0][0]


def test_positive_feedback_adds_the_up_delta_and_counts_the_vote(captured):
    from app.config import settings

    memory.apply_feedback("abc", helpful=True)

    sql, params = captured[0]
    assert "GREATEST(-1.0, LEAST(1.0" in sql
    assert params[:2] == [settings.feedback_up, 1]


def test_negative_feedback_subtracts_the_down_delta_without_counting(captured):
    from app.config import settings

    memory.apply_feedback("abc", helpful=False)

    _, params = captured[0]
    assert params[:2] == [-settings.feedback_down, 0]


def test_query_incidents_stacks_filters_over_the_validity_filter(monkeypatch):
    reads: list[tuple[str, list]] = []
    monkeypatch.setattr(
        memory, "_read", lambda sql, params: reads.append((sql, params)) or ([], "fallback")
    )

    memory.query_incidents(service="software-pc", severity="high", limit=999)

    sql, params = reads[0]
    assert "service = %s" in sql
    assert "severity = %s" in sql
    assert memory.CURRENT_SQL_FILTER in sql
    assert params == ["software-pc", "high", 50]


def test_superseding_an_incident_with_itself_is_rejected(captured):
    assert memory.supersede("abc", "abc") is False
    assert captured == []
