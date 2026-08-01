import asyncio
import json
import logging
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)

_sql_tool: tuple[str, str, bool] | None = None


def is_configured() -> bool:
    return bool(settings.cockroach_mcp_url and settings.cockroach_mcp_api_key)


def _pick_sql_tool(tools: list) -> Any:
    for tool in tools:
        if tool.name == "select_query":
            return tool
    for tool in tools:
        if "sql" in tool.name.lower() or "quer" in tool.name.lower():
            return tool
    return None


def _sql_arg(schema: dict | None) -> str:
    properties = (schema or {}).get("properties", {})
    for name in ("query", "sql", "statement"):
        if name in properties:
            return name
    for name in properties:
        if properties[name].get("type") == "string":
            return name
    return "sql"


def _database_name() -> str:
    from urllib.parse import urlparse

    return urlparse(settings.database_url).path.lstrip("/") or "defaultdb"


def _parse(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "results", "result", "data", "content"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, (dict, str)):
                return _parse(value)
    if isinstance(payload, str):
        return _parse(json.loads(payload))
    raise ValueError("MCP response without recognizable rows")


async def _discover(session) -> tuple[str, str, bool]:
    global _sql_tool
    if _sql_tool is None:
        tools = await session.list_tools()
        tool = _pick_sql_tool(tools.tools)
        if tool is None:
            names = ", ".join(t.name for t in tools.tools) or "(none)"
            raise ValueError(
                f"The MCP Server does not expose a SQL tool. It exposes: {names}"
            )
        schema = getattr(tool, "inputSchema", None) or {}
        needs_db = "database" in schema.get("properties", {})
        _sql_tool = (tool.name, _sql_arg(schema), needs_db)
    return _sql_tool


async def _call(sql: str) -> list[dict]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": f"Bearer {settings.cockroach_mcp_api_key}"}
    if settings.cockroach_mcp_cluster_id:
        headers["mcp-cluster-id"] = settings.cockroach_mcp_cluster_id
    async with streamablehttp_client(settings.cockroach_mcp_url, headers=headers) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            name, arg, needs_db = await _discover(session)
            args = {arg: sql}
            if needs_db:
                args["database"] = _database_name()
            result = await session.call_tool(name, args)
            if result.isError:
                raise ValueError(f"The MCP returned an error for: {sql[:120]}")
            if result.structuredContent is not None:
                return _parse(result.structuredContent)
            texts = [c.text for c in result.content if getattr(c, "text", None)]
            return _parse("\n".join(texts))


def _run(sql: str) -> list[dict]:
    return asyncio.run(asyncio.wait_for(_call(sql), timeout=15))


def run_sql(sql: str) -> list[dict] | None:
    try:
        return _run(sql)
    except Exception as exc:
        log.error("MCP configured but not responding, falling back to psycopg: %s", exc)
        return None


def probe() -> str:
    if not is_configured():
        return "not configured"
    try:
        _run("SELECT 1")
        return "ok"
    except Exception as exc:
        log.warning("The MCP probe failed, falling back to psycopg: %s", exc)
        return "fallback"
