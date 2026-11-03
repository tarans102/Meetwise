"""Shared LangGraph state. Nodes return partial updates to these keys."""

from __future__ import annotations

from typing import Any, TypedDict


class MeetingState(TypedDict, total=False):
    # Inputs
    meeting_id: str
    filename: str
    raw_text: str
    user_title: str | None
    user_date: str | None
    user_participants: list[str]

    # Preprocessing
    utterances: list[dict[str, Any]]
    detected_speakers: list[str]

    # Metadata
    title: str
    title_generated: bool
    participants: list[str]
    context: dict[str, Any]

    # Analysis
    summary: dict[str, Any]
    topics: list[dict[str, Any]]
    action_items: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    unresolved_issues: list[dict[str, Any]]
    events: list[dict[str, Any]]

    # Verification loop
    verification: dict[str, Any]
    verification_feedback: str | None
    attempts: int
