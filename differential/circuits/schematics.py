"""Schematic renderer for the circuit library (SVG, PNG, dark SVG and test-point maps).

For every circuit id this writes, next to the netlist in ``circuits/<id>/``:

* ``<id>_schematic.svg`` and ``<id>_schematic.png``: dark lines on white;
* ``<id>_schematic_dark.svg``: light lines (#e6e6e6) on a transparent background, same geometry;
* ``<id>_testpoints.json``: each test point's marker position in the SVG's user coordinates
  (the viewBox system), so a web page can overlay a clickable circle on it.

Each block (PSU LV and HV rows, triode stage, tone control, op-amp stage, line driver) has a
small layout helper that places its parts on a local grid and returns its ports. The standalone
schematics add the bench fixtures from the netlist; the channel strip reuses the same helpers on
one landscape sheet, with the PSU along the top and its rails wired down to the stages.

Only real parts are drawn. The ESR resistor of an electrolytic and the three track elements of a
potentiometer belong to one symbol; behavioural sources, sense sources, inductors and parameter
nodes are simulation infrastructure, and the PSU shows a "rectifier out" source in their place.

Every render is checked before anything is written: each component is drawn exactly once, the
drawn wiring reproduces the netlist connectivity (no opens, no shorts, no stray wire ends or
crossings), each test point sits on its own node, and no label touches a line, a marker or
another label. Junction dots are placed wherever three or more connections meet.

Run ``python -m differential.circuits.schematics`` to regenerate every circuit.
"""

from __future__ import annotations

import io
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, TypeVar

import matplotlib
import numpy as np
import schemdraw
import schemdraw.elements as elm
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.transforms import Bbox
from schemdraw.elements import Element, Element2Term
from schemdraw.segments import Segment, SegmentArc, SegmentCircle

from differential.circuits.library import CIRCUIT_IDS, get_circuit
from differential.circuits.model import CircuitSpec, ComponentSpec
from differential.circuits.netlist import Element as NetElement
from differential.circuits.units import format_si, parse_value
from differential.config import CIRCUITS_DIR

Pt = tuple[float, float]
Side = Literal["left", "right", "above", "below"]
Compass = Literal["n", "s", "e", "w", "ne", "nw", "se", "sw"]
Role = Literal["ink", "muted", "tp_hv", "tp_lv"]

# ---------------------------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------------------------
IN_PER_UNIT = 0.5  # 1 grid unit = 0.5 in = 36 SVG user units (pt)
PNG_DPI = 150
LINE_W = 1.3
FONT_FAMILY = ["Inter", "DejaVu Sans"]
SVG_FONT_STACK = "'Inter', 'DejaVu Sans', 'Helvetica Neue', Arial, sans-serif"
FS_LABEL = 9.5  # component labels, rail names
FS_TP = 8.5  # test-point ids
FS_SMALL = 7.5  # pin numbers, fixture captions, notes
FS_STAGE = 9.0  # stage headings
FS_TITLE = 13.0
MARGIN = 0.6  # grid units of white space around the drawing
SIZE_STEP_PT = 12.0  # sheet sizes are multiples of 12 pt (= 25 px at 150 dpi)
TP_RING = 11.0  # test-point ring diameter (pt)
TP_DOT = 4.6  # test-point centre dot diameter (pt)
LINE_PITCH = 1.39  # baseline pitch of multi-line labels (em)

HV_COLOR = "#d03b3b"
LV_COLOR = "#0b6e69"


@dataclass(frozen=True)
class Theme:
    name: str
    ink: str
    muted: str
    background: str | None  # None = transparent
    tp_text: dict[bool, str]  # hv -> colour of the "TPn" label


LIGHT = Theme("light", ink="#1b1b1b", muted="#6b6b6b", background="#ffffff",
              tp_text={True: HV_COLOR, False: LV_COLOR})
DARK = Theme("dark", ink="#e6e6e6", muted="#a3a3a3", background=None,
             tp_text={True: "#ee7b7b", False: "#4fb8b0"})


def _colour(theme: Theme, role: Role) -> str:
    if role == "tp_hv":
        return theme.tp_text[True]
    if role == "tp_lv":
        return theme.tp_text[False]
    return theme.ink if role == "ink" else theme.muted


# ---------------------------------------------------------------------------------------------
# Custom symbols
# ---------------------------------------------------------------------------------------------
E = TypeVar("E", bound=Element)


def _new(cls: type[E], **kwargs: Any) -> E:
    """Instantiate a schemdraw element (several have unannotated constructors)."""
    return cls(**kwargs)


TUBE_R = 1.0  # triode envelope radius


