"""Set the unmodeled ("no single fault fits") thresholds on the right population.

The first calibration (eval/train.py) used random validation units, many of them
faults that cause no symptom and almost never trigger the unmodeled hypothesis.
On symptomatic units, the only kind that reaches a bench and the kind in the test
set, its false-alarm rate was about twice the 5 % budget (ADR-029).

Two levels are calibrated, because a complaint concentrates the prior on the
faults that fit it and so changes how much evidence U needs:

* ``unmod_offset_nocomplaint`` for sessions without complaint information (the
  engine alone, the scripted baselines, the folklore prior), calibrated with the
  engine-alone protocol;
* ``unmod_offset`` for sessions whose prior was read from a complaint, calibrated
  with the full system's protocol (complaint rendered from the main template
  bank, read by the offline extractor); a complaint in which the reader finds no
  symptom falls back to the first level, which is fixed by then.

Both use per-case noise seeds as in eval/harness.py and the same units:
negatives are symptomatic single-fault validation units from draws 0-49 (the
pilot split uses draws 50-99, so the pilot checks the thresholds on unseen
units); positives are the unmodeled_val split (double faults and modifications).
Each level is the offset that flags the most positives while flagging at most
5 % of negatives. Both rates rise with the offset, so the search brackets the
largest feasible offset and bisects to 0.1; every evaluated point is recorded.

Usage: python -m eval.recalibrate_unmodeled [--circuits all]
Writes data/models/<circuit>/generative.npz (offsets only) and meta.json.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.config import MODELS_DIR, n_workers
from differential.engine.bundle import load_bundle
from differential.engine.symptom_prior import derive_facts
from differential.nlp.benchmark import MAIN_BANK, PERSONAS, render
from differential.sim.montecarlo import BASE_SEED, load_dataset
from eval.cases import load_cases, symptomatic_faults
from eval.harness import SYSTEMS, bundle_for, run_one

PROBES = [1.0, 2.0, 4.0, 6.0, 8.0, 10.0]  # bracketing pass: stop at the first infeasible one
RESOLUTION = 0.1
FPR_BUDGET = 0.05
CALIBRATION_MAX_DRAW = 50  # validation draws 0-49; the pilot split uses 50-99
N_SINGLE = {COMPOSITE_ID: 200, **dict.fromkeys(BLOCK_IDS, 80)}
# (name, system run by eval/harness.py, GenerativeModel attribute), in calibration order
REGIMES = (("no_complaint", "engine_gen", "unmod_offset_nocomplaint"),
           ("complaint", "hybrid", "unmod_offset"))


def _flag(args: tuple[str, str, dict[str, float], dict[str, Any], dict[str, Any]]
          ) -> tuple[bool, float]:
    cid, system, offsets, row, meta = args
    spec = SYSTEMS[system]
    # same cache key as run_one, so the offsets reach the bundle it runs on
    gen = bundle_for(cid, spec.model_variant).gen
    for attr, value in offsets.items():
        setattr(gen, attr, value)
    r = run_one((spec, cid, row, meta))
    return bool(r["top_group"] == -1), float(r["unmodeled_prob"])


def calibration_singles(cid: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Symptomatic single-fault validation units (draws 0-49) with rendered complaints."""
    sm = load_bundle(cid, with_disc=False).symptom_model
    assert sm is not None and sm.reference is not None
    circ = get_circuit(cid)
    tp_stage = {tp.id: tp.stage for tp in circ.test_points}
    pool = set(symptomatic_faults(sm))
    va = load_dataset(cid, "val")
    va = va[va["ok"] & va["hypothesis"].isin(pool) & (va["draw"] < CALIBRATION_MAX_DRAW)]
    va = va.sample(frac=1.0, random_state=5)
    rng = np.random.default_rng([BASE_SEED, 404, len(cid)])
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for _, r in va.iterrows():
        facts = derive_facts(circ, sm.reference, r)
        if not facts.any:
            continue
        persona = PERSONAS[int(rng.integers(len(PERSONAS)))]
        row = r.to_dict()
        row["case_id"] = f"{cid}-calib-{len(out):04d}"
        meta = {"case_id": row["case_id"], "persona": persona,
                "complaint": render(facts, persona, rng, tp_stage, MAIN_BANK)}
        out.append((row, meta))
        if len(out) >= N_SINGLE[cid]:
            break
    return out


