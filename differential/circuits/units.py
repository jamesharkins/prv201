"""SPICE value parsing and engineering-notation formatting."""

from __future__ import annotations

import math
import re

_SUFFIX = {
    "t": 1e12,
    "g": 1e9,
    "meg": 1e6,
    "k": 1e3,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}
_NUM = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Zµ]*)$")


def parse_value(text: str) -> float:
    """Parse a SPICE number such as ``2200u``, ``1Meg``, ``4.7k`` or ``1e-9``.

    Trailing unit letters after the scale suffix (``10uF``) are ignored, as SPICE does.
    """
    token = text.strip()
    m = _NUM.match(token)
    if not m:
        raise ValueError(f"not a SPICE number: {text!r}")
    mantissa = float(m.group(1))
    suffix = m.group(2).lower()
    if not suffix:
        return mantissa
    if suffix.startswith("meg"):
        return mantissa * 1e6
    scale = _SUFFIX.get(suffix[0])
    if scale is None:
        # Pure unit text such as "V" or "Ohm": no scaling.
        return mantissa
    return mantissa * scale


_PREFIXES = [
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "µ"),
    (1e-9, "n"),
    (1e-12, "p"),
]


def format_si(value: float, unit: str = "", digits: int = 3) -> str:
    """Human-readable engineering notation, e.g. ``format_si(2.2e-3, 'F') -> '2.2 mF'``."""
    if value == 0 or not math.isfinite(value):
        return f"{value:g} {unit}".strip()
    mag = abs(value)
    for scale, prefix in _PREFIXES:
        if mag >= scale * 0.9995:
            scaled = value / scale
            text = f"{scaled:.{digits}g}"
            return f"{text} {prefix}{unit}".strip()
    scale, prefix = _PREFIXES[-1]
    return f"{value / scale:.{digits}g} {prefix}{unit}".strip()


def spice_number(value: float) -> str:
    """Render a float for a netlist or ``alter`` command (full precision, no suffix)."""
    return f"{value:.9g}"
