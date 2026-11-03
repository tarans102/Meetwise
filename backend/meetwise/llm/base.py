"""Provider-agnostic interfaces. Nothing outside this package imports a provider SDK directly."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import numpy as np


class LLMOutputError(ValueError):
    """The model returned something that is not a usable JSON object."""


class ChatModel(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, d) float32 array, one row per input text."""
        ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(raw: str) -> dict[str, Any]:
    text = _FENCE.sub("", (raw or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMOutputError("The model response contained no JSON object.")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMOutputError(
            f"The model response was not valid JSON: {exc.msg}."
        ) from exc
    if not isinstance(value, dict):
        raise LLMOutputError("The model response was JSON but not an object.")
    return value


def complete_json(
    model: ChatModel, system: str, user: str, attempts: int = 2
) -> dict[str, Any]:
    """Ask for JSON, retrying once on malformed output."""
    last_error: LLMOutputError | None = None
    for _ in range(max(1, attempts)):
        try:
            return parse_json_object(model.complete(system, user))
        except LLMOutputError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error
