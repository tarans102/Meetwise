"""Transcript view for the UI. Re-derives utterances from the stored raw text.

Parsing is deterministic, so the IDs match the ones the pipeline used for
citations, action-item evidence, and topic groupings.
"""

from __future__ import annotations

from meetwise.ingest.transcript import parse_utterances


def transcript_lines(raw_text: str) -> list[dict]:
    return [u.to_dict() for u in parse_utterances(raw_text)]
