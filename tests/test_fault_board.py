from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def test_draw_is_sealed_random_and_buildable(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("draw_faults", "hardware/fault_board/draw_faults.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    units = mod.draw(7)
    assert len(units) == 60 and {b for _, b, _ in units} == {"A", "B", "C"}
    assert not any("beta_low" in f for _, _, f in units)
    for board in "ABC":
        faults = [f for _, b, f in units if b == board]
        assert len(faults) == len(set(faults)) == 20
    assert mod.draw(7) == units and mod.draw(8) != units
    mod.main(["--seed", "7", "--out-dir", str(tmp_path)])
    rows = list(csv.DictReader((tmp_path / "recording_sheet.csv").open()))
    assert rows and all(r["value"] == "" for r in rows)
    assert len(list(csv.DictReader((tmp_path / "sealed_key.csv").open()))) == 60


def test_replay_on_simulated_recordings() -> None:
    """Recordings made from simulated units must be diagnosed like the simulator's own units."""
    from differential.sim.measurement import simulate_reading
    from eval.cases import load_cases
    from eval.fault_board import evaluate

    df, _ = load_cases("driver", "pilot")
    df = df[df["ok"]].head(12)
    rng = np.random.default_rng(0)
    units, key = {}, {}
    keys = [c for c in df.columns if ":" in c and c.split(":")[0] in ("dc", "ac", "ac20", "ac20k", "thd")]
    for i, (_, r) in enumerate(df.iterrows()):
        u = f"U{i:03d}"
        units[u] = {"board": "A", "notes": [],
                    "readings": {k: simulate_reading(k.split(":")[0], float(r[k]), rng, float(r["fundamental"]))
                                 for k in keys}}
        key[u] = str(r["hypothesis"])
    out = evaluate(units, key)
    eng = out["methods"]["engine"]
    assert out["n_faults"] == 12 and 0 <= out["engine_top1_correct"] <= 12
    assert eng["top1"]["value"] >= 0.5  # the engine should mostly name simulated faults
    assert set(out["methods"]) == {"engine", "fixed_order", "half_split", "random"}
