"""Monte Carlo parameter draws: component tolerances plus fault application.

A draw is a ``Draw`` holding
  * ``alters``    element name -> value            (``alter NAME = value``)
  * ``altermods`` (model name, param) -> value     (``altermod MODEL param = value``)
  * ``lift``      component ref -> out-of-circuit reading (for lift tests)
  * ``severity``  fault-severity parameters that were sampled (for provenance)
Structural netlist edits needed by a fault (added shorting resistors, broken
leads) are described by :func:`structural_edits` and applied by the builder.

Tolerance distributions (documented in docs/DECISIONS.md, ADR-006):
  * passive values: truncated normal, sigma = tol/2, truncated at +-tol
  * electrolytic ESR: nominal (tan-delta limit) x U(0.4, 1.0)
  * potentiometer: track total +-20 %, rotation setting +-0.02 of track
  * BJT beta: model BF x log-uniform(0.82, 3.2) -> hFE 100-300 at 10 mA (datasheet)
  * zener voltage: truncated normal, sigma = 2.5 %, +-5 %
  * triode: MU x U(0.9, 1.1); KG1 x log-uniform(0.8, 1.25)
  * op-amp gain-bandwidth: 3 MHz x U(0.7, 1.3)
  * mains: +-5 % (common factor on both rectifier peak voltages)

Aged units (stress splits only, ``age_draw``; ADR-032): after the tolerance draw every
part of an ageing kind drifts in the direction parts age, independently per part:
  * electrolytic: capacitance x U(0.70, 0.95) and ESR x log-uniform(1.2, 3.0), inside
    the usual end-of-life limits (capacitance down 30 %, ESR up 3x)
  * fixed resistor: value x U(1.00, 1.10) (carbon resistors drift up with age)
  * triode: emission (perveance scale) x U(0.70, 1.00), above the worn-tube fault range
Film capacitors, transistors, diodes, zeners, potentiometers and op-amps do not age here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from differential.circuits.model import CircuitSpec, ComponentSpec
from differential.sim.faults import Fault

R_OPEN = 1e9
C_OPEN = 1e-15
BRIDGE = "BRIDGE"  # pseudo-ref for out-of-catalog solder-bridge modifications

# BF scale range chosen so the simulated hFE at 10 mA, VCE = 1 V spans the onsemi
# datasheet window of 100-300 (the unscaled onsemi model gives 119 there; BF x 0.82
# gives 100 and BF x 3.2 gives 300, measured with ngspice).
BETA_SCALE_RANGE = {
    "bjt_2n3904": (0.82, 3.2),
}
MODEL_BF = {"Q2N3904": 206.302}
# 1N4745A (Diodes Inc. subcircuit): Vz = VZ source (14.6 V) + reverse-diode drop,
# 16 V at the 15.5 mA test current; +-5 % tolerance applies to the 16 V total.
ZENER_VZ_SOURCE = 14.6
ZENER_VZ_NOMINAL = 16.0

TRIODE_MU = 100.0
TRIODE_KG1 = 1060.0
OPAMP_GBW_MHZ = 3.0
MAINS_TOL = 0.05

AGE_ELECTROLYTIC_C = (0.70, 0.95)
AGE_ELECTROLYTIC_ESR = (1.2, 3.0)
AGE_RESISTOR = (1.00, 1.10)
AGE_TRIODE_EMISSION = (0.70, 1.00)


@dataclass
class Draw:
    alters: dict[str, float] = field(default_factory=dict)
    altermods: dict[tuple[str, str], float] = field(default_factory=dict)
    lift: dict[str, float] = field(default_factory=dict)
    severity: dict[str, float] = field(default_factory=dict)


def device_model_name(comp: ComponentSpec) -> str:
    """Per-device model clone name used by the builder (so altermod is per device)."""
    assert comp.model is not None
    return f"{comp.model}_{comp.ref}".upper()


def _trunc_normal(rng: np.random.Generator, sigma: float, limit: float) -> float:
    while True:
        x = float(rng.normal(0.0, sigma))
        if abs(x) <= limit:
            return x


def _log_uniform(rng: np.random.Generator, lo: float, hi: float) -> float:
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


def _widen(lo: float, hi: float, scale: float) -> tuple[float, float]:
    """Widen a multiplicative spread [lo, hi] around its geometric centre."""
    if scale == 1.0:
        return lo, hi
    c = math.sqrt(lo * hi)
    return c * (lo / c) ** scale, c * (hi / c) ** scale


def healthy_draw(circuit: CircuitSpec, rng: np.random.Generator, tol_scale: float = 1.0) -> Draw:
    """Draw every tolerance-affected parameter of a healthy unit.

    ``tol_scale`` widens every spread (the stress set uses 1.5); at 1.0 the random
    stream and the values are exactly those of the training data.
    """
    s = tol_scale
    d = Draw()
    net = circuit.netlist
    for comp in circuit.components:
        kind = comp.kind
        if kind in ("resistor", "film_cap", "electrolytic"):
            nominal = comp.nominal
            assert nominal is not None and comp.tolerance is not None
            tol = comp.tolerance * s
            val = nominal * (1.0 + _trunc_normal(rng, tol / 2, tol))
            d.alters[comp.main_element] = val
            d.lift[comp.ref] = val
            if kind == "electrolytic":
                esr_el = comp.elements["esr"]
                esr_nom = net.element(esr_el).numeric_value
                assert esr_nom is not None
                d.alters[esr_el] = esr_nom * float(rng.uniform(0.4, 1.0))
        elif kind == "potentiometer":
            nominal = comp.nominal
            assert nominal is not None and comp.tolerance is not None and comp.setting is not None
            tol = comp.tolerance * s
            total = nominal * (1.0 + _trunc_normal(rng, tol / 2, tol))
            setting = min(0.99, max(0.01, comp.setting + float(rng.uniform(-0.02 * s, 0.02 * s))))
            d.alters[comp.elements["upper"]] = total * (1.0 - setting)
            d.alters[comp.elements["lower"]] = total * setting
            d.alters[comp.elements["wiper"]] = float(rng.uniform(0.5, 2.0))
            d.lift[comp.ref] = total
        elif kind == "bjt":
            assert comp.model is not None
            lo, hi = _widen(*BETA_SCALE_RANGE[comp.family], s)
            scale = _log_uniform(rng, lo, hi)
            d.altermods[(device_model_name(comp), "bf")] = MODEL_BF[comp.model] * scale
            d.lift[comp.ref] = scale  # relative hFE as read on a transistor tester
        elif kind == "zener":
            dv = ZENER_VZ_NOMINAL * _trunc_normal(rng, 0.025 * s, 0.05 * s)
            d.alters[comp.params["vz"]] = ZENER_VZ_SOURCE + dv
            d.lift[comp.ref] = ZENER_VZ_NOMINAL + dv
        elif kind == "diode":
            d.lift[comp.ref] = 1.0  # forward drop reads normal on a diode test
        elif kind == "triode":
            d.alters[comp.params["pv"]] = 1.0
            mu_lo, mu_hi = (0.9, 1.1) if s == 1.0 else (1 - 0.1 * s, 1 + 0.1 * s)
            d.alters[comp.params["mu"]] = TRIODE_MU * float(rng.uniform(mu_lo, mu_hi))
            kg_lo, kg_hi = _widen(0.8, 1.25, s)
            d.alters[comp.params["kg"]] = TRIODE_KG1 * _log_uniform(rng, kg_lo, kg_hi)
            d.lift[comp.ref] = TRIODE_KG1 / d.alters[comp.params["kg"]]  # relative emission
        elif kind == "opamp":
            g_lo, g_hi = (0.7, 1.3) if s == 1.0 else (1 - 0.3 * s, 1 + 0.3 * s)
            d.alters[comp.params["gbw"]] = OPAMP_GBW_MHZ * float(rng.uniform(g_lo, g_hi))
            d.alters[comp.params["dead"]] = 0.0
            d.alters[comp.params["rail"]] = 1.0
            d.lift[comp.ref] = d.alters[comp.params["gbw"]] / OPAMP_GBW_MHZ
        else:  # pragma: no cover - guarded by the YAML schema test
            raise ValueError(f"unknown kind {kind}")
    if circuit.hum is not None:
        mains = 1.0 + float(rng.uniform(-MAINS_TOL * s, MAINS_TOL * s))
        d.severity["mains_factor"] = mains
        for rect in circuit.hum.rectifiers:
            d.alters[rect.pk_source] = rect.pk_nominal * mains
    return d


def age_draw(circuit: CircuitSpec, draw: Draw, rng: np.random.Generator) -> Draw:
    """Age a healthy draw in place (aged-unit stress splits); returns the draw.

    Applied after ``healthy_draw`` and before the fault, so a catalogued fault acts on
    an aged unit. Out-of-circuit readings follow the aged values.
    """
    net = circuit.netlist
    for comp in circuit.components:
        if comp.kind == "electrolytic":
            main = comp.main_element
            draw.alters[main] *= float(rng.uniform(*AGE_ELECTROLYTIC_C))
            draw.lift[comp.ref] = draw.alters[main]
            esr_el = comp.elements["esr"]
            esr = draw.alters.get(esr_el, net.element(esr_el).numeric_value)
            assert esr is not None
            draw.alters[esr_el] = esr * _log_uniform(rng, *AGE_ELECTROLYTIC_ESR)
        elif comp.kind == "resistor":
            main = comp.main_element
            draw.alters[main] *= float(rng.uniform(*AGE_RESISTOR))
            draw.lift[comp.ref] = draw.alters[main]
        elif comp.kind == "triode":
            k = float(rng.uniform(*AGE_TRIODE_EMISSION))
            draw.alters[comp.params["pv"]] *= k
            draw.lift[comp.ref] *= k
    draw.severity["aged"] = 1.0
    _sync_rectifiers(circuit, draw)
    return draw


def apply_fault(
    circuit: CircuitSpec, draw: Draw, fault: Fault, rng: np.random.Generator
) -> Draw:
    """Modify a healthy draw in place to realise ``fault``; returns the draw."""
    if fault.is_healthy:
        _sync_rectifiers(circuit, draw)
        return draw
    if fault.ref == BRIDGE:
        # Out-of-catalog modification: solder bridge between two nodes.
        r = _log_uniform(rng, 0.1, 10.0)
        draw.severity["bridge_ohms"] = r
        draw.alters[bridge_element(fault)] = r
        _sync_rectifiers(circuit, draw)
        return draw
    comp = circuit.component(fault.ref)
    mode = fault.mode
    main = comp.main_element
    if comp.kind == "resistor":
        if mode == "open":
            draw.alters[main] = R_OPEN
        elif mode == "short":
            draw.alters[main] = _log_uniform(rng, 0.01, 1.0)
        elif mode.startswith("drift_x"):
            draw.alters[main] *= float(mode.removeprefix("drift_x"))
        elif mode.startswith("value_x"):  # out-of-catalog: wrong value fitted
            draw.alters[main] *= float(mode.removeprefix("value_x"))
        draw.lift[comp.ref] = draw.alters[main]
    elif comp.kind in ("film_cap", "electrolytic"):
        if mode == "open":
            draw.alters[main] = C_OPEN
            draw.lift[comp.ref] = C_OPEN
        elif mode == "short":
            r = _log_uniform(rng, 0.1, 10.0)
            draw.severity["short_ohms"] = r
            draw.alters[f"RFLT_{comp.ref}"] = r
            draw.lift[comp.ref] = 0.0  # reads as a short on a capacitance meter
        elif mode == "cap_loss_50":
            draw.alters[main] *= 0.5
            draw.lift[comp.ref] = draw.alters[main]
        elif mode == "cap_loss_90":
            draw.alters[main] *= 0.1
            draw.lift[comp.ref] = draw.alters[main]
        elif mode.startswith("value_x"):  # out-of-catalog: wrong value fitted
            draw.alters[main] *= float(mode.removeprefix("value_x"))
            draw.lift[comp.ref] = draw.alters[main]
        elif mode == "high_esr":
            esr_el = comp.elements["esr"]
            nominal_esr = circuit.netlist.element(esr_el).numeric_value
            assert nominal_esr is not None
            factor = _log_uniform(rng, 10.0, 100.0)
            draw.severity["esr_factor"] = factor
            draw.alters[esr_el] = nominal_esr * factor
    elif comp.kind == "potentiometer":
        if mode == "wiper_open":
            draw.alters[comp.elements["wiper"]] = R_OPEN
        elif mode == "track_open":
            side = "upper" if rng.uniform() < 0.5 else "lower"
            draw.severity["track_open_upper"] = 1.0 if side == "upper" else 0.0
            draw.alters[comp.elements[side]] = R_OPEN
            draw.lift[comp.ref] = R_OPEN
    elif comp.kind in ("diode", "zener"):
        if mode == "open":
            draw.alters[f"RFLT_{comp.ref}"] = R_OPEN
            draw.lift[comp.ref] = 0.0
        elif mode == "short":
            r = _log_uniform(rng, 0.1, 10.0)
            draw.severity["short_ohms"] = r
            draw.alters[f"RFLT_{comp.ref}"] = r
            draw.lift[comp.ref] = -1.0
    elif comp.kind == "bjt":
        if mode == "ce_short":
            r = _log_uniform(rng, 1.0, 50.0)
            draw.severity["short_ohms"] = r
            draw.alters[f"RFLT_{comp.ref}"] = r
            draw.lift[comp.ref] = -1.0
        elif mode == "be_open":
            draw.alters[f"RFLT_{comp.ref}"] = R_OPEN
            draw.lift[comp.ref] = 0.0
        elif mode == "beta_low":
            key = (device_model_name(comp), "bf")
            draw.altermods[key] *= 0.2
            draw.lift[comp.ref] *= 0.2
        elif mode == "cb_leak":
            r = _log_uniform(rng, 47e3, 470e3)
            draw.severity["leak_ohms"] = r
            draw.alters[f"RFLT_{comp.ref}"] = r
            draw.lift[comp.ref] = -2.0
    elif comp.kind == "triode":
        if mode == "low_emission":
            k = float(rng.uniform(0.3, 0.6))
            draw.severity["emission"] = k
            draw.alters[comp.params["pv"]] = k
            draw.lift[comp.ref] *= k
        elif mode == "heater_open":
            draw.alters[comp.params["pv"]] = 0.0
            draw.lift[comp.ref] = 0.0
    elif comp.kind == "opamp":
        if mode == "dead":
            rail = 1.0 if rng.uniform() < 0.5 else 0.0
            draw.severity["dead_rail_high"] = rail
            draw.alters[comp.params["dead"]] = 1.0
            draw.alters[comp.params["rail"]] = rail
            draw.lift[comp.ref] = 0.0
        elif mode == "gbw_low":
            factor = _log_uniform(rng, 0.01, 0.1)
            draw.severity["gbw_factor"] = factor
            draw.alters[comp.params["gbw"]] *= factor
            draw.lift[comp.ref] *= factor
    else:  # pragma: no cover
        raise ValueError(f"unsupported fault {fault.id}")
    _sync_rectifiers(circuit, draw)
    return draw


def _sync_rectifiers(circuit: CircuitSpec, draw: Draw) -> None:
    """Keep each rectifier's reservoir-capacitance parameter node equal to the reservoir."""
    if circuit.hum is None:
        return
    for rect in circuit.hum.rectifiers:
        if rect.reservoir in circuit.refs:
            draw.alters[rect.cres_source] = draw.alters[circuit.component(rect.reservoir).main_element]


