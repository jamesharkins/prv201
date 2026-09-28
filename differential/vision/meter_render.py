"""Synthetic phone photos of a 6000-count handheld digital multimeter.

Differential asks the technician to photograph the multimeter display. Claude
vision reads the photo in live mode and ``differential.vision.meter_read.read_offline``
is the offline fallback. Neither can be measured without labelled photos, so this
module renders them: a meter face with a custom-segment LCD, placed in a random
bench scene and "photographed" with perspective (up to 25 degrees of tilt, with the
LCD losing contrast off-axis), rotation (up to 15 degrees), glare, blur, lighting,
shadows, sensor noise and JPEG compression whose strength depends on a difficulty
level ("easy", "medium", "hard").

LCD layout conventions (shared with the offline reader). The LCD glass is
``LCD_W`` x ``LCD_H`` "LCD units" and contains:

* four slanted seven-segment digits, a minus sign left of the first digit and a
  decimal point after each of the first three digits;
* fixed annunciator icons on the top line: AUTO, a DC slot and an AC slot (drawn
  either as the words DC/AC or as the ⎓ and ~ symbols, depending on the meter
  model), HOLD and a battery icon;
* fixed unit icons right of the digits: ``M k Ω`` on one line and ``m V`` below,
  so "kΩ" lights the k and Ω icons and "mV" the m and V icons;
* optionally an analog bar graph under the digits.

Readings follow a 6000-count autoranging meter with leading-zero blanking:
600.0 mV / 6.000 V / 60.00 V / 600.0 V for volts, 600.0 Ω up to 60.00 MΩ for
resistance, and "0L" (overload, labelled ``"OL"``) with the decimal point of the
range. A real meter has a different layout, which is why live mode uses Claude
vision and the offline reader is only a fallback for this layout.

Everything random comes from the ``numpy`` generator passed in, so a seed fixes
the dataset exactly.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from differential.config import METER_DIR
from differential.sim.measurement import simulate_reading

Point = tuple[float, float]
Polyline = list[Point]
RGB = tuple[int, int, int]

SYNTHETIC_DIR = METER_DIR / "synthetic"
DEFAULT_SEED = 20260928
DIFFICULTIES = ("easy", "medium", "hard")
DIFFICULTY_MIX = {"easy": 0.4, "medium": 0.4, "hard": 0.2}
UNITS = ("mV", "V", "Ω", "kΩ", "MΩ")
MODES = ("DC", "AC", "resistance")
OVERLOAD_TEXT = "OL"
COUNTS = 6000  # display counts: the largest reading on any range is 5999

# ---------------------------------------------------------------------------
# LCD geometry (LCD units; the glass spans 0..LCD_W x 0..LCD_H, y points down)
# ---------------------------------------------------------------------------

LCD_W, LCD_H = 400.0, 220.0
N_DIGITS = 4
DIGIT_W, DIGIT_H = 56.0, 120.0
DIGIT_TOP = 58.0
DIGIT_LEFT = 46.0
DIGIT_PITCH = 68.0
SEG_T = 11.0  # segment thickness
SEG_GAP = 1.5
SLANT = 0.10  # italic digits: x shift per unit of height above the baseline
DP_SIZE = 9.0
SEGMENTS = "abcdefg"
# a top, b upper right, c lower right, d bottom, e lower left, f upper left, g middle
PATTERNS: dict[str, str] = {
    "0": "abcdef",
    "1": "bc",
    "2": "abdeg",
    "3": "abcdg",
    "4": "bcfg",
    "5": "acdfg",
    "6": "acdefg",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
    "L": "def",
    " ": "",
}
BAR_COUNT = 30
BAR_PITCH = 9.0
BAR_Y0, BAR_Y1 = 188.0, 200.0

# Meter face (face units; the LCD glass is drawn 1:1 at GLASS_X0, GLASS_Y0)
FACE_W, FACE_H = 560.0, 1060.0
GLASS_X0, GLASS_Y0 = 80.0, 96.0
BODY_RADIUS = 64.0
PANEL = (30.0, 36.0, 530.0, 1024.0)
BEZEL = (62.0, 78.0, 498.0, 334.0)
DIAL_CENTRE = (280.0, 650.0)
JACKS: dict[str, Point] = {"A": (140.0, 950.0), "COM": (280.0, 950.0), "VΩ": (420.0, 950.0)}
DIAL_FUNCTIONS = ("OFF", "V~", "V⎓", "mV", "Ω", "A")
DIAL_ANGLES = (-120.0, -72.0, -24.0, 24.0, 72.0, 120.0)  # degrees clockwise from up


def _hbar(x0: float, x1: float, yc: float, t: float) -> Polyline:
    """Horizontal segment with pointed (mitred) ends."""
    h = t / 2
    return [(x0, yc), (x0 + h, yc - h), (x1 - h, yc - h), (x1, yc), (x1 - h, yc + h), (x0 + h, yc + h)]


def _vbar(xc: float, y0: float, y1: float, t: float) -> Polyline:
    """Vertical segment with pointed (mitred) ends."""
    h = t / 2
    return [(xc, y0), (xc + h, y0 + h), (xc + h, y1 - h), (xc, y1), (xc - h, y1 - h), (xc - h, y0 + h)]


def _slant(points: Sequence[Point], baseline: float) -> Polyline:
    return [(x + SLANT * (baseline - y), y) for x, y in points]


def digit_left(i: int) -> float:
    return DIGIT_LEFT + i * DIGIT_PITCH


@cache
def segment_polygons(i: int) -> dict[str, Polyline]:
    """The seven segment polygons of digit ``i`` (0 = leftmost) in LCD units."""
    x0, y0, w, h, t, g = digit_left(i), DIGIT_TOP, DIGIT_W, DIGIT_H, SEG_T, SEG_GAP
    ht = t / 2
    raw = {
        "a": _hbar(x0 + ht + g, x0 + w - ht - g, y0 + ht, t),
        "b": _vbar(x0 + w - ht, y0 + ht + g, y0 + h / 2 - g, t),
        "c": _vbar(x0 + w - ht, y0 + h / 2 + g, y0 + h - ht - g, t),
        "d": _hbar(x0 + ht + g, x0 + w - ht - g, y0 + h - ht, t),
        "e": _vbar(x0 + ht, y0 + h / 2 + g, y0 + h - ht - g, t),
        "f": _vbar(x0 + ht, y0 + ht + g, y0 + h / 2 - g, t),
        "g": _hbar(x0 + ht + g, x0 + w - ht - g, y0 + h / 2, t),
    }
    return {k: _slant(v, y0 + h) for k, v in raw.items()}


def dp_polygon(i: int) -> Polyline:
    """Decimal point after digit ``i`` (i = 0, 1, 2)."""
    cx = digit_left(i) + DIGIT_W + 6.0
    y1 = DIGIT_TOP + DIGIT_H
    s = DP_SIZE / 2
    return [(cx - s, y1 - DP_SIZE), (cx + s, y1 - DP_SIZE), (cx + s, y1), (cx - s, y1)]


def minus_polygon() -> Polyline:
    return _slant(_hbar(8.0, 36.0, DIGIT_TOP + DIGIT_H / 2, SEG_T), DIGIT_TOP + DIGIT_H)


def bar_polygon(i: int) -> Polyline:
    x0 = DIGIT_LEFT + i * BAR_PITCH
    return [(x0, BAR_Y0), (x0 + 5.0, BAR_Y0), (x0 + 5.0, BAR_Y1), (x0, BAR_Y1)]


def scale_strokes() -> list[Polyline]:
    """Printed bar-graph scale (baseline and ticks), always visible on meters with a bar graph."""
    xa, xb = DIGIT_LEFT, DIGIT_LEFT + BAR_COUNT * BAR_PITCH
    ticks = [[(xa + j * 5 * BAR_PITCH, 204.0), (xa + j * 5 * BAR_PITCH, 209.0)] for j in range(7)]
    return [[(xa, 204.0), (xb, 204.0)], *ticks]


# ---------------------------------------------------------------------------
# Stroke glyphs for annunciators and panel legends (cap height 1, y down)
# ---------------------------------------------------------------------------


def _arc(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, n: int = 14) -> Polyline:
    """Points on an elliptical arc; angles in degrees, 0 = right, 90 = down."""
    return [
        (cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
        for a in np.linspace(a0, a1, n)
    ]


def _build_glyphs() -> dict[str, tuple[float, list[Polyline]]]:
    sine = [(x, 0.5 - 0.2 * math.sin(2 * math.pi * x / 0.8)) for x in np.linspace(0.0, 0.8, 17)]
    return {
        "A": (0.72, [[(0, 1), (0.36, 0), (0.72, 1)], [(0.15, 0.62), (0.57, 0.62)]]),
        "C": (0.68, [_arc(0.34, 0.5, 0.34, 0.5, 45, 315)]),
        "D": (0.66, [[(0, 0), (0, 1)], [(0, 0), *_arc(0.28, 0.5, 0.38, 0.5, -90, 90), (0, 1)]]),
        "E": (0.6, [[(0.6, 0), (0, 0), (0, 1), (0.6, 1)], [(0, 0.5), (0.5, 0.5)]]),
        "F": (0.56, [[(0.56, 0), (0, 0), (0, 1)], [(0, 0.5), (0.46, 0.5)]]),
        "G": (0.7, [[*_arc(0.35, 0.5, 0.35, 0.5, 315, 45, 18), (0.7, 0.56), (0.42, 0.56)]]),
        "H": (0.64, [[(0, 0), (0, 1)], [(0.64, 0), (0.64, 1)], [(0, 0.5), (0.64, 0.5)]]),
        "L": (0.54, [[(0, 0), (0, 1), (0.54, 1)]]),
        "M": (0.8, [[(0, 1), (0, 0), (0.4, 0.62), (0.8, 0), (0.8, 1)]]),
        "N": (0.66, [[(0, 1), (0, 0), (0.66, 1), (0.66, 0)]]),
        "O": (0.72, [_arc(0.36, 0.5, 0.36, 0.5, 0, 360, 28)]),
        "R": (0.62, [[(0, 1), (0, 0), (0.34, 0), *_arc(0.34, 0.26, 0.26, 0.26, -90, 90)[1:], (0, 0.52)],
                     [(0.3, 0.52), (0.62, 1)]]),
        "S": (0.6, [[*_arc(0.3, 0.26, 0.29, 0.25, -15, -270), *_arc(0.3, 0.75, 0.3, 0.25, -90, 165)[1:]]]),
        "T": (0.64, [[(0, 0), (0.64, 0)], [(0.32, 0), (0.32, 1)]]),
        "U": (0.62, [[(0, 0), (0, 0.68), *_arc(0.31, 0.68, 0.31, 0.32, 180, 0)[1:-1], (0.62, 0.68),
                      (0.62, 0)]]),
        "V": (0.7, [[(0, 0), (0.35, 1), (0.7, 0)]]),
        "k": (0.52, [[(0, 0), (0, 1)], [(0.5, 0.36), (0, 0.74)], [(0.2, 0.6), (0.54, 1)]]),
        "m": (0.78, [[(0, 1), (0, 0.38)],
                     [(0, 0.56), *_arc(0.195, 0.56, 0.195, 0.17, 180, 360)[1:], (0.39, 1)],
                     [(0.39, 0.56), *_arc(0.585, 0.56, 0.195, 0.17, 180, 360)[1:], (0.78, 1)]]),
        "Ω": (0.8, [[(0.02, 1), (0.22, 1), *_arc(0.4, 0.45, 0.37, 0.43, 120, 420, 30), (0.58, 1),
                     (0.78, 1)]]),
        "~": (0.8, [sine]),
        "⎓": (0.8, [[(0, 0.3), (0.8, 0.3)], [(0, 0.72), (0.2, 0.72)], [(0.3, 0.72), (0.5, 0.72)],
                    [(0.6, 0.72), (0.8, 0.72)]]),
    }


GLYPHS = _build_glyphs()
LETTER_SPACING = 0.18


def text_width(text: str, height: float) -> float:
    widths = [GLYPHS[c][0] for c in text if c != " "]
    spaces = text.count(" ") * 0.5
    return height * (sum(widths) + spaces + LETTER_SPACING * max(len(text) - 1, 0))


def text_strokes(text: str, x: float, y: float, height: float) -> list[Polyline]:
    """Polylines of ``text`` with its top-left corner at (x, y)."""
    out: list[Polyline] = []
    cursor = x
    for ch in text:
        if ch == " ":
            cursor += height * (0.5 + LETTER_SPACING)
            continue
        w, strokes = GLYPHS[ch]
        out += [[(cursor + px * height, y + py * height) for px, py in s] for s in strokes]
        cursor += height * (w + LETTER_SPACING)
    return out


@dataclass(frozen=True)
class Icon:
    """A fixed LCD annunciator: ``text`` drawn with its top-left at (x, y)."""

    text: str
    x: float
    y: float
    height: float
    stroke: float

    def strokes(self) -> list[Polyline]:
        return text_strokes(self.text, self.x, self.y, self.height)

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + text_width(self.text, self.height), self.y + self.height)


ICONS: dict[str, Icon] = {
    "AUTO": Icon("AUTO", 12.0, 13.0, 17.0, 3.0),
    "DC_text": Icon("DC", 76.0, 12.0, 19.0, 3.4),
    "AC_text": Icon("AC", 116.0, 12.0, 19.0, 3.4),
    "DC_sym": Icon("⎓", 83.0, 12.0, 19.0, 3.4),
    "AC_sym": Icon("~", 123.0, 12.0, 19.0, 3.4),
    "HOLD": Icon("HOLD", 160.0, 13.0, 17.0, 3.0),
    "M": Icon("M", 325.0, 100.0, 26.0, 4.0),
    "k": Icon("k", 352.0, 100.0, 26.0, 4.0),
    "Ω": Icon("Ω", 372.0, 100.0, 26.0, 4.0),
    "m": Icon("m", 330.0, 148.0, 26.0, 4.0),
    "V": Icon("V", 362.0, 148.0, 26.0, 4.0),
}
UNIT_ICONS: dict[str, tuple[str, ...]] = {
    "V": ("V",),
    "mV": ("m", "V"),
    "Ω": ("Ω",),
    "kΩ": ("k", "Ω"),
    "MΩ": ("M", "Ω"),
}
BATTERY_BOX = (358.0, 14.0, 386.0, 30.0)

# ---------------------------------------------------------------------------
# Display text conventions
# ---------------------------------------------------------------------------

_OVERLOAD_RE = re.compile(r"^[-+]?\.?[O0]\.?L\.?$")
_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
# Decimal point positions of the ranges of this meter (index of the digit before it).
RANGE_DP: dict[str, tuple[int | None, ...]] = {
    "mV": (2,),
    "V": (0, 1, 2),
    "Ω": (2,),
    "kΩ": (0, 1, 2),
    "MΩ": (0, 1),
}
OVERLOAD_DP = {"mV": 2, "V": 2, "Ω": 2, "kΩ": 1, "MΩ": 1}


def normalize_value_text(text: str) -> str:
    """Canonical display text: '15.15', '-0.512', or 'OL' for any overload spelling."""
    t = text.strip().replace(" ", "").replace("−", "-").replace("–", "-").upper()
    if _OVERLOAD_RE.match(t):
        return OVERLOAD_TEXT
    t = t.lstrip("+")
    if t.startswith("."):
        t = "0" + t
    if t.startswith("-."):
        t = "-0" + t[1:]
    return t


def value_of(text: str) -> float | None:
    """Numeric value of a display text in its displayed unit (None for OL / not a number)."""
    t = normalize_value_text(text)
    if t == OVERLOAD_TEXT or not _NUMBER_RE.match(t):
        return None
    return float(t)


@dataclass(frozen=True)
class DisplayState:
    """What the LCD shows."""

    chars: tuple[str, ...]  # four digit characters from PATTERNS (" " = blank)
    dp: int | None  # decimal point after this digit
    minus: bool
    overload: bool
    unit: str
    mode: str
    auto: bool
    bar_fraction: float


def display_state(value_text: str, unit: str, mode: str, auto: bool = True) -> DisplayState:
    """Lay a display text out on the four-digit LCD (right-aligned, leading zeros blanked)."""
    if unit not in UNITS:
        raise ValueError(f"unit must be one of {UNITS}, got {unit!r}")
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if (mode == "resistance") != unit.endswith("Ω"):
        raise ValueError(f"unit {unit} does not belong to mode {mode}")
    text = normalize_value_text(value_text)
    if text == OVERLOAD_TEXT:
        p = OVERLOAD_DP[unit]
        chars = [" "] * N_DIGITS
        chars[p], chars[p + 1] = "0", "L"
        return DisplayState(tuple(chars), p, False, True, unit, mode, auto, 1.0)
    if not _NUMBER_RE.match(text):
        raise ValueError(f"not a display number: {value_text!r}")
    minus = text.startswith("-")
    body = text.lstrip("-")
    int_part, _, frac = body.partition(".")
    digits = int_part + frac
    if len(digits) > N_DIGITS or (frac and len(int_part) > N_DIGITS - 1):
        raise ValueError(f"{value_text!r} does not fit a 4-digit display")
    if int(digits) >= COUNTS:
        raise ValueError(f"{value_text!r} exceeds {COUNTS} counts")
    if len(int_part) > 1 and int_part[0] == "0":
        raise ValueError(f"{value_text!r} has a leading zero (the display blanks it)")
    offset = N_DIGITS - len(digits)
    chars = [" "] * offset + list(digits)
    dp = offset + len(int_part) - 1 if frac else None
    if dp is not None and dp not in RANGE_DP[unit]:
        raise ValueError(f"{value_text!r} is not a range of the {unit} function")
    full_scale = COUNTS * 10.0 ** (-len(frac))
    frac_bar = min(abs(float(body)) / full_scale, 1.0)
    if minus and float(body) == 0.0:
        minus = False
    return DisplayState(tuple(chars), dp, minus, False, unit, mode, auto, frac_bar)


def format_reading(value: float, ranges: Sequence[tuple[str, float, int]]) -> tuple[str, str] | None:
    """Autorange ``value`` (base units) over ``ranges`` = (unit, scale, decimals).

    Returns (display text, unit) on the lowest range that shows it within 6000
    counts, or None when it overloads the top range.
    """
    for unit, scale, decimals in ranges:
        text = f"{value * scale:.{decimals}f}"
        counts = int(text.replace("-", "").replace(".", ""))
        if counts < COUNTS:
            if counts == 0:
                text = text.lstrip("-")
            return text, unit
    return None


VOLT_RANGES: tuple[tuple[str, float, int], ...] = (
    ("mV", 1e3, 1), ("V", 1.0, 3), ("V", 1.0, 2), ("V", 1.0, 1),
)
AC_VOLT_RANGES = VOLT_RANGES[1:]  # the V~ position starts at 6 V; mV has its own position
OHM_RANGES: tuple[tuple[str, float, int], ...] = (
    ("Ω", 1.0, 1), ("kΩ", 1e-3, 3), ("kΩ", 1e-3, 2), ("kΩ", 1e-3, 1), ("MΩ", 1e-6, 3), ("MΩ", 1e-6, 2),
)

# ---------------------------------------------------------------------------
# Representative readings for this project
# ---------------------------------------------------------------------------

# Healthy DC levels at the channel strip's test points (median of the simulated
# validation draws, data/sim) plus a transistor base-emitter bias.
DC_POINTS: tuple[tuple[str, float], ...] = (
    ("TP1 unregulated LV rail", 23.97),
    ("TP2 zener reference", 15.89),
    ("TP3 regulated +15 V rail", 15.12),
    ("TP4 HV reservoir", 281.6),
    ("TP5 HV filter node", 273.0),
    ("TP6 B+", 254.2),
    ("TP7 triode grid", 0.001),
    ("TP8 triode cathode", 1.208),
    ("TP9 triode plate", 169.8),
    ("TP10 tone-stack input (DC blocked)", 0.0),
    ("TP13 op-amp input", 7.666),
    ("TP15 op-amp output", 7.666),
    ("TP16 half-supply bias", 7.666),
    ("TP18 Q501 base", 3.643),
    ("TP19 Q501 emitter", 3.019),
    ("TP20 Q501 collector", 9.348),
    ("TP21 Q502 emitter", 8.634),
    ("TP23 driver supply", 14.86),
    ("Q501 base-emitter bias", 0.624),
    ("Q101 base-emitter bias", 0.66),
)
# AC readings in millivolts (meter mV position): rail ripple and signal levels.
AC_MV_POINTS: tuple[tuple[str, float], ...] = (
    ("hum:TP1 LV reservoir ripple (rms)", 25.7),
    ("hum:TP4 HV reservoir ripple (rms)", 85.6),
    ("hum:TP3 regulated-rail ripple (rms)", 0.16),
    ("hum:TP5 HV filter ripple (rms)", 0.57),
    ("ac:TP7 test tone at the grid", 100.0),
    ("ac:TP15 op-amp output signal", 245.0),
    ("ac:TP22 line output, -10 dBV", 316.0),
)
# AC readings in volts (meter V~ position).
AC_V_POINTS: tuple[tuple[str, float], ...] = (
    ("LV transformer secondary", 18.0),
    ("HV transformer secondary", 200.0),
    ("heater winding", 6.3),
    ("ac:TP22 line output, 0 dBu", 0.775),
    ("ac:TP22 line output, +4 dBu", 1.228),
)
# Resistors from the circuit library (value, tolerance), measured lifted.
RESISTORS: tuple[tuple[str, float, float], ...] = (
    ("R102", 1e3, 0.01), ("R103", 2.2e3, 0.05), ("R104", 220e3, 0.05), ("R105", 10e3, 0.05),
    ("R106", 22e3, 0.05), ("R201", 1e6, 0.05), ("R202", 2.2e3, 0.01), ("R203", 100e3, 0.01),
    ("R204", 1.5e3, 0.01), ("R301", 47e3, 0.01), ("R302", 4.7e3, 0.01), ("R303", 33e3, 0.01),
    ("R405", 10e3, 0.01), ("R406", 100.0, 0.01), ("R501", 39e3, 0.01), ("R502", 13e3, 0.01),
    ("R504", 470.0, 0.01), ("R507", 47.0, 0.01), ("R508", 100e3, 0.05),
)
SCENARIOS = {"dc": 0.56, "dc_reversed": 0.06, "ac_mv": 0.12, "ac_v": 0.06, "ohm": 0.14, "overload": 0.06}


@dataclass(frozen=True)
class ReadingSpec:
    value_text: str
    unit: str
    mode: str
    auto: bool
    scenario: str


def _dc_level(rng: np.random.Generator) -> tuple[str, float]:
    name, nominal = DC_POINTS[int(rng.integers(len(DC_POINTS)))]
    u = rng.uniform()
    if u < 0.12:  # a dead or shorted node
        return f"{name}, faulty (collapsed)", nominal * rng.uniform(0.0, 0.08)
    if u < 0.30:  # bias drift
        return f"{name}, faulty (drifted)", nominal * rng.uniform(0.3, 1.3)
    return name, nominal


def sample_reading(rng: np.random.Generator) -> ReadingSpec:
    """A reading a technician could photograph while diagnosing the channel strip."""
    names = list(SCENARIOS)
    kind = names[int(rng.choice(len(names), p=np.array(list(SCENARIOS.values()))))]
    if kind in ("dc", "dc_reversed"):
        name, level = _dc_level(rng)
        reading = simulate_reading("dc", level, rng)  # DMM noise and display resolution
        if kind == "dc_reversed":
            reading = -reading if abs(reading) >= 0.01 else -rng.uniform(0.5, 30.0)
            name += ", leads reversed"
        fmt = format_reading(reading, VOLT_RANGES)
        assert fmt is not None
        return ReadingSpec(fmt[0], fmt[1], "DC", True, f"dc:{name}")
    if kind == "ac_mv":
        if rng.uniform() < 0.6:
            name, mv = AC_MV_POINTS[int(rng.integers(len(AC_MV_POINTS)))]
            mv *= rng.uniform(0.8, 1.25)
        else:
            name, mv = "ac: signal or ripple level", float(np.exp(rng.uniform(np.log(0.3), np.log(599.0))))
        return ReadingSpec(f"{min(mv, 599.9):.1f}", "mV", "AC", False, f"ac_mv:{name}")
    if kind == "ac_v":
        name, v = AC_V_POINTS[int(rng.integers(len(AC_V_POINTS)))]
        fmt = format_reading(v * rng.normal(1.0, 0.03), AC_VOLT_RANGES)
        assert fmt is not None
        return ReadingSpec(fmt[0], fmt[1], "AC", True, f"ac_v:{name}")
    if kind == "ohm":
        u = rng.uniform()
        if u < 0.1:
            name, r = "shorted probes", rng.uniform(0.1, 0.6)
        else:
            ref, nominal, tol = RESISTORS[int(rng.integers(len(RESISTORS)))]
            r = nominal * (1.0 + rng.normal(0.0, tol / 2))
            name = f"{ref} lifted"
            if u > 0.85:
                r *= rng.uniform(1.3, 4.0)
                name += ", drifted high"
        fmt = format_reading(r, OHM_RANGES)
        assert fmt is not None
        return ReadingSpec(fmt[0], fmt[1], "resistance", True, f"ohm:{name}")
    if rng.uniform() < 0.7:
        return ReadingSpec(OVERLOAD_TEXT, "MΩ", "resistance", True, "overload: open circuit on Ω")
    return ReadingSpec(OVERLOAD_TEXT, "mV", "DC", False, "overload: rail measured on the mV position")


# ---------------------------------------------------------------------------
# Meter models and camera settings
# ---------------------------------------------------------------------------

BODY_COLOURS: dict[str, RGB] = {
    "yellow": (226, 184, 42), "orange": (224, 116, 36), "red": (182, 42, 44), "grey": (92, 94, 100),
    "blue": (54, 88, 140), "green": (48, 118, 80), "black": (44, 44, 48),
}
LCD_COLOURS: tuple[RGB, ...] = (
    (176, 184, 166), (182, 184, 178), (168, 182, 160), (170, 178, 184), (186, 186, 170),
)


@dataclass(frozen=True)
class MeterStyle:
    body_name: str
    body: RGB
    panel: RGB
    bezel: RGB
    lcd: RGB
    segment: RGB
    ghost: float  # visibility of inactive segments (0 = invisible, 1 = like active)
    segment_shadow: float  # faint offset copy of active segments (LCD reflector)
    symbols: bool  # ⎓ / ~ instead of the words DC / AC
    bargraph: bool
    battery: bool
    hold: bool
    buttons: tuple[RGB, ...]

    def to_json(self) -> dict[str, Any]:
        return {"body": self.body_name, "lcd": list(self.lcd), "ghost": round(self.ghost, 3),
                "segment_shadow": round(self.segment_shadow, 3), "symbols": self.symbols,
                "bargraph": self.bargraph, "battery": self.battery, "hold": self.hold}


def _sample_style(rng: np.random.Generator, difficulty: str) -> MeterStyle:
    name = list(BODY_COLOURS)[int(rng.integers(len(BODY_COLOURS)))]
    body = _jitter(rng, BODY_COLOURS[name], 10)
    panel_v = int(rng.integers(46, 64))
    lcd = _jitter(rng, LCD_COLOURS[int(rng.integers(len(LCD_COLOURS)))], 6)
    ghost_hi = {"easy": 0.06, "medium": 0.1, "hard": 0.14}[difficulty]
    ghost = 0.0 if rng.uniform() < 0.45 else float(rng.uniform(0.02, ghost_hi))
    grey = (150, 150, 156)
    buttons = (
        (228, 190, 40) if name != "yellow" else (70, 110, 190),
        (70, 110, 190) if rng.uniform() < 0.5 else grey,
        grey,
        grey,
    )
    return MeterStyle(
        body_name=name,
        body=body,
        panel=(panel_v, panel_v, panel_v + 4),
        bezel=_jitter(rng, (22, 22, 25), 3),
        lcd=lcd,
        segment=_jitter(rng, (34, 38, 40), 5),
        ghost=ghost,
        segment_shadow=float(rng.uniform(0.08, 0.2)) if rng.uniform() < 0.5 else 0.0,
        symbols=bool(rng.uniform() < 0.5),
        bargraph=bool(rng.uniform() < 0.5),
        battery=bool(rng.uniform() < 0.15),
        hold=bool(rng.uniform() < 0.05),
        buttons=buttons,
    )


def _jitter(rng: np.random.Generator, colour: Sequence[int], amount: int) -> RGB:
    c = [int(np.clip(v + rng.integers(-amount, amount + 1), 0, 255)) for v in colour]
    return (c[0], c[1], c[2])


@dataclass(frozen=True)
class DifficultyProfile:
    tilt: tuple[float, float]  # degrees of camera tilt against the meter plane
    roll: tuple[float, float]  # in-plane rotation, degrees (either sign)
    glass_px: tuple[float, float]  # LCD glass width in a 480-px-wide frame
    glare_p: float
    glare: tuple[float, float]  # peak glare strength (0..1 blend towards white)
    blur: tuple[float, float]  # Gaussian sigma, pixels
    motion_p: float
    motion: tuple[float, float]  # motion-blur length, pixels
    noise: tuple[float, float]  # sensor noise sigma (0..255 scale)
    jpeg: tuple[int, int]  # JPEG quality
    light: float  # strength of lighting / colour-cast changes
    shadow_p: float  # probability of a hard shadow edge across the meter


PROFILES: dict[str, DifficultyProfile] = {
    "easy": DifficultyProfile((0.0, 8.0), (0.0, 4.0), (240.0, 330.0), 0.25, (0.08, 0.25), (0.0, 0.8),
                              0.0, (0.0, 0.0), (1.0, 3.0), (85, 95), 0.08, 0.0),
    "medium": DifficultyProfile((4.0, 16.0), (2.0, 9.0), (210.0, 320.0), 0.5, (0.2, 0.45), (0.5, 1.5),
                                0.25, (3.0, 7.0), (2.0, 6.0), (70, 90), 0.18, 0.15),
    "hard": DifficultyProfile((10.0, 25.0), (5.0, 15.0), (185.0, 300.0), 0.8, (0.35, 0.8), (1.0, 2.2),
                              0.35, (5.0, 10.0), (4.0, 9.0), (45, 75), 0.3, 0.35),
}

# ---------------------------------------------------------------------------
# Drawing helpers (cv2 with anti-aliasing and 1/16-pixel precision)
# ---------------------------------------------------------------------------

_SHIFT = 4
_ONE = 1 << _SHIFT


def _px(points: Sequence[Point], k: float, ox: float, oy: float) -> np.ndarray:
    arr = (np.asarray(points, dtype=np.float64) + np.array([ox, oy])) * (k * _ONE)
    return np.asarray(np.round(arr), dtype=np.int32).reshape(-1, 1, 2)


def _fill(img: np.ndarray, points: Sequence[Point], colour: RGB | int, k: float,
          ox: float = 0.0, oy: float = 0.0) -> None:
    cv2.fillPoly(img, [_px(points, k, ox, oy)], colour, lineType=cv2.LINE_AA, shift=_SHIFT)


def _stroke(img: np.ndarray, lines: Sequence[Sequence[Point]], colour: RGB | int, width: float,
            k: float, ox: float = 0.0, oy: float = 0.0, closed: bool = False) -> None:
    thickness = max(1, round(width * k))
    cv2.polylines(img, [_px(line, k, ox, oy) for line in lines], closed, colour, thickness,
                  lineType=cv2.LINE_AA, shift=_SHIFT)


def _circle(img: np.ndarray, centre: Point, radius: float, colour: RGB | int, k: float,
            thickness: float = -1.0) -> None:
    c = (round(centre[0] * k * _ONE), round(centre[1] * k * _ONE))
    th = -1 if thickness < 0 else max(1, round(thickness * k))
    cv2.circle(img, c, round(radius * k * _ONE), colour, th, lineType=cv2.LINE_AA, shift=_SHIFT)


def rounded_rect(x0: float, y0: float, x1: float, y1: float, r: float, n: int = 8) -> Polyline:
    pts: Polyline = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90.0), (x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, 90.0),
                       (x0 + r, y0 + r, 180.0)):
        pts += _arc(cx, cy, r, r, a0, a0 + 90.0, n + 1)
    return pts


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return (round(a[0] + t * (b[0] - a[0])), round(a[1] + t * (b[1] - a[1])), round(a[2] + t * (b[2] - a[2])))


# ---------------------------------------------------------------------------
# Meter face
# ---------------------------------------------------------------------------


def _draw_lcd(img: np.ndarray, k: float, style: MeterStyle, disp: DisplayState,
              rng: np.random.Generator) -> None:
    ox, oy = GLASS_X0, GLASS_Y0
    glass = (round(GLASS_X0 * k), round(GLASS_Y0 * k), round((GLASS_X0 + LCD_W) * k),
             round((GLASS_Y0 + LCD_H) * k))
    _fill(img, [(0, 0), (LCD_W, 0), (LCD_W, LCD_H), (0, LCD_H)], style.lcd, k, ox, oy)
    # gentle brightness gradient across the glass
    x0, y0, x1, y1 = glass
    gy, gx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    ang = rng.uniform(0, 2 * math.pi)
    ramp = ((gx - x0) * math.cos(ang) + (gy - y0) * math.sin(ang)) / max(x1 - x0, 1)
    region = img[y0:y1, x0:x1].astype(np.float32) * (1.0 + 0.05 * ramp)[..., None]
    img[y0:y1, x0:x1] = np.clip(region, 0, 255).astype(np.uint8)

    on_polys: list[Polyline] = []
    off_polys: list[Polyline] = []
    for i, ch in enumerate(disp.chars):
        polys = segment_polygons(i)
        for s in SEGMENTS:
            (on_polys if s in PATTERNS[ch] else off_polys).append(polys[s])
    for i in range(N_DIGITS - 1):
        (on_polys if disp.dp == i else off_polys).append(dp_polygon(i))
    (on_polys if disp.minus else off_polys).append(minus_polygon())
    if style.bargraph:
        n_on = round(disp.bar_fraction * BAR_COUNT)
        for i in range(BAR_COUNT):
            (on_polys if i < n_on else off_polys).append(bar_polygon(i))

    slot = "sym" if style.symbols else "text"
    on_icons = list(UNIT_ICONS[disp.unit])
    if disp.mode in ("DC", "AC"):
        on_icons.append(f"{disp.mode}_{slot}")
    if disp.auto:
        on_icons.append("AUTO")
    if style.hold:
        on_icons.append("HOLD")
    candidates = ["AUTO", f"DC_{slot}", f"AC_{slot}", "HOLD", "M", "k", "Ω", "m", "V"]
    off_icons = [n for n in candidates if n not in on_icons]

    if style.ghost > 0:
        ghost = _mix(style.lcd, style.segment, style.ghost)
        for p in off_polys:
            _fill(img, p, ghost, k, ox, oy)
        for name in off_icons:
            _stroke(img, ICONS[name].strokes(), ghost, ICONS[name].stroke, k, ox, oy)
    if style.segment_shadow > 0:
        shade = _mix(style.lcd, style.segment, style.segment_shadow)
        for p in on_polys:
            _fill(img, p, shade, k, ox + 1.6, oy + 2.2)
        for name in on_icons:
            _stroke(img, ICONS[name].strokes(), shade, ICONS[name].stroke, k, ox + 1.6, oy + 2.2)
    for p in on_polys:
        _fill(img, p, _mix(style.segment, style.lcd, float(rng.uniform(0.0, 0.08))), k, ox, oy)
    for name in on_icons:
        _stroke(img, ICONS[name].strokes(), style.segment, ICONS[name].stroke, k, ox, oy)
    if style.bargraph:  # printed scale under the bar graph (always visible)
        _stroke(img, scale_strokes(), style.segment, 1.6, k, ox, oy)
    if style.battery:
        bx0, by0, bx1, by1 = BATTERY_BOX
        _stroke(img, [[(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)]], style.segment, 2.4, k, ox, oy,
                closed=True)
        _fill(img, [(bx1, by0 + 5), (bx1 + 3, by0 + 5), (bx1 + 3, by1 - 5), (bx1, by1 - 5)],
              style.segment, k, ox, oy)
        _fill(img, [(bx0 + 3, by0 + 3), (bx0 + 9, by0 + 3), (bx0 + 9, by1 - 3), (bx0 + 3, by1 - 3)],
              style.segment, k, ox, oy)


def _dial_function(disp: DisplayState) -> str:
    if disp.mode == "resistance":
        return "Ω"
    if disp.unit == "mV":
        return "mV"
    return "V~" if disp.mode == "AC" else "V⎓"


def _draw_face(style: MeterStyle, disp: DisplayState, k: float,
               rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Render the meter face at ``k`` pixels per face unit.

    Returns (RGB image, body alpha mask, LCD window mask).
    """
    w, h = math.ceil(FACE_W * k), math.ceil(FACE_H * k)
    img = np.zeros((h, w, 3), np.uint8)
    alpha = np.zeros((h, w), np.uint8)
    window = np.zeros((h, w), np.uint8)
    body = rounded_rect(0.0, 0.0, FACE_W, FACE_H, BODY_RADIUS)
    _fill(alpha, body, 255, k)
    _fill(img, body, style.body, k)
    lip = _mix(style.body, (0, 0, 0), 0.25)
    _stroke(img, [rounded_rect(12.0, 12.0, FACE_W - 12.0, FACE_H - 12.0, BODY_RADIUS - 12.0)], lip, 5.0, k,
            closed=True)
    _fill(img, rounded_rect(*PANEL, 36.0), style.panel, k)
    bezel = rounded_rect(*BEZEL, 10.0)
    _fill(img, bezel, style.bezel, k)
    _fill(window, bezel, 255, k)
    _draw_lcd(img, k, style, disp, rng)

    legend = (225, 225, 225)
    labels = ("SEL", "RANGE", "HOLD", "REL")
    for j, colour in enumerate(style.buttons):
        bx = 70.0 + j * 110.0
        _fill(img, rounded_rect(bx, 356.0, bx + 90.0, 400.0, 12.0), _mix(colour, (0, 0, 0), 0.35), k, 0, 3)
        _fill(img, rounded_rect(bx, 356.0, bx + 90.0, 400.0, 12.0), colour, k)
        tw = text_width(labels[j], 13.0)
        _stroke(img, text_strokes(labels[j], bx + 45.0 - tw / 2, 410.0, 13.0), legend, 2.2, k)

    cx, cy = DIAL_CENTRE
    _circle(img, DIAL_CENTRE, 168.0, _mix(style.panel, (255, 255, 255), 0.08), k)
    selected = DIAL_FUNCTIONS.index(_dial_function(disp))
    for name, ang in zip(DIAL_FUNCTIONS, DIAL_ANGLES, strict=True):
        a = math.radians(ang)
        ux, uy = math.sin(a), -math.cos(a)
        _stroke(img, [[(cx + 172 * ux, cy + 172 * uy), (cx + 186 * ux, cy + 186 * uy)]], legend, 3.0, k)
        tw = text_width(name, 24.0)
        _stroke(img, text_strokes(name, cx + 216 * ux - tw / 2, cy + 216 * uy - 12.0, 24.0), legend, 3.0, k)
    _circle(img, DIAL_CENTRE, 132.0, (38, 38, 42), k)
    _circle(img, DIAL_CENTRE, 132.0, (70, 70, 76), k, thickness=4.0)
    a = math.radians(DIAL_ANGLES[selected])
    ux, uy = math.sin(a), -math.cos(a)
    grip = [(cx - 118 * ux, cy - 118 * uy), (cx + 118 * ux, cy + 118 * uy)]
    _stroke(img, [grip], (58, 58, 64), 46.0, k)
    _stroke(img, [[(cx + 40 * ux, cy + 40 * uy), (cx + 124 * ux, cy + 124 * uy)]], (235, 235, 230), 12.0, k)

    for name, (jx, jy) in JACKS.items():
        ring = (170, 30, 30) if name != "COM" else (20, 20, 20)
        _circle(img, (jx, jy), 38.0, (30, 30, 32), k)
        _circle(img, (jx, jy), 32.0, ring, k, thickness=7.0)
        _circle(img, (jx, jy), 16.0, (8, 8, 8), k)
        tw = text_width(name, 18.0)
        _stroke(img, text_strokes(name, jx - tw / 2, jy - 70.0, 18.0), legend, 2.6, k)

    # soft lighting across the body so it does not look flat
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    shade = 1.04 - 0.1 * (xx / w + yy / h) / 2
    img = np.clip(img.astype(np.float32) * shade[..., None], 0, 255).astype(np.uint8)
    return img, alpha, window


