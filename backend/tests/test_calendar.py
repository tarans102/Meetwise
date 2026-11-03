from datetime import date

from meetwise.domain.calendar import parse_when
from meetwise.storage.calendar_repo import CalendarRepository
from meetwise.storage.db import Database

REF = date(2026, 10, 30)


def _event(**overrides):
    base = {"title": "Vendor call", "date": "14 November", "start_time": "10am", "end_time": "11am",
            "participants": ["Priya"], "location": None, "event_type": "meeting",
            "confidence": "proposed", "evidence_ids": ["U003"]}
    base.update(overrides)
    return base


def test_free_text_dates_and_times_are_parsed_with_reference_year():
    assert parse_when("14 November", "10am", "11am", REF) == {
        "starts_at": "2026-11-14T10:00", "ends_at": "2026-11-14T11:00", "all_day": False}
    assert parse_when("2026-12-01", None, None, REF) == {
        "starts_at": "2026-12-01", "ends_at": None, "all_day": True}
    assert parse_when("next spring", "10:30", None, REF)["starts_at"] is None
    assert parse_when("Dec 5", "2:30 pm", None, REF)["starts_at"] == "2026-12-05T14:30"


def test_extracted_events_stay_pending_until_the_user_confirms():
    cal = CalendarRepository(Database(":memory:"))
    cal.replace_pending_from_meeting("m1", [_event()], REF)
    assert cal.list_events() == []
    pending = cal.list_pending()
    assert len(pending) == 1 and pending[0]["starts_at"] == "2026-11-14T10:00"
    cal.confirm(pending[0]["id"])
    shown = cal.list_events(start="2026-11-01", end="2026-11-30")
    assert len(shown) == 1 and shown[0]["review_status"] == "confirmed"


def test_reprocessing_replaces_only_pending_suggestions_not_confirmed_events():
    cal = CalendarRepository(Database(":memory:"))
    cal.replace_pending_from_meeting("m1", [_event(), _event(title="Second")], REF)
    confirmed = cal.list_pending()[0]["id"]
    cal.confirm(confirmed)
    cal.replace_pending_from_meeting("m1", [_event(title="Revised")], REF)
    titles = sorted(e["title"] for e in cal.list_events(include_pending=True))
    assert titles == ["Revised", "Vendor call"]  # the confirmed one survives, the old pending one is gone


def test_undated_suggestions_are_kept_for_review_without_a_calendar_slot():
    cal = CalendarRepository(Database(":memory:"))
    cal.replace_pending_from_meeting("m1", [_event(date=None, start_time=None)], REF)
    pending = cal.list_pending()
    assert len(pending) == 1 and pending[0]["starts_at"] is None


def test_manual_event_crud_and_completion_flag():
    cal = CalendarRepository(Database(":memory:"))
    event_id = cal.create_event(title="Board prep", starts_at="2026-11-02T09:00", event_type="general")
    cal.update_event(event_id, completed=True, location="Room 4")
    event = cal.get_event(event_id)
    assert event["completed"] is True and event["location"] == "Room 4" and event["review_status"] == "confirmed"
    cal.delete_event(event_id)
    assert cal.get_event(event_id) is None
