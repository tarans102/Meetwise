"""SQLite connection and schema. Shared by the repository and the vector store."""

from __future__ import annotations

import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    title TEXT,
    title_generated INTEGER NOT NULL DEFAULT 0,
    meeting_date TEXT,
    participants TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    stage TEXT,
    error TEXT,
    source_filename TEXT,
    raw_text TEXT NOT NULL,
    user_title TEXT,
    user_date TEXT,
    user_participants TEXT NOT NULL DEFAULT '[]',
    result TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    designation TEXT NOT NULL DEFAULT '',
    responsibilities TEXT NOT NULL DEFAULT '[]',
    ownership TEXT NOT NULL DEFAULT '[]',
    aliases TEXT NOT NULL DEFAULT '[]',
    manager_id TEXT,
    is_user INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    description TEXT NOT NULL,
    assignee TEXT,
    due_date TEXT,
    due_on TEXT,
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    assignment_type TEXT NOT NULL,
    category TEXT,
    verdict TEXT,
    evidence_ids TEXT NOT NULL DEFAULT '[]',
    dependencies TEXT NOT NULL DEFAULT '[]',
    verification_notes TEXT NOT NULL DEFAULT '[]',
    embedding BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    meeting_id TEXT,
    event TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    text TEXT NOT NULL,
    metadata TEXT NOT NULL,
    embedding BLOB NOT NULL,
    dim INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_meeting ON chunks(meeting_id);
CREATE INDEX IF NOT EXISTS idx_tasks_meeting ON tasks(meeting_id);
"""


EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    scope TEXT NOT NULL,
    meeting_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations TEXT NOT NULL DEFAULT '[]',
    status TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    starts_at TEXT,
    ends_at TEXT,
    all_day INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL DEFAULT 'general',
    review_status TEXT NOT NULL DEFAULT 'confirmed',
    extracted_confidence TEXT,
    date_text TEXT,
    location TEXT,
    participants TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    source_meeting_id TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_source ON calendar_events(source_meeting_id);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring databases created before `due_on` existed up to date, then backfill it."""
    from meetwise.domain.calendar import parse_date, reference_date

    columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "due_on" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN due_on TEXT")
    rows = conn.execute("""SELECT t.id, t.due_date, m.user_date, m.created_at
           FROM tasks t JOIN meetings m ON m.id = t.meeting_id
           WHERE t.due_on IS NULL AND t.due_date IS NOT NULL""").fetchall()
    for task_id, due_text, user_date, created_at in rows:
        resolved = parse_date(
            due_text, reference_date(user_date or (created_at or "")[:10])
        )
        if resolved:
            conn.execute(
                "UPDATE tasks SET due_on = ? WHERE id = ?",
                (resolved.isoformat(), task_id),
            )
    conn.commit()


class Database:
    def __init__(self, path: str = ":memory:") -> None:
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA + EXTRA_SCHEMA)
        self.conn.commit()
        _migrate(self.conn)