class TriodeSymbol(Element):  # type: ignore[no-untyped-call]
    """Triode from primitives: round envelope, plate, dashed control grid and cathode.

    Anchors: ``plate`` (top of the envelope), ``grid`` (left) and ``cathode`` (bottom).
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        r, w, y_el = TUBE_R, 0.42, 0.42
        self.segments.append(SegmentCircle((0.0, 0.0), r))
        self.segments.append(Segment([(-w, y_el), (w, y_el)]))  # plate
        self.segments.append(Segment([(0.0, y_el), (0.0, r)]))
        n_dash, gap = 4, 0.09
        dash = (2 * w - (n_dash - 1) * gap) / n_dash
        for i in range(n_dash):  # control grid
            x0 = -w + i * (dash + gap)
            self.segments.append(Segment([(x0, 0.0), (x0 + dash, 0.0)]))
        self.segments.append(Segment([(-r, 0.0), (-w, 0.0)]))
        # indirectly heated cathode: a sleeve with turned-down ends, lead from its centre
        self.segments.append(Segment([(-w, -y_el - 0.12), (-w, -y_el), (w, -y_el),
                                      (w, -y_el - 0.12)]))
        self.segments.append(Segment([(0.0, -y_el), (0.0, -r)]))
        self.anchors["plate"] = (0.0, r)
        self.anchors["grid"] = (-r, 0.0)
        self.anchors["cathode"] = (0.0, -r)
        self.anchors["center"] = (0.0, 0.0)


class PolarCap(Element2Term):  # type: ignore[no-untyped-call]
    """Electrolytic capacitor: straight positive plate at the start, curved negative plate.

    ``plus_side`` (+1 or -1) puts the '+' to the left or right of the drawing direction.
    """

    def __init__(self, *, plus_side: int = 1, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        plate, gap, rc = 0.25, 0.2, 0.45
        nan = (math.nan, math.nan)
        self.segments.append(Segment([(0.0, 0.0), nan, (0.0, plate), (0.0, -plate), nan,
                                      (gap, 0.0)]))
        half = math.degrees(math.asin(plate / rc))
        self.segments.append(SegmentArc((gap + rc, 0.0), width=2 * rc, height=2 * rc,
                                        theta1=180 - half, theta2=180 + half))
        px, py, s = -0.17, 0.3 * plus_side, 0.07
        self.segments.append(Segment([(px - s, py), (px + s, py)]))
        self.segments.append(Segment([(px, py - s), (px, py + s)]))


# ---------------------------------------------------------------------------------------------
# Sheet: drawing primitives plus the bookkeeping the checks need
# ---------------------------------------------------------------------------------------------
@dataclass
class _Terminal:
    owner: str  # component ref, fixture or rectifier name, "GND", "FLAG" or "LABEL"
    node: str
    xy: Pt


@dataclass
class _Text:
    xy: Pt
    s: str
    ha: str = "center"
    va: str = "center"
    size: float = FS_LABEL
    weight: str = "normal"
    role: Role = "ink"


@dataclass
class _Site:
    xy: Pt
    label: Compass


@dataclass
class Ports:
    """Connection points a block exposes to its neighbours and to the supplies."""

    inp: Pt
    out: Pt
    rails: dict[str, Pt] = field(default_factory=dict)


def _passive_value(value: str) -> str:
    """SPICE value as printed on a schematic: ``1Meg`` -> ``1M``, ``2200u`` -> ``2200µ``."""
    return re.sub(r"(?i)meg$", "M", value).replace("u", "µ")


def _value_text(comp: ComponentSpec) -> str:
    if comp.kind in {"resistor", "potentiometer", "film_cap", "electrolytic"}:
        return _passive_value(comp.value)
    return comp.value


def _fixture_value(el: NetElement) -> str:
    """Bench-fixture value from its netlist line: a resistance, a DC level or a sine frequency."""
    if el.letter == "R":
        return _passive_value(el.value)
    if sine := re.search(r"SIN\(\s*\S+\s+\S+\s+([^\s)]+)", el.value, re.IGNORECASE):
        return format_si(parse_value(sine.group(1)), "Hz") + " sine"
    if dc := re.search(r"DC\s+(\S+)", el.value, re.IGNORECASE):
        return format_si(parse_value(dc.group(1)), "V", digits=4)
    raise ValueError(f"cannot describe fixture {el.name}: {el.value!r}")


def external_nodes(circuit: CircuitSpec, comp: ComponentSpec) -> list[str]:
    """Nodes of a part that reach the rest of the circuit, in element order.

    Internal nodes (an electrolytic's ESR joint, a pot's track tap) and parameter nodes that
    only feed simulation infrastructure are dropped.
    """
    own = set(comp.elements.values())
    infra = set(circuit.infrastructure)
    used: set[str] = set()
    for el in circuit.netlist.elements:
        if el.name not in own and el.name not in infra:
            used.update(el.nodes)
    out: list[str] = []
    for name in comp.elements.values():
        for node in circuit.netlist.element(name).nodes:
            if (node == "0" or node in used) and node not in out:
                out.append(node)
    return out


def _pt(p: Any) -> Pt:
    """Anchor point snapped to 1e-4 grid units (0.004 pt) so wires stay orthogonal."""
    return (round(float(p[0]), 4) + 0.0, round(float(p[1]), 4) + 0.0)


def _plus_side(start: Pt, end: Pt, label_side: Side) -> int:
    """Side of the element (+1 = left of its direction) facing away from the label."""
    ux, uy = end[0] - start[0], end[1] - start[1]
    away = {"above": (0, -1), "below": (0, 1), "right": (-1, 0), "left": (1, 0)}[label_side]
    return 1 if -uy * away[0] + ux * away[1] > 0 else -1


def _label_anchor(a: Pt, b: Pt, side: Side, gap: float) -> tuple[Pt, str, str]:
    cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    if side == "right":
        return (cx + gap, cy), "left", "center"
    if side == "left":
        return (cx - gap, cy), "right", "center"
    if side == "above":
        return (cx, cy + gap), "center", "bottom"
    return (cx, cy - gap), "center", "top"


class Sheet:
    """One schematic sheet: a schemdraw drawing plus texts, terminals and test-point sites."""

    def __init__(self, circuit: CircuitSpec, theme: Theme) -> None:
        self.circuit = circuit
        self.theme = theme
        self.d = schemdraw.Drawing(show=False)
        self.d.config(unit=2.0, fontsize=FS_LABEL, font=FONT_FAMILY[0], lw=LINE_W,
                      color=theme.ink, margin=0.0)
        self.wires: list[tuple[Pt, Pt]] = []
        self.terminals: list[_Terminal] = []
        self.texts: list[_Text] = []
        self.sites: dict[str, _Site] = {}
        self.drawn: list[str] = []

    # ---- basic drawing -------------------------------------------------------------------
    def add(self, element: Element, role: Role = "ink") -> Element:
        if role != "ink":
            element.color(_colour(self.theme, role))
        self.d.add(element)
        return element

    def wire(self, *pts: Pt) -> None:
        """Orthogonal wire through ``pts``."""
        for a, b in pairwise(pts):
            if a == b:
                continue
            if a[0] != b[0] and a[1] != b[1]:
                raise ValueError(f"wires must be horizontal or vertical: {a} -> {b}")
            self.add(elm.Line().endpoints(a, b))
            self.wires.append((a, b))

    def text(self, xy: Pt, s: str, *, ha: str = "center", va: str = "center",
             size: float = FS_LABEL, weight: str = "normal", role: Role = "ink") -> None:
        self.texts.append(_Text(xy, s, ha, va, size, weight, role))

    def terminal(self, owner: str, node: str, xy: Pt) -> None:
        self.terminals.append(_Terminal(owner, node, xy))

    def ground(self, xy: Pt, role: Role = "ink") -> None:
        self.add(elm.Ground().at(xy).theta(0), role)
        self.terminal("GND", "0", xy)

    def supply(self, xy: Pt, node: str, name: str) -> None:
        """Supply flag with its rail name; it joins every flag and label of that net."""
        self.add(_new(elm.Vdd).at(xy).theta(0))
        self.text((xy[0], xy[1] + 0.55), name, va="bottom", weight="bold")
        self.terminal("FLAG", node, xy)

    def net_label(self, xy: Pt, node: str, name: str, vertical: bool = False) -> None:
        """Rail name written beside the wire through ``xy`` (above it, or right of a vertical
        wire); it joins the flags and labels of the same net."""
        if vertical:
            self.text((xy[0] + 0.28, xy[1]), name, ha="left", va="center", weight="bold")
        else:
            self.text((xy[0], xy[1] + 0.28), name, ha="left", va="bottom", weight="bold")
        self.terminal("LABEL", node, xy)

    def site(self, node: str, xy: Pt, label: Compass) -> None:
        """Candidate test-point marker position for ``node`` (the first registration wins)."""
        self.sites.setdefault(node, _Site(xy, label))

    def heading(self, xy: Pt, s: str) -> None:
        self.text(xy, s.upper(), ha="left", va="bottom", size=FS_STAGE, weight="bold",
                  role="muted")

    def note(self, xy: Pt, s: str, ha: str = "left", va: str = "top") -> None:
        self.text(xy, s, ha=ha, va=va, size=FS_SMALL, role="muted")

    def dashed_box(self, lo: Pt, hi: Pt, caption: str) -> None:
        corners = [lo, (hi[0], lo[1]), hi, (lo[0], hi[1]), lo]
        for a, b in pairwise(corners):
            self.add(elm.Line().endpoints(a, b).linestyle("--").linewidth(0.8), "muted")
        self.text((lo[0] + 0.2, hi[1] - 0.18), caption, ha="left", va="top", size=FS_SMALL,
                  weight="bold", role="muted")

    # ---- components ----------------------------------------------------------------------
    def _component(self, ref: str) -> tuple[ComponentSpec, list[str]]:
        comp = self.circuit.component(ref)
        if ref in self.drawn:
            raise ValueError(f"{ref} drawn twice")
        self.drawn.append(ref)
        return comp, external_nodes(self.circuit, comp)

    def label(self, ref: str, xy: Pt, ha: str = "left", va: str = "center",
              extra: str | None = None) -> None:
        comp = self.circuit.component(ref)
        text = f"{ref}\n{_value_text(comp)}" + (f"\n{extra}" if extra else "")
        self.text(xy, text, ha=ha, va=va)

    def part(self, ref: str, a: Pt, b: Pt, side: Side, *, plus: Literal["a", "b"] = "a",
             gap: float = 0.4) -> None:
        """Two-terminal part from ``a`` (its first external node) to ``b`` (the second).

        Electrolytics get their '+' plate at ``plus``; diodes point from anode ``a`` to
        cathode ``b``. The "REF / VALUE" label goes on ``side``.
        """
        comp, nodes = self._component(ref)
        if len(nodes) != 2:
            raise ValueError(f"{ref}: expected 2 external nodes, got {nodes}")
        start, end = (b, a) if comp.kind == "electrolytic" and plus == "b" else (a, b)
        element: Element2Term
        if comp.kind == "resistor":
            element = _new(elm.Resistor)
        elif comp.kind == "film_cap":
            element = elm.Capacitor()
        elif comp.kind == "electrolytic":
            element = PolarCap(plus_side=_plus_side(start, end, side))
        elif comp.kind == "diode":
            element = _new(elm.Diode)
        elif comp.kind == "zener":
            element = _new(elm.Zener)
            gap += 0.07
        else:
            raise ValueError(f"{ref}: kind {comp.kind} is not a two-terminal part")
        self.add(element.endpoints(start, end))
        self.terminal(ref, nodes[0], a)
        self.terminal(ref, nodes[1], b)
        self.label(ref, *_label_anchor(a, b, side, gap))

    def pot(self, ref: str, top: Pt, bottom: Pt, wiper: Literal["left", "right"],
            function: str) -> Pt:
        """Vertical potentiometer; returns the wiper point. The label goes opposite the wiper."""
        _, nodes = self._component(ref)
        el = _new(elm.Potentiometer).endpoints(top, bottom)
        if (wiper == "left") == (top[1] > bottom[1]):
            el.flip()
        self.add(el)
        tap = _pt(el.absanchors["tap"])
        for node, xy in zip(nodes, (top, bottom, tap), strict=True):
            self.terminal(ref, node, xy)
        mid = ((top[0] + bottom[0]) / 2, (top[1] + bottom[1]) / 2)
        dx, ha = (-0.42, "right") if wiper == "right" else (0.42, "left")
        self.label(ref, (mid[0] + dx, mid[1]), ha=ha, extra=function)
        return tap

    def npn(self, ref: str, base: Pt, theta: float = 0.0) -> dict[str, Pt]:
        """NPN transistor placed by its base lead; returns its collector/base/emitter points."""
        _, nodes = self._component(ref)
        el = self.add(elm.BjtNpn(circle=True).anchor("base").at(base).theta(theta))
        pins = {k: _pt(el.absanchors[k]) for k in ("collector", "base", "emitter")}
        for node, key in zip(nodes, ("collector", "base", "emitter"), strict=True):
            self.terminal(ref, node, pins[key])
        return pins

    def opamp(self, ref: str, non_inv: Pt) -> dict[str, Pt]:
        """Op-amp with the non-inverting input on top, placed by that input."""
        _, nodes = self._component(ref)
        el = self.add(elm.Opamp(flip=True).anchor("in2").at(non_inv).theta(0))
        out = _pt(el.absanchors["out"])
        x_sup = non_inv[0] + 0.72
        pins = {
            "in_p": non_inv,
            "in_n": _pt(el.absanchors["in1"]),
            "out": out,
            # supply pins where the sloped sides cross a third of the body length
            "vpos": (x_sup, out[1] + 1.25 * (1 - 0.72 / 2.165)),
            "vneg": (x_sup, out[1] - 1.25 * (1 - 0.72 / 2.165)),
        }
        for node, key in zip(nodes, ("in_p", "in_n", "out", "vpos", "vneg"), strict=True):
            self.terminal(ref, node, pins[key])
        return pins

    def triode(self, ref: str, center: Pt) -> dict[str, Pt]:
        _, nodes = self._component(ref)
        el = self.add(TriodeSymbol().anchor("center").at(center).theta(0))
        pins = {k: _pt(el.absanchors[k]) for k in ("plate", "grid", "cathode")}
        for node, key in zip(nodes, ("plate", "grid", "cathode"), strict=True):
            self.terminal(ref, node, pins[key])
        return pins

    def pin_number(self, xy: Pt, s: str, ha: str, va: str) -> None:
        self.text(xy, s, ha=ha, va=va, size=FS_SMALL, role="muted")

    # ---- fixtures and infrastructure -----------------------------------------------------
    def fixture(self, name: str, a: Pt, b: Pt, side: Side,
                kind: Literal["r", "sine", "dc"] = "r") -> None:
        """Bench fixture from the netlist, drawn muted and labelled with its netlist value.
        ``a``/``b`` follow the element's node order; for sources ``a`` is the + terminal."""
        spec = self.circuit.netlist.element(name)
        text = f"{name}\n{_fixture_value(spec)}"
        element: Element2Term
        if kind == "r":
            element = _new(elm.Resistor).endpoints(a, b)
        elif kind == "sine":
            element = _new(elm.SourceSin).endpoints(b, a)
        else:
            element = _new(elm.SourceV).endpoints(b, a)
        self.add(element, "muted")
        self.terminal(name, spec.nodes[0], a)
        self.terminal(name, spec.nodes[1], b)
        xy, ha, va = _label_anchor(a, b, side, 0.4 if kind == "r" else 0.66)
        self.text(xy, text, ha=ha, va=va, role="muted")

    def rectifier(self, plus: Pt, minus: Pt, node: str, text: str) -> None:
        """DC source standing in for the transformer and rectifier (behavioural in the netlist)."""
        self.add(_new(elm.SourceV).endpoints(minus, plus))
        self.terminal("rectifier:" + node, node, plus)
        self.terminal("rectifier:" + node, "0", minus)
        xy, ha, va = _label_anchor(plus, minus, "left", 0.66)
        self.text(xy, text, ha=ha, va=va)


