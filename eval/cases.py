"""Build evaluation cases (ADR-013, ADR-030) and simulate them.

Every set samples *units that reach a bench*, i.e. units that show a symptom:
each case draws a hypothesis, simulates one unit, and keeps it only if the unit
shows a symptom; otherwise it draws a new hypothesis (not just a new unit). For
single faults this is a uniform sample of symptomatic units, so each fault
appears in proportion to how often it causes a symptom; a fault that never did
in 400 training draws is left out (such a unit would not reach a bench).

* ``test``            the locked single-fault test set;
* ``pilot``           the same protocol from its own seed stream, used before the
                      lock to set bars (never used for any tuning);
* ``test_wide``, ``pilot_wide``   channel strip, tolerances 1.5x wider (stress);
* ``unmodeled_val``   double faults and out-of-catalog modifications for
                      calibrating the "no single fault fits" threshold;
* ``unmodeled_pilot`` the same, used only to set the T13 bar before the lock;
* ``unmodeled_test``  the held-out set used for T13.
Outputs: data/eval/cases__<circuit>__<split>.parquet (observables + provenance)
and .jsonl (facts, complaint texts). These are committed.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.config import EVAL_DATA_DIR
from differential.engine.symptom_prior import SymptomFacts, SymptomModel, derive_facts
from differential.nlp.benchmark import MAIN_BANK, PERSONAS, leakage, render
from differential.sim.draws import BRIDGE
from differential.sim.faults import fault_catalog, parse_fault_id
from differential.sim.montecarlo import (
    BASE_SEED,
    SPLIT_INDEX,
    Job,
    circuit_index,
    load_dataset,
    run_jobs,
)

N_CASES = {
    "test": {COMPOSITE_ID: 500, **dict.fromkeys(BLOCK_IDS, 100)},
    "pilot": {COMPOSITE_ID: 200, **dict.fromkeys(BLOCK_IDS, 60)},
    "test_wide": {COMPOSITE_ID: 300},
    "pilot_wide": {COMPOSITE_ID: 150},
    "unmodeled_val": {COMPOSITE_ID: 60, **dict.fromkeys(BLOCK_IDS, 20)},
    "unmodeled_pilot": {COMPOSITE_ID: 60, **dict.fromkeys(BLOCK_IDS, 20)},
    "unmodeled_test": {COMPOSITE_ID: 50, **dict.fromkeys(BLOCK_IDS, 10)},
}
UNMODELED_SPLITS = ("unmodeled_val", "unmodeled_pilot", "unmodeled_test")
MAX_ATTEMPTS = 200
N_TEST = N_CASES["test"]  # kept for callers that size the test set


def symptom_model(cid: str) -> SymptomModel:
    return SymptomModel.fit(cid, load_dataset(cid, "train"))


def eligible_faults(sm: SymptomModel) -> list[str]:
    """Faults that caused a symptom in at least one training draw."""
    assert sm.symptomatic_rate is not None
    return [h for h, r in zip(sm.hypotheses, sm.symptomatic_rate, strict=True)
            if h != "healthy" and r > 0]


def symptomatic_faults(sm: SymptomModel) -> list[str]:
    """Faults that cause a symptom in at least half of training draws (used to
    compose double faults and for descriptive statistics)."""
    assert sm.symptomatic_rate is not None
    return [h for h, r in zip(sm.hypotheses, sm.symptomatic_rate, strict=True)
            if h != "healthy" and r >= 0.5]


def _bridge_pairs(cid: str) -> list[str]:
    """Solder bridges between test-point nodes of the same stage that no single part joins."""
    c = get_circuit(cid)
    direct = set()
    for el in c.netlist.elements:
        if len(el.nodes) >= 2:
            direct.add(frozenset(el.nodes[:2]))
    pairs = []
    tps = [tp for tp in c.test_points if not tp.hv]
    for i, a in enumerate(tps):
        for b in tps[i + 1:]:
            if a.stage == b.stage and a.node != b.node and frozenset((a.node, b.node)) not in direct:
                pairs.append(f"{BRIDGE}:{a.node}~{b.node}")
    return pairs


class UnmodeledSampler:
    """70 % double faults on distinct parts, 30 % out-of-catalog modifications."""

    def __init__(self, cid: str, sm: SymptomModel) -> None:
        c = get_circuit(cid)
        self.symp = symptomatic_faults(sm)
        self.passive = [p.ref for p in c.components if p.kind in ("resistor", "film_cap", "electrolytic")]
        self.bridges = _bridge_pairs(cid)

    def draw(self, rng: np.random.Generator) -> str:
        if rng.uniform() < 0.7:
            while True:
                a, b = rng.choice(len(self.symp), size=2, replace=False)
                fa, fb = parse_fault_id(self.symp[a]), parse_fault_id(self.symp[b])
                if fa.ref != fb.ref:
                    return f"{fa.id}+{fb.id}"
        if self.bridges and rng.uniform() < 0.4:
            return str(self.bridges[int(rng.integers(len(self.bridges)))])
        ref = self.passive[int(rng.integers(len(self.passive)))]
        factor = [4.0, 0.25, 5.0, 0.2][int(rng.integers(4))]
        return f"{ref}:value_x{factor:g}"


def _case_rng(cid: str, split: str, case_idx: int, attempt: int) -> np.random.Generator:
    """Hypothesis choice for one attempt of one case: its own seed, so the case list
    does not depend on how attempts are batched."""
    return np.random.default_rng([BASE_SEED, 77, SPLIT_INDEX[split], circuit_index(cid),
                                  case_idx, attempt])


def build_split(cid: str, split: str) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    sm = symptom_model(cid)
    assert sm.reference is not None
    circ = get_circuit(cid)
    tp_stage = {tp.id: tp.stage for tp in circ.test_points}
    n = N_CASES[split][cid]
    if split in UNMODELED_SPLITS:
        sampler = UnmodeledSampler(cid, sm)
        pick = sampler.draw
    else:
        faults = eligible_faults(sm)

        def pick(rng: np.random.Generator) -> str:
            return faults[int(rng.integers(len(faults)))]

    kept: dict[int, dict[str, object]] = {}
    attempts = dict.fromkeys(range(n), 0)
    tried: dict[int, list[str]] = {i: [] for i in range(n)}
    pending = list(range(n))
    while pending:
        hyps = {i: pick(_case_rng(cid, split, i, attempts[i])) for i in pending}
        jobs = [Job(cid, split, hyps[i], 100000 + i, (attempts[i],)) for i in pending]
        df, _ = run_jobs(jobs, tag=f"{cid}__{split}__round{max(attempts[i] for i in pending)}")
        df = df.set_index(["hyp_index", "draw"])
        nxt = []
        for i in pending:
            row = df.loc[(100000 + i, attempts[i])]
            tried[i].append(hyps[i])
            facts = derive_facts(circ, sm.reference, row) if bool(row["ok"]) else None
            if facts is not None and facts.any:
                rec = row.to_dict()
                rec.update({"case_id": f"{cid}-{split}-{i:04d}", "case_index": i, "circuit": cid,
                            "hypothesis": hyps[i], "redraws": attempts[i], "draw": attempts[i],
                            "hyp_index": 100000 + i, "_facts": facts})
                kept[i] = rec
            elif attempts[i] + 1 < MAX_ATTEMPTS:
                attempts[i] += 1
                nxt.append(i)
            else:
                raise RuntimeError(f"{cid} {split} case {i}: no symptomatic unit in {MAX_ATTEMPTS} draws")
        pending = nxt
    rows = [kept[i] for i in range(n)]
    # Complaint texts: one persona per case from the main bank; paraphrases are
    # rendered separately from the held-out bank by eval/nlp_benchmark.py.
    meta = []
    trng = np.random.default_rng([BASE_SEED, 91, SPLIT_INDEX[split], list(N_TEST).index(cid)])
    for r in rows:
        facts = r.pop("_facts")
        assert isinstance(facts, SymptomFacts)
        persona = PERSONAS[int(trng.integers(len(PERSONAS)))]
        text = render(facts, persona, trng, tp_stage, MAIN_BANK)
        meta.append({
            "case_id": r["case_id"], "circuit": cid, "split": split, "hypothesis": r["hypothesis"],
            "redraws": r["redraws"], "rejected_hypotheses": tried[int(r["case_index"])][:-1],  # type: ignore[call-overload]
            "ok": bool(r["ok"]),
            "facts": {
                "features": facts.features, "severity": facts.severity,
                "output_change_db": facts.output_change_db, "hum_rise_db": facts.hum_rise_db,
                "thd_pct": facts.thd_pct, "output_dc_v": facts.output_dc_v,
                "drift_tps": facts.drift_tps},
            "persona": persona, "complaint": text, "leakage": leakage(text),
        })
    return pd.DataFrame(rows), meta


def write_split(cid: str, split: str) -> tuple[int, int]:
    df, meta = build_split(cid, split)
    EVAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(EVAL_DATA_DIR / f"cases__{cid}__{split}.parquet", index=False, compression="zstd")
    with (EVAL_DATA_DIR / f"cases__{cid}__{split}.jsonl").open("w") as fh:
        for m in meta:
            fh.write(json.dumps(m) + "\n")
    return len(df), int(sum(int(m["redraws"]) for m in meta))  # type: ignore[call-overload]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--circuits", default="all")
    ap.add_argument("--splits", default="unmodeled_val,unmodeled_pilot,pilot,test,unmodeled_test")
    args = ap.parse_args()
    for split in args.splits.split(","):
        cids = [c for c in ([COMPOSITE_ID, *BLOCK_IDS] if args.circuits == "all"
                            else args.circuits.split(",")) if c in N_CASES[split]]
        for cid in cids:
            n, redraws = write_split(cid, split)
            print(f"{cid} {split}: {n} cases ({redraws} rejected draws)", flush=True)


def load_cases(cid: str, split: str) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    df = pd.read_parquet(EVAL_DATA_DIR / f"cases__{cid}__{split}.parquet")
    meta = [json.loads(line) for line in
            (EVAL_DATA_DIR / f"cases__{cid}__{split}.jsonl").read_text().splitlines() if line]
    return df, meta


def all_catalog_ids(cid: str) -> list[str]:
    return [f.id for f in fault_catalog(get_circuit(cid))]


if __name__ == "__main__":
    main()
