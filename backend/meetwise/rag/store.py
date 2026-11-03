"""Vector store with metadata filtering and hybrid (semantic + keyword) scoring.

Stored in the same SQLite database as the rest of the application, so it needs no
extra service. Search is an exact scan, which is appropriate for organisational
meeting volumes; swap in an ANN index behind this same interface if that changes.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from meetwise.rag.chunker import Chunk
from meetwise.storage.db import Database
from meetwise.textutils import normalize_name, tokenize


@dataclass
class SearchFilters:
    meeting_ids: list[str] | None = None
    title_contains: str | None = None
    date_from: str | None = None  # ISO yyyy-mm-dd, inclusive
    date_to: str | None = None
    participants: list[str] | None = None  # any-of
    content_types: list[str] | None = None
    topic_contains: str | None = None
    assignee: str | None = None
    status: str | None = None

    def matches(self, meta: dict[str, Any]) -> bool:
        if self.meeting_ids and meta.get("meeting_id") not in self.meeting_ids:
            return False
        if (
            self.title_contains
            and self.title_contains.lower()
            not in (meta.get("meeting_title") or "").lower()
        ):
            return False
        date = meta.get("meeting_date") or ""
        if self.date_from and (not date or date < self.date_from):
            return False
        if self.date_to and (not date or date > self.date_to):
            return False
        if self.participants:
            present = {normalize_name(p) for p in meta.get("participants") or []}
            if not any(normalize_name(p) in present for p in self.participants):
                return False
        if self.content_types and meta.get("content_type") not in self.content_types:
            return False
        if (
            self.topic_contains
            and self.topic_contains.lower() not in (meta.get("topic") or "").lower()
        ):
            return False
        if self.assignee and normalize_name(
            meta.get("assignee") or ""
        ) != normalize_name(self.assignee):
            return False
        if self.status and meta.get("status") != self.status:
            return False
        return True


@dataclass
class Hit:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    semantic: float
    keyword: float
    score: float = field(default=0.0)


class VectorStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def replace_meeting(
        self, meeting_id: str, chunks: list[Chunk], embeddings: np.ndarray
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts differ.")
        rows = [
            (
                c.id,
                meeting_id,
                c.text,
                json.dumps(c.metadata, ensure_ascii=False),
                np.asarray(e, dtype=np.float32).tobytes(),
                int(len(e)),
            )
            for c, e in zip(chunks, embeddings)
        ]
        with self.db.lock:
            self.db.conn.execute(
                "DELETE FROM chunks WHERE meeting_id = ?", (meeting_id,)
            )
            self.db.conn.executemany(
                "INSERT INTO chunks (id, meeting_id, text, metadata, embedding, dim) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            self.db.conn.commit()

    def update_meeting_metadata(self, meeting_id: str, updates: dict[str, Any]) -> None:
        """Propagate meeting-level edits (e.g. a renamed title) to every chunk."""
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT id, metadata FROM chunks WHERE meeting_id = ?", (meeting_id,)
            ).fetchall()
            for row in rows:
                meta = json.loads(row["metadata"])
                meta.update(updates)
                self.db.conn.execute(
                    "UPDATE chunks SET metadata = ? WHERE id = ?",
                    (json.dumps(meta, ensure_ascii=False), row["id"]),
                )
            self.db.conn.commit()

    def search(
        self,
        query_vec: np.ndarray,
        query_text: str,
        filters: SearchFilters | None,
        k: int,
        alpha: float,
        min_score: float,
    ) -> list[Hit]:
        with self.db.lock:
            rows = self.db.conn.execute(
                "SELECT id, text, metadata, embedding, dim FROM chunks"
            ).fetchall()

        candidates = []
        for row in rows:
            meta = json.loads(row["metadata"])
            if filters is not None and not filters.matches(meta):
                continue
            if row["dim"] != query_vec.shape[0]:
                continue  # embedded with a different model; not comparable
            vector = np.frombuffer(row["embedding"], dtype=np.float32)
            candidates.append((row["id"], row["text"], meta, vector))
        if not candidates:
            return []

        query = query_vec.astype(np.float32)
        q_norm = np.linalg.norm(query) or 1.0
        matrix = np.stack([c[3] for c in candidates])
        norms = np.linalg.norm(matrix, axis=1)
        norms[norms == 0] = 1.0
        semantic = np.clip((matrix / norms[:, None]) @ (query / q_norm), 0.0, 1.0)

        # BM25-style keyword score over the candidate set (IDF-weighted term coverage).
        query_terms = set(tokenize(query_text))
        doc_terms = [set(tokenize(c[1])) for c in candidates]
        doc_freq: Counter[str] = Counter()
        for terms in doc_terms:
            doc_freq.update(terms & query_terms)
        n_docs = len(candidates)
        idf = {t: math.log((n_docs + 1) / (doc_freq[t] + 1)) + 1.0 for t in query_terms}
        idf_total = sum(idf.values()) or 1.0
        keyword = [
            sum(idf[t] for t in query_terms if t in terms) / idf_total
            for terms in doc_terms
        ]

        hits: list[Hit] = []
        for i, (chunk_id, text, meta, _) in enumerate(candidates):
            sem, kw = float(semantic[i]), float(keyword[i])
            score = alpha * sem + (1.0 - alpha) * kw
            if score >= min_score:
                hits.append(Hit(chunk_id, text, meta, sem, kw, score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]
