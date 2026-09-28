from __future__ import annotations

import math

import numpy as np
import pytest

from differential.circuits.library import get_circuit
from differential.sim import measurement as meas
from differential.sim.builder import build_deck, control_lines, fault_netlist, model_cards
from differential.sim.draws import (
    BRIDGE,
    C_OPEN,
    R_OPEN,
    apply_fault,
    healthy_draw,
    structural_edits,
)
from differential.sim.faults import (
    FAULT_MODES,
    HEALTHY_FAULT,
    MODE_LABELS,
    MODE_TYPE,
    UNMODELED_FAULT,
    Fault,
    fault_catalog,
    parse_fault_id,
    part_kind,
)
from differential.sim.montecarlo import (
    SPLIT_INDEX,
    Job,
    catalog_jobs,
    draw_rng,
    make_draw,
    run_job,
    seed_label,
)
from differential.sim.observables import (
    all_observables,
    lift_observables,
    measurement_cost,
    observable_map,
    spice_observables,
    thd_node,
)
from differential.sim.runner import parse_output, simulate_draws


def test_catalog_sizes_and_labels() -> None:
    sizes = {cid: len(fault_catalog(get_circuit(cid))) for cid in
             ("psu", "triode", "tone", "opamp", "driver", "channel_strip")}
    assert sizes["channel_strip"] == sum(v - 1 for k, v in sizes.items()
                                         if k != "channel_strip") + 1
    for modes in FAULT_MODES.values():
        for m in modes:
            assert m in MODE_LABELS and m in MODE_TYPE
    f = Fault("R203", "open")
    assert parse_fault_id(f.id) == f
    assert parse_fault_id("healthy") == HEALTHY_FAULT
    assert UNMODELED_FAULT.label().startswith("no single-fault")
    assert HEALTHY_FAULT.label().startswith("healthy")
    assert f.label() == "R203 open circuit"
    c = get_circuit("triode")
    assert part_kind(c, f) == "resistor" and part_kind(c, HEALTHY_FAULT) == "healthy"


def test_observables_costs() -> None:
    c = get_circuit("channel_strip")
    obs = observable_map(c)
    assert obs["dc:TP3"].cost == 1.0
    assert obs["dc:TP9"].cost == 3.0  # HV surcharge
    assert obs["ac:TP9"].cost == 5.0
    assert obs["lift:R501"].cost == 10.0
    assert obs["lift:C104"].cost == 12.0
    assert measurement_cost("hum", False) == 3.0
    assert thd_node(c) == "out"
    assert len(all_observables(c)) == len(spice_observables(c)) + len(lift_observables(c))
    assert thd_node(get_circuit("psu")) is None
    assert obs["dc:TP3"].unit == "V" and obs["thd:TP22"].unit == "%"


def test_healthy_draw_within_tolerance_and_deterministic() -> None:
    c = get_circuit("channel_strip")
    d1 = healthy_draw(c, np.random.default_rng(3))
    d2 = healthy_draw(c, np.random.default_rng(3))
    assert d1.alters == d2.alters and d1.altermods == d2.altermods
    for comp in c.components:
        if comp.kind in ("resistor", "film_cap", "electrolytic"):
            v = d1.alters[comp.main_element]
            assert abs(v / comp.nominal - 1) <= comp.tolerance + 1e-12
    assert 0.95 <= d1.severity["mains_factor"] <= 1.05
    assert d1.alters["VCRES_LV"] if "VCRES_LV" in d1.alters else True


