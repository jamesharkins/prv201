#!/usr/bin/env python3
"""Expected readings for the Differential fault board (hardware/fault_board/).

Regenerates ``expected_readings.md`` and ``expected_readings.json`` from the
project's own simulation layer, so every number a technician compares against
comes from the same netlist (circuits/driver/driver.cir), device models
(circuits/lib/devices.lib), tolerance draws and fault models that the diagnosis
engine is trained on.

Run from the repository root with the project venv active::

    source .venv/bin/activate
    python hardware/fault_board/make_expected.py          # about 30 s on 4 cores

What it computes (ngspice through ``differential.sim``):

* healthy board and each of the ten jumper faults: nominal readings (every part
  at its netlist value, the fault part as fitted on the board) and the 5th-95th
  percentile over Monte Carlo tolerance draws (``make_draw``, seed split "demo");
* the engine's own catalog draws for the same faults, to show that each board
  realisation sits inside what the engine expects;
* look-alikes: catalog hypotheses that no single reading separates from a fault;
* a board-level netlist (every jumper header modelled, fault parts fitted),
  checked against the catalog fault models for every jumper position;
* a safety screen: supply current, dissipation, transistor stress and capacitor
  polarity for every board state, every pair of shunts on F, and the whole catalog
  at worst-case severity;
* settling times after power-up (with the bench supply's 50 mA current limit)
  and after moving a jumper shunt, with the peak current through each header;
* the sensitivity of every reading to the bench-supply setting;
* the gain error at the bench test level versus the small-signal model.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import itertools
import json
import math
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from differential.circuits.library import DEVICE_LIBRARY, get_circuit  # noqa: E402
from differential.circuits.model import CircuitSpec  # noqa: E402
from differential.circuits.netlist import Element, Netlist, parse_netlist  # noqa: E402
from differential.circuits.units import parse_value, spice_number  # noqa: E402
from differential.config import n_workers  # noqa: E402
from differential.sim import draws as draws_module  # noqa: E402
from differential.sim import measurement as meas  # noqa: E402
from differential.sim.builder import control_lines, fault_netlist  # noqa: E402
from differential.sim.draws import (  # noqa: E402
    MODEL_BF,
    R_OPEN,
    Draw,
    apply_fault,
    device_model_name,
)
from differential.sim.faults import (  # noqa: E402
    HEALTHY_FAULT,
    MODE_LABELS,
    fault_catalog,
    parse_fault_id,
)
from differential.sim.montecarlo import (  # noqa: E402
    BASE_SEED,
    SPLIT_INDEX,
    circuit_index,
    make_draw,
)
from differential.sim.observables import ObservableSpec, spice_observables  # noqa: E402
from differential.sim.runner import (  # noqa: E402
    HARM_RE,
    DrawResult,
    ngspice_version,
    parse_output,
    simulate_draws,
)

# ---------------------------------------------------------------------------
# Board definition
# ---------------------------------------------------------------------------

CIRCUIT_ID = "driver"
SPLIT = "demo"  # seed stream; SimulatedBench uses hypothesis indices >= 200000 here
BOARD_SEED_WORD = 1  # extra SeedSequence word for the tolerances of the fitted fault parts
DEFAULT_DRAWS = 50

GAIN_TEST_VPK = 0.10  # generator level for gain readings: 0.20 Vpp at GEN
HEADER_CONTACT_OHMS = 0.05  # assumed jumper-shunt contact resistance (board-wiring check)
SUPPLY_LIMIT_A = 0.050  # bench-supply current limit
SUPPLY_STEP_V = 0.10  # supply-sensitivity step
TP17_ZERO_V = 0.010  # DC readings below these magnitudes are entered as 0 (see section 1)
TP22_ZERO_V = 0.100  # ADR-012 "DC at output" threshold

# onsemi 2N3903/D, maximum ratings table. VCEO and IC are in the project's verified
# claims (docs/research/sources_technical.yaml, onsemi_2n3903_2n3904_datasheet);
# PD is verified there for the TO-92 2N3906; VEBO is read from the same 2N3904 table.
BJT_VCEO_V = 40.0
BJT_IC_A = 0.200
BJT_PD_W = 0.625
BJT_VEBO_V = 6.0
REVERSE_POLARITY_FLAG_V = -0.3  # flag any electrolytic reverse-biased beyond this

# Fault parts fitted on the board (see BOM.csv / faults.md)
RF3_OHMS = 100e3  # JF3: Q501 collector-base leakage
RF4_OHMS = 2.2e3  # JF4: second R503 in series (drift x2)
CF5_FARADS = 10e-6  # JF5: degraded C502 (cap loss 90 %)
RF8_OHMS = 22.0  # JF8: Q502 collector-emitter "short" (series safety resistor)
RF10_OHMS = 470.0  # JF10: R509 drifted x10
FAULT_PART_TOL = 0.01  # 1 % metal film
CF5_TOL = 0.20
FAULT_PART_RATING_W = 0.25
FIXTURE_RATING_W = 0.25
BOARD_RATING_OVERRIDE_W = {"R506": 0.6}  # fitted as a 0.6 W part (same 1 kohm 1 % value)
CF5_RATING_V = 25.0


@dataclass(frozen=True)
class BoardFault:
    header: str
    fault_id: str
    fitted: str  # what the F position does, in words


BOARD_FAULTS: tuple[BoardFault, ...] = (
    BoardFault("JF1", "C501:open", "C501 negative lead disconnected from TP17"),
    BoardFault("JF2", "Q501:be_open", "Q501 base lead disconnected from TP18"),
    BoardFault("JF3", "Q501:cb_leak",
               "RF3 100 kΩ connected from Q501 collector (TP20) to base (TP18)"),
    BoardFault("JF4", "R503:drift_x2", "RF4 2.2 kΩ inserted in series with R503 (4.4 kΩ)"),
    BoardFault("JF5", "C502:cap_loss_90", "C502 100 µF swapped for CF5 10 µF"),
    BoardFault("JF6", "R505:open", "R505 lower lead disconnected from TP20"),
    BoardFault("JF7", "Q502:be_open", "Q502 base lead disconnected from TP20"),
    BoardFault("JF8", "Q502:ce_short",
               "RF8 22 Ω connected from Q502 collector (TP23) to emitter (TP21)"),
    BoardFault("JF9", "C503:open", "C503 negative lead disconnected from R507"),
    BoardFault("JF10", "R509:drift_x10", "R509 47 Ω swapped for RF10 470 Ω"),
)
HEADERS = tuple(bf.header for bf in BOARD_FAULTS)

# Header wiring. Pin 2 (centre) is always the circuit node the model names; pin 1
# is the healthy connection (H), pin 3 the fault connection (F); unused pins are NC.
HEADER_COMMON = {
    "JF1": "drv_in", "JF2": "q1b", "JF3": "q1b", "JF4": "q1e2", "JF5": "q1e2",
    "JF6": "q1c", "JF7": "q1c", "JF8": "q2e", "JF9": "out_c", "JF10": "vcc_d",
}
# Netlist element -> (terminal index, pin node): the element reaches pin 2 via pin 1.
PIN1_REWIRES = {
    "C501": (0, "jf1_1"),
    "Q501": (1, "jf2_1"),
    "R503": (1, "jf4_1"),
    "C502": (0, "jf5_1"),
    "R505": (1, "jf6_1"),
    "Q502": (1, "jf7_1"),
    "RESR_C503": (1, "jf9_1"),
    "R509": (1, "jf10_1"),
}


def esr_cf5(c: CircuitSpec) -> float:
    """CF5's ESR at the same tan-delta as the model's C502 (general-purpose 25 V part)."""
    comp = c.component("C502")
    esr = c.netlist.element(comp.elements["esr"]).numeric_value
    assert esr is not None and comp.nominal is not None
    return esr * comp.nominal / CF5_FARADS


def fault_parts(c: CircuitSpec) -> list[tuple[str, str, str, float]]:
    return [
        ("RF3", "q1c", "jf3_3", RF3_OHMS),
        ("RF4", "jf4_1", "jf4_3", RF4_OHMS),
        ("CF5", "jf5_3", "cf5_esr", CF5_FARADS),
        ("RESR_CF5", "cf5_esr", "0", esr_cf5(c)),
        ("RF8", "vcc_d", "jf8_3", RF8_OHMS),
        ("RF10", "vreg", "jf10_3", RF10_OHMS),
    ]


def header_of(pin_node: str) -> str:
    return pin_node.split("_")[0].upper()


def board_netlist(
    c: CircuitSpec,
    positions: dict[str, str],
    *,
    part_values: dict[str, float] | None = None,
    switched: str | None = None,
    switch_times: tuple[float, float, float, float] | None = None,
    signal_vpk: float | None = None,
    supply_limit: bool = False,
    supply_ramp_s: float | None = None,
) -> str:
    """The physical board as a netlist: every header modelled, fault parts fitted.

    ``positions`` maps header -> "H", "F" or "none" (shunt removed). A ``switched``
    header gets two voltage-controlled switches instead of a fixed shunt: H opens at
    t0, F closes at t1, F opens at t2, H closes at t3 (``switch_times``).
    ``supply_limit`` puts the bench supply's 50 mA current limit between the ideal
    source and VREG; ``supply_ramp_s`` also ramps the source up from 0 V (power-up).
    """
    base = parse_netlist(fault_netlist(c, HEALTHY_FAULT))
    sig = c.signal
    assert sig is not None
    elements: list[Element] = []
    for el in base.elements:
        new = el
        if el.name in PIN1_REWIRES:
            idx, pin = PIN1_REWIRES[el.name]
            nodes = list(el.nodes)
            if nodes[idx] != HEADER_COMMON[header_of(pin)]:
                raise RuntimeError(f"{el.name}: expected node {HEADER_COMMON[header_of(pin)]}, "
                                   f"netlist has {nodes[idx]} (did driver.cir change?)")
            nodes[idx] = pin
            new = new.with_nodes(tuple(nodes))
        if el.name == sig.source and signal_vpk is not None:
            new = new.with_value(f"DC 0 AC 1 SIN(0 {spice_number(signal_vpk)} "
                                 f"{spice_number(sig.frequency)})")
        if el.name == "VREG_BENCH" and supply_limit:
            vreg = parse_value(el.value.split()[-1])
            value = (f"DC {spice_number(vreg)}" if supply_ramp_s is None else
                     f"PWL(0 0 {spice_number(supply_ramp_s)} {spice_number(vreg)})")
            new = Element("VREG_BENCH", ("vsrc", "0"), value)
            # 1 mohm well below the limit, saturating smoothly at the limit (a hard
            # min/max clamp stalls ngspice's time-step control)
            elements.append(Element(
                "BLIMIT", ("vsrc", "vreg"),
                f"I = {SUPPLY_LIMIT_A}*tanh(V(vsrc,vreg)*1000/{SUPPLY_LIMIT_A})"))
        elements.append(new)
    values = dict(part_values or {})
    for name, a, b, v in fault_parts(c):
        elements.append(Element(name, (a, b), spice_number(values.get(name, v))))
    # An open header contact is R_OPEN (1 Gohm, the project's open-circuit convention,
    # ADR-007), so parked leads never float.
    pins = sorted({n for el in elements for n in el.nodes if n.startswith("jf")})
    for p in pins:
        elements.append(Element(f"RLK_{p}", (p, HEADER_COMMON[header_of(p)]),
                                spice_number(R_OPEN)))
    directives = list(base.directives)
    for h in HEADERS:
        common = HEADER_COMMON[h]
        num = h[2:]
        if h == switched:
            assert switch_times is not None
            t0, t1, t2, t3 = switch_times
            e = 1e-6
            pwl_h = f"PWL(0 1 {t0} 1 {t0 + e} 0 {t3} 0 {t3 + e} 1)"
            pwl_f = f"PWL(0 0 {t1} 0 {t1 + e} 1 {t2} 1 {t2 + e} 0)"
            elements += [
                Element(f"SSH_{h}_H", (common, f"am{num}_1", f"ctl{num}_1", "0"), "SWSH"),
                Element(f"VAM_{h}_H", (f"am{num}_1", f"jf{num}_1"), "DC 0"),
                Element(f"VCTL_{h}_H", (f"ctl{num}_1", "0"), pwl_h),
                Element(f"SSH_{h}_F", (common, f"am{num}_3", f"ctl{num}_3", "0"), "SWSH"),
                Element(f"VAM_{h}_F", (f"am{num}_3", f"jf{num}_3"), "DC 0"),
                Element(f"VCTL_{h}_F", (f"ctl{num}_3", "0"), pwl_f),
            ]
            directives.append(f".model SWSH SW(VT=0.5 VH=0.1 RON={HEADER_CONTACT_OHMS} "
                              f"ROFF={spice_number(R_OPEN)})")
            continue
        pos = positions.get(h, "H")
        if pos in ("H", "F"):
            pin = f"jf{num}_{1 if pos == 'H' else 3}"
            elements.append(Element(f"RSH_{h}", (common, pin), spice_number(HEADER_CONTACT_OHMS)))
        elif pos != "none":
            raise ValueError(pos)
    net = Netlist(title=f"* fault board / {positions}", includes=[], elements=elements,
                  directives=directives)
    return net.render([DEVICE_LIBRARY])


def board_positions(fault_header: str | None) -> dict[str, str]:
    return {h: ("F" if h == fault_header else "H") for h in HEADERS}


# ---------------------------------------------------------------------------
# Draws
# ---------------------------------------------------------------------------


def _trunc_normal(rng: np.random.Generator, sigma: float, limit: float) -> float:
    """Same distribution as differential.sim.draws (ADR-006)."""
    while True:
        x = float(rng.normal(0.0, sigma))
        if abs(x) <= limit:
            return x


def nominal_draw(c: CircuitSpec) -> Draw:
    """Every part at its netlist value, transistors at the model card's BF."""
    d = Draw()
    for comp in c.components:
        if comp.kind in ("resistor", "film_cap", "electrolytic"):
            assert comp.nominal is not None
            d.alters[comp.main_element] = comp.nominal
            d.lift[comp.ref] = comp.nominal
            if comp.kind == "electrolytic":
                esr = comp.elements["esr"]
                v = c.netlist.element(esr).numeric_value
                assert v is not None
                d.alters[esr] = v
        elif comp.kind == "bjt":
            assert comp.model is not None
            d.altermods[(device_model_name(comp), "bf")] = MODEL_BF[comp.model]
            d.lift[comp.ref] = 1.0  # relative hFE, as in draws.healthy_draw
    return d


