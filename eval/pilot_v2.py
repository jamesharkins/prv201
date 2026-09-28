"""Second feasibility pilot, run before the targets are locked (never on test data).

Adds what the M1 review asked for: a half-split tracing baseline, calibration over
every step (not only at the stop), the unmodeled detector's operating point, the
folklore-prior robustness check, and the widened-tolerance stress set. Uses the
pilot split (units simulated from their own seed stream with the test protocol),
the pilot_wide split and the unmodeled_pilot split; none of them is used for any
training, calibration or tuning (ADR-029, ADR-030).
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


def by_symptom_rate(df: pd.DataFrame, cid: str) -> pd.DataFrame:
    """Attach each unit's fault symptom rate (share of training draws with a symptom)."""
    from eval.cases import symptom_model

    sm = symptom_model(cid)
    assert sm.symptomatic_rate is not None
    rate = dict(zip(sm.hypotheses, sm.symptomatic_rate, strict=True))
    return df.assign(symptom_rate=[float(rate.get(t, np.nan)) for t in df["truth"]])


BANDS = [(0.0, 0.25), (0.25, 0.5), (0.5, 1.0001)]


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
    out: dict[str, object] = {"protocol": "pilot split: symptomatic units simulated from their own "
                                          "seed stream with the test protocol; never test data",
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
    # Accuracy by how often the true fault causes a symptom (the test set includes
    # rarely-symptomatic faults in proportion to how often they reach a bench).
    rated = pd.concat([by_symptom_rate(runs["hybrid"][c], c) for c in CIRCUITS], ignore_index=True)
    out["hybrid_by_symptom_rate"] = {
        f"{lo:.2f}-{min(hi, 1.0):.2f}": {
            "n": int(((rated.symptom_rate > lo) & (rated.symptom_rate <= hi)).sum()),
            "top1": float(rated[(rated.symptom_rate > lo) & (rated.symptom_rate <= hi)]["correct"].mean())}
        for lo, hi in BANDS}
    out["seconds"] = time.time() - t0
    metrics_io.update("pilot2", out)
    text = json.dumps(out, indent=1, default=float)
    (metrics_io.METRICS.parent / "pilot2.log").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
