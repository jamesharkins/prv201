"""Worst-case voltage audit of every test point (safety hazard model).

A unit on the bench is faulted by definition, and a fault can put high voltage on
a node that is low-voltage in normal operation (a leaky coupling capacitor puts
B+ on the next grid; a cut-off tube lets its plate rise to B+). For every test
point we therefore take the largest |DC| reading over every catalog fault and
every tolerance draw in the training simulations.

Outputs
  differential/safety/hv_map.json  used at runtime by the safety layer
  results/metrics.json  section "hv_audit"
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from differential.circuits.library import CIRCUIT_IDS, get_circuit
from differential.safety.rules import HV_THRESHOLD_V
from differential.sim.montecarlo import load_dataset
from eval import metrics_io

HV_MAP = Path(__file__).resolve().parent.parent / "differential" / "safety" / "hv_map.json"


def audit(cid: str) -> dict[str, object]:
    c = get_circuit(cid)
    df = load_dataset(cid, "train")
    df = df[df["ok"]]
    healthy = df[df["hypothesis"] == "healthy"]
    out: dict[str, object] = {}
    for tp in c.test_points:
        col = f"dc:{tp.id}"
        if col not in df.columns:
            continue
        v = np.abs(df[col].to_numpy(dtype=float))
        hv_rows = df[np.abs(df[col]) > HV_THRESHOLD_V]
        faults = sorted(set(hv_rows["hypothesis"]) - {"healthy"})
        out[tp.id] = {
            "name": tp.name,
            "flag_hv": tp.hv,
            "normal_max_v": round(float(np.abs(healthy[col]).max()), 2),
            "worst_case_v": round(float(np.nanmax(v)), 2),
            "faults_above_threshold": len(faults),
            "example_faults": faults[:6],
            "hazard": "hv" if tp.hv else ("hv_under_fault" if faults else "lv"),
        }
    return out


def main() -> None:
    result = {cid: audit(cid) for cid in CIRCUIT_IDS}
    HV_MAP.write_text(json.dumps(result, indent=1, sort_keys=True))
    summary = {}
    for cid, tps in result.items():
        hazards = [v["hazard"] for v in tps.values()]  # type: ignore[index]
        summary[cid] = {
            "test_points": len(tps),
            "hv_normal": hazards.count("hv"),
            "hv_under_fault": hazards.count("hv_under_fault"),
            "low_voltage": hazards.count("lv"),
            "points": tps,
        }
    metrics_io.update("hv_audit", {"threshold_v": HV_THRESHOLD_V, "circuits": summary})
    for cid, s in summary.items():
        print(cid, {k: v for k, v in s.items() if k != "points"})
        for tp, info in s["points"].items():  # type: ignore[union-attr]
            if info["hazard"] != "lv":
                print(f"   {tp:5s} {info['hazard']:15s} normal {info['normal_max_v']:7.1f} V  worst "
                      f"{info['worst_case_v']:7.1f} V  faults>{HV_THRESHOLD_V:.0f}V: "
                      f"{info['faults_above_threshold']}  e.g. {info['example_faults'][:3]}")


if __name__ == "__main__":
    main()
