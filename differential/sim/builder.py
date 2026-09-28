"""Build ngspice decks for one (circuit, hypothesis) and a batch of Monte Carlo draws.

Each deck contains the fault-specific netlist once and a ``.control`` script that,
for every draw, applies the draw with ``alter``/``altermod``, runs the operating
point, the AC analyses (1 kHz, 20 Hz, 20 kHz), the 120 Hz hum analysis and the
1 kHz transient + Fourier analysis for THD, and echoes tagged result lines:

    @@B <draw> <analysis>          analysis begins
    @@V <draw> <analysis> k=v ...  values (observable index = value)
    @@P <draw> <analysis> <plot>   active plot after the analysis (guards against
                                   reading a stale plot when an analysis fails)
    @@E <draw> <analysis>          analysis ends (Fourier output sits between B and E)
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from differential.circuits.library import DEVICE_LIBRARY
from differential.circuits.model import CircuitSpec
from differential.circuits.netlist import Element
from differential.circuits.units import spice_number
from differential.sim.draws import Draw, device_model_name, structural_edits
from differential.sim.faults import Fault
from differential.sim.observables import ObservableSpec, spice_observables

AC_FREQS = {"ac": 1000.0, "ac20": 20.0, "ac20k": 20000.0}
HUM_FREQ = 120.0
# Transient for THD: 7 ms at 1 kHz, 2 ms saved; Fourier uses the last period.
TRAN_CMD = "tran 10u 7m 5m 10u"

RETRY_OPTIONS = [
    "",
    ".options itl1=500 itl2=200 gminsteps=50 srcsteps=50",
    ".options itl1=1000 itl2=500 itl4=100 gminsteps=100 srcsteps=200 reltol=0.003 "
    "vntol=1e-5 abstol=1e-10 method=gear rshunt=1e10",
]
MAX_ECHO_ITEMS = 12


@lru_cache(maxsize=1)
def model_cards() -> dict[str, tuple[str, str]]:
    """Parse ``.model`` cards from the device library: name -> (type, params)."""
    text = DEVICE_LIBRARY.read_text()
    joined: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("+") and joined:
            joined[-1] += " " + s[1:].strip()
        else:
            joined.append(s)
    cards: dict[str, tuple[str, str]] = {}
    for line in joined:
        m = re.match(r"^\.model\s+(\S+)\s+(\w+)\s*\((.*)\)\s*$", line, flags=re.I)
        if m:
            cards[m.group(1).upper()] = (m.group(2), m.group(3))
    return cards


@dataclass(frozen=True)
class Deck:
    text: str
    observables: tuple[ObservableSpec, ...]
    draw_ids: tuple[int, ...]


def _as_list(fault: Fault | Sequence[Fault]) -> list[Fault]:
    return [fault] if isinstance(fault, Fault) else list(fault)


def fault_netlist(circuit: CircuitSpec, fault: Fault | Sequence[Fault], retry: int = 0) -> str:
    """Render the netlist with per-device model clones and the faults' structural edits."""
    faults = _as_list(fault)
    net = circuit.netlist
    cards = model_cards()
    elements: list[Element] = []
    clone_lines: list[str] = []
    per_device = {c.main_element: c for c in circuit.components if c.kind in ("bjt", "zener")}
    edits = [e for f in faults for e in structural_edits(circuit, f)]
    removed = {e.remove_element for e in edits if e.remove_element}
    rewires = {e.rewire[0]: e.rewire for e in edits if e.rewire}
    sig = circuit.signal
    for el in net.elements:
        if el.name in removed:
            continue
        new = el
        if el.name in per_device:
            comp = per_device[el.name]
            assert comp.model is not None
            clone = device_model_name(comp)
            mtype, params = cards[comp.model.upper()]
            clone_lines.append(f".model {clone} {mtype}({params})")
            new = new.with_value(clone)
        if el.name in rewires:
            _, idx, node = rewires[el.name]
            nodes = list(new.nodes)
            nodes[idx] = node
            new = new.with_nodes(tuple(nodes))
        if sig is not None and el.name == sig.source:
            amp = sig.tran_amplitude or 0.0
            new = new.with_value(
                f"DC 0 AC 1 SIN(0 {spice_number(amp)} {spice_number(sig.frequency)})"
            )
        elements.append(new)
    for e in edits:
        elements.append(Element(e.add_name, (e.node_a, e.node_b), spice_number(e.default_value)))
    lines = [f"* {circuit.id} / {'+'.join(f.id for f in faults)}", f".include {DEVICE_LIBRARY}", ".options noinit noacct"]
    if RETRY_OPTIONS[retry]:
        lines.append(RETRY_OPTIONS[retry])
    lines += clone_lines
    lines += [el.line() for el in elements]
    return "\n".join(lines) + "\n"


