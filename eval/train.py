"""Fit every engine artifact per circuit and write data/models/<circuit>/.

Steps (all seeds fixed):
 1. Generative model: GMMs on all training draws.
 2. Ambiguity groups: confusion on validation draws.
 3. Symptom model: P(feature | fault) from training draws; eps/lambda calibrated on
    validation cases whose complaints are rendered from the main template bank
    and parsed by the offline extractor (the same path the hybrid uses offline).
 4. Discriminative model: LightGBM on masked, noise-augmented training draws,
    temperature-scaled on validation.
 5. Unmodeled threshold: the per-dimension log-density offset of the unmodeled
    hypothesis is chosen on validation sessions so that at most 5 % of single-fault
    validation cases end with U as the top group, maximising detection of the
    validation double-fault / out-of-catalog cases.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.config import MODELS_DIR, n_workers
from differential.engine.ambiguity import build_groups
from differential.engine.bundle import EngineBundle
from differential.engine.data import build_engine_data
from differential.engine.discriminative import DiscriminativeModel
from differential.engine.generative import GenerativeModel
from differential.engine.session import DiagnosisSession
from differential.engine.symptom_prior import SymptomModel, derive_facts
from differential.nlp.benchmark import MAIN_BANK, PERSONAS, render
from differential.nlp.symptoms import extract_rules
from differential.sim.measurement import simulate_lift, simulate_reading
from differential.sim.montecarlo import BASE_SEED, load_dataset

OFFSETS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
MC_VARIANTS = (50, 100, 200)  # Monte Carlo sample-size ablation (the full model uses 400)
FPR_BUDGET = 0.05


def run_case(bundle: EngineBundle, row: pd.Series, truth_ref: str, seed: int,
             prior: np.ndarray | None = None, policy: str = "eig_per_cost") -> tuple[int, float]:
    rng = np.random.default_rng(seed)

    def measure(o):  # type: ignore[no-untyped-def]
        if o.is_lift:
            return float(simulate_lift(o.ref == truth_ref, rng))
        return simulate_reading(o.kind, float(row[o.key]), rng, float(row.fundamental))

    s = DiagnosisSession(bundle, policy=policy, prior=prior, seed=seed)
    r = s.run(measure)
    return r.top_group, r.unmodeled_prob


def calibrate_unmodeled(bundle: EngineBundle, val: pd.DataFrame, unmod: pd.DataFrame,
                        n_single: int = 120) -> dict[str, object]:
    rng = np.random.default_rng(BASE_SEED)
    single = val[(val.hypothesis != "healthy") & val.ok]
    single = single.sample(min(n_single, len(single)), random_state=1)
    results = []
    for off in OFFSETS:
        bundle.gen.unmod_offset = off
        fp = sum(run_case(bundle, r, r.hypothesis.split(":")[0], int(rng.integers(1 << 30)))[0] == -1
                 for _, r in single.iterrows())
        tp = sum(run_case(bundle, r, "", int(rng.integers(1 << 30)))[0] == -1
                 for _, r in unmod[unmod.ok].iterrows())
        results.append({"offset": off, "fpr": fp / len(single),
                         "tpr": tp / max(int(unmod.ok.sum()), 1)})
    ok = [r for r in results if r["fpr"] <= FPR_BUDGET]
    best = max(ok, key=lambda r: (r["tpr"], -r["fpr"], r["offset"])) if ok else min(
        results, key=lambda r: r["fpr"])
    bundle.gen.unmod_offset = float(best["offset"])  # type: ignore[arg-type]
    return {"chosen": best, "grid": results}


def train_circuit(cid: str, skip_disc: bool = False) -> dict[str, object]:
    t0 = time.time()
    circ = get_circuit(cid)
    tr_df = load_dataset(cid, "train")
    va_df = load_dataset(cid, "val")
    tr = build_engine_data(cid, tr_df)
    va = build_engine_data(cid, va_df)
    gen = GenerativeModel.fit(tr, workers=n_workers())
    groups = build_groups(gen, va, per_hyp=40)
    sm = SymptomModel.fit(cid, tr_df)
    # Calibrate the symptom likelihood on validation complaints parsed offline.
    rng = np.random.default_rng([BASE_SEED, 5, len(cid)])
    tp_stage = {tp.id: tp.stage for tp in circ.test_points}
    vs = va_df[va_df.ok & (va_df.hypothesis != "healthy")]
    vs = vs.sample(min(1500, len(vs)), random_state=2)
    assert sm.reference is not None
    reports, truths = [], []
    for _, r in vs.iterrows():
        facts = derive_facts(circ, sm.reference, r)
        if not facts.any:
            continue
        persona = PERSONAS[int(rng.integers(len(PERSONAS)))]
        text = render(facts, persona, rng, tp_stage, MAIN_BANK)
        reports.append(extract_rules(text).features())
        truths.append(sm.hypotheses.index(r.hypothesis))
    sm.calibrate(reports, truths)
    disc = None
    if not skip_disc:
        disc = DiscriminativeModel.fit(tr, va, n_masks=3, num_threads=n_workers())
    bundle = EngineBundle(circ, gen, groups, disc=disc, symptom_model=sm)
    from eval.cases import load_cases

    unmod_df, _ = load_cases(cid, "unmodeled_val")
    cal = calibrate_unmodeled(bundle, va_df, unmod_df)
    bundle.meta = {
        "circuit": cid,
        "train_rows": len(tr.X),
        "val_rows": len(va.X),
        "components_total": len(gen.comp_hyp),
        "groups": int(groups.n_groups),
        "nontrivial_groups": [g for g in groups.nontrivial()],
        "symptom_eps": sm.eps,
        "symptom_lambda": sm.lam,
        "disc_temperature": None if disc is None else disc.temperature,
        "unmodeled_calibration": cal,
        "seconds": time.time() - t0,
    }
    d = bundle.save()
    sm.save(d / "symptom_model.json")
    # Sample-size ablation: the same generative model fitted on fewer draws per fault.
    for n in MC_VARIANTS:
        GenerativeModel.fit(build_engine_data(cid, tr_df, max_draws=n),
                            workers=n_workers()).save(d / f"generative_n{n}.npz")
    return bundle.meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--circuits", default="all")
    ap.add_argument("--skip-disc", action="store_true")
    args = ap.parse_args()
    cids = [COMPOSITE_ID, *BLOCK_IDS] if args.circuits == "all" else args.circuits.split(",")
    summary = {}
    for cid in cids:
        meta = train_circuit(cid, skip_disc=args.skip_disc)
        summary[cid] = {k: v for k, v in meta.items() if k != "nontrivial_groups"}
        print(cid, json.dumps(summary[cid], default=str)[:600], flush=True)
    (MODELS_DIR / "training_summary.json").write_text(json.dumps(summary, indent=1, default=str))


if __name__ == "__main__":
    main()
