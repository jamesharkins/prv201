"""Complaint-reading benchmark (target T18).

For every test unit, the held-out paraphrase bank (written independently of the
extractor, never used for tuning) renders one complaint in the unit's persona from
its simulated symptom facts. The extractor's symptom classes are scored against
those facts: micro-F1 over (unit, symptom) pairs, overall and by writer persona.
The development bank (MAIN_BANK, used while writing the rules) is scored too, to
show how much of the performance is familiarity with the phrasing.

Also writes data/eval/paraphrases__<circuit>__test.jsonl, which the
``hybrid_paraphrase`` ablation reads. Claude extraction runs only with an API key.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.config import EVAL_DATA_DIR
from differential.engine.symptom_prior import FEATURES, SymptomFacts
from differential.nlp.benchmark import leakage, render
from differential.nlp.paraphrase_bank import PARAPHRASE_BANK, SEVERITY_TAG_P
from differential.nlp.symptoms import extract_rules
from differential.sim.montecarlo import BASE_SEED
from eval import metrics_io
from eval.cases import load_cases


def facts_from(d: dict[str, Any]) -> SymptomFacts:
    return SymptomFacts(features=dict(d["features"]), severity=str(d["severity"]),
                        output_change_db=d.get("output_change_db"), hum_rise_db=d.get("hum_rise_db"),
                        thd_pct=d.get("thd_pct"), output_dc_v=d.get("output_dc_v"),
                        drift_tps=list(d.get("drift_tps") or []))


def f1(tp: int, fp: int, fn: int) -> float:
    return 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 1.0


def score(pairs: list[tuple[dict[str, bool], dict[str, bool]]]) -> dict[str, float]:
    tp = fp = fn = 0
    for gold, pred in pairs:
        for f in FEATURES:
            g, p = bool(gold.get(f)), bool(pred.get(f))
            tp += g and p
            fp += p and not g
            fn += g and not p
    return {"micro_f1": f1(tp, fp, fn), "precision": tp / (tp + fp) if tp + fp else 1.0,
            "recall": tp / (tp + fn) if tp + fn else 1.0, "n": len(pairs)}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--render-only", action="store_true",
                    help="write the paraphrase files for the hybrid_paraphrase ablation without "
                         "scoring anything (safe before the targets are locked)")
    render_only = ap.parse_args().render_only
    held: dict[str, list[tuple[dict[str, bool], dict[str, bool]]]] = {}
    dev: dict[str, list[tuple[dict[str, bool], dict[str, bool]]]] = {}
    leaks = 0
    for cid in [COMPOSITE_ID, *BLOCK_IDS]:
        circ = get_circuit(cid)
        tp_stage = {tp.id: tp.stage for tp in circ.test_points}
        _, meta = load_cases(cid, "test")
        rng = np.random.default_rng([BASE_SEED, 303, len(cid)])
        out = []
        for m in meta:
            if not m.get("facts"):
                continue
            facts = facts_from(m["facts"])
            persona = str(m["persona"])
            text = render(facts, persona, rng, tp_stage, PARAPHRASE_BANK, SEVERITY_TAG_P)
            leak = leakage(text)
            leaks += bool(leak)
            out.append({"case_id": m["case_id"], "persona": persona, "text": text, "leakage": leak})
            if render_only:
                continue
            gold = facts.features
            held.setdefault(persona, []).append((gold, extract_rules(text).features()))
            dev.setdefault(persona, []).append((gold, extract_rules(str(m["complaint"])).features()))
        with (EVAL_DATA_DIR / f"paraphrases__{cid}__test.jsonl").open("w") as fh:
            for rec in out:
                fh.write(json.dumps(rec) + "\n")
    if render_only:
        print(f"paraphrases written; {leaks} texts with leakage (nothing scored)")
        return
    result = {
        "held_out_rules": score([p for v in held.values() for p in v]),
        "held_out_rules_by_persona": {k: score(v) for k, v in held.items()},
        "development_rules": score([p for v in dev.values() for p in v]),
        "development_rules_by_persona": {k: score(v) for k, v in dev.items()},
        "held_out_texts_with_leakage": leaks,
        "claude": "pending: requires DIFFERENTIAL_API_KEY",
    }
    metrics_io.update("nlp", result)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
