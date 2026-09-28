"""Single-component fault catalog (brief §2.2).

A ``Fault`` is (component ref, mode). ``fault_catalog`` enumerates the healthy
hypothesis plus every catalog fault for every component of a circuit. Severity
parameters that vary between draws (e.g. how high a failed capacitor's ESR is)
are sampled in :mod:`differential.sim.draws`.
"""

from __future__ import annotations

from dataclasses import dataclass

from differential.circuits.model import CircuitSpec

HEALTHY = "healthy"
UNMODELED = "unmodeled"

FAULT_MODES: dict[str, tuple[str, ...]] = {
    "resistor": ("open", "short", "drift_x0.5", "drift_x2", "drift_x10"),
    "film_cap": ("open", "short"),
    "electrolytic": ("open", "short", "cap_loss_50", "cap_loss_90", "high_esr"),
    "potentiometer": ("wiper_open", "track_open"),
    "diode": ("open", "short"),
    "zener": ("open", "short"),
    "bjt": ("ce_short", "be_open", "beta_low", "cb_leak"),
    "triode": ("low_emission", "heater_open"),
    "opamp": ("dead", "gbw_low"),
}

MODE_LABELS: dict[str, str] = {
    "open": "open circuit",
    "short": "short circuit",
    "drift_x0.5": "value drifted to 0.5x",
    "drift_x2": "value drifted to 2x",
    "drift_x10": "value drifted to 10x",
    "cap_loss_50": "capacitance loss (-50 %)",
    "cap_loss_90": "capacitance loss (-90 %)",
    "high_esr": "high ESR",
    "wiper_open": "wiper open",
    "track_open": "track open",
    "ce_short": "collector-emitter short",
    "be_open": "base-emitter open",
    "beta_low": "gain (beta) degraded to 20 %",
    "cb_leak": "collector-base leakage",
    "low_emission": "low emission (worn cathode)",
    "heater_open": "heater open (no conduction)",
    "dead": "dead (output stuck at a rail)",
    "gbw_low": "degraded gain-bandwidth",
}

# Coarse fault-type grouping used for disaggregated error analysis.
MODE_TYPE: dict[str, str] = {
    "open": "open",
    "wiper_open": "open",
    "track_open": "open",
    "be_open": "open",
    "heater_open": "open",
    "short": "short",
    "ce_short": "short",
    "drift_x0.5": "drift",
    "drift_x2": "drift",
    "drift_x10": "drift",
    "cap_loss_50": "degradation",
    "cap_loss_90": "degradation",
    "high_esr": "degradation",
    "beta_low": "degradation",
    "cb_leak": "leakage",
    "low_emission": "degradation",
    "gbw_low": "degradation",
    "dead": "dead",
}

CAPACITOR_KINDS = ("film_cap", "electrolytic")


@dataclass(frozen=True, order=True)
class Fault:
    ref: str
    mode: str

    @property
    def id(self) -> str:
        if self.mode in (HEALTHY, UNMODELED):
            return self.mode
        return f"{self.ref}:{self.mode}"

    @property
    def is_healthy(self) -> bool:
        return self.mode == HEALTHY

    def label(self) -> str:
        if self.mode == HEALTHY:
            return "healthy (no fault)"
        if self.mode == UNMODELED:
            return "no single-fault model matches (possible multiple faults or a modification)"
        return f"{self.ref} {MODE_LABELS.get(self.mode, self.mode)}"


HEALTHY_FAULT = Fault("", HEALTHY)
UNMODELED_FAULT = Fault("", UNMODELED)


def parse_fault_id(fault_id: str) -> Fault:
    if fault_id in (HEALTHY, UNMODELED):
        return Fault("", fault_id)
    ref, mode = fault_id.split(":", 1)
    return Fault(ref, mode)


def fault_catalog(circuit: CircuitSpec) -> list[Fault]:
    """Healthy hypothesis followed by every single fault, in component order."""
    faults = [HEALTHY_FAULT]
    for comp in circuit.components:
        for mode in FAULT_MODES[comp.kind]:
            faults.append(Fault(comp.ref, mode))
    return faults


def part_kind(circuit: CircuitSpec, fault: Fault) -> str:
    if fault.mode in (HEALTHY, UNMODELED):
        return fault.mode
    return circuit.component(fault.ref).kind
