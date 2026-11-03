"""HTTP API. Thin layer: validation and orchestration only, no business logic."""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from meetwise.config import settings
from meetwise.ingest.extract import (
    SUPPORTED_EXTENSIONS,
    UnsupportedFormatError,
    extract_text,
)
from meetwise.llm.providers import build_chat_model, build_embedder
from meetwise.services.transcript import transcript_lines
from meetwise.rag.retriever import Retriever
from meetwise.rag.store import SearchFilters, VectorStore
from meetwise.services.pipeline import MeetingPipeline
from meetwise.storage.db import Database
from meetwise.storage.calendar_repo import CalendarRepository
from meetwise.storage.chat_repo import ChatRepository
from meetwise.storage.repository import Repository
from meetwise.chat.service import ChatService
from datetime import date as _date

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="MeetWise API", version="0.1.0")


@lru_cache
def services() -> dict:
    db = Database(settings.db_path)
    repo = Repository(db)
    embedder = build_embedder(settings)
    store = VectorStore(db)
    chat = build_chat_model(settings)
    retriever = Retriever(store, embedder)
    return {
        "repo": repo,
        "store": store,
        "retriever": retriever,
        "pipeline": MeetingPipeline(
            settings=settings, repo=repo, store=store, embedder=embedder, chat=chat
        ),
        "chat": ChatService(
            chat_model=chat, retriever=retriever, repo=repo, store=ChatRepository(db)
        ),
        "chat_store": ChatRepository(db),
        "calendar": CalendarRepository(db),
    }


class MeetingPatch(BaseModel):
    title: str | None = None
    meeting_date: str | None = None
    participants: list[str] | None = None


class TaskPatch(BaseModel):
    status: str | None = Field(
        default=None, pattern="^(not_started|in_progress|completed|blocked)$"
    )


class PersonIn(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    designation: str = ""
    responsibilities: list[str] = []
    ownership: list[str] = []
    aliases: list[str] = []
    manager_id: str | None = None
    is_user: bool = False


class SearchIn(BaseModel):
    query: str
    k: int = Field(default=6, ge=1, le=50)
    meeting_ids: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    participants: list[str] | None = None
    content_types: list[str] | None = None


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
    }


@app.post("/api/meetings", status_code=202)
async def upload_meeting(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user_title: str | None = Form(None),
    user_date: str | None = Form(None),
    user_participants: str | None = Form(None),
) -> dict:
    filename = file.filename or "transcript.txt"
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        raise HTTPException(415, "Upload a TXT, PDF, or DOCX transcript.")
    try:
        text = extract_text(filename, await file.read())
    except UnsupportedFormatError as exc:
        raise HTTPException(415, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, f"Could not read this file: {exc}") from exc
    if not text.strip():
        raise HTTPException(422, "The file contains no extractable text.")

    svc = services()
    participants = [
        p.strip() for p in (user_participants or "").split(",") if p.strip()
    ]
    meeting_id = svc["repo"].create_meeting(
        source_filename=filename,
        raw_text=text,
        user_title=(user_title or "").strip() or None,
        user_date=(user_date or "").strip() or None,
        user_participants=participants,
    )
    background.add_task(svc["pipeline"].process, meeting_id)
    return {"id": meeting_id, "status": "queued"}


@app.get("/api/meetings")
def list_meetings() -> list[dict]:
    return services()["repo"].list_meetings()


@app.get("/api/meetings/{meeting_id}")
def get_meeting(meeting_id: str) -> dict:
    meeting = services()["repo"].get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found.")
    meeting.pop("raw_text", None)
    return meeting


@app.patch("/api/meetings/{meeting_id}")
def edit_meeting(meeting_id: str, patch: MeetingPatch) -> dict:
    svc = services()
    meeting = svc["repo"].get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found.")
    fields: dict = {}
    if patch.title is not None:
        fields.update(title=patch.title.strip(), title_generated=False)
    if patch.meeting_date is not None:
        fields["meeting_date"] = patch.meeting_date
    if patch.participants is not None:
        fields["participants"] = patch.participants
    svc["repo"].update_meeting(meeting_id, **fields)
    if patch.title is not None:
        svc["store"].update_meeting_metadata(
            meeting_id, {"meeting_title": patch.title.strip()}
        )
    return {"id": meeting_id, "updated": list(fields)}


