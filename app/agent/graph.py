"""The Atlas multi-agent graph (LangGraph).

A stateful graph with conditional routing, a self-correction loop, and a
human-in-the-loop interrupt:

    plan ─► (documents) ─────────────────────────► search_docs ─► answer
         └► generate_sql ─► approval ─► execute_sql ─► validate ─┐
                 ▲   (rejected)─► answer        (retry) │        │
                 └──────────────────────────────────────┘        ▼
                                            (both) search_docs ─► visualize ─► answer

The agent reaches the database only through its MCP client (``mcp_client``).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .. import llm
from ..schemas import ChartSpec, Plan, Review, SQLDraft
from . import mcp_client, prompts

logger = logging.getLogger(__name__)

MAX_SQL_ATTEMPTS = 3


class AgentState(TypedDict, total=False):
    question: str
    schema: str
    plan: dict
    route: str
    sql: str
    sql_rationale: str
    sql_attempts: int
    last_error: str | None
    result: dict
    needs_approval: bool
    approval_reason: str
    approved: bool
    rejected: bool
    review: dict
    docs: list
    chart: dict
    answer: str


# ---------------------------------------------------------------------------
# Guardrail heuristic for human-in-the-loop
# ---------------------------------------------------------------------------
# Personal / contact data — reading it should pause for human approval.
_PII = re.compile(r"\b(email|phone|address|ssn|social_security|passport|password|date_of_birth|dob)\b",
                  re.IGNORECASE)


def _is_sensitive(sql: str) -> tuple[bool, str]:
    low = sql.lower()
    if _PII.search(low):
        return True, "This query reads personal contact details (e.g. email addresses) — personal data."
    # A raw `SELECT *` with no row limit could pull an entire table verbatim.
    if re.search(r"select\s+\*", low) and " limit " not in low:
        return True, "This query selects entire raw rows (SELECT *) with no row limit."
    return False, ""


# ---------------------------------------------------------------------------
# Evidence formatting for the writer
# ---------------------------------------------------------------------------
def _format_result(result: dict, max_rows: int = 50) -> str:
    if not result or "error" in result:
        return f"(no data — {result.get('error', 'empty result') if result else 'empty result'})"
    rows = result.get("rows", [])
    shown = rows[:max_rows]
    note = f"\n(showing {len(shown)} of {result.get('row_count', len(rows))} rows)" if len(rows) > max_rows else ""
    return f"columns: {result.get('columns')}\nrows: {json.dumps(shown, default=str)}{note}"


def _format_docs(docs: list) -> str:
    if not docs:
        return "(no documents)"
    return "\n\n".join(f"[{i}] {d['title']} ({d['doc_type']}):\n{d['content']}" for i, d in enumerate(docs, 1))


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
async def plan_node(state: AgentState) -> dict:
    schema = await mcp_client.get_schema()
    plan: Plan = await llm.get_structured(Plan).ainvoke(
        [("system", prompts.PLANNER_SYSTEM), ("human", f"Schema:\n{schema}\n\nQuestion: {state['question']}")]
    )
    return {
        "schema": schema,
        "plan": plan.model_dump(),
        "route": plan.route,
        "sql_attempts": 0,
        "last_error": None,
    }


async def generate_sql_node(state: AgentState) -> dict:
    draft: SQLDraft = await llm.get_structured(SQLDraft).ainvoke(
        [
            ("system", prompts.SQL_SYSTEM),
            ("human", prompts.sql_user_prompt(state["question"], state["schema"], state.get("last_error"))),
        ]
    )
    return {
        "sql": draft.sql.strip(),
        "sql_rationale": draft.rationale,
        "sql_attempts": state.get("sql_attempts", 0) + 1,
    }


def approval_node(state: AgentState) -> dict:
    sensitive, reason = _is_sensitive(state["sql"])
    if not sensitive:
        return {"needs_approval": False, "approved": True, "rejected": False}
    decision = interrupt({"sql": state["sql"], "reason": reason})
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    return {"needs_approval": True, "approval_reason": reason, "approved": approved, "rejected": not approved}


async def execute_sql_node(state: AgentState) -> dict:
    result = await mcp_client.run_sql(state["sql"])
    return {"result": result}


async def validate_node(state: AgentState) -> dict:
    result = state.get("result", {})
    if "error" in result:
        return {"review": {"answers_question": False, "issue": result["error"]}, "last_error": result["error"]}
    review: Review = await llm.get_structured(Review).ainvoke(
        [
            ("system", prompts.VALIDATOR_SYSTEM),
            ("human", f"Question: {state['question']}\n\nSQL:\n{state['sql']}\n\nResult:\n{_format_result(result)}"),
        ]
    )
    return {"review": review.model_dump(), "last_error": review.issue if not review.answers_question else None}


async def search_docs_node(state: AgentState) -> dict:
    docs = await mcp_client.search_documents(state["question"], k=4)
    return {"docs": docs}


async def visualize_node(state: AgentState) -> dict:
    result = state.get("result", {})
    rows = result.get("rows", []) if result else []
    if "error" in (result or {}) or len(rows) < 2 or len(result.get("columns", [])) < 2:
        return {"chart": {"type": "none"}}
    spec: ChartSpec = await llm.get_structured(ChartSpec).ainvoke(
        [
            ("system", prompts.VISUALIZER_SYSTEM),
            ("human", f"Question: {state['question']}\nColumns: {result['columns']}\nSample rows: {json.dumps(rows[:5], default=str)}"),
        ]
    )
    return {"chart": spec.model_dump()}


async def answer_node(state: AgentState) -> dict:
    if state.get("rejected"):
        return {"answer": "I held off — that query wasn't approved, so I didn't run it. "
                          "You can rephrase it to avoid exposing raw personal data (for example, ask for an aggregate)."}
    evidence = []
    if state.get("result") is not None and state.get("route") in ("sql", "both"):
        evidence.append(f"SQL RESULT:\n{_format_result(state['result'])}")
    if state.get("docs"):
        evidence.append(f"DOCUMENTS:\n{_format_docs(state['docs'])}")
    human = f"Question: {state['question']}\n\nEvidence:\n" + "\n\n".join(evidence or ["(none)"])
    msg = await llm.get_chat(temperature=0.3, max_tokens=1200).ainvoke(
        [("system", prompts.ANSWER_SYSTEM), ("human", human)]
    )
    content = msg.content if hasattr(msg, "content") else str(msg)
    return {"answer": content}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
def route_after_plan(state: AgentState) -> str:
    return "search_docs" if state["route"] == "documents" else "generate_sql"


def route_after_approval(state: AgentState) -> str:
    return "answer" if state.get("rejected") else "execute_sql"


def route_after_validate(state: AgentState) -> str:
    review = state.get("review", {})
    if not review.get("answers_question") and state.get("sql_attempts", 0) < MAX_SQL_ATTEMPTS:
        return "generate_sql"
    return "search_docs" if state["route"] == "both" else "visualize"


def route_after_docs(state: AgentState) -> str:
    return "visualize" if state["route"] == "both" else "answer"


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("generate_sql", generate_sql_node)
    g.add_node("approval", approval_node)
    g.add_node("execute_sql", execute_sql_node)
    g.add_node("validate", validate_node)
    g.add_node("search_docs", search_docs_node)
    g.add_node("visualize", visualize_node)
    g.add_node("answer", answer_node)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", route_after_plan, ["search_docs", "generate_sql"])
    g.add_edge("generate_sql", "approval")
    g.add_conditional_edges("approval", route_after_approval, ["answer", "execute_sql"])
    g.add_edge("execute_sql", "validate")
    g.add_conditional_edges("validate", route_after_validate, ["generate_sql", "search_docs", "visualize"])
    g.add_conditional_edges("search_docs", route_after_docs, ["visualize", "answer"])
    g.add_edge("visualize", "answer")
    g.add_edge("answer", END)

    return g.compile(checkpointer=MemorySaver())


graph = build_graph()
