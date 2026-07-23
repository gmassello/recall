from unittest.mock import MagicMock

import pytest

from app import memory

FILA = {
    "id": "abc",
    "title": "checkout lento",
    "symptom": "latencia p99 alta",
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
def capturas(monkeypatch):
    llamadas: list[tuple[str, list]] = []

    def fake_fetch_one(sql, params=None):
        llamadas.append((sql, list(params or [])))
        return dict(FILA)

    monkeypatch.setattr(memory, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(
        memory, "execute", lambda sql, params=None: llamadas.append((sql, list(params or [])))
    )
    monkeypatch.setattr(
        memory, "fetch", lambda sql, params=None: llamadas.append((sql, [])) or [{"id": 1}]
    )
    return llamadas


@pytest.fixture
def embedder(monkeypatch):
    fake = MagicMock()
    fake.embed.return_value = [0.1] * 4
    monkeypatch.setattr(memory, "get_embedder", lambda: fake)
    return fake


def test_editar_title_o_symptom_reembebe(capturas, embedder):
    memory.update_incident("abc", {"title": "nuevo titulo"})

    sql_update = capturas[-1][0]
    embedder.embed.assert_called_once_with("nuevo titulo latencia p99 alta")
    assert "embedding = %s" in sql_update
    assert "title = %s" in sql_update


def test_editar_title_identico_no_reembebe(capturas, embedder):
    memory.update_incident("abc", {"title": "checkout lento"})

    embedder.embed.assert_not_called()
    assert "embedding" not in capturas[-1][0]


def test_editar_solo_root_cause_no_reembebe(capturas, embedder):
    memory.update_incident("abc", {"root_cause": "pool agotado"})

    sql_update = capturas[-1][0]
    embedder.embed.assert_not_called()
    assert "embedding" not in sql_update
    assert "root_cause = %s" in sql_update


def test_editar_sin_cambios_no_emite_update(capturas, embedder):
    memory.update_incident("abc", {})

    assert len(capturas) == 1
    assert "SELECT" in capturas[0][0]


def test_eliminar_limpia_superseded_by_colgantes(capturas):
    assert memory.delete_incident("abc") is True

    sql_limpieza, sql_delete = capturas[0][0], capturas[1][0]
    assert "SET superseded_by = NULL" in sql_limpieza
    assert "WHERE superseded_by = %s" in sql_limpieza
    assert "DELETE FROM incidents WHERE id = %s" in sql_delete


def test_borrar_todo_devuelve_la_cantidad(capturas):
    assert memory.clear_memory() == 1
    assert "DELETE FROM incidents" in capturas[0][0]
