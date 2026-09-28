"""Instrument interface (brief §2.10).

Every reading that enters a diagnosis passes through one of these classes, so the
engine never cares whether a value came from a simulated bench, a SCPI instrument,
a meter photo or the technician's keyboard. High-voltage test points are never
measured automatically: the technician places the probe and confirms, and the
safety layer attaches its warnings before the step is shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from differential.sim.observables import ObservableSpec


@dataclass(frozen=True)
class InstrumentReading:
    key: str
    value: float
    unit: str
    source: str  # "simulated", "scpi:<resource>", "manual", "photo"
    raw: str = ""


class InstrumentError(RuntimeError):
    """The instrument could not produce a trustworthy reading."""


@runtime_checkable
class Instrument(Protocol):
    name: str

    def supports(self, obs: ObservableSpec) -> bool: ...

    def measure(self, obs: ObservableSpec) -> InstrumentReading: ...


class ManualEntry:
    """Readings typed (or confirmed from a photo) by the technician."""

    name = "manual"

    def __init__(self) -> None:
        self._pending: dict[str, float] = {}

    def supports(self, obs: ObservableSpec) -> bool:
        return True

    def provide(self, key: str, value: float) -> None:
        self._pending[key] = float(value)

    def measure(self, obs: ObservableSpec) -> InstrumentReading:
        if obs.key not in self._pending:
            raise InstrumentError(f"no manual reading entered for {obs.key}")
        return InstrumentReading(obs.key, self._pending.pop(obs.key), obs.unit, "manual")
