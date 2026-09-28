"""Numeric grounding check (brief §2.6, target T9).

Any *reading-like* number in an agent message or repair ticket must be traceable
to a tool result or to something the technician typed. Reading-like means a
number with a unit (V, mV, dB, Hz, %, ohm, F, A, s), a decimal fraction, or a
percentage. Part designators and test-point names (R203, TP9, 12AX7, 1N4148)
and plain small counts ("two readings", "step 3") are not readings.

Traceability allows for display rounding and for the unit and scale changes
an explanation naturally makes: 0.873 may appear as 87%, 87.3% or 0.87;
0.0123 V as 12.3 mV; 250.4 V as 250 V.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

UNIT_SCALE = {
    "v": 1.0, "mv": 1e-3, "uv": 1e-6, "µv": 1e-6, "kv": 1e3, "vrms": 1.0, "mvrms": 1e-3,
    "ma": 1e-3, "ua": 1e-6, "µa": 1e-6,
    "hz": 1.0, "khz": 1e3,
    "ohm": 1.0, "ohms": 1.0, "ω": 1.0, "k": 1e3, "kω": 1e3, "kohm": 1e3, "mω": 1e6,
    "meg": 1e6, "uf": 1e-6, "µf": 1e-6, "nf": 1e-9, "pf": 1e-12,
    "s": 1.0, "ms": 1e-3,
    "db": 1.0, "dbv": 1.0, "%": 1.0, "×": 1.0, "v/v": 1.0, "bits": 1.0,
    "units": 1.0, "$": 1.0,
}
_UNITS = sorted(UNIT_SCALE, key=len, reverse=True)
_UNIT_RE = "|".join(re.escape(u) for u in _UNITS if u != "$")
NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?P<cur>\$)?(?P<num>[-−+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-−+]?\d*\.\d+|[-−+]?\d+)"
    r"(?:\s?(?P<unit>" + _UNIT_RE + r"))?(?![A-Za-z0-9_])",
    flags=re.IGNORECASE,
)
IDENT_RE = re.compile(r"\b(?:[A-Za-z]{1,4}\d+[A-Za-z0-9]*|\d+[A-Za-z]{1,3}\d+[A-Za-z0-9]*)\b")
SMALL_COUNT_MAX = 12


@dataclass(frozen=True)
class NumberMention:
    text: str
    value: float
    unit: str
    start: int

    @property
    def reading_like(self) -> bool:
        return bool(self.unit) or "." in self.text or self.text.startswith("$") or abs(
            self.value) > SMALL_COUNT_MAX


@dataclass
class GroundingReport:
    ok: bool
    checked: int
    ungrounded: list[NumberMention] = field(default_factory=list)


def _collect_numbers(obj: Any, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if math.isfinite(float(obj)):
            out.append(float(obj))
        return
    if isinstance(obj, str):
        for m in NUMBER_RE.finditer(obj):
            v = _to_float(m.group("num"))
            if v is not None:
                out.append(v * UNIT_SCALE.get((m.group("unit") or "").lower(), 1.0))
                out.append(v)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", "").replace("−", "-"))
    except ValueError:
        return None


def find_numbers(text: str) -> list[NumberMention]:
    idents = [(m.start(), m.end()) for m in IDENT_RE.finditer(text)]
    out = []
    for m in NUMBER_RE.finditer(text):
        if any(a <= m.start() < b for a, b in idents):
            continue
        v = _to_float(m.group("num"))
        if v is None:
            continue
        unit = (m.group("unit") or "").lower()
        if m.group("cur"):
            unit = "$"
        out.append(NumberMention(m.group(0), v, unit, m.start()))
    return out


def _decimals(text: str) -> int:
    t = text.replace(",", "")
    num = re.search(r"\d*\.?\d+", t)
    s = num.group(0) if num else ""
    return len(s.split(".")[1]) if "." in s else 0


def _matches(mention: NumberMention, source: float) -> bool:
    """Could ``mention`` be a rounded/rescaled rendering of ``source``?"""
    scale = UNIT_SCALE.get(mention.unit, 1.0)
    shown = mention.value
    d = _decimals(mention.text)
    candidates = [source, source / scale if scale else source, source * 100.0, abs(source),
                  abs(source) / scale if scale else abs(source), abs(source) * 100.0]
    for c in candidates:
        if not math.isfinite(c):
            continue
        tol = 0.5 * 10.0 ** (-d) + 1e-9
        if abs(abs(shown) - abs(c)) <= tol:
            return True
        # allow 2-3 significant-figure rendering of large or small values
        if c != 0 and abs(abs(shown) - abs(c)) / abs(c) <= 0.006:
            return True
    return False


def check_grounding(text: str, evidence: Iterable[Any]) -> GroundingReport:
    """Check every reading-like number in ``text`` against numbers in ``evidence``."""
    pool: list[float] = []
    for e in evidence:
        _collect_numbers(e, pool)
    mentions = [m for m in find_numbers(text) if m.reading_like]
    bad = [m for m in mentions if not any(_matches(m, s) for s in pool)]
    return GroundingReport(ok=not bad, checked=len(mentions), ungrounded=bad)


def redact_ungrounded(text: str, report: GroundingReport) -> str:
    """Replace ungrounded numbers with a visible placeholder (last-resort fallback)."""
    out = text
    for m in sorted(report.ungrounded, key=lambda x: -x.start):
        out = out[: m.start] + "[value withheld: not from a measurement or tool]" + out[
            m.start + len(m.text):]
    return out