def apply_board_parts(c: CircuitSpec, fault_id: str, d: Draw,
                      rng: np.random.Generator | None) -> Draw:
    """Replace the catalog's sampled severity by the part fitted on the board.

    ``rng`` None -> nominal part values; otherwise each part gets its own tolerance
    draw (1 % resistors; CF5 +-20 % with ESR at tan-delta limit x U(0.4, 1.0)).
    """
    def part(nominal: float, tol: float) -> float:
        return nominal if rng is None else nominal * (1.0 + _trunc_normal(rng, tol / 2, tol))

    if fault_id == "Q501:cb_leak":
        d.alters["RFLT_Q501"] = part(RF3_OHMS, FAULT_PART_TOL)
    elif fault_id == "Q502:ce_short":
        d.alters["RFLT_Q502"] = part(RF8_OHMS, FAULT_PART_TOL)
    elif fault_id == "R503:drift_x2":
        d.alters["R503"] = d.alters["R503"] / 2.0 + part(RF4_OHMS, FAULT_PART_TOL)
    elif fault_id == "R509:drift_x10":
        d.alters["R509"] = part(RF10_OHMS, FAULT_PART_TOL)
    elif fault_id == "C502:cap_loss_90":
        d.alters["C502"] = part(CF5_FARADS, CF5_TOL)
        d.alters["RESR_C502"] = esr_cf5(c) * (1.0 if rng is None else float(rng.uniform(0.4, 1.0)))
    return d


def nominal_fault_draw(c: CircuitSpec, fault_id: str, board: bool = True) -> Draw:
    d = nominal_draw(c)
    apply_fault(c, d, parse_fault_id(fault_id), np.random.default_rng(0))
    if board:
        apply_board_parts(c, fault_id, d, None)
    return d


def worst_case_draw(c: CircuitSpec, fault_id: str) -> Draw:
    """Nominal parts with the most current-hungry end of the catalog severity range."""
    f = parse_fault_id(fault_id)
    d = nominal_fault_draw(c, fault_id, board=False)
    if f.is_healthy:
        return d
    comp = c.component(f.ref)
    if comp.kind == "resistor" and f.mode == "short":
        d.alters[comp.main_element] = 0.01
    elif comp.kind == "electrolytic" and f.mode == "short":
        d.alters[f"RFLT_{f.ref}"] = 0.1
    elif comp.kind == "electrolytic" and f.mode == "high_esr":
        esr = comp.elements["esr"]
        d.alters[esr] = float(c.netlist.element(esr).numeric_value or 0.0) * 100.0
    elif f.mode == "ce_short":
        d.alters[f"RFLT_{f.ref}"] = 1.0
    elif f.mode == "cb_leak":
        d.alters[f"RFLT_{f.ref}"] = 47e3
    return d


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------

FAILURES: list[dict[str, object]] = []


def run_ngspice(text: str, files: Sequence[str] = ()) -> tuple[str, dict[str, str]]:
    with tempfile.TemporaryDirectory(prefix="faultboard_") as tmp:
        path = Path(tmp) / "deck.cir"
        path.write_text(text)
        proc = subprocess.run(["ngspice", "-b", str(path)], capture_output=True, text=True,
                              timeout=300, cwd=tmp)
        got = {f: (Path(tmp) / f).read_text() for f in files if (Path(tmp) / f).exists()}
        return proc.stdout + "\n" + proc.stderr, got


def simulate(c: CircuitSpec, fault_id: str, draws: list[tuple[int, Draw]]) -> list[DrawResult]:
    batch = simulate_draws(c, parse_fault_id(fault_id), draws)
    FAILURES.extend(batch.failures)
    return [batch.results[i] for i, _ in draws]


def simulate_board_deck(c: CircuitSpec, net_text: str) -> DrawResult:
    """Run the project's standard analyses (builder.control_lines) on a board netlist."""
    ctl, obs = control_lines(c, [(0, Draw())])
    expected: dict[str, list[int]] = {}
    for i, o in enumerate(obs):
        expected.setdefault("op" if o.kind == "dc" else o.kind, []).append(i)
    out, _ = run_ngspice(net_text + "\n".join(ctl) + "\n")
    res = parse_output(out, len(obs), (0,), expected)[0]
    if not res.ok:
        FAILURES.append({"circuit": "fault_board", "hypothesis": "board netlist", "draw": 0,
                         "reason": res.reason})
    return res


def reading_value(kind: str, value: float, fundamental: float) -> float:
    """What the instrument shows (and the engine receives) for a noise-free value."""
    if not math.isfinite(value):
        return math.nan
    if kind == "dc":
        return value
    if kind in ("ac", "ac20", "ac20k"):
        return max(value, 0.0)
    if kind == "thd":
        if not math.isfinite(fundamental) or fundamental < meas.THD_MIN_FUNDAMENTAL:
            return meas.THD_NO_SIGNAL
        return min(max(value, meas.THD_FLOOR), meas.THD_NO_SIGNAL)
    raise ValueError(kind)


@dataclass
class HypStats:
    fault_id: str
    readings: np.ndarray  # draws x observables (instrument view)
    engine: np.ndarray  # same in engine space
    supply_ma: np.ndarray
    n_failed: int


def to_stats(c: CircuitSpec, obs: list[ObservableSpec], fault_id: str,
             draws: list[tuple[int, Draw]], results: list[DrawResult]) -> HypStats:
    vreg = vreg_volts(c)
    tp23 = [o.key for o in obs].index("dc:TP23")
    rows, eng, sup, failed = [], [], [], 0
    for (_, d), r in zip(draws, results, strict=True):
        if not r.ok:
            failed += 1
            continue
        row = [reading_value(o.kind, float(v), r.fundamental) for o, v in zip(obs, r.values,
                                                                             strict=True)]
        rows.append(row)
        eng.append([meas.reading_to_engine(o.kind, v) for o, v in zip(obs, row, strict=True)])
        r509 = d.alters.get("R509", float(c.netlist.element("R509").numeric_value or 47.0))
        sup.append(1e3 * (vreg - row[tp23]) / r509)
    return HypStats(fault_id, np.array(rows), np.array(eng), np.array(sup), failed)


