import pytest

from app.config import settings
from app.providers import bedrock
from app.providers.base import Message, ToolSpec

TOOLS = [ToolSpec(name="search_memory", description="searches", input_schema={})]

MESSAGES = [Message(role="user", text="hello")]


class FakeClient:
    def __init__(self, stop_reason: str) -> None:
        self.stop_reason = stop_reason
        self.kwargs: dict = {}

    def converse(self, **kwargs):
        self.kwargs = kwargs
        return {
            "stopReason": self.stop_reason,
            "output": {"message": {"content": [{"text": "done"}]}},
        }


@pytest.fixture
def client(monkeypatch):
    def build(stop_reason: str = "tool_use") -> FakeClient:
        fake = FakeClient(stop_reason)
        monkeypatch.setattr(bedrock, "_client", lambda: fake)
        return fake

    return build


def test_converse_caps_the_output_tokens(client):
    fake = client()

    bedrock.BedrockClaudeProvider().converse("system", MESSAGES, TOOLS)

    assert fake.kwargs["inferenceConfig"] == {"maxTokens": settings.max_tokens}


@pytest.mark.parametrize(
    "stop_reason,expected",
    [("max_tokens", True), ("tool_use", False), ("end_turn", False)],
)
def test_the_turn_reports_truncation(client, stop_reason, expected):
    client(stop_reason)

    turn = bedrock.BedrockClaudeProvider().converse("system", MESSAGES, TOOLS)

    assert turn.truncated is expected
