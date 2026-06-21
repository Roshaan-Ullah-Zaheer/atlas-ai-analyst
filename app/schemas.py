"""Pydantic models for the agent's structured outputs.

Each reasoning step that must be machine-readable (planning, SQL drafting,
review, chart selection) returns one of these via the LLM's structured-output
mode, so the graph routes on typed data rather than parsing free text.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Plan(BaseModel):
    """The planner's decision about how to answer the question."""

    intent: str = Field(description="One sentence restating what the user actually wants.")
    route: Literal["sql", "documents", "both"] = Field(
        description=(
            "sql = answerable from the structured tables; documents = a policy/how/why "
            "question answered from company documents; both = needs structured data AND "
            "document context."
        )
    )
    steps: list[str] = Field(
        default_factory=list,
        description="2-4 short steps describing how you'll answer.",
    )


class SQLDraft(BaseModel):
    """A single read-only SQL query the agent intends to run."""

    sql: str = Field(description="One read-only PostgreSQL SELECT/WITH query. No semicolons, no writes.")
    rationale: str = Field(description="One sentence on what the query computes.")


class Review(BaseModel):
    """The validator's verdict on whether the result answers the question."""

    answers_question: bool = Field(description="True if the rows genuinely answer the user's question.")
    issue: Optional[str] = Field(
        default=None,
        description="If answers_question is false, what's wrong and how to fix the SQL (be specific).",
    )


class ChartSpec(BaseModel):
    """How to visualize the result, chosen by the visualizer."""

    type: Literal["bar", "line", "pie", "none"] = Field(
        description="The best chart for this result, or 'none' if a table/number is clearer."
    )
    x: Optional[str] = Field(default=None, description="Column name for the category / x-axis.")
    y: Optional[str] = Field(default=None, description="Column name for the numeric value / y-axis.")
    title: Optional[str] = Field(default=None, description="Short chart title.")


class SampleQuestions(BaseModel):
    """Starter questions generated for the live schema, shown in the sidebar."""

    questions: list[str] = Field(
        description=(
            "Exactly 5 short, natural-language starter questions that this assistant can "
            "answer from the given schema. Diverse, specific to the schema, no numbering."
        )
    )
