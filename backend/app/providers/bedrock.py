import json
from typing import Any

import boto3

from app.config import settings
from app.providers.base import Message, ToolSpec, ToolUse, Turn


def _client():
    return boto3.client("bedrock-runtime", region_name=settings.aws_region)


def _to_bedrock_message(message: Message) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if message.text:
        content.append({"text": message.text})
    for use in message.tool_uses:
        content.append(
            {"toolUse": {"toolUseId": use.id, "name": use.name, "input": use.args}}
        )
    for result in message.tool_results:
        content.append(
            {
                "toolResult": {
                    "toolUseId": result.id,
                    "content": [{"json": {"result": result.content}}],
                    "status": "error" if result.is_error else "success",
                }
            }
        )
    return {"role": message.role, "content": content}


class BedrockClaudeProvider:
    def __init__(self) -> None:
        self.client = _client()
        self.model_id = settings.bedrock_model_id

    def converse(
        self, system: str, messages: list[Message], tools: list[ToolSpec]
    ) -> Turn:
        response = self.client.converse(
            modelId=self.model_id,
            system=[{"text": system}],
            messages=[_to_bedrock_message(m) for m in messages],
            inferenceConfig={"maxTokens": settings.max_tokens},
            toolConfig={
                "tools": [
                    {
                        "toolSpec": {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": {"json": tool.input_schema},
                        }
                    }
                    for tool in tools
                ]
            },
        )
        turn = Turn(truncated=response.get("stopReason") == "max_tokens")
        for block in response["output"]["message"]["content"]:
            if "text" in block:
                turn.text += block["text"]
            elif "toolUse" in block:
                use = block["toolUse"]
                turn.tool_uses.append(
                    ToolUse(id=use["toolUseId"], name=use["name"], args=use["input"])
                )
        return turn


class BedrockTitanEmbedder:
    def __init__(self) -> None:
        self.client = _client()
        self.model_id = settings.bedrock_embedding_model_id

    def embed(self, text: str) -> list[float]:
        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(
                {
                    "inputText": text,
                    "dimensions": settings.embedding_dims,
                    "normalize": True,
                }
            ),
        )
        return json.loads(response["body"].read())["embedding"]
