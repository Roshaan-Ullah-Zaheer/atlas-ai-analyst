"""Application configuration.

Loads environment variables from ``.env.local`` (falling back to the default
``.env`` discovery) and exposes the settings the agent, MCP server, and data
layer need. LangChain/LangSmith read ``LANGCHAIN_*`` directly from the env.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv()


def _split(raw: str | None) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


# Database (Neon · PostgreSQL + pgvector)
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# LLM (provider-agnostic: Gemini -> Groq)
GOOGLE_API_KEYS: list[str] = _split(os.getenv("GOOGLE_API_KEYS"))
GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY") or None

# App
ALLOWED_ORIGINS: list[str] = _split(os.getenv("ALLOWED_ORIGINS")) or ["*"]
PORT: int = int(os.getenv("PORT", "7860"))

# Models (swap these for Claude/OpenAI in production — provider-agnostic)
GEMINI_CHAT_MODEL: str = "gemini-2.5-flash"
GEMINI_CHAT_FALLBACK: str = "gemini-2.5-flash-lite"
GROQ_CHAT_MODEL: str = "llama-3.3-70b-versatile"
EMBED_MODEL: str = "models/gemini-embedding-001"
EMBED_DIM: int = 768

# Guardrails
MAX_RESULT_ROWS: int = 1000          # hard cap on rows returned by run_sql
STATEMENT_TIMEOUT_MS: int = 15000    # per-query timeout


def missing_keys() -> list[str]:
    """Names of required credentials that are not configured."""
    missing: list[str] = []
    if not DATABASE_URL:
        missing.append("DATABASE_URL")
    if not GOOGLE_API_KEYS and not GROQ_API_KEY:
        missing.append("GOOGLE_API_KEYS_or_GROQ_API_KEY")
    return missing
