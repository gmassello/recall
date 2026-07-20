from datetime import datetime, timedelta, timezone

import pytest

from app.memory import CURRENT_SQL_FILTER, is_current

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def row(**overrides) -> dict:
    base = {"distance": 0.2, "superseded_by": None, "valid_until": None}
    return base | overrides


@pytest.mark.parametrize(
    "candidate,esperado",
    [
        (row(), True),
        (row(valid_until=NOW - timedelta(days=1)), False),
        (row(valid_until=NOW + timedelta(days=1)), True),
        (row(superseded_by="otro-uuid"), False),
        (row(distance=None), False),
    ],
    ids=[
        "vigente",
        "valid_until-vencido",
        "valid_until-futuro",
        "reemplazado",
        "sin-embedding",
    ],
)
def test_vigencia_de_un_candidato(candidate, esperado):
    assert is_current(candidate, NOW) is esperado


def test_valid_until_como_string_iso():
    vencido = row(valid_until=(NOW - timedelta(days=1)).isoformat())
    assert is_current(vencido, NOW) is False


def test_el_filtro_sql_cubre_los_mismos_campos_que_el_predicado():
    assert "valid_until" in CURRENT_SQL_FILTER
    assert "superseded_by" in CURRENT_SQL_FILTER
