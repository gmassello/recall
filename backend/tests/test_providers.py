import json
import types

import pytest

from app.providers import anthropic_provider
from app.providers.anthropic_provider import AnthropicProvider, _to_anthropic_message
from app.providers.bedrock import _to_bedrock_message
from app.providers.base import Message, ToolResult

ROWS = [{"id": "i1", "title": "Pool exhausted", "score": 0.31, "root_cause": None}]


def _tool_result_block(content):
    message = Message(role="user", tool_results=[ToolResult(id="u1", content=content)])
    return _to_anthropic_message(message)["content"][0]


def test_the_tool_result_is_serialized_as_json_not_a_python_repr():
    block = _tool_result_block(ROWS)

    assert json.loads(block["content"]) == ROWS
    assert "'" not in block["content"]
    assert "None" not in block["content"]


def test_a_string_content_passes_through_untouched():
    assert _tool_result_block("already text")["content"] == "already text"


def test_the_tool_results_come_before_the_text():
    message = Message(
        role="user",
        text="some text",
        tool_results=[ToolResult(id="u1", content=ROWS)],
    )
    types_ = [block["type"] for block in _to_anthropic_message(message)["content"]]

    assert types_.index("tool_result") < types_.index("text")


def test_anthropic_marks_the_error_result():
    message = Message(role="user", tool_results=[ToolResult(id="u1", content={}, is_error=True)])
    block = _to_anthropic_message(message)["content"][0]

    assert block["is_error"] is True


@pytest.mark.parametrize(
    "stop_reason,expected",
    [("max_tokens", True), ("tool_use", False)],
)
def test_anthropic_also_reports_truncation_in_the_turn(
    monkeypatch, stop_reason, expected
):
    response = types.SimpleNamespace(stop_reason=stop_reason, content=[])
    client = types.SimpleNamespace(
        messages=types.SimpleNamespace(create=lambda **kw: response)
    )
    monkeypatch.setattr(anthropic_provider.settings, "anthropic_api_key", "k")
    monkeypatch.setattr(anthropic_provider.anthropic, "Anthropic", lambda **kw: client)

    turn = AnthropicProvider().converse("system", [Message(role="user", text="x")], [])

    assert turn.truncated is expected


def test_bedrock_marks_the_error_result_as_a_status():
    ok = ToolResult(id="u1", content={})
    failure = ToolResult(id="u2", content={}, is_error=True)
    message = Message(role="user", tool_results=[ok, failure])

    statuses = [
        block["toolResult"]["status"]
        for block in _to_bedrock_message(message)["content"]
    ]

    assert statuses == ["success", "error"]
