"""Replay every method on readings recorded from the hardware fault boards (target T7).

Protocol: hardware/fault_board/validation_protocol.md. Each unit is one fault inserted
into one board; every measurement was recorded once. Each method is replayed on those
recordings, with the 40-unit budget and no unsoldering tests, so every reading it
uses is real. Group-aware top-1/top-3 with exact intervals; the engine's top-1 lower
bound decides T7.

    python -m eval.fault_board --sheet recording_sheet.csv --key sealed_key.csv \\
        [--healthy healthy_sheets.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from differential.engine.bundle import EngineBundle, load_bundle
from differential.engine.session import DiagnosisSession
from eval import metrics_io
from eval.stats import exact_binomial

CIRCUIT = "driver"
METHODS = {"engine": "eig_per_cost", "fixed_order": "fixed_order", "half_split": "half_split",
           "random": "random"}


def read_sheet(path: Path) -> dict[str, dict[str, Any]]:
    """unit -> {"board": ..., "readings": {key: value}, "notes": [...]}. Blank values are
    left out (the method then cannot take that reading)."""
    units: dict[str, dict[str, Any]] = defaultdict(lambda: {"readings": {}, "notes": []})
    with path.open() as fh:
        for row in csv.DictReader(fh):
            u = units[row["unit"]]
            u["board"] = row.get("board", "")
            if str(row.get("value", "")).strip():
                u["readings"][row["key"]] = float(row["value"])
            if str(row.get("notes", "")).strip():
                u["notes"].append(f"{row['key']}: {row['notes']}")
    return dict(units)


def read_key(path: Path) -> dict[str, str]:
    with path.open() as fh:
        return {row["unit"]: row["fault"] for row in csv.DictReader(fh)}


def replay(bundle: EngineBundle, readings: dict[str, float], policy: str, seed: int) -> dict[str, Any]:
    """One diagnosis on recorded readings; a reading missing from the sheet is not offered."""
    s = DiagnosisSession(bundle, policy=policy, seed=seed, allow_lifts=False)
    for key in list(s._obs):
        if key not in readings:
            s._obs = {k: o for k, o in s._obs.items() if k != key}
    res = s.run(lambda o: float(readings[o.key]))
    return {"top_group": res.top_group, "ranked": [g for g, _ in res.ranked_groups],
            "cost": res.cost, "unmodeled_prob": res.unmodeled_prob, "steps": res.steps}


def evaluate(units: dict[str, dict[str, Any]], key: dict[str, str],
             bundle: EngineBundle | None = None) -> dict[str, Any]:
    bundle = bundle or load_bundle(CIRCUIT, with_disc=False)
    per_method: dict[str, list[dict[str, Any]]] = {m: [] for m in METHODS}
    for i, (unit, u) in enumerate(sorted(units.items())):
        truth = key[unit]
        tg = int(bundle.groups.group_of[bundle.hypotheses.index(truth)])
        for name, policy in METHODS.items():
            r = replay(bundle, u["readings"], policy, seed=20260928 + i)
            per_method[name].append({"unit": unit, "board": u.get("board", ""), "truth": truth,
                                     "correct": r["top_group"] == tg, "top3": tg in r["ranked"][:3],
                                     "flagged": r["top_group"] == -1, "cost": r["cost"]})
    out: dict[str, Any] = {"status": "measured", "n_faults": len(units), "methods": {}}
    for name, rows in per_method.items():
        k1 = sum(r["correct"] for r in rows)
        k3 = sum(r["top3"] for r in rows)
        boards = sorted({r["board"] for r in rows})
        out["methods"][name] = {
            "top1": exact_binomial(k1, len(rows)).as_dict(),
            "top3": exact_binomial(k3, len(rows)).as_dict(),
            "flagged": sum(r["flagged"] for r in rows), "mean_cost": float(np.mean([r["cost"] for r in rows])),
            "by_board": {b: {"n": sum(r["board"] == b for r in rows),
                             "top1": sum(r["correct"] for r in rows if r["board"] == b)} for b in boards},
        }
    eng = per_method["engine"]
    out["engine_top1_correct"] = sum(r["correct"] for r in eng)
    half = {r["unit"]: r["correct"] for r in per_method["half_split"]}
    out["paired_vs_half_split"] = {
        "engine_only": sum(r["correct"] and not half[r["unit"]] for r in eng),
        "half_split_only": sum(half[r["unit"]] and not r["correct"] for r in eng)}
    out["units"] = per_method
    return out


def healthy_check(units: dict[str, dict[str, Any]], bundle: EngineBundle) -> dict[str, Any]:
    """Each healthy board's readings against the simulated healthy distribution, and how
    often the engine, given every reading, would say that no single fault fits."""
    h = bundle.hypotheses.index("healthy")
    rows = []
    for unit, u in sorted(units.items()):
        s = DiagnosisSession(bundle, allow_lifts=False)
        z = {}
        for key, v in u["readings"].items():
            if key in s._obs:
                pred = s.expected_reading(key, "healthy")
                if pred is not None:
                    mean, lo, hi = pred
                    z[key] = {"value": v, "predicted": mean, "in_95": bool(lo <= v <= hi)}
        for key, v in u["readings"].items():
            if key in s._obs:
                s.record(key, v)
        post = s.posterior()
        rows.append({"unit": unit, "board": u.get("board", ""),
                     "in_95_share": float(np.mean([x["in_95"] for x in z.values()])) if z else None,
                     "p_healthy": float(post[h]), "p_no_single_fault": float(post[-1]), "readings": z})
    return {"boards": rows,
            "flagged_no_single_fault": sum(r["p_no_single_fault"] >= 0.5 for r in rows)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sheet", type=Path, required=True)
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("--healthy", type=Path)
    a = ap.parse_args(argv)
    bundle = load_bundle(CIRCUIT, with_disc=False)
    out = evaluate(read_sheet(a.sheet), read_key(a.key), bundle)
    if a.healthy:
        out["healthy_check"] = healthy_check(read_sheet(a.healthy), bundle)
    metrics_io.update("fault_board", out)
    print(json.dumps({k: v for k, v in out.items() if k != "units"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
