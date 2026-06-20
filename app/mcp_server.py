"""Atlas MCP server.

Exposes the database and document search as **MCP tools** using the official MCP
SDK (FastMCP), served over SSE. The LangGraph agent connects to this server as an
MCP *client* (see ``app/agent/mcp_client.py``) and calls these tools — a real
client/server split over the wire, not in-process function calls.

Tools:
  • get_schema()                 — introspect the database
  • run_sql(sql)                 — execute a guarded, read-only query
  • search_documents(query, k)   — semantic search over documents (pgvector)
"""

from __future__ import annotations

import json
import logging

from mcp.server.fastmcp import FastMCP

from . import db

logger = logging.getLogger(__name__)

mcp = FastMCP("atlas-data-tools")


@mcp.tool()
async def get_schema() -> str:
    """Return the database schema — every table with its columns, types, primary
    keys and foreign keys. ALWAYS call this before writing SQL so you use the exact
    table and column names that exist (never guess names)."""
    schema = await db.get_schema()
    return db.render_schema_text(schema)


@mcp.tool()
async def run_sql(sql: str) -> str:
    """Execute a single READ-ONLY SQL query (only SELECT / WITH is allowed) against
    the PostgreSQL database and return the result as JSON:
    {"columns": [...], "rows": [...], "row_count": N, "truncated": bool}.

    Writes and DDL (INSERT/UPDATE/DELETE/DROP/...) are rejected, the query is run in
    a read-only transaction with a timeout, and rows are capped. If the query fails,
    this returns a string starting with "ERROR:" describing the problem — read it and
    fix the SQL, then call run_sql again."""
    try:
        result = await db.run_sql(sql)
        return json.dumps(result, default=str)
    except db.QueryError as exc:
        return f"ERROR: {exc}"


@mcp.tool()
async def search_documents(query: str, k: int = 4) -> str:
    """Semantic search over company documents (policies, FAQs, product guides,
    release notes) using pgvector. Returns a JSON list of
    {"title", "doc_type", "content", "similarity"}. Use this for qualitative
    "why / how / what is our policy on ..." questions that the structured tables
    cannot answer. ``k`` is the number of documents to return (1-10)."""
    try:
        docs = await db.search_documents(query, k)
        return json.dumps(docs, default=str)
    except Exception as exc:  # noqa: BLE001 - surface a usable error to the agent
        return f"ERROR: {exc}"


# Starlette sub-app (SSE transport) mounted by the FastAPI app at /mcp.
sse_app = mcp.sse_app()
