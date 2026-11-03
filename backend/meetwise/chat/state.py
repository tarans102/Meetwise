"""Chat graph state. Keys must not share names with graph nodes (LangGraph requirement)."""

from __future__ import annotations

from typing import Any, TypedDict


class ChatState(TypedDict, total=False):
    question: str
    scope: str  # "meeting" | "all"
    meeting_id: str | None
    history: list[dict[str, str]]
    search_plan: dict[str, Any]
    sources: list[dict[str, Any]]
    status: str  # set by grade (no evidence) or finalize
    final_answer: str
    citations: list[dict[str, Any]]
    draft: dict[str, Any]
    cited: list[str]
    verification: dict[str, Any]
    feedback: str | None
    attempts: int