def _at(origin: Pt) -> Callable[[float, float], Pt]:
    """Local-grid helper: ``p(x, y)`` is the point (x, y) relative to ``origin``."""
    ox, oy = origin

    def p(x: float, y: float) -> Pt:
        return (round(ox + x, 6), round(oy + y, 6))

    return p


def _off(xy: Pt, dx: float, dy: float) -> Pt:
    return (round(xy[0] + dx, 6), round(xy[1] + dy, 6))


# ---------------------------------------------------------------------------------------------
# Block layouts (local grid; x to the right, y up). Each returns its ports.
# ---------------------------------------------------------------------------------------------
def block_psu_lv(sh: Sheet, origin: Pt) -> Ports:
    """Rectifier out -> C101 -> zener-referenced series pass regulator. Output: vreg."""
    p = _at(origin)
    sh.rectifier(p(0, 0), p(0, -2.5), "vunreg", "rectifier out (≈24 V)")
    sh.ground(p(0, -2.5))
    sh.wire(p(0, 0), p(2, 0))
    sh.site("vunreg", p(1, 0), "n")
    sh.part("C101", p(2, 0), p(2, -2.5), "right")
    sh.ground(p(2, -2.5))
    sh.wire(p(2, 0), p(4.5, 0))
    sh.part("R102", p(4.5, 0), p(4.5, -2.5), "right")
    q = sh.npn("Q101", p(6.75, -0.7517), theta=90)
    sh.label("Q101", _off(q["base"], 0.62, -0.3), ha="left", va="top")
    sh.wire(p(4.5, 0), q["collector"])
    # zener reference and its filter capacitor
    vz = p(4.5, -2.5)
    sh.wire(vz, p(6.75, -2.5), q["base"])
    sh.site("vz", p(5.6, -2.5), "s")
    sh.part("D101", p(4.5, -5.0), vz, "left")
    sh.ground(p(4.5, -5.0))
    sh.part("C102", p(6.75, -2.5), p(6.75, -5.0), "right")
    sh.ground(p(6.75, -5.0))
    # reverse-protection diode across the pass transistor (anode on the regulated side)
    sh.wire(q["emitter"], p(9.5, 0))
    sh.wire(p(5.0, 0), p(5.0, 1.75))
    sh.wire(p(8.5, 0), p(8.5, 1.75))
    sh.part("D102", p(8.5, 1.75), p(5.0, 1.75), "above")
    sh.part("C103", p(9.5, 0), p(9.5, -2.5), "right")
    sh.ground(p(9.5, -2.5))
    sh.wire(p(9.5, 0), p(11.5, 0))
    sh.part("R103", p(11.5, 0), p(11.5, -2.5), "right")
    sh.ground(p(11.5, -2.5))
    sh.wire(p(11.5, 0), p(13.5, 0))
    sh.site("vreg", p(12.5, 0), "n")
    return Ports(inp=p(0, 0), out=p(13.5, 0))


