import json

from app.providers.anthropic_provider import _to_anthropic_message
from app.providers.bedrock import _to_bedrock_message
from app.providers.base import Message, ToolResult

FILAS = [{"id": "i1", "title": "Pool agotado", "score": 0.31, "root_cause": None}]


def _bloque_tool_result(content):
    message = Message(role="user", tool_results=[ToolResult(id="u1", content=content)])
    return _to_anthropic_message(message)["content"][0]


def test_el_tool_result_viaja_como_json_y_no_como_repr_de_python():
    bloque = _bloque_tool_result(FILAS)

    assert json.loads(bloque["content"]) == FILAS
    assert "'" not in bloque["content"]
    assert "None" not in bloque["content"]


def test_un_content_string_pasa_sin_tocar():
    assert _bloque_tool_result("ya es texto")["content"] == "ya es texto"


def test_los_tool_results_van_antes_del_texto():
    message = Message(
        role="user",
        text="un texto",
        tool_results=[ToolResult(id="u1", content=FILAS)],
    )
    tipos = [bloque["type"] for bloque in _to_anthropic_message(message)["content"]]

    assert tipos.index("tool_result") < tipos.index("text")


def test_el_error_viaja_marcado_en_anthropic():
    message = Message(role="user", tool_results=[ToolResult(id="u1", content={}, is_error=True)])
    bloque = _to_anthropic_message(message)["content"][0]

    assert bloque["is_error"] is True


def test_el_error_viaja_como_status_en_bedrock():
    ok = ToolResult(id="u1", content={})
    falla = ToolResult(id="u2", content={}, is_error=True)
    message = Message(role="user", tool_results=[ok, falla])

    estados = [
        bloque["toolResult"]["status"]
        for bloque in _to_bedrock_message(message)["content"]
    ]

    assert estados == ["success", "error"]
