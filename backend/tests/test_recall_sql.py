from app.config import settings
from app.db import to_vector_literal
from app.memory import CURRENT_SQL_FILTER, _recall_sql

EMBEDDING = [0.1234567] * settings.embedding_dims
VECTOR = to_vector_literal(EMBEDDING)

MCP_MAX_QUERY = 16384


def rendered_length(sql: str, params: list) -> int:
    return len(sql) + sum(len(str(p)) for p in params)


def test_without_service_the_query_has_no_where():
    sql, params = _recall_sql(EMBEDDING, None)

    assert "WHERE" not in sql
    assert params[-1] == settings.recall_candidates


def test_with_service_the_query_filters_in_sql():
    sql, params = _recall_sql(EMBEDDING, "software-pc")

    assert "WHERE service = %s" in sql
    assert CURRENT_SQL_FILTER in sql
    assert "software-pc" in params


def test_the_embedding_is_sent_once():
    _, params = _recall_sql(EMBEDDING, "software-pc")

    assert params.count(VECTOR) == 1


def test_the_query_fits_in_what_the_mcp_accepts():
    for service in (None, "software-pc"):
        sql, params = _recall_sql(EMBEDDING, service)

        assert rendered_length(sql, params) < MCP_MAX_QUERY
