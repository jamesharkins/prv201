"""SCPI instruments over VISA (pyvisa), for the low-voltage fault board.

Supported roles:
  * ``dmm``   - DC volts: ``MEAS:VOLT:DC?`` (SCPI-99 common command set).
  * ``scope`` - amplitudes as RMS volts on channel 1 (probe on the test point),
                with channel 2 on the signal-generator output for gain readings.
                Command strings default to the Rigol DS1000Z family and can be
                overridden for other scopes.
The technician always places the probe; ``measure`` only triggers and reads.
Test points flagged as high voltage are refused here: Differential's hardware
path is limited to the 24 V fault board (brief §2.10), and B+ readings on real
equipment are entered by hand after the safety briefing.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from differential.instruments.base import InstrumentError, InstrumentReading
from differential.sim.observables import ObservableSpec

MAX_BENCH_VOLTS = 24.0
# Reading rules for the low-voltage fault board (hardware/fault_board/procedure.md):
# quantities the model does not contain are reported as the model's zero.
DC_ZERO_BAND_V = {"TP17": 0.010, "TP22": 0.100}  # generator offset / capacitor leakage
NOISE_FLOOR_VRMS = 0.005  # below this the scope shows noise, not a sine: gain is 0

DEFAULT_COMMANDS: dict[str, dict[str, str]] = {
    "dmm": {"dc": "MEAS:VOLT:DC?"},
    "scope": {
        "vrms_tp": ":MEASure:ITEM? VRMS,CHANnel1",
        "vrms_ref": ":MEASure:ITEM? VRMS,CHANnel2",
    },
}
ROLE_KINDS = {"dmm": ("dc",), "scope": ("ac", "ac20", "ac20k", "hum")}


def _parse_float(text: str) -> float:
    try:
        value = float(text.strip().split(",")[0])
    except ValueError as e:
        raise InstrumentError(f"unparseable instrument response: {text!r}") from e
    # Many instruments report overload as 9.9E37.
    if not math.isfinite(value) or abs(value) >= 9.0e37:
        raise InstrumentError("instrument reports overload or no signal")
    return value


class ScpiInstrument:
    def __init__(self, resource_name: str, role: str = "dmm", resource: Any = None,
                 commands: Mapping[str, str] | None = None, timeout_ms: int = 5000) -> None:
        if role not in ROLE_KINDS:
            raise ValueError(f"unknown role {role}")
        self.role = role
        self.resource_name = resource_name
        self.name = f"scpi:{resource_name}"
        self.commands = dict(DEFAULT_COMMANDS[role])
        self.commands.update(commands or {})
        if resource is None:
            import pyvisa

            resource = pyvisa.ResourceManager().open_resource(resource_name)
        self._res = resource
        self._res.timeout = timeout_ms
        self.idn = str(self._res.query("*IDN?")).strip()

    def supports(self, obs: ObservableSpec) -> bool:
        return obs.kind in ROLE_KINDS[self.role] and not obs.hv

    def measure(self, obs: ObservableSpec) -> InstrumentReading:
        if obs.hv:
            raise InstrumentError(
                f"{obs.key} is a high-voltage test point; the SCPI path only serves the "
                f"{MAX_BENCH_VOLTS:.0f} V fault board. Enter this reading by hand.")
        if not self.supports(obs):
            raise InstrumentError(f"{self.role} cannot measure {obs.kind}")
        if self.role == "dmm":
            raw = str(self._res.query(self.commands["dc"]))
            value = _parse_float(raw)
            if obs.tp in DC_ZERO_BAND_V and abs(value) <= DC_ZERO_BAND_V[obs.tp]:
                value = 0.0
            if abs(value) > MAX_BENCH_VOLTS * 1.1:
                raise InstrumentError(
                    f"{value:.1f} V exceeds the fault board's {MAX_BENCH_VOLTS:.0f} V limit")
            return InstrumentReading(obs.key, value, "V", self.name, raw.strip())
        tp = _parse_float(str(self._res.query(self.commands["vrms_tp"])))
        if obs.kind != "hum" and tp < NOISE_FLOOR_VRMS:
            return InstrumentReading(obs.key, 0.0, "V/V", self.name,
                                     f"CH1 {tp:.4g} Vrms: noise only, gain reported as 0")
        if obs.kind == "hum":
            return InstrumentReading(obs.key, tp, "V", self.name, f"CH1 {tp:.4g} Vrms")
        ref = _parse_float(str(self._res.query(self.commands["vrms_ref"])))
        if ref <= 0:
            raise InstrumentError("no reference signal on channel 2")
        return InstrumentReading(obs.key, tp / ref, "V/V", self.name,
                                 f"CH1 {tp:.4g} Vrms / CH2 {ref:.4g} Vrms")
