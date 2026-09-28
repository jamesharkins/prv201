"""Instrument layer: simulated bench determinism, SCPI parsing and HV refusal."""

from __future__ import annotations

import math

import pytest

from differential.circuits.library import get_circuit
from differential.instruments import InstrumentError, ManualEntry, SimulatedBench, noise_seed
from differential.instruments.scpi import ScpiInstrument
from differential.sim.observables import observable_map


class FakeVisa:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.timeout = 0
        self.log: list[str] = []

    def query(self, cmd: str) -> str:
        self.log.append(cmd)
        return self.responses[cmd]


def _obs(cid: str, key: str):  # type: ignore[no-untyped-def]
    return observable_map(get_circuit(cid))[key]


def _driver_row() -> dict[str, object]:
    obs = observable_map(get_circuit("driver"))
    row: dict[str, object] = {"case_id": "driver-test-0001", "circuit": "driver",
                              "hypothesis": "C502:open", "fundamental": 0.5}
    for key, o in obs.items():
        if not o.is_lift:
            row[key] = 1.0 if o.kind != "thd" else 0.1
    return row


def test_noise_seed_is_stable_and_distinct() -> None:
    assert noise_seed("a", "dc:TP1") == noise_seed("a", "dc:TP1")
    assert noise_seed("a", "dc:TP1") != noise_seed("a", "dc:TP2")


def test_simulated_bench_repeatable_readings() -> None:
    bench = SimulatedBench.from_case_row(_driver_row())
    dc = next(o for o in observable_map(get_circuit("driver")).values() if o.kind == "dc")
    a, b = bench.measure(dc), bench.measure(dc)
    assert a.value == b.value
    assert a.unit == "V" and a.source == "simulated"
    assert abs(a.value - 1.0) < 0.05


def test_simulated_bench_lift_verdicts() -> None:
    bench = SimulatedBench.from_case_row(_driver_row())
    obs = observable_map(get_circuit("driver"))
    verdicts = {k: bench.measure(o).value for k, o in obs.items() if o.is_lift}
    assert verdicts["lift:C502"] in (0.0, 1.0)
    # specificity 0.99: almost every healthy part tests good
    assert sum(v for k, v in verdicts.items() if k != "lift:C502") <= 2


def test_scpi_dmm_reads_and_parses() -> None:
    res = FakeVisa({"*IDN?": "FAKE,DMM,0,1", "MEAS:VOLT:DC?": "+1.23450000E+01\n"})
    dmm = ScpiInstrument("FAKE::1", role="dmm", resource=res)
    dc = next(o for o in observable_map(get_circuit("driver")).values()
              if o.kind == "dc" and not o.hv)
    r = dmm.measure(dc)
    assert math.isclose(r.value, 12.345)
    assert dmm.idn == "FAKE,DMM,0,1"


def test_scpi_rejects_overload_and_over_voltage() -> None:
    dc = next(o for o in observable_map(get_circuit("driver")).values()
              if o.kind == "dc" and not o.hv)
    over = ScpiInstrument("F", resource=FakeVisa({"*IDN?": "x", "MEAS:VOLT:DC?": "9.9E37"}))
    with pytest.raises(InstrumentError):
        over.measure(dc)
    high = ScpiInstrument("F", resource=FakeVisa({"*IDN?": "x", "MEAS:VOLT:DC?": "48.0"}))
    with pytest.raises(InstrumentError):
        high.measure(dc)


def test_scpi_refuses_high_voltage_points() -> None:
    hv = next(o for o in observable_map(get_circuit("psu")).values() if o.hv and o.kind == "dc")
    dmm = ScpiInstrument("F", resource=FakeVisa({"*IDN?": "x", "MEAS:VOLT:DC?": "1.0"}))
    assert not dmm.supports(hv)
    with pytest.raises(InstrumentError, match="high-voltage"):
        dmm.measure(hv)


def test_scpi_scope_gain_is_ratio_of_channels() -> None:
    res = FakeVisa({"*IDN?": "RIGOL", ":MEASure:ITEM? VRMS,CHANnel1": "2.0",
                    ":MEASure:ITEM? VRMS,CHANnel2": "0.5"})
    scope = ScpiInstrument("F", role="scope", resource=res)
    ac = next(o for o in observable_map(get_circuit("driver")).values()
              if o.kind == "ac" and not o.hv)
    assert math.isclose(scope.measure(ac).value, 4.0)


def test_manual_entry_requires_value() -> None:
    m = ManualEntry()
    dc = next(o for o in observable_map(get_circuit("driver")).values() if o.kind == "dc")
    with pytest.raises(InstrumentError):
        m.measure(dc)
    m.provide(dc.key, 3.3)
    assert m.measure(dc).value == 3.3


def test_fault_board_reading_rules() -> None:
    obs = observable_map(get_circuit("driver"))
    tp22 = obs["dc:TP22"]
    dmm = ScpiInstrument("F", resource=FakeVisa({"*IDN?": "x", "MEAS:VOLT:DC?": "0.042"}))
    assert dmm.measure(tp22).value == 0.0
    ac = next(o for o in obs.values() if o.kind == "ac" and not o.hv)
    noise = FakeVisa({"*IDN?": "x", ":MEASure:ITEM? VRMS,CHANnel1": "0.001",
                      ":MEASure:ITEM? VRMS,CHANnel2": "0.07"})
    assert ScpiInstrument("F", role="scope", resource=noise).measure(ac).value == 0.0
