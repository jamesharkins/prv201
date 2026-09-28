"""Observable (measurement) definitions and effort costs (brief §2.2).

Keys look like ``dc:TP3``, ``ac:TP9``, ``hum:TP1``, ``ac20:TP22``, ``ac20k:TP22``,
``thd:TP22`` and ``lift:R203``.

Costs: DC probe 1; AC/scope measurement 3; +2 on a high-voltage test point;
lifting a component 10 (+2 when the part sits on a high-voltage node, because the
supply must be discharged and verified first).
"""

from __future__ import annotations

from dataclasses import dataclass

from differential.circuits.model import CircuitSpec

COST_DC = 1.0
COST_SCOPE = 3.0
COST_HV_EXTRA = 2.0
COST_LIFT = 10.0

SCOPE_KINDS = ("ac", "hum", "ac20", "ac20k", "thd")
SPICE_KINDS = ("dc", *SCOPE_KINDS)

KIND_LABEL = {
    "dc": "DC voltage",
    "ac": "1 kHz signal level (gain from input)",
    "hum": "120 Hz ripple/hum amplitude",
    "ac20": "20 Hz response (gain from input)",
    "ac20k": "20 kHz response (gain from input)",
    "thd": "total harmonic distortion at 1 kHz",
    "lift": "out-of-circuit component test",
}
KIND_INSTRUMENT = {
    "dc": "DMM on DC volts",
    "ac": "oscilloscope with a 1 kHz test tone at the input",
    "hum": "oscilloscope, AC-coupled, no input signal",
    "ac20": "oscilloscope with a 20 Hz test tone at the input",
    "ac20k": "oscilloscope with a 20 kHz test tone at the input",
    "thd": "distortion analyser or scope FFT at nominal level",
    "lift": "desolder one lead and test with an LCR/ESR meter or transistor tester",
}


@dataclass(frozen=True)
class ObservableSpec:
    key: str
    kind: str
    tp: str | None
    node: str | None
    ref: str | None
    hv: bool
    cost: float

    @property
    def is_lift(self) -> bool:
        return self.kind == "lift"

    @property
    def unit(self) -> str:
        return {
            "dc": "V",
            "ac": "V/V",
            "ac20": "V/V",
            "ac20k": "V/V",
            "hum": "V",
            "thd": "%",
            "lift": "",
        }[self.kind]


def measurement_cost(kind: str, hv: bool) -> float:
    base = COST_DC if kind == "dc" else COST_LIFT if kind == "lift" else COST_SCOPE
    return base + (COST_HV_EXTRA if hv else 0.0)


def spice_observables(circuit: CircuitSpec) -> list[ObservableSpec]:
    """Simulated observables in a fixed, documented order (grouped by kind)."""
    out: list[ObservableSpec] = []
    for kind in SPICE_KINDS:
        for tp in circuit.test_points:
            if kind in tp.measurements:
                out.append(
                    ObservableSpec(
                        key=f"{kind}:{tp.id}",
                        kind=kind,
                        tp=tp.id,
                        node=tp.node,
                        ref=None,
                        hv=tp.hv,
                        cost=measurement_cost(kind, tp.hv),
                    )
                )
    return out


def lift_observables(circuit: CircuitSpec) -> list[ObservableSpec]:
    out = []
    for comp in circuit.components:
        hv = circuit.component_is_hv(comp.ref)
        out.append(
            ObservableSpec(
                key=f"lift:{comp.ref}",
                kind="lift",
                tp=None,
                node=None,
                ref=comp.ref,
                hv=hv,
                cost=measurement_cost("lift", hv),
            )
        )
    return out


def all_observables(circuit: CircuitSpec) -> list[ObservableSpec]:
    return spice_observables(circuit) + lift_observables(circuit)


def observable_map(circuit: CircuitSpec) -> dict[str, ObservableSpec]:
    return {o.key: o for o in all_observables(circuit)}


def thd_node(circuit: CircuitSpec) -> str | None:
    for o in spice_observables(circuit):
        if o.kind == "thd":
            return o.node
    return None