def block_psu_hv(sh: Sheet, origin: Pt) -> Ports:
    """Rectifier out -> C104 reservoir with R104 bleeder -> two RC sections. Output: bplus."""
    p = _at(origin)
    sh.rectifier(p(0, 0), p(0, -2.5), "hv1", "rectifier out (≈282 V)")
    sh.ground(p(0, -2.5))
    sh.wire(p(0, 0), p(2, 0))
    sh.site("hv1", p(1, 0), "n")
    sh.part("C104", p(2, 0), p(2, -2.5), "right")
    sh.ground(p(2, -2.5))
    sh.wire(p(2, 0), p(4, 0))
    sh.part("R104", p(4, 0), p(4, -2.5), "right")
    sh.ground(p(4, -2.5))
    sh.wire(p(4, 0), p(5, 0))
    sh.part("R105", p(5, 0), p(7, 0), "above")
    sh.wire(p(7, 0), p(8.75, 0))
    sh.site("hv2", p(8.15, 0), "n")
    sh.part("C105", p(7.5, 0), p(7.5, -2.5), "right")
    sh.ground(p(7.5, -2.5))
    sh.part("R106", p(8.75, 0), p(10.75, 0), "above")
    sh.wire(p(10.75, 0), p(13.5, 0))
    sh.part("C106", p(11.5, 0), p(11.5, -2.5), "right")
    sh.ground(p(11.5, -2.5))
    sh.site("bplus", p(12.75, 0), "n")
    return Ports(inp=p(0, 0), out=p(13.5, 0))


def block_triode(sh: Sheet, origin: Pt) -> Ports:
    """Common-cathode 12AX7 stage. Input (in_jack) at the origin; B+ enters R203 at the top."""
    p = _at(origin)
    sh.part("C201", p(0, 0), p(2, 0), "above")
    sh.wire(p(2, 0), p(3, 0))
    sh.part("R201", p(3, 0), p(3, -2.5), "left")
    sh.ground(p(3, -2.5))
    sh.part("R202", p(3, 0), p(5, 0), "above")
    v = sh.triode("V201", p(7, 0))
    sh.wire(p(5, 0), v["grid"])
    sh.site("grid", p(5.5, 0), "s")
    sh.label("V201", p(8.3, 0.45), ha="left")
    sh.pin_number(_off(v["plate"], 0.12, 0.08), "1", "left", "bottom")
    sh.pin_number(_off(v["grid"], -0.1, 0.1), "2", "right", "bottom")
    sh.pin_number(_off(v["cathode"], 0.12, -0.08), "3", "left", "top")
    # plate circuit
    plate = p(7, 2.5)
    sh.wire(v["plate"], plate)
    sh.site("plate", p(7, 1.75), "w")
    sh.part("R203", p(7, 4.75), plate, "right")
    sh.wire(plate, p(8.25, 2.5))
    sh.part("C203", p(8.25, 2.5), p(10.25, 2.5), "above")
    # cathode circuit
    cath = p(7, -2.25)
    sh.wire(v["cathode"], cath)
    sh.site("cath", p(7, -1.62), "e")
    sh.part("R204", cath, p(7, -4.5), "left")
    sh.ground(p(7, -4.5))
    sh.wire(cath, p(8.75, -2.25))
    sh.part("C202", p(8.75, -2.25), p(8.75, -4.5), "right")
    sh.ground(p(8.75, -4.5))
    return Ports(inp=p(0, 0), out=p(10.25, 2.5), rails={"bplus": p(7, 4.75)})


def block_tone(sh: Sheet, origin: Pt) -> Ports:
    """Passive Baxandall: treble network on top, bass network below. Input tone_in at origin."""
    p = _at(origin)
    sh.wire(p(0, 0), p(1, 0))
    sh.site("tone_in", p(0.5, 0), "n")
    # treble: C303 -> VR302 -> C304, wiper to the output
    sh.part("C303", p(1, 0), p(3, 0), "above")
    sh.wire(p(3, 0), p(4.5, 0))
    treble = sh.pot("VR302", p(4.5, 0), p(4.5, -2.5), "right", "TREBLE")
    sh.part("C304", p(4.5, -2.5), p(4.5, -4.5), "right")
    sh.ground(p(4.5, -4.5))
    # bass: R301 -> VR301 (C301/C302 across its halves) -> R302, wiper through R303
    sh.wire(p(1, 0), p(1, -6))
    sh.part("R301", p(1, -6), p(3, -6), "above")
    sh.wire(p(3, -6), p(4.5, -6), p(6, -6))
    bass = sh.pot("VR301", p(4.5, -6), p(4.5, -8.5), "right", "BASS")
    sh.part("C301", p(6, -6), p(6, -7.25), "right", gap=0.36)
    sh.wire(bass, p(6.75, -7.25), p(7.5, -7.25))
    sh.site("bass_w", p(5.55, -7.25), "s")
    sh.part("C302", p(6.75, -7.25), p(6.75, -8.5), "right", gap=0.36)
    sh.wire(p(6.75, -8.5), p(4.5, -8.5))
    sh.part("R302", p(4.5, -8.5), p(4.5, -10.5), "right")
    sh.ground(p(4.5, -10.5))
    sh.part("R303", p(7.5, -7.25), p(9.5, -7.25), "above")
    sh.wire(p(9.5, -7.25), p(10.5, -7.25), p(10.5, -1.25))
    sh.wire(treble, p(10.5, -1.25), p(12, -1.25))
    sh.site("tone_out", p(11.25, -1.25), "n")
    return Ports(inp=p(0, 0), out=p(12, -1.25))


