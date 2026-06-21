"""Atlas FastAPI application.

Serves the agent (SSE), mounts the MCP server, and exposes a couple of helper
endpoints (schema, health). The LangGraph agent connects back to the mounted MCP
server as an MCP client.
"""

from __future__ import annotations

import asyncio
import sys

# psycopg's async mode is incompatible with Windows' default ProactorEventLoop;
# use the selector loop locally. No-op on Linux (the deploy target).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from sse_starlette.sse import EventSourceResponse

from . import config, db, llm
from .agent import prompts
from .agent.graph import graph
from .mcp_server import mcp
from .schemas import SampleQuestions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("atlas")

app = FastAPI(title="Atlas — Multi-Agent AI Analyst", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the MCP server (SSE transport) at /mcp -> SSE endpoint is /mcp/sse.
app.mount("/mcp", mcp.sse_app())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "missing_config": config.missing_keys()}


@app.get("/api/schema")
async def api_schema() -> JSONResponse:
    """The database schema, for the frontend's schema explorer."""
    return JSONResponse(await db.get_schema())


# Starter questions, generated once from the live schema and cached for the
# container's lifetime (one LLM call, not one per visit). Falls back to a
# curated set if generation fails.
_samples_cache: list[str] | None = None

FALLBACK_SAMPLES = [
    "Total revenue by customer segment from completed orders",
    "Top 10 products by revenue, with their category",
    "Which sales reps generated the most revenue?",
    "What is our refund policy and how long do refunds take?",
    "Show me the email addresses of customers who churned",
]


@app.get("/api/samples")
async def api_samples() -> JSONResponse:
    """LLM-generated starter questions tailored to the live schema (cached)."""
    global _samples_cache
    if _samples_cache:
        return JSONResponse({"questions": _samples_cache, "generated": True})
    try:
        schema_text = db.render_schema_text(await db.get_schema())
        result: SampleQuestions = await llm.get_structured(SampleQuestions).ainvoke(
            [
                ("system", prompts.SAMPLES_SYSTEM),
                ("human", f"Schema:\n{schema_text}\n\nGenerate the 5 starter questions."),
            ]
        )
        qs = [q.strip() for q in result.questions if q and q.strip()][:5]
        if len(qs) >= 3:
            _samples_cache = qs
            return JSONResponse({"questions": qs, "generated": True})
    except Exception:  # noqa: BLE001 - degrade gracefully to the curated set
        logger.exception("sample question generation failed")
    return JSONResponse({"questions": FALLBACK_SAMPLES, "generated": False})


def _events_from_update(node: str, update: dict) -> list[dict]:
    """Map a LangGraph node update to UI-facing SSE events."""
    update = update or {}
    if node == "plan":
        plan = update.get("plan", {})
        return [{"type": "plan", "intent": plan.get("intent"), "route": update.get("route"), "steps": plan.get("steps", [])}]
    if node == "generate_sql":
        return [{"type": "sql", "sql": update.get("sql"), "rationale": update.get("sql_rationale"), "attempt": update.get("sql_attempts")}]
    if node == "approval":
        if update.get("needs_approval") is False:
            return [{"type": "approved", "auto": True}]
        return [{"type": "approved", "auto": False, "approved": update.get("approved")}]
    if node == "execute_sql":
        r = update.get("result", {})
        if "error" in r:
            return [{"type": "result_error", "error": r["error"]}]
        return [{"type": "result", "columns": r.get("columns"), "rows": r.get("rows"), "row_count": r.get("row_count"), "truncated": r.get("truncated")}]
    if node == "validate":
        rv = update.get("review", {})
        return [{"type": "review", "answers_question": rv.get("answers_question"), "issue": rv.get("issue")}]
    if node == "search_docs":
        return [{"type": "sources", "docs": update.get("docs", [])}]
    if node == "visualize":
        return [{"type": "chart", "spec": update.get("chart", {})}]
    if node == "answer":
        return [{"type": "answer", "text": update.get("answer", "")}]
    return []


async def _agent_sse(inp, thread_id: str):
    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        async for chunk in graph.astream(inp, cfg, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__":
                    payload = (update[0].value if isinstance(update, (list, tuple)) else update.value) or {}
                    yield {"data": json.dumps({"type": "approval_required", "sql": payload.get("sql"), "reason": payload.get("reason"), "thread_id": thread_id})}
                    return
                for event in _events_from_update(node, update):
                    yield {"data": json.dumps(event, default=str)}
        yield {"data": json.dumps({"type": "done"})}
    except Exception as exc:  # noqa: BLE001 - surface to the client
        logger.exception("agent stream failed")
        yield {"data": json.dumps({"type": "error", "message": str(exc)})}


@app.get("/api/ask")
async def ask(question: str, thread_id: str):
    """Stream the agent's run for a question as SSE."""
    return EventSourceResponse(_agent_sse({"question": (question or "").strip()}, thread_id))


@app.get("/api/resume")
async def resume(thread_id: str, approved: bool = False):
    """Resume a run that paused for human approval."""
    return EventSourceResponse(_agent_sse(Command(resume={"approved": approved}), thread_id))


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await db.close_pool()


if __name__ == "__main__":
    import uvicorn

    # Run uvicorn on the (selector) loop we set above; loop="none" tells uvicorn
    # to use the current loop rather than creating a ProactorEventLoop on Windows.
    server = uvicorn.Server(
        uvicorn.Config(app, host="0.0.0.0", port=config.PORT, loop="none", log_level="info")
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())
