from datetime import date

from meetwise.chat.nodes import ChatNodes
from meetwise.chat.service import ChatService
from meetwise.llm.hashing import HashingEmbedder
from meetwise.services.commitments import reconcile_action_items
from meetwise.ingest.transcript import parse_utterances
from meetwise.rag.chunker import build_chunks
from meetwise.rag.retriever import Retriever
from meetwise.rag.store import Hit, VectorStore
from meetwise.storage.chat_repo import ChatRepository
from meetwise.storage.db import Database
from meetwise.storage.repository import Repository
from tests.fakes import SAMPLE_TRANSCRIPT, ScriptedChat

TODAY = "2026-10-30"


def _add_meeting(repo, store, embedder, title, when, text, participants, decisions=None, items=None):
    mid = repo.create_meeting(source_filename=f"{title}.txt", raw_text=text, user_title=title,
                              user_date=when, user_participants=participants)
    utts = parse_utterances(text)
    result = {
        "summary": {"executive_summary": f"{title} covered the agenda.", "key_points": [], "outcomes": []},
        "topics": [{"name": title, "utterance_ids": [u.id for u in utts]}],
        "action_items": [], "decisions": decisions or [], "unresolved_issues": [], "events": [],
    }
    if items:
        result["action_items"] = reconcile_action_items(repo, embedder, {"id": mid, "title": title, "date": when}, items)
    repo.save_result(mid, title=title, title_generated=False, participants=participants,
                     meeting_date=when, result=result)
    chunks = build_chunks({"id": mid, "title": title, "date": when, "participants": participants}, result, utts)
    store.replace_meeting(mid, chunks, embedder.embed([c.text for c in chunks]))
    return mid


def _seed():
    db = Database(":memory:")
    repo, embedder = Repository(db), HashingEmbedder()
    store = VectorStore(db)
    checklist = {"description": "Send the revised launch checklist", "assignee": "Rahul",
                 "due_date": "Friday", "status": "not_started", "priority": "high",
                 "assignment_type": "explicit", "category": "team", "evidence_ids": ["U002"],
                 "dependencies": [], "verification_notes": [], "verdict": "confirmed"}
    decision = [{"statement": "Launch on 14 November", "status": "finalized", "alternatives": ["7 November"],
                 "rationale": "Vendor availability", "evidence_ids": ["U001", "U003"]}]
    m1 = _add_meeting(repo, store, embedder, "Q3 Launch Planning", "2026-10-01", SAMPLE_TRANSCRIPT,
                      ["Priya", "Rahul"], decision, [checklist])
    m2 = _add_meeting(repo, store, embedder, "Hiring Plan", "2026-10-20",
                      "Priya: We need two more backend engineers.\nSam: Legal can review the offer letters by Thursday.",
                      ["Priya", "Sam"])
    retriever = Retriever(store, embedder)
    return {"db": db, "repo": repo, "store": store, "retriever": retriever, "m1": m1, "m2": m2}


def _nodes(env, chat, **kw):
    return ChatNodes(chat=chat, retriever=env["retriever"], repo=env["repo"], today=TODAY, **kw)


def run_chat(nodes, state):
    """Mirror of the LangGraph routing, so the agent logic is tested without langgraph installed."""
    state = dict(state)
    state.update(nodes.plan(state))
    state.update(nodes.retrieve(state))
    state.update(nodes.grade(state))
    if nodes.route_after_grade(state) == "answer":
        while True:
            state.update(nodes.answer(state))
            state.update(nodes.verify(state))
            if nodes.route_after_verify(state) != "answer":
                break
    state.update(nodes.finalize(state))
    return state


def _base(question, scope="all", meeting_id=None):
    return {"question": question, "scope": scope, "meeting_id": meeting_id, "history": [], "attempts": 0}


def test_grounded_answer_is_cited_and_verified():
    env = _seed()
    chat = ScriptedChat({
        "chat_plan": {"search_query": "launch checklist", "include_tasks": True, "task_scope": "all"},
        "chat_answer": {"answer": "Rahul agreed to send the revised launch checklist by Friday [S1].",
                        "used_sources": ["S1"], "evidence_status": "confirmed", "missing": None},
    })
    state = run_chat(_nodes(env, chat), _base("What did Rahul commit to?"))
    assert state["status"] == "answered"
    assert state["citations"] and state["citations"][0]["source_id"] == "S1"
    assert "[S1]" in state["final_answer"]


def test_fabricated_citation_is_rejected_and_the_agent_refuses_after_retries():
    env = _seed()
    chat = ScriptedChat({
        "chat_plan": {"search_query": "launch checklist"},
        "chat_answer": {"answer": "Rahul will finish it on Monday [S9].", "evidence_status": "confirmed"},
    })
    state = run_chat(_nodes(env, chat, max_attempts=2), _base("launch checklist status"))
    assert chat.calls.count("chat_answer") == 2
    assert state["status"] == "insufficient_evidence"
    assert "[S9]" not in state["final_answer"] and "Monday" not in state["final_answer"]


def test_a_retry_with_corrected_citations_succeeds():
    env = _seed()
    chat = ScriptedChat({
        "chat_plan": {"search_query": "launch checklist"},
        "chat_answer": [
            {"answer": "Rahul owns it [S7].", "evidence_status": "confirmed"},
            {"answer": "Rahul owns the revised launch checklist [S1].", "evidence_status": "confirmed"},
        ],
    })
    state = run_chat(_nodes(env, chat), _base("who owns the launch checklist"))
    assert chat.calls.count("chat_answer") == 2 and state["status"] == "answered"