def block_opamp(sh: Sheet, origin: Pt) -> Ports:
    """Non-inverting gain-of-11 stage biased at half supply. Input tone_out at the origin."""
    p = _at(origin)
    ox, oy = origin
    sh.part("C401", p(0, 0), p(2, 0), "above")
    sh.wire(p(2, 0), p(3.75, 0))
    # half-supply bias network
    sh.part("R401", p(3.75, 0), p(3.75, -3), "right")
    sh.wire(p(3.75, -3), p(2.25, -3), p(0.75, -3))
    sh.site("vref", p(3.0, -3), "s")
    sh.part("R402", p(0.75, -1.25), p(0.75, -3), "right")
    sh.supply(p(0.75, -1.25), "vreg", "+15 V")
    sh.part("C402", p(2.25, -3), p(2.25, -5.25), "left")
    sh.ground(p(2.25, -5.25))
    sh.part("R403", p(3.75, -3), p(3.75, -5.25), "right")
    sh.ground(p(3.75, -5.25))
    # op-amp with its feedback network below
    u = sh.opamp("U401", p(6, 0))
    sh.wire(p(3.75, 0), u["in_p"])
    sh.site("op_in", p(4.9, 0), "n")
    sh.label("U401", _off(u["vpos"], 0.35, 0.3), ha="left", va="bottom")
    sh.pin_number(_off(u["in_p"], -0.1, 0.08), "3", "right", "bottom")
    sh.pin_number(_off(u["in_n"], -0.1, 0.08), "2", "right", "bottom")
    sh.pin_number(_off(u["out"], 0.12, -0.1), "1", "left", "top")
    fb = p(5.5, -3.0)
    sh.wire(u["in_n"], (fb[0], u["in_n"][1]), fb)
    sh.part("R404", p(9, -3.0), p(6.75, -3.0), "below")
    sh.wire(p(6.75, -3.0), fb)
    sh.site("op_fb", p(6.1, -3.0), "s")
    sh.part("R405", fb, p(5.5, -5.0), "right")
    sh.part("C403", p(5.5, -5.0), p(5.5, -7.0), "right")
    sh.ground(p(5.5, -7.0))
    sh.wire(u["vneg"], p(u["vneg"][0] - ox, -1.75))
    sh.ground(p(u["vneg"][0] - ox, -1.75))
    # supply pin and its decoupling capacitor
    rail = p(u["vpos"][0] - ox, 2.5)
    sh.wire(u["vpos"], rail, p(10, 2.5))
    sh.part("C405", p(10, 2.5), p(10, 0.9), "right")
    sh.ground(p(10, 0.9))
    # output: R406 -> C404 -> drv_in with R407 to ground
    y = u["out"][1] - oy
    sh.wire(u["out"], p(9, y))
    sh.site("op_pin", p(8.55, y), "n")
    sh.wire(p(9, y), p(9, -3.0))
    sh.part("R406", p(9, y), p(11, y), "below")
    sh.part("C404", p(11, y), p(13, y), "above")
    sh.wire(p(13, y), p(15, y))
    sh.part("R407", p(13.75, y), p(13.75, y - 2.25), "right")
    sh.ground(p(13.75, y - 2.25))
    sh.site("drv_in", p(14.4, y), "n")
    return Ports(inp=p(0, 0), out=p(15, y), rails={"vreg": rail})


def block_driver(sh: Sheet, origin: Pt) -> Ports:
    """Common-emitter amplifier Q501 direct-coupled to emitter follower Q502."""
    p = _at(origin)
    oy = origin[1]
    sh.part("C501", p(0, 0), p(2, 0), "above", plus="b")
    sh.wire(p(2, 0), p(3, 0))
    q1 = sh.npn("Q501", p(4.25, 0))
    x1 = q1["collector"][0]  # Q501 collector/emitter column
    sh.wire(p(3, 0), q1["base"])
    sh.site("q1b", p(3.6, 0), "s")
    sh.label("Q501", _off(q1["base"], 1.3, -0.05), ha="left")
    q2 = sh.npn("Q502", (x1 + 1.5, oy + 1.75))
    x2 = q2["collector"][0]  # Q502 collector/emitter column
    sh.label("Q502", _off(q2["base"], 1.3, 0.1), ha="left")
    # supply decoupling and the local rail vcc_d
    rail = oy + 5.5
    sh.wire(p(-2.0, 5.5), p(-1.25, 5.5))
    sh.part("R509", p(-1.25, 5.5), p(0.75, 5.5), "above")
    sh.wire(p(0.75, 5.5), (x2, rail))
    sh.site("vcc_d", p(1.9, 5.5), "n")
    sh.part("C504", p(0.75, 5.5), p(0.75, 3.5), "left")
    sh.ground(p(0.75, 3.5))
    # Q501 base bias
    sh.part("R501", p(3, 5.5), p(3, 3.25), "left")
    sh.wire(p(3, 3.25), p(3, 0))
    sh.part("R502", p(3, 0), p(3, -2.5), "left")
    sh.ground(p(3, -2.5))
    # collector load and the direct coupling to Q502
    q1c = (x1, oy + 1.75)
    sh.part("R505", (x1, rail), (x1, oy + 3.25), "left")
    sh.wire((x1, oy + 3.25), q1c)
    sh.wire(q1["collector"], q1c, q2["base"])
    sh.site("q1c", (x1 + 0.75, oy + 1.75), "n")
    sh.wire(q2["collector"], (x2, rail))
    # Q501 emitter degeneration: R503 unbypassed, R504 bypassed by C502
    e1, e2 = (x1, oy - 1.3), (x1, oy - 3.3)
    sh.wire(q1["emitter"], e1)
    sh.site("q1e", (x1, oy - 1.0), "w")
    sh.part("R503", e1, e2, "right")
    sh.part("R504", e2, (x1, oy - 5.3), "left")
    sh.ground((x1, oy - 5.3))
    sh.wire(e2, (x1 + 1.25, oy - 3.3))
    sh.part("C502", (x1 + 1.25, oy - 3.3), (x1 + 1.25, oy - 5.3), "right")
    sh.ground((x1 + 1.25, oy - 5.3))
    # emitter follower and output network
    q2e = (x2, oy)
    sh.wire(q2["emitter"], q2e, p(8, 0))
    sh.site("q2e", (x2, oy + 0.55), "e")
    sh.part("R506", q2e, (x2, oy - 2.5), "right")
    sh.ground((x2, oy - 2.5))
    sh.part("C503", p(8, 0), p(10, 0), "above")
    sh.part("R507", p(10, 0), p(12, 0), "above")
    sh.wire(p(12, 0), p(14, 0))
    sh.part("R508", p(12.75, 0), p(12.75, -2.5), "right")
    sh.ground(p(12.75, -2.5))
    sh.site("out", p(13.4, 0), "n")
    return Ports(inp=p(0, 0), out=p(14, 0), rails={"vreg": p(-2.0, 5.5)})


# ---------------------------------------------------------------------------------------------
# Fixtures shared by the standalone sheets
# ---------------------------------------------------------------------------------------------
FIXTURE_X = -3.5  # generator / bench-supply column, relative to the block input


def fixture_generator(sh: Sheet, port: Pt, source: str, rsrc: str) -> None:
    """Signal generator with its source resistance, feeding ``port`` from the left."""
    x, y = port[0] + FIXTURE_X, port[1]
    sh.fixture(rsrc, (x, y), port, "above")
    sh.fixture(source, (x, y), (x, y - 2.5), "left", "sine")
    sh.ground((x, y - 2.5), "muted")
    sh.dashed_box((x - 2.2, y - 3.55), (port[0] - 0.75, y + 1.6), "TEST FIXTURE: SIGNAL GENERATOR")


def fixture_load(sh: Sheet, port: Pt, name: str, lead: float = 1.5) -> None:
    """Load resistor from ``port`` to ground, ``lead`` units to the right of the port."""
    x, y = port[0] + lead, port[1]
    sh.wire(port, (x, y))
    sh.fixture(name, (x, y), (x, y - 2.5), "right")
    sh.ground((x, y - 2.5), "muted")
    width = 0.75 + 0.17 * len(name)  # clears the "NAME / value" label
    sh.dashed_box((x - 0.8, y - 3.55), (x + width, y + 1.0), "TEST FIXTURE")


def fixture_supply(sh: Sheet, rail: Pt, port: Pt, name: str, node: str, rail_name: str) -> None:
    """Bench supply stacked above the signal generator, wired over it to the ``rail`` pin."""
    x, top = port[0] + FIXTURE_X, port[1] + 5.5
    sh.wire((x, top), (rail[0], top), rail)
    sh.fixture(name, (x, top), (x, top - 2.5), "left", "dc")
    sh.ground((x, top - 2.5), "muted")
    sh.dashed_box((x - 3.1, top - 3.5), (x + 1.1, top + 1.0), "TEST FIXTURE: BENCH SUPPLY")
    sh.net_label((x + 1.5, top), node, rail_name)


