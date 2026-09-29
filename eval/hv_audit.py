"""Worst-case voltage audit of every test point (safety hazard model).

A unit on the bench is faulted by definition, and a fault can put high voltage on
a node that is low-voltage in normal operation (a leaky coupling capacitor puts
B+ on the next grid; a cut-off tube lets its plate rise to B+). For every test
point we therefore take the largest |DC| voltage over every catalog fault and
every tolerance draw in the training simulations. The audit uses the unloaded node
voltage (``open:`` columns: what a finger would touch), not the meter reading,
which a 10 MOhm meter pulls down at high-impedance nodes; the larger of the two
is taken, so the audit never sees less than either.

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
    out: dict[str, object] = {}
    for tp in c.test_points:
        col = f"dc:{tp.id}"
        if col not in df.columns:
            continue
        cols = [col] + ([f"open:{tp.id}"] if f"open:{tp.id}" in df.columns else [])
        mag = df[cols].abs().max(axis=1)
        v = mag.to_numpy(dtype=float)
        hv_rows = df[mag > HV_THRESHOLD_V]
        faults = sorted(set(hv_rows["hypothesis"]) - {"healthy"})
        worst_row = df.iloc[int(np.nanargmax(v))]
        out[tp.id] = {
            "name": tp.name,
            "flag_hv": tp.hv,
            "normal_max_v": round(float(mag[df["hypothesis"] == "healthy"].max()), 2),
            "worst_case_v": round(float(np.nanmax(v)), 2),
            "faults_above_threshold": len(faults),
            "example_faults": faults[:6],
            "worst_fault": str(worst_row["hypothesis"]),
            "hazard": "hv" if tp.hv else ("hv_under_fault" if faults else "lv"),
        }
    return out


def out_of_catalog_check(splits: tuple[str, ...]) -> dict[str, object]:
    """Units outside the catalog (double faults, wrong-value parts, solder bridges) with a
    point above 50 V that the hazard map marks as low voltage (round-6 review). The map is
    built from single catalog faults only, so this is where it could miss a hazard."""
    from differential.safety.hazards import hazard
    from eval.cases import load_cases
    from eval.lock import require_lock

    if any("test" in s for s in splits):
        require_lock("check test units against the hazard map")
    per: dict[str, object] = {}
    units = misses = 0
    for cid in CIRCUIT_IDS:
        found: list[dict[str, object]] = []
        n = 0
        for split in splits:
            df, _ = load_cases(cid, split)
            df = df[df["ok"]]
            n += len(df)
            tps = [c.split(":", 1)[1] for c in df.columns if c.startswith("dc:")]
            low = [tp for tp in tps if not hazard(cid, tp).high_voltage]
            for _, row in df.iterrows():
                for tp in low:
                    cols = [f"dc:{tp}"] + ([f"open:{tp}"] if f"open:{tp}" in df.columns else [])
                    v = max(abs(float(row[c])) for c in cols)
                    if v > HV_THRESHOLD_V:
                        found.append({"split": split, "seed": str(row["seed"]),
                                      "hypothesis": str(row["hypothesis"]), "tp": tp, "volts": round(v, 1)})
        units += n
        misses += len({(f["split"], f["seed"]) for f in found})
        per[cid] = {"units": n, "misses": found}
    return {"splits": list(splits), "units": units, "units_with_miss": misses, "circuits": per}


def main() -> None:
    import sys

    if "--out-of-catalog" in sys.argv:
        splits = tuple(sys.argv[sys.argv.index("--out-of-catalog") + 1:]) or ("unmodeled_val",
                                                                              "unmodeled_pilot")
        res = out_of_catalog_check(splits)
        key = "out_of_catalog_test" if any("test" in s for s in splits) else "out_of_catalog"
        metrics_io.update(f"hv_audit_{key}", res)
        print(f"{res['units_with_miss']} of {res['units']} out-of-catalog units put more than "
              f"{HV_THRESHOLD_V:.0f} V on a point the hazard map calls low voltage ({', '.join(splits)})")
        return
    result = {cid: audit(cid) for cid in CIRCUIT_IDS}
    HV_MAP.write_text(json.dumps(result, indent=1, sort_keys=True))
    summary = {}
    from differential.agent.format import fault_label

    for cid, tps in result.items():
        hazards = [v["hazard"] for v in tps.values()]  # type: ignore[index]
        summary[cid] = {
            "test_points": len(tps),
            "hv_normal": hazards.count("hv"),
            "hv_under_fault": hazards.count("hv_under_fault"),
            "low_voltage": hazards.count("lv"),
            "points": tps,
        }
        # The clearest example of a fault-only hazard: the normally low-voltage point
        # with the highest worst case, and the fault that produces it.
        fault_only = [(tp, v) for tp, v in tps.items() if v["hazard"] == "hv_under_fault"]  # type: ignore[index]
        if fault_only:
            tp, v = max(fault_only, key=lambda kv: kv[1]["worst_case_v"])  # type: ignore[index]
            summary[cid]["showcase"] = {
                "tp": tp, "name": v["name"], "normal_max_v": v["normal_max_v"],  # type: ignore[index]
                "worst_case_v": v["worst_case_v"], "fault": v["worst_fault"],  # type: ignore[index]
                "fault_label": fault_label(str(v["worst_fault"])),  # type: ignore[index]
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
