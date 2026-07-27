import asyncio
import types

import pytest

from app.mcp import cockroach_client
from app.mcp.cockroach_client import _discover, _parse, _pick_sql_tool, _sql_arg, probe

ROWS = [{"id": 1}]


class FakeTool:
    def __init__(self, name: str, inputSchema: dict | None = None) -> None:
        self.name = name
        self.inputSchema = inputSchema


class FakeSession:
    def __init__(self) -> None:
        self.calls = 0

    async def list_tools(self):
        self.calls += 1
        return types.SimpleNamespace(
            tools=[FakeTool("execute_sql", {"properties": {"sql": {"type": "string"}}})]
        )


@pytest.fixture
def without_cache(monkeypatch):
    monkeypatch.setattr(cockroach_client, "_sql_tool", None)


@pytest.mark.parametrize(
    "payload",
    [
        ROWS,
        {"rows": ROWS},
        {"results": ROWS},
        {"result": ROWS},
        {"data": ROWS},
        {"content": ROWS},
        '{"result": [{"id": 1}]}',
        {"result": {"rows": ROWS}},
    ],
    ids=[
        "plain-list",
        "rows",
        "results",
        "result",
        "data",
        "content",
        "json-string",
        "nested-result",
    ],
)
def test_parse_recognizes_the_mcp_wrappers(payload):
    assert _parse(payload) == ROWS


def test_parse_fails_with_an_unknown_shape():
    with pytest.raises(ValueError):
        _parse({"unexpected": 1})


@pytest.mark.parametrize(
    "schema,expected",
    [
        ({"properties": {"statement": {"type": "string"}}}, "statement"),
        (
            {
                "properties": {
                    "database": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["database", "query"],
            },
            "query",
        ),
        ({"properties": {"limit": {"type": "integer"}}}, "sql"),
        (None, "sql"),
    ],
    ids=["by-property", "prefers-known-name", "no-string", "no-schema"],
)
def test_the_argument_name_comes_from_the_input_schema(schema, expected):
    assert _sql_arg(schema) == expected


def test_tool_choice_by_name():
    tools = [FakeTool("list_databases"), FakeTool("execute_sql")]
    assert _pick_sql_tool(tools).name == "execute_sql"
    assert _pick_sql_tool([FakeTool("list_databases")]) is None


def test_select_query_takes_priority():
    tools = [FakeTool("execute_sql"), FakeTool("select_query")]
    assert _pick_sql_tool(tools).name == "select_query"


def test_the_sql_tool_is_discovered_only_once(without_cache):
    session = FakeSession()

    first = asyncio.run(_discover(session))
    second = asyncio.run(_discover(session))

    assert first == second == ("execute_sql", "sql", False)
    assert session.calls == 1


def test_the_probe_does_not_leak_the_error_detail(monkeypatch):
    secret = "https://admin:hunter2@mcp.internal:8080"
    monkeypatch.setattr(cockroach_client.settings, "cockroach_mcp_url", "https://x")
    monkeypatch.setattr(cockroach_client.settings, "cockroach_mcp_api_key", "k")
    monkeypatch.setattr(
        cockroach_client, "_run", lambda sql: (_ for _ in ()).throw(RuntimeError(secret))
    )

    assert probe() == "fallback"