# ---------------------------------------------------------------------------
# Scene, camera and image effects
# ---------------------------------------------------------------------------


def _smooth_noise(rng: np.random.Generator, h: int, w: int, cell: int) -> np.ndarray:
    small = rng.standard_normal((h // cell + 3, w // cell + 3)).astype(np.float32)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


def _background(rng: np.random.Generator, w: int, h: int) -> tuple[np.ndarray, str]:
    kind = ("wood", "cutting_mat", "esd_mat", "desk", "fabric")[int(rng.integers(5))]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = rng.uniform(0, math.pi)
    u = xx * math.cos(ang) + yy * math.sin(ang)
    v = -xx * math.sin(ang) + yy * math.cos(ang)
    if kind == "wood":
        base = np.array(_jitter(rng, (170, 118, 72), 20), np.float32)
        warp = _smooth_noise(rng, h, w, 50) * 14.0
        grain = 0.5 + 0.5 * np.sin((v + warp) * rng.uniform(0.12, 0.3))
        shade = 1.0 - 0.2 * grain**3 + 0.05 * _smooth_noise(rng, h, w, 6)
    elif kind == "cutting_mat":
        base = np.array(_jitter(rng, (46, 118, 88), 12), np.float32)
        pitch = rng.uniform(22.0, 40.0)
        lines = (np.mod(u, pitch) < 1.2) | (np.mod(v, pitch) < 1.2)
        bold = (np.mod(u, pitch * 5) < 2.2) | (np.mod(v, pitch * 5) < 2.2)
        shade = 1.0 + 0.45 * lines + 0.35 * bold + 0.03 * _smooth_noise(rng, h, w, 40)
    elif kind == "esd_mat":
        base = np.array(_jitter(rng, (96, 116, 134), 12), np.float32)
        speckle = rng.standard_normal((h, w)).astype(np.float32)
        shade = 1.0 + 0.06 * speckle + 0.05 * _smooth_noise(rng, h, w, 30)
    elif kind == "desk":
        base = np.array(_jitter(rng, (212, 208, 200), 15), np.float32)
        shade = 1.0 + 0.03 * _smooth_noise(rng, h, w, 60) + 0.015 * _smooth_noise(rng, h, w, 4)
    else:
        base = np.array(_jitter(rng, (46, 44, 52), 10), np.float32)
        weave = np.sin(u * 1.3) * np.sin(v * 1.3)
        shade = 1.0 + 0.12 * weave + 0.08 * _smooth_noise(rng, h, w, 20)
    img = np.clip(base[None, None, :] * shade[..., None], 0, 255).astype(np.uint8)
    for _ in range(int(rng.integers(0, 4))):
        _clutter(img, rng)
    img = cv2.GaussianBlur(img, (0, 0), float(rng.uniform(0.8, 2.2)))
    return img, kind


def _clutter(img: np.ndarray, rng: np.random.Generator) -> None:
    """A PCB, a screwdriver or a loose wire lying on the bench."""
    h, w = img.shape[:2]
    cx, cy = rng.uniform(0, w), rng.uniform(0, h)
    ang = rng.uniform(0, math.pi)
    ca, sa = math.cos(ang), math.sin(ang)

    def rot(pts: Sequence[Point]) -> np.ndarray:
        return np.array([(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts], np.int32)

    item = int(rng.integers(3))
    if item == 0:
        bw, bh = rng.uniform(90, 200), rng.uniform(60, 140)
        cv2.fillPoly(img, [rot([(-bw / 2, -bh / 2), (bw / 2, -bh / 2), (bw / 2, bh / 2), (-bw / 2, bh / 2)])],
                     _jitter(rng, (38, 110, 60), 10), lineType=cv2.LINE_AA)
        for _ in range(8):
            p = [(rng.uniform(-bw / 2, bw / 2), rng.uniform(-bh / 2, bh / 2)) for _ in range(3)]
            cv2.polylines(img, [rot(p)], False, (70, 150, 96), 2, lineType=cv2.LINE_AA)
        for _ in range(10):
            x, y = rng.uniform(-bw / 2, bw / 2), rng.uniform(-bh / 2, bh / 2)
            cv2.circle(img, tuple(int(v) for v in rot([(x, y)])[0]), 3, (190, 188, 170), -1, cv2.LINE_AA)
        chip = [(-20, -12), (20, -12), (20, 12), (-20, 12)]
        cv2.fillPoly(img, [rot(chip)], (24, 24, 26), lineType=cv2.LINE_AA)
    elif item == 1:
        length = rng.uniform(140, 260)
        cv2.fillPoly(img, [rot([(0, -3), (length * 0.55, -3), (length * 0.55, 3), (0, 3)])], (180, 180, 185),
                     lineType=cv2.LINE_AA)
        handle = [(length * 0.55, -12), (length, -12), (length, 12), (length * 0.55, 12)]
        cv2.fillPoly(img, [rot(handle)], _jitter(rng, (200, 50, 40), 40), lineType=cv2.LINE_AA)
    else:
        pts = [(0.0, 0.0)]
        for _ in range(4):
            pts.append((pts[-1][0] + rng.uniform(40, 90), pts[-1][1] + rng.uniform(-50, 50)))
        colour = [(200, 40, 40), (30, 30, 30), (230, 200, 40), (40, 90, 200)][int(rng.integers(4))]
        cv2.polylines(img, [rot(pts)], False, colour, int(rng.integers(3, 6)), lineType=cv2.LINE_AA)


def _rotation(tilt: float, tilt_dir: float, roll: float) -> np.ndarray:
    t = math.radians(tilt)
    pitch, yaw, r = t * math.cos(tilt_dir), t * math.sin(tilt_dir), math.radians(roll)
    rx = np.array([[1, 0, 0], [0, math.cos(pitch), -math.sin(pitch)], [0, math.sin(pitch), math.cos(pitch)]])
    ry = np.array([[math.cos(yaw), 0, math.sin(yaw)], [0, 1, 0], [-math.sin(yaw), 0, math.cos(yaw)]])
    rz = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]])
    return np.asarray(rz @ rx @ ry, dtype=np.float64)