# ---------------------------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------------------------
def layout_psu(sh: Sheet) -> None:
    lv = block_psu_lv(sh, (0.0, 0.0))
    sh.heading((-4.0, 3.4), sh.circuit.stage_name("psu_lv"))
    sh.net_label(_off(lv.out, 0.2, 0), "vreg", "+15 V")
    fixture_load(sh, lv.out, "RLOAD_LV", lead=2.5)
    hv = block_psu_hv(sh, (0.0, -9.0))
    sh.heading((-4.0, -6.9), sh.circuit.stage_name("psu_hv"))
    sh.net_label(_off(hv.out, 0.2, 0), "bplus", "B+ ≈254 V")
    fixture_load(sh, hv.out, "RLOAD_HV", lead=3.0)
    sh.note((-4.0, -13.0), "Mains transformer, rectifier diodes and fuse are not shown; each "
            "rectifier is modelled by its DC output.")


def layout_triode(sh: Sheet) -> None:
    ports = block_triode(sh, (0.0, 0.0))
    fixture_generator(sh, ports.inp, "VIN", "RSRC")
    fixture_supply(sh, ports.rails["bplus"], ports.inp, "VBPLUS_BENCH", "bplus", "B+")
    sh.wire(ports.out, _off(ports.out, 0.75, 0))
    sh.site("tone_in", _off(ports.out, 0.95, 0), "n")
    fixture_load(sh, _off(ports.out, 0.75, 0), "RLOAD_TONE")


def layout_tone(sh: Sheet) -> None:
    ports = block_tone(sh, (0.0, 0.0))
    fixture_generator(sh, ports.inp, "VIN_T", "RSRC_T")
    fixture_load(sh, ports.out, "RLOAD_OP")


def layout_opamp(sh: Sheet) -> None:
    ports = block_opamp(sh, (0.0, 0.0))
    sh.site("tone_out", (0.0, 0.0), "n")
    fixture_generator(sh, ports.inp, "VIN_O", "RSRC_O")
    fixture_supply(sh, ports.rails["vreg"], ports.inp, "VREG_BENCH", "vreg", "+15 V")
    fixture_load(sh, ports.out, "RLOAD_DRV")


def layout_driver(sh: Sheet) -> None:
    ports = block_driver(sh, (0.0, 0.0))
    sh.site("drv_in", (0.0, 0.0), "n")
    fixture_generator(sh, ports.inp, "VIN_D", "RSRC_D")
    fixture_supply(sh, ports.rails["vreg"], ports.inp, "VREG_BENCH", "vreg", "+15 V")
    fixture_load(sh, ports.out, "RLOAD_EXT")


def layout_channel_strip(sh: Sheet) -> None:
    """Signal path left to right; PSU rows along the top with B+ and +15 V wired down."""
    triode = block_triode(sh, (0.0, 0.0))
    fixture_generator(sh, triode.inp, "VIN", "RSRC")
    tone_in = _off(triode.out, 0.75, 0)
    sh.wire(triode.out, tone_in)
    tone = block_tone(sh, tone_in)
    opamp = block_opamp(sh, tone.out)
    driver = block_driver(sh, opamp.out)
    fixture_load(sh, driver.out, "RLOAD_EXT")
    # HV row ends right above the plate load: B+ drops straight down to R203
    y_psu = 10.5
    bplus = triode.rails["bplus"]
    hv = block_psu_hv(sh, (bplus[0] - 13.5, y_psu))
    sh.wire(hv.out, bplus)
    sh.net_label((bplus[0], (y_psu + bplus[1]) / 2), "bplus", "B+ ≈254 V", vertical=True)
    # LV row ends right above U401's supply pin; a bus branches off to the line driver
    vreg, drv = opamp.rails["vreg"], driver.rails["vreg"]
    lv = block_psu_lv(sh, (vreg[0] - 13.5, y_psu))
    sh.wire(lv.out, vreg)
    sh.wire((vreg[0], drv[1]), drv)
    sh.net_label((vreg[0] + 0.9, drv[1]), "vreg", "+15 V")
    # stage headings
    sh.heading((hv.inp[0] - 4.0, y_psu + 3.3), sh.circuit.stage_name("psu_hv"))
    sh.heading((lv.inp[0] - 4.0, y_psu + 3.3), sh.circuit.stage_name("psu_lv"))
    y_cap = -9.6
    for (x, _), stage in ((triode.inp, "triode"), (tone.inp, "tone"), (opamp.inp, "opamp"),
                          (driver.inp, "driver")):
        sh.heading((x, y_cap), sh.circuit.stage_name(stage))
    sh.note((hv.inp[0] - 4.0, y_cap - 0.6), "Mains transformer, rectifier diodes, fuse and "
            "heater wiring are not shown; each rectifier is modelled by its DC output.")


LAYOUTS: dict[str, Callable[[Sheet], None]] = {
    "psu": layout_psu,
    "triode": layout_triode,
    "tone": layout_tone,
    "opamp": layout_opamp,
    "driver": layout_driver,
    "channel_strip": layout_channel_strip,
}


# ---------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------
Key = tuple[float, float]


def _key(xy: Pt) -> Key:
    return (round(xy[0], 4) + 0.0, round(xy[1], 4) + 0.0)


def _inside(p: Key, a: Key, b: Key) -> bool:
    """True if ``p`` lies strictly inside the axis-aligned segment a-b."""
    if a[0] == b[0] == p[0]:
        return min(a[1], b[1]) < p[1] < max(a[1], b[1])
    if a[1] == b[1] == p[1]:
        return min(a[0], b[0]) < p[0] < max(a[0], b[0])
    return False


class _Union:
    def __init__(self) -> None:
        self.parent: dict[Key, Key] = {}

    def find(self, k: Key) -> Key:
        self.parent.setdefault(k, k)
        while self.parent[k] != k:
            self.parent[k] = self.parent[self.parent[k]]
            k = self.parent[k]
        return k

    def union(self, a: Key, b: Key) -> None:
        self.parent[self.find(a)] = self.find(b)


def check_topology(sh: Sheet) -> tuple[list[Key], list[str]]:
    """Compare the drawn wiring with the netlist; return (junction dots, errors)."""
    errors: list[str] = []
    segs = [(_key(a), _key(b)) for a, b in sh.wires]
    terms = [(t, _key(t.xy)) for t in sh.terminals if t.owner != "LABEL"]
    labels = [(t, _key(t.xy)) for t in sh.terminals if t.owner == "LABEL"]
    points = {k for s in segs for k in s} | {k for _, k in terms}
    nets = _Union()
    degree: dict[Key, int] = defaultdict(int)
    for a, b in segs:
        nets.union(a, b)
        degree[a] += 1
        degree[b] += 1
    for _, k in terms:
        nets.find(k)
        degree[k] += 1
    for pnt in points:  # T-junctions: a point on the inside of a wire joins it
        for a, b in segs:
            if _inside(pnt, a, b):
                nets.union(pnt, a)
                degree[pnt] += 2
    for i, (a, b) in enumerate(segs):  # crossings are legal but unwanted
        for c, e in segs[i + 1:]:
            x = (a[0], c[1]) if a[0] == b[0] else (c[0], a[1])
            if _inside(x, a, b) and _inside(x, c, e):
                errors.append(f"wires cross at {x}")
    for t, k in labels:  # a net label names the wire it is written on
        seg = next((s for s in segs if k in s or _inside(k, *s)), None)
        if seg is None:
            errors.append(f"net label {t.node!r} at {k} is not on a wire")
        else:
            nets.union(k, seg[0])
    first: dict[str, Key] = {}
    for t, k in terms + labels:  # ground symbols, supply flags and labels join their net
        if t.owner in ("GND", "FLAG", "LABEL"):
            nets.union(k, first.setdefault(t.node, k))
    term_keys = {k for _, k in terms}
    for k in {k for s in segs for k in s} - term_keys:
        if degree[k] < 2:
            errors.append(f"dangling wire end at {k}")
    nodes_of: dict[Key, set[str]] = defaultdict(set)
    owners: dict[Key, list[str]] = defaultdict(list)
    pieces: dict[str, set[Key]] = defaultdict(set)
    for t, k in terms + labels:
        root = nets.find(k)
        nodes_of[root].add(t.node)
        pieces[t.node].add(root)
        if t.owner != "LABEL":
            owners[root].append(t.owner)
    for root, nodes in nodes_of.items():
        if len(nodes) > 1:
            errors.append(f"short between nodes {sorted(nodes)} ({sorted(set(owners[root]))})")
        elif len(owners[root]) < 2:
            errors.append(f"unconnected terminal on node {next(iter(nodes))}: {owners[root]}")
    for node, roots in pieces.items():
        if len(roots) > 1:
            errors.append(f"node {node!r} is drawn as {len(roots)} separate pieces")
    if missing := sorted({c.ref for c in sh.circuit.components} - set(sh.drawn)):
        errors.append(f"components not drawn: {missing}")
    if lost := sorted(set(sh.circuit.fixtures) - {t.owner for t in sh.terminals}):
        errors.append(f"fixtures not drawn: {lost}")
    for tp in sh.circuit.test_points:  # each marker sits on its own node
        site = sh.sites.get(tp.node)
        if site is None:
            errors.append(f"{tp.id}: no marker position for node {tp.node!r}")
            continue
        k = _key(site.xy)
        on = k if k in term_keys else next(
            (a for a, b in segs if k in (a, b) or _inside(k, a, b)), None)
        if on is None or nodes_of.get(nets.find(on)) != {tp.node}:
            errors.append(f"{tp.id}: marker at {k} is not on node {tp.node!r}")
    dots = sorted(k for k in points if degree[k] >= 3)
    return dots, errors