@pytest.mark.parametrize(
    ("fault", "check"),
    [
        (Fault("R203", "open"), lambda d: d.alters["R203"] == R_OPEN),
        (Fault("R203", "drift_x10"), lambda d: 9.0 < d.alters["R203"] / 1e5 < 11.0),
        (Fault("C203", "open"), lambda d: d.alters["C203"] == C_OPEN),
        (Fault("C203", "short"), lambda d: 0.1 <= d.alters["RFLT_C203"] <= 10),
        (Fault("C101", "cap_loss_90"), lambda d: d.alters["VCRES_LV"] == d.alters["C101"] < 3e-4),
        (Fault("C101", "high_esr"), lambda d: d.alters["RESR_C101"] >= 0.72),
        (Fault("VR301", "wiper_open"), lambda d: d.alters["RVR301W"] == R_OPEN),
        (Fault("VR301", "track_open"), lambda d: R_OPEN in (d.alters["RVR301A"], d.alters["RVR301B"])),
        (Fault("D101", "open"), lambda d: d.alters["RFLT_D101"] == R_OPEN),
        (Fault("D102", "short"), lambda d: d.alters["RFLT_D102"] <= 10),
        (Fault("Q501", "beta_low"), lambda d: d.altermods[("Q2N3904_Q501", "bf")] < 0.2 * 206.302 * 3.3),
        (Fault("Q501", "cb_leak"), lambda d: 47e3 <= d.alters["RFLT_Q501"] <= 470e3),
        (Fault("Q502", "ce_short"), lambda d: d.alters["RFLT_Q502"] <= 50),
        (Fault("Q502", "be_open"), lambda d: d.alters["RFLT_Q502"] == R_OPEN),
        (Fault("V201", "heater_open"), lambda d: d.alters["VPV_V201"] == 0.0),
        (Fault("V201", "low_emission"), lambda d: 0.3 <= d.alters["VPV_V201"] <= 0.6),
        (Fault("U401", "dead"), lambda d: d.alters["VPDEAD_U401"] == 1.0),
        (Fault("U401", "gbw_low"), lambda d: d.alters["VPGBW_U401"] <= 0.4),
        (Fault("R203", "value_x4"), lambda d: 3.5 < d.alters["R203"] / 1e5 < 4.5),
        (Fault("C301", "value_x5"), lambda d: 4 < d.alters["C301"] / 10e-9 < 6),
        (Fault(BRIDGE, "q1b~q1e"), lambda d: 0.1 <= d.alters["RBRIDGE_Q1B_Q1E"] <= 10),
    ],
)
def test_apply_fault(fault: Fault, check) -> None:  # type: ignore[no-untyped-def]
    c = get_circuit("channel_strip")
    rng = np.random.default_rng(0)
    d = apply_fault(c, healthy_draw(c, rng), fault, rng)
    assert check(d)


def test_structural_edits_and_netlist() -> None:
    c = get_circuit("channel_strip")
    assert structural_edits(c, HEALTHY_FAULT) == []
    edits = structural_edits(c, Fault("Q502", "be_open"))
    assert edits[0].rewire == ("Q502", 1, "q502_bopen")
    text = fault_netlist(c, Fault("Q502", "be_open"))
    assert "Q502 vcc_d q502_bopen q2e Q2N3904_Q502" in text
    assert ".model Q2N3904_Q502 NPN(" in text
    text = fault_netlist(c, Fault("D101", "open"))
    assert "XD101 " not in text and "RFLT_D101 0 vz" in text
    text = fault_netlist(c, [Fault("C101", "short"), Fault(BRIDGE, "q1b~q1e")], retry=2)
    assert "RFLT_C101 vunreg 0" in text and "RBRIDGE_Q1B_Q1E q1b q1e" in text
    assert "method=gear" in text
    assert "SIN(0 0.0221 1000)" in text
    assert "Q2N3904" in model_cards()


def test_control_lines_structure() -> None:
    c = get_circuit("channel_strip")
    d = healthy_draw(c, np.random.default_rng(1))
    lines, obs = control_lines(c, [(7, d)])
    text = "\n".join(lines)
    assert '@@B 7 op' in text and '@@P 7 hum $curplot' in text and "fourier 1000 v(out)" in text
    assert "alter @VHUMREF[acmag] = 1" in text and "alter @VIN[acmag] = 1" in text
    assert len(obs) == len(spice_observables(c))
    lines_psu, _ = control_lines(get_circuit("psu"), [(0, healthy_draw(get_circuit("psu"),
                                                                       np.random.default_rng(1)))])
    assert not any("fourier" in ln for ln in lines_psu)


def test_parse_output_detects_problems() -> None:
    text = "\n".join([
        "@@B 0 op", "@@P 0 op op1", "@@V 0 op 0=1.5 1=2.5", "@@E 0 op",
        "@@B 0 ac", "@@P 0 ac op1", "@@V 0 ac 2=0.5", "@@E 0 ac",
        "@@B 1 op", "DC solution failed -", "@@P 1 op op2", "@@V 1 op 0=1 1=", "@@E 1 op",
        "@@B 2 op", "@@P 2 op op3", "@@V 2 op 0=1 1=2", "@@E 2 op",
        "@@B 2 thd 3", "@@P 2 thd tran1", " No. Harmonics: 10, THD: 0.5 %, Gridsize: 200",
        " 1       1000        1.25      -3.4        1          0", "@@E 2 thd",
    ])
    expected = {"op": [0, 1], "ac": [2]}
    res = parse_output(text, 4, (0, 1, 2), expected)
    assert not res[0].ok and "wrong plot" in res[0].reason
    assert not res[1].ok and "DC solution failed" in res[1].reason
    assert not res[2].ok and "missing analyses: ac" in res[2].reason
    res2 = parse_output(text, 4, (2,), {"op": [0, 1], "thd": [3]})
    assert res2[2].ok and res2[2].values[3] == 0.5 and res2[2].fundamental == 1.25


