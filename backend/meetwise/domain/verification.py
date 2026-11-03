"""Deterministic grounding checks. These run before any LLM-based verification.

They confirm that cited evidence exists, that the description overlaps the cited
text, that an explicit assignee is actually named in that text, and that any
deadline is present in the evidence. Unsupported detail is removed or downgraded
rather than presented as confirmed.
"""

from __future__ import annotations

from meetwise.domain.models import ActionItem
from meetwise.domain.org import OrgContext
from meetwise.ingest.transcript import Utterance
from meetwise.textutils import contains_phrase, token_overlap, tokenize


def _date_supported(due: str, evidence_text: str) -> bool:
    tokens = tokenize(due)
    if not tokens:
        return True
    evidence_tokens = set(tokenize(evidence_text))
    return any(token in evidence_tokens for token in tokens)


def verify_action_item(
    item: ActionItem, utterances: dict[str, Utterance], org: OrgContext
) -> tuple[str, list[str]]:
    """Mutates `item` where needed and returns (verdict, notes)."""
    cited = [utterances[i] for i in item.evidence_ids if i in utterances]
    if not cited:
        item.evidence_ids = []
        return "unsupported", ["No valid transcript evidence was cited."]

    notes: list[str] = []
    verdict = "confirmed"
    evidence_text = " ".join(u.text for u in cited)

    overlap = token_overlap(item.description, evidence_text)
    if overlap < 0.2:
        verdict = "unsupported"
        notes.append("The description is not supported by the cited passages.")
    elif overlap < 0.4:
        verdict = "inferred"
        notes.append("The description only partly matches the cited passages.")

    if item.assignee is None:
        item.assignment_type = "unassigned"
    elif item.assignment_type == "explicit":
        person = org.resolve(item.assignee)
        names = person.names() if person else [item.assignee]
        # A speaker committing in the first person ("I will send it") is an explicit owner,
        # so the speaker label counts as a naming of that person.
        speakers = " ".join(u.speaker or "" for u in cited)
        searchable = f"{evidence_text} {speakers}"
        if not any(contains_phrase(searchable, name) for name in names):
            item.assignment_type = "inferred"
            notes.append(
                "The assignee is not named in the cited passages, so the assignment is inferred."
            )

    if item.assignment_type == "inferred":
        verdict = "inferred" if verdict == "confirmed" else verdict

    if item.due_date and not _date_supported(item.due_date, evidence_text):
        notes.append(
            f"The deadline '{item.due_date}' does not appear in the cited passages and was removed."
        )
        item.due_date = None

    return verdict, notes
