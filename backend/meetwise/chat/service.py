"""Session handling around the chat graph. Enforces scope and records every turn."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from meetwise.chat.nodes import ChatNodes
from meetwise.chat.workflow import build_chat_graph
from meetwise.llm.base import ChatModel
from meetwise.rag.retriever import Retriever
from meetwise.storage.chat_repo import ChatRepository
from meetwise.storage.repository import Repository

logger = logging.getLogger(__name__)
SCOPES = ("meeting", "all")


class ChatService:
    def __init__(
        self,
        *,
        chat_model: ChatModel,
        retriever: Retriever,
        repo: Repository,
        store: ChatRepository,
    ) -> None:
        self.chat_model = chat_model
        self.retriever = retriever
        self.repo = repo
        self.store = store

    def ask(
        self,
        question: str,
        *,
        scope: str = "all",
        meeting_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            raise ValueError("The question must not be empty.")
        if scope not in SCOPES:
            raise ValueError("scope must be 'meeting' or 'all'.")

        meeting = None
        if scope == "meeting":
            if not meeting_id:
                raise ValueError("meeting_id is required when scope is 'meeting'.")
            meeting = self.repo.get_meeting(meeting_id)
            if meeting is None:
                raise LookupError("Meeting not found.")

        if session_id is None:
            session_id = self.store.create_session(
                title=question[:60], scope=scope, meeting_id=meeting_id
            )
        elif self.store.get_session(session_id) is None:
            raise LookupError("Chat session not found.")

        history = self.store.recent_messages(session_id, limit=6)
        self.store.add_message(session_id, "user", question)

        nodes = ChatNodes(
            chat=self.chat_model,
            retriever=self.retriever,
            repo=self.repo,
            today=date.today().isoformat(),
        )
        try:
            state = build_chat_graph(nodes).invoke(
                {
                    "question": question,
                    "scope": scope,
                    "meeting_id": meeting_id,
                    "history": history,
                    "attempts": 0,
                }
            )
            message = self.store.add_message(
                session_id,
                "assistant",
                state["final_answer"],
                citations=state.get("citations", []),
                status=state.get("status"),
            )
        except Exception as exc:
            logger.exception("chat turn failed")
            message = self.store.add_message(
                session_id,
                "assistant",
                "Something went wrong while answering. Please try again.",
                status="error",
            )
            message["error"] = f"{type(exc).__name__}: {exc}"

        return {
            "session_id": session_id,
            "message": message,
            "scope": {
                "type": scope,
                "meeting_id": meeting_id,
                "meeting_title": meeting["title"] if meeting else None,
            },
        }
