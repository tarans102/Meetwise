from meetwise.domain.attribution import classify_action_item
from meetwise.domain.models import ActionItem, Event
from meetwise.domain.verification import verify_action_item
from meetwise.ingest.transcript import parse_utterances
from tests.fakes import SAMPLE_TRANSCRIPT, sample_org


def _utts():
    return {u.id: u for u in parse_utterances(SAMPLE_TRANSCRIPT)}


def test_unassigned_is_never_invented():
    item = ActionItem.from_llm({"description": "Book the venue", "assignee": "TBD",
                                "assignment_type": "explicit", "evidence_ids": ["U001"]})
    assert item.assignee is None and item.assignment_type == "unassigned"


def test_alias_resolves_to_subordinate_as_team_responsibility():
    org = sample_org()
    item = ActionItem.from_llm({"description": "Send the revised launch checklist", "assignee": "Rahul",
                                "assignment_type": "explicit", "evidence_ids": ["U002"]})
    texts = {k: v.text for k, v in _utts().items()}
    classify_action_item(item, org, texts)
    assert item.category == "team"


def test_direct_responsibility_for_current_user():
    org = sample_org()
    item = ActionItem.from_llm({"description": "Finalize the launch date", "assignee": "Priya",
                                "evidence_ids": ["U001"]})
    classify_action_item(item, org, {k: v.text for k, v in _utts().items()})
    assert item.category == "direct"


def test_other_person_linked_to_user_is_dependency_and_unrelated_is_not_relevant():
    org = sample_org()
    texts = {k: v.text for k, v in _utts().items()}
    linked = ActionItem.from_llm({"description": "Review the contract", "assignee": "Sam",
                                  "dependencies": ["Priya approval"], "evidence_ids": ["U004"]})
    classify_action_item(linked, org, texts)
    assert linked.category == "dependency"
    unrelated = ActionItem.from_llm({"description": "Order new office chairs", "assignee": "Sam",
                                     "evidence_ids": ["U004"]})
    classify_action_item(unrelated, org, texts)
    assert unrelated.category == "not_relevant"


def test_uncited_evidence_is_unsupported():
    org = sample_org()
    item = ActionItem.from_llm({"description": "Ship the mobile app", "assignee": "Rahul",
                                "assignment_type": "explicit", "evidence_ids": ["U099"]})
    verdict, notes = verify_action_item(item, _utts(), org)
    assert verdict == "unsupported" and notes


def test_explicit_assignee_not_in_evidence_is_downgraded_and_fake_deadline_removed():
    org = sample_org()
    item = ActionItem.from_llm({"description": "Send the revised launch checklist", "assignee": "Sam",
                                "assignment_type": "explicit", "due_date": "next Tuesday",
                                "evidence_ids": ["U002"]})
    verdict, notes = verify_action_item(item, _utts(), org)
    assert item.assignment_type == "inferred"
    assert item.due_date is None
    assert verdict == "inferred"
    assert any("removed" in n for n in notes)


def test_grounded_item_is_confirmed_and_keeps_stated_deadline():
    org = sample_org()
    item = ActionItem.from_llm({"description": "Send the revised launch checklist", "assignee": "Rahul",
                                "assignment_type": "explicit", "due_date": "Friday", "evidence_ids": ["U002"]})
    verdict, _ = verify_action_item(item, _utts(), org)
    assert verdict == "confirmed" and item.due_date == "Friday"


def test_confirmed_event_without_date_is_demoted():
    event = Event.from_llm({"title": "Launch review", "confidence": "confirmed", "date": None, "evidence_ids": []})
    assert event.confidence == "tentative"