def _plane_homography(rot: np.ndarray, focal: float, scale: float, image_centre: Point) -> np.ndarray:
    """Face units -> image pixels for a pinhole camera looking at the meter plane.

    The LCD centre is placed on the optical axis at a distance where one face
    unit spans ``scale`` pixels.
    """
    z0 = focal / scale
    cam = np.array([[focal, 0, image_centre[0]], [0, focal, image_centre[1]], [0, 0, 1]])
    ext = np.column_stack([rot[:, 0], rot[:, 1], [0.0, 0.0, z0]])
    lcd_centre = (GLASS_X0 + LCD_W / 2, GLASS_Y0 + LCD_H / 2)
    to_centre = np.array([[1, 0, -lcd_centre[0]], [0, 1, -lcd_centre[1]], [0, 0, 1]])
    return np.asarray(cam @ ext @ to_centre, dtype=np.float64)


def _apply_h(hmat: np.ndarray, points: Sequence[Point]) -> np.ndarray:
    pts = np.asarray(points, np.float64)
    hom = np.column_stack([pts, np.ones(len(pts))]) @ hmat.T
    return np.asarray(hom[:, :2] / hom[:, 2:3], dtype=np.float64)


def glass_corners_face() -> list[Point]:
    return [(GLASS_X0, GLASS_Y0), (GLASS_X0 + LCD_W, GLASS_Y0), (GLASS_X0 + LCD_W, GLASS_Y0 + LCD_H),
            (GLASS_X0, GLASS_Y0 + LCD_H)]


