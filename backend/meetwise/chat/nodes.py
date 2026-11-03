"""Chat agent nodes: plan -> retrieve -> grade -> answer -> verify -> finalize.

Guarantees enforced in code, not left to the model:
- If nothing relevant is retrieved, the model is never called and the user is told so.
- Every [Sn] citation must refer to a source that was actually provided.
- Every number in a non-insufficient answer must appear in the cited sources.
- After a bounded number of retries, the agent refuses rather than presenting an unchecked answer.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from meetwise.chat import prompts
from meetwise.chat.state import ChatState
from meetwise.domain.models import clean_list, clean_text, coerce
from meetwise.llm.base import ChatModel, LLMOutputError, complete_json
from meetwise.rag.retriever import Retriever
from meetwise.rag.store import Hit, SearchFilters
from meetwise.storage.repository import Repository

CONTENT_TYPES = frozenset(
    {"transcript", "summary", "action_item", "decision", "unresolved_issue", "event"}
)
TASK_SCOPES = frozenset({"mine", "team", "dependencies", "all"})
EVIDENCE_STATUSES = frozenset({"confirmed", "inferred", "insufficient"})
TASK_CATEGORIES_FOR_SCOPE = {
    "mine": {"direct"},
    "team": {"team"},
    "dependencies": {"dependency"},
}

CITATION = re.compile(r"\[(S\d+)\]")
NUMBER = re.compile(r"(?<!\w)\d+(?!\w)")
_FIRST_PERSON = re.compile(r"\b(my|me|i|i'm|mine)\b", re.IGNORECASE)
_TASK_HINTS = (
    "task",
    "commitment",
    "pending",
    "owe",
    "owns",
    "assigned",
    "assignment",
    "deadline",
    "blocked",
    "blocking",
    "action item",
    "responsib",
    "status",
)


def _looks_like_task_question(question: str) -> bool:
    lowered = question.lower()
    return any(hint in lowered for hint in _TASK_HINTS)


def _iso_or_none(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _format_history(history: list[dict[str, str]]) -> str:
    return "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-4:])


def _format_source(source: dict[str, Any]) -> str:
    label = source["kind"].replace("_", " ")
    header = f"[{source['sid']}] {label} | {source['meeting_title'] or 'untitled'} ({source['meeting_date'] or 'undated'})"
    details = [d for d in (source.get("speaker"), source.get("timestamp")) if d]
    if details:
        header += " | " + " ".join(details)
    if source.get("source_ids"):
        header += " | ids: " + ", ".join(source["source_ids"])
    return f"{header}\n{source['text']}"


class ChatNodes:
    def __init__(
        self,
        *,
        chat: ChatModel,
        retriever: Retriever,
        repo: Repository,
        today: str,
        max_attempts: int = 2,
        min_relevance: float = 0.2,
        k: int = 8,
        per_meeting_cap: int = 3,
        max_task_sources: int = 8,
    ) -> None:
        self.chat = chat
        self.retriever = retriever
        self.repo = repo
        self.today = today
        self.max_attempts = max_attempts
        self.min_relevance = min_relevance
        self.k = k
        self.per_meeting_cap = per_meeting_cap
        self.max_task_sources = max_task_sources
        self._meetings: dict[str, dict[str, Any] | None] = {}

    # ----- helpers --------------------------------------------------------

    def _meeting(self, meeting_id: str | None) -> dict[str, Any] | None:
        if not meeting_id:
            return None
        if meeting_id not in self._meetings:
            self._meetings[meeting_id] = self.repo.get_meeting(meeting_id)
        return self._meetings[meeting_id]

    def _ask(self, prompt: str) -> dict[str, Any]:
        try:
            return complete_json(self.chat, prompts.CHAT_SYSTEM, prompt)
        except LLMOutputError:
            return {}

    def _filters(
        self, plan: dict[str, Any], scope: str, meeting_id: str | None, extras: bool
    ) -> SearchFilters:
        all_scope = scope == "all"
        return SearchFilters(
            meeting_ids=[meeting_id] if scope == "meeting" else None,
            date_from=plan["date_from"] if all_scope else None,
            date_to=plan["date_to"] if all_scope else None,
            participants=(plan["participants"] or None) if extras else None,
            content_types=(plan["content_types"] or None) if extras else None,
        )

    def _search(self, queries: list[str], filters: SearchFilters) -> list[Hit]:
        best: dict[str, Hit] = {}
        for query in queries:
            for hit in self.retriever.search(query, filters=filters, k=self.k * 2):
                if hit.chunk_id not in best or hit.score > best[hit.chunk_id].score:
                    best[hit.chunk_id] = hit
        return sorted(best.values(), key=lambda h: h.score, reverse=True)

    def _diversify(self, hits: list[Hit], scope: str) -> list[Hit]:
        """Across all meetings, cap hits per meeting so one long meeting cannot crowd out the rest."""
        if scope == "meeting":
            return hits
        counts: dict[str, int] = {}
        kept: list[Hit] = []
        for hit in hits:
            meeting_id = hit.metadata["meeting_id"]
            if counts.get(meeting_id, 0) < self.per_meeting_cap:
                kept.append(hit)
                counts[meeting_id] = counts.get(meeting_id, 0) + 1
        return kept

    @staticmethod
    def _hit_source(hit: Hit) -> dict[str, Any]:
        meta = hit.metadata
        return {
            "kind": meta.get("content_type", "transcript"),
            "text": hit.text,
            "meeting_id": meta.get("meeting_id"),
            "meeting_title": meta.get("meeting_title", ""),
            "meeting_date": meta.get("meeting_date", ""),
            "source_ids": list(meta.get("source_ids") or []),
            "timestamp": meta.get("timestamp", ""),
            "speaker": meta.get("speaker", ""),
            "score": round(hit.score, 3),
            "task_id": meta.get("task_id", ""),
        }

    def _task_sources(
        self, scope: str, meeting_id: str | None, task_scope: str
    ) -> list[dict[str, Any]]:
        allowed = TASK_CATEGORIES_FOR_SCOPE.get(task_scope)
        sources: list[dict[str, Any]] = []
        for task in self.repo.list_tasks():
            if scope == "meeting" and task["meeting_id"] != meeting_id:
                continue
            category = task.get("category") or "uncertain"
            if allowed is not None and category not in allowed:
                continue
            if allowed is None and category == "not_relevant":
                continue
            meeting = self._meeting(task["meeting_id"]) or {}
            history = self.repo.task_history(task["id"])[-4:]
            text = (
                f"Task: {task['description']}. Owner: {task.get('assignee') or 'unassigned'} "
                f"(category: {category}, assignment: {task.get('assignment_type')}). "
                f"Due: {task.get('due_date') or 'not stated'}. Status: {task.get('status')}. "
                f"Priority: {task.get('priority')}."
            )
            if history:
                text += " History: " + " ".join(
                    f"{h['event']}: {h['detail']}" for h in history
                )
            sources.append(
                {
                    "kind": "task",
                    "text": text,
                    "meeting_id": task["meeting_id"],
                    "meeting_title": meeting.get("title") or "",
                    "meeting_date": meeting.get("meeting_date") or "",
                    "source_ids": list(task.get("evidence_ids") or []),
                    "timestamp": "",
                    "speaker": "",
                    "score": 1.0,
                    "task_id": task["id"],
                }
            )
            if len(sources) >= self.max_task_sources:
                break
        return sources

    def _citation(self, source: dict[str, Any]) -> dict[str, Any]:
        if source["task_id"]:
            link = f"/tasks?task={source['task_id']}"
        elif source["meeting_id"]:
            anchor = f"#{source['source_ids'][0]}" if source["source_ids"] else ""
            link = f"/meetings/{source['meeting_id']}{anchor}"
        else:
            link = None
        return {
            "source_id": source["sid"],
            "kind": source["kind"],
            "meeting_id": source["meeting_id"],
            "meeting_title": source["meeting_title"],
            "meeting_date": source["meeting_date"],
            "excerpt": source["text"][:600],
            "source_ids": source["source_ids"],
            "timestamp": source["timestamp"],
            "speaker": source["speaker"],
            "task_id": source["task_id"] or None,
            "link": link,
        }

    # ----- nodes ----------------------------------------------------------

    def plan(self, state: ChatState) -> dict[str, Any]:
        question = state["question"]
        if state["scope"] == "meeting":
            title = (self._meeting(state.get("meeting_id")) or {}).get(
                "title", "the open meeting"
            )
            scope_text = f"only the open meeting: {title}"
        else:
            scope_text = "all of the user's processed meetings"

        data = self._ask(
            prompts.plan_prompt(
                question,
                self.today,
                scope_text,
                _format_history(state.get("history", [])),
            )
        )
        include_tasks = data.get("include_tasks")
        if not isinstance(include_tasks, bool):
            include_tasks = _looks_like_task_question(question)
        default_task_scope = "mine" if _FIRST_PERSON.search(question) else "all"

        plan = {
            "search_query": clean_text(data.get("search_query")) or question,
            "date_from": _iso_or_none(data.get("date_from")),
            "date_to": _iso_or_none(data.get("date_to")),
            "participants": clean_list(data.get("participants")),
            "content_types": [
                t for t in clean_list(data.get("content_types")) if t in CONTENT_TYPES
            ],
            "include_tasks": include_tasks,
            "task_scope": coerce(
                data.get("task_scope"), TASK_SCOPES, default_task_scope
            ),
        }
        return {"search_plan": plan}

    def retrieve(self, state: ChatState) -> dict[str, Any]:
        plan = state["search_plan"]
        scope, meeting_id = state["scope"], state.get("meeting_id")
        queries = list(dict.fromkeys([plan["search_query"], state["question"]]))

        hits = self._search(
            queries, self._filters(plan, scope, meeting_id, extras=True)
        )
        if not hits and (plan["participants"] or plan["content_types"]):
            # Planner filters can be wrong; retry without them rather than answer from nothing.
            hits = self._search(
                queries, self._filters(plan, scope, meeting_id, extras=False)
            )

        hits = self._diversify(hits, scope)[: self.k]
        sources = [self._hit_source(h) for h in hits]
        if plan["include_tasks"]:
            sources += self._task_sources(scope, meeting_id, plan["task_scope"])
        for index, source in enumerate(sources, start=1):
            source["sid"] = f"S{index}"
        return {"sources": sources}

    def grade(self, state: ChatState) -> dict[str, Any]:
        relevant = [
            s
            for s in state.get("sources", [])
            if s["kind"] == "task" or s["score"] >= self.min_relevance
        ]
        if not relevant:
            where = "this meeting" if state["scope"] == "meeting" else "your meetings"
            return {
                "sources": [],
                "status": "insufficient_evidence",
                "final_answer": (
                    f"I couldn't find anything in {where} that answers this. Try rephrasing, "
                    "or check that the meeting has finished processing."
                ),
                "citations": [],
            }
        for index, source in enumerate(relevant, start=1):
            source["sid"] = f"S{index}"
        return {"sources": relevant}

    def route_after_grade(self, state: ChatState) -> str:
        return "finalize" if state.get("status") else "answer"

    def answer(self, state: ChatState) -> dict[str, Any]:
        block = "\n\n".join(_format_source(s) for s in state["sources"])
        data = self._ask(
            prompts.answer_prompt(
                state["question"],
                self.today,
                _format_history(state.get("history", [])),
                block,
                state.get("feedback"),
            )
        )
        draft = {
            "answer": str(data.get("answer") or "").strip(),
            "used_sources": clean_list(data.get("used_sources")),
            "evidence_status": coerce(
                data.get("evidence_status"), EVIDENCE_STATUSES, "inferred"
            ),
            "missing": clean_text(data.get("missing")),
        }
        return {"draft": draft, "attempts": int(state.get("attempts", 0)) + 1}

    def verify(self, state: ChatState) -> dict[str, Any]:
        sources = {s["sid"]: s for s in state.get("sources", [])}
        draft = state.get("draft") or {}
        answer = draft.get("answer", "")
        status = draft.get("evidence_status", "insufficient")
        problems: list[str] = []

        markers = CITATION.findall(answer)
        invalid = sorted({m for m in markers if m not in sources})
        if invalid:
            problems.append(
                f"cited {', '.join(invalid)}, which do not exist; cite only the labels provided"
            )
        cited = list(dict.fromkeys(m for m in markers if m in sources))

        if not answer:
            problems.append("the answer was empty")
        elif not cited and status != "insufficient":
            problems.append("the answer has no valid source citations")

        if answer and status != "insufficient":
            cited_text = " ".join(sources[c]["text"] for c in cited)
            prose = CITATION.sub("", answer)
            for number in dict.fromkeys(NUMBER.findall(prose)):
                if not re.search(rf"(?<!\d){re.escape(number)}(?!\d)", cited_text):
                    problems.append(
                        f"the number '{number}' does not appear in the cited sources"
                    )

        return {
            "cited": cited,
            "verification": {"passed": not problems, "problems": problems},
            "feedback": "; ".join(problems) or None,
        }

    def route_after_verify(self, state: ChatState) -> str:
        if state.get("feedback") and int(state.get("attempts", 0)) < self.max_attempts:
            return "answer"
        return "finalize"

    def finalize(self, state: ChatState) -> dict[str, Any]:
        if state.get("status"):  # already decided by grade
            return {}
        sources = {s["sid"]: s for s in state.get("sources", [])}
        draft = state.get("draft") or {}
        passed = (state.get("verification") or {}).get("passed", False)

        if passed and draft.get("evidence_status") != "insufficient":
            status, text, cited = "answered", draft["answer"], state.get("cited", [])
        elif passed:
            status = "insufficient_evidence"
            text = draft.get("answer") or "I couldn't find that in your meetings."
            if draft.get("missing"):
                text += f" Missing: {draft['missing']}"
            cited = state.get("cited", [])
        else:
            status = "insufficient_evidence"
            text = (
                "I found related material, but I couldn't write an answer I could check against it. "
                "The most relevant sources are listed below."
            )
            cited = [s["sid"] for s in state.get("sources", [])[:3]]

        return {
            "status": status,
            "final_answer": text,
            "citations": [self._citation(sources[c]) for c in cited if c in sources],
        }
