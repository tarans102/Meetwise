"""Offline lexical embedder (signed feature hashing). No model server required.

It captures word overlap rather than meaning, so it is a development and fallback
option. Production retrieval should use a real embedding model.
"""

from __future__ import annotations

import zlib

import numpy as np

from meetwise.textutils import tokenize


class HashingEmbedder:
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hashing:{dim}"

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                h = zlib.crc32(token.encode("utf-8"))
                sign = 1.0 if (h >> 16) & 1 else -1.0
                out[row, h % self.dim] += sign
            norm = np.linalg.norm(out[row])
            if norm:
                out[row] /= norm
        return out