def vreg_volts(c: CircuitSpec) -> float:
    return parse_value(c.netlist.element("VREG_BENCH").value.split()[-1])


# ---------------------------------------------------------------------------
# Operating-point stress analysis (safety)
# ---------------------------------------------------------------------------

_ASSIGN = re.compile(r"^\s*(\S+)\s*=\s*([-+0-9.eE]+)\s*$")


def op_point(net_text: str, alters: dict[str, float] | None = None,
             altermods: dict[tuple[str, str], float] | None = None
             ) -> tuple[dict[str, float], dict[str, dict[str, float]], float]:
    ctl = [".control", "set noaskquit", "set numdgt=12"]
    for name, v in sorted((alters or {}).items()):
        ctl.append(f"alter {name} = {spice_number(v)}")
    for (model, param), v in sorted((altermods or {}).items()):
        ctl.append(f"altermod {model} {param} = {spice_number(v)}")
    ctl += ["op", "print all", "print @q501[ic] @q501[ib] @q502[ic] @q502[ib]",
            "print i(VREG_BENCH)", ".endc", ".end"]
    out, _ = run_ngspice(net_text + "\n".join(ctl) + "\n")
    vals: dict[str, float] = {}
    for line in out.splitlines():
        m = _ASSIGN.match(line)
        if m:
            vals[m.group(1).lower()] = float(m.group(2))
    volts = {"0": 0.0}
    for k, v in vals.items():
        if k.startswith("v(") and k.endswith(")"):
            volts[k[2:-1]] = v
        elif not (k.startswith("@") or k.startswith("i(") or "#" in k):
            volts[k] = v
    bjt = {q: {"ic": vals[f"@{q}[ic]"], "ib": vals[f"@{q}[ib]"]} for q in ("q501", "q502")}
    return volts, bjt, -vals["i(vreg_bench)"]


@dataclass
class Stress:
    supply_ma: float
    resistors: dict[str, tuple[float, float, float]]  # name -> (P W, rating W, fraction)
    r506_w: float
    bjts: dict[str, dict[str, float]]
    caps: dict[str, tuple[float, float]]  # name -> (V(+) - V(-), rating V)
    header_ma: dict[str, float]
    problems: list[str]


def cap_rating_v(c: CircuitSpec, name: str) -> float:
    if name == "CF5":
        return CF5_RATING_V
    for comp in c.components:
        if comp.main_element == name and comp.rating:
            return parse_value(comp.rating.split()[0])
    raise KeyError(name)


def resistor_rating_w(c: CircuitSpec, name: str, board: bool) -> float | None:
    if name in ("RF3", "RF4", "RF8", "RF10"):
        return FAULT_PART_RATING_W
    if name in ("RSRC_D", "RLOAD_EXT"):
        return FIXTURE_RATING_W
    if board and name in BOARD_RATING_OVERRIDE_W:
        return BOARD_RATING_OVERRIDE_W[name]
    for comp in c.components:
        if comp.main_element == name and comp.kind == "resistor" and comp.rating:
            return parse_value(comp.rating.split()[0])
    return None  # ESR, fault paths, header contacts, leak models


def stress(c: CircuitSpec, net_text: str, polarity: dict[str, int], board: bool,
           alters: dict[str, float] | None = None,
           altermods: dict[tuple[str, str], float] | None = None) -> Stress:
    volts, bjt, isup = op_point(net_text, alters, altermods)
    alters = alters or {}
    elements = parse_netlist(net_text).elements
    res: dict[str, tuple[float, float, float]] = {}
    caps: dict[str, tuple[float, float]] = {}
    bj: dict[str, dict[str, float]] = {}
    hdr: dict[str, float] = {}
    r506_w = math.nan
    problems: list[str] = []

    def v(n: str) -> float:
        return volts[n.lower()]

    for el in elements:
        if el.letter == "R":
            r = alters.get(el.name, el.numeric_value)
            assert r is not None
            dv = v(el.nodes[0]) - v(el.nodes[1])
            p = dv * dv / r
            if el.name.startswith("RSH_"):
                hdr[el.name[4:]] = 1e3 * abs(dv / r)
            if el.name == "R506":
                r506_w = p
            rating = resistor_rating_w(c, el.name, board)
            if rating is not None:
                res[el.name] = (p, rating, p / rating)
                if p > rating:
                    problems.append(f"{el.name} {1e3 * p:.0f} mW > {1e3 * rating:.0f} mW")
        elif el.letter == "C" and el.name in polarity:
            plus = polarity[el.name]
            dv = v(el.nodes[plus]) - v(el.nodes[1 - plus])
            rating = cap_rating_v(c, el.name)
            caps[el.name] = (dv, rating)
            if dv < REVERSE_POLARITY_FLAG_V:
                problems.append(f"{el.name} reverse-biased {dv:.2f} V")
            if abs(dv) > rating:
                problems.append(f"{el.name} {dv:.1f} V > {rating:.0f} V")
        elif el.letter == "Q":
            name = el.name.lower()
            cn, bn, en = el.nodes
            vce = v(cn) - v(en)
            vbe = v(bn) - v(en)
            ic, ib = bjt[name]["ic"], bjt[name]["ib"]
            p = vce * ic + vbe * ib
            bj[el.name] = {"vce": vce, "ic": ic, "p": p, "veb_rev": max(0.0, -vbe),
                           "vcb_rev": max(0.0, v(cn) - v(bn))}
            over = [msg for bad, msg in (
                (vce > BJT_VCEO_V, f"VCE {vce:.1f} V > {BJT_VCEO_V:.0f} V"),
                (ic > BJT_IC_A, f"IC {1e3 * ic:.0f} mA > {1e3 * BJT_IC_A:.0f} mA"),
                (p > BJT_PD_W, f"P {1e3 * p:.0f} mW > {1e3 * BJT_PD_W:.0f} mW"),
                (-vbe > BJT_VEBO_V, f"reverse VEB {-vbe:.1f} V > {BJT_VEBO_V:.1f} V"),
            ) if bad]
            if over:
                problems.append(f"{el.name} " + ", ".join(over))
    if isup > SUPPLY_LIMIT_A:
        problems.append(f"supply {1e3 * isup:.0f} mA > {1e3 * SUPPLY_LIMIT_A:.0f} mA limit")
    return Stress(1e3 * isup, res, r506_w, bj, caps, hdr, problems)


def electrolytic_polarity(c: CircuitSpec, board_text: str) -> dict[str, int]:
    """Index of each electrolytic's + terminal: the node at the higher healthy DC voltage."""
    volts, _, _ = op_point(board_text)
    pol: dict[str, int] = {}
    for el in parse_netlist(board_text).elements:
        if el.letter == "C":
            a, b = (volts[n.lower()] for n in el.nodes)
            if abs(a - b) < 0.1:
                raise RuntimeError(f"{el.name}: polarity undefined ({a:.3f} V vs {b:.3f} V)")
            pol[el.name] = 0 if a > b else 1
    return pol


# ---------------------------------------------------------------------------
# Transients: settling after power-up and after a shunt move
# ---------------------------------------------------------------------------


def tran_table(net_text: str, tstop: float, tout: float, tmax: float, vectors: Sequence[str],
               extremes: dict[str, str]) -> tuple[dict[str, np.ndarray],
                                                  dict[str, tuple[float, float]]]:
    """Transient with internal steps <= ``tmax``.

    Returns ``vectors`` resampled every ``tout`` (for settling analysis), and the
    (max, min) of each ``extremes`` expression over the full-resolution solution.
    """
    labels = list(extremes)
    ctl = [".control", "set noaskquit", "set wr_singlescale", "set wr_vecnames",
           f"tran {spice_number(tout)} {spice_number(tstop)} 0 {spice_number(tmax)}"]
    for i, label in enumerate(labels):
        ctl += [f"let xv{i} = {extremes[label]}", f"meas tran xmax{i} MAX xv{i}",
                f"meas tran xmin{i} MIN xv{i}"]
    ctl += ["linearize", "wrdata w.txt " + " ".join(vectors), ".endc", ".end"]
    out, files = run_ngspice(net_text + "\n".join(ctl) + "\n", files=["w.txt"])
    if "w.txt" not in files or "aborted" in out or "too small" in out:
        raise RuntimeError("transient failed:\n" + out[-2000:])
    found = {m.group(1): float(m.group(2)) for m in
             re.finditer(r"^\s*(xm(?:ax|in)\d+)\s*=\s*([-+0-9.eE]+)", out, flags=re.M)}
    ext = {label: (found[f"xmax{i}"], found[f"xmin{i}"]) for i, label in enumerate(labels)}
    data = np.loadtxt(files["w.txt"].splitlines()[1:])
    return {k: data[:, i] for i, k in enumerate(["time", *vectors])}, ext


def alter_lines(d: Draw) -> list[str]:
    out = [f"alter {name} = {spice_number(v)}" for name, v in sorted(d.alters.items())]
    out += [f"altermod {m} {p} = {spice_number(v)}" for (m, p), v in sorted(d.altermods.items())]
    return out


def fundamentals(c: CircuitSpec, fault_id: str, d: Draw, freq: float, vpk: float,
                 nodes: Sequence[str]) -> dict[str, float]:
    """Fundamental amplitude (V peak) at each node for a sine of ``vpk`` at GEN."""
    assert c.signal is not None
    net = re.sub(rf"^({re.escape(c.signal.source)}\s+\S+\s+\S+\s).*$",
                 rf"\g<1>DC 0 AC 1 SIN(0 {spice_number(vpk)} {spice_number(freq)})",
                 fault_netlist(c, parse_fault_id(fault_id)), count=1, flags=re.M)
    period = 1.0 / freq
    n_per = 40 if freq < 100 else 20
    step = spice_number(period / 200)
    ctl = [".control", "set noaskquit", *alter_lines(d),
           f"tran {step} {spice_number(n_per * period)} {spice_number((n_per - 2) * period)} "
           f"{step}", f"fourier {spice_number(freq)} " + " ".join(f"v({n})" for n in nodes),
           ".endc", ".end"]
    out, _ = run_ngspice(net + "\n".join(ctl) + "\n")
    found: dict[str, float] = {}
    for block in out.split("Fourier analysis for ")[1:]:
        name = block.split(":", 1)[0].strip().lower()
        for line in block.splitlines():
            m = HARM_RE.match(line)
            if m:
                found[name[2:-1]] = float(m.group(2))
                break
    return found


