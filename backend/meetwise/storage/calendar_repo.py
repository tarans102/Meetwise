"""Local calendar store. Nothing here talks to an external calendar service.

Events extracted from meetings are stored as `pending_review` and stay off the
calendar until the user confirms them.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from meetwise.domain.calendar import parse_when
from meetwise.storage.db import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CalendarRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _decode(row: dict[str, Any]) -> dict[str, Any]:
        row["all_day"] = bool(row["all_day"])
        row["completed"] = bool(row["completed"])
        row["participants"] = json.loads(row["participants"] or "[]")
        return row

    def _insert(self, data: dict[str, Any]) -> str:
        """Caller holds the lock and commits."""
        event_id = uuid.uuid4().hex
        now = _now()
        self.db.conn.execute(
            """INSERT INTO calendar_events (id, title, starts_at, ends_at, all_day, event_type, review_status,
               extracted_confidence, date_text, location, participants, notes, source_meeting_id,
               completed, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                event_id,
                data["title"],
                data.get("starts_at"),
                data.get("ends_at"),
                int(bool(data.get("all_day", False))),
                data.get("event_type", "general"),
                data.get("review_status", "confirmed"),
                data.get("extracted_confidence"),
                data.get("date_text"),
                data.get("location"),
                json.dumps(data.get("participants") or [], ensure_ascii=False),
                data.get("notes"),
                data.get("source_meeting_id"),
                now,
                now,
            ),
        )
        return event_id

    def create_event(self, **data: Any) -> str:
        with self.db.lock:
            event_id = self._insert(data)
            self.db.conn.commit()
        return event_id

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self.db.lock:
            row = self.db.conn.execute(
                "SELECT * FROM calendar_events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._decode(dict(row)) if row else None

    def update_event(self, event_id: str, **fields: Any) -> None:
        if not fields:
            return
        encoded: dict[str, Any] = {}
        for key, value in fields.items():
            if key == "participants":
                value = json.dumps(value or [], ensure_ascii=False)
            elif isinstance(value, bool):
                value = int(value)
            encoded[key] = value
        encoded["updated_at"] = _now()
        assignments = ", ".join(f"{k} = ?" for k in encoded)
        with self.db.lock:
            self.db.conn.execute(
                f"UPDATE calendar_events SET {assignments} WHERE id = ?",
                (*encoded.values(), event_id),
            )
            self.db.conn.commit()

    def delete_event(self, event_id: str) -> None:
        with self.db.lock:
            self.db.conn.execute(
                "DELETE FROM calendar_events WHERE id = ?", (event_id,)
            )
            self.db.conn.commit()

    def list_events(
        self,
        start: str | None = None,
        end: str | None = None,
        include_pending: bool = False,
    ) -> list[dict[str, Any]]:
        """Events on the calendar. `start`/`end` are inclusive yyyy-mm-dd bounds."""
        clauses = ["starts_at IS NOT NULL"]
        params: list[Any] = []
        if not include_pending:
            clauses.append("review_status != 'pending_review'")
        if start:
            clauses.append("substr(starts_at, 1, 10) >= ?")
            params.append(start)
        if end:
            clauses.append("substr(starts_at, 1, 10) <= ?")
            params.append(end)
        sql = f"SELECT * FROM calendar_events WHERE {' AND '.join(clauses)} ORDER BY starts_at"
        with self.db.lock:
            rows = self.db.conn.execute(sql, tuple(params)).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def list_pending(self) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT * FROM calendar_events WHERE review_status = 'pending_review' ORDER BY created_at"
            ).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def confirm(self, event_id: str, **overrides: Any) -> None:
        self.update_event(event_id, review_status="confirmed", **overrides)

    def replace_pending_from_meeting(
        self, meeting_id: str, events: list[dict[str, Any]], reference: date
    ) -> int:
        """Re-processing a meeting replaces its pending suggestions but never confirmed events."""
        with self.db.lock:
            self.db.conn.execute(
                "DELETE FROM calendar_events WHERE source_meeting_id = ? AND review_status = 'pending_review'",
                (meeting_id,),
            )
            for event in events:
                when = parse_when(
                    event.get("date"),
                    event.get("start_time"),
                    event.get("end_time"),
                    reference,
                )
                self._insert(
                    {
                        "title": event["title"],
                        "starts_at": when["starts_at"],
                        "ends_at": when["ends_at"],
                        "all_day": when["all_day"],
                        "event_type": event.get("event_type", "general"),
                        "review_status": "pending_review",
                        "extracted_confidence": event.get("confidence"),
                        "date_text": event.get("date"),
                        "location": event.get("location"),
                        "participants": event.get("participants") or [],
                        "source_meeting_id": meeting_id,
                    }
                )
            self.db.conn.commit()
            return len(events)