def _echo_values(tag: str, draw_id: int, items: list[tuple[int, str]]) -> list[str]:
    out = []
    for start in range(0, len(items), MAX_ECHO_ITEMS):
        chunk = items[start : start + MAX_ECHO_ITEMS]
        body = " ".join(f"{i}=$&{vec}" for i, vec in chunk)
        out.append(f'echo "@@V {draw_id} {tag} {body}"')
    return out


def control_lines(
    circuit: CircuitSpec, draws: list[tuple[int, Draw]], with_thd: bool = True
) -> tuple[list[str], tuple[ObservableSpec, ...]]:
    obs = tuple(spice_observables(circuit))
    idx_by_kind: dict[str, list[tuple[int, ObservableSpec]]] = {}
    for i, o in enumerate(obs):
        idx_by_kind.setdefault(o.kind, []).append((i, o))
    sig = circuit.signal
    hum = circuit.hum
    lines = [".control", "set noaskquit"]
    for draw_id, d in draws:
        for name, value in sorted(d.alters.items()):
            lines.append(f"alter {name} = {spice_number(value)}")
        for (model, param), value in sorted(d.altermods.items()):
            lines.append(f"altermod {model} {param} = {spice_number(value)}")
        # --- DC operating point
        lines.append(f'echo "@@B {draw_id} op"')
        lines.append("op")
        lines.append(f'echo "@@P {draw_id} op $curplot"')
        items = []
        for i, o in idx_by_kind.get("dc", []):
            vec = f"xq{i}"
            lines.append(f"let {vec} = v({o.node})")
            items.append((i, vec))
        lines += _echo_values("op", draw_id, items)
        lines.append(f'echo "@@E {draw_id} op"')
        # --- AC gains from the signal generator
        if sig is not None:
            for kind, freq in AC_FREQS.items():
                entries = idx_by_kind.get(kind, [])
                if not entries:
                    continue
                f = spice_number(freq)
                lines.append(f'echo "@@B {draw_id} {kind}"')
                lines.append(f"ac lin 1 {f} {f}")
                lines.append(f'echo "@@P {draw_id} {kind} $curplot"')
                items = []
                for i, o in entries:
                    vec = f"xq{i}"
                    lines.append(f"let {vec} = mag(v({o.node}))")
                    items.append((i, vec))
                lines += _echo_values(kind, draw_id, items)
                lines.append(f'echo "@@E {draw_id} {kind}"')
        # --- 120 Hz hum (ripple-current injection, signal off)
        if hum is not None and idx_by_kind.get("hum"):
            if sig is not None:
                lines.append(f"alter @{sig.source}[acmag] = 0")
            lines.append(f"alter @{hum.reference_source}[acmag] = 1")
            lines.append(f'echo "@@B {draw_id} hum"')
            lines.append(f"ac lin 1 {spice_number(HUM_FREQ)} {spice_number(HUM_FREQ)}")
            lines.append(f'echo "@@P {draw_id} hum $curplot"')
            items = []
            for i, o in idx_by_kind["hum"]:
                vec = f"xq{i}"
                lines.append(f"let {vec} = mag(v({o.node}))")
                items.append((i, vec))
            lines += _echo_values("hum", draw_id, items)
            lines.append(f'echo "@@E {draw_id} hum"')
            lines.append(f"alter @{hum.reference_source}[acmag] = 0")
            if sig is not None:
                lines.append(f"alter @{sig.source}[acmag] = 1")
        # --- THD via transient + Fourier
        if with_thd and sig is not None and idx_by_kind.get("thd"):
            i, o = idx_by_kind["thd"][0]
            lines.append(f'echo "@@B {draw_id} thd {i}"')
            lines.append(TRAN_CMD)
            lines.append(f'echo "@@P {draw_id} thd $curplot"')
            lines.append(f"fourier {spice_number(sig.frequency)} v({o.node})")
            lines.append(f'echo "@@E {draw_id} thd"')
        lines.append("destroy all")
    lines += [".endc", ".end"]
    return lines, obs


def build_deck(
    circuit: CircuitSpec,
    fault: Fault | Sequence[Fault],
    draws: list[tuple[int, Draw]],
    retry: int = 0,
    with_thd: bool = True,
) -> Deck:
    net = fault_netlist(circuit, fault, retry=retry)
    ctl, obs = control_lines(circuit, draws, with_thd=with_thd)
    return Deck(text=net + "\n".join(ctl) + "\n", observables=obs, draw_ids=tuple(i for i, _ in draws))