def _apply_glare(face: np.ndarray, window: np.ndarray, k: float, centre: Point, axes: Point,
                 angle: float, strength: float) -> None:
    """Specular glare: an elliptical highlight on the LCD window, blended towards white."""
    x0, y0 = int(BEZEL[0] * k), int(BEZEL[1] * k)
    x1, y1 = math.ceil(BEZEL[2] * k), math.ceil(BEZEL[3] * k)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx = xx / k - (GLASS_X0 + centre[0])
    dy = yy / k - (GLASS_Y0 + centre[1])
    ca, sa = math.cos(angle), math.sin(angle)
    r2 = ((dx * ca + dy * sa) / axes[0]) ** 2 + ((-dx * sa + dy * ca) / axes[1]) ** 2
    blend = strength * np.exp(-0.5 * r2) * (window[y0:y1, x0:x1].astype(np.float32) / 255.0)
    region = face[y0:y1, x0:x1].astype(np.float32)
    light = np.array([252.0, 250.0, 244.0], np.float32)
    face[y0:y1, x0:x1] = np.clip(region + blend[..., None] * (light - region), 0, 255).astype(np.uint8)


def _draw_leads(img: np.ndarray, hmat: np.ndarray, scale: float, rng: np.random.Generator) -> None:
    h, w = img.shape[:2]
    for jack, colour in (("COM", (28, 28, 30)), ("VΩ", (176, 30, 32))):
        p0 = _apply_h(hmat, [JACKS[jack]])[0]
        down = _apply_h(hmat, [(JACKS[jack][0], JACKS[jack][1] + 100.0)])[0] - p0
        down /= max(np.linalg.norm(down), 1e-6)
        p1 = p0 + down * rng.uniform(80, 160) + np.array([rng.uniform(-60, 60), 0.0])
        p2 = np.array([p0[0] + rng.uniform(-160, 160), h + 30.0])
        t = np.linspace(0, 1, 40)[:, None]
        curve = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t**2 * p2
        thick = max(3, round(14 * scale))
        pts = np.round(curve * _ONE).astype(np.int32).reshape(-1, 1, 2)
        cv2.circle(img, (round(p0[0] * _ONE), round(p0[1] * _ONE)), round(24 * scale * _ONE), colour, -1,
                   cv2.LINE_AA, _SHIFT)
        cv2.polylines(img, [pts], False, colour, thick, cv2.LINE_AA, _SHIFT)
        hi = tuple(min(255, c + 60) for c in colour)
        highlight = pts - np.array([_ONE, _ONE], np.int32)
        cv2.polylines(img, [highlight], False, hi, max(1, thick // 4), cv2.LINE_AA, _SHIFT)
    del w


def _motion_kernel(length: float, angle: float) -> np.ndarray:
    size = math.ceil(length) | 1
    kern = np.zeros((size, size), np.float32)
    c = size / 2 - 0.5
    dx, dy = math.cos(angle) * (length - 1) / 2, math.sin(angle) * (length - 1) / 2
    start = (round((c - dx) * _ONE), round((c - dy) * _ONE))
    end = (round((c + dx) * _ONE), round((c + dy) * _ONE))
    cv2.line(kern, start, end, 1.0, 1, cv2.LINE_AA, _SHIFT)
    return kern / max(float(kern.sum()), 1e-6)


def _r(x: float, nd: int = 3) -> float:
    return round(float(x), nd)


def render_meter(value_text: str, unit: str, mode: str, rng: np.random.Generator,
                 difficulty: str = "easy", auto: bool = True) -> tuple[Image.Image, dict[str, Any]]:
    """Render one synthetic phone photo of the meter showing ``value_text`` ``unit`` in ``mode``.

    ``difficulty`` is "easy", "medium" or "hard" (strength of the camera effects).
    Returns the photo (already through JPEG compression) and its label: value_text
    (normalised), value (float in the displayed unit, None for overload), unit,
    mode, difficulty and params (meter model, camera, effects, LCD corners in the
    image). The generator ``rng`` is the only source of randomness.
    """
    if difficulty not in PROFILES:
        raise ValueError(f"difficulty must be one of {DIFFICULTIES}")
    prof = PROFILES[difficulty]
    disp = display_state(value_text, unit, mode, auto)
    style = _sample_style(rng, difficulty)

    portrait = rng.uniform() < 0.7
    w, h = (480, 640) if portrait else (640, 480)
    focal = 1.1 * max(w, h)
    tilt = rng.uniform(*prof.tilt)
    tilt_dir = rng.uniform(0, 2 * math.pi)
    roll = rng.uniform(*prof.roll) * (1 if rng.uniform() < 0.5 else -1)
    scale = rng.uniform(*prof.glass_px) / LCD_W * (1.0 if portrait else 0.95)
    rot = _rotation(tilt, tilt_dir, roll)
    cx = rng.uniform(0.4, 0.6) * w
    cy = rng.uniform(0.3, 0.45) * h if portrait else rng.uniform(0.35, 0.5) * h
    centre = (cx, cy)
    margin = 12.0
    hmat = _plane_homography(rot, focal, scale, centre)
    for _ in range(40):  # keep the whole LCD window in frame
        hmat = _plane_homography(rot, focal, scale, centre)
        box = _apply_h(hmat, [(BEZEL[0], BEZEL[1]), (BEZEL[2], BEZEL[1]), (BEZEL[2], BEZEL[3]),
                              (BEZEL[0], BEZEL[3])])
        if box[:, 0].min() >= margin and box[:, 1].min() >= margin and box[:, 0].max() <= w - margin \
                and box[:, 1].max() <= h - margin:
            break
        scale *= 0.96
        centre = (0.8 * centre[0] + 0.2 * w / 2, 0.8 * centre[1] + 0.2 * h / 2)

    # Twisted-nematic LCDs lose contrast when viewed off-axis.
    lcd_contrast = 1.0 - 0.3 * (math.sin(math.radians(tilt)) / math.sin(math.radians(25.0))) ** 2
    style = replace(style, segment=_mix(style.segment, style.lcd, 1.0 - lcd_contrast))
    k = min(1.6, 1.3 * scale)  # face raster resolution, a little above the photo's
    face, alpha, window = _draw_face(style, disp, k, rng)
    glare: dict[str, Any] | None = None
    if rng.uniform() < prof.glare_p:
        glare = {
            "centre": [_r(rng.uniform(30, LCD_W - 30), 1), _r(rng.uniform(20, LCD_H - 20), 1)],
            "axes": [_r(rng.uniform(50, 170), 1), _r(rng.uniform(22, 80), 1)],
            "angle": _r(rng.uniform(-0.7, 0.7)),
            "strength": _r(rng.uniform(*prof.glare)),
        }
        _apply_glare(face, window, k, tuple(glare["centre"]), tuple(glare["axes"]), glare["angle"],
                     glare["strength"])

    to_px = hmat @ np.diag([1.0 / k, 1.0 / k, 1.0])
    background, bg_kind = _background(rng, w, h)
    scene: np.ndarray = background.astype(np.float32)
    # contact shadow of the meter on the bench
    light_dir = rng.uniform(0, 2 * math.pi)
    off = rng.uniform(5, 18)
    shift = np.array([[1, 0, off * math.cos(light_dir)], [0, 1, off * math.sin(light_dir)], [0, 0, 1]])
    shadow: np.ndarray = cv2.warpPerspective(alpha, shift @ to_px, (w, h), flags=cv2.INTER_LINEAR)
    shadow = shadow.astype(np.float32)
    shadow = cv2.GaussianBlur(shadow / 255.0, (0, 0), float(rng.uniform(6, 14)))
    scene *= (1.0 - rng.uniform(0.25, 0.5) * shadow)[..., None]
    warped = cv2.warpPerspective(face, to_px, (w, h), flags=cv2.INTER_LINEAR).astype(np.float32)
    a = cv2.warpPerspective(alpha, to_px, (w, h), flags=cv2.INTER_LINEAR).astype(np.float32)[..., None] / 255
    scene = scene * (1.0 - a) + warped * a
    scene_u8 = np.clip(scene, 0, 255).astype(np.uint8)
    _draw_leads(scene_u8, hmat, scale, rng)
    img: np.ndarray = scene_u8.astype(np.float32)

    # lighting: global gain/offset, colour cast, gradient and vignetting
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    gain = 1.0 + rng.uniform(-prof.light, prof.light * 0.5)
    offset = rng.uniform(-25, 15) * prof.light / 0.3
    cast = 1.0 + rng.uniform(-0.6, 0.6, 3) * prof.light
    g_ang = rng.uniform(0, 2 * math.pi)
    ramp = ((xx - w / 2) * math.cos(g_ang) + (yy - h / 2) * math.sin(g_ang)) / max(w, h)
    grad = 1.0 + rng.uniform(0, 1.5 * prof.light) * ramp
    rr = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / ((w / 2) ** 2 + (h / 2) ** 2)
    vig = 1.0 - rng.uniform(0.05, 0.3) * rr
    img = img * (gain * grad * vig)[..., None] * cast[None, None, :] + offset
    shadow_edge: dict[str, float] | None = None
    if rng.uniform() < prof.shadow_p:
        s_ang = rng.uniform(0, 2 * math.pi)
        px_, py_ = rng.uniform(0.2, 0.8) * w, rng.uniform(0.2, 0.8) * h
        dist = (xx - px_) * math.cos(s_ang) + (yy - py_) * math.sin(s_ang)
        soft = rng.uniform(6, 25)
        depth = rng.uniform(0.15, 0.4)
        img *= (1.0 - depth / (1.0 + np.exp(-dist / soft)))[..., None]
        shadow_edge = {"angle": _r(s_ang), "depth": _r(depth), "softness": _r(soft, 1)}

    blur_sigma = rng.uniform(*prof.blur)
    motion: dict[str, float] | None = None
    if rng.uniform() < prof.motion_p:
        length, m_ang = rng.uniform(*prof.motion), rng.uniform(0, math.pi)
        img = cv2.filter2D(img, -1, _motion_kernel(length, m_ang))
        motion = {"length": _r(length, 2), "angle": _r(m_ang)}
        blur_sigma *= 0.4
    if blur_sigma > 0.25:
        img = cv2.GaussianBlur(img, (0, 0), blur_sigma)
    noise = rng.uniform(*prof.noise)
    img += rng.normal(0.0, noise, (h, w, 1)).astype(np.float32)
    img += rng.normal(0.0, noise * 0.4, (h, w, 3)).astype(np.float32)
    quality = int(rng.integers(prof.jpeg[0], prof.jpeg[1] + 1))
    photo = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), mode="RGB")
    photo = Image.open(io.BytesIO(encode_jpeg(photo, quality))).convert("RGB")

    corners = _apply_h(hmat, glass_corners_face())
    label = {
        "value_text": normalize_value_text(value_text),
        "value": value_of(value_text),
        "unit": unit,
        "mode": mode,
        "difficulty": difficulty,
        "params": {
            "size": [w, h],
            "meter": style.to_json(),
            "auto": auto,
            "camera": {"tilt_deg": _r(tilt, 2), "tilt_dir": _r(tilt_dir), "roll_deg": _r(roll, 2),
                       "glass_px": _r(scale * LCD_W, 1), "focal_px": _r(focal, 1)},
            "lcd_contrast": _r(lcd_contrast),
            "glare": glare,
            "blur_sigma": _r(blur_sigma),
            "motion_blur": motion,
            "noise_sigma": _r(noise),
            "jpeg_quality": quality,
            "lighting": {"gain": _r(gain), "offset": _r(offset, 2), "cast": [_r(c) for c in cast]},
            "shadow_edge": shadow_edge,
            "background": bg_kind,
            "lcd_corners": [[_r(x, 2), _r(y, 2)] for x, y in corners],
        },
    }
    return photo, label


