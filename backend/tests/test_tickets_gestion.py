import pytest

from app import tickets
from app.tickets import OPEN_SQL_FILTER, MockTicketSource


@pytest.fixture
def capturas(monkeypatch):
    llamadas: list[tuple[str, list]] = []

    def fake_fetch_one(sql, params=None):
        llamadas.append((sql, list(params or [])))
        return {"id": "t1"}

    monkeypatch.setattr(tickets, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(
        tickets, "fetch", lambda sql, params=None: llamadas.append((sql, [])) or [{"id": 1}]
    )
    return llamadas


def test_editar_arma_el_update_solo_con_los_campos_cambiados(capturas):
    MockTicketSource().update("t1", {"title": "nuevo", "severity": "sev1"})

    sql, params = capturas[-1]
    assert "UPDATE tickets" in sql
    assert "title = %s" in sql
    assert "severity = %s" in sql
    assert "status = %s" not in sql
    assert params == ["nuevo", "sev1", "t1"]


def test_editar_sin_cambios_no_emite_update(capturas):
    MockTicketSource().update("t1", {})

    assert len(capturas) == 1
    assert "SELECT" in capturas[0][0]


def test_eliminar_borra_por_id(capturas):
    assert MockTicketSource().delete("t1") is True

    sql, params = capturas[0]
    assert "DELETE FROM tickets WHERE id = %s" in sql
    assert params == ["t1"]


def test_borrar_todo_usa_el_mismo_filtro_que_la_cola(capturas):
    assert MockTicketSource().clear_open() == 1
    assert f"DELETE FROM tickets WHERE {OPEN_SQL_FILTER}" in capturas[0][0]

    MockTicketSource().list_open()
    assert OPEN_SQL_FILTER in capturas[-1][0]
