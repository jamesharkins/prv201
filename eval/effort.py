"""Effort to a confirmed answer (ADR-041).

A technician replaces a part only after confirming it, usually by unsoldering it and
testing it out of circuit. The scripted procedures (fixed-order chart, half-split
tracing) end that way (they unsolder their leading suspect once it holds half the
belief, ADR-033); the engine and random probing stop when the belief is high enough,
often without unsoldering anything. Comparing their raw efforts therefore charges the
scripts for a confirmation the others skip (round-4 review).

For every diagnosis this module splits the effort into probing (in-circuit readings)
and unsoldering (out-of-circuit tests), and computes the effort to a confirmed answer:
the session's effort plus one unsoldering test of the named group's leading part,
unless the session already unsoldered a part of the named group and found it
defective. A "no single fault fits" call names no part and is charged nothing (the
unit goes to a senior technician; the flag rate is reported beside the effort).
Lift readings are recomputed exactly as the harness took them (same noise seed), so
the accounting needs no new runs.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from differential.instruments.simulated import noise_seed
from differential.sim.faults import parse_fault_id
from differential.sim.measurement import simulate_lift
from differential.sim.observables import scaled_cost
from eval.harness import bundle_for


def _lift_ref(key: str) -> str | None:
    return key.split(":", 1)[1] if key.startswith("lift:") else None


def breakdown(df: pd.DataFrame, cid: str,
              cost_scale: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> pd.DataFrame:
    """Add probe_cost, lift_cost, confirm_cost and confirmed_cost to one circuit's runs.
    ``cost_scale`` is the run's (scope, lift, hv) weight scaling, so the confirming test
    is charged at the same weights as the session's own readings."""
    if df.empty:
        return df.assign(probe_cost=[], lift_cost=[], confirm_cost=[], confirmed_cost=[])
    bundle = bundle_for(cid)
    obs = bundle.observables
    probe, lift, confirm = [], [], []
    for r in df.itertuples(index=False):
        keys = json.loads(r.keys)
        spent = json.loads(r.trace_cost)
        step = np.diff([0.0, *spent]) if spent else np.zeros(0)
        if len(step) != len(keys):  # every step takes one reading; fall back to list costs
            step = np.array([obs[k].cost for k in keys])
        is_lift = np.array([k.startswith("lift:") for k in keys], dtype=bool)
        probe.append(float(step[~is_lift].sum()) if len(step) else 0.0)
        lift.append(float(step[is_lift].sum()) if len(step) else 0.0)
        confirm.append(_confirm_charge(bundle, r, keys, cost_scale))
    out = df.assign(probe_cost=probe, lift_cost=lift, confirm_cost=confirm)
    return out.assign(confirmed_cost=out["cost"] + out["confirm_cost"])


def _confirm_charge(bundle: Any, r: Any, keys: list[str],
                    cost_scale: tuple[float, float, float]) -> float:
    if int(r.top_group) == -1:
        return 0.0
    members = [h for h in bundle.groups.members(int(r.top_group)) if h != "healthy"]
    named = {parse_fault_id(h).ref for h in members}
    if not named:
        return 0.0
    truth_refs = {parse_fault_id(f).ref for f in str(r.truth).split("+")} if r.truth != "healthy" else set()
    for k in keys:
        ref = _lift_ref(k)
        if ref in named:
            rng = np.random.default_rng(noise_seed(str(r.case_id), k))
            if simulate_lift(ref in truth_refs, rng) == 1:
                return 0.0
    lead = str(r.top_hypothesis)
    ref = parse_fault_id(lead).ref if lead != "healthy" else sorted(named)[0]
    if ref not in named:
        ref = sorted(named)[0]
    return float(scaled_cost(bundle.observables[f"lift:{ref}"], *cost_scale))


def with_effort(runs: dict[str, pd.DataFrame],
                cost_scale: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> dict[str, pd.DataFrame]:
    return {cid: breakdown(df, cid, cost_scale) for cid, df in runs.items()}


def summary(frames: dict[str, pd.DataFrame], weights: dict[str, float]) -> dict[str, float]:
    """Test-mix-weighted means of the effort parts and the share of answers that needed
    a confirming test."""
    def w(col: str, f: Any = None) -> float:
        return sum(weights[c] * float((f(df) if f else df[col]).mean()) for c, df in frames.items())

    return {"effort": w("cost"), "probing": w("probe_cost"), "unsoldering": w("lift_cost"),
            "confirming_charge": w("confirm_cost"), "confirmed_effort": w("confirmed_cost"),
            "share_charged": w("", lambda d: (d["confirm_cost"] > 0).astype(float)),
            "flagged": w("", lambda d: (d["top_group"] == -1).astype(float))}