def test_numbers_must_appear_in_the_cited_sources():
    nodes = ChatNodes(chat=ScriptedChat(), retriever=None, repo=None, today=TODAY)
    sources = {"S1": {"sid": "S1", "text": "Decision: Launch on 14 November."}}
    state = {"sources": list(sources.values()), "draft": {"answer": "The launch is on 3 December [S1].",
                                                        "evidence_status": "confirmed"}}
    state.update(nodes.verify(state))
    assert not state["verification"]["passed"]
    assert any("'3'" in p for p in state["verification"]["problems"])
    state["draft"] = {"answer": "The launch is on 14 November [S1].", "evidence_status": "confirmed"}
    state.update(nodes.verify(state))
    assert state["verification"]["passed"]


def test_no_relevant_evidence_skips_the_model_entirely():
    env = _seed()
    chat = ScriptedChat()
    state = run_chat(_nodes(env, chat), _base("submarine maintenance schedule"))
    assert state["status"] == "insufficient_evidence"
    assert "chat_answer" not in chat.calls
    assert "couldn't find" in state["final_answer"]


def test_meeting_scope_never_leaks_other_meetings():
    env = _seed()
    chat = ScriptedChat({"chat_plan": {"search_query": "offer letters engineers"}})
    state = run_chat(_nodes(env, chat), _base("What about the offer letters?", scope="meeting", meeting_id=env["m2"]))
    assert state["sources"], "expected sources from the open meeting"
    assert all(s["meeting_id"] == env["m2"] for s in state["sources"])


def test_all_scope_retrieves_across_meetings_and_caps_per_meeting():
    env = _seed()
    chat = ScriptedChat({"chat_plan": {"search_query": "launch"}})
    state = run_chat(_nodes(env, chat, per_meeting_cap=1), _base("What did we say about launch and hiring?"))
    ids = {s["meeting_id"] for s in state["sources"] if s["kind"] != "task"}
    assert env["m1"] in ids


def test_planner_date_range_limits_all_scope_retrieval():
    env = _seed()
    chat = ScriptedChat({"chat_plan": {"search_query": "hiring engineers", "date_from": "2026-10-15"}})
    state = run_chat(_nodes(env, chat), _base("What did we say about hiring engineers?"))
    assert state["sources"]
    assert all(s["meeting_id"] == env["m2"] for s in state["sources"])


def test_task_questions_include_task_records_with_history():
    env = _seed()
    chat = ScriptedChat({"chat_plan": {"search_query": "pending commitments", "include_tasks": True,
                                       "task_scope": "all"}})
    state = run_chat(_nodes(env, chat), _base("What commitments are still pending?"))
    tasks = [s for s in state["sources"] if s["kind"] == "task"]
    assert tasks and "Owner: Rahul" in tasks[0]["text"]


def test_fallback_plan_when_planner_output_is_unreadable():
    env = _seed()
    chat = ScriptedChat({"chat_plan": "not json"})
    state = _nodes(env, chat).plan(_base("What are my pending commitments?"))
    plan = state["search_plan"]
    assert plan["search_query"] == "What are my pending commitments?"
    assert plan["include_tasks"] is True and plan["task_scope"] == "mine"


def test_diversity_cap_keeps_other_meetings_visible():
    nodes = ChatNodes(chat=ScriptedChat(), retriever=None, repo=None, today=TODAY, per_meeting_cap=2)
    hits = [Hit(f"a{i}", "t", {"meeting_id": "A"}, 0.9, 0.9, 0.9 - i * 0.01) for i in range(5)]
    hits.append(Hit("b0", "t", {"meeting_id": "B"}, 0.5, 0.5, 0.5))
    kept = nodes._diversify(hits, "all")
    assert sum(1 for h in kept if h.metadata["meeting_id"] == "A") == 2
    assert any(h.metadata["meeting_id"] == "B" for h in kept)


def test_chat_repository_round_trips_sessions_and_citations():
    db = Database(":memory:")
    store = ChatRepository(db)
    sid = store.create_session(title="Launch?", scope="all", meeting_id=None)
    store.add_message(sid, "user", "When is launch?")
    store.add_message(sid, "assistant", "14 November [S1].", citations=[{"source_id": "S1"}], status="answered")
    messages = store.list_messages(sid)
    assert messages[1]["citations"] == [{"source_id": "S1"}] and messages[1]["status"] == "answered"
    assert store.recent_messages(sid, limit=1) == [{"role": "assistant", "content": "14 November [S1]."}]


def test_service_validates_scope_and_meeting():
    env = _seed()
    service = ChatService(chat_model=ScriptedChat(), retriever=env["retriever"], repo=env["repo"],
                          store=ChatRepository(env["db"]))
    for kwargs, error in [({"scope": "bogus"}, ValueError), ({"scope": "meeting"}, ValueError),
                          ({"scope": "meeting", "meeting_id": "nope"}, LookupError)]:
        try:
            service.ask("hello", **kwargs)
            raise AssertionError(f"expected {error.__name__} for {kwargs}")
        except error:
            pass