Seg = tuple[float, float, float, float]


def _stroke_segments(ax: Any) -> list[Seg]:
    """Every stroked outline on the axes as display-space segments (markers excluded)."""
    out: list[Seg] = []

    def add(verts: Any) -> None:
        for (x0, y0), (x1, y1) in pairwise(verts):
            if all(math.isfinite(v) for v in (x0, y0, x1, y1)):
                out.append((x0, y0, x1, y1))

    for line in ax.lines:
        if line.get_marker() in (None, "None", "", " "):
            add(line.get_transform().transform(line.get_path().vertices))
    for patch in ax.patches:
        for poly in patch.get_path().to_polygons(patch.get_transform(), closed_only=False):
            add(poly)
    return out


def _hits(seg: Seg, box: Bbox) -> bool:
    """Liang-Barsky test: does the segment touch the box?"""
    x0, y0, x1, y1 = seg
    t0, t1 = 0.0, 1.0
    dx, dy = x1 - x0, y1 - y0
    for p, q in ((-dx, x0 - box.x0), (dx, box.x1 - x0), (-dy, y0 - box.y0), (dy, box.y1 - y0)):
        if p == 0:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


def check_collisions(fig: Figure, ax: Any) -> list[str]:
    """Labels must not touch each other, any stroke, or a test-point marker."""
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    boxes = [(t.get_text().replace("\n", " / "), t.get_window_extent(renderer).padded(-0.3))
             for t in ax.texts if t.get_text().strip()]
    issues: list[str] = []
    for i, (s1, b1) in enumerate(boxes):
        issues += [f"label {s1!r} overlaps label {s2!r}" for s2, b2 in boxes[i + 1:]
                   if b1.overlaps(b2)]
    segs = _stroke_segments(ax)
    arr = np.array(segs).reshape(-1, 4)
    lo_x, hi_x = np.minimum(arr[:, 0], arr[:, 2]), np.maximum(arr[:, 0], arr[:, 2])
    lo_y, hi_y = np.minimum(arr[:, 1], arr[:, 3]), np.maximum(arr[:, 1], arr[:, 3])
    for s, box in boxes:  # bounding-box prefilter, then the exact test
        near = np.flatnonzero((hi_x >= box.x0) & (lo_x <= box.x1) & (hi_y >= box.y0)
                              & (lo_y <= box.y1))
        if any(_hits(segs[i], box) for i in near):
            issues.append(f"label {s!r} touches a line")
    for line in ax.lines:
        if line.get_marker() != "o" or (line.get_gid() or "").endswith("-dot"):
            continue
        (cx, cy), = line.get_transform().transform(line.get_xydata())
        rad = line.get_markersize() / 2 * fig.dpi / 72 + 1.0
        for s, box in boxes:
            nx, ny = min(max(cx, box.x0), box.x1), min(max(cy, box.y0), box.y1)
            if math.hypot(nx - cx, ny - cy) < rad:
                issues.append(f"label {s!r} overlaps marker {line.get_gid() or 'legend'}")
    return issues


# ---------------------------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------------------------
class SchematicError(RuntimeError):
    """A layout failed one of the render checks."""


_COMPASS: dict[str, tuple[float, float, str, str]] = {
    "n": (0.0, 0.25, "center", "bottom"),
    "s": (0.0, -0.25, "center", "top"),
    "e": (0.25, 0.0, "left", "center"),
    "w": (-0.25, 0.0, "right", "center"),
    "ne": (0.19, 0.19, "left", "bottom"),
    "nw": (-0.19, 0.19, "right", "bottom"),
    "se": (0.19, -0.19, "left", "top"),
    "sw": (-0.19, -0.19, "right", "top"),
}


@dataclass
class Rendered:
    fig: Figure
    tp_data: dict[str, Pt]  # marker positions, drawing units
    issues: list[str]
    extent: tuple[float, float, float, float]  # xmin, ymin, xmax, ymax (drawing units)


def _marker(ax: Any, xy: Pt, hv: bool, gid: str | None) -> None:
    colour = HV_COLOR if hv else LV_COLOR
    ring = Line2D([xy[0]], [xy[1]], marker="o", markersize=TP_RING, markeredgewidth=1.4,
                  markeredgecolor=colour, markerfacecolor=(*matplotlib.colors.to_rgb(colour), 0.16),
                  linestyle="none", zorder=7, clip_on=False)
    dot = Line2D([xy[0]], [xy[1]], marker="o", markersize=TP_DOT, markeredgewidth=0,
                 markerfacecolor=colour, linestyle="none", zorder=7.5, clip_on=False)
    if gid:
        ring.set_gid(gid)
        dot.set_gid(gid + "-dot")
    ax.add_line(ring)
    ax.add_line(dot)


def _content_box(fig: Figure, ax: Any) -> Bbox:
    """Union of every artist's extent, in drawing units."""
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    boxes = [a.get_window_extent(renderer) for a in (*ax.lines, *ax.patches, *ax.texts)]
    return Bbox.union(boxes).transformed(ax.transData.inverted())


def _set_extent(fig: Figure, ax: Any, extent: tuple[float, float, float, float]) -> None:
    x0, y0, x1, y1 = extent
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    fig.set_size_inches((x1 - x0) * IN_PER_UNIT, (y1 - y0) * IN_PER_UNIT)


def _draw_text(ax: Any, theme: Theme, t: _Text) -> None:
    """Draw a label one line at a time: each SVG <text> then keeps its own text-anchor, so the
    alignment survives a browser substituting another font for Inter."""
    lines = t.s.split("\n")
    pitch = t.size * LINE_PITCH / (72.0 * IN_PER_UNIT)
    for i, line in enumerate(lines):
        if t.va == "top":
            dy = -i * pitch
        elif t.va == "bottom":
            dy = (len(lines) - 1 - i) * pitch
        else:
            dy = ((len(lines) - 1) / 2 - i) * pitch
        ax.text(t.xy[0], t.xy[1] + dy, line, ha=t.ha, va=t.va, fontsize=t.size,
                fontweight=t.weight, color=_colour(theme, t.role), family=FONT_FAMILY,
                zorder=6, clip_on=False)


