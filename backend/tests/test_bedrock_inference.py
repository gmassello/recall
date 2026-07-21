import pytest

from app.config import settings
from app.providers import bedrock
from app.providers.base import Message, ToolSpec

TOOLS = [ToolSpec(name="search_memory", description="busca", input_schema={})]

MENSAJES = [Message(role="user", text="hola")]


class FakeClient:
    def __init__(self, stop_reason: str) -> None:
        self.stop_reason = stop_reason
        self.kwargs: dict = {}

    def converse(self, **kwargs):
        self.kwargs = kwargs
        return {
            "stopReason": self.stop_reason,
            "output": {"message": {"content": [{"text": "listo"}]}},
        }


@pytest.fixture
def cliente(monkeypatch):
    def build(stop_reason: str = "tool_use") -> FakeClient:
        fake = FakeClient(stop_reason)
        monkeypatch.setattr(bedrock, "_client", lambda: fake)
        return fake

    return build


def test_converse_acota_los_tokens_de_salida(cliente):
    fake = cliente()

    bedrock.BedrockClaudeProvider().converse("system", MENSAJES, TOOLS)

    assert fake.kwargs["inferenceConfig"] == {"maxTokens": settings.max_tokens}


@pytest.mark.parametrize(
    "stop_reason,esperado",
    [("max_tokens", True), ("tool_use", False), ("end_turn", False)],
)
def test_el_truncado_viaja_en_el_turno(cliente, stop_reason, esperado):
    cliente(stop_reason)

    turn = bedrock.BedrockClaudeProvider().converse("system", MENSAJES, TOOLS)

    assert turn.truncated is esperado
