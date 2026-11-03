from meetwise.graph.nodes import PipelineNodes
from tests.fakes import SAMPLE_TRANSCRIPT, ScriptedChat, sample_org


def _initial():
    return {"meeting_id": "m1", "filename": "Launch_sync.txt", "raw_text": SAMPLE_TRANSCRIPT,
            "user_title": None, "user_date": "2026-10-30", "user_participants": ["Priya"]}


def test_langgraph_workflow_runs_end_to_end():
    try:
        import langgraph  # noqa: F401
    except ImportError:
        print("  (skipped: langgraph is not installed in this environment)")
        return
    from meetwise.graph.workflow import build_graph

    persisted: list[dict] = []
    nodes = PipelineNodes(chat=ScriptedChat(), org=sample_org(), persist=persisted.append)
    build_graph(nodes).invoke(_initial())
    assert len(persisted) == 1
    assert persisted[0]["title"] == "Q3 Launch Planning"
    assert persisted[0]["action_items"][0]["category"] == "team"


def test_langgraph_conditional_retry_edge_runs_second_extraction_pass():
    try:
        import langgraph  # noqa: F401
    except ImportError:
        print("  (skipped: langgraph is not installed in this environment)")
        return
    from meetwise.graph.workflow import build_graph

    bad = {"action_items": [{"description": "Ship the mobile app", "assignee": "Rahul", "evidence_ids": ["U099"]}]}
    good = {"action_items": [{"description": "Send the revised launch checklist", "assignee": "Rahul",
                              "assignment_type": "explicit", "due_date": "Friday", "evidence_ids": ["U002"]}]}
    chat = ScriptedChat({"action_items": [bad, good]})
    persisted: list[dict] = []
    nodes = PipelineNodes(chat=chat, org=sample_org(), persist=persisted.append, max_attempts=2)
    build_graph(nodes).invoke(_initial())
    assert chat.calls.count("action_items") == 2
    assert persisted[0]["attempts"] == 2