def _title_block(ax: Any, theme: Theme, circuit: CircuitSpec, top_left: Pt) -> None:
    x, y = top_left
    _draw_text(ax, theme, _Text((x, y + 1.55), circuit.name, "left", "bottom", FS_TITLE, "bold"))
    legend = [(False, "test point"), (True, "high-voltage test point (above 50 V DC)")]
    for i, (hv, text) in enumerate(legend):
        lx = x + 0.15 + 2.3 * i
        _marker(ax, (lx, y + 0.95), hv, None)
        _draw_text(ax, theme, _Text((lx + 0.3, y + 0.95), text, "left", "center", FS_SMALL,
                                    role="muted"))


def build(circuit: CircuitSpec, theme: Theme, check_labels: bool = True) -> Rendered:
    """Lay out and draw one circuit; collect every check failure in ``issues``."""
    if circuit.id not in LAYOUTS:
        raise SchematicError(f"no schematic layout for circuit {circuit.id!r}")
    sh = Sheet(circuit, theme)
    LAYOUTS[circuit.id](sh)
    dots, issues = check_topology(sh)
    for k in dots:
        sh.add(elm.Dot(radius=0.085).at(k))
    fig = Figure()
    FigureCanvasAgg(fig)
    fig.set_dpi(72)  # display units == SVG user units
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_axis_off()
    bb = sh.d.get_bbox()
    _set_extent(fig, ax, (bb.xmin - 5, bb.ymin - 5, bb.xmax + 5, bb.ymax + 5))
    sh.d.draw(show=False, canvas=ax)
    for t in sh.texts:
        _draw_text(ax, theme, t)
    tp_data: dict[str, Pt] = {}
    for tp in circuit.test_points:
        site = sh.sites.get(tp.node)
        if site is None:
            continue
        tp_data[tp.id] = site.xy
        _marker(ax, site.xy, tp.hv, f"tp-{tp.id}")
        dx, dy, ha, va = _COMPASS[site.label]
        _draw_text(ax, theme, _Text((site.xy[0] + dx, site.xy[1] + dy), tp.id, ha, va, FS_TP,
                                    "bold", "tp_hv" if tp.hv else "tp_lv"))
    content = _content_box(fig, ax)
    _title_block(ax, theme, circuit, (content.x0, content.y1))
    full = _content_box(fig, ax)
    # whole-unit sheet size: integer SVG points and integer PNG pixels at PNG_DPI
    step = SIZE_STEP_PT / (72.0 * IN_PER_UNIT)
    w = math.ceil((full.width + 2 * MARGIN) / step - 1e-9) * step
    h = math.ceil((full.height + 2 * MARGIN) / step - 1e-9) * step
    x0, y1 = full.x0 - MARGIN, full.y1 + MARGIN
    extent = (x0, y1 - h, x0 + w, y1)
    _set_extent(fig, ax, extent)
    if check_labels:
        issues += check_collisions(fig, ax)
    return Rendered(fig, tp_data, issues, extent)


def _svg_text(r: Rendered, theme: Theme, title: str, salt: str) -> str:
    """SVG with real <text>, a font fallback stack and ids unique to this file."""
    buf = io.StringIO()
    with matplotlib.rc_context({"svg.fonttype": "none", "svg.hashsalt": salt}):
        r.fig.savefig(buf, format="svg", metadata={"Date": None},
                      facecolor=theme.background or "none", transparent=theme.background is None)
    svg = buf.getvalue()
    svg = re.sub(r"font-family: '[^;\"]*'", f"font-family: {SVG_FONT_STACK}", svg)
    head = svg.index(">", svg.index("<svg")) + 1
    return svg[:head] + f"\n <title>{title}</title>" + svg[head:]


_SVG_NS = "{http://www.w3.org/2000/svg}"


def svg_geometry(svg: str) -> tuple[list[float], dict[str, Pt]]:
    """ViewBox and test-point marker centres as written in an SVG from this module."""
    root = ET.fromstring(svg)
    view_box = [float(v) for v in root.attrib["viewBox"].split()]
    markers: dict[str, Pt] = {}
    for g in root.iter(f"{_SVG_NS}g"):
        gid = g.attrib.get("id", "")
        if gid.startswith("tp-") and not gid.endswith("-dot"):
            use = next(g.iter(f"{_SVG_NS}use"))
            markers[gid[3:]] = (float(use.attrib["x"]), float(use.attrib["y"]))
    return view_box, markers


def render(circuit_id: str, out_dir: Path | None = None) -> dict[str, Any]:
    """Render one circuit's schematic files and test-point map; return a summary."""
    circuit = get_circuit(circuit_id)
    folder = out_dir or CIRCUITS_DIR / circuit_id
    folder.mkdir(parents=True, exist_ok=True)
    title = f"{circuit.name} - schematic"
    light = build(circuit, LIGHT)
    if light.issues:
        raise SchematicError(f"{circuit_id}: " + "; ".join(light.issues))
    dark = build(circuit, DARK, check_labels=False)  # same geometry; compared below
    svg_light = _svg_text(light, LIGHT, title, f"{circuit_id}-light")
    svg_dark = _svg_text(dark, DARK, title, f"{circuit_id}-dark")
    view_box, markers = svg_geometry(svg_light)
    if svg_geometry(svg_dark) != (view_box, markers):
        raise SchematicError(f"{circuit_id}: light and dark SVG geometry differ")
    x0, _, _, y1 = light.extent
    scale = IN_PER_UNIT * 72.0
    test_points: dict[str, dict[str, Any]] = {}
    for tp in circuit.test_points:
        x, y = light.tp_data[tp.id]
        sx, sy = (x - x0) * scale, (y1 - y) * scale
        mx, my = markers[tp.id]
        if abs(mx - sx) > 0.05 or abs(my - sy) > 0.05:
            raise SchematicError(f"{circuit_id}: {tp.id} marker at {(mx, my)}, expected "
                                 f"{(sx, sy)}")
        test_points[tp.id] = {"x": round(mx, 2), "y": round(my, 2), "hv": tp.hv, "node": tp.node}
    paths = {
        "svg": folder / f"{circuit_id}_schematic.svg",
        "png": folder / f"{circuit_id}_schematic.png",
        "svg_dark": folder / f"{circuit_id}_schematic_dark.svg",
        "json": folder / f"{circuit_id}_testpoints.json",
    }
    paths["svg"].write_text(svg_light, encoding="utf-8")
    paths["svg_dark"].write_text(svg_dark, encoding="utf-8")
    light.fig.savefig(paths["png"], dpi=PNG_DPI, facecolor=LIGHT.background,
                      metadata={"Software": None})
    box = [int(v) if float(v).is_integer() else v for v in view_box]
    tp_map = {"width": box[2], "height": box[3], "viewBox": box, "test_points": test_points}
    paths["json"].write_text(json.dumps(tp_map, indent=2) + "\n", encoding="utf-8")
    return {
        "id": circuit_id,
        "files": {k: str(v) for k, v in paths.items()},
        "svg_size": (view_box[2], view_box[3]),
        "png_size": png_size(paths["png"]),
        "test_points": test_points,
    }


def png_size(path: Path) -> tuple[int, int]:
    """Pixel size from a PNG's IHDR chunk."""
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def render_all(out_dir: Path | None = None) -> list[dict[str, Any]]:
    """Render every circuit in the library."""
    return [render(cid, out_dir / cid if out_dir else None) for cid in CIRCUIT_IDS]


def main() -> None:
    for summary in render_all():
        w, h = summary["png_size"]
        print(f"{summary['id']:>14}: {len(summary['test_points'])} test points, "
              f"PNG {w}x{h} px -> {Path(summary['files']['svg']).parent}")


if __name__ == "__main__":
    main()
