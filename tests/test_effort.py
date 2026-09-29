"""Effort to a confirmed answer (eval/effort.py, ADR-041)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from differential.instruments.simulated import noise_seed
from differential.sim.measurement import simulate_lift
from differential.sim.observables import COST_HV_EXTRA, COST_LIFT
from eval.effort import _confirm_charge


def _bundle() -> SimpleNamespace:
    groups = SimpleNamespace(members=lambda g: {0: ["R1:open"], 1: ["C2:short", "R3:short"]}[g])
    obs = {"lift:R1": SimpleNamespace(cost=COST_LIFT, hv=False, is_lift=True, kind="lift"),
           "lift:C2": SimpleNamespace(cost=COST_LIFT + COST_HV_EXTRA, hv=True, is_lift=True, kind="lift"),
           "lift:R3": SimpleNamespace(cost=COST_LIFT, hv=False, is_lift=True, kind="lift")}
    return SimpleNamespace(groups=groups, observables=obs)


def _row(top_group: int, top: str, truth: str, case: str = "u1") -> SimpleNamespace:
    return SimpleNamespace(top_group=top_group, top_hypothesis=top, truth=truth, case_id=case,
                           keys=json.dumps([]))


def test_unconfirmed_answer_pays_one_unsoldering_test_of_its_leading_part() -> None:
    b = _bundle()
    assert _confirm_charge(b, _row(0, "R1:open", "R1:open"), ["dc:TP1"], (1, 1, 1)) == COST_LIFT
    # a high-voltage part costs the hands-off extra, at the run's weights
    assert _confirm_charge(b, _row(1, "C2:short", "C2:short"), [], (1, 1, 1)) == COST_LIFT + COST_HV_EXTRA
    assert _confirm_charge(b, _row(1, "C2:short", "C2:short"), [], (1, 2, 1)) == 2 * COST_LIFT + COST_HV_EXTRA


def test_a_confirming_lift_already_taken_is_not_charged_again() -> None:
    b = _bundle()
    key = "lift:R1"
    read = simulate_lift(True, np.random.default_rng(noise_seed("u1", key)))
    charge = _confirm_charge(b, _row(0, "R1:open", "R1:open"), [key], (1, 1, 1))
    assert charge == (0.0 if read == 1 else COST_LIFT)


def test_a_flag_names_no_part_and_is_not_charged() -> None:
    assert _confirm_charge(_bundle(), _row(-1, "R1:open", "R1:open"), [], (1, 1, 1)) == 0.0
