import pytest

from app.mcp.cockroach_client import _parse, _pick_sql_tool, _sql_arg

FILAS = [{"id": 1}]


class FakeTool:
    def __init__(self, name: str, inputSchema: dict | None = None) -> None:
        self.name = name
        self.inputSchema = inputSchema


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
