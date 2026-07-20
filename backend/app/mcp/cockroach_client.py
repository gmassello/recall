import asyncio
import json
import logging
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.cockroach_mcp_url and settings.cockroach_mcp_api_key)


def _pick_sql_tool(names: list[str]) -> str | None:
    for name in names:
        if "sql" in name.lower() or "quer" in name.lower():
            return name
    return None


def _parse(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "results", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
    if isinstance(payload, str):
        return _parse(json.loads(payload))
    raise ValueError("Respuesta del MCP sin filas reconocibles")


async def _call(sql: str) -> list[dict]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": f"Bearer {settings.cockroach_mcp_api_key}"}
    async with streamablehttp_client(settings.cockroach_mcp_url, headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_name = _pick_sql_tool([t.name for t in tools.tools])
            if tool_name is None:
                raise ValueError("El MCP Server no expone una herramienta SQL")
            result = await session.call_tool(tool_name, {"sql": sql})
            if result.isError:
                raise ValueError(f"El MCP devolvio error para: {sql[:120]}")
            if result.structuredContent is not None:
                return _parse(result.structuredContent)
            texts = [c.text for c in result.content if getattr(c, "text", None)]
            return _parse("\n".join(texts))


def run_sql(sql: str) -> list[dict] | None:
    try:
        return asyncio.run(asyncio.wait_for(_call(sql), timeout=15))
    except Exception as exc:
        log.warning("MCP no disponible, se usa conexion directa: %s", exc)
        return None
