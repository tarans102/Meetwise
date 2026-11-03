"""Domain records produced by the pipeline.

Plain dataclasses keep the domain independent of any web or LLM framework.
Each `from_llm` constructor sanitises untrusted model output and returns None
for records that cannot be salvaged.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

PRIORITIES = frozenset({"high", "medium", "low"})
TASK_STATUSES = frozenset({"not_started", "in_progress", "completed", "blocked"})
ASSIGNMENT_TYPES = frozenset({"explicit", "inferred", "unassigned"})
CATEGORIES = frozenset({"direct", "team", "dependency", "uncertain", "not_relevant"})
VERDICTS = frozenset({"confirmed", "inferred", "unsupported"})
DECISION_STATUSES = frozenset({"finalized", "pending"})
EVENT_TYPES = frozenset({"meeting", "deadline", "general"})
EVENT_CONFIDENCE = frozenset({"confirmed", "proposed", "tentative"})

VERDICT_RANK = {"unsupported": 0, "inferred": 1, "confirmed": 2}
_NON_NAMES = frozenset(
    {
        "",
        "unassigned",
        "none",
        "null",
        "n/a",
        "na",
        "tbd",
        "unknown",
        "nobody",
        "no one",
    }
)
_UTTERANCE_ID = re.compile(r"^U\d{3,}$")


def coerce(value: Any, allowed: frozenset[str], default: str) -> str:
    normalised = str(value or "").strip().lower().replace(" ", "_")
    return normalised if normalised in allowed else default


def weaker(a: str, b: str) -> str:
    """The less trusted of two verdicts."""
    return a if VERDICT_RANK[a] <= VERDICT_RANK[b] else b


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def clean_name(value: Any) -> str | None:
    text = clean_text(value)
    if text is None or text.lower() in _NON_NAMES:
        return None
    return text


def clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (clean_text(v) for v in value) if t]


def clean_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for raw in value:
        candidate = str(raw).strip().upper()
        if _UTTERANCE_ID.match(candidate) and candidate not in ids:
            ids.append(candidate)
    return ids


class _Record:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        return cls(**data)


@dataclass
class ActionItem(_Record):
    description: str
    assignee: str | None
    due_date: str | None
    priority: str
    status: str
    assignment_type: str
    evidence_ids: list[str]
    dependencies: list[str] = field(default_factory=list)
    category: str | None = None
    verdict: str | None = None
    verification_notes: list[str] = field(default_factory=list)

    @classmethod
    def from_llm(cls, raw: dict[str, Any]) -> "ActionItem | None":
        description = clean_text(raw.get("description"))
        if not description:
            return None
        assignee = clean_name(raw.get("assignee"))
        assignment = coerce(raw.get("assignment_type"), ASSIGNMENT_TYPES, "inferred")
        if assignee is None:
            assignment = "unassigned"
        elif assignment == "unassigned":
            assignment = "inferred"
        return cls(
            description=description,
            assignee=assignee,
            due_date=clean_text(raw.get("due_date")),
            priority=coerce(raw.get("priority"), PRIORITIES, "medium"),
            status=coerce(raw.get("status"), TASK_STATUSES, "not_started"),
            assignment_type=assignment,
            evidence_ids=clean_ids(raw.get("evidence_ids")),
            dependencies=clean_list(raw.get("dependencies")),
        )


@dataclass
class Decision(_Record):
    statement: str
    status: str
    alternatives: list[str]
    rationale: str | None
    evidence_ids: list[str]

    @classmethod
    def from_llm(cls, raw: dict[str, Any]) -> "Decision | None":
        statement = clean_text(raw.get("statement"))
        if not statement:
            return None
        return cls(
            statement=statement,
            status=coerce(raw.get("status"), DECISION_STATUSES, "pending"),
            alternatives=clean_list(raw.get("alternatives")),
            rationale=clean_text(raw.get("rationale")),
            evidence_ids=clean_ids(raw.get("evidence_ids")),
        )


@dataclass
class UnresolvedIssue(_Record):
    description: str
    responsible: str | None
    explicitly_unresolved: bool
    evidence_ids: list[str]

    @classmethod
    def from_llm(cls, raw: dict[str, Any]) -> "UnresolvedIssue | None":
        description = clean_text(raw.get("description"))
        if not description:
            return None
        explicit = raw.get("explicitly_unresolved") in (True, "true", "True")
        return cls(
            description=description,
            responsible=clean_name(raw.get("responsible")),
            explicitly_unresolved=explicit,
            evidence_ids=clean_ids(raw.get("evidence_ids")),
        )


@dataclass
class Event(_Record):
    title: str
    date: str | None
    start_time: str | None
    end_time: str | None
    participants: list[str]
    location: str | None
    event_type: str
    confidence: str
    evidence_ids: list[str]

    @classmethod
    def from_llm(cls, raw: dict[str, Any]) -> "Event | None":
        title = clean_text(raw.get("title"))
        if not title:
            return None
        date = clean_text(raw.get("date"))
        confidence = coerce(raw.get("confidence"), EVENT_CONFIDENCE, "proposed")
        # A confirmed event without a date is not actually confirmable.
        if confidence == "confirmed" and date is None:
            confidence = "tentative"
        return cls(
            title=title,
            date=date,
            start_time=clean_text(raw.get("start_time")),
            end_time=clean_text(raw.get("end_time")),
            participants=clean_list(raw.get("participants")),
            location=clean_text(raw.get("location")),
            event_type=coerce(raw.get("event_type"), EVENT_TYPES, "general"),
            confidence=confidence,
            evidence_ids=clean_ids(raw.get("evidence_ids")),
        )
