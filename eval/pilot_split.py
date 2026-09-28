"""Pilot split used to set the target bars (never the test set).

Symptomatic validation units, drawn like the test cases: each circuit's faults that
produce a symptom in at least half of units, a unit kept only if it shows a
symptom, complaint rendered from the main template bank. Only validation draws
50-99 are used: draws 0-49 set the unmodeled detector's threshold
(eval/recalibrate_unmodeled.py), so the pilot checks that threshold on units it
was not tuned on. The likelihood models never see validation draws, but the other
calibration steps (ambiguity groups, symptom-prior smoothing, classifier
temperature) use all of them, so the pilot stays mildly optimistic and the bars
sit below it.
"""

from __future__ import annotations

import json

import numpy as np

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.config import EVAL_DATA_DIR
from differential.engine.symptom_prior import derive_facts
from differential.nlp.benchmark import MAIN_BANK, PERSONAS, leakage, render
from differential.sim.montecarlo import BASE_SEED, load_dataset
from eval.cases import symptom_model, symptomatic_faults

N_PILOT = {COMPOSITE_ID: 200, **dict.fromkeys(BLOCK_IDS, 60)}
PILOT_MIN_DRAW = 50  # validation draws 0-49 are reserved for calibration


def build(cid: str) -> int:
    sm = symptom_model(cid)
    assert sm.reference is not None
    circ = get_circuit(cid)
    tp_stage = {tp.id: tp.stage for tp in circ.test_points}
    pool = set(symptomatic_faults(sm))
    val = load_dataset(cid, "val")
    val = val[val["ok"] & val["hypothesis"].isin(pool) & (val["draw"] >= PILOT_MIN_DRAW)]
    val = val.sample(frac=1.0, random_state=11)
    rng = np.random.default_rng([BASE_SEED, 55, len(cid)])
    rows, meta = [], []
    for _, r in val.iterrows():
        facts = derive_facts(circ, sm.reference, r)
        if not facts.any:
            continue
        i = len(rows)
        persona = PERSONAS[int(rng.integers(len(PERSONAS)))]
        text = render(facts, persona, rng, tp_stage, MAIN_BANK)
        rec = r.to_dict()
        rec.update({"case_id": f"{cid}-pilot-{i:04d}", "case_index": i, "circuit": cid})
        rows.append(rec)
        meta.append({"case_id": rec["case_id"], "circuit": cid, "split": "pilot",
                     "hypothesis": r["hypothesis"], "ok": True, "persona": persona,
                     "complaint": text, "leakage": leakage(text),
                     "facts": {"features": facts.features, "severity": facts.severity}})
        if len(rows) >= N_PILOT[cid]:
            break
    import pandas as pd

    EVAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(EVAL_DATA_DIR / f"cases__{cid}__pilot.parquet", index=False)
    with (EVAL_DATA_DIR / f"cases__{cid}__pilot.jsonl").open("w") as fh:
        for m in meta:
            fh.write(json.dumps(m) + "\n")
    return len(rows)


def main() -> None:
    for cid in [COMPOSITE_ID, *BLOCK_IDS]:
        print(cid, build(cid), "pilot cases", flush=True)


if __name__ == "__main__":
    main()
