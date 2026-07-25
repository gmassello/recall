import types as pytypes

import pytest
from google.genai import types

from app.providers import gemini_provider
from app.providers.gemini_provider import (
    GeminiEmbedder,
    GeminiProvider,
    _clean_schema,
    _to_gemini_content,
)
from app.providers.base import Message, ToolResult, ToolUse

FILAS = [{"id": "i1", "title": "Pool agotado", "score": 0.31}]


def test_el_rol_assistant_se_mapea_a_model_y_el_texto_precede_al_function_call():
    message = Message(
        role="assistant",
        text="reviso la memoria",
        tool_uses=[ToolUse(id="search_memory", name="search_memory", args={"symptom": "x"})],
    )
    content = _to_gemini_content(message, {})

    assert content.role == "model"
    assert content.parts[0].text == "reviso la memoria"
    assert content.parts[1].function_call.name == "search_memory"


def test_el_tool_result_viaja_como_function_response_con_el_nombre_resuelto():
    previos = [
        Message(
            role="assistant",
            tool_uses=[ToolUse(id="u1", name="search_memory", args={})],
        )
    ]
    names = gemini_provider._name_by_id(previos)
    message = Message(role="user", tool_results=[ToolResult(id="u1", content=FILAS)])

    part = _to_gemini_content(message, names).parts[0]

    assert part.function_response.name == "search_memory"
    assert part.function_response.response == {"result": FILAS}


def test_clean_schema_saca_default_y_pone_el_type_en_mayuscula():
    schema = {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}}

    cleaned = _clean_schema(schema)

    assert cleaned["type"] == "OBJECT"
    assert cleaned["properties"]["limit"]["type"] == "INTEGER"
    assert "default" not in cleaned["properties"]["limit"]


@pytest.mark.parametrize(
    "finish_reason,esperado",
    [(types.FinishReason.MAX_TOKENS, True), (types.FinishReason.STOP, False)],
)
def test_reporta_el_truncado_desde_el_finish_reason(monkeypatch, finish_reason, esperado):
    part = pytypes.SimpleNamespace(text="hola", function_call=None)
    candidate = pytypes.SimpleNamespace(
        finish_reason=finish_reason,
        content=pytypes.SimpleNamespace(parts=[part]),
    )
    respuesta = pytypes.SimpleNamespace(candidates=[candidate])
    cliente = pytypes.SimpleNamespace(
        models=pytypes.SimpleNamespace(generate_content=lambda **kw: respuesta)
    )
    monkeypatch.setattr(gemini_provider.settings, "gemini_api_key", "k")
    monkeypatch.setattr(gemini_provider.genai, "Client", lambda **kw: cliente)

    turn = GeminiProvider().converse("system", [Message(role="user", text="x")], [])

    assert turn.truncated is esperado
    assert turn.text == "hola"


def test_el_embedding_sale_normalizado(monkeypatch):
    respuesta = pytypes.SimpleNamespace(
        embeddings=[pytypes.SimpleNamespace(values=[3.0, 4.0])]
    )
    cliente = pytypes.SimpleNamespace(
        models=pytypes.SimpleNamespace(embed_content=lambda **kw: respuesta)
    )
    monkeypatch.setattr(gemini_provider.settings, "gemini_api_key", "k")
    monkeypatch.setattr(gemini_provider.genai, "Client", lambda **kw: cliente)

    vector = GeminiEmbedder().embed("un sintoma")

    assert vector == [0.6, 0.8]
