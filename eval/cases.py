"""Build evaluation cases (ADR-013) and simulate them.

* ``test``            single-fault cases, uniform over each circuit's symptomatic
                      faults, seeds from the disjoint test stream; a unit that shows
                      no symptom is redrawn so every case has a complaint.
* ``unmodeled_val``   double faults + out-of-catalog modifications for calibrating
                      the unmodeled threshold.
* ``unmodeled_test``  the held-out unmodeled set used for AUROC.
Outputs: data/eval/cases__<split>.parquet (observables + provenance) and
data/eval/cases__<split>.jsonl (facts, complaint texts). These are committed.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.config import EVAL_DATA_DIR
from differential.engine.symptom_prior import SymptomModel, derive_facts
from differential.nlp.benchmark import MAIN_BANK, PERSONAS, leakage, render
from differential.sim.draws import BRIDGE
from differential.sim.faults import fault_catalog, parse_fault_id
from differential.sim.montecarlo import BASE_SEED, SPLIT_INDEX, Job, load_dataset, run_jobs

N_TEST = {COMPOSITE_ID: 500, **dict.fromkeys(BLOCK_IDS, 100)}
N_UNMOD_TEST = {COMPOSITE_ID: 50, **dict.fromkeys(BLOCK_IDS, 10)}
N_UNMOD_VAL = {COMPOSITE_ID: 60, **dict.fromkeys(BLOCK_IDS, 20)}
MAX_REDRAWS = 20


def symptom_model(cid: str) -> SymptomModel:
    return SymptomModel.fit(cid, load_dataset(cid, "train"))


def symptomatic_faults(sm: SymptomModel) -> list[str]:
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


def unmodeled_hypotheses(cid: str, n: int, rng: np.random.Generator, sm: SymptomModel) -> list[str]:
    """70 % double faults on distinct parts, 30 % out-of-catalog modifications."""
    symp = symptomatic_faults(sm)
    c = get_circuit(cid)
    passive = [comp.ref for comp in c.components if comp.kind in ("resistor", "film_cap", "electrolytic")]
    bridges = _bridge_pairs(cid)
    out = []
    n_double = int(round(0.7 * n))
    while len(out) < n_double:
        a, b = rng.choice(len(symp), size=2, replace=False)
        fa, fb = parse_fault_id(symp[a]), parse_fault_id(symp[b])
        if fa.ref != fb.ref:
            out.append(f"{fa.id}+{fb.id}")
    while len(out) < n:
        if bridges and rng.uniform() < 0.4:
            out.append(str(bridges[int(rng.integers(len(bridges)))]))
        else:
            ref = passive[int(rng.integers(len(passive)))]
            factor = [4.0, 0.25, 5.0, 0.2][int(rng.integers(4))]
            out.append(f"{ref}:value_x{factor:g}")
    return out


def _case_job(cid: str, split: str, hyp: str, case_idx: int, attempt: int) -> Job:
    return Job(cid, split, hyp, 100000 + case_idx, (attempt,))


def build_split(cid: str, split: str) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    sm = symptom_model(cid)
    circ = get_circuit(cid)
    tp_stage = {tp.id: tp.stage for tp in circ.test_points}
    # Distinct hypothesis-sampling stream per (split, circuit): no shared case lists.
    rng = np.random.default_rng([BASE_SEED, 77, SPLIT_INDEX[split], list(N_TEST).index(cid)])
    if split == "test":
        pool = symptomatic_faults(sm)
        hyps = [pool[int(rng.integers(len(pool)))] for _ in range(N_TEST[cid])]
    elif split == "unmodeled_test":
        hyps = unmodeled_hypotheses(cid, N_UNMOD_TEST[cid], rng, sm)
    elif split == "unmodeled_val":
        hyps = unmodeled_hypotheses(cid, N_UNMOD_VAL[cid], rng, sm)
    else:
        raise ValueError(split)
    assert sm.reference is not None
    rows: list[dict[str, object]] = []
    pending = list(enumerate(hyps))
    attempts = dict.fromkeys(range(len(hyps)), 0)
    while pending:
        jobs = [_case_job(cid, split, h, i, attempts[i]) for i, h in pending]
        df, _ = run_jobs(jobs, tag=f"{cid}__{split}__round{max(attempts.values())}")
        df = df.set_index(["hyp_index", "draw"])
        nxt = []
        for i, h in pending:
            row = df.loc[(100000 + i, attempts[i])]
            facts = derive_facts(circ, sm.reference, row) if bool(row["ok"]) else None
            need_symptom = split == "test"
            if row["ok"] and (facts is not None) and (facts.any or not need_symptom):
                rec = row.to_dict()
                rec.update({"case_id": f"{cid}-{split}-{i:04d}", "case_index": i, "circuit": cid,
                            "hypothesis": h, "redraws": attempts[i], "draw": attempts[i],
                            "hyp_index": 100000 + i})
                rec["_facts"] = facts
                rows.append(rec)
            elif attempts[i] + 1 < MAX_REDRAWS:
                attempts[i] += 1
                nxt.append((i, h))
            else:
                rec = row.to_dict()
                rec.update({"case_id": f"{cid}-{split}-{i:04d}", "case_index": i, "circuit": cid,
                            "hypothesis": h, "redraws": attempts[i], "draw": attempts[i],
                            "hyp_index": 100000 + i, "_facts": facts})
                rows.append(rec)
        pending = nxt
    rows.sort(key=lambda r: int(r["case_index"]))  # type: ignore[arg-type]
    # Complaint texts: one persona per case from the main bank; paraphrases are
    # rendered separately from the held-out bank by eval/nlp_benchmark.py.
    meta = []
    trng = np.random.default_rng([BASE_SEED, 91, SPLIT_INDEX[split], list(N_TEST).index(cid)])
    for r in rows:
        facts = r.pop("_facts")
        persona = PERSONAS[int(trng.integers(len(PERSONAS)))]
        text = render(facts, persona, trng, tp_stage, MAIN_BANK) if facts is not None else ""
        leaks = leakage(text)
        meta.append({
            "case_id": r["case_id"], "circuit": cid, "split": split, "hypothesis": r["hypothesis"],
            "redraws": r["redraws"], "ok": bool(r["ok"]),
            "facts": None if facts is None else {
                "features": facts.features, "severity": facts.severity,
                "output_change_db": facts.output_change_db, "hum_rise_db": facts.hum_rise_db,
                "thd_pct": facts.thd_pct, "output_dc_v": facts.output_dc_v,
                "drift_tps": facts.drift_tps},
            "persona": persona, "complaint": text, "leakage": leaks,
        })
    df_out = pd.DataFrame(rows)
    return df_out, meta


def write_split(cid: str, split: str) -> tuple[int, int]:
    df, meta = build_split(cid, split)
    EVAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(EVAL_DATA_DIR / f"cases__{cid}__{split}.parquet", index=False, compression="zstd")
    with (EVAL_DATA_DIR / f"cases__{cid}__{split}.jsonl").open("w") as fh:
        for m in meta:
            fh.write(json.dumps(m) + "\n")
    return len(df), int((~df["ok"]).sum()) if len(df) else 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--circuits", default="all")
    ap.add_argument("--splits", default="unmodeled_val,test,unmodeled_test")
    args = ap.parse_args()
    cids = [COMPOSITE_ID, *BLOCK_IDS] if args.circuits == "all" else args.circuits.split(",")
    for split in args.splits.split(","):
        for cid in cids:
            n, bad = write_split(cid, split)
            print(f"{cid} {split}: {n} cases ({bad} failed)", flush=True)


if __name__ == "__main__":
    main()


def load_cases(cid: str, split: str) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    df = pd.read_parquet(EVAL_DATA_DIR / f"cases__{cid}__{split}.parquet")
    meta = [json.loads(line) for line in
            (EVAL_DATA_DIR / f"cases__{cid}__{split}.jsonl").read_text().splitlines() if line]
    return df, meta


def all_catalog_ids(cid: str) -> list[str]:
    return [f.id for f in fault_catalog(get_circuit(cid))]
