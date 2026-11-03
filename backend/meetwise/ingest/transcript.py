"""Transcript cleaning, utterance parsing, and windowing for long transcripts.

Supported line shapes:
    Rahul: text
    [00:12:03] Rahul: text
    Rahul (00:12): text
Lines that do not start a new speaker turn are appended to the previous turn.
Speakerless transcripts are split into paragraphs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_SPEAKER_LINE = re.compile(
    r"^\s*(?:\[(?P<ts_a>\d{1,2}:\d{2}(?::\d{2})?)\]\s*)?"
    r"(?P<speaker>[A-Z][A-Za-z .'-]{0,40}?)\s*"
    r"(?:\((?P<ts_b>\d{1,2}:\d{2}(?::\d{2})?)\))?\s*:\s*(?P<text>\S.*)$"
)


@dataclass
class Utterance:
    id: str
    text: str
    speaker: str | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Utterance":
        return cls(**data)

    def render(self) -> str:
        parts = [f"[{self.id}]"]
        if self.timestamp:
            parts.append(f"[{self.timestamp}]")
        if self.speaker:
            parts.append(f"{self.speaker}:")
        parts.append(self.text)
        return " ".join(parts)


def clean_transcript(raw: str) -> str:
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = text.replace("\u00a0", " ")
    cleaned: list[str] = []
    previous_blank = True
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            if not previous_blank:
                cleaned.append("")
            previous_blank = True
            continue
        cleaned.append(line)
        previous_blank = False
    return "\n".join(cleaned).strip()


def parse_utterances(raw: str) -> list[Utterance]:
    text = clean_transcript(raw)
    records: list[dict] = []
    current: dict | None = None
    speaker_lines = 0

    for line in text.split("\n"):
        if not line:
            continue
        match = _SPEAKER_LINE.match(line)
        if match:
            speaker_lines += 1
            if current:
                records.append(current)
            current = {
                "speaker": match.group("speaker").strip(),
                "timestamp": match.group("ts_a") or match.group("ts_b"),
                "text": match.group("text").strip(),
            }
        elif current is not None:
            current["text"] += " " + line
        else:
            current = {"speaker": None, "timestamp": None, "text": line}
    if current:
        records.append(current)

    if speaker_lines == 0:
        records = [
            {"speaker": None, "timestamp": None, "text": " ".join(p.split())}
            for p in text.split("\n\n")
            if p.strip()
        ]

    return [
        Utterance(
            id=f"U{i:03d}",
            text=r["text"],
            speaker=r["speaker"],
            timestamp=r["timestamp"],
        )
        for i, r in enumerate(records, start=1)
    ]


def render_utterances(utterances: list[Utterance]) -> str:
    return "\n".join(u.render() for u in utterances)


def make_windows(utterances: list[Utterance], max_chars: int) -> list[list[Utterance]]:
    """Group consecutive utterances so each window stays near max_chars.

    A single utterance longer than the budget still forms its own window.
    """
    windows: list[list[Utterance]] = []
    current: list[Utterance] = []
    size = 0
    for utterance in utterances:
        length = len(utterance.render()) + 1
        if current and size + length > max_chars:
            windows.append(current)
            current, size = [], 0
        current.append(utterance)
        size += length
    if current:
        windows.append(current)
    return windows
