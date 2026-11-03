from meetwise.graph.nodes import PipelineNodes
from meetwise.services.commitments import reconcile_action_items
from meetwise.storage.db import Database
from meetwise.storage.repository import Repository
from meetwise.llm.hashing import HashingEmbedder
from tests.fakes import SAMPLE_TRANSCRIPT, ScriptedChat, sample_org

CHAIN = ["preprocess", "metadata", "summarize", "segment", "extract_decisions",
         "extract_events", "extract_actions", "attribute", "verify"]


def _state(**overrides):
    state = {"meeting_id": "m1", "filename": "Launch_sync.txt", "raw_text": SAMPLE_TRANSCRIPT,
             "user_title": None, "user_date": "2026-10-30", "user_participants": ["Priya"]}
    state.update(overrides)
    return state


def _run(nodes, state, steps=CHAIN):
    for name in steps:
        state.update(getattr(nodes, name)(state))
    return state


def test_full_chain_is_grounded_and_personalised():
    chat = ScriptedChat()
    state = _run(PipelineNodes(chat=chat, org=sample_org()), _state())
    assert state["title"] == "Q3 Launch Planning" and state["title_generated"] is True
    assert state["participants"][0] == "Priya"  # user-provided metadata is preserved first
    item = state["action_items"][0]
    assert item["assignee"] == "Rahul" and item["assignment_type"] == "explicit"
    assert item["category"] == "team" and item["verdict"] == "confirmed"
    assert item["due_date"] == "Friday"
    assert state["decisions"][0]["status"] == "finalized"
    assert state["unresolved_issues"][0]["explicitly_unresolved"] is True
    assert state["verification"]["passed"] is True
    assert "verify" in chat.calls


def test_user_supplied_title_is_never_overwritten():
    state = _run(PipelineNodes(chat=ScriptedChat(), org=sample_org()), _state(user_title="My own title"))
    assert state["title"] == "My own title" and state["title_generated"] is False


def test_malformed_metadata_falls_back_without_failing_the_meeting():
    chat = ScriptedChat({"metadata": "this is not json"})
    state = _run(PipelineNodes(chat=chat, org=sample_org()), _state())
    assert state["title"] == "Launch Sync" and state["title_generated"] is True
    assert state["action_items"]  # the rest of the pipeline still ran


def test_hallucinated_topic_ids_are_ignored_and_fall_back_to_whole_transcript():
    chat = ScriptedChat({"segment": {"topics": [{"name": "X", "start_id": "U050", "end_id": "U060"}]}})
    state = _run(PipelineNodes(chat=chat, org=sample_org()), _state())
    assert state["topics"][0]["name"] == "General discussion"
    assert len(state["topics"][0]["utterance_ids"]) == 4


def test_unsupported_items_trigger_a_bounded_retry_and_then_recover():
    bad = {"action_items": [{"description": "Ship the mobile app", "assignee": "Rahul",
                             "assignment_type": "explicit", "evidence_ids": ["U099"]}]}
    good = {"action_items": [{"description": "Send the revised launch checklist", "assignee": "Rahul",
                              "assignment_type": "explicit", "due_date": "Friday", "evidence_ids": ["U002"]}]}
    chat = ScriptedChat({"action_items": [bad, good]})
    nodes = PipelineNodes(chat=chat, org=sample_org(), max_attempts=2)
    state = _run(nodes, _state())
    assert nodes.route_after_verify(state) == "extract_actions"  # first pass was unsupported
    state.update(nodes.extract_actions(state))
    state.update(nodes.attribute(state))
    state.update(nodes.verify(state))
    assert nodes.route_after_verify(state) == "persist"
    assert state["attempts"] == 2 and state["action_items"][0]["verdict"] == "confirmed"


def test_retries_are_capped_even_if_verification_keeps_failing():
    bad = {"action_items": [{"description": "Ship the mobile app", "assignee": "Rahul", "evidence_ids": ["U099"]}]}
    nodes = PipelineNodes(chat=ScriptedChat({"action_items": bad}), org=sample_org(), max_attempts=2)
    state = _run(nodes, _state())
    state.update(nodes.extract_actions(state))
    state.update(nodes.attribute(state))
    state.update(nodes.verify(state))
    assert nodes.route_after_verify(state) == "persist"
    assert state["action_items"][0]["verdict"] == "unsupported"  # kept, but never presented as confirmed


def test_unavailable_llm_verifier_caps_confidence_at_inferred():
    state = _run(PipelineNodes(chat=ScriptedChat({"verify": "not json"}), org=sample_org()), _state())
    assert state["action_items"][0]["verdict"] == "inferred"
    assert any("unavailable" in n for n in state["verification"]["notes"])


def test_commitment_reconciled_across_meetings_instead_of_duplicated():
    db = Database(":memory:")
    repo, embedder = Repository(db), HashingEmbedder()
    base = {"description": "Send the revised launch checklist", "assignee": "Rahul", "due_date": "Friday",
            "status": "not_started", "priority": "high", "assignment_type": "explicit",
            "category": "team", "evidence_ids": ["U002"], "dependencies": [],
            "verification_notes": [], "verdict": "confirmed"}

    m1 = repo.create_meeting(source_filename="a.txt", raw_text="x", user_title=None,
                             user_date="2026-10-01", user_participants=[])
    first = reconcile_action_items(repo, embedder, {"id": m1, "title": "Launch", "date": "2026-10-01"},
                                   [dict(base)])
    assert first[0]["reconciliation"] == "new"

    m2 = repo.create_meeting(source_filename="b.txt", raw_text="y", user_title=None,
                             user_date="2026-10-15", user_participants=[])
    later = dict(base, due_date="Monday", description="Send revised launch checklist to the team")
    second = reconcile_action_items(repo, embedder, {"id": m2, "title": "Follow-up", "date": "2026-10-15"}, [later])
    assert second[0]["reconciliation"] == "existing"

    tasks = repo.list_tasks()
    assert len(tasks) == 1 and tasks[0]["due_date"] == "Monday"
    events = [h["event"] for h in repo.task_history(tasks[0]["id"])]
    assert "deadline_changed" in events and "mentioned_again" in events
