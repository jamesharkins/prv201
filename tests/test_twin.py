"""The healthy-channel comparison baseline (eval/twin.py, the session's "twin" policy)."""

from __future__ import annotations

import pytest

from differential.circuits.library import COMPOSITE_ID, get_circuit
from differential.engine.bundle import load_bundle
from differential.engine.compare import channels_differ
from differential.engine.session import DiagnosisSession
from differential.sim.montecarlo import CASE_INDEX_BASE, make_draw
from eval.twin import _is_supply_key, _supply_refs, twin_draw


def test_channels_differ_rule() -> None:
    assert not channels_differ("dc", 10.0, 10.5)[0]  # 5% apart
    assert channels_differ("dc", 10.0, 12.0)[0]  # 17% apart
    assert not channels_differ("dc", 0.01, 0.04)[0]  # 30 mV: below the 50 mV floor
    assert channels_differ("ac", 1.0, 1.2)[0]  # 1.6 dB
    assert not channels_differ("ac", 1.0, 1.05)[0]  # 0.4 dB
    assert not channels_differ("hum", 0.0, 1e-9)[0]  # both at the noise floor


def test_twin_shares_the_supply_and_draws_its_own_channel() -> None:
    c = get_circuit(COMPOSITE_ID)
    refs = _supply_refs(c)
    hyp_index, hyp, draw = CASE_INDEX_BASE + 7, "R502:open", 0
    a = make_draw(COMPOSITE_ID, "pilot", hyp_index, hyp, draw)
    b, target = twin_draw(c, "pilot", hyp_index, hyp, draw)
    assert target.mode == "healthy"  # a channel fault stays in channel A
    supply = [k for k in a.alters if _is_supply_key(k, refs)]
    assert supply and all(b.alters[k] == a.alters[k] for k in supply)
    channel = [k for k in a.alters if not _is_supply_key(k, refs)]
    assert sum(b.alters[k] != a.alters[k] for k in channel) > len(channel) // 2
    nominal = c.component("R502").nominal
    assert nominal is not None
    assert b.alters["R502"] == pytest.approx(nominal, rel=0.2)  # a healthy part in channel B
    assert a.alters["R502"] > 10 * nominal  # open in channel A


def test_a_supply_fault_is_in_both_channels() -> None:
    c = get_circuit(COMPOSITE_ID)
    _, target = twin_draw(c, "pilot", CASE_INDEX_BASE + 2, "C106:short", 2)
    assert not isinstance(target, list) and target.ref == "C106" and target.mode == "short"


def test_twin_policy_needs_the_other_channel_and_charges_both_readings() -> None:
    bundle = load_bundle(COMPOSITE_ID, with_disc=False)
    with pytest.raises(ValueError):
        DiagnosisSession(bundle, policy="twin")
    s = DiagnosisSession(bundle, policy="twin", twin_reading=lambda o: 0.0)
    once = DiagnosisSession(bundle, policy="twin", twin_reading=lambda o: 0.0, twin_charge_both=False)
    base = bundle.observables
    assert s._obs["ac:TP22"].cost == 2 * base["ac:TP22"].cost  # a channel point: both read
    assert s._obs["dc:TP4"].cost == base["dc:TP4"].cost  # the shared supply: read once
    assert s._obs["lift:C203"].cost == base["lift:C203"].cost  # one part unsoldered
    assert once._obs["ac:TP22"].cost == base["ac:TP22"].cost


def test_twin_compares_the_outputs_first_then_traces_the_differing_channel() -> None:
    bundle = load_bundle(COMPOSITE_ID, with_disc=False)
    healthy = {"ac:TP22": 1.0, "ac:TP17": 1.0, "ac:TP12": 1.0, "ac:TP10": 1.0}
    s = DiagnosisSession(bundle, policy="twin", twin_reading=lambda o: healthy.get(o.key, 1.0))
    rec = s.recommend()
    assert rec is not None and rec.key == "ac:TP22"
    s.record("ac:TP22", 0.2)  # the faulty channel's output is 14 dB down
    avail = {o.key for o in s.candidates()}
    # (recommend() may unsolder first once one suspect holds 40% of the belief)
    assert s._twin_next(avail) == "ac:TP12"  # half-split of the four stage outputs
    s.record("ac:TP12", 1.0)  # alike at the tone-control output
    assert s._twin_next(avail - {"ac:TP12"}) == "ac:TP17"  # so the op-amp stage or later
    s2 = DiagnosisSession(bundle, policy="twin", twin_reading=lambda o: 1.0)
    s2.record("ac:TP22", 1.02)  # outputs alike: the chart order, supply first
    assert s2._twin_next({o.key for o in s2.candidates()}) is None
