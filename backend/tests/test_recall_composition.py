from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app import memory
from app.config import settings

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def row(distance: float, quality: float = 0.0, **overrides) -> dict:
    base = {
        "id": f"id-{distance}",
        "title": "t",
        "symptom": "s",
        "created_at": NOW - timedelta(days=1),
        "quality_score": quality,
        "valid_until": None,
        "superseded_by": None,
        "distance": distance,
    }
    return {**base, **overrides}


@pytest.fixture
def embedder(monkeypatch):
    fake = MagicMock()
    fake.embed.return_value = [0.1] * 4
    monkeypatch.setattr(memory, "get_embedder", lambda: fake)
    return fake


def test_recall_cuts_at_top_k_sorted_by_score_and_keeps_via(embedder, monkeypatch):
    monkeypatch.setattr(settings, "recall_top_k", 2)
    rows = [row(0.9), row(0.1), row(0.5), row(0.3, superseded_by="x")]
    monkeypatch.setattr(memory, "_read", lambda sql, params: (rows, "mcp"))

    hits, via = memory.recall("symptom")

    assert via == "mcp"
    assert [h["distance"] for h in hits] == [0.1, 0.5]
    assert all("score" in h for h in hits)


def test_quality_beats_distance_in_the_ranking(embedder, monkeypatch):
    monkeypatch.setattr(settings, "recall_top_k", 2)
    rows = [row(0.30), row(0.31, quality=1.0)]
    monkeypatch.setattr(memory, "_read", lambda sql, params: (rows, "fallback"))

    hits, _ = memory.recall("symptom")

    assert hits[0]["distance"] == 0.31


def test_read_prefers_the_mcp_when_it_answers(monkeypatch):
    monkeypatch.setattr(memory.cockroach_client, "is_configured", lambda: True)
    monkeypatch.setattr(memory, "render", lambda sql, params: sql)
    monkeypatch.setattr(memory.cockroach_client, "run_sql", lambda sql: [{"id": 1}])
    monkeypatch.setattr(
        memory, "fetch", lambda sql, params: pytest.fail("psycopg must not be reached")
    )

    assert memory._read("SELECT 1", []) == ([{"id": 1}], "mcp")


def test_read_falls_back_to_psycopg_when_the_mcp_fails(monkeypatch):
    monkeypatch.setattr(memory.cockroach_client, "is_configured", lambda: True)
    monkeypatch.setattr(memory, "render", lambda sql, params: sql)
    monkeypatch.setattr(memory.cockroach_client, "run_sql", lambda sql: None)
    monkeypatch.setattr(memory, "fetch", lambda sql, params: [{"id": 2}])

    assert memory._read("SELECT 1", []) == ([{"id": 2}], "fallback")


def test_read_skips_the_mcp_when_not_configured(monkeypatch):
    monkeypatch.setattr(memory.cockroach_client, "is_configured", lambda: False)
    monkeypatch.setattr(
        memory.cockroach_client, "run_sql", lambda sql: pytest.fail("MCP must not be reached")
    )
    monkeypatch.setattr(memory, "fetch", lambda sql, params: [])

    assert memory._read("SELECT 1", []) == ([], "fallback")
