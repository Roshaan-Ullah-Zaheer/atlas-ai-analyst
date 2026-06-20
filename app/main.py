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

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, db
from .mcp_server import mcp

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