def test_simulate_draws_real_ngspice_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    c = get_circuit("tone")
    rng = np.random.default_rng(0)
    draws = [(i, apply_fault(c, healthy_draw(c, rng), HEALTHY_FAULT, rng)) for i in range(2)]
    batch = simulate_draws(c, HEALTHY_FAULT, draws)
    assert all(r.ok for r in batch.results.values()) and not batch.failures
    gain = batch.results[0].values[[o.key for o in spice_observables(c)].index("ac:TP12")]
    assert 20 * math.log10(gain) == pytest.approx(-27.0, abs=1.5)

    # Force every attempt to fail: failures are recorded, never dropped.
    import differential.sim.runner as runner

    monkeypatch.setattr(runner, "_run_ngspice", lambda text, timeout: ("garbage", True))
    batch = runner.simulate_draws(c, HEALTHY_FAULT, draws[:1])
    assert len(batch.failures) == 1 and "timeout" in batch.failures[0]["reason"]
    assert batch.results[0].attempt == 2


def test_measurement_model() -> None:
    assert meas.dmm_resolution(0.3) == 1e-4
    assert meas.dmm_resolution(15.0) == 1e-2
    assert meas.dmm_resolution(250.0) == 0.1
    assert meas.dmm_resolution(2000.0) == 1.0
    assert meas.dmm_sigma(10.0) == pytest.approx((0.05 + 0.02) / 2)
    rng = np.random.default_rng(0)
    r = meas.simulate_reading("dc", 15.15, rng)
    assert abs(r - 15.15) < 0.3 and round(r / 0.01) == pytest.approx(r / 0.01)
    assert meas.simulate_reading("thd", 0.2, rng, fundamental=0.001) == meas.THD_NO_SIGNAL
    assert meas.simulate_reading("ac", 0.0, rng) >= meas.GAIN_FLOOR
    assert meas.simulate_reading("hum", 0.0, rng) >= meas.HUM_FLOOR
    for kind, v in (("dc", 12.0), ("ac", 40.0), ("hum", 0.01), ("thd", 0.5)):
        t = meas.to_engine(kind, v)
        assert meas.from_engine(kind, t) == pytest.approx(v, rel=1e-3)  # floors add in quadrature
        assert meas.engine_noise_sd(kind, t) > 0
    assert meas.to_engine("thd", 0.5, fundamental=0.0) == pytest.approx(2.0)
    assert meas.reading_to_engine("ac", 0.0) == pytest.approx(-60.0)
    assert meas.simulate_lift(True, np.random.default_rng(1)) in (0, 1)
    with pytest.raises(ValueError):
        meas.to_engine("bad", 1.0)


def test_seeds_disjoint_and_deterministic() -> None:
    labels = {split: seed_label("tone", split, 3, 7) for split in SPLIT_INDEX}
    assert len(set(labels.values())) == len(labels)
    a = draw_rng("tone", "train", 3, 7).uniform()
    b = draw_rng("tone", "train", 3, 7).uniform()
    c = draw_rng("tone", "test", 3, 7).uniform()
    assert a == b and a != c
    d1 = make_draw("tone", "train", 3, "R301:open", 0)
    d2 = make_draw("tone", "train", 3, "R301:open", 0)
    assert d1.alters == d2.alters


def test_catalog_jobs_and_run_job() -> None:
    jobs = catalog_jobs("tone", "train", 120)
    assert len(jobs) == 28 * 3 and jobs[0].draws == tuple(range(50))
    key, rows, fails = run_job(Job("tone", "train", "C303:open", 5, (0, 1)))
    assert key.startswith("tone|train|C303:open") and len(rows) == 2 and not fails
    assert rows[0]["ok"] and "liftval:C303" in rows[0]
    key, rows, _ = run_job(Job("tone", "unmodeled_test", "R301:open+C303:short", 100001, (1,)))
    assert rows[0]["ok"] and rows[0]["hypothesis"] == "R301:open+C303:short"


def test_build_deck_draw_ids() -> None:
    c = get_circuit("triode")
    rng = np.random.default_rng(0)
    deck = build_deck(c, Fault("R203", "open"), [(4, healthy_draw(c, rng))])
    assert deck.draw_ids == (4,) and "R203" in deck.text
