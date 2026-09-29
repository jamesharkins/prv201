"""Complaint-reading benchmark (target T18).

Gold labels are the symptoms each complaint *reports* (the unit's symptoms after
complaint noise, ADR-032), so a symptom the writer left out is not counted
against the reader. Three banks render the same reported symptoms for every test
unit, each in the unit's persona:

* bank B (``paraphrase_bank_b``): sealed; written without access to the reader,
  its rules or the other banks; never scored before the targets were locked. T18
  is scored here.
* bank A (``paraphrase_bank``): the held-out bank the evaluation complaints come
  from; its aggregate score was seen once before the rules were last extended, so
  it is reported as "seen once".
* the development bank (``MAIN_BANK``), which the rules were written against,
  shows how much of the score is familiarity with the phrasing.

Micro-F1 over (unit, symptom) pairs is the target; macro-F1 and per-symptom recall
are reported so rare symptoms are not hidden. ``--render-only`` (safe before the
lock) writes data/eval/complaints__<circuit>__test.jsonl with the development-bank
and bank-B texts for the ``hybrid_devbank`` and ``hybrid_bank_b`` ablations.
Claude extraction runs only with an API key.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID, get_circuit
from differential.config import EVAL_DATA_DIR
from differential.engine.symptom_prior import FEATURES, SymptomFacts
from differential.nlp.benchmark import MAIN_BANK, leakage, render
from differential.nlp.symptoms import extract_rules
from differential.sim.montecarlo import BASE_SEED
from eval import metrics_io
from eval.cases import load_cases
from eval.lock import require_lock


def bank_b() -> tuple[dict[str, dict[str, list[str]]], dict[str, dict[str, str]]] | None:
    try:
        from differential.nlp.paraphrase_bank_b import PARAPHRASE_BANK_B, SEVERITY_TAG_B
    except ImportError:
        return None
    return PARAPHRASE_BANK_B, SEVERITY_TAG_B


def facts_from(d: dict[str, Any], features: dict[str, bool] | None = None) -> SymptomFacts:
    return SymptomFacts(features=dict(features if features is not None else d["features"]),
                        severity=str(d["severity"]),
                        output_change_db=d.get("output_change_db"), hum_rise_db=d.get("hum_rise_db"),
                        thd_pct=d.get("thd_pct"), output_dc_v=d.get("output_dc_v"),
                        drift_tps=list(d.get("drift_tps") or []))


def f1(tp: int, fp: int, fn: int) -> float:
    return 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 1.0


def score(pairs: list[tuple[dict[str, bool], dict[str, bool]]]) -> dict[str, Any]:
    tp = fp = fn = 0
    per: dict[str, list[int]] = {f: [0, 0, 0] for f in FEATURES}
    for gold, pred in pairs:
        for f in FEATURES:
            g, p = bool(gold.get(f)), bool(pred.get(f))
            tp += g and p
            fp += p and not g
            fn += g and not p
            per[f][0] += g and p
            per[f][1] += p and not g
            per[f][2] += g and not p
    present = [f for f in FEATURES if per[f][0] + per[f][2] > 0]
    return {"micro_f1": f1(tp, fp, fn), "precision": tp / (tp + fp) if tp + fp else 1.0,
            "recall": tp / (tp + fn) if tp + fn else 1.0, "n": len(pairs),
            "macro_f1": float(np.mean([f1(*per[f]) for f in present])) if present else 1.0,
            "recall_by_symptom": {f: per[f][0] / (per[f][0] + per[f][2]) for f in present},
            "support_by_symptom": {f: per[f][0] + per[f][2] for f in present}}


def score_claude(held_texts: list[tuple[str, dict[str, bool], str]]) -> dict[str, Any]:
    """Claude extraction on the same held-out texts (live, or replayed from the cache).
    A text whose extraction fails counts as an empty prediction, and the failures are counted."""
    from differential.agent.llm import LLMClient, LLMUnavailable
    from differential.nlp.symptoms import extract_llm

    client = LLMClient()
    by: dict[str, list[tuple[dict[str, bool], dict[str, bool]]]] = {}
    failures = 0
    for i, (persona, gold, text) in enumerate(held_texts):
        try:
            pred = extract_llm(text, client).features()
        except LLMUnavailable:
            if i == 0:
                return {"claude": "pending: requires DIFFERENTIAL_API_KEY (or a replay cache)"}
            pred, failures = {}, failures + 1
        except Exception:  # malformed output: scored as no symptoms read
            pred, failures = {}, failures + 1
        by.setdefault(persona, []).append((gold, pred))
    return {"bank_b_claude": score([p for v in by.values() for p in v]),
            "bank_b_claude_by_persona": {k: score(v) for k, v in by.items()},
            "claude_failures": failures, "claude_model": client.model,
            "claude_cost_usd": client.usage.cost_usd(client.model)}


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--render-only", action="store_true",
                    help="write the development-bank and bank-B texts for the ablations without "
                         "scoring anything (safe before the targets are locked)")
    render_only = ap.parse_args().render_only
    if not render_only:
        require_lock("score complaint reading on test units")
    b = bank_b()
    by_bank: dict[str, dict[str, list[tuple[dict[str, bool], dict[str, bool]]]]] = {
        "bank_b": {}, "bank_a_seen_once": {}, "development": {}}
    b_texts: list[tuple[str, dict[str, bool], str]] = []  # (persona, gold, text) for Claude
    leaks = 0
    for cid in [COMPOSITE_ID, *BLOCK_IDS]:
        circ = get_circuit(cid)
        tp_stage = {tp.id: tp.stage for tp in circ.test_points}
        _, meta = load_cases(cid, "test")
        drng = np.random.default_rng([BASE_SEED, 303, len(cid)])
        brng = np.random.default_rng([BASE_SEED, 304, len(cid)])
        out = []
        for m in meta:
            if not m.get("facts"):
                continue
            gold = dict(m.get("reported") or m["facts"]["features"])
            facts = facts_from(m["facts"], gold)
            persona = str(m["persona"])
            dev_text = render(facts, persona, drng, tp_stage, MAIN_BANK)
            rec: dict[str, Any] = {"case_id": m["case_id"], "persona": persona,
                                   "dev_complaint": dev_text}
            if b is not None:
                btext = render(facts, persona, brng, tp_stage, b[0], b[1])
                rec["bank_b_complaint"] = btext
                leaks += bool(leakage(btext))
            out.append(rec)
            if render_only:
                continue
            by_bank["development"].setdefault(persona, []).append(
                (gold, extract_rules(dev_text).features()))
            by_bank["bank_a_seen_once"].setdefault(persona, []).append(
                (gold, extract_rules(str(m["complaint"])).features()))
            if b is not None:
                by_bank["bank_b"].setdefault(persona, []).append(
                    (gold, extract_rules(rec["bank_b_complaint"]).features()))
                b_texts.append((persona, gold, rec["bank_b_complaint"]))
        with (EVAL_DATA_DIR / f"complaints__{cid}__test.jsonl").open("w") as fh:
            for rec in out:
                fh.write(json.dumps(rec) + "\n")
    if render_only:
        print(f"complaint texts written (bank B {'present' if b else 'missing'}; "
              f"{leaks} bank-B texts with leakage); nothing scored")
        return
    if b is None:
        raise SystemExit("bank B (differential/nlp/paraphrase_bank_b.py) is missing; T18 needs it")
    result: dict[str, Any] = {"gold": "reported symptoms (after complaint noise)",
                              "bank_b_texts_with_leakage": leaks}
    for bank, per in by_bank.items():
        result[f"{bank}_rules"] = score([p for v in per.values() for p in v])
        result[f"{bank}_rules_by_persona"] = {k: score(v) for k, v in per.items()}
    result.update(score_claude(b_texts))
    metrics_io.update("nlp", result)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
