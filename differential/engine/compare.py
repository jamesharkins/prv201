"""When two channels' readings differ: the healthy-channel comparison (a baseline).

In stereo and multichannel gear a technician compares the faulty channel with the healthy
one at the same point. The rule of thumb used here, fixed before any tuning: a DC reading
differs when the two differ by more than ``rel`` of the larger and by more than 50 mV; a
signal, hum or distortion reading differs when the ratio exceeds ``1 + rel`` (0.83 dB at
10%).
"""

from __future__ import annotations

import math

from differential.sim.measurement import GAIN_FLOOR, HUM_FLOOR

DIFFER_REL = 0.10
DC_FLOOR_V = 0.05
THD_FLOOR_RATIO = 1e-4


def channels_differ(kind: str, a: float, b: float, rel: float = DIFFER_REL) -> tuple[bool, float]:
    """Whether readings ``a`` and ``b`` of the same point in two channels differ, and a
    relative size of the difference (for ranking)."""
    if kind == "dc":
        d = abs(a - b)
        score = d / max(abs(a), abs(b), 1e-9)
        return d > DC_FLOOR_V and score > rel, score
    floor = HUM_FLOOR if kind == "hum" else THD_FLOOR_RATIO if kind == "thd" else GAIN_FLOOR
    ra, rb = max(a, floor), max(b, floor)
    db = abs(20.0 * math.log10(ra / rb))
    return db > 20.0 * math.log10(1.0 + rel), db / 20.0
