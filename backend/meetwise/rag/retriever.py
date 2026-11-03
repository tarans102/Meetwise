"""Reusable retrieval facade. Chat, duplicate detection and linking all use this,
so none of them depend on the chat feature."""

from __future__ import annotations

import numpy as np

from meetwise.llm.base import Embedder
from meetwise.rag.store import Hit, SearchFilters, VectorStore


class Retriever:
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self.store = store
        self.embedder = embedder

    def _embed(self, text: str) -> np.ndarray | None:
        vectors = self.embedder.embed([text])
        return vectors[0] if vectors.size else None

    def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        k: int = 6,
        alpha: float = 0.6,
        min_score: float = 0.12,
    ) -> list[Hit]:
        """Hybrid retrieval: semantic similarity blended with keyword coverage."""
        vector = self._embed(query)
        if vector is None:
            return []
        return self.store.search(vector, query, filters, k, alpha, min_score)

    def find_similar(
        self,
        text: str,
        filters: SearchFilters | None = None,
        k: int = 3,
        min_score: float = 0.5,
    ) -> list[Hit]:
        """Semantic-only lookup, e.g. for checking whether a commitment already exists."""
        vector = self._embed(text)
        if vector is None:
            return []
        return self.store.search(
            vector, text, filters, k, alpha=1.0, min_score=min_score
        )
