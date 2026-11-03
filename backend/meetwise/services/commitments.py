"""Cross-meeting commitment tracking.

For each newly extracted action item, look for an open task with the same owner
and a closely matching description. If one exists, record the re-mention and any
change to deadline or status in the task's history, instead of creating a duplicate.

Each item also gets `due_on`, its deadline resolved to a calendar date against the
meeting date ("Friday" said in a meeting on 28 Oct becomes 2026-10-30).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from meetwise.domain.calendar import parse_date, reference_date
from meetwise.llm.base import Embedder
from meetwise.storage.repository import Repository
from meetwise.textutils import normalize_name

MATCH_THRESHOLD = 0.8
_ACTIVE_STATUSES = frozenset({"in_progress", "completed", "blocked"})


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def _deadline_label(task_or_item: dict[str, Any]) -> str:
    return task_or_item.get("due_on") or task_or_item.get("due_date") or "no deadline"


def reconcile_action_items(
    repo: Repository,
    embedder: Embedder,
    meeting: dict[str, Any],
    items: list[dict[str, Any]],
    threshold: float = MATCH_THRESHOLD,
) -> list[dict[str, Any]]:
    mid = meeting["id"]
    label = f"'{meeting['title']}' ({meeting.get('date') or 'undated'})"
    reference = reference_date(meeting.get("date"))

    open_tasks = []
    for task in repo.open_tasks():
        blob = task.get("embedding")
        task["vector"] = np.frombuffer(blob, dtype=np.float32).copy() if blob else None
        open_tasks.append(task)

    for item in items:
        resolved = parse_date(item.get("due_date"), reference)
        item["due_on"] = resolved.isoformat() if resolved else None

        vector = embedder.embed([item["description"]])
        vector = vector[0] if vector.size else None
        owner = normalize_name(item.get("assignee") or "")

        best, best_score = None, 0.0
        if vector is not None:
            for task in open_tasks:
                if (
                    normalize_name(task.get("assignee") or "") != owner
                    or task.get("vector") is None
                ):
                    continue
                score = _cosine(vector, task["vector"])
                if score > best_score:
                    best, best_score = task, score

        if best is not None and best_score >= threshold:
            task_id = best["id"]
            repo.add_history(
                task_id, mid, "mentioned_again", f"Discussed again in {label}."
            )
            updates: dict[str, Any] = {}
            new_due_on = item["due_on"]
            new_due_text = item.get("due_date")
            deadline_moved = (new_due_on and new_due_on != best.get("due_on")) or (
                not new_due_on and new_due_text and new_due_text != best.get("due_date")
            )
            if deadline_moved:
                repo.add_history(
                    task_id,
                    mid,
                    "deadline_changed",
                    f"{_deadline_label(best)} -> {_deadline_label(item)} (in {label}).",
                )
                updates["due_on"] = new_due_on or best.get("due_on")
                updates["due_date"] = new_due_text or best.get("due_date")
            new_status = item.get("status")
            if new_status in _ACTIVE_STATUSES and new_status != best.get("status"):
                repo.add_history(
                    task_id,
                    mid,
                    "status_changed",
                    f"{best.get('status')} -> {new_status} (in {label}).",
                )
                updates["status"] = new_status
            repo.update_task(task_id, **updates)
            best.update(updates)
            item["task_id"] = task_id
            item["reconciliation"] = "existing"
        else:
            blob = vector.astype(np.float32).tobytes() if vector is not None else None
            task_id = repo.insert_task(mid, item, blob)
            repo.add_history(task_id, mid, "created", f"Recorded from {label}.")
            open_tasks.append(
                {
                    "id": task_id,
                    "assignee": item.get("assignee"),
                    "due_date": item.get("due_date"),
                    "due_on": item["due_on"],
                    "status": item.get("status", "not_started"),
                    "vector": vector,
                }
            )
            item["task_id"] = task_id
            item["reconciliation"] = "new"
    return items
