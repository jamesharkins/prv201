"""Evaluation harness: run diagnosis systems over evaluation cases.

Common random numbers: the instrument noise for (case, observable) is seeded
by a hash of both, so every system sees the identical reading for the same
measurement of the same unit. That makes paired comparisons sharp.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from differential.config import EVAL_DATA_DIR, MODELS_DIR, n_workers
from differential.engine.bundle import EngineBundle, load_bundle
from differential.engine.generative import GenerativeModel
from differential.engine.session import DiagnosisSession
from differential.instruments.simulated import noise_seed
from differential.nlp.symptoms import extract_rules
from differential.sim.faults import UNMODELED, parse_fault_id, part_kind
from differential.sim.measurement import simulate_lift, simulate_reading
from differential.sim.observables import ObservableSpec

RUNS_DIR = EVAL_DATA_DIR / "runs"


@dataclass(frozen=True)
class SystemSpec:
    name: str
    policy: str = "eig_per_cost"
    likelihood: str = "generative"
    prior: str = "uniform"  # uniform | symptoms_rules | symptoms_oracle | recap_folklore
    model_variant: str = ""  # "" or e.g. "n50" for the sample-size ablation
    text_field: str = "complaint"  # which complaint text feeds the extractor


SYSTEMS: dict[str, SystemSpec] = {
    "random": SystemSpec("random", policy="random"),
    "fixed_order": SystemSpec("fixed_order", policy="fixed_order"),
    "half_split": SystemSpec("half_split", policy="half_split"),
    "engine_gen": SystemSpec("engine_gen"),
    "engine_disc": SystemSpec("engine_disc", likelihood="discriminative"),
    "hybrid": SystemSpec("hybrid", prior="symptoms_rules"),
    # ablations
    "hybrid_paraphrase": SystemSpec("hybrid_paraphrase", prior="symptoms_rules",
                                    text_field="paraphrase"),
    "hybrid_oracle": SystemSpec("hybrid_oracle", prior="symptoms_oracle"),
    "recap_prior": SystemSpec("recap_prior", prior="recap_folklore"),
    "engine_eig_nocost": SystemSpec("engine_eig_nocost", policy="eig"),
    "engine_n50": SystemSpec("engine_n50", model_variant="n50"),
    "engine_n100": SystemSpec("engine_n100", model_variant="n100"),
    "engine_n200": SystemSpec("engine_n200", model_variant="n200"),
}


@lru_cache(maxsize=32)
def bundle_for(cid: str, variant: str = "") -> EngineBundle:
    b = load_bundle(cid)
    if variant:
        b.gen = GenerativeModel.load(MODELS_DIR / cid / f"generative_{variant}.npz")
        # keep the calibrated unmodeled offset of the full model
        b.gen.unmod_offset = load_bundle(cid, with_disc=False).gen.unmod_offset
    return b


def recap_prior(bundle: EngineBundle, capacitor_share: float = 0.6) -> np.ndarray:
    """Forum-folklore prior: capacitor faults get `capacitor_share` of the mass."""
    kinds = [part_kind(bundle.circuit, parse_fault_id(h)) for h in bundle.hypotheses]
    is_cap = np.array([k in ("film_cap", "electrolytic") for k in kinds])
    p = np.where(is_cap, capacitor_share / max(is_cap.sum(), 1),
                 (1 - capacitor_share) / max((~is_cap).sum(), 1))
    return p / p.sum()


def make_prior(spec: SystemSpec, bundle: EngineBundle, meta: dict[str, Any]) -> np.ndarray | None:
    sm = bundle.symptom_model
    if spec.prior == "uniform" or sm is None:
        return None
    if spec.prior == "symptoms_rules":
        text = str(meta.get(spec.text_field) or meta.get("complaint") or "")
        return np.asarray(sm.prior(extract_rules(text).features()))
    if spec.prior == "symptoms_oracle":
        facts = meta.get("facts") or {}
        return np.asarray(sm.prior(facts.get("features", {})))
    if spec.prior == "recap_folklore":
        return recap_prior(bundle)
    raise ValueError(spec.prior)


def run_one(args: tuple[SystemSpec, str, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    spec, cid, row, meta = args
    bundle = bundle_for(cid, spec.model_variant)
    case_id = str(row["case_id"])
    truth = str(row["hypothesis"])
    single = "+" not in truth and truth in bundle.hypotheses
    truth_refs = {parse_fault_id(f).ref for f in truth.split("+")}

    def measure(o: ObservableSpec) -> float:
        rng = np.random.default_rng(noise_seed(case_id, o.key))
        if o.is_lift:
            return float(simulate_lift(o.ref in truth_refs, rng))
        return simulate_reading(o.kind, float(row[o.key]), rng, float(row["fundamental"]))

    prior = make_prior(spec, bundle, meta)
    t0 = time.perf_counter()
    s = DiagnosisSession(bundle, policy=spec.policy, likelihood=spec.likelihood, prior=prior,
                         seed=noise_seed(case_id, "policy") % (2**31))
    res = s.run(measure)
    groups = bundle.groups
    truth_group = int(groups.group_of[bundle.hypotheses.index(truth)]) if single else -1
    ranked = [g for g, _ in res.ranked_groups]
    top_hyp = s.top_hypotheses(1)[0][0]
    return {
        "system": spec.name,
        "case_id": case_id,
        "circuit": cid,
        "truth": truth,
        "truth_group": truth_group,
        "single_fault": single,
        "top_group": res.top_group,
        "top_hypothesis": top_hyp,
        "correct": res.top_group == truth_group,
        "top3": truth_group in ranked[:3],
        "confidence": res.top_mass,
        "unmodeled_prob": res.unmodeled_prob,
        "cost": res.cost,
        "steps": res.steps,
        "stop_reason": res.stop_reason,
        "seconds": time.perf_counter() - t0,
        "step_seconds": json.dumps([round(t.seconds, 5) for t in res.trace]),
        "keys": json.dumps([r.key for r in res.readings]),
        "truth_kind": part_kind(bundle.circuit, parse_fault_id(truth)) if single else UNMODELED,
        "pred_kind": part_kind(bundle.circuit, parse_fault_id(top_hyp)),
        "trace_mass": json.dumps([round(t.top_mass, 4) for t in res.trace]),
        "trace_cost": json.dumps([t.cost_spent for t in res.trace]),
        "trace_correct": json.dumps([t.top_group == truth_group for t in res.trace]),
    }


def load_split(cid: str, split: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    from eval.cases import load_cases

    return load_cases(cid, split)


def run_system(spec: SystemSpec, cid: str, split: str = "test", workers: int | None = None,
               limit: int | None = None, force: bool = False) -> pd.DataFrame:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out = RUNS_DIR / f"{spec.name}__{cid}__{split}{'' if limit is None else f'__{limit}'}.parquet"
    if out.exists() and not force:
        return pd.read_parquet(out)
    df, meta = load_split(cid, split)
    meta_by_id = {m["case_id"]: m for m in meta}
    paraphrases = _paraphrases(cid, split)
    rows = []
    for _, r in df.iterrows():
        if not r["ok"]:
            continue
        m = dict(meta_by_id[r["case_id"]])
        m["paraphrase"] = paraphrases.get(r["case_id"], m.get("complaint"))
        rows.append((spec, cid, r.to_dict(), m))
        if limit is not None and len(rows) >= limit:
            break
    workers = workers or n_workers()
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run_one, rows, chunksize=4))
    else:
        results = [run_one(a) for a in rows]
    res = pd.DataFrame(results)
    res.to_parquet(out, index=False)
    return res


def _paraphrases(cid: str, split: str) -> dict[str, str]:
    p = EVAL_DATA_DIR / f"paraphrases__{cid}__{split}.jsonl"
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            out[d["case_id"]] = d["text"]
    return out


def results_path(name: str, cid: str, split: str = "test") -> Path:
    return RUNS_DIR / f"{name}__{cid}__{split}.parquet"
