from app.config import settings
from app.memory import CURRENT_SQL_FILTER, DISTANCE_OP, VECTOR_CAST, _recall_sql

EMBEDDING = [0.1]

INDEXABLE_ORDER = f"ORDER BY embedding {DISTANCE_OP} %s{VECTOR_CAST}"


def test_without_service_the_query_has_no_where():
    sql, params = _recall_sql(EMBEDDING, None)

    assert "WHERE" not in sql
    assert INDEXABLE_ORDER in sql
    assert params[-1] == settings.recall_candidates


def test_with_service_the_query_filters_in_sql():
    sql, params = _recall_sql(EMBEDDING, "payments-api")

    assert "WHERE service = %s" in sql
    assert CURRENT_SQL_FILTER in sql
    assert "payments-api" in params
    assert INDEXABLE_ORDER in sql
