"""Turns a processed meeting into retrieval chunks with structured metadata.

Transcript text is chunked by topic (never as one document). Structured records
(summary, actions, decisions, issues, events) are indexed as their own chunks so
questions like "what did we decide" retrieve the decision directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from meetwise.ingest.transcript import Utterance


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _base_metadata(meeting: dict[str, Any], content_type: str) -> dict[str, Any]:
    return {
        "meeting_id": meeting["id"],
        "meeting_title": meeting.get("title") or "",
        "meeting_date": meeting.get("date") or "",
        "participants": list(meeting.get("participants") or []),
        "content_type": content_type,
        "topic": "",
        "speaker": "",
        "timestamp": "",
        "source_ids": [],
        "assignee": "",
        "status": "",
        "priority": "",
        "category": "",
        "assignment_type": "",
        "task_id": "",
    }


def build_chunks(
    meeting: dict[str, Any],
    result: dict[str, Any],
    utterances: list[Utterance],
    max_chars: int = 1200,
) -> list[Chunk]:
    mid = meeting["id"]
    by_id = {u.id: u for u in utterances}
    chunks: list[Chunk] = []

    def add(kind: str, text: str, **overrides: Any) -> None:
        meta = _base_metadata(meeting, kind)
        meta.update(overrides)
        chunks.append(Chunk(id=f"{mid}:{kind}:{len(chunks)}", text=text, metadata=meta))

    # Transcript chunks, grouped by topic and split at a size boundary.
    for topic in result.get("topics", []):
        buffer: list[Utterance] = []
        size = 0

        def flush() -> None:
            if not buffer:
                return
            speakers = list(dict.fromkeys(u.speaker for u in buffer if u.speaker))
            add(
                "transcript",
                "\n".join(u.render() for u in buffer),
                topic=topic.get("name", ""),
                speaker=", ".join(speakers),
                timestamp=next((u.timestamp for u in buffer if u.timestamp), ""),
                source_ids=[u.id for u in buffer],
            )

        for uid in topic.get("utterance_ids", []):
            utterance = by_id.get(uid)
            if utterance is None:
                continue
            if size + len(utterance.text) > max_chars and buffer:
                flush()
                buffer, size = [], 0
            buffer.append(utterance)
            size += len(utterance.text)
        flush()
        buffer = []

    summary = result.get("summary") or {}
    if summary.get("executive_summary"):
        parts = [f"Meeting summary: {summary['executive_summary']}"]
        if summary.get("key_points"):
            parts.append("Key points: " + "; ".join(summary["key_points"]))
        if summary.get("outcomes"):
            parts.append("Outcomes: " + "; ".join(summary["outcomes"]))
        add("summary", " ".join(parts))

    for item in result.get("action_items", []):
        assignee = item.get("assignee") or "unassigned"
        text = (
            f"Action item: {item['description']}. Assignee: {assignee}. "
            f"Due: {item.get('due_date') or 'not stated'}. Status: {item.get('status')}. "
            f"Priority: {item.get('priority')}."
        )
        add(
            "action_item",
            text,
            assignee=item.get("assignee") or "",
            status=item.get("status") or "",
            priority=item.get("priority") or "",
            category=item.get("category") or "",
            assignment_type=item.get("assignment_type") or "",
            task_id=item.get("task_id") or "",
            source_ids=list(item.get("evidence_ids", [])),
        )

    for decision in result.get("decisions", []):
        text = f"Decision ({decision.get('status')}): {decision['statement']}."
        if decision.get("alternatives"):
            text += (
                " Alternatives considered: " + "; ".join(decision["alternatives"]) + "."
            )
        if decision.get("rationale"):
            text += f" Rationale: {decision['rationale']}."
        add(
            "decision",
            text,
            status=decision.get("status") or "",
            source_ids=list(decision.get("evidence_ids", [])),
        )

    for issue in result.get("unresolved_issues", []):
        text = f"Unresolved issue: {issue['description']}. Responsible: {issue.get('responsible') or 'not identified'}."
        add(
            "unresolved_issue",
            text,
            assignee=issue.get("responsible") or "",
            source_ids=list(issue.get("evidence_ids", [])),
        )

    for event in result.get("events", []):
        text = (
            f"Event ({event.get('confidence')} {event.get('event_type')}): {event['title']}. "
            f"Date: {event.get('date') or 'not stated'}. Time: {event.get('start_time') or 'not stated'}."
        )
        add(
            "event",
            text,
            status=event.get("confidence") or "",
            source_ids=list(event.get("evidence_ids", [])),
        )

    return chunks
