"""LangGraph node implementations.

Nodes are plain methods on PipelineNodes, which takes its dependencies (chat model,
org context, persistence callable) by injection. That keeps each node independently
testable and replaceable, and lets this module import without LangGraph installed.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from meetwise.domain.attribution import classify_action_item
from meetwise.domain.models import (
    VERDICT_RANK,
    ActionItem,
    Decision,
    Event,
    UnresolvedIssue,
    clean_list,
    clean_text,
    coerce,
    VERDICTS,
    weaker,
)
from meetwise.domain.org import OrgContext
from meetwise.domain.verification import verify_action_item
from meetwise.graph import prompts
from meetwise.graph.state import MeetingState
from meetwise.ingest.transcript import (
    Utterance,
    make_windows,
    parse_utterances,
    render_utterances,
)
from meetwise.llm.base import ChatModel, LLMOutputError, complete_json
from meetwise.textutils import jaccard

logger = logging.getLogger(__name__)
T = TypeVar("T")
SYSTEM = prompts.SYSTEM


def _dedupe_names(names: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for name in names:
        key = name.strip().lower()
        if key and key not in seen:
            seen[key] = name.strip()
    return list(seen.values())


def _fallback_title(filename: str | None) -> str:
    stem = Path(filename or "").stem.replace("_", " ").replace("-", " ").strip()
    return stem.title() or "Untitled meeting"


def _fill_missing(a: T, b: Any) -> T:
    """Merge duplicate records: union evidence, fill empty fields from the other record."""
    for f in dataclasses.fields(a):  # type: ignore[arg-type]
        current, incoming = getattr(a, f.name), getattr(b, f.name)
        if f.name == "evidence_ids":
            setattr(a, f.name, list(dict.fromkeys(current + incoming)))
        elif current in (None, "", []) and incoming not in (None, "", []):
            setattr(a, f.name, incoming)
    return a


def _merge_similar(
    items: list[T], text_of: Callable[[T], str], threshold: float = 0.8
) -> list[T]:
    merged: list[T] = []
    for item in items:
        for index, existing in enumerate(merged):
            if jaccard(text_of(item), text_of(existing)) >= threshold:
                merged[index] = _fill_missing(existing, item)
                break
        else:
            merged.append(item)
    return merged


class PipelineNodes:
    def __init__(
        self,
        *,
        chat: ChatModel,
        org: OrgContext,
        window_chars: int = 12000,
        max_attempts: int = 2,
        persist: Callable[[dict[str, Any]], None] | None = None,
        on_stage: Callable[[str], None] | None = None,
    ) -> None:
        self.chat = chat
        self.org = org
        self.window_chars = window_chars
        self.max_attempts = max_attempts
        self._persist = persist
        self._on_stage = on_stage

    # ----- plumbing -------------------------------------------------------

    def node(self, name: str, fn: Callable[[MeetingState], dict[str, Any]]):
        """Wrap a node so the current stage is reported before it runs."""

        def run(state: MeetingState) -> dict[str, Any]:
            if self._on_stage:
                self._on_stage(name)
            logger.info("meetwise node: %s", name)
            return fn(state)

        run.__name__ = name
        return run

    def _utterances(self, state: MeetingState) -> list[Utterance]:
        return [Utterance.from_dict(u) for u in state.get("utterances", [])]

    def _windows(self, state: MeetingState) -> list[list[Utterance]]:
        return make_windows(self._utterances(state), self.window_chars)

    def _ask(self, user_prompt: str) -> dict[str, Any]:
        return complete_json(self.chat, SYSTEM, user_prompt)

    def _extract_list(
        self, data: dict[str, Any], key: str, parse: Callable[[dict], T | None]
    ) -> list[T]:
        out: list[T] = []
        for raw in data.get(key) or []:
            if isinstance(raw, dict):
                record = parse(raw)
                if record is not None:
                    out.append(record)
        return out

    # ----- nodes ----------------------------------------------------------

    def preprocess(self, state: MeetingState) -> dict[str, Any]:
        utterances = parse_utterances(state.get("raw_text", ""))
        if not utterances:
            raise ValueError(
                "No readable transcript text was found in the uploaded file."
            )
        speakers = list(dict.fromkeys(u.speaker for u in utterances if u.speaker))
        return {
            "utterances": [u.to_dict() for u in utterances],
            "detected_speakers": speakers,
            "attempts": 0,
            "verification_feedback": None,
        }

    def metadata(self, state: MeetingState) -> dict[str, Any]:
        windows = self._windows(state)
        excerpt = render_utterances(windows[0])
        try:
            data = self._ask(
                prompts.metadata_prompt(
                    excerpt, self.org.prompt_block(), state.get("detected_speakers", [])
                )
            )
        except LLMOutputError as exc:
            # Metadata is useful but not essential: fall back rather than fail the meeting.
            logger.warning("metadata generation failed, using fallbacks: %s", exc)
            data = {}

        user_title = clean_text(state.get("user_title"))
        title = (
            user_title
            or clean_text(data.get("title"))
            or _fallback_title(state.get("filename"))
        )
        participants = _dedupe_names(
            list(state.get("user_participants", []))
            + list(state.get("detected_speakers", []))
            + clean_list(data.get("participants"))
        )
        context = {
            "purpose": clean_text(data.get("context")),
            "topic_hints": clean_list(data.get("topics")),
        }
        return {
            "title": title,
            "title_generated": user_title is None,
            "participants": participants,
            "context": context,
        }

    def summarize(self, state: MeetingState) -> dict[str, Any]:
        windows = self._windows(state)
        if len(windows) == 1:
            data = self._ask(prompts.summary_prompt(render_utterances(windows[0])))
        else:
            partials = [
                self._ask(prompts.partial_summary_prompt(render_utterances(w)))
                for w in windows
            ]
            data = self._ask(
                prompts.reduce_summary_prompt(json.dumps(partials, ensure_ascii=False))
            )
        return {
            "summary": {
                "executive_summary": clean_text(data.get("executive_summary")) or "",
                "key_points": clean_list(data.get("key_points")),
                "outcomes": clean_list(data.get("outcomes")),
            }
        }

    def segment(self, state: MeetingState) -> dict[str, Any]:
        utterances = self._utterances(state)
        index = {u.id: i for i, u in enumerate(utterances)}
        topics: list[dict[str, Any]] = []
        for window in self._windows(state):
            data = self._ask(prompts.segment_prompt(render_utterances(window)))
            for raw in data.get("topics") or []:
                if not isinstance(raw, dict):
                    continue
                start = str(raw.get("start_id", "")).strip().upper()
                end = str(raw.get("end_id", "")).strip().upper()
                if start not in index or end not in index or index[end] < index[start]:
                    continue  # ignore hallucinated or inverted ranges
                topics.append(
                    {
                        "name": clean_text(raw.get("name")) or "Discussion",
                        "start_id": start,
                        "end_id": end,
                        "utterance_ids": [
                            u.id for u in utterances[index[start] : index[end] + 1]
                        ],
                    }
                )
        if not topics and utterances:
            topics = [
                {
                    "name": "General discussion",
                    "start_id": utterances[0].id,
                    "end_id": utterances[-1].id,
                    "utterance_ids": [u.id for u in utterances],
                }
            ]
        return {"topics": topics}

    def extract_decisions(self, state: MeetingState) -> dict[str, Any]:
        decisions: list[Decision] = []
        issues: list[UnresolvedIssue] = []
        for window in self._windows(state):
            data = self._ask(prompts.decisions_prompt(render_utterances(window)))
            decisions += self._extract_list(data, "decisions", Decision.from_llm)
            issues += self._extract_list(
                data, "unresolved_issues", UnresolvedIssue.from_llm
            )
        decisions = _merge_similar(decisions, lambda d: d.statement)
        issues = _merge_similar(issues, lambda i: i.description)
        return {
            "decisions": [d.to_dict() for d in decisions],
            "unresolved_issues": [i.to_dict() for i in issues],
        }

    def extract_events(self, state: MeetingState) -> dict[str, Any]:
        events: list[Event] = []
        for window in self._windows(state):
            data = self._ask(prompts.events_prompt(render_utterances(window)))
            events += self._extract_list(data, "events", Event.from_llm)
        events = _merge_similar(events, lambda e: f"{e.title} {e.date or ''}")
        return {"events": [e.to_dict() for e in events]}

    def extract_actions(self, state: MeetingState) -> dict[str, Any]:
        feedback = state.get("verification_feedback")
        known = self.org.prompt_block()
        items: list[ActionItem] = []
        for window in self._windows(state):
            data = self._ask(
                prompts.actions_prompt(render_utterances(window), known, feedback)
            )
            items += self._extract_list(data, "action_items", ActionItem.from_llm)
        items = _merge_similar(items, lambda i: i.description)
        return {
            "action_items": [i.to_dict() for i in items],
            "attempts": int(state.get("attempts", 0)) + 1,
            "verification_feedback": None,
        }

    def attribute(self, state: MeetingState) -> dict[str, Any]:
        text_by_id = {u.id: u.text for u in self._utterances(state)}
        items = [ActionItem.from_dict(d) for d in state.get("action_items", [])]
        for item in items:
            classify_action_item(item, self.org, text_by_id)
        return {"action_items": [i.to_dict() for i in items]}

    def verify(self, state: MeetingState) -> dict[str, Any]:
        utterances = {u.id: u for u in self._utterances(state)}
        items = [ActionItem.from_dict(d) for d in state.get("action_items", [])]
        global_notes: list[str] = []
        contradictions: list[dict[str, Any]] = []

        # 1. Deterministic grounding checks.
        for item in items:
            item.verdict, item.verification_notes = verify_action_item(
                item, utterances, self.org
            )

        # 2. LLM verification against the cited evidence.
        if items:
            payload = [
                {
                    "index": i,
                    "description": item.description,
                    "assignee": item.assignee,
                    "assignment_type": item.assignment_type,
                    "due_date": item.due_date,
                    "evidence": [
                        utterances[e].render()
                        for e in item.evidence_ids
                        if e in utterances
                    ],
                }
                for i, item in enumerate(items)
            ]
            try:
                data = self._ask(
                    prompts.verify_prompt(
                        json.dumps(payload, ensure_ascii=False, indent=1)
                    )
                )
                for entry in data.get("verdicts") or []:
                    if not isinstance(entry, dict) or not isinstance(
                        entry.get("index"), int
                    ):
                        continue
                    idx = entry["index"]
                    if 0 <= idx < len(items):
                        judged = coerce(entry.get("verdict"), VERDICTS, "inferred")
                        items[idx].verdict = weaker(
                            items[idx].verdict or "confirmed", judged
                        )
                        note = clean_text(entry.get("note"))
                        if note:
                            items[idx].verification_notes.append(note)
                contradictions = [
                    c for c in (data.get("contradictions") or []) if isinstance(c, dict)
                ]
            except LLMOutputError as exc:
                # Without the second opinion, nothing may be presented as fully confirmed.
                global_notes.append(
                    f"LLM verification unavailable ({exc}); items capped at 'inferred'."
                )
                for item in items:
                    item.verdict = weaker(item.verdict or "inferred", "inferred")

        for item in items:
            item.verdict = item.verdict or "inferred"

        unsupported = [i.description for i in items if i.verdict == "unsupported"]
        feedback = None
        if unsupported:
            feedback = "remove or correct these items: " + "; ".join(unsupported)

        counts = {v: sum(1 for i in items if i.verdict == v) for v in VERDICT_RANK}
        verification = {
            "passed": not unsupported,
            "counts": counts,
            "contradictions": contradictions,
            "notes": global_notes,
        }
        return {
            "action_items": [i.to_dict() for i in items],
            "verification": verification,
            "verification_feedback": feedback,
        }

    def route_after_verify(self, state: MeetingState) -> str:
        """Retry extraction when unsupported items remain and attempts are left."""
        if (
            state.get("verification_feedback")
            and int(state.get("attempts", 0)) < self.max_attempts
        ):
            return "extract_actions"
        return "persist"

    def persist(self, state: MeetingState) -> dict[str, Any]:
        if self._persist is not None:
            self._persist(dict(state))
        return {}