def _evaluate(pool: ProcessPoolExecutor, cid: str, system: str, offsets: dict[str, float],
              off: float, singles: list[tuple[dict[str, Any], dict[str, Any]]],
              unmod: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, float]:
    jobs = [(cid, system, offsets, row, meta) for row, meta in singles + unmod]
    res = list(pool.map(_flag, jobs, chunksize=4))
    fp = sum(f for f, _ in res[:len(singles)])
    tp = sum(f for f, _ in res[len(singles):])
    return {"offset": off, "fpr": fp / len(singles), "tpr": tp / max(len(unmod), 1)}


def calibrate(cid: str) -> dict[str, Any]:
    t0 = time.time()
    singles = calibration_singles(cid)
    udf, umeta = load_cases(cid, "unmodeled_val")
    ub = {m["case_id"]: m for m in umeta}
    unmod = [(r.to_dict(), ub[r["case_id"]]) for _, r in udf[udf["ok"]].iterrows()]
    chosen: dict[str, float] = {}
    report: dict[str, Any] = {}
    with ProcessPoolExecutor(max_workers=n_workers()) as pool:
        for regime, system, attr in REGIMES:
            grid: list[dict[str, float]] = []
            fixed = dict(chosen)

            def probe(off: float) -> bool:
                g = _evaluate(pool, cid, system, {**fixed, attr: off}, off, singles, unmod)  # noqa: B023
                grid.append(g)  # noqa: B023
                print(cid, regime, g, flush=True)  # noqa: B023
                return g["fpr"] <= FPR_BUDGET

            # Both rates rise with the offset, so the best feasible offset is the largest
            # one within the false-alarm budget: bracket it, then bisect to RESOLUTION.
            lo, hi = 0.0, None
            if probe(0.0):
                for off in PROBES:
                    if probe(off):
                        lo = off
                    else:
                        hi = off
                        break
                while hi is not None and hi - lo > RESOLUTION + 1e-9:
                    mid = round(round((lo + hi) / 2 / RESOLUTION) * RESOLUTION, 2)
                    if mid in (lo, hi):
                        break
                    if probe(mid):
                        lo = mid
                    else:
                        hi = mid
            grid.sort(key=lambda g: g["offset"])
            ok = [g for g in grid if g["fpr"] <= FPR_BUDGET]
            best = max(ok, key=lambda g: (g["tpr"], -g["fpr"], g["offset"])) if ok else min(
                grid, key=lambda g: (g["fpr"], -g["tpr"]))
            chosen[attr] = float(best["offset"])
            report[regime] = {"system": system, "chosen": best, "grid": grid}
    # Ablation variants (generative_n*.npz) inherit these offsets in eval/harness.py.
    d = MODELS_DIR / cid
    b = load_bundle(cid, with_disc=False)
    for attr, value in chosen.items():
        setattr(b.gen, attr, value)
    b.gen.save(d / "generative.npz")
    meta_path = d / "meta.json"
    meta = json.loads(meta_path.read_text())
    if "unmodeled_calibration_v1" not in meta:
        meta["unmodeled_calibration_v1"] = meta.get("unmodeled_calibration")
    meta["unmodeled_calibration"] = {
        "protocol": "eval/recalibrate_unmodeled.py; negatives: symptomatic single-fault "
                    f"validation units, draws 0-{CALIBRATION_MAX_DRAW - 1}; positives: "
                    "unmodeled_val split",
        "fpr_budget": FPR_BUDGET, "n_single": len(singles), "n_unmodeled": len(unmod),
        "regimes": report, "offsets": chosen, "seconds": round(time.time() - t0, 1)}
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
    return dict(meta["unmodeled_calibration"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--circuits", default="all")
    args = ap.parse_args()
    cids = [COMPOSITE_ID, *BLOCK_IDS] if args.circuits == "all" else args.circuits.split(",")
    for cid in cids:
        cal = calibrate(cid)
        print(cid, "chosen", json.dumps({r: v["chosen"] for r, v in cal["regimes"].items()}),
              f"{cal['seconds']} s", flush=True)


if __name__ == "__main__":
    main()
