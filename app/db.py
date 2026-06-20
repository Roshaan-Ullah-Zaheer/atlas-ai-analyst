"""Async PostgreSQL access (Neon) + pgvector.

Exposes the three capabilities the MCP server turns into tools:
  • get_schema()        — introspect the database for schema-aware prompting
  • run_sql(sql)        — execute a *read-only*, time-boxed, row-capped query
  • search_documents()  — semantic search over documents via pgvector

run_sql is guarded several ways: only SELECT/WITH is allowed, a forbidden-keyword
check blocks writes/DDL, the query runs in a READ ONLY transaction with a
statement timeout, and results are capped. This is the safety net beneath the
agent's human-in-the-loop approval.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import numpy as np
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from . import config, llm

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None


async def _configure(conn) -> None:
    await register_vector_async(conn)


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        pool = AsyncConnectionPool(
            conninfo=config.DATABASE_URL,
            min_size=1,
            max_size=5,
            open=False,
            configure=_configure,
            timeout=30,
        )
        await pool.open(wait=True)
        _pool = pool
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Read-only guardrail
# ---------------------------------------------------------------------------
class QueryError(Exception):
    """Raised when a query is rejected by the guardrail or fails to execute."""


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"merge|copy|vacuum|reindex|call|do|comment|lock|set|reset)\b",
    re.IGNORECASE,
)


def check_read_only(sql: str) -> tuple[bool, str]:
    """Return (ok, reason). Only single SELECT/WITH statements are allowed."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return False, "Empty query."
    if ";" in stripped:
        return False, "Only a single statement is allowed."
    head = stripped.lstrip("(").lower()
    if not (head.startswith("select") or head.startswith("with")):
        return False, "Only SELECT / WITH (read-only) queries are allowed."
    if _FORBIDDEN.search(stripped):
        return False, "Query contains a forbidden write/DDL keyword."
    return True, ""


async def run_sql(sql: str) -> dict[str, Any]:
    """Execute a guarded, read-only query. Returns columns, rows, and metadata."""
    ok, reason = check_read_only(sql)
    if not ok:
        raise QueryError(reason)

    pool = await get_pool()
    try:
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(f"SET LOCAL statement_timeout = {int(config.STATEMENT_TIMEOUT_MS)}")
                await cur.execute("SET LOCAL transaction_read_only = on")
                await cur.execute(sql)
                rows = await cur.fetchmany(config.MAX_RESULT_ROWS + 1)
                columns = [c.name for c in cur.description] if cur.description else []
            await conn.rollback()
    except Exception as exc:  # noqa: BLE001 - surface a clean message to the agent
        raise QueryError(str(exc).strip()) from exc

    truncated = len(rows) > config.MAX_RESULT_ROWS
    rows = rows[: config.MAX_RESULT_ROWS]
    # JSON-friendly rows (dates/decimals -> str/float)
    clean = [{k: _jsonable(v) for k, v in row.items()} for row in rows]
    return {"columns": columns, "rows": clean, "row_count": len(clean), "truncated": truncated}


def _jsonable(value: Any) -> Any:
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


# ---------------------------------------------------------------------------
# Semantic document search (pgvector)
# ---------------------------------------------------------------------------
async def search_documents(query: str, k: int = 4) -> list[dict[str, Any]]:
    """Embed the query and return the k most similar documents (cosine)."""
    k = max(1, min(int(k), 10))
    # numpy float32 array so the pgvector adapter sends it as a `vector` (not float8[]).
    embedding = np.asarray(llm.embed_query(query), dtype=np.float32)
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, title, doc_type, content, "
                "1 - (embedding <=> %s) AS similarity "
                "FROM documents ORDER BY embedding <=> %s LIMIT %s",
                (embedding, embedding, k),
            )
            rows = await cur.fetchall()
        await conn.rollback()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "doc_type": r["doc_type"],
            "content": r["content"],
            "similarity": round(float(r["similarity"]), 4),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------
async def get_schema() -> dict[str, Any]:
    """Introspect public tables -> {tables: [{name, columns:[{name,type,pk,fk}]}]}."""
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT c.table_name, c.column_name, c.data_type, c.ordinal_position
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                ORDER BY c.table_name, c.ordinal_position
                """
            )
            cols = await cur.fetchall()

            await cur.execute(
                """
                SELECT tc.table_name, kcu.column_name, tc.constraint_type,
                       ccu.table_name AS foreign_table
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                LEFT JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name AND tc.constraint_type = 'FOREIGN KEY'
                WHERE tc.table_schema = 'public'
                  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
                """
            )
            keys = await cur.fetchall()
        await conn.rollback()

    pk: set[tuple[str, str]] = set()
    fk: dict[tuple[str, str], str] = {}
    for k in keys:
        ref = (k["table_name"], k["column_name"])
        if k["constraint_type"] == "PRIMARY KEY":
            pk.add(ref)
        elif k["constraint_type"] == "FOREIGN KEY":
            fk[ref] = k["foreign_table"]

    tables: dict[str, dict[str, Any]] = {}
    for col in cols:
        t = tables.setdefault(col["table_name"], {"name": col["table_name"], "columns": []})
        ref = (col["table_name"], col["column_name"])
        t["columns"].append(
            {
                "name": col["column_name"],
                "type": col["data_type"],
                "pk": ref in pk,
                "fk": fk.get(ref),
            }
        )
    return {"tables": list(tables.values())}


def render_schema_text(schema: dict[str, Any]) -> str:
    """Compact text rendering of the schema for prompts."""
    lines: list[str] = []
    for table in schema["tables"]:
        parts = []
        for col in table["columns"]:
            tag = ""
            if col["pk"]:
                tag = " PK"
            elif col["fk"]:
                tag = f" FK->{col['fk']}"
            parts.append(f"{col['name']} {col['type']}{tag}")
        lines.append(f"{table['name']}({', '.join(parts)})")
    return "\n".join(lines)
