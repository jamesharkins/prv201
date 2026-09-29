"""Human-readable formatting of readings and predictions (used by tools, agent and ticket)."""

from __future__ import annotations

import math
import re

from differential.sim.faults import MODE_LABELS, parse_fault_id

_MARKUP = re.compile(r"[\x00-\x1f\x7f<>\[\]{}()#*_`|\\~^=]+")


def clean_text(text: str, limit: int = 200) -> str:
    """Free text that goes on the ticket (names, the owner's approval note): control
    characters, line breaks and markup characters removed, whitespace collapsed, length
    capped, so a field cannot add headings, links or fake ticket lines."""
    return " ".join(_MARKUP.sub(" ", str(text)).split())[:limit].strip()


_NOT_NAME = re.compile(r"[^\w .'-]|[\d_]")


def clean_name(name: str) -> str:
    """A person's name for the ticket: letters, spaces and . ' - only (no digits, so no
    number can reach the ticket through a name), at most 60 characters."""
    return " ".join(_NOT_NAME.sub(" ", str(name)).split())[:60].strip(" .'-")


def person_name(name: str) -> str:
    """``clean_name``, refusing text that is not a name (empty, or more than six words)."""
    out = clean_name(name)
    if sum(c.isalpha() for c in out) < 2 or len(out.split()) > 6:
        raise ValueError("give a person's name (letters only, at most six words)")
    return out


def fmt_volts(v: float) -> str:
    a = abs(v)
    if a >= 100:
        return f"{v:.1f} V"
    if a >= 1:
        return f"{v:.2f} V"
    if a >= 1e-3:
        return f"{v * 1e3:.1f} mV"
    return f"{v * 1e6:.0f} µV"


def fmt_reading(kind: str, value: float) -> str:
    if not math.isfinite(value):
        return "n/a"
    if kind == "dc":
        return fmt_volts(value)
    if kind in ("ac", "ac20", "ac20k"):
        db = 20.0 * math.log10(max(value, 1e-6))
        return f"{value:.3g} V/V ({db:+.1f} dB)"
    if kind == "hum":
        return f"{fmt_volts(value)} rms"
    if kind == "thd":
        return f"{value:.3g} %"
    if kind == "lift":
        return "out of tolerance" if value >= 0.5 else "within tolerance"
    return f"{value:.4g}"


def fault_label(hypothesis: str) -> str:
    if hypothesis in ("healthy", "unmodeled"):
        return {"healthy": "no fault", "unmodeled": "a fault outside the single-fault model"}[
            hypothesis]
    f = parse_fault_id(hypothesis)
    return f"{f.ref} {MODE_LABELS.get(f.mode, f.mode)}"


def pct(p: float) -> str:
    return f"{100.0 * p:.0f}%"
