"""A simulated bench: a virtual unit with a hidden fault.

The unit's noise-free observables come from the same ngspice pipeline as the
training data (one Monte Carlo draw of the hidden fault). Each measurement adds
the documented instrument noise and display quantisation. Noise is seeded by
(unit id, observable), exactly as in the evaluation harness, so re-measuring a
point returns the same reading and every diagnosis policy sees identical
readings for the same unit (common random numbers).
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from differential.instruments.base import InstrumentError, InstrumentReading
from differential.sim.faults import parse_fault_id
from differential.sim.measurement import simulate_lift, simulate_reading
from differential.sim.observables import ObservableSpec


def noise_seed(unit_id: str, key: str) -> int:
    h = hashlib.sha256(f"{unit_id}|{key}".encode()).digest()
    return int.from_bytes(h[:8], "little")


class SimulatedBench:
    name = "simulated"

    def __init__(self, unit_id: str, circuit_id: str, hypothesis: str,
                 values: Mapping[str, float], fundamental: float) -> None:
        self.unit_id = unit_id
        self.circuit_id = circuit_id
        self.hypothesis = hypothesis  # hidden from the diagnosis; kept for scoring
        self._values = dict(values)
        self._fundamental = float(fundamental)
        self._defective = {parse_fault_id(f).ref for f in hypothesis.split("+")
                           if f and f != "healthy"}

    @classmethod
    def from_case_row(cls, row: Mapping[str, Any]) -> SimulatedBench:
        values = {k: float(v) for k, v in row.items()
                  if isinstance(k, str) and ":" in k and not k.startswith("liftval:")}
        return cls(str(row["case_id"]), str(row["circuit"]), str(row["hypothesis"]), values,
                   float(row["fundamental"]))

    @classmethod
    def simulate(cls, circuit_id: str, hypothesis: str, unit_index: int = 0,
                 split: str = "demo") -> SimulatedBench:
        """Run ngspice now for one unit of ``hypothesis`` (about a second per unit)."""
        from differential.sim.montecarlo import Job, run_job

        _, rows, failures = run_job(Job(circuit_id, split, hypothesis, 200000 + unit_index,
                                        (unit_index,)))
        if failures or not rows or not rows[0]["ok"]:
            raise InstrumentError(f"simulation failed for {circuit_id} {hypothesis}")
        row = dict(rows[0])
        row["case_id"] = f"{circuit_id}-{split}-{hypothesis}-{unit_index}"
        return cls.from_case_row(row)

    def supports(self, obs: ObservableSpec) -> bool:
        return obs.is_lift or obs.key in self._values

    def measure(self, obs: ObservableSpec) -> InstrumentReading:
        rng = np.random.default_rng(noise_seed(self.unit_id, obs.key))
        if obs.is_lift:
            verdict = float(simulate_lift(obs.ref in self._defective, rng))
            return InstrumentReading(obs.key, verdict, "", self.name,
                                     "out of tolerance" if verdict else "within tolerance")
        if obs.key not in self._values:
            raise InstrumentError(f"{obs.key} is not available on this unit")
        true_value = self._values[obs.key]
        if not math.isfinite(true_value):
            raise InstrumentError(f"{obs.key}: no simulated value")
        value = simulate_reading(obs.kind, true_value, rng, self._fundamental)
        return InstrumentReading(obs.key, value, obs.unit, self.name)