def settle_tolerance(v_final: float) -> float:
    """Within the DMM's accuracy of the final value, and never tighter than 10 mV."""
    return max(meas.DMM_PCT * abs(v_final) + meas.DMM_DIGITS * meas.dmm_resolution(v_final),
               0.010)


def settle_time(t: np.ndarray, v: np.ndarray, t_from: float, t_to: float) -> float:
    sel = (t >= t_from) & (t <= t_to)
    tt, vv = t[sel], v[sel]
    final = vv[-1]
    bad = np.abs(vv - final) > settle_tolerance(final)
    if not bad.any():
        return 0.0
    return float(tt[np.nonzero(bad)[0][-1]] - t_from)


# ---------------------------------------------------------------------------
# Separation tests in engine space
# ---------------------------------------------------------------------------


def _halo(kind: str, t: float) -> float:
    """About 95 % of instrument noise plus the engine's variance floor (ADR-008)."""
    return 2.0 * math.sqrt(meas.engine_noise_sd(kind, t) ** 2 + meas.VAR_FLOOR[kind])


def separation(kind: str, a: np.ndarray, b: np.ndarray) -> int:
    """+1 if a reads clearly higher than b, -1 if clearly lower, 0 if the bands overlap."""
    a5, a95 = np.percentile(a, [5, 95])
    b5, b95 = np.percentile(b, [5, 95])
    if a95 + _halo(kind, a95) < b5 - _halo(kind, b5):
        return -1
    if b95 + _halo(kind, b95) < a5 - _halo(kind, a5):
        return 1
    return 0


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def sig3(v: float) -> str:
    if not math.isfinite(v):
        return "n/a"
    if v == 0:
        return "0"
    d = max(0, 2 - math.floor(math.log10(abs(v))))
    return f"{v:.{d}f}"


def fmt_dc(v: float) -> str:
    d = max(0, round(-math.log10(meas.dmm_resolution(v))))
    s = f"{v:.{d}f}"
    return f"{0.0:.{d}f}" if float(s) == 0 else s


def fmt(kind: str, v: float) -> str:
    if not math.isfinite(v):
        return "n/a"
    if kind == "dc":
        return fmt_dc(v)
    if kind in ("ac", "ac20", "ac20k"):
        return "<0.001" if v < meas.GAIN_FLOOR else sig3(v)
    if kind == "thd":
        return "100 (no signal)" if v >= meas.THD_NO_SIGNAL else sig3(v)
    if kind == "ma":
        return f"{v:.2f}"
    raise ValueError(kind)


def dmm_limit(v: float) -> float:
    return meas.DMM_PCT * abs(v) + meas.DMM_DIGITS * meas.dmm_resolution(v)


def accept_window(o: ObservableSpec, p5: float, p95: float) -> str:
    if o.kind == "dc":
        if o.tp == "TP17" and max(abs(p5), abs(p95)) < TP17_ZERO_V:
            return f"within ±{TP17_ZERO_V:.3f} V: enter 0"
        if o.tp == "TP22" and max(abs(p5), abs(p95)) < TP22_ZERO_V:
            return f"within ±{TP22_ZERO_V:.3f} V: enter 0"
        return f"{fmt_dc(p5 - dmm_limit(p5))} to {fmt_dc(p95 + dmm_limit(p95))}"
    if o.kind in ("ac", "ac20", "ac20k"):
        if p95 < meas.GAIN_FLOOR:
            return "no signal: enter 0"
        return f"{sig3(p5 * (1 - meas.SCOPE_REL))} to {sig3(p95 * (1 + meas.SCOPE_REL))}"
    if o.kind == "thd":
        if p5 >= meas.THD_NO_SIGNAL:
            return "no signal: enter 100"
        hi = min(p95 * (1 + meas.THD_REL), meas.THD_NO_SIGNAL)
        return f"{sig3(p5 * (1 - meas.THD_REL))} to {sig3(hi)}"
    raise ValueError(o.kind)


def row_label(o: ObservableSpec, c: CircuitSpec) -> str:
    tp = c.test_point(o.tp or "")
    if o.kind == "dc":
        return f"DC {o.tp} {tp.node} (V)"
    if o.kind == "ac":
        return f"Gain {o.tp} {tp.node}, 1 kHz (V/V)"
    if o.kind == "ac20":
        return f"Gain {o.tp} {tp.node}, 20 Hz (V/V)"
    if o.kind == "ac20k":
        return f"Gain {o.tp} {tp.node}, 20 kHz (V/V)"
    if o.kind == "thd":
        return f"THD {o.tp} {tp.node}, 1 kHz at 1.38 Vpp (%)"
    raise ValueError(o.kind)


def ordinal(k: int) -> str:
    suffix = "th" if 10 <= k % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(k % 10, "th")
    return f"{k}{suffix}"


def md_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def fault_title(fault_id: str) -> str:
    if fault_id == "healthy":
        return "healthy (all shunts on H)"
    f = parse_fault_id(fault_id)
    return f"{f.ref} {MODE_LABELS[f.mode]}"


