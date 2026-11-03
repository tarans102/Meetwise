"""Runs the LangGraph workflow for one meeting and persists the outcome.

Status, stage, and errors are written to the meeting record so the UI can show
progress, completion, or a failure with a readable explanation.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from meetwise.config import Settings
from meetwise.domain.org import OrgContext, Person
from meetwise.graph.nodes import PipelineNodes
from meetwise.graph.workflow import build_graph
from meetwise.ingest.transcript import Utterance
from meetwise.llm.base import ChatModel, Embedder
from meetwise.rag.chunker import build_chunks
from meetwise.rag.store import VectorStore
from meetwise.services.commitments import reconcile_action_items
from meetwise.storage.calendar_repo import CalendarRepository
from meetwise.storage.repository import Repository

logger = logging.getLogger(__name__)


class MeetingPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        repo: Repository,
        store: VectorStore,
        embedder: Embedder,
        chat: ChatModel,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.store = store
        self.embedder = embedder
        self.chat = chat
        self.calendar = CalendarRepository(repo.db)

    def _load_org(self) -> OrgContext:
        return OrgContext([Person(**p) for p in self.repo.list_people()])

    def process(self, meeting_id: str) -> None:
        meeting = self.repo.get_meeting(meeting_id)
        if meeting is None:
            logger.error("process called for unknown meeting %s", meeting_id)
            return

        nodes = PipelineNodes(
            chat=self.chat,
            org=self._load_org(),
            window_chars=self.settings.window_chars,
            max_attempts=self.settings.max_extraction_attempts,
            persist=lambda state: self._persist(meeting_id, state),
            on_stage=lambda stage: self.repo.set_stage(meeting_id, stage),
        )
        self.repo.update_meeting(
            meeting_id, status="processing", stage="preprocess", error=None
        )

        initial = {
            "meeting_id": meeting_id,
            "filename": meeting["source_filename"],
            "raw_text": meeting["raw_text"],
            "user_title": meeting["user_title"],
            "user_date": meeting["user_date"],
            "user_participants": meeting["user_participants"] or [],
        }
        try:
            build_graph(nodes).invoke(initial)
        except Exception as exc:  # surfaced to the user as a readable error state
            logger.exception("meeting processing failed: %s", meeting_id)
            self.repo.set_error(meeting_id, f"{type(exc).__name__}: {exc}")

    def _persist(self, meeting_id: str, state: dict[str, Any]) -> None:
        meeting = self.repo.get_meeting(meeting_id)
        utterances = [Utterance.from_dict(u) for u in state.get("utterances", [])]
        title = state.get("title") or "Untitled meeting"
        meeting_date = meeting["user_date"] if meeting else None

        items = reconcile_action_items(
            self.repo,
            self.embedder,
            {"id": meeting_id, "title": title, "date": meeting_date},
            list(state.get("action_items", [])),
        )
        result = {
            "summary": state.get("summary", {}),
            "context": state.get("context", {}),
            "topics": state.get("topics", []),
            "action_items": items,
            "decisions": state.get("decisions", []),
            "unresolved_issues": state.get("unresolved_issues", []),
            "events": state.get("events", []),
            "verification": state.get("verification", {}),
        }
        self.repo.save_result(
            meeting_id,
            title=title,
            title_generated=bool(state.get("title_generated")),
            participants=state.get("participants", []),
            meeting_date=meeting_date,
            result=result,
        )
        self.calendar.replace_pending_from_meeting(
            meeting_id, result["events"], reference=date.today()
        )

        chunks = build_chunks(
            {
                "id": meeting_id,
                "title": title,
                "date": meeting_date,
                "participants": state.get("participants", []),
            },
            result,
            utterances,
        )
        if chunks:
            vectors = self.embedder.embed([c.text for c in chunks])
            self.store.replace_meeting(meeting_id, chunks, vectors)
        logger.info("indexed %d chunks for meeting %s", len(chunks), meeting_id)
