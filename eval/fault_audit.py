"""Fault-signature audit: sampled catalogued faults against an independent solver (ADR-040).

Why: the engine learns each fault's signature from ngspice. The hand calculations
(`tools/hand_calcs.py`) check healthy bias points only, so a fault inserted on the
wrong node, a model that misbehaves outside its normal regime, or ngspice settling on
a wrong operating point would go unnoticed. This audit re-derives the readings of a
random sample of faulted units without ngspice and without the simulator's netlist
builder, and reports how often the two agree.

What is independent of the simulator:
  * the circuit is read from the healthy block netlist (``circuits/<block>/<block>.cir``)
    and each fault is inserted by this file from its catalog definition (open = 1 GOhm,
    capacitor open = 1 fF, short = the drawn resistance across the part's terminals,
    leakage = the drawn resistance from collector to base, and so on), not by
    ``differential.sim.builder``;
  * the operating point and the small-signal responses are solved here (nodal analysis,
    Newton iteration with source stepping, numpy), not by ngspice;
  * device behaviour comes from the published equations, written out here: the SPICE
    Gummel-Poon equations with the onsemi 2N3904 card, the Shockley equation with the
    Diodes Inc. diode and zener cards, Koren's triode equation, and the op-amp
    macro-model's equations as documented in ``circuits/lib/devices.lib``.
What it does not test: whether those equations describe real parts (the hand
calculations and the hardware target T7 address that), THD, and the meter's loading.

Sample: faults of the five blocks and of the channel strip, stratified by circuit and
fault type (open, short, drift, degradation, leakage, dead): up to two faults of each
type per circuit, drawn with a fixed seed. (The channel strip was added after the first
comparison run on the blocks, under the same rule.) For each fault, three of its training draws are rebuilt from their seeds
(two as-new, one aged), so both solvers see the same part values and fault severity.

Agreement rule (fixed before the first comparison run):
  * DC (unloaded, every test point): |ngspice - solver| <= 2 x the bench meter's
    accuracy at the solver's value (0.5 % of reading + 2 counts on the auto range);
  * AC gain (20 Hz, 1 kHz, 20 kHz) and 120 Hz hum: within 0.5 dB (about 2 x the scope's
    3 %), after clamping both values at the instrument floor (gain 1e-3, hum 100 uV),
    because readings below the floor cannot be told apart on the bench;
  * a fault agrees when every reading of all three draws agrees.
The result is the number of agreeing faults with an exact 95 % interval; every
disagreement is listed with its readings.

Writes results/fault_audit.json, docs/fault_audit.md and metrics.json "fault_audit".
Run: python -m eval.fault_audit
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.circuits.model import CircuitSpec
from differential.config import REPO_ROOT, RESULTS_DIR
from differential.sim.faults import HEALTHY_FAULT, MODE_TYPE, Fault, fault_catalog
from differential.sim.measurement import DMM_PCT, DMM_RANGES, GAIN_FLOOR, HUM_FLOOR
from differential.sim.montecarlo import Job, is_aged, make_draw, run_job

VT = 0.025852  # thermal voltage at 27 C
GMIN = 1e-12  # node-to-ground conductance so a floating node stays defined
OPEN_OHMS = 1e9  # catalog definition of an open resistor, lead or junction
OPEN_FARADS = 1e-15  # catalog definition of an open capacitor
EXP_CAP = 40.0  # exponent above which exp() continues linearly (no overflow)
SEED = 20260929
PER_TYPE = 2
AUDITED = [*BLOCK_IDS, COMPOSITE_ID]
DC_FACTOR = 2.0
AC_DB = 0.5

# Published device parameters (verbatim from the cards cited in circuits/lib/devices.lib).
Q2N3904 = dict(IS=1.26532e-10, BF=206.302, NF=1.5, VAF=1000.0, IKF=0.0272221, ISE=2.30771e-09,
               NE=3.31052, BR=20.6302, NR=2.89609, VAR=9.39809, IKR=0.272221, ISC=2.30771e-09,
               NC=1.9876, RB=5.8376, RC=2.65711, CJE=4.64214e-12, VJE=0.4, MJE=0.256227,
               TF=4.19578e-10, XTF=0.906167, VTF=8.75418, ITF=0.0105823, CJC=3.76961e-12,
               VJC=0.4, MJC=0.238109, XCJC=0.8, FC=0.512134, TR=6.82023e-08)
DIODES = {"D1N4148": dict(IS=222e-12, N=1.65, RS=68.6e-3, CJO=4e-12, VJ=1.0, M=0.333, TT=5.76e-9),
          "DF_1N4745A": dict(IS=25.7e-12, N=1.10, RS=0.620, CJO=74.4e-12, VJ=1.0, M=0.330,
                             TT=50.1e-9),
          "DR_1N4745A": dict(IS=5.15e-15, N=1.80, RS=0.897, CJO=0.0, VJ=1.0, M=0.5, TT=0.0),
          "DX_KOREN": dict(IS=1e-9, N=1.0, RS=1.0, CJO=10e-12, VJ=1.0, M=0.5, TT=1e-9)}
DIODE_FC = 0.5  # SPICE default forward-bias depletion coefficient
KOREN = dict(KP=600.0, KVB=300.0, EX=1.4, RGI=2000.0)  # 12AX7; MU and KG1 from parameter nodes
PARAM_PREFIXES = ("VPVZ_", "VPV_", "VMU_", "VKG_", "VPGBW_", "VPDEAD_", "VPRAIL_", "VCRES_")


def lexp(x: float) -> float:
    return math.exp(x) if x < EXP_CAP else math.exp(EXP_CAP) * (1.0 + x - EXP_CAP)


def qdep(v: float, cjo: float, vj: float, m: float, fc: float) -> float:
    """SPICE depletion charge of a junction (linearised above fc * vj)."""
    if cjo == 0.0:
        return 0.0
    if v < fc * vj:
        return float(cjo * vj * (1.0 - (1.0 - v / vj) ** (1.0 - m)) / (1.0 - m))
    f1 = float(vj * (1.0 - (1.0 - fc) ** (1.0 - m)) / (1.0 - m))
    f2 = float((1.0 - fc) ** (1.0 + m))
    f3 = 1.0 - fc * (1.0 + m)
    return float(cjo * (f1 + (f3 * (v - fc * vj) + m / (2.0 * vj) * (v * v - (fc * vj) ** 2)) / f2))


def spice_num(tok: str) -> float:
    m = re.match(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)(meg|[fpnumkgt])?", tok.lower())
    if not m:
        raise ValueError(tok)
    mult = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6,
            "g": 1e9, "t": 1e12}
    return float(m.group(1)) * mult.get(m.group(2) or "", 1.0)


# ------------------------------------------------------------------ netlist
@dataclass
class El:
    name: str
    kind: str  # R C L V I BV BI D Q X
    nodes: list[str]
    value: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)


def parse_netlist(text: str) -> list[El]:
    lines: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("*"):
            continue
        if s.lower().startswith(".control"):
            break
        if s.startswith("+"):
            lines[-1] += " " + s[1:]
            continue
        if s.startswith("."):
            continue
        lines.append(s)
    out = []
    for s in lines:
        tok = s.split()
        name, t = tok[0], tok[0][0].upper()
        if t in "RCL":
            out.append(El(name, t, tok[1:3], spice_num(tok[3])))
        elif t in "VI":
            dc, rest, i = 0.0, tok[3:], 0
            while i < len(rest):
                u = rest[i].upper()
                if u == "DC":
                    dc, i = spice_num(rest[i + 1]), i + 2
                elif u == "AC":
                    i += 2
                elif u.startswith("SIN"):
                    break
                else:
                    dc, i = spice_num(rest[i]), i + 1
            out.append(El(name, t, tok[1:3], dc))
        elif t == "B":
            typ, expr = s.split("=", 1)
            out.append(El(name, "B" + typ.split()[-1].upper(), tok[1:3], 0.0,
                          {"expr": expr.strip()}))
        elif t == "D":
            out.append(El(name, "D", tok[1:3], 0.0, {"model": tok[3]}))
        elif t == "Q":
            out.append(El(name, "Q", tok[1:4], 0.0, {"model": tok[4], "BF": Q2N3904["BF"]}))
        elif t == "X":
            out.append(El(name, "X", tok[1:-1], 0.0, {"sub": tok[-1]}))
        else:
            raise ValueError(f"unsupported element {s}")
    return out


def expand(els: list[El]) -> list[El]:
    """Replace subcircuit instances by their primitive elements (internal nodes prefixed)."""
    out: list[El] = []
    for el in els:
        if el.kind != "X":
            out.append(el)
            continue
        p = el.name + ":"
        sub, n = el.params["sub"], el.nodes
        if sub == "ZENER_1N4745A":  # A K PVZ
            a, k, pvz = n
            out += [El(p + "DF", "D", [a, k], 0.0, {"model": "DF_1N4745A"}),
                    El(p + "DR", "D", [p + "n3", a], 0.0, {"model": "DR_1N4745A"}),
                    El(p + "BVZ", "BV", [k, p + "n3"], 0.0, {"fn": "copy", "node": pvz})]
        elif sub == "TRIODE_KOREN":  # P G K PV PMU PKG
            pl, g, k, pv, pmu, pkg = n
            out += [El(p + "Bp", "TRIODE", [pl, k], 0.0, {"g": g, "pv": pv, "pmu": pmu, "pkg": pkg}),
                    El(p + "RGI", "R", [g, p + "gg"], KOREN["RGI"]),
                    El(p + "D3", "D", [p + "gg", k], 0.0, {"model": "DX_KOREN"}),
                    El(p + "Cgk", "C", [g, k], 2.3e-12), El(p + "Cgp", "C", [g, pl], 2.4e-12),
                    El(p + "Cpk", "C", [pl, k], 0.9e-12)]
        elif sub == "OPAMP_BEH":  # INP INM OUT VCC VEE PGBW PDEAD PRAIL
            inp, inm, o, vcc, vee, pgbw, pdead, prail = n
            r1 = 2e5 / (6.2832e-3 * 3)
            out += [El(p + "Rin", "R", [inp, inm], 10e6),
                    El(p + "Bmid", "BV", [p + "mid", "0"], 0.0, {"fn": "mid", "vcc": vcc, "vee": vee}),
                    El(p + "Bgm", "GM", [p + "mid", p + "n1"], 0.0,
                       {"inp": inp, "inm": inm, "pgbw": pgbw}),
                    El(p + "R1", "R", [p + "n1", p + "mid"], r1),
                    El(p + "C1", "C", [p + "n1", p + "mid"], 1e-9),
                    El(p + "Bout", "BV", [p + "outi", "0"], 0.0,
                       {"fn": "opout", "n1": p + "n1", "mid": p + "mid", "vcc": vcc, "vee": vee,
                        "pdead": pdead, "prail": prail}),
                    El(p + "Rout", "R", [p + "outi", o], 50.0),
                    El(p + "Iq", "I", [vcc, vee], 2.5e-3)]
        else:
            raise ValueError(sub)
    return out


# ------------------------------------------------------------------ faults
def terminals(circuit: CircuitSpec, ref: str, els: dict[str, El]) -> tuple[str, str]:
    """The two outer terminals of a two-terminal part (an electrolytic is C in series with
    its ESR)."""
    comp = circuit.component(ref)
    main = els[comp.main_element]
    if comp.kind == "electrolytic":
        esr = els[comp.elements["esr"]]
        return main.nodes[0], esr.nodes[1] if esr.nodes[0] == main.nodes[1] else esr.nodes[0]
    return main.nodes[0], main.nodes[1]


def apply_draw(circuit: CircuitSpec, els: list[El], fault: Fault, d: Any) -> list[El]:
    """Set every element to the unit's drawn value, then insert the fault from its
    definition. The draw supplies values and severities only; the fault's topology is
    built here."""
    by = {e.name: e for e in els}
    for name, v in d.alters.items():
        if name in by:
            by[name].value = float(v)
    for (model, param), v in d.altermods.items():
        for comp in circuit.components:
            if comp.kind == "bjt" and model == f"{comp.model}_{comp.ref}".upper() and param == "bf":
                by[comp.main_element].params["BF"] = float(v)
    out = list(els)
    if fault.is_healthy:
        return sync_reservoirs(circuit, out)
    comp = circuit.component(fault.ref)
    mode, main = fault.mode, by[comp.main_element]
    extra = f"AUDIT_{comp.ref}"
    if comp.kind == "resistor":
        if mode == "open":
            main.value = OPEN_OHMS
        # short and drift: the drawn value already carries the fault's resistance
    elif comp.kind in ("film_cap", "electrolytic"):
        if mode == "open":
            main.value = OPEN_FARADS
        elif mode == "short":
            a, b = terminals(circuit, comp.ref, by)
            out.append(El(extra, "R", [a, b], float(d.severity["short_ohms"])))
        # cap_loss and high_esr: drawn values of the capacitance or the ESR
    elif comp.kind == "potentiometer":
        if mode == "wiper_open":
            by[comp.elements["wiper"]].value = OPEN_OHMS
        else:
            side = "upper" if d.severity.get("track_open_upper", 0.0) == 1.0 else "lower"
            by[comp.elements[side]].value = OPEN_OHMS
    elif comp.kind in ("diode", "zener"):
        a, k = main.nodes[0], main.nodes[1]
        if mode == "open":
            out = [e for e in out if e is not main]
            out.append(El(extra, "R", [a, k], OPEN_OHMS))
        else:
            out.append(El(extra, "R", [a, k], float(d.severity["short_ohms"])))
    elif comp.kind == "bjt":
        c, b, e = main.nodes
        if mode == "ce_short":
            out.append(El(extra, "R", [c, e], float(d.severity["short_ohms"])))
        elif mode == "cb_leak":
            out.append(El(extra, "R", [c, b], float(d.severity["leak_ohms"])))
        elif mode == "be_open":
            main.nodes = [c, extra + "_b", e]
            out.append(El(extra, "R", [b, extra + "_b"], OPEN_OHMS))
        # beta_low: the drawn BF already carries the fault
    # triode and op-amp faults act through their parameter nodes (drawn values)
    return sync_reservoirs(circuit, out)


def sync_reservoirs(circuit: CircuitSpec, els: list[El]) -> list[El]:
    """The rectifier model reads its reservoir capacitance from a parameter source."""
    if circuit.hum is None:
        return els
    by = {e.name: e for e in els}
    for rect in circuit.hum.rectifiers:
        by[rect.cres_source].value = by[circuit.component(rect.reservoir).main_element].value
    return els


# ------------------------------------------------------------------ solver
class Solver:
    """Modified nodal analysis: node voltages plus the currents of voltage-type branches."""

    def __init__(self, els: list[El], signal_source: str | None, hum_source: str | None) -> None:
        self.els = expand(els)
        nodes: dict[str, int] = {}
        for e in self.els:
            for n in self._nodes(e):
                if n != "0" and n not in nodes:
                    nodes[n] = len(nodes)
        self.node = nodes
        self.nn = len(nodes)
        self.branch: dict[str, int] = {}
        for e in self.els:
            if e.kind in ("V", "BV", "L"):
                self.branch[e.name] = self.nn + len(self.branch)
        self.n = self.nn + len(self.branch)
        self.signal, self.hum = signal_source, hum_source
        junction: set[str] = set()
        for e in self.els:
            if e.kind == "D":
                junction.update([e.name + ":a" if DIODES[e.params["model"]]["RS"] > 0 else e.nodes[0],
                                 e.nodes[1]])
            elif e.kind == "Q":
                junction.update([e.name + ":c", e.name + ":b", e.nodes[2]])
            elif e.kind == "TRIODE":
                junction.update([*e.nodes, e.params["g"]])
        self.junction = np.array(sorted(self.node[n] for n in junction if n != "0"), dtype=int)
        for e in self.els:  # rectifier expressions
            if e.kind == "BV" and "expr" in e.params and "max(" in e.params["expr"]:
                m = re.match(r"max\(V\((\w+)\) - I\((\w+)\)\*\(([\d.]+) \+ 1/\(240\*V\((\w+)\)\)\)",
                             e.params["expr"])
                assert m, e.params["expr"]
                e.params.update(fn="rect", pk=m.group(1), sense=m.group(2), rw=float(m.group(3)),
                                cres=m.group(4))
            if e.kind == "BI":
                m = re.match(r"2\*V\((\w+)\)\*I\((\w+)\)", e.params["expr"])
                assert m, e.params["expr"]
                e.params.update(ref=m.group(1), sense=m.group(2))

    @staticmethod
    def _nodes(e: El) -> list[str]:
        ns = list(e.nodes)
        if e.kind == "D" and DIODES[e.params["model"]]["RS"] > 0:
            ns.append(e.name + ":a")
        if e.kind == "Q":
            ns += [e.name + ":c", e.name + ":b"]
        for key in ("g", "pv", "pmu", "pkg", "node", "vcc", "vee", "n1", "mid", "pdead", "prail",
                    "inp", "inm", "pgbw"):
            if key in e.params and isinstance(e.params[key], str):
                ns.append(e.params[key])
        return ns

    def v(self, x: np.ndarray, node: str) -> float:
        return 0.0 if node == "0" else float(x[self.node[node]])

    def _add(self, F: np.ndarray, node: str, i: float) -> None:
        if node != "0":
            F[self.node[node]] += i

    def residual(self, x: np.ndarray, lam: float = 1.0) -> np.ndarray:
        """Sum of currents leaving each node; branch rows hold the branch equations."""
        F = np.zeros(self.n)
        F[: self.nn] += GMIN * x[: self.nn]
        v = self.v
        for e in self.els:
            k = e.kind
            if k == "R":
                a, b = e.nodes
                i = (v(x, a) - v(x, b)) / e.value
                self._add(F, a, i)
                self._add(F, b, -i)
            elif k == "C":
                continue
            elif k in ("V", "L", "BV"):
                a, b = e.nodes
                j = self.branch[e.name]
                self._add(F, a, x[j])
                self._add(F, b, -x[j])
                if k == "L":
                    target = 0.0
                elif k == "V":
                    target = e.value * (1.0 if e.name.startswith(PARAM_PREFIXES) else lam)
                else:
                    target = self._bv(x, e)
                F[j] = v(x, a) - v(x, b) - target
            elif k == "I":
                a, b = e.nodes
                self._add(F, a, lam * e.value)
                self._add(F, b, -lam * e.value)
            elif k == "BI":
                a, b = e.nodes
                i = 2.0 * v(x, e.params["ref"]) * x[self.branch[e.params["sense"]]]
                self._add(F, a, i)
                self._add(F, b, -i)
            elif k == "GM":
                a, b = e.nodes
                i = 6.2832e-3 * v(x, e.params["pgbw"]) * (v(x, e.params["inp"]) - v(x, e.params["inm"]))
                self._add(F, a, i)
                self._add(F, b, -i)
            elif k == "D":
                self._diode(F, x, e)
            elif k == "Q":
                self._bjt(F, x, e)
            elif k == "TRIODE":
                pl, kk = e.nodes
                vpk = v(x, pl) - v(x, kk)
                vgk = v(x, e.params["g"]) - v(x, kk)
                mu, kg1 = v(x, e.params["pmu"]), v(x, e.params["pkg"])
                arg = KOREN["KP"] * (1.0 / mu + vgk / math.sqrt(KOREN["KVB"] + vpk * vpk))
                e1 = (vpk / KOREN["KP"]) * float(np.logaddexp(0.0, arg))
                ip = v(x, e.params["pv"]) * 2.0 * max(e1, 0.0) ** KOREN["EX"] / kg1
                self._add(F, pl, ip)
                self._add(F, kk, -ip)
        return F

    def _bv(self, x: np.ndarray, e: El) -> float:
        v, p = self.v, e.params
        fn = p["fn"]
        if fn == "copy":
            return v(x, p["node"])
        if fn == "mid":
            return 0.5 * (v(x, p["vcc"]) + v(x, p["vee"]))
        if fn == "opout":
            vcc, vee, mid = v(x, p["vcc"]), v(x, p["vee"]), v(x, p["mid"])
            h = 0.5 * (vcc - vee) - 1.5
            live = mid + h * math.tanh((v(x, p["n1"]) - mid) / h)
            rail = v(x, p["prail"]) * (vcc - 1.5) + (1.0 - v(x, p["prail"])) * (vee + 1.5)
            dead = v(x, p["pdead"])
            return (1.0 - dead) * live + dead * rail
        if fn == "rect":
            vpk, i = v(x, p["pk"]), x[self.branch[p["sense"]]]
            c = max(v(x, p["cres"]), 1e-18)
            return float(max(vpk - i * (p["rw"] + 1.0 / (240.0 * c)), 0.6366 * vpk - i * p["rw"]))
        raise ValueError(fn)

    def _diode(self, F: np.ndarray, x: np.ndarray, e: El) -> None:
        m = DIODES[e.params["model"]]
        a, k = e.nodes
        ai = e.name + ":a" if m["RS"] > 0 else a
        if m["RS"] > 0:
            ir = (self.v(x, a) - self.v(x, ai)) / m["RS"]
            self._add(F, a, ir)
            self._add(F, ai, -ir)
        vd = self.v(x, ai) - self.v(x, k)
        i = m["IS"] * (lexp(vd / (m["N"] * VT)) - 1.0)
        self._add(F, ai, i)
        self._add(F, k, -i)

    def _bjt(self, F: np.ndarray, x: np.ndarray, e: El) -> None:
        p = Q2N3904
        c, b, em = e.nodes
        ci, bi = e.name + ":c", e.name + ":b"
        for outer, inner, r in ((c, ci, p["RC"]), (b, bi, p["RB"])):
            i = (self.v(x, outer) - self.v(x, inner)) / r
            self._add(F, outer, i)
            self._add(F, inner, -i)
        vbe = self.v(x, bi) - self.v(x, em)
        vbc = self.v(x, bi) - self.v(x, ci)
        cbe = p["IS"] * (lexp(vbe / (p["NF"] * VT)) - 1.0)
        cbc = p["IS"] * (lexp(vbc / (p["NR"] * VT)) - 1.0)
        cben = p["ISE"] * (lexp(vbe / (p["NE"] * VT)) - 1.0)
        cbcn = p["ISC"] * (lexp(vbc / (p["NC"] * VT)) - 1.0)
        q1 = 1.0 / (1.0 - vbc / p["VAF"] - vbe / p["VAR"])
        q2 = cbe / p["IKF"] + cbc / p["IKR"]
        qb = q1 * (1.0 + math.sqrt(max(1.0 + 4.0 * q2, 0.0))) / 2.0
        ic = (cbe - cbc) / qb - cbc / p["BR"] - cbcn
        ib = cbe / e.params["BF"] + cben + cbc / p["BR"] + cbcn
        self._add(F, ci, ic)
        self._add(F, bi, ib)
        self._add(F, em, -(ic + ib))

    def jacobian(self, x: np.ndarray, lam: float, F0: np.ndarray) -> np.ndarray:
        J = np.zeros((self.n, self.n))
        for j in range(self.n):
            h = 1e-7 * max(1.0, abs(x[j]))
            xp = x.copy()
            xp[j] += h
            J[:, j] = (self.residual(xp, lam) - F0) / h
        return J

    def newton(self, x: np.ndarray, lam: float, iters: int = 300) -> tuple[np.ndarray, bool]:
        for _ in range(iters):
            F = self.residual(x, lam)
            J = self.jacobian(x, lam, F)
            try:
                dx = np.linalg.solve(J, -F)
            except np.linalg.LinAlgError:
                dx = np.linalg.lstsq(J, -F, rcond=None)[0]
            # limit the step on junction nodes only (exponential devices); linear internal
            # nodes such as an op-amp's gain node may need to move by megavolts
            big = float(np.max(np.abs(dx[self.junction]))) if len(self.junction) else 0.0
            step = min(1.0, 10.0 / big) if big > 0 else 1.0
            big = float(np.max(np.abs(dx[: self.nn]))) if self.nn else 0.0
            f0 = float(np.linalg.norm(F))
            while True:
                xn = x + step * dx
                fn = float(np.linalg.norm(self.residual(xn, lam)))
                if fn <= f0 or step < 1e-6:
                    break
                step *= 0.5
            x = xn
            if step * big < 1e-9 and fn < 1e-9:
                return x, True
        return x, float(np.linalg.norm(self.residual(x, lam))) < 1e-6

    def operating_point(self) -> np.ndarray:
        x = np.zeros(self.n)
        for e in self.els:  # parameter nodes start at their values (they are never stepped)
            if e.kind == "V" and e.name.startswith(PARAM_PREFIXES) and e.nodes[1] == "0":
                x[self.node[e.nodes[0]]] = e.value
        ok = False
        for lam in (0.02, 0.05, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0):
            x, ok = self.newton(x, lam)
        if not ok:
            raise RuntimeError("operating point did not converge")
        return x

    def charges(self, x: np.ndarray) -> np.ndarray:
        """Charge stored in the junctions at each node: the depletion and diffusion
        capacitances of the published cards (SPICE equations). Capacitors are stamped
        exactly in ``ac``."""
        Q = np.zeros(self.n)
        v = self.v

        def put(a: str, b: str, q: float) -> None:
            self._add(Q, a, q)
            self._add(Q, b, -q)

        for e in self.els:
            if e.kind == "D":
                m = DIODES[e.params["model"]]
                a = e.name + ":a" if m["RS"] > 0 else e.nodes[0]
                vd = v(x, a) - v(x, e.nodes[1])
                i = m["IS"] * (lexp(vd / (m["N"] * VT)) - 1.0)
                put(a, e.nodes[1], qdep(vd, m["CJO"], m["VJ"], m["M"], DIODE_FC) + m["TT"] * i)
            elif e.kind == "Q":
                p = Q2N3904
                _c, b, em = e.nodes
                ci, bi = e.name + ":c", e.name + ":b"
                vbe, vbc, vbx = v(x, bi) - v(x, em), v(x, bi) - v(x, ci), v(x, b) - v(x, ci)
                cbe = p["IS"] * (lexp(vbe / (p["NF"] * VT)) - 1.0)
                cbc = p["IS"] * (lexp(vbc / (p["NR"] * VT)) - 1.0)
                q1 = 1.0 / (1.0 - vbc / p["VAF"] - vbe / p["VAR"])
                qb = q1 * (1.0 + math.sqrt(max(1.0 + 4.0 * (cbe / p["IKF"] + cbc / p["IKR"]), 0.0))) / 2.0
                if vbe > 0.0:
                    t = cbe / (cbe + p["ITF"])
                    argtf = p["XTF"] * math.exp(vbc / (1.44 * p["VTF"])) * t * t
                    cbe = cbe * (1.0 + argtf) / qb
                put(bi, em, p["TF"] * cbe + qdep(vbe, p["CJE"], p["VJE"], p["MJE"], p["FC"]))
                put(bi, ci, p["TR"] * cbc + qdep(vbc, p["CJC"] * p["XCJC"], p["VJC"], p["MJC"], p["FC"]))
                put(b, ci, qdep(vbx, p["CJC"] * (1.0 - p["XCJC"]), p["VJC"], p["MJC"], p["FC"]))
        return Q

    def ac(self, x: np.ndarray, freq: float, source: str) -> np.ndarray:
        """Small-signal node voltages at ``freq`` for a 1 V AC excitation of ``source``."""
        F0 = self.residual(x, 1.0)
        A = self.jacobian(x, 1.0, F0).astype(complex)
        w = 2 * math.pi * freq
        Q0 = self.charges(x)
        for j in range(self.nn):
            h = 1e-6 * max(1.0, abs(x[j]))
            xp = x.copy()
            xp[j] += h
            A[:, j] += 1j * w * (self.charges(xp) - Q0) / h
        for e in self.els:
            if e.kind == "C":
                a, b = e.nodes
                y = 1j * w * e.value
                for n1, n2, sgn in ((a, a, 1), (b, b, 1), (a, b, -1), (b, a, -1)):
                    if n1 != "0" and n2 != "0":
                        A[self.node[n1], self.node[n2]] += sgn * y
            elif e.kind == "L":
                j = self.branch[e.name]
                A[j, j] -= 1j * w * e.value
        rhs = np.zeros(self.n, dtype=complex)
        rhs[self.branch[source]] = 1.0
        return np.linalg.solve(A, rhs)


# ------------------------------------------------------------------ readings
def solver_readings(circuit: CircuitSpec, fault: Fault, d: Any) -> dict[str, float]:
    text = (REPO_ROOT / "circuits" / circuit.id / f"{circuit.id}.cir").read_text()
    els = apply_draw(circuit, parse_netlist(text), fault, d)
    sig = circuit.signal.source if circuit.signal is not None else None
    hum = circuit.hum.reference_source if circuit.hum is not None else None
    s = Solver(els, sig, hum)
    x = s.operating_point()
    out: dict[str, float] = {}
    for tp in circuit.test_points:
        if "dc" in tp.measurements:
            out[f"open:{tp.id}"] = s.v(x, tp.node)
    for kind, freq, src in (("ac", 1000.0, sig), ("ac20", 20.0, sig), ("ac20k", 20000.0, sig),
                            ("hum", 120.0, hum)):
        tps = [tp for tp in circuit.test_points if kind in tp.measurements]
        if not tps or src is None:
            continue
        xa = s.ac(x, freq, src)
        for tp in tps:
            out[f"{kind}:{tp.id}"] = 0.0 if tp.node == "0" else float(abs(xa[s.node[tp.node]]))
    return out


def dmm_accuracy(v: float) -> float:
    """Bench meter accuracy at a reading: 0.5 % of reading + 2 counts on the auto range."""
    res = next((r for top, r in DMM_RANGES if abs(v) <= top), DMM_RANGES[-1][1])
    return DMM_PCT * abs(v) + 2 * res


def agrees(key: str, sim: float, ref: float) -> tuple[bool, float]:
    """(agreement, difference): volts for DC, dB for AC gain and hum."""
    kind = key.split(":")[0]
    if kind == "open":
        diff = sim - ref
        return abs(diff) <= DC_FACTOR * dmm_accuracy(ref), diff
    floor = HUM_FLOOR if kind == "hum" else GAIN_FLOOR
    db = 20 * math.log10(max(sim, floor) / max(ref, floor))
    return abs(db) <= AC_DB, db


# ------------------------------------------------------------------ sample
def sample_faults(seed: int = SEED, per_type: int = PER_TYPE) -> list[tuple[str, Fault]]:
    rng = np.random.default_rng(seed)
    out = []
    for cid in AUDITED:
        cat = [f for f in fault_catalog(get_circuit(cid)) if not f.is_healthy]
        by_type: dict[str, list[Fault]] = {}
        for f in cat:
            by_type.setdefault(MODE_TYPE[f.mode], []).append(f)
        for t in sorted(by_type):
            fs = by_type[t]
            pick = rng.choice(len(fs), size=min(per_type, len(fs)), replace=False)
            out += [(cid, fs[int(i)]) for i in sorted(pick)]
    return out


def audit_draws(hyp_index: int) -> list[int]:
    """Two as-new training draws and one aged one (ADR-039 parity rule)."""
    new = [i for i in range(8) if not is_aged("train", hyp_index, i)][:2]
    aged = [i for i in range(8) if is_aged("train", hyp_index, i)][:1]
    return new + aged


def audit_fault(cid: str, fault: Fault, log: Callable[[str], None] = print) -> dict[str, Any]:
    circuit = get_circuit(cid)
    cat = fault_catalog(circuit)
    hyp = next(i for i, f in enumerate(cat) if f.id == fault.id)
    draws = audit_draws(hyp)
    _, rows, _failures = run_job(Job(cid, "train", fault.id, hyp, tuple(draws), with_thd=False))
    by_draw = {int(r["draw"]): r for r in rows}
    checks: list[dict[str, Any]] = []
    for dr in draws:
        row = by_draw.get(dr)
        if row is None or not row["ok"]:
            checks.append({"draw": dr, "error": "ngspice run failed"})
            continue
        d = make_draw(cid, "train", hyp, fault.id, dr)
        try:
            ref = solver_readings(circuit, fault, d)
        except RuntimeError as exc:
            checks.append({"draw": dr, "error": f"solver: {exc}"})
            continue
        for key, rv in ref.items():
            sv = float(row[key])
            ok, diff = agrees(key, sv, rv)
            checks.append({"draw": dr, "aged": bool(row["aged"]), "reading": key, "ngspice": sv,
                           "solver": rv, "diff": diff, "agree": ok})
    good = all(c.get("agree", False) for c in checks)
    log(f"{cid:7s} {fault.id:22s} {'agree' if good else 'DISAGREE'} "
        f"({sum(c.get('agree', False) for c in checks)}/{len(checks)} readings)")
    return {"circuit": cid, "fault": fault.id, "type": MODE_TYPE.get(fault.mode, "healthy"), "draws": draws,
            "agree": good, "checks": checks}


KEY_READING = {"psu": "open:TP3", "triode": "open:TP9", "tone": "ac:TP12", "opamp": "open:TP15",
               "driver": "open:TP20", COMPOSITE_ID: "ac:TP22"}


def write_report(summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    lo, hi = summary["ci95"]
    lines = [
        "# Fault-signature audit",
        "",
        "Generated by `eval/fault_audit.py` (do not edit by hand); ADR-040. A stratified random",
        "sample of catalogued faults (up to two of each fault type per circuit, fixed seed) is",
        "re-solved without ngspice and without the simulator's netlist builder: the faults are",
        "inserted from their catalog definitions and the circuit is solved by a nodal solver",
        "written for the audit, with the published device equations. Each fault is checked on",
        "three of its training units (two as-new, one aged), rebuilt from their seeds.",
        "",
        "Agreement rule, fixed before the first comparison: DC within twice the bench meter's",
        "accuracy (0.5 % of reading + 2 counts); AC gain and 120 Hz hum within 0.5 dB after",
        "clamping at the instrument floor; a fault agrees when every reading of its three units",
        "agrees.",
        "",
        f"**Result: {summary['faults_agree']} of {summary['faults']} faults agree "
        f"(exact 95 % interval {100 * lo:.1f}-{100 * hi:.1f} %); "
        f"{summary['readings_agree']} of {summary['readings']} readings.**",
        "",
    ]
    fr = summary.get("first_run")
    if fr:
        lines += [
            "## First comparison run",
            "",
            f"The first run covered the five blocks: {fr['faults_agree']} of {fr['faults']} faults and "
            f"{fr['readings_agree']} of {fr['readings']} readings agreed; the audit solver failed to "
            f"solve some units. The disagreeing faults were {', '.join(fr['disagreeing'])}.",
            "Every one traced to the audit solver, not to the simulator: its small-signal model",
            "left out the junction capacitances of the device cards, which carry the signal when",
            "a triode grid is fed through an open (1 GOhm) grid stopper and when a shorted",
            "transistor leaves only capacitive feed-through at 20 kHz; and its Newton step limit",
            "stalled when an op-amp output was driven to a rail. The capacitances were added and",
            "the step limit was confined to junction nodes; the rule did not change. The channel",
            "strip was then added to the sample under the same rule.",
            "",
        ]
    lines += ["## By circuit and fault type", "",
              "| Circuit | Faults | Agree |", "|---|---|---|"]
    lines += [f"| {c} | {v['faults']} | {v['agree']} |" for c, v in summary["by_block"].items()]
    lines += ["", "| Fault type | Faults | Agree |", "|---|---|---|"]
    lines += [f"| {t} | {v['faults']} | {v['agree']} |" for t, v in summary["by_type"].items()]
    lines += ["", "## Every audited fault", "",
              "One reading per fault is shown (first as-new unit); all readings are in "
              "`results/fault_audit.json`.", "",
              "| Circuit | Fault | Type | Reading | ngspice | Audit solver | Agree |",
              "|---|---|---|---|---|---|---|"]
    for r in results:
        key = KEY_READING[r["circuit"]]
        c = next((c for c in r["checks"] if c.get("reading") == key), None)
        if c is None:
            lines.append(f"| {r['circuit']} | {r['fault']} | {r['type']} | - | - | - | "
                         f"{'yes' if r['agree'] else 'no'} |")
            continue
        unit = "V" if key.startswith("open:") else "V/V"
        lines.append(f"| {r['circuit']} | {r['fault']} | {r['type']} | {key.split(':', 1)[1]} "
                     f"{'DC' if unit == 'V' else '1 kHz gain'} | {c['ngspice']:.4g} {unit} | "
                     f"{c['solver']:.4g} {unit} | {'yes' if r['agree'] else 'no'} |")
    lines += ["", "What the audit does not show: that the device equations describe real parts",
              "(the hand calculations check healthy bias points against datasheet behavior, and",
              "the hardware target T7 tests real boards); THD; meter loading.", ""]
    (REPO_ROOT / "docs" / "fault_audit.md").write_text("\n".join(lines))


def main() -> None:
    from eval import metrics_io
    from eval.stats import exact_binomial

    ap = argparse.ArgumentParser()
    ap.add_argument("--healthy-only", action="store_true",
                    help="check the solver on healthy units only (no fault comparison)")
    args = ap.parse_args()
    if args.healthy_only:
        for cid in AUDITED:
            audit_fault(cid, HEALTHY_FAULT)
        return
    results = [audit_fault(cid, f) for cid, f in sample_faults()]
    k, n = sum(r["agree"] for r in results), len(results)
    ci = exact_binomial(k, n)
    readings = [c for r in results for c in r["checks"] if "agree" in c]
    summary = {
        "faults": n, "faults_agree": k, "agree_rate": k / n, "ci95": [ci.lo, ci.hi],
        "readings": len(readings), "readings_agree": sum(c["agree"] for c in readings),
        "by_block": {cid: {"faults": sum(r["circuit"] == cid for r in results),
                           "agree": sum(r["agree"] for r in results if r["circuit"] == cid)}
                     for cid in AUDITED},
        "by_type": {t: {"faults": sum(r["type"] == t for r in results),
                        "agree": sum(r["agree"] for r in results if r["type"] == t)}
                    for t in sorted({r["type"] for r in results})},
        "disagreements": [{"circuit": r["circuit"], "fault": r["fault"],
                           "readings": [c for c in r["checks"] if not c.get("agree", False)]}
                          for r in results if not r["agree"]],
        "rule": {"dc": f"|diff| <= {DC_FACTOR:g} x meter accuracy (0.5 % + 2 counts)",
                 "ac_hum_db": AC_DB, "gain_floor": GAIN_FLOOR, "hum_floor_v": HUM_FLOOR},
        "seed": SEED, "per_type": PER_TYPE,
    }
    first = RESULTS_DIR / "fault_audit_run1.json"
    if first.exists():
        f1 = json.loads(first.read_text())["summary"]
        summary["first_run"] = {"faults": f1["faults"], "faults_agree": f1["faults_agree"],
                                "readings": f1["readings"], "readings_agree": f1["readings_agree"],
                                "disagreeing": [x["fault"] for x in f1["disagreements"]]}
    (RESULTS_DIR / "fault_audit.json").write_text(json.dumps({"summary": summary, "faults": results},
                                                             indent=1, default=float))
    write_report(summary, results)
    metrics_io.update("fault_audit", {k2: v for k2, v in summary.items() if k2 != "disagreements"}
                      | {"n_disagreements": len(summary["disagreements"])})
    print(json.dumps({k2: v for k2, v in summary.items() if k2 != "disagreements"}, indent=1))


if __name__ == "__main__":
    main()
