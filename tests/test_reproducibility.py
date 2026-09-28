"""Stored simulation rows can be regenerated exactly from their seeds."""

from __future__ import annotations

import math

import pytest

from differential.config import SIM_DIR
from differential.sim.montecarlo import Job, load_dataset, run_job

pytestmark = pytest.mark.skipif(not (SIM_DIR / "driver__train.parquet").exists(),
                                reason="simulation datasets not present")


@pytest.mark.parametrize("cid", ["driver", "triode"])
def test_stored_rows_regenerate_exactly(cid: str) -> None:
    df = load_dataset(cid, "train")
    df = df[df["ok"]]
    for _, row in df.sample(2, random_state=3).iterrows():
        _, rows, failures = run_job(Job(cid, "train", str(row["hypothesis"]),
                                        int(row["hyp_index"]), (int(row["draw"]),)))
        assert not failures
        new = rows[0]
        keys = [k for k in new if ":" in k and not k.startswith("liftval:")]
        for k in keys:
            a, b = float(new[k]), float(row[k])
            # Datasets store float32; ngspice prints six significant digits.
            assert (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=2e-6,
                                                                     abs_tol=1e-9), (k, a, b)
