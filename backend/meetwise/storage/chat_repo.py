"""Chat sessions and messages. Citations are stored with each assistant message."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from meetwise.storage.db import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ChatRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_session(self, *, title: str, scope: str, meeting_id: str | None) -> str:
        session_id = uuid.uuid4().hex
        now = _now()
        with self.db.lock:
            self.db.conn.execute(
                "INSERT INTO chat_sessions (id, title, scope, meeting_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, title, scope, meeting_id, now, now),
            )
            self.db.conn.commit()
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT * FROM chat_sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        now = _now()
        with self.db.lock:
            cursor = self.db.conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, citations, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    role,
                    content,
                    json.dumps(citations or [], ensure_ascii=False),
                    status,
                    now,
                ),
            )
            self.db.conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            self.db.conn.commit()
            message_id = cursor.lastrowid
        return {
            "id": message_id,
            "role": role,
            "content": content,
            "citations": citations or [],
            "status": status,
            "created_at": now,
        }

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        out = []
        for r in rows:
            row = dict(r)
            row["citations"] = json.loads(row["citations"] or "[]")
            out.append(row)
        return out

    def recent_messages(self, session_id: str, limit: int = 6) -> list[dict[str, str]]:
        messages = self.list_messages(session_id)[-limit:]
        return [{"role": m["role"], "content": m["content"]} for m in messages]
