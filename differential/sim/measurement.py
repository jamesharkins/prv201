"""Measurement model: instrument noise, display quantisation and observation transforms.

Instruments (brief §2.2):
  * DMM, DC volts: accuracy +-(0.5 % of reading + 2 counts), 6000-count autoranging
    (600 mV / 6 V / 60 V / 600 V / 1000 V ranges). The +- figure is a specification
    limit, so the noise is modelled as Gaussian with sigma = limit / 2 (about 95 % of
    readings inside the limit), and readings are rounded to the display resolution.
  * Oscilloscope amplitude: +-3 % -> sigma 1.5 %, with an amplitude noise floor.
  * Distortion (THD): +-10 % relative (sigma 5 %), floor 0.01 %; with less than
    10 mV of fundamental the analyser cannot lock and reads 100 %.
  * Out-of-circuit component test: binary verdict with sensitivity 0.97 and
    specificity 0.99.

The engine works in a transformed space where tolerance effects are roughly
additive: DC -> asinh(v / 50 mV); gains -> dB; hum -> dBV; THD -> log10(%).
"""

from __future__ import annotations

import math

import numpy as np

# (range upper limit in volts, display resolution in volts) for a 6000-count meter
DMM_RANGES = ((0.6, 1e-4), (6.0, 1e-3), (60.0, 1e-2), (600.0, 0.1), (1000.0, 1.0))
DMM_PCT = 0.005
DMM_DIGITS = 2
SCOPE_REL = 0.03
GAIN_FLOOR = 1e-3  # gains below -60 dB re the generator read at the floor
HUM_FLOOR = 1e-4  # 100 uV rms ripple floor
THD_FLOOR = 0.01  # percent
THD_NO_SIGNAL = 100.0  # percent reading when the analyser cannot lock
THD_MIN_FUNDAMENTAL = 0.01  # V peak
THD_REL = 0.10
LIFT_SENSITIVITY = 0.97
LIFT_SPECIFICITY = 0.99
DC_SCALE = 0.05

# Variance floors in transformed units (see ADR-008).
VAR_FLOOR = {
    "dc": 0.004**2,
    "ac": 0.05**2,
    "ac20": 0.05**2,
    "ac20k": 0.05**2,
    "hum": 0.1**2,
    "thd": 0.01**2,
}


def dmm_resolution(v: float) -> float:
    mag = abs(v)
    for limit, res in DMM_RANGES:
        if mag < limit:
            return res
    return 1.0


def dmm_sigma(v: float) -> float:
    return (DMM_PCT * abs(v) + DMM_DIGITS * dmm_resolution(v)) / 2.0


def floor_combine(x: float, floor: float) -> float:
    return math.sqrt(x * x + floor * floor)


# ---------------------------------------------------------------------------
# Transforms (natural units -> engine space) and their noise
# ---------------------------------------------------------------------------


def to_engine(kind: str, value: float, fundamental: float | None = None) -> float:
    """Map a noise-free simulated observable or a reading into engine space."""
    if kind == "dc":
        return math.asinh(value / DC_SCALE)
    if kind in ("ac", "ac20", "ac20k"):
        return 20.0 * math.log10(floor_combine(max(value, 0.0), GAIN_FLOOR))
    if kind == "hum":
        return 20.0 * math.log10(floor_combine(max(value, 0.0), HUM_FLOOR))
    if kind == "thd":
        if fundamental is not None and (
            not math.isfinite(fundamental) or fundamental < THD_MIN_FUNDAMENTAL
        ):
            value = THD_NO_SIGNAL
        return math.log10(min(max(value, THD_FLOOR), THD_NO_SIGNAL))
    raise ValueError(kind)


def from_engine(kind: str, t: float) -> float:
    """Inverse transform (for displaying predicted readings)."""
    if kind == "dc":
        return DC_SCALE * math.sinh(t)
    if kind in ("ac", "ac20", "ac20k", "hum"):
        return float(10.0 ** (t / 20.0))
    if kind == "thd":
        return float(10.0**t)
    raise ValueError(kind)


def engine_noise_sd(kind: str, t: float) -> float:
    """Measurement-noise standard deviation in engine space at engine value ``t``."""
    if kind == "dc":
        v = from_engine("dc", t)
        return dmm_sigma(v) / math.sqrt(DC_SCALE**2 + v * v)
    if kind in ("ac", "ac20", "ac20k", "hum"):
        return 20.0 / math.log(10.0) * (SCOPE_REL / 2.0)
    if kind == "thd":
        return (THD_REL / 2.0) / math.log(10.0)
    raise ValueError(kind)


# ---------------------------------------------------------------------------
# Simulated readings (natural units) for the SimulatedInstrument and eval
# ---------------------------------------------------------------------------


def simulate_reading(
    kind: str, value: float, rng: np.random.Generator, fundamental: float | None = None
) -> float:
    """Noisy, quantised instrument reading for a noise-free simulated value."""
    if kind == "dc":
        noisy = value + float(rng.normal(0.0, dmm_sigma(value)))
        res = dmm_resolution(noisy)
        return round(noisy / res) * res
    if kind in ("ac", "ac20", "ac20k"):
        g = floor_combine(max(value, 0.0), GAIN_FLOOR)
        noisy = g * (1.0 + float(rng.normal(0.0, SCOPE_REL / 2.0)))
        return float(f"{max(noisy, GAIN_FLOOR):.3g}")
    if kind == "hum":
        h = floor_combine(max(value, 0.0), HUM_FLOOR)
        noisy = h * (1.0 + float(rng.normal(0.0, SCOPE_REL / 2.0)))
        return float(f"{max(noisy, HUM_FLOOR):.3g}")
    if kind == "thd":
        if fundamental is not None and (
            not math.isfinite(fundamental) or fundamental < THD_MIN_FUNDAMENTAL
        ):
            return THD_NO_SIGNAL
        base = min(max(value, THD_FLOOR), THD_NO_SIGNAL)
        noisy = base * (1.0 + float(rng.normal(0.0, THD_REL / 2.0)))
        return float(f"{min(max(noisy, THD_FLOOR), THD_NO_SIGNAL):.3g}")
    raise ValueError(kind)


def simulate_lift(defective: bool, rng: np.random.Generator) -> int:
    """Binary out-of-circuit verdict: 1 = out of tolerance / defective."""
    if defective:
        return int(rng.uniform() < LIFT_SENSITIVITY)
    return int(rng.uniform() >= LIFT_SPECIFICITY)


def reading_to_engine(kind: str, reading: float) -> float:
    """Transform an instrument reading (already noisy) into engine space."""
    if kind == "thd":
        return math.log10(min(max(reading, THD_FLOOR), THD_NO_SIGNAL))
    if kind in ("ac", "ac20", "ac20k"):
        return 20.0 * math.log10(max(reading, GAIN_FLOOR))
    if kind == "hum":
        return 20.0 * math.log10(max(reading, HUM_FLOOR))
    return to_engine(kind, reading)
