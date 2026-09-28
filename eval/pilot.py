"""Feasibility pilot used to set the M1 targets (run before the targets were locked).

Protocol: for each circuit, fit the generative engine on training draws 0-299,
build ambiguity groups and the symptom model from the same draws, then run
diagnosis sessions on symptomatic cases drawn from *held-out training draws*
300-399. The validation and test splits are not touched. Results go to the
metrics.json section "pilot".
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from differential.circuits.library import CIRCUIT_IDS, get_circuit
from differential.config import n_workers
from differential.engine.ambiguity import build_groups
from differential.engine.bundle import EngineBundle
from differential.engine.data import build_engine_data
from differential.engine.generative import GenerativeModel
from differential.engine.session import DiagnosisSession
from differential.engine.symptom_prior import SymptomModel, derive_facts
from differential.sim.measurement import simulate_lift, simulate_reading
from differential.sim.montecarlo import load_dataset
from eval import metrics_io

CONFIGS = [
    ("eig_per_cost", False),
    ("eig_per_cost", True),
    ("fixed_order", False),
    ("random", False),
]


def run_circuit(cid: str, n_cases: int, seed: int = 1) -> dict[str, object]:
    df = load_dataset(cid, "train")
    circ = get_circuit(cid)
    tr = build_engine_data(cid, df[df.draw < 300])
    hold = build_engine_data(cid, df[df.draw >= 300])
    t0 = time.time()
    gen = GenerativeModel.fit(tr, workers=n_workers())
    fit_s = time.time() - t0
    groups = build_groups(gen, hold, per_hyp=30)
    sm = SymptomModel.fit(cid, df[df.draw < 300])
    rate = dict(zip(sm.hypotheses, sm.symptomatic_rate, strict=True))
    symptomatic = [h for h, r in rate.items() if r >= 0.5 and h != "healthy"]
    bundle = EngineBundle(circ, gen, groups)
    pool = df[(df.draw >= 300) & df.ok & df.hypothesis.isin(symptomatic)]
    rows = pool.sample(min(n_cases, len(pool)), random_state=seed)
    out: dict[str, object] = {
        "cases": len(rows),
        "hypotheses": gen.n_hyp,
        "symptomatic_faults": len(symptomatic),
        "latent_faults": gen.n_hyp - 1 - len(symptomatic),
        "ambiguity_groups": groups.n_groups,
        "fit_seconds": fit_s,
    }
    for policy, use_prior in CONFIGS:
        rng = np.random.default_rng(seed)
        correct, costs, conf_ok, conf_n, secs = [], [], 0, 0, []
        for _, row in rows.iterrows():
            truth = row.hypothesis
            tg = groups.group_of[gen.hypotheses.index(truth)]
            prior = sm.prior(derive_facts(circ, sm.reference, row).features) if use_prior else None

            def measure(o, row=row, truth=truth, rng=rng):  # type: ignore[no-untyped-def]
                if o.is_lift:
                    return float(simulate_lift(o.ref == truth.split(":")[0], rng))
                return simulate_reading(o.kind, float(row[o.key]), rng, float(row.fundamental))

            s = DiagnosisSession(bundle, policy=policy, prior=prior, seed=int(row.draw))
            r = s.run(measure)
            ok = r.top_group == tg
            correct.append(ok)
            costs.append(r.cost)
            secs.append(r.seconds / max(r.steps, 1))
            if r.stop_reason == "confident":
                conf_n += 1
                conf_ok += int(ok)
        name = policy + ("_symptom_prior" if use_prior else "")
        out[name] = {
            "top1": float(np.mean(correct)),
            "mean_cost": float(np.mean(costs)),
            "median_cost": float(np.median(costs)),
            "accuracy_when_confident": conf_ok / conf_n if conf_n else None,
            "confident_fraction": conf_n / len(rows),
            "seconds_per_step": float(np.mean(secs)),
        }
        print(cid, name, out[name], flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--circuits", default="all")
    ap.add_argument("--cases", type=int, default=100)
    ap.add_argument("--composite-cases", type=int, default=200)
    args = ap.parse_args()
    cids = CIRCUIT_IDS if args.circuits == "all" else tuple(args.circuits.split(","))
    results = {}
    for cid in cids:
        n = args.composite_cases if cid == "channel_strip" else args.cases
        results[cid] = run_circuit(cid, n)
    pooled = {}
    for name in ("eig_per_cost", "eig_per_cost_symptom_prior", "fixed_order", "random"):
        tot = sum(int(results[c]["cases"]) for c in results)  # type: ignore[call-overload]
        pooled[name] = {
            "top1": sum(results[c][name]["top1"] * results[c]["cases"] for c in results) / tot,  # type: ignore[index,operator]
            "mean_cost": sum(results[c][name]["mean_cost"] * results[c]["cases"] for c in results) / tot,  # type: ignore[index,operator]
        }
    tot = sum(int(results[c]["cases"]) for c in results)  # type: ignore[call-overload]
    conf_frac = sum(results[c]["eig_per_cost"]["confident_fraction"] * results[c]["cases"]  # type: ignore[index,operator]
                    for c in results) / tot
    conf_hits = sum((results[c]["eig_per_cost"]["accuracy_when_confident"] or 0)  # type: ignore[index,operator]
                    * results[c]["eig_per_cost"]["confident_fraction"] * results[c]["cases"]  # type: ignore[index,operator]
                    for c in results)
    data = {"protocol": "fit on training draws 0-299; evaluate on held-out training draws 300-399",
            "circuits": results, "pooled": pooled,
            "pooled_confident_fraction": conf_frac,
            "pooled_accuracy_when_confident": conf_hits / (conf_frac * tot) if conf_frac else None}
    metrics_io.update("pilot", data)
    print(pd.DataFrame(pooled).T)


if __name__ == "__main__":
    main()
