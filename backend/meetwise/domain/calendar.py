"""Turns extracted, free-text dates and times into calendar values.

Unparseable dates return None, so the event or deadline is kept for review rather
than placed on the calendar with a guessed date.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_DATE_FORMATS = ["%Y-%m-%d", "%d %B %Y", "%B %d %Y", "%d %b %Y", "%b %d %Y"]
_YEARLESS_FORMATS = ["%d %B", "%B %d", "%d %b", "%b %d"]
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_LEADING = re.compile(r"^(by|on|this|the)\s+")
_TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", re.IGNORECASE)


def reference_date(meeting_date: str | None) -> date:
    """The date that relative phrases ('Friday', 'tomorrow') are resolved against."""
    if meeting_date:
        try:
            return date.fromisoformat(str(meeting_date)[:10])
        except ValueError:
            pass
    return date.today()


def parse_date(text: str | None, reference: date) -> date | None:
    if not text:
        return None
    cleaned = " ".join(str(text).replace(",", " ").split())
    lowered = cleaned.lower()
    if lowered in ("today", "tonight"):
        return reference
    if lowered == "tomorrow":
        return reference + timedelta(days=1)

    words = _LEADING.sub("", lowered).split()
    following_week = bool(words) and words[0] == "next"
    if following_week:
        words = words[1:]
    if len(words) == 1 and words[0] in _WEEKDAYS:
        # The next occurrence on or after the reference date; "next X" adds a week.
        offset = (_WEEKDAYS[words[0]] - reference.weekday()) % 7
        return reference + timedelta(days=offset + (7 if following_week else 0))

    stripped = _LEADING.sub("", lowered)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).date()
        except ValueError:
            pass
    for fmt in _YEARLESS_FORMATS:  # no year given: assume the reference year
        try:
            return datetime.strptime(f"{stripped} {reference.year}", f"{fmt} %Y").date()
        except ValueError:
            pass
    return None


def parse_time(text: str | None) -> str | None:
    match = _TIME.match(text or "")
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    suffix = (match.group(3) or "").lower()
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def parse_when(
    date_text: str | None, start_time: str | None, end_time: str | None, reference: date
) -> dict:
    day = parse_date(date_text, reference)
    if day is None:
        return {"starts_at": None, "ends_at": None, "all_day": True}
    start = parse_time(start_time)
    if start is None:
        return {"starts_at": day.isoformat(), "ends_at": None, "all_day": True}
    end = parse_time(end_time)
    return {
        "starts_at": f"{day.isoformat()}T{start}",
        "ends_at": f"{day.isoformat()}T{end}" if end else None,
        "all_day": False,
    }