def encode_jpeg(image: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def generate_dataset(n: int = 300, out_dir: Path = SYNTHETIC_DIR,
                     seed: int = DEFAULT_SEED) -> list[dict[str, Any]]:
    """Render ``n`` photos into ``out_dir`` with ``labels.jsonl`` (40 % easy, 40 % medium, 20 % hard).

    Image ``i`` uses the generator ``default_rng([seed, i])``, so any single image
    can be regenerated on its own and the dataset is identical for a given seed.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n_easy, n_medium = round(n * DIFFICULTY_MIX["easy"]), round(n * DIFFICULTY_MIX["medium"])
    levels = ["easy"] * n_easy + ["medium"] * n_medium + ["hard"] * (n - n_easy - n_medium)
    levels = [levels[j] for j in np.random.default_rng(seed).permutation(n)]
    labels: list[dict[str, Any]] = []
    for i, difficulty in enumerate(levels):
        rng = np.random.default_rng([seed, i])
        spec = sample_reading(rng)
        photo, label = render_meter(spec.value_text, spec.unit, spec.mode, rng, difficulty, auto=spec.auto)
        name = f"meter_{i:04d}.jpg"
        photo.save(out_dir / name, format="JPEG", quality=label["params"]["jpeg_quality"])
        label["params"]["scenario"] = spec.scenario
        labels.append({"file": name, **label})
    keep = {lab["file"] for lab in labels}
    for stale in out_dir.glob("meter_*.jpg"):
        if stale.name not in keep:
            stale.unlink()
    with open(out_dir / "labels.jsonl", "w", encoding="utf-8") as fh:
        for lab in labels:
            fh.write(json.dumps(lab, ensure_ascii=False) + "\n")
    return labels


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Render the synthetic meter-photo dataset.")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--out", type=Path, default=SYNTHETIC_DIR)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args(argv)
    labels = generate_dataset(args.n, args.out, args.seed)
    counts = {d: sum(lab["difficulty"] == d for lab in labels) for d in DIFFICULTIES}
    print(f"wrote {len(labels)} photos to {args.out} ({counts})")


if __name__ == "__main__":
    main()
