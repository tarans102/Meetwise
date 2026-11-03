"""Prompt templates. Every user prompt begins with a 'TASK: <name>' line, which
also lets test doubles route requests deterministically."""

from __future__ import annotations

SYSTEM = (
    "You are MeetWise, an analyst that extracts structured information from meeting transcripts. "
    "Use only what the transcript states. Never invent names, dates, owners, or commitments. "
    "Cite utterance IDs such as U012 in evidence_ids for every claim. "
    "Respond with exactly one JSON object and nothing else."
)


def metadata_prompt(
    excerpt: str, known_people: str, detected_speakers: list[str]
) -> str:
    speakers = ", ".join(detected_speakers) or "none"
    return f"""TASK: metadata
Organisation directory:
{known_people}
Speakers detected in the transcript: {speakers}

Transcript excerpt:
{excerpt}

Return JSON with keys:
"title": 3 to 8 words, specific to the meeting's subject.
"participants": names of people who spoke or were explicitly named as attending.
"topics": 2 to 5 short topic names.
"context": one sentence describing the purpose of the meeting."""


def summary_prompt(excerpt: str) -> str:
    return f"""TASK: summary
Transcript:
{excerpt}

Return JSON with keys:
"executive_summary": 3 to 5 sentences covering what was discussed and concluded.
"key_points": list of the main discussion points.
"outcomes": list of concrete results or agreements reached."""


def partial_summary_prompt(excerpt: str) -> str:
    return f"""TASK: partial_summary
Transcript section (part of a longer meeting):
{excerpt}

Return JSON with keys "key_points" and "outcomes", each a list of short statements from this section only."""


def reduce_summary_prompt(partials_json: str) -> str:
    return f"""TASK: summary_reduce
The following are partial notes from consecutive sections of one meeting, in order:
{partials_json}

Combine them into JSON with keys:
"executive_summary": 3 to 5 sentences for the whole meeting.
"key_points": de-duplicated main discussion points.
"outcomes": de-duplicated concrete results."""


def segment_prompt(excerpt: str) -> str:
    return f"""TASK: segment
Transcript:
{excerpt}

Divide the transcript into contiguous discussion topics. Return JSON:
{{"topics": [{{"name": "short topic name", "start_id": "U001", "end_id": "U008"}}]}}
start_id and end_id must be utterance IDs that appear in the transcript above, and topics must not overlap."""


def actions_prompt(excerpt: str, known_people: str, feedback: str | None) -> str:
    retry = (
        f"\nA previous attempt was checked and these items were not supported: {feedback}\nOnly report commitments that the transcript clearly supports.\n"
        if feedback
        else ""
    )
    return f"""TASK: action_items
Organisation directory (use these exact names where a person is referenced):
{known_people}
{retry}
Transcript:
{excerpt}

Extract concrete tasks or commitments. Rules:
- Use assignment_type "explicit" only when the transcript itself names the owner for that task.
- Use "inferred" when ownership is implied by context, and say so.
- Use "unassigned" with assignee null when nobody is named. Never invent an assignee.
- Only include a due_date that is stated in the transcript; otherwise null.
- Put dependencies on other tasks or people in dependencies.
- Do not turn general discussion into tasks.

Return JSON:
{{"action_items": [{{"description": "...", "assignee": "name or null", "assignment_type": "explicit|inferred|unassigned", "due_date": "stated deadline or null", "priority": "high|medium|low", "status": "not_started|in_progress|completed|blocked", "dependencies": [], "evidence_ids": ["U002"]}}]}}"""


def decisions_prompt(excerpt: str) -> str:
    return f"""TASK: decisions
Transcript:
{excerpt}

Identify decisions and unresolved issues. Rules:
- "finalized" only when the group agreed. "pending" when a decision was deferred or still open.
- List alternatives that were actually considered, and the rationale only if it was stated.
- An unresolved issue is a problem or question raised but explicitly left open. Do not list topics that were simply discussed and closed.

Return JSON:
{{"decisions": [{{"statement": "...", "status": "finalized|pending", "alternatives": [], "rationale": null, "evidence_ids": ["U001"]}}],
"unresolved_issues": [{{"description": "...", "responsible": "name or null", "explicitly_unresolved": true, "evidence_ids": ["U004"]}}]}}"""


def events_prompt(excerpt: str) -> str:
    return f"""TASK: events
Transcript:
{excerpt}

Identify meetings, deadlines and events that were mentioned for the calendar. Rules:
- confidence "confirmed": a date and time were explicitly agreed.
- confidence "proposed": someone suggested it and it was not agreed.
- confidence "tentative": vague or conditional timing.
- Use null for any field the transcript does not state.

Return JSON:
{{"events": [{{"title": "...", "date": "YYYY-MM-DD or stated text or null", "start_time": null, "end_time": null, "participants": [], "location": null, "event_type": "meeting|deadline|general", "confidence": "confirmed|proposed|tentative", "evidence_ids": ["U003"]}}]}}"""


def verify_prompt(items_json: str) -> str:
    return f"""TASK: verify
Each item below was extracted from a meeting. Its "evidence" lists the transcript passages it cites.
Check whether each item is actually supported by its evidence and whether the assignee and deadline are supported.
{items_json}

Return JSON:
{{"verdicts": [{{"index": 0, "verdict": "confirmed|inferred|unsupported", "note": "short reason"}}],
"contradictions": [{{"description": "what conflicts", "evidence_ids": ["U001", "U007"]}}]}}
Use "inferred" when the item is plausible but not explicitly stated. Use "unsupported" when the evidence does not back it."""
