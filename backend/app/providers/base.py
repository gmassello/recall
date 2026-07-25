from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolUse:
    id: str
    name: str
    args: dict[str, Any]
    signature: Any = None


@dataclass
class ToolResult:
    id: str
    content: Any
    is_error: bool = False


@dataclass
class Message:
    role: str
    text: str | None = None
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class Turn:
    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
    truncated: bool = False


class LLMProvider(Protocol):
    def converse(
        self, system: str, messages: list[Message], tools: list[ToolSpec]
    ) -> Turn: ...


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...
