from meetwise.ingest.transcript import make_windows, parse_utterances
from tests.fakes import SAMPLE_TRANSCRIPT


def test_speaker_turns_and_ids():
    utts = parse_utterances(SAMPLE_TRANSCRIPT)
    assert [u.id for u in utts] == ["U001", "U002", "U003", "U004"]
    assert utts[1].speaker == "Rahul"
    assert "revised launch checklist" in utts[1].text


def test_timestamps_in_both_shapes_and_continuation_lines():
    raw = "[00:12:03] Priya: First point.\nstill the same thought.\nRahul (00:14): Reply here."
    utts = parse_utterances(raw)
    assert len(utts) == 2
    assert utts[0].timestamp == "00:12:03"
    assert "still the same thought" in utts[0].text
    assert utts[1].timestamp == "00:14" and utts[1].speaker == "Rahul"


def test_speakerless_transcript_splits_on_paragraphs():
    utts = parse_utterances("We reviewed the budget.\n\nNext we discussed hiring.")
    assert len(utts) == 2 and all(u.speaker is None for u in utts)


def test_windows_respect_budget_and_cover_everything():
    utts = parse_utterances("\n".join(f"Ann: point number {i} " + "x" * 80 for i in range(40)))
    windows = make_windows(utts, max_chars=500)
    assert len(windows) > 1
    assert sum(len(w) for w in windows) == len(utts)
