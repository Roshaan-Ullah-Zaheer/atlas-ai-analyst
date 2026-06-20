"""Provider-agnostic LLM + embeddings.

A single place that builds chat models and embedders with automatic failover:
each Gemini key (primary model -> lite fallback) is tried in turn, then Groq as
the final text fallback. Swapping to Anthropic Claude or OpenAI is a one-line
change here — the rest of the app is provider-agnostic.
"""

from __future__ import annotations

import logging

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_groq import ChatGroq

from . import config

logger = logging.getLogger(__name__)


def _chat_candidates(temperature: float, max_tokens: int) -> list:
    candidates: list = []
    for key in config.GOOGLE_API_KEYS:
        for model in (config.GEMINI_CHAT_MODEL, config.GEMINI_CHAT_FALLBACK):
            candidates.append(
                ChatGoogleGenerativeAI(
                    model=model,
                    google_api_key=key,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
            )
    if config.GROQ_API_KEY:
        candidates.append(
            ChatGroq(
                model=config.GROQ_CHAT_MODEL,
                api_key=config.GROQ_API_KEY,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
    if not candidates:
        raise RuntimeError("No LLM providers configured (set GOOGLE_API_KEYS or GROQ_API_KEY).")
    return candidates


def get_chat(temperature: float = 0.2, max_tokens: int = 2048):
    """A chat model that fails over across all Gemini keys, then Groq."""
    primary, *rest = _chat_candidates(temperature, max_tokens)
    return primary.with_fallbacks(rest) if rest else primary


def get_structured(schema, temperature: float = 0.0, max_tokens: int = 2048):
    """A chat model returning a structured (Pydantic) ``schema``, with failover.

    ``with_structured_output`` is applied per-candidate so the fallback chain
    still yields a parsed object.
    """
    wrapped = [c.with_structured_output(schema) for c in _chat_candidates(temperature, max_tokens)]
    primary, *rest = wrapped
    return primary.with_fallbacks(rest) if rest else primary


# --- Embeddings ---------------------------------------------------------------
_embedders: list[GoogleGenerativeAIEmbeddings] | None = None


def _get_embedders() -> list[GoogleGenerativeAIEmbeddings]:
    global _embedders
    if _embedders is None:
        _embedders = [
            GoogleGenerativeAIEmbeddings(
                model=config.EMBED_MODEL,
                google_api_key=key,
                output_dimensionality=config.EMBED_DIM,
            )
            for key in config.GOOGLE_API_KEYS
        ]
    return _embedders


def embed_query(text: str) -> list[float]:
    """Embed a single query string, rotating Gemini keys on failure."""
    last_error: Exception | None = None
    for embedder in _get_embedders():
        try:
            return embedder.embed_query(text)
        except Exception as exc:  # noqa: BLE001 - try the next key
            last_error = exc
            logger.warning("[embed] key failed, trying next: %s", exc)
    raise last_error or RuntimeError("No embedding provider available.")


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of documents, rotating Gemini keys on failure."""
    last_error: Exception | None = None
    for embedder in _get_embedders():
        try:
            return embedder.embed_documents(texts)
        except Exception as exc:  # noqa: BLE001 - try the next key
            last_error = exc
            logger.warning("[embed] batch key failed, trying next: %s", exc)
    raise last_error or RuntimeError("No embedding provider available.")
