"""The agent's MCP client.

The LangGraph agent does not touch the database directly — it connects to the
Atlas MCP server over SSE (the same server mounted by the FastAPI app at /mcp)
and invokes its tools. This is a real client/server boundary over the wire.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from .. import config

logger = logging.getLogger(__name__)

# The agent connects back to its own app's mounted MCP server over localhost SSE.
MCP_URL = f"http://127.0.0.1:{config.PORT}/mcp/sse"

_client: MultiServerMCPClient | None = None
_tools: dict[str, Any] | None = None


async def _get_tools() -> dict[str, Any]:
    global _client, _tools
    if _tools is None:
        _client = MultiServerMCPClient({"atlas": {"url": MCP_URL, "transport": "sse"}})
        tools = await _client.get_tools()
        _tools = {t.name: t for t in tools}
        logger.info("[mcp-client] connected, tools: %s", list(_tools))
    return _tools


def _as_text(result: Any) -> str:
    """MCP tool results come back as text or a list of content blocks."""
    if isinstance(result, str):
        return result
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return result[0].get("text", "")
    return str(result)


async def _call(name: str, args: dict[str, Any]) -> str:
    tools = await _get_tools()
    if name not in tools:
        raise RuntimeError(f"MCP tool '{name}' not available (have: {list(tools)})")
    return _as_text(await tools[name].ainvoke(args))


# --- Typed convenience wrappers used by the graph nodes ----------------------
async def get_schema() -> str:
    text = ""
    for _ in range(3):  # the schema is critical for SQL generation; retry transients
        text = await _call("get_schema", {})
        if text and not text.startswith("ERROR:"):
            return text
    return text


async def run_sql(sql: str) -> dict[str, Any]:
    raw = await _call("run_sql", {"sql": sql})
    if raw.startswith("ERROR:"):
        return {"error": raw[6:].strip()}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": f"Unparseable tool output: {raw[:200]}"}


async def search_documents(query: str, k: int = 4) -> list[dict[str, Any]]:
    raw = await _call("search_documents", {"query": query, "k": k})
    if raw.startswith("ERROR:"):
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []
