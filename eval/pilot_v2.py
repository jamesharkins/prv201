"""Second feasibility pilot, run before the targets are locked (never on test data).

Adds what the M1 review asked for: a half-split tracing baseline, calibration over
every step (not only at the stop), the unmodeled detector's operating point, the
folklore-prior robustness check, and the widened-tolerance stress set. Uses the
pilot split (symptomatic validation units) and the pilot_wide split.
Writes metrics.json section "pilot2" and results/pilot2.log.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from eval import metrics_io
from eval.harness import SYSTEMS, run_system
from eval.stats import auroc, ece

PILOT_SYSTEMS = ["engine_gen", "hybrid", "fixed_order", "half_split", "random", "recap_prior"]
CIRCUITS = [COMPOSITE_ID, *BLOCK_IDS]


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
    # Unmodeled detector: unmodeled_val (used for calibration, so optimistic) vs pilot singles.
    pos, neg, flagged = [], [], []
    for cid in CIRCUITS:
        u = run_system(SYSTEMS["engine_gen"], cid, split="unmodeled_val")
        pos += list(u["unmodeled_prob"])
        flagged += list(u["top_group"] == -1)
        neg += list(runs["engine_gen"][cid]["unmodeled_prob"])
    out["unmodeled_auroc"] = auroc(np.array(pos), np.array(neg))
    out["unmodeled_flag_rate"] = float(np.mean(flagged))
    out["single_false_flag_rate"] = float(np.mean(pooled["engine_gen"]["top_group"] == -1))
    out["seconds"] = time.time() - t0
    metrics_io.update("pilot2", out)
    text = json.dumps(out, indent=1, default=float)
    (metrics_io.METRICS.parent / "pilot2.log").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
