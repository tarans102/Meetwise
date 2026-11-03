"""Small, dependency-free text helpers shared by ingestion, verification and retrieval."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an the and or of to in on for with is are was were be been by at as it this that "
    "we i you they he she will would should can could from so do does did not".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in STOPWORDS]


def normalize_name(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (name or "").lower()).split())


def contains_phrase(haystack: str, phrase: str) -> bool:
    """Whole-word, case-insensitive containment (so 'Ann' does not match 'Annual')."""
    needle = normalize_name(phrase)
    if not needle:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
    return re.search(pattern, normalize_name(haystack)) is not None


def token_overlap(claim: str, evidence: str) -> float:
    """Fraction of the claim's content tokens that appear in the evidence."""
    claim_tokens = set(tokenize(claim))
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & set(tokenize(evidence))) / len(claim_tokens)


def jaccard(a: str, b: str) -> float:
    sa, sb = set(tokenize(a)), set(tokenize(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