def _finite(x: Any) -> Any:
    """JSON has no NaN: map non-finite floats to None, recursively."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): _finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_finite(v) for v in x]
    return x


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--draws", type=int, default=DEFAULT_DRAWS,
                    help="Monte Carlo draws per hypothesis (default 50)")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", type=Path, default=HERE / "expected_readings.md")
    args = ap.parse_args(argv)
    n = args.draws
    workers = args.workers or n_workers()
    t_start = dt.datetime.now()

    c = get_circuit(CIRCUIT_ID)
    obs = spice_observables(c)
    keys = [o.key for o in obs]
    catalog = fault_catalog(c)
    hyp_index = {f.id: i for i, f in enumerate(catalog)}
    board_ids = ["healthy", *(bf.fault_id for bf in BOARD_FAULTS)]
    for fid in board_ids:
        if fid not in hyp_index:
            raise SystemExit(f"{fid} is not in the driver fault catalog")
    header_of_fault = {bf.fault_id: bf.header for bf in BOARD_FAULTS}
    log = lambda msg: print(f"[make_expected] {msg}", file=sys.stderr, flush=True)  # noqa: E731

    def catalog_draws(fid: str) -> list[tuple[int, Draw]]:
        return [(i, make_draw(CIRCUIT_ID, SPLIT, hyp_index[fid], fid, i)) for i in range(n)]

    def board_draws(fid: str) -> list[tuple[int, Draw]]:
        out = []
        for i, d in catalog_draws(fid):
            rng = np.random.default_rng([BASE_SEED, circuit_index(CIRCUIT_ID), SPLIT_INDEX[SPLIT],
                                         hyp_index[fid], i, BOARD_SEED_WORD])
            out.append((i, apply_board_parts(c, fid, d, rng)))
        return out

    # 1. Nominal readings: board parts, and the plain catalog model for comparison
    log("nominal readings")
    nominal: dict[str, DrawResult] = {}
    nominal_draws: dict[str, Draw] = {}
    for fid in board_ids:
        d = nominal_fault_draw(c, fid, board=True)
        nominal_draws[fid] = d
        nominal[fid] = simulate(c, fid, [(0, d)])[0]
    nominal_stats = {fid: to_stats(c, obs, fid, [(0, nominal_draws[fid])], [nominal[fid]])
                     for fid in board_ids}

    # 2. Monte Carlo: board parts (tolerance draws) and the full catalog (engine's view)
    log(f"Monte Carlo: {len(board_ids)} board states + {len(catalog)} catalog hypotheses "
        f"x {n} draws on {workers} workers")

    def job_board(fid: str) -> tuple[str, HypStats]:
        dr = board_draws(fid)
        return fid, to_stats(c, obs, fid, dr, simulate(c, fid, dr))

    def job_catalog(fid: str) -> tuple[str, HypStats]:
        dr = catalog_draws(fid)
        return fid, to_stats(c, obs, fid, dr, simulate(c, fid, dr))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        board_mc = dict(pool.map(job_board, board_ids))
        cat_mc = dict(pool.map(job_catalog, [f.id for f in catalog]))

    # 3. Signatures (vs healthy) and look-alikes (engine view, catalog draws)
    log("signatures and look-alikes")
    healthy_b = board_mc["healthy"]
    signature: dict[str, dict[str, int]] = {}
    for fid in board_ids:
        s = board_mc[fid]
        signature[fid] = {o.key: separation(o.kind, s.engine[:, j], healthy_b.engine[:, j])
                          for j, o in enumerate(obs)}
    look_alikes: dict[str, list[str]] = {}
    for fid in board_ids[1:]:
        mine = cat_mc[fid]
        alikes = []
        for f in catalog:
            if f.id == fid:
                continue
            other = cat_mc[f.id]
            if all(separation(o.kind, mine.engine[:, j], other.engine[:, j]) == 0
                   for j, o in enumerate(obs)):
                alikes.append(f.id)
        look_alikes[fid] = alikes

    # Where the board nominal sits relative to the engine's catalog band
    outside_catalog: dict[str, list[str]] = {}
    for fid in board_ids:
        cm = cat_mc[fid]
        nom = nominal_stats[fid].engine[0]
        outs = []
        for j, o in enumerate(obs):
            lo, hi = np.percentile(cm.engine[:, j], [5, 95])
            if not (lo - _halo(o.kind, lo) <= nom[j] <= hi + _halo(o.kind, hi)):
                outs.append(o.key)
        outside_catalog[fid] = outs

    # Smallest non-zero DC any catalog hypothesis predicts at TP17 / TP22
    zero_evidence: dict[str, tuple[str, float] | None] = {}
    for tp in ("TP17", "TP22"):
        j = keys.index(f"dc:{tp}")
        best: tuple[str, float] | None = None
        for f in catalog:
            vals = np.abs(cat_mc[f.id].readings[:, j])
            if np.median(vals) > 0.001:
                p5 = float(np.percentile(vals, 5))
                if best is None or p5 < best[1]:
                    best = (f.id, p5)
        zero_evidence[tp] = best

    # 4. Board-level netlist check (headers as 0.05 ohm links, parts as fitted)
    log("board netlist check")
    board_check: dict[str, dict[str, float]] = {}
    board_nets = {fid: board_netlist(c, board_positions(header_of_fault.get(fid)))
                  for fid in board_ids}
    for fid in board_ids:
        r = simulate_board_deck(c, board_nets[fid])
        ref = nominal[fid]
        ddc, dgain = 0.0, 0.0
        for j, o in enumerate(obs):
            a = reading_value(o.kind, float(r.values[j]), r.fundamental)
            b = reading_value(o.kind, float(ref.values[j]), ref.fundamental)
            if o.kind == "dc":
                ddc = max(ddc, abs(a - b))
            elif o.kind in ("ac", "ac20", "ac20k") and b >= meas.GAIN_FLOOR:
                dgain = max(dgain, abs(a / b - 1.0))
            elif o.kind in ("ac", "ac20", "ac20k") and max(a, b) >= meas.GAIN_FLOOR:
                dgain = max(dgain, 1.0)  # one reads a signal, the other does not
        board_check[fid] = {"max_dc_mv": 1e3 * ddc, "max_gain_pct": 100 * dgain}

    # Pure catalog nominal (model severity) for the three faults whose board part differs
    catalog_nominal: dict[str, DrawResult] = {}
    for fid in ("Q501:cb_leak", "Q502:ce_short", "C502:cap_loss_90"):
        d = nominal_fault_draw(c, fid, board=False)
        if fid == "Q501:cb_leak":
            d.alters["RFLT_Q501"] = math.sqrt(47e3 * 470e3)  # geometric centre of 47k-470k
        if fid == "Q502:ce_short":
            d.alters["RFLT_Q502"] = math.sqrt(1.0 * 50.0)  # geometric centre of 1-50 ohm
        catalog_nominal[fid] = simulate(c, fid, [(0, d)])[0]

    # 5. Safety: board states, JF8 dead short, catalog screen at worst-case severity
    log("safety screen")
    polarity = electrolytic_polarity(c, board_nets["healthy"])
    board_stress = {fid: stress(c, board_nets[fid], polarity, board=True) for fid in board_ids}
    dead_short = stress(c, board_netlist(c, board_positions("JF8"), part_values={"RF8": 1e-3}),
                        polarity, board=True)
    # Two shunts on F at once (a setter's slip, or a deliberate double fault)
    pairs: dict[str, Stress] = {}
    for a, b in itertools.combinations(HEADERS, 2):
        pos = {h: ("F" if h in (a, b) else "H") for h in HEADERS}
        pairs[f"{a}+{b}"] = stress(c, board_netlist(c, pos), polarity, board=True)
    cat_polarity = {k: v for k, v in polarity.items() if k != "CF5"}
    screen: dict[str, Stress] = {}
    for f in catalog:
        d = worst_case_draw(c, f.id)
        screen[f.id] = stress(c, fault_netlist(c, f), cat_polarity, board=False,
                              alters=d.alters, altermods=d.altermods)

    # 6. Test level: every gain reading at both bench levels vs the small-signal model
    log("test-level check")
    assert c.signal is not None and c.signal.tran_amplitude is not None
    thd_vpk = c.signal.tran_amplitude
    j22 = keys.index("ac:TP22")
    freq_of = {"ac": 1000.0, "ac20": 20.0, "ac20k": 20000.0}
    gain_obs = [o for o in obs if o.kind in freq_of]
    level_jobs = [(fid, kind, vpk) for fid in board_ids for kind in freq_of
                  for vpk in (GAIN_TEST_VPK, thd_vpk)]

    def job_level(job: tuple[str, str, float]) -> tuple[tuple[str, str, float], dict[str, float]]:
        fid, kind, vpk = job
        nodes = [o.node or "" for o in gain_obs if o.kind == kind]
        return job, fundamentals(c, fid, nominal_draws[fid], freq_of[kind], vpk, nodes)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        level_raw = dict(pool.map(job_level, level_jobs))
    # ratio (bench fundamental gain / small-signal gain) per state, level and observable
    level_check: dict[str, dict[str, dict[str, float]]] = {}
    for fid in board_ids:
        per_level: dict[str, dict[str, float]] = {}
        for vpk in (GAIN_TEST_VPK, thd_vpk):
            ratios = {}
            for o in gain_obs:
                small = float(nominal[fid].values[keys.index(o.key)])
                amp = level_raw[(fid, o.kind, vpk)].get(o.node or "", math.nan)
                if small >= meas.GAIN_FLOOR:
                    ratios[o.key] = (amp / vpk) / small
            per_level[f"{2 * vpk:.2f} Vpp"] = ratios
        level_check[fid] = per_level

    # 7. Supply sensitivity (healthy, nominal parts)
    log("supply sensitivity")
    vreg = vreg_volts(c)
    d_lo, d_hi = nominal_draw(c), nominal_draw(c)
    d_lo.alters["VREG_BENCH"] = vreg - SUPPLY_STEP_V
    d_hi.alters["VREG_BENCH"] = vreg + SUPPLY_STEP_V
    lo, hi = simulate(c, "healthy", [(0, d_lo), (1, d_hi)])
    sensitivity = {o.key: (float(hi.values[j]) - float(lo.values[j])) / (2 * SUPPLY_STEP_V)
                   for j, o in enumerate(obs) if o.kind == "dc" or o.key == "ac:TP22"}

    # 8. Settling: power-up (current-limited supply) and every shunt move
    log("settling transients")
    tp_nodes = {tp.id: tp.node for tp in c.test_points}
    vecs = [f"v({node})" for node in tp_nodes.values()]
    cap_nodes = {el.name: (el.nodes[polarity[el.name]], el.nodes[1 - polarity[el.name]])
                 for el in parse_netlist(board_nets["healthy"]).elements if el.letter == "C"}

    cap_expr = {f"cap:{name}": f"v({p})-v({m})" for name, (p, m) in cap_nodes.items()}

    def transient_summary(tr: dict[str, np.ndarray], ext: dict[str, tuple[float, float]]
                          ) -> dict[str, Any]:
        isup = -tr["i(VREG_BENCH)"]
        margins = {k[4:]: round(v[1], 3) + 0.0 for k, v in ext.items() if k.startswith("cap:")}
        worst_cap = min(margins, key=lambda k: margins[k])
        return {"peak_supply_ma": -1e3 * ext["supply"][1],
                "limit_ms": 1e3 * float(np.sum(np.diff(tr["time"])[
                    isup[1:] > 0.99 * SUPPLY_LIMIT_A])),
                "min_cap_margin_v": margins[worst_cap], "worst_cap": worst_cap}

    up, up_ext = tran_table(
        board_netlist(c, board_positions(None), signal_vpk=0.0, supply_limit=True,
                      supply_ramp_s=1e-3), 20.0, 1e-3, 50e-6, [*vecs, "i(VREG_BENCH)"],
        {"supply": "i(VREG_BENCH)", **cap_expr})
    powerup = {"settle_s": max(settle_time(up["time"], up[v], 0.0, 20.0) for v in vecs),
               "final_ma": -1e3 * float(up["i(VREG_BENCH)"][-1]),
               **transient_summary(up, up_ext)}
    t0, t1, t2, t3, t_end = 1.0, 1.5, 21.5, 22.0, 42.0
    moves: dict[str, dict[str, Any]] = {}

    def job_move(h: str) -> tuple[str, dict[str, Any]]:
        net = board_netlist(c, board_positions(None), switched=h, signal_vpk=0.0,
                            switch_times=(t0, t1, t2, t3), supply_limit=True)
        tr, ext = tran_table(net, t_end, 2e-3, 2e-4, [*vecs, "i(VREG_BENCH)"],
                             {"supply": "i(VREG_BENCH)", "hdr_h": f"i(VAM_{h}_H)",
                              "hdr_f": f"i(VAM_{h}_F)", "tp22": "v(out)", **cap_expr})
        tt = tr["time"]
        tp22 = max(ext["tp22"], key=abs)
        return h, {
            "to_fault_s": max(settle_time(tt, tr[v], t1, t2) for v in vecs),
            "to_healthy_s": max(settle_time(tt, tr[v], t3, t_end) for v in vecs),
            "peak_header_ma": 1e3 * max(abs(x) for x in (*ext["hdr_h"], *ext["hdr_f"])),
            "tp22_extreme_v": round(tp22, 3) + 0.0,
            **transient_summary(tr, ext),
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        moves = dict(pool.map(job_move, HEADERS))

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    log("writing report")
    total_draws = sum(len(s.readings) + s.n_failed for s in board_mc.values()) + \
        sum(len(s.readings) + s.n_failed for s in cat_mc.values())
    net_hash = hashlib.sha256(fault_netlist(c, HEALTHY_FAULT).encode()).hexdigest()
    lib_hash = hashlib.sha256(DEVICE_LIBRARY.read_bytes()).hexdigest()
    tol_hash = hashlib.sha256(Path(draws_module.__file__).read_bytes()).hexdigest()
    manifest_path = ROOT / "data" / "sim" / "manifest.json"
    manifest_match = "data/sim/manifest.json not found"
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text())
        checks = {"driver netlist": m.get("netlist_sha256", {}).get(CIRCUIT_ID) == net_hash,
                  "device library": m.get("netlist_sha256", {}).get("devices.lib") == lib_hash,
                  "draws.py": m.get("tolerance_spec_sha256") == tol_hash}
        manifest_match = "; ".join(f"{k}: {'same' if v else 'DIFFERENT'}"
                                   for k, v in checks.items())
        if not all(checks.values()):
            manifest_match += (" (a file changed after the engine's training data were "
                               "simulated; check that the change leaves the default draws "
                               "and the netlist unchanged, or re-run `differential sim`)")
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, cwd=ROOT, timeout=10).stdout.strip() or "unknown"
    except OSError:
        head = "unknown"

    L: list[str] = []
    w = L.append
    w("# Fault board: expected readings")
    w("")
    w(f"Generated by `hardware/fault_board/make_expected.py` on {t_start:%Y-%m-%d}. "
      "Do not edit by hand. Re-run the script after any change to `circuits/driver/`, "
      "`circuits/lib/devices.lib` or `differential/sim/`.")
    w("")
    w("Every number below comes from ngspice runs of the project's own simulation layer "
      "(`differential.sim`): the driver netlist and YAML, the onsemi 2N3904 model card, the "
      "project's tolerance draws (ADR-006) and fault models (ADR-007), and the project's "
      "instrument model (ADR-008).")
    w("")
    w("Contents: 1 Measurement conditions · 2 Healthy board · 3 Quick-look matrix · "
      "4 One table per jumper fault · 5 Board realisation versus the engine's catalog · "
      "6 Look-alikes · 7 Safety check · 8 Why gains are read at 0.20 Vpp · "
      "9 Bench-supply sensitivity · 10 Settling times · 11 Provenance")
    w("")

    # --- 1. Conditions
    w("## 1. Measurement conditions (read this first)")
    w("")
    w(f"* **Supply.** Set the bench supply so that the DMM reads **{vreg:.2f} V** at the "
      f"VREG post (fixture VREG_BENCH). Current limit **{1e3 * SUPPLY_LIMIT_A:.0f} mA**. "
      f"Every DC reading moves with the supply (section 9).")
    w("* **Generator.** Connect it at the **GEN** post: the model's `drv_src` node, the left "
      "end of RSRC_D (100 Ω). Keep it connected with its output **on** for every reading, "
      "because the model always has VIN_D in circuit.")
    w("  * **DC readings.** Set the generator to 0 V: DC function, or a sine at 0 V offset "
      "with the amplitude at minimum. This is the model's operating point (VIN_D = DC 0).")
    w(f"  * **Gain readings** (`ac`, `ac20`, `ac20k`): a sine at 1 kHz, 20 Hz or 20 kHz, "
      f"**{2 * GAIN_TEST_VPK:.2f} Vpp measured at GEN**. "
      "Gain = amplitude at the test point ÷ amplitude at GEN, both read the same way "
      "(both RMS or both peak-to-peak). Use ×10 probes. With the SCPI scope path, "
      "CH1 goes on the test point and CH2 on GEN.")
    w(f"  * **THD reading** (`thd:TP22`): a 1 kHz sine, **{2 * thd_vpk:.2f} Vpp at GEN** "
      f"({thd_vpk:.2f} V peak, the model's transient level). Use a distortion analyser, "
      "or a scope FFT with at least 60 dB of dynamic range.")
    w("* **Load.** RLOAD_EXT (10 kΩ) is fitted permanently. Connect nothing else to TP22 "
      "except the probe.")
    w("* **Instruments** (the engine's measurement model, ADR-008): DMM "
      f"±({100 * meas.DMM_PCT:.1f} % + {meas.DMM_DIGITS} counts) on a 6000-count "
      f"autoranging meter; scope amplitude ±{100 * meas.SCOPE_REL:.0f} %; THD "
      f"±{100 * meas.THD_REL:.0f} % relative.")
    w("* **Zero conventions.** Every hypothesis on this board predicts exactly 0 V DC at "
      "TP17 and TP22 (they sit behind coupling capacitors or at the generator). The model "
      "has no generator offset and no capacitor leakage. Real hardware reads a few "
      f"millivolts there. **Enter 0 for a TP17 DC reading within ±{1e3 * TP17_ZERO_V:.0f} mV "
      f"or a TP22 DC reading within ±{1e3 * TP22_ZERO_V:.0f} mV.**")
    ev17, ev22 = zero_evidence["TP17"], zero_evidence["TP22"]
    if ev17 and ev22:
        w(f"  The smallest non-zero value any catalog fault predicts there is "
          f"{1e3 * ev17[1]:.1f} mV at TP17 ({ev17[0]}, 5th percentile) and {ev22[1]:.2f} V "
          f"at TP22 ({ev22[0]}), so the conventions hide no fault information. "
          f"The {1e3 * TP22_ZERO_V:.0f} mV figure is the project's own \"DC at output\" "
          "symptom threshold (ADR-012).")
    w("* **No signal.** When a test point shows no 1 kHz sine, only noise, the gain is below "
      f"the model's floor ({meas.GAIN_FLOOR:g}, i.e. -60 dB). **Enter 0.** An automatic RMS "
      "ratio of pure noise would mislead the engine. A THD reading with no fundamental "
      f"above {1e3 * meas.THD_MIN_FUNDAMENTAL:.0f} mV peak is **entered as 100**. A "
      f"gain below 0.1 at {2 * GAIN_TEST_VPK:.2f} Vpp is repeated at {2 * thd_vpk:.2f} Vpp "
      "before it is entered (section 8).")
    w("* **Columns.** *Nominal*: every part at its netlist value, transistors at the model "
      "card's BF, fault part as fitted. The unscaled onsemi card gives hFE ≈ 119 at 10 mA "
      "(differential/sim/draws.py), near the low end of the 100–300 spread in the draws, so "
      "a real board usually reads nearer the middle of the band. Judge a reading by the "
      "accept window, not by the nominal. *5–95 %*: 5th to 95th percentile of "
      f"{n} Monte Carlo tolerance draws (resistors ±1 % or ±5 %, electrolytics ±20 % with "
      "ESR at 0.4–1.0 × tan-delta limit, 2N3904 hFE 100–300; fault parts at their own "
      "tolerance). *Accept window*: the 5–95 % band widened by the instrument tolerance. "
      "A reading inside it is consistent with the simulation. *vs healthy*: `higher` or "
      "`lower` when this reading's band, widened by instrument noise and the engine's "
      "variance floor, does not overlap the healthy band. Only these readings can tell the "
      "fault from a healthy board.")
    w("")

    main_rows = [o for o in obs if o.kind == "dc"] + [obs[j22]]
    other_rows = [o for o in obs if o not in main_rows]

    def hyp_table(fid: str, with_healthy: bool) -> list[str]:
        s = board_mc[fid]
        nom = nominal_stats[fid]
        h_nom = nominal_stats["healthy"]
        header = ["Reading"] + (["Healthy nominal"] if with_healthy else []) + \
            ["Nominal", "5–95 %", "Accept window"] + (["vs healthy"] if with_healthy else [])
        rows: list[list[str]] = []

        def one(o: ObservableSpec) -> list[str]:
            j = keys.index(o.key)
            p5, p95 = (float(x) for x in np.percentile(s.readings[:, j], [5, 95]))
            row = [row_label(o, c)]
            if with_healthy:
                row.append(fmt(o.kind, float(h_nom.readings[0, j])))
            lo_s, hi_s = fmt(o.kind, p5), fmt(o.kind, p95)
            row += [fmt(o.kind, float(nom.readings[0, j])),
                    lo_s if lo_s == hi_s else f"{lo_s} to {hi_s}", accept_window(o, p5, p95)]
            if with_healthy:
                sgn = signature[fid][o.key]
                row.append("**higher**" if sgn > 0 else "**lower**" if sgn < 0 else "")
            return row

        for o in main_rows:
            rows.append(one(o))
        p5s, p95s = np.percentile(s.supply_ma, [5, 95])
        sup_row = ["Supply current, bench display (mA)"]
        if with_healthy:
            sup_row.append(fmt("ma", float(h_nom.supply_ma[0])))
        sup_row += [fmt("ma", float(nom.supply_ma[0])), f"{p5s:.2f} to {p95s:.2f}", "—"]
        if with_healthy:
            sup_row.append("")
        rows.append(sup_row)
        blank = [""] * (len(header) - 1)
        rows.append(["*Other scope readings*", *blank])
        for o in other_rows:
            rows.append(one(o))
        return md_table(header, rows)

    # --- 2. Healthy
    w("## 2. Healthy board (all shunts on H)")
    w("")
    w("Use this table for the power-up check (README) and the demo pre-flight "
      "(procedure.md).")
    w("")
    L.extend(hyp_table("healthy", with_healthy=False))
    w("")

    # --- 3. Quick look
    w("## 3. Quick-look matrix (nominal readings)")
    w("")
    w("DC in volts at the DMM's display resolution, gains in V/V. Compare each column "
      "with the healthy row.")
    w("")
    ql_keys = [f"dc:{tp.id}" for tp in c.test_points] + ["ac:TP22", "ac20:TP22"]
    header = ["Shunt", "Catalog id", *[k.split(":")[1] for k in ql_keys[:7]],
              "Gain TP22 1 kHz", "Gain TP22 20 Hz", "Supply mA"]
    rows = []
    for fid in board_ids:
        ns = nominal_stats[fid]
        cells = [fmt(k.split(":")[0], float(ns.readings[0, keys.index(k)])) for k in ql_keys]
        rows.append([header_of_fault.get(fid, "all H"), f"`{fid}`", *cells,
                     fmt("ma", float(ns.supply_ma[0]))])
    L.extend(md_table(header, rows))
    w("")

    # --- 4. Per-fault tables
    w("## 4. One table per jumper fault")
    w("")
    w("Move one shunt from H to F, wait for the settling time (section 10), then compare. "
      "Rows marked **higher**/**lower** are the fault's signature.")
    w("")
    for bf in BOARD_FAULTS:
        fid = bf.fault_id
        w(f"### {bf.header} on F: `{fid}` ({fault_title(fid)})")
        w("")
        changed = [o.key for o in obs if signature[fid][o.key] != 0]
        w(f"Fitted: {bf.fitted}. Readings that differ from healthy: "
          + (", ".join(f"`{k}`" for k in changed) if changed else "none") + ".")
        w("")
        L.extend(hyp_table(fid, with_healthy=True))
        w("")

    # --- 5. Realisation vs catalog
    w("## 5. Board realisation versus the engine's catalog")
    w("")
    w("The engine models each fault with a range of severities (ADR-007). The board "
      "realises one of them. For every jumper position, the table gives the board's "
      "nominal readings against the engine's own catalog draws (`make_draw`, "
      f"{n} draws, severity sampled as in training). It also compares a board-level "
      "netlist, with every header modelled as a "
      f"{HEADER_CONTACT_OHMS} Ω link and the fault parts as fitted, against the catalog "
      "fault model at the same severity.")
    w("")
    rows = []
    for fid in board_ids:
        outs = outside_catalog[fid]
        bc = board_check[fid]
        rows.append([header_of_fault.get(fid, "all H"), f"`{fid}`",
                     f"{len(obs) - len(outs)} of {len(obs)}",
                     ", ".join(f"`{k}`" for k in outs) or "none",
                     f"{bc['max_dc_mv']:.2f}", f"{bc['max_gain_pct']:.2f}"])
    L.extend(md_table(["Shunt", "Catalog id", "Board nominal inside the engine's 5–95 % "
                       "(± instrument)", "Outside", "Board netlist vs model: max ΔDC (mV)",
                       "max Δgain (%)"], rows))
    w("")
    sev_rows = []
    ce_pct = math.log(RF8_OHMS / 1.0) / math.log(50.0 / 1.0)
    cb_pct = math.log(RF3_OHMS / 47e3) / math.log(470e3 / 47e3)
    sev_rows.append(["JF3 `Q501:cb_leak`", "collector-base resistance, log-uniform "
                     "47 kΩ–470 kΩ", "RF3 100 kΩ", ordinal(round(100 * cb_pct))])
    sev_rows.append(["JF8 `Q502:ce_short`", "collector-emitter resistance, log-uniform "
                     "1–50 Ω", "RF8 22 Ω", ordinal(round(100 * ce_pct))])
    esr_c502 = float(c.netlist.element("RESR_C502").numeric_value or 0.0)
    sev_rows.append(["JF5 `C502:cap_loss_90`", "0.1 × C502 (10 µF ±20 %); ESR stays at "
                     f"C502's {esr_c502:.2f} Ω × U(0.4, 1)",
                     f"CF5 10 µF, ESR up to {esr_cf5(c):.1f} Ω (same tan-delta)",
                     "capacitance: same distribution"])
    L.extend(md_table(["Fault", "Engine's severity model", "Board part",
                       "Board part's percentile in the severity range"], sev_rows))
    w("")
    w("Effect of the board part versus the catalog's typical severity (nominal parts, "
      "1 kHz gain at TP22 and DC at TP21):")
    w("")
    rows = []
    for fid, label in (("Q501:cb_leak", "catalog geometric centre 149 kΩ"),
                       ("Q502:ce_short", "catalog geometric centre 7.1 Ω"),
                       ("C502:cap_loss_90", "catalog ESR 1.86 Ω")):
        cat = catalog_nominal[fid]
        brd = nominal[fid]
        rows.append([f"`{fid}`", label,
                     f"{fmt('ac', float(cat.values[j22]))} / "
                     f"{fmt('dc', float(cat.values[keys.index('dc:TP21')]))} V",
                     f"{fmt('ac', float(brd.values[j22]))} / "
                     f"{fmt('dc', float(brd.values[keys.index('dc:TP21')]))} V"])
    L.extend(md_table(["Fault", "Catalog reference", "Catalog: gain TP22 / DC TP21",
                       "Board: gain TP22 / DC TP21"], rows))
    w("")

    # --- 6. Look-alikes
    w("## 6. Look-alikes (expected ambiguity)")
    w("")
    w("For each board fault, these are the other catalog hypotheses whose readings overlap "
      f"on **all {len(obs)}** simulated observables. The overlap test uses 5–95 % bands of "
      f"{n} catalog draws, widened by instrument noise and the engine's variance floor. "
      "No single reading separates them. They are likely to end up in one ambiguity group "
      "(ADR-011), and the agent then offers a lift test to split it. The test is "
      "conservative: a combination of readings may still separate some of them.")
    w("")
    rows = []
    for bf in BOARD_FAULTS:
        al = look_alikes[bf.fault_id]
        rows.append([bf.header, f"`{bf.fault_id}`",
                     ", ".join(f"`{a}`" for a in al) if al else "none"])
    L.extend(md_table(["Shunt", "Board fault", "Look-alikes in the catalog"], rows))
    w("")

    # --- 7. Safety
    w("## 7. Safety check (simulated DC operating points)")
    w("")
    w(f"Limits: bench-supply current limit {1e3 * SUPPLY_LIMIT_A:.0f} mA. Resistor ratings "
      "from driver.yaml, except R506, which is fitted as a 0.6 W part (same 1 kΩ 1 % "
      "value). Fault parts and fixtures are 0.25 W. Electrolytic voltage ratings from "
      f"driver.yaml; CF5 is {CF5_RATING_V:.0f} V. 2N3904 limits (onsemi 2N3903/D): "
      f"VCEO {BJT_VCEO_V:.0f} V, IC {1e3 * BJT_IC_A:.0f} mA, PD {1e3 * BJT_PD_W:.0f} mW, "
      f"VEBO {BJT_VEBO_V:.1f} V. Electrolytic polarity: + lead on the node that is more "
      "positive in the healthy board (" + ", ".join(
          f"{k}: {'first' if v == 0 else 'second'} netlist node"
          for k, v in sorted(polarity.items())) + ").")
    w("")
    rows = []
    for fid in board_ids:
        st = board_stress[fid]
        hot = max(st.resistors.items(), key=lambda kv: kv[1][2])
        q = st.bjts
        cap_min = min(st.caps.items(), key=lambda kv: kv[1][0])
        cap_max = max(st.caps.items(), key=lambda kv: abs(kv[1][0]) / kv[1][1])
        rows.append([
            header_of_fault.get(fid, "all H"), f"`{fid}`", f"{st.supply_ma:.2f}",
            f"{hot[0]} {1e3 * hot[1][0]:.0f} mW ({100 * hot[1][2]:.0f} %)",
            f"{1e3 * st.r506_w:.0f} mW ({100 * st.r506_w / 0.25:.0f} % of 0.25 W)",
            f"{1e3 * q['Q501']['p']:.1f} / {1e3 * q['Q502']['p']:.1f}",
            f"{max(q['Q501']['veb_rev'], q['Q502']['veb_rev']):.2f}",
            f"{cap_min[0]} {cap_min[1][0]:+.2f} V; {cap_max[0]} {abs(cap_max[1][0]):.1f} V of "
            f"{cap_max[1][1]:.0f} V",
            f"{max(st.header_ma.values()):.2f}",
            "within ratings" if not st.problems else "; ".join(st.problems)])
    L.extend(md_table(["Shunt", "State", "Supply mA", "Hottest resistor (% of fitted rating)",
                       "R506 vs driver.yaml rating", "Q501 / Q502 P (mW)",
                       "Largest reverse VEB (V)", "Lowest polarity margin; highest V/rating",
                       "Largest header current (mA)", "Verdict"], rows))
    w("")
    ds = dead_short
    j8 = board_stress["Q502:ce_short"]
    w(f"**Q502 collector-emitter short (JF8).** R506 and R509 limit the short-circuit "
      f"current, not the transistor. With RF8 = {RF8_OHMS:.0f} Ω the supply draws "
      f"{j8.supply_ma:.2f} mA and R506 dissipates {1e3 * j8.r506_w:.0f} mW. A dead short "
      f"(1 mΩ instead of RF8) would draw {ds.supply_ma:.2f} mA, with R506 at "
      f"{1e3 * ds.r506_w:.0f} mW ({100 * ds.r506_w / 0.25:.0f} % of the 0.25 W in "
      f"driver.yaml, {100 * ds.r506_w / BOARD_RATING_OVERRIDE_W['R506']:.0f} % of the "
      f"0.6 W part fitted). Q502's reverse base-emitter voltage would be "
      f"{ds.bjts['Q502']['veb_rev']:.2f} V against its {BJT_VEBO_V:.1f} V rating "
      f"({j8.bjts['Q502']['veb_rev']:.2f} V with RF8 fitted). "
      "So no part exceeds a rating even without the series resistor. RF8 is fitted to keep "
      "the physical fault inside the engine's modelled 1–50 Ω range, and it adds margin. "
      "R506 is fitted as a 0.6 W part because this state and the Q501 base-open state "
      "(JF2) run it at more than 70 % of the 0.25 W in driver.yaml. The switch-on surge "
      f"is small because R506 sets the current: at most "
      f"{moves['JF8']['peak_header_ma']:.1f} mA through JF8 (section 10).")
    w("")
    unsafe = [(fid, st) for fid, st in screen.items() if st.problems]
    w(f"**Catalog screen.** Every one of the {len(catalog) - 1} catalog faults was simulated "
      "at the current-hungriest end of its severity range: resistor short 0.01 Ω, "
      "capacitor short 0.1 Ω, C-E short 1 Ω, C-B leak 47 kΩ, ESR × 100. The screen used "
      "driver.yaml ratings and the same limits as above. "
      f"{len(unsafe)} would exceed a limit and are not realised on the board:")
    w("")
    rows = [[f"`{fid}`", f"{st.supply_ma:.1f}", "; ".join(st.problems)] for fid, st in unsafe]
    L.extend(md_table(["Catalog fault (worst case)", "Supply mA", "Exceeds"], rows))
    w("")
    bad_pairs = {k: st.problems for k, st in pairs.items() if st.problems}
    top_i = max(pairs, key=lambda k: pairs[k].supply_ma)
    top_r = max(pairs, key=lambda k: pairs[k].r506_w)
    top_v = max(pairs, key=lambda k: max(q["veb_rev"] for q in pairs[k].bjts.values()))
    w(f"**Two shunts on F at once.** All {len(pairs)} two-header combinations were also "
      "simulated. This covers a setter who forgets to return a shunt, and a deliberate "
      "double fault used to show the engine's \"unmodeled\" hypothesis. "
      + ("Every combination stays within the limits above. "
         if not bad_pairs else f"**{len(bad_pairs)} "
         f"{'exceeds' if len(bad_pairs) == 1 else 'exceed'} a limit, so never set it:** "
         + "; ".join(f"{k}: {', '.join(v)}" for k, v in bad_pairs.items()) + ". ")
      + f"Highest supply current {pairs[top_i].supply_ma:.2f} mA ({top_i}). Highest R506 "
      f"dissipation {1e3 * pairs[top_r].r506_w:.0f} mW ({top_r}). Largest reverse VEB "
      f"{max(q['veb_rev'] for q in pairs[top_v].bjts.values()):.2f} V ({top_v}).")
    w("")

    # --- 8. Test level
    w("## 8. Why gains are read at 0.20 Vpp")
    w("")
    w("The engine's gain observables are small-signal AC analyses. A bench reading uses a "
      "finite amplitude, so a state that is strongly non-linear reads a different gain. For "
      f"every board state and each of the {len(gain_obs)} gain readings (1 kHz at TP17–TP22, "
      "20 Hz and 20 kHz at TP22), a transient + Fourier analysis at each bench level gives "
      "the fundamental gain. The table shows the reading whose ratio to the small-signal "
      "gain is furthest from 1. Readings below the 0.001 floor are skipped.")
    w("")
    lab_g, lab_t = f"{2 * GAIN_TEST_VPK:.2f} Vpp", f"{2 * thd_vpk:.2f} Vpp"

    def worst(ratios: dict[str, float]) -> tuple[str, float] | None:
        if not ratios:
            return None
        k = max(ratios, key=lambda key: abs(ratios[key] - 1.0))
        return k, ratios[k]

    rows = []
    overall: dict[str, tuple[float, str, str]] = {}
    for fid in board_ids:
        cells = []
        for lab in (lab_g, lab_t):
            wv = worst(level_check[fid][lab])
            cells.append("no signal anywhere" if wv is None else f"{wv[1]:.4f} (`{wv[0]}`)")
            if wv is not None and abs(wv[1] - 1) > abs(overall.get(lab, (1.0, "", ""))[0] - 1):
                overall[lab] = (wv[1], fid, wv[0])
        rows.append([header_of_fault.get(fid, "all H"), f"`{fid}`", *cells])
    L.extend(md_table(["Shunt", "State", f"Worst ratio at {lab_g}", f"Worst ratio at {lab_t}"],
                      rows))
    w("")
    wg, wt = overall[lab_g], overall[lab_t]
    w(f"At {lab_g} the largest deviation is {100 * abs(1 - wg[0]):.1f} % (`{wg[1]}`, "
      f"`{wg[2]}`), inside the scope's ±{100 * meas.SCOPE_REL:.0f} %. At {lab_t} it would "
      f"be {100 * abs(1 - wt[0]):.1f} % (`{wt[1]}`, `{wt[2]}`). Use {lab_t} for the THD "
      "reading, which the model computes at that level.")
    small = [(fid, o.key, float(nominal[fid].values[keys.index(o.key)]))
             for fid in board_ids for o in gain_obs
             if meas.GAIN_FLOOR <= float(nominal[fid].values[keys.index(o.key)]) < 0.1]
    if small:
        parts = [f"`{k}` in `{fid}` (small-signal {sig3(g)}; {lab_t} ratio "
                 f"{level_check[fid][lab_t][k]:.4f})" for fid, k, g in small]
        w("")
        w("**Small outputs.** Some gains are real but tiny: " + "; ".join(parts) + ". At "
          f"{lab_g} they are only millivolts. If a reading at {lab_g} gives a gain below "
          f"0.1, repeat it at {lab_t} and divide by the {lab_t} at GEN. The ratios show "
          "these states are linear at that level. Enter 0 only if no sine is visible even "
          f"at {lab_t}.")
    w("")

    # --- 9. Supply sensitivity
    w("## 9. Bench-supply sensitivity (healthy, nominal parts)")
    w("")
    w(f"Change of each reading per +{SUPPLY_STEP_V:.2f} V at VREG (central difference "
      f"around {vreg:.2f} V):")
    w("")
    rows = []
    for o in obs:
        if o.key not in sensitivity:
            continue
        s = sensitivity[o.key] * SUPPLY_STEP_V
        unit = "V" if o.kind == "dc" else "V/V"
        rows.append([row_label(o, c), f"{s:+.4f} {unit}"])
    L.extend(md_table(["Reading", f"Change per +{SUPPLY_STEP_V:.2f} V"], rows))
    w("")

    # --- 10. Settling
    w("## 10. Settling times")
    w("")
    w("\"Settled\" means every test point is within the DMM accuracy of its final value, "
      "and never tighter than 10 mV. The simulations use the bench supply with its "
      f"{1e3 * SUPPLY_LIMIT_A:.0f} mA current limit and the generator at 0 V. They also "
      "track the voltage across every electrolytic (+ lead minus − lead) to check "
      "polarity during the transients.")
    w("")
    w(f"* **Power-up** (supply ramped in 1 ms): the supply is in current limit for "
      f"{powerup['limit_ms']:.0f} ms while C504 charges, so its CC indicator may flash. "
      f"All test points are settled after {powerup['settle_s']:.1f} s. Final supply "
      f"current {powerup['final_ma']:.2f} mA. Lowest electrolytic polarity margin "
      f"{powerup['min_cap_margin_v']:+.2f} V ({powerup['worst_cap']}).")
    w("* **Moving one shunt** H→F at t = 1.5 s and back F→H at t = 22 s (0.5 s out of both "
      "positions each time):")
    w("")
    rows = []
    for h in HEADERS:
        mv = moves[h]
        rows.append([h, f"`{BOARD_FAULTS[HEADERS.index(h)].fault_id}`",
                     f"{mv['to_fault_s']:.1f}", f"{mv['to_healthy_s']:.1f}",
                     f"{mv['peak_header_ma']:.1f}", f"{mv['peak_supply_ma']:.1f}",
                     f"{mv['limit_ms']:.0f}", f"{mv['tp22_extreme_v']:+.2f}",
                     f"{mv['min_cap_margin_v']:+.2f} ({mv['worst_cap']})"])
    L.extend(md_table(["Shunt", "Fault", "Settle after H→F (s)", "Settle after F→H (s)",
                       "Peak header current (mA)", "Peak supply current (mA)",
                       "Time in current limit (ms)", "Largest TP22 excursion (V)",
                       "Lowest electrolytic polarity margin (V)"], rows))
    w("")
    worst_settle = max(max(mv["to_fault_s"], mv["to_healthy_s"]) for mv in moves.values())
    worst_margin = min(min(mv["min_cap_margin_v"] for mv in moves.values()),
                       powerup["min_cap_margin_v"])
    w(f"The worst settling time after a move is {worst_settle:.1f} s, counted from when the "
      "shunt lands. TP22's excursion decays through C503 into R508 and RLOAD_EXT. "
      + (f"No electrolytic is reverse-biased at any time (lowest margin {worst_margin:+.2f} V)."
         if worst_margin > REVERSE_POLARITY_FLAG_V else
         f"**Warning:** an electrolytic reaches {worst_margin:+.2f} V (reverse)."))
    w("")

    # --- 11. Provenance
    w("## 11. Provenance")
    w("")
    n_fail = len(FAILURES)
    prov = [
        ["Circuit", f"`{CIRCUIT_ID}`: circuits/driver/driver.cir + driver.yaml"],
        ["Netlist SHA-256 (healthy, as simulated)", f"`{net_hash}`"],
        ["Device library SHA-256", f"`{lib_hash}`"],
        ["Tolerance spec SHA-256 (differential/sim/draws.py)", f"`{tol_hash}`"],
        ["Matches data/sim/manifest.json", manifest_match],
        ["ngspice", ngspice_version()],
        ["git HEAD", f"`{head}` (uncommitted working-tree changes are not reflected in "
                     "this hash; the SHA-256 values above are authoritative)"],
        ["Monte Carlo seeds", f"`SeedSequence([{BASE_SEED}, {circuit_index(CIRCUIT_ID)}, "
                              f"{SPLIT_INDEX[SPLIT]}, hypothesis index, draw])` (split "
                              f"\"{SPLIT}\"); board fault parts add a final word "
                              f"{BOARD_SEED_WORD}"],
        ["Draws", f"{n} per hypothesis; {total_draws} Monte Carlo draws in total "
                  f"({len(board_ids)} board states + {len(catalog)} catalog hypotheses)"],
        ["Simulation failures", f"{n_fail}" + (" (listed in expected_readings.json)"
                                              if n_fail else " (none)")],
    ]
    L.extend(md_table(["Item", "Value"], prov))
    w("")
    args.out.write_text("\n".join(L) + "\n")

    # JSON twin for software (e.g. automatic comparison in the demo)
    def stats_json(s: HypStats, nom: HypStats) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for j, o in enumerate(obs):
            p5, p95 = np.percentile(s.readings[:, j], [5, 95])
            out[o.key] = {"nominal": float(nom.readings[0, j]), "p5": float(p5),
                          "p95": float(p95)}
        p5, p95 = np.percentile(s.supply_ma, [5, 95])
        out["supply_ma"] = {"nominal": float(nom.supply_ma[0]), "p5": float(p5),
                            "p95": float(p95)}
        return out

    js: dict[str, Any] = {
        "generated": f"{t_start:%Y-%m-%d}",
        "generator": "hardware/fault_board/make_expected.py",
        "circuit": CIRCUIT_ID,
        "netlist_sha256": net_hash,
        "draws_per_hypothesis": n,
        "conditions": {"vreg_v": vreg, "supply_limit_a": SUPPLY_LIMIT_A,
                       "gain_test_vpp": 2 * GAIN_TEST_VPK, "thd_test_vpp": 2 * thd_vpk,
                       "tp17_zero_v": TP17_ZERO_V, "tp22_zero_v": TP22_ZERO_V,
                       "gain_floor": meas.GAIN_FLOOR, "thd_no_signal": meas.THD_NO_SIGNAL},
        "states": {},
        "look_alikes": look_alikes,
        "outside_catalog_band": outside_catalog,
        "board_netlist_check": board_check,
        "safety": {fid: {"supply_ma": st.supply_ma, "r506_w": st.r506_w,
                         "problems": st.problems,
                         "bjts": st.bjts, "header_ma": st.header_ma}
                   for fid, st in board_stress.items()},
        "safety_jf8_dead_short": {"supply_ma": ds.supply_ma, "r506_w": ds.r506_w,
                                  "q502_veb_rev": ds.bjts["Q502"]["veb_rev"]},
        "catalog_screen_exceeds": {fid: st.problems for fid, st in unsafe},
        "double_fault_screen": {k: {"supply_ma": st.supply_ma, "r506_w": st.r506_w,
                                    "problems": st.problems} for k, st in pairs.items()},
        "test_level": level_check,
        "supply_sensitivity_per_volt": sensitivity,
        "settling": {"power_up": powerup,
                     "moves": moves},
        "zero_evidence": zero_evidence,
        "failures": FAILURES,
    }
    for fid in board_ids:
        js["states"][fid] = {
            "header": header_of_fault.get(fid),
            "signature": {k: v for k, v in signature[fid].items() if v},
            "board": stats_json(board_mc[fid], nominal_stats[fid]),
            "catalog": stats_json(cat_mc[fid], nominal_stats[fid]),
        }
    args.out.with_suffix(".json").write_text(
        json.dumps(_finite(js), indent=1, sort_keys=True, allow_nan=False) + "\n")
    log(f"wrote {args.out} and {args.out.with_suffix('.json')} "
        f"({(dt.datetime.now() - t_start).total_seconds():.0f} s, {n_fail} failures)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
