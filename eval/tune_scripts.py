"""Tune the scripted baselines' unsoldering threshold on the pilot (ADR-046).

The fixed-order chart and half-split tracing unsolder their leading suspect once it holds
a share of the belief (``session.CONFIRM_AT``, 0.5 until round 6). Reviewers asked whether
that threshold was tuned for the scripts as carefully as the engine's own rules. This
sweep runs each script on the pilot split at several thresholds and applies a rule fixed
before the sweep: the threshold with the lowest effort to a confirmed answer among those
whose top-1 accuracy is within 1 point of the script's best. Tuning a baseline on the
pilot can only make the engine's targets harder. Pilot units only; never test data.
Writes metrics.json section "script_threshold".
"""

from __future__ import annotations

import time

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from eval import metrics_io
from eval.effort import summary as effort_summary
from eval.effort import with_effort
from eval.harness import SystemSpec, run_system
from eval.set_bars import WEIGHTS

THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
SCRIPTS = ("fixed_order", "half_split")
CIRCUITS = [COMPOSITE_ID, *BLOCK_IDS]
ACCURACY_SLACK = 0.01


def main() -> None:
    t0 = time.time()
    table: dict[str, dict[str, dict[str, float]]] = {}
    chosen: dict[str, float] = {}
    for script in SCRIPTS:
        table[script] = {}
        for th in THRESHOLDS:
            spec = SystemSpec(f"{script}_c{round(100 * th)}", policy=script, confirm_at=th)
            runs = {cid: run_system(spec, cid, split="pilot") for cid in CIRCUITS}
            top1 = sum(WEIGHTS[c] * float(df["correct"].mean()) for c, df in runs.items())
            eff = effort_summary(with_effort(runs), WEIGHTS)
            table[script][f"{th:.1f}"] = {"top1": top1, "confirmed_effort": eff["confirmed_effort"],
                                         "probing": eff["probing"], "unsoldering": eff["unsoldering"]
                                         + eff["confirming_charge"]}
            print(script, th, round(100 * top1, 1), round(eff["confirmed_effort"], 2), flush=True)
        best = max(r["top1"] for r in table[script].values())
        ok = {th: r for th, r in table[script].items() if r["top1"] >= best - ACCURACY_SLACK}
        chosen[script] = float(min(ok, key=lambda th: ok[th]["confirmed_effort"]))
    out = {"rule": "lowest effort to a confirmed answer among thresholds within 1 point of the "
                   "script's best top-1 (pilot, test-mix weights)",
           "thresholds": list(THRESHOLDS), "table": table, "chosen": chosen,
           "seconds": time.time() - t0}
    metrics_io.update("script_threshold", out)
    print("chosen:", chosen)


if __name__ == "__main__":
    main()
