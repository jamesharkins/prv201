"""Second feasibility pilot, run before the targets are locked (never on test data).

Adds what the M1 review asked for: a half-split tracing baseline, calibration over
every step (not only at the stop), the unmodeled detector's operating point, the
folklore-prior robustness check, and the widened-tolerance stress set. Uses the
pilot split (symptomatic validation units, draws 50-99), the pilot_wide split and
the unmodeled_pilot split; none of them is used by any calibration step that the
pilot checks (ADR-029).
Writes metrics.json section "pilot2" and results/pilot2.log.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from eval import metrics_io
from eval.harness import SYSTEMS, bundle_for, run_system, unmodeled_outcome
from eval.stats import auroc, ece

PILOT_SYSTEMS = ["engine_gen", "hybrid", "fixed_order", "half_split", "random", "recap_prior"]
CIRCUITS = [COMPOSITE_ID, *BLOCK_IDS]


def population_check(cid: str = COMPOSITE_ID, n: int = 200) -> dict[str, float]:
    """Why the first pilot (units of every catalog fault) scored higher than this one
    (symptomatic units only): the engine alone on validation units (draws 50-99) of
    faults that usually cause no symptom, next to its score on the pilot split."""
    from concurrent.futures import ProcessPoolExecutor

    from differential.config import n_workers
    from differential.sim.montecarlo import load_dataset
    from eval.cases import symptom_model
    from eval.harness import run_one

    sm = symptom_model(cid)
    assert sm.symptomatic_rate is not None
    latent = {h for h, r in zip(sm.hypotheses, sm.symptomatic_rate, strict=True)
              if h != "healthy" and r < 0.5}
    va = load_dataset(cid, "val")
    va = va[va["ok"] & va["hypothesis"].isin(latent) & (va["draw"] >= 50)]
    va = va.sample(min(n, len(va)), random_state=13)
    jobs = []
    for i, (_, r) in enumerate(va.iterrows()):
        row = r.to_dict()
        row["case_id"] = f"{cid}-latent-{i:04d}"
        jobs.append((SYSTEMS["engine_gen"], cid, row, {"case_id": row["case_id"]}))
    with ProcessPoolExecutor(max_workers=n_workers()) as pool:
        res = pd.DataFrame(list(pool.map(run_one, jobs, chunksize=4)))
    return {"n": len(res), "engine_top1_no_symptom_faults": float(res["correct"].mean()),
            "engine_mean_cost_no_symptom_faults": float(res["cost"].mean()),
            "no_symptom_faults": len(latent),
            "faults": len([h for h in sm.hypotheses if h != "healthy"])}


def step_ece(df: pd.DataFrame) -> float:
    conf, corr = [], []
    for m, c in zip(df["trace_mass"], df["trace_correct"], strict=True):
        conf += json.loads(m)
        corr += json.loads(c)
    return float(ece(np.array(conf), np.array(corr, dtype=float))[0])


def main() -> None:
    t0 = time.time()
    runs: dict[str, dict[str, pd.DataFrame]] = {s: {} for s in PILOT_SYSTEMS}
    for cid in CIRCUITS:
        for s in PILOT_SYSTEMS:
            runs[s][cid] = run_system(SYSTEMS[s], cid, split="pilot")
        print(cid, "done", round(time.time() - t0), "s", flush=True)
    pooled = {s: pd.concat(runs[s].values(), ignore_index=True) for s in PILOT_SYSTEMS}
    out: dict[str, object] = {"protocol": "symptomatic validation units (pilot split), "
                                          "models fit on training draws; never test data",
                              "n_cases": {cid: len(runs["hybrid"][cid]) for cid in CIRCUITS}}
    per = {}
    for s, df in pooled.items():
        per[s] = {"top1": float(df["correct"].mean()), "top3": float(df["top3"].mean()),
                  "mean_cost": float(df["cost"].mean())}
    out["pooled"] = per
    out["n_total"] = len(pooled["hybrid"])
    out["hybrid_misses"] = int((~pooled["hybrid"]["correct"].astype(bool)).sum())
    out["hybrid_false_flags"] = int((pooled["hybrid"]["top_group"] == -1).sum())
    cs = {s: runs[s][COMPOSITE_ID] for s in PILOT_SYSTEMS}
    out["channel_strip"] = {s: {"top1": float(d["correct"].mean()), "mean_cost": float(d["cost"].mean())}
                            for s, d in cs.items()}
    eg = per["engine_gen"]
    out["effort_ratio_vs_fixed_order"] = eg["mean_cost"] / per["fixed_order"]["mean_cost"]
    out["effort_ratio_vs_half_split"] = eg["mean_cost"] / per["half_split"]["mean_cost"]
    out["effort_ratio_vs_random"] = eg["mean_cost"] / per["random"]["mean_cost"]
    out["hybrid_vs_engine_effort_ratio"] = per["hybrid"]["mean_cost"] / eg["mean_cost"]
    out["cs_margin_vs_fixed_order"] = (out["channel_strip"]["hybrid"]["top1"]  # type: ignore[index]
                                       - out["channel_strip"]["fixed_order"]["top1"])  # type: ignore[index]
    out["cs_margin_vs_random"] = (out["channel_strip"]["hybrid"]["top1"]  # type: ignore[index]
                                  - out["channel_strip"]["random"]["top1"])  # type: ignore[index]
    out["cs_margin_vs_half_split"] = (out["channel_strip"]["hybrid"]["top1"]  # type: ignore[index]
                                      - out["channel_strip"]["half_split"]["top1"])  # type: ignore[index]
    out["hybrid_step_ece"] = step_ece(pooled["hybrid"])
    out["hybrid_stop_ece"] = float(ece(pooled["hybrid"]["confidence"].to_numpy(),
                                       pooled["hybrid"]["correct"].to_numpy(dtype=float))[0])
    out["recap_prior_top1_delta"] = per["recap_prior"]["top1"] - eg["top1"]
    steps = np.concatenate([json.loads(x) for x in cs["hybrid"]["step_seconds"]])
    out["cs_step_seconds_p95"] = float(np.percentile(steps, 95))
    # Stress set: hybrid on widened tolerances vs hybrid on the nominal pilot units.
    wide = run_system(SYSTEMS["hybrid"], COMPOSITE_ID, split="pilot_wide")
    out["wide_top1"] = float(wide["correct"].mean())
    out["wide_top1_drop"] = float(cs["hybrid"]["correct"].mean() - wide["correct"].mean())
    out["wide_n"] = len(wide)
    # Unmodeled detector on the unmodeled_pilot split (never used for calibration)
    # against the pilot's single-fault units; full system (T13) and engine alone.
    for s in ("hybrid", "engine_gen"):
        pos, neg, outcomes = [], [], []
        for cid in CIRCUITS:
            u = run_system(SYSTEMS[s], cid, split="unmodeled_pilot")
            b = bundle_for(cid)
            pos += list(u["unmodeled_prob"])
            outcomes += [unmodeled_outcome(b, t, int(g))
                         for t, g in zip(u["truth"], u["top_group"], strict=True)]
            neg += list(runs[s][cid]["unmodeled_prob"])
        oc = pd.Series(outcomes)
        out[f"{s}_unmodeled_auroc"] = auroc(np.array(pos), np.array(neg))
        out[f"{s}_unmodeled_flag_rate"] = float((oc == "flagged").mean())
        out[f"{s}_unmodeled_faulty_part_rate"] = float((oc == "faulty_part").mean())
        out[f"{s}_unmodeled_misleading_rate"] = float((oc == "misleading").mean())
        out[f"{s}_unmodeled_n"] = len(pos)
        out[f"{s}_single_false_flag_rate"] = float(np.mean(pooled[s]["top_group"] == -1))
    out["population_check"] = population_check()
    out["seconds"] = time.time() - t0
    metrics_io.update("pilot2", out)
    text = json.dumps(out, indent=1, default=float)
    (metrics_io.METRICS.parent / "pilot2.log").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
