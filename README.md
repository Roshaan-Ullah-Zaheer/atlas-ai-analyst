<div align="center">

# 🧭 Atlas — Multi-Agent AI Analyst

**Ask your business data anything in plain English. A team of agents plans, queries a SQL + vector database through an MCP server, validates and self-corrects, then writes a clear, charted, fully-sourced answer — pausing for your approval before anything sensitive.**

</div>

---

## ✨ What it does

Atlas is "chat with your database + documents," built the way an enterprise actually wants it: a real multi-agent system you can watch think.

- 🧭 **Plans** the question and routes it (structured SQL vs. semantic document search vs. both).
- 🛠️ **Calls tools through a custom MCP server** (`run_sql`, `search_documents`, `get_schema`) — the agent is the MCP client.
- 🧮 **Queries PostgreSQL + pgvector** for both exact analytics and semantic search over documents.
- ✅ **Validates & self-corrects** — a bad query is inspected against the schema, fixed, and retried automatically.
- ✋ **Pauses for human approval** before anything sensitive or expensive (LangGraph interrupt).
- 📊 **Visualizes** — picks the right chart for the result.
- 🔍 **Stays a glass box** — shows the generated SQL, rows, validation, and a LangSmith trace for every answer.

## 🧱 Tech

LangGraph (multi-agent orchestration, conditional routing, self-correction, human-in-the-loop) · custom **MCP server + client** (SSE) · **PostgreSQL + pgvector** · **Pydantic** structured outputs · **LangSmith** tracing · provider-agnostic LLM (**Gemini → Groq**, swappable to Claude / OpenAI).

> **Provider-agnostic by design** — free tiers are used so the public demo costs nothing; the *identical* architecture runs on Anthropic Claude / OpenAI and managed pgvector in production.

## 🎯 Skills demonstrated

_(architecture diagram, screenshots, live demo link, and setup guide added as the build progresses)_

---

_MIT licensed._