@app.get("/api/tasks")
def list_tasks(
    category: str | None = None, status: str | None = None, assignee: str | None = None
) -> list[dict]:
    print(services()["repo"])
    return services()["repo"].list_tasks(
        category=category, status=status, assignee=assignee
    )


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, patch: TaskPatch) -> dict:
    svc = services()
    task = svc["repo"].get_task(task_id)
    if task is None:
        raise HTTPException(404, "Task not found.")
    if patch.status and patch.status != task["status"]:
        svc["repo"].update_task(task_id, status=patch.status)
        svc["repo"].add_history(
            task_id,
            task["meeting_id"],
            "status_changed",
            f"{task['status']} -> {patch.status} (set by user).",
        )
    return svc["repo"].get_task(task_id)


@app.get("/api/tasks/{task_id}/history")
def task_history(task_id: str) -> list[dict]:
    return services()["repo"].task_history(task_id)


@app.get("/api/people")
def list_people() -> list[dict]:
    return services()["repo"].list_people()


@app.put("/api/people/{person_id}")
def upsert_person(person_id: str, person: PersonIn) -> dict:
    data = person.model_dump()
    data["id"] = person_id
    services()["repo"].upsert_person(data)
    return data


@app.delete("/api/people/{person_id}", status_code=204)
def delete_person(person_id: str) -> None:
    services()["repo"].delete_person(person_id)


@app.post("/api/search")
def search(body: SearchIn) -> list[dict]:
    filters = SearchFilters(
        meeting_ids=body.meeting_ids,
        date_from=body.date_from,
        date_to=body.date_to,
        participants=body.participants,
        content_types=body.content_types,
    )
    hits = services()["retriever"].search(body.query, filters=filters, k=body.k)
    return [
        {
            "chunk_id": h.chunk_id,
            "text": h.text,
            "score": round(h.score, 4),
            "semantic": round(h.semantic, 4),
            "keyword": round(h.keyword, 4),
            "metadata": h.metadata,
        }
        for h in hits
    ]


# ----- chat ---------------------------------------------------------------


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default="all", pattern="^(meeting|all)$")
    meeting_id: str | None = None
    session_id: str | None = None


@app.post("/api/chat")
def chat_turn(body: ChatIn) -> dict:
    try:
        return services()["chat"].ask(
            body.question,
            scope=body.scope,
            meeting_id=body.meeting_id,
            session_id=body.session_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/chat/sessions")
def list_chat_sessions() -> list[dict]:
    return services()["chat_store"].list_sessions()


@app.get("/api/chat/sessions/{session_id}")
def get_chat_session(session_id: str) -> dict:
    store = services()["chat_store"]
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Chat session not found.")
    return {**session, "messages": store.list_messages(session_id)}


# ----- local calendar -----------------------------------------------------


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    starts_at: str | None = None
    ends_at: str | None = None
    all_day: bool = False
    event_type: str = Field(default="general", pattern="^(meeting|deadline|general)$")
    location: str | None = None
    participants: list[str] = []
    notes: str | None = None


class EventPatch(BaseModel):
    title: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    all_day: bool | None = None
    event_type: str | None = Field(default=None, pattern="^(meeting|deadline|general)$")
    review_status: str | None = Field(default=None, pattern="^(tentative|confirmed)$")
    location: str | None = None
    participants: list[str] | None = None
    notes: str | None = None
    completed: bool | None = None


@app.get("/api/events")
def list_events(start: str | None = None, end: str | None = None) -> list[dict]:
    return services()["calendar"].list_events(start=start, end=end)


@app.get("/api/events/pending")
def pending_events() -> list[dict]:
    return services()["calendar"].list_pending()


@app.post("/api/events", status_code=201)
def create_event(body: EventIn) -> dict:
    cal = services()["calendar"]
    event_id = cal.create_event(**body.model_dump(), review_status="confirmed")
    return cal.get_event(event_id)


@app.patch("/api/events/{event_id}")
def update_event(event_id: str, body: EventPatch) -> dict:
    cal = services()["calendar"]
    if cal.get_event(event_id) is None:
        raise HTTPException(404, "Event not found.")
    cal.update_event(event_id, **body.model_dump(exclude_none=True))
    return cal.get_event(event_id)


@app.post("/api/events/{event_id}/confirm")
def confirm_event(event_id: str, body: EventPatch | None = None) -> dict:
    cal = services()["calendar"]
    if cal.get_event(event_id) is None:
        raise HTTPException(404, "Event not found.")
    overrides = (
        body.model_dump(exclude_none=True, exclude={"review_status"}) if body else {}
    )
    cal.confirm(event_id, **overrides)
    return cal.get_event(event_id)


@app.delete("/api/events/{event_id}", status_code=204)
def delete_event(event_id: str) -> None:
    services()["calendar"].delete_event(event_id)


@app.get("/api/meetings/{meeting_id}/transcript")
def get_transcript(meeting_id: str) -> list[dict]:
    meeting = services()["repo"].get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found.")
    return transcript_lines(meeting["raw_text"])
