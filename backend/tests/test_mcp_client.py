import asyncio
import types

import pytest

from app.mcp import cockroach_client
from app.mcp.cockroach_client import _discover, _parse, _pick_sql_tool, _sql_arg, probe

FILAS = [{"id": 1}]


class FakeTool:
    def __init__(self, name: str, inputSchema: dict | None = None) -> None:
        self.name = name
        self.inputSchema = inputSchema


class FakeSession:
    def __init__(self) -> None:
        self.llamadas = 0

    async def list_tools(self):
        self.llamadas += 1
        return types.SimpleNamespace(
            tools=[FakeTool("execute_sql", {"properties": {"sql": {"type": "string"}}})]
        )


@pytest.fixture
def sin_cache(monkeypatch):
    monkeypatch.setattr(cockroach_client, "_sql_tool", None)


@pytest.mark.parametrize(
    "payload",
    [
        FILAS,
        {"rows": FILAS},
        {"results": FILAS},
        {"result": FILAS},
        {"data": FILAS},
        {"content": FILAS},
        '{"result": [{"id": 1}]}',
        {"result": {"rows": FILAS}},
    ],
    ids=[
        "lista-directa",
        "rows",
        "results",
        "result",
        "data",
        "content",
        "string-json",
        "result-anidado",
    ],
)
def test_parse_reconoce_los_envoltorios_del_mcp(payload):
    assert _parse(payload) == FILAS


def test_parse_falla_con_forma_desconocida():
    with pytest.raises(ValueError):
        _parse({"inesperado": 1})


@pytest.mark.parametrize(
    "schema,esperado",
    [
        ({"properties": {"statement": {"type": "string"}}}, "statement"),
        (
            {
                "properties": {"db": {"type": "string"}, "q": {"type": "string"}},
                "required": ["q"],
            },
            "q",
        ),
        ({"properties": {"limite": {"type": "integer"}}}, "sql"),
        (None, "sql"),
    ],
    ids=["por-propiedad", "prioriza-required", "sin-string", "sin-schema"],
)
def test_nombre_del_argumento_sale_del_input_schema(schema, esperado):
    assert _sql_arg(schema) == esperado


def test_eleccion_de_tool_por_nombre():
    tools = [FakeTool("list_databases"), FakeTool("execute_sql")]
    assert _pick_sql_tool(tools).name == "execute_sql"
    assert _pick_sql_tool([FakeTool("list_databases")]) is None


def test_la_tool_sql_se_descubre_una_sola_vez(sin_cache):
    session = FakeSession()

    primera = asyncio.run(_discover(session))
    segunda = asyncio.run(_discover(session))

    assert primera == segunda == ("execute_sql", "sql")
    assert session.llamadas == 1


def test_el_probe_no_filtra_el_detalle_del_error(monkeypatch):
    secreto = "https://admin:hunter2@mcp.interno:8080"
    monkeypatch.setattr(cockroach_client.settings, "cockroach_mcp_url", "https://x")
    monkeypatch.setattr(cockroach_client.settings, "cockroach_mcp_api_key", "k")
    monkeypatch.setattr(
        cockroach_client, "_run", lambda sql: (_ for _ in ()).throw(RuntimeError(secreto))
    )

    assert probe() == "fallback"
