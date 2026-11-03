"""Deterministic test doubles: a scripted chat model that routes on the TASK line."""
from __future__ import annotations

import copy
import json

SAMPLE_TRANSCRIPT = """Priya: Let's finalize the launch date. The vendor says 14 November works for them.
Rahul: Okay, I will send the revised launch checklist by Friday.
Priya: Good. We agreed on 14 November as the launch date.
Rahul: I'm waiting on legal before I can sign off the press release.
"""

DEFAULT_RESPONSES = {
    "metadata": {"title": "Q3 Launch Planning", "participants": ["Priya", "Rahul"],
                 "topics": ["launch date"], "context": "Planning the Q3 product launch."},
    "summary": {"executive_summary": "The team fixed the launch date and assigned a checklist.",
                "key_points": ["Launch date discussed"], "outcomes": ["Launch set for 14 November"]},
    "segment": {"topics": [{"name": "Launch date", "start_id": "U001", "end_id": "U004"}]},
    "decisions": {"decisions": [{"statement": "Launch on 14 November", "status": "finalized",
                                 "alternatives": ["7 November"], "rationale": "Vendor availability",
                                 "evidence_ids": ["U001", "U003"]}],
                  "unresolved_issues": [{"description": "Press release sign-off pending legal review",
                                         "responsible": "Rahul", "explicitly_unresolved": True,
                                         "evidence_ids": ["U004"]}]},
    "events": {"events": []},
    "action_items": {"action_items": [{
        "description": "Send the revised launch checklist", "assignee": "Rahul",
        "assignment_type": "explicit", "due_date": "Friday", "priority": "high",
        "status": "not_started", "dependencies": [], "evidence_ids": ["U002"]}]},
    "verify": {"verdicts": [{"index": 0, "verdict": "confirmed", "note": ""}], "contradictions": []},
}


class ScriptedChat:
    """Returns canned JSON per TASK. A list value is consumed one entry per call."""

    name = "scripted"

    def __init__(self, overrides: dict | None = None) -> None:
        self.responses = copy.deepcopy(DEFAULT_RESPONSES)
        self.responses.update(overrides or {})
        self.calls: list[str] = []

    def complete(self, system: str, user: str) -> str:
        task = user.splitlines()[0].replace("TASK:", "").strip()
        self.calls.append(task)
        value = self.responses.get(task, {})
        if isinstance(value, list):
            value = value.pop(0) if len(value) > 1 else value[0]
        if isinstance(value, str):
            return value  # raw, possibly malformed output
        return json.dumps(value)


def sample_org():
    from meetwise.domain.org import OrgContext, Person

    return OrgContext([
        Person(id="p1", name="Priya Nair", designation="Head of Product", responsibilities=["product launch"],
               ownership=["roadmap"], aliases=["Priya"], is_user=True),
        Person(id="p2", name="Rahul Mehta", designation="Engineering Lead", aliases=["Rahul"], manager_id="p1",
               responsibilities=["launch checklist", "engineering delivery"]),
        Person(id="p3", name="Sam Okafor", designation="Legal Counsel", aliases=["Sam"]),
    ])
