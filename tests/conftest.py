"""Shared fixtures: a small, freshly simulated dataset for the tone block.

Tests never read the (uncommitted) Monte Carlo cache; they simulate what they
need, so they pass from a clean clone.
"""

from __future__ import annotations

import pandas as pd
import pytest

from differential.circuits.library import get_circuit
from differential.sim.faults import fault_catalog
from differential.sim.montecarlo import Job, run_job


def _simulate(cid: str, split: str, n: int) -> pd.DataFrame:
    rows = []
    for i, f in enumerate(fault_catalog(get_circuit(cid))):
        _, r, _ = run_job(Job(cid, split, f.id, i, tuple(range(n))))
        rows += r
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def tone_train() -> pd.DataFrame:
    return _simulate("tone", "train", 40)


@pytest.fixture(scope="session")
def tone_val() -> pd.DataFrame:
    return _simulate("tone", "val", 12)


@pytest.fixture(scope="session")
def tone_bundle(tone_train: pd.DataFrame, tone_val: pd.DataFrame):  # type: ignore[no-untyped-def]
    from differential.engine.ambiguity import build_groups
    from differential.engine.bundle import EngineBundle
    from differential.engine.data import build_engine_data
    from differential.engine.generative import GenerativeModel
    from differential.engine.symptom_prior import SymptomModel

    tr = build_engine_data("tone", tone_train)
    va = build_engine_data("tone", tone_val)
    gen = GenerativeModel.fit(tr, max_components=2, workers=1)
    groups = build_groups(gen, va, per_hyp=8)
    sm = SymptomModel.fit("tone", tone_train)
    return EngineBundle(get_circuit("tone"), gen, groups, symptom_model=sm)
