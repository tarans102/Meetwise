"""Persistence for meetings, people, tasks and task history."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from meetwise.storage.db import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: str | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    if type(value) is list:
        return value
    return json.loads(value)


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _write(self, sql: str, params: tuple = ()) -> None:
        with self.db.lock:
            self.db.conn.execute(sql, params)
            self.db.conn.commit()

    def _rows(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self.db.lock:
            return [dict(r) for r in self.db.conn.execute(sql, params).fetchall()]

    # ----- meetings -------------------------------------------------------

    def create_meeting(
        self,
        *,
        source_filename: str,
        raw_text: str,
        user_title: str | None,
        user_date: str | None,
        user_participants: list[str],
    ) -> str:
        meeting_id = uuid.uuid4().hex
        self._write(
            """INSERT INTO meetings (id, title, title_generated, meeting_date, participants, status, stage,
               source_filename, raw_text, user_title, user_date, user_participants, created_at)
               VALUES (?, ?, 0, ?, '[]', 'queued', 'queued', ?, ?, ?, ?, ?, ?)""",
            (
                meeting_id,
                user_title,
                user_date,
                source_filename,
                raw_text,
                user_title,
                user_date,
                _dump(user_participants),
                _now(),
            ),
        )
        return meeting_id

    def update_meeting(self, meeting_id: str, **fields: Any) -> None:
        if not fields:
            return
        encoded = {
            k: (_dump(v) if isinstance(v, (list, dict)) else v)
            for k, v in fields.items()
        }
        assignments = ", ".join(f"{k} = ?" for k in encoded)
        self._write(
            f"UPDATE meetings SET {assignments} WHERE id = ?",
            (*encoded.values(), meeting_id),
        )

    def set_stage(self, meeting_id: str, stage: str) -> None:
        self.update_meeting(meeting_id, stage=stage)

    def set_error(self, meeting_id: str, message: str) -> None:
        self.update_meeting(meeting_id, status="error", stage="error", error=message)

    def save_result(
        self,
        meeting_id: str,
        *,
        title: str,
        title_generated: bool,
        participants: list[str],
        meeting_date: str | None,
        result: dict[str, Any],
    ) -> None:
        self.update_meeting(
            meeting_id,
            title=title,
            title_generated=int(title_generated),
            participants=participants,
            meeting_date=meeting_date,
            result=result,
            status="completed",
            stage="completed",
            error=None,
        )

    def get_meeting(self, meeting_id: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM meetings WHERE id = ?", (meeting_id,))
        return self._decode_meeting(rows[0]) if rows else None

    def list_meetings(self) -> list[dict[str, Any]]:
        rows = self._rows(
            """SELECT m.id, m.title, m.meeting_date, m.participants, m.status, m.stage, m.error, m.result,
                      m.created_at, COUNT(t.id) AS action_count
               FROM meetings m LEFT JOIN tasks t ON t.meeting_id = m.id
               GROUP BY m.id ORDER BY m.created_at DESC"""
        )
        for row in rows:
            row["participants"] = _load(row["participants"], [])
            result = _load(row.pop("result"), None) or {}
            row["executive_summary"] = (result.get("summary") or {}).get(
                "executive_summary"
            )
        return rows

    @staticmethod
    def _decode_meeting(row: dict[str, Any]) -> dict[str, Any]:
        row["participants"] = _load(row["participants"], [])
        row["user_participants"] = _load(row["user_participants"], [])
        row["result"] = _load(row["result"], None)
        row["title_generated"] = bool(row["title_generated"])
        return row

    # ----- people ---------------------------------------------------------

    def list_people(self) -> list[dict[str, Any]]:
        people = self._rows("SELECT * FROM people ORDER BY name")
        for p in people:
            p["responsibilities"] = _load(p["responsibilities"], [])
            p["ownership"] = _load(p["ownership"], [])
            p["aliases"] = _load(p["aliases"], [])
            p["is_user"] = bool(p["is_user"])
        return people

    def upsert_person(self, person: dict[str, Any]) -> None:
        if person.get("is_user"):
            # Only one user profile exists per workspace.
            self._write("UPDATE people SET is_user = 0 WHERE id != ?", (person["id"],))
        self._write(
            """INSERT INTO people (id, name, designation, responsibilities, ownership, aliases, manager_id, is_user)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name, designation=excluded.designation,
               responsibilities=excluded.responsibilities, ownership=excluded.ownership,
               aliases=excluded.aliases, manager_id=excluded.manager_id, is_user=excluded.is_user""",
            (
                person["id"],
                person["name"],
                person.get("designation", ""),
                _dump(person.get("responsibilities", [])),
                _dump(person.get("ownership", [])),
                _dump(person.get("aliases", [])),
                person.get("manager_id"),
                int(bool(person.get("is_user"))),
            ),
        )

    def delete_person(self, person_id: str) -> None:
        self._write(
            "UPDATE people SET manager_id = NULL WHERE manager_id = ?", (person_id,)
        )
        self._write("DELETE FROM people WHERE id = ?", (person_id,))

    # ----- tasks ----------------------------------------------------------

    def insert_task(
        self, meeting_id: str, item: dict[str, Any], embedding: bytes | None
    ) -> str:
        task_id = uuid.uuid4().hex
        now = _now()
        values = {
            "id": task_id,
            "meeting_id": meeting_id,
            "description": item["description"],
            "assignee": item.get("assignee"),
            "due_date": item.get("due_date"),
            "due_on": item.get("due_on"),
            "priority": item.get("priority", "medium"),
            "status": item.get("status", "not_started"),
            "assignment_type": item.get("assignment_type", "unassigned"),
            "category": item.get("category"),
            "verdict": item.get("verdict"),
            "evidence_ids": _dump(item.get("evidence_ids", [])),
            "dependencies": _dump(item.get("dependencies", [])),
            "verification_notes": _dump(item.get("verification_notes", [])),
            "embedding": embedding,
            "created_at": now,
            "updated_at": now,
        }
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        self._write(
            f"INSERT INTO tasks ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
        return task_id

    def update_task(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        self._write(
            f"UPDATE tasks SET {assignments} WHERE id = ?", (*fields.values(), task_id)
        )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self._decode_task(rows[0]) if rows else None

    def list_tasks(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if assignee:
            clauses.append("assignee = ?")
            params.append(assignee)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._rows(
            f"SELECT * FROM tasks {where} ORDER BY created_at DESC", tuple(params)
        )
        print("ROWS: ", [self._decode_task(r) for r in rows])
        return [self._decode_task(r) for r in rows]

    def open_tasks(self) -> list[dict[str, Any]]:
        rows = self._rows("SELECT * FROM tasks WHERE status != 'completed'")
        return [self._decode_task(r) for r in rows]

    @staticmethod
    def _decode_task(row: dict[str, Any]) -> dict[str, Any]:
        row["evidence_ids"] = _load(row["evidence_ids"], [])
        row["dependencies"] = _load(row["dependencies"], [])
        row["verification_notes"] = _load(row["verification_notes"], [])
        row["embedding"] = ""
        return row

    def add_history(
        self, task_id: str, meeting_id: str | None, event: str, detail: str
    ) -> None:
        self._write(
            "INSERT INTO task_history (task_id, meeting_id, event, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, meeting_id, event, detail, _now()),
        )

    def task_history(self, task_id: str) -> list[dict[str, Any]]:
        return self._rows(
            "SELECT * FROM task_history WHERE task_id = ? ORDER BY id", (task_id,)
        )
