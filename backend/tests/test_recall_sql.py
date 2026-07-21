from app.config import settings
from app.memory import CURRENT_SQL_FILTER, DISTANCE_OP, VECTOR_CAST, _recall_sql

EMBEDDING = [0.1]

ORDEN_ACELERABLE = f"ORDER BY embedding {DISTANCE_OP} %s{VECTOR_CAST}"


def test_sin_servicio_la_query_no_lleva_where():
    sql, params = _recall_sql(EMBEDDING, None)

    assert "WHERE" not in sql
    assert ORDEN_ACELERABLE in sql
    assert params[-1] == settings.recall_candidates


def test_con_servicio_la_query_filtra_en_sql():
    sql, params = _recall_sql(EMBEDDING, "payments-api")

    assert "WHERE service = %s" in sql
    assert CURRENT_SQL_FILTER in sql
    assert "payments-api" in params
    assert ORDEN_ACELERABLE in sql
