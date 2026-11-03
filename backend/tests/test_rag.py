import numpy as np

from meetwise.llm.hashing import HashingEmbedder
from meetwise.rag.chunker import build_chunks
from meetwise.rag.retriever import Retriever
from meetwise.rag.store import SearchFilters, VectorStore
from meetwise.ingest.transcript import parse_utterances
from meetwise.storage.db import Database
from tests.fakes import SAMPLE_TRANSCRIPT


def _index(store, embedder, meeting_id, title, date, text, participants):
    utts = parse_utterances(text)
    result = {
        "summary": {"executive_summary": f"Summary of {title}", "key_points": [], "outcomes": []},
        "topics": [{"name": "Launch date", "utterance_ids": [u.id for u in utts]}],
        "action_items": [], "decisions": [{"statement": "Launch on 14 November", "status": "finalized",
                                           "alternatives": [], "rationale": None, "evidence_ids": ["U001"]}],
        "unresolved_issues": [], "events": [],
    }
    chunks = build_chunks({"id": meeting_id, "title": title, "date": date, "participants": participants}, result, utts)
    store.replace_meeting(meeting_id, chunks, embedder.embed([c.text for c in chunks]))


def _setup():
    db = Database(":memory:")
    store, embedder = VectorStore(db), HashingEmbedder()
    _index(store, embedder, "m1", "Q3 Launch Planning", "2026-10-01", SAMPLE_TRANSCRIPT, ["Priya", "Rahul"])
    _index(store, embedder, "m2", "Hiring Plan", "2026-10-20",
           "Priya: We need two more backend engineers.\nSam: Legal can review the offer letters.", ["Priya", "Sam"])
    return Retriever(store, embedder)


def test_chunks_carry_structured_metadata():
    retriever = _setup()
    hits = retriever.search("revised launch checklist Friday", filters=SearchFilters(meeting_ids=["m1"]))
    assert hits, "expected a hit for the checklist commitment"
    meta = hits[0].metadata
    assert meta["meeting_id"] == "m1" and meta["meeting_title"] == "Q3 Launch Planning"
    assert meta["meeting_date"] == "2026-10-01"
    assert meta["content_type"] in {"transcript", "summary", "decision"}


def test_metadata_filter_constrains_meetings_and_participants():
    retriever = _setup()
    only_sam = retriever.search("engineers offer letters", filters=SearchFilters(participants=["Sam"]))
    assert only_sam and all("Sam" in h.metadata["participants"] for h in only_sam)
    only_october_20 = retriever.search("launch", filters=SearchFilters(date_from="2026-10-15"))
    assert all(h.metadata["meeting_date"] >= "2026-10-15" for h in only_october_20)


def test_content_type_filter():
    retriever = _setup()
    decisions = retriever.search("launch 14 November", filters=SearchFilters(content_types=["decision"]))
    assert decisions and all(h.metadata["content_type"] == "decision" for h in decisions)


def test_unrelated_query_returns_no_evidence_rather_than_noise():
    retriever = _setup()
    assert retriever.search("quarterly submarine maintenance schedule") == []


def test_meeting_title_edit_propagates_to_chunks():
    db = Database(":memory:")
    store, embedder = VectorStore(db), HashingEmbedder()
    _index(store, embedder, "m1", "Old title", "2026-10-01", SAMPLE_TRANSCRIPT, ["Priya"])
    store.update_meeting_metadata("m1", {"meeting_title": "New title"})
    hits = Retriever(store, embedder).search("launch checklist")
    assert hits and all(h.metadata["meeting_title"] == "New title" for h in hits)


def test_vectors_from_a_different_model_are_skipped():
    db = Database(":memory:")
    store = VectorStore(db)
    store.replace_meeting("m1", build_chunks({"id": "m1", "title": "T", "date": None, "participants": []},
                                             {"summary": {"executive_summary": "launch"}}, []),
                          np.ones((1, 8), dtype=np.float32))
    assert store.search(np.ones(16, dtype=np.float32), "launch", None, 5, 1.0, 0.0) == []