@dataclass(frozen=True)
class StructuralEdit:
    """A netlist edit: add a two-terminal resistor, optionally breaking a lead first."""

    add_name: str
    node_a: str
    node_b: str
    default_value: float
    remove_element: str | None = None
    rewire: tuple[str, int, str] | None = None  # (element, node index, new node)


def bridge_element(fault: Fault) -> str:
    a, b = fault.mode.split("~")
    return f"RBRIDGE_{a}_{b}".upper()


def structural_edits(circuit: CircuitSpec, fault: Fault) -> list[StructuralEdit]:
    if fault.is_healthy:
        return []
    if fault.ref == BRIDGE:
        a, b = fault.mode.split("~")
        return [StructuralEdit(bridge_element(fault), a, b, 1.0)]
    comp = circuit.component(fault.ref)
    mode = fault.mode
    name = f"RFLT_{comp.ref}"
    net = circuit.netlist
    if comp.kind in ("film_cap", "electrolytic") and mode == "short":
        if comp.kind == "electrolytic":
            a = net.element(comp.main_element).nodes[0]
            b = net.element(comp.elements["esr"]).nodes[1]
        else:
            a, b = net.element(comp.main_element).nodes
        return [StructuralEdit(name, a, b, 1.0)]
    if comp.kind in ("diode", "zener"):
        anode, cathode = net.element(comp.main_element).nodes[:2]
        if mode == "open":
            return [StructuralEdit(name, anode, cathode, R_OPEN, remove_element=comp.main_element)]
        return [StructuralEdit(name, anode, cathode, 1.0)]
    if comp.kind == "bjt":
        c, b, e = net.element(comp.main_element).nodes
        if mode == "ce_short":
            return [StructuralEdit(name, c, e, 1.0)]
        if mode == "cb_leak":
            return [StructuralEdit(name, c, b, 1e5)]
        if mode == "be_open":
            new_node = f"{comp.ref.lower()}_bopen"
            return [
                StructuralEdit(name, b, new_node, R_OPEN, rewire=(comp.main_element, 1, new_node))
            ]
    return []
