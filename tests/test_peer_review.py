"""Peer-review pipeline helpers (tools/peer_review.py)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import peer_review as pr  # noqa: E402


def test_criteria_split_covers_every_criterion_with_balanced_points() -> None:
    crits = [{"id": f"C{i}", "points": p} for i, p in enumerate([16, 12, 12, 8, 8, 4, 4], start=1)]
    split = pr.split_criteria(crits, ["A", "B", "C", "D"])
    ids = sorted(i for v in split.values() for i in v)
    assert ids == sorted(c["id"] for c in crits)
    loads = [sum(c["points"] for c in crits if c["id"] in v) for v in split.values()]
    assert max(loads) - min(loads) <= 8


def test_quotes_are_verified_against_the_cited_page() -> None:
    page = "The engine   recommends the next\nmeasurement by information gain."
    assert pr.quote_on_page("recommends the next measurement", page)
    assert not pr.quote_on_page("recommends the cheapest measurement", page)


def test_evidence_search_and_tone_check() -> None:
    paras = [(1, "We report every target as met or missed with a bootstrap interval against baselines."),
             (2, "The team enjoyed the project and learned a lot about teamwork overall.")]
    ev = pr.find_evidence(paras, ["target", "baseline", "interval"], k=1)
    assert ev[0]["page"] == 1
    assert pr.tone_issues("This is obviously sloppy.") == ["obviously", "sloppy"]
