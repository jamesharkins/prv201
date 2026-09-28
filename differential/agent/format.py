"""Human-readable formatting of readings and predictions (used by tools, agent and ticket)."""

from __future__ import annotations

import math

from differential.sim.faults import MODE_LABELS, parse_fault_id


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
