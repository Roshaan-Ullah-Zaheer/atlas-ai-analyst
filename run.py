"""Local / preview launcher.

Uses a selector event loop on Windows (psycopg's async mode is incompatible with
the default ProactorEventLoop) and runs uvicorn on it. On Linux this is a normal
uvicorn launch. The Docker image runs ``uvicorn app.main:app`` directly.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn  # noqa: E402

from app import config  # noqa: E402

if __name__ == "__main__":
    server = uvicorn.Server(
        uvicorn.Config("app.main:app", host="127.0.0.1", port=config.PORT, loop="none", log_level="warning")
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())
