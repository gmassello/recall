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

ROWS = [{"id": "i1", "title": "Pool exhausted", "score": 0.31}]


def test_the_assistant_role_maps_to_model_and_text_precedes_the_function_call():
    message = Message(
        role="assistant",
        text="checking memory",
        tool_uses=[ToolUse(id="search_memory", name="search_memory", args={"symptom": "x"})],
    )
    content = _to_gemini_content(message, {})

    assert content.role == "model"
    assert content.parts[0].text == "checking memory"
    assert content.parts[1].function_call.name == "search_memory"


def test_the_tool_result_becomes_a_function_response_with_the_resolved_name():
    previous = [
        Message(
            role="assistant",
            tool_uses=[ToolUse(id="u1", name="search_memory", args={})],
        )
    ]
    names = gemini_provider._name_by_id(previous)
    message = Message(role="user", tool_results=[ToolResult(id="u1", content=ROWS)])

    part = _to_gemini_content(message, names).parts[0]

    assert part.function_response.name == "search_memory"
    assert part.function_response.response == {"result": ROWS}


def test_clean_schema_drops_default_and_uppercases_the_type():
    schema = {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}}

    cleaned = _clean_schema(schema)

    assert cleaned["type"] == "OBJECT"
    assert cleaned["properties"]["limit"]["type"] == "INTEGER"
    assert "default" not in cleaned["properties"]["limit"]


@pytest.mark.parametrize(
    "finish_reason,expected",
    [(types.FinishReason.MAX_TOKENS, True), (types.FinishReason.STOP, False)],
)
def test_reports_truncation_from_the_finish_reason(monkeypatch, finish_reason, expected):
    part = pytypes.SimpleNamespace(text="hello", function_call=None)
    candidate = pytypes.SimpleNamespace(
        finish_reason=finish_reason,
        content=pytypes.SimpleNamespace(parts=[part]),
    )
    response = pytypes.SimpleNamespace(candidates=[candidate])
    client = pytypes.SimpleNamespace(
        models=pytypes.SimpleNamespace(generate_content=lambda **kw: response)
    )
    monkeypatch.setattr(gemini_provider.settings, "gemini_api_key", "k")
    monkeypatch.setattr(gemini_provider.genai, "Client", lambda **kw: client)

    turn = GeminiProvider().converse("system", [Message(role="user", text="x")], [])

    assert turn.truncated is expected
    assert turn.text == "hello"


def test_the_embedding_comes_out_normalized(monkeypatch):
    response = pytypes.SimpleNamespace(
        embeddings=[pytypes.SimpleNamespace(values=[3.0, 4.0])]
    )
    client = pytypes.SimpleNamespace(
        models=pytypes.SimpleNamespace(embed_content=lambda **kw: response)
    )
    monkeypatch.setattr(gemini_provider.settings, "gemini_api_key", "k")
    monkeypatch.setattr(gemini_provider.genai, "Client", lambda **kw: client)

    vector = GeminiEmbedder().embed("a symptom")

    assert vector == [0.6, 0.8]
