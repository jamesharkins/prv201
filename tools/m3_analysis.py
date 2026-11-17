"""Failure analysis for the M3 report, computed from committed evaluation runs.

Writes results/m3_analysis.json with:
  - t13_by_kind: outcome of every out-of-catalog test unit (hybrid system) by kind of
    alteration (double fault, wrong-value part, solder bridge) and by circuit;
  - agent_vs_engine: the offline agent's sessions next to the engine's stored run on the
    same test units, including sessions that ended without a measurement;
  - redteam: replies of the red-team harness by kind (refused, diagnosis started instead
    of answering, other), offline and live, from results/redteam_<mode>.json;
  - misses: the full system's misses on single faults, split into "no single fault fits"
    flags and wrong names, by circuit;
  - cost_ablation: the engine with and without effort weighting (readings taken, stops);
  - llm_only: the language-model-alone baseline (T5) replayed from the response cache (no
    key, no cost), next to the full system on the same units, by circuit and part kind.

Usage: python tools/m3_analysis.py   (after `make eval` and the agent and red-team runs)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # this checkout's code, not another installed copy
RUNS = ROOT / "data" / "eval" / "runs"
RESULTS = ROOT / "results"


def alteration_kind(truth: str) -> str:
    if "+" in truth:
        return "double_fault"
    if truth.upper().startswith("BRIDGE"):
        return "solder_bridge"
    return "wrong_value_part"


def t13_by_kind() -> dict[str, Any]:
    from eval import harness as H

    rows = []
    for f in sorted(RUNS.glob("hybrid__*__unmodeled_test.parquet")):
        d = pd.read_parquet(f)
        cid = str(d["circuit"].iloc[0])
        bundle = H.bundle_for(cid, H.SYSTEMS["hybrid"].model_variant)
        for truth, group in zip(d["truth"], d["top_group"], strict=True):
            rows.append({"circuit": cid, "kind": alteration_kind(str(truth)),
                         "outcome": H.unmodeled_outcome(bundle, str(truth), int(group))})
    df = pd.DataFrame(rows)
    out: dict[str, Any] = {"n": len(df), "by_kind": {}, "by_circuit": {}}
    for key, col in (("by_kind", "kind"), ("by_circuit", "circuit")):
        for k, g in df.groupby(col):
            counts = g["outcome"].value_counts().to_dict()
            out[key][str(k)] = {"n": len(g), **{str(o): int(c) for o, c in counts.items()},
                                "misleading_share": round(float((g["outcome"] == "misleading").mean()), 4)}
    return out


def agent_vs_engine() -> dict[str, Any]:
    before = RESULTS / "agent_offline_before_adr052.jsonl"
    path = before if before.exists() else RESULTS / "agent_offline.jsonl"
    sessions = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    engine = pd.concat([pd.read_parquet(f) for f in RUNS.glob("hybrid__*__test.parquet")])
    engine = engine.set_index("case_id")
    live_path = RESULTS / "agent_live.jsonl"
    live = {}
    if live_path.exists():
        live = {r["case_id"]: r for r in map(json.loads, live_path.read_text().splitlines()) if r}
    zero = [s for s in sessions if float(s["effort"]) == 0.0]
    return {
        "file": path.name, "n": len(sessions),
        "agent_correct": sum(bool(s["correct"]) for s in sessions),
        "engine_correct_same_units": int(sum(bool(engine.loc[s["case_id"], "correct"]) for s in sessions)),
        "sessions_without_measurement": len(zero),
        "wrong_without_measurement": sum(not s["correct"] for s in zero),
        "live_correct_on_those": sum(bool(live[s["case_id"]]["correct"]) for s in zero
                                     if not s["correct"] and s["case_id"] in live),
    }


def reply_kind(replies: list[dict[str, Any]]) -> str:
    from eval.redteam.harness import REFUSAL_MARKERS

    text = "\n".join(r["text"] for r in replies).lower()
    if any(r["meta"].get("refused") for r in replies) or any(m in text for m in REFUSAL_MARKERS):
        return "refused"
    first = replies[0]["text"].strip() if replies else ""
    if re.match(r"I couldn't match that description|I understood:", first):
        return "diagnosis_started"
    return "other"


def redteam() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in ("offline", "live"):
        p = RESULTS / f"redteam_{mode}.json"
        if not p.exists():
            continue
        res = json.loads(p.read_text())
        kinds: dict[str, Counter[str]] = {"attack": Counter(), "benign": Counter()}
        for r in res:
            side = "attack" if r["expect"] == "refuse" else "benign"
            kinds[side][reply_kind(r["replies"])] += 1
        out[mode] = {side: dict(c) for side, c in kinds.items()}
        out[mode]["endorsing_phrase_matches"] = sum(1 for r in res if r.get("matched"))
    return out


def llm_only_vs_system() -> dict[str, Any]:
    import numpy as np

    from eval import harness as H
    from eval import llm_baseline as B

    df = B.run("llm_only")  # replays data/llm_cache; None without a key or a cache
    if df is None:
        return {"status": "pending: no cached responses"}
    hyb = pd.concat([H.run_system(H.SYSTEMS["hybrid"], c, "test") for c in df["circuit"].unique()])
    m = df.merge(hyb[["case_id", "correct", "truth_kind"]], on="case_id", suffixes=("_llm", "_system"))
    wrong = same_part = 0
    for _, r in m[~m["correct_llm"]].iterrows():
        bundle = H.bundle_for(str(r["circuit"]))
        ranked = [h for h in json.loads(r["ranked"]) if h in bundle.hypotheses]
        if ranked:
            wrong += 1
            same_part += int(H.parse_fault_id(ranked[0]).ref == H.parse_fault_id(str(r["truth"])).ref)

    def table(col: str) -> dict[str, Any]:
        return {str(k): {"n": len(g), "llm": round(float(g["correct_llm"].mean()), 4),
                         "system": round(float(g["correct_system"].mean()), 4)}
                for k, g in m.groupby(col)}

    conf = pd.to_numeric(m["confidence"], errors="coerce")
    return {
        "n": len(m), "top1_llm": round(float(m["correct_llm"].mean()), 4),
        "top1_system": round(float(m["correct_system"].mean()), 4),
        "by_circuit": table("circuit"), "by_part_kind": table("truth_kind"),
        "wrong_named": wrong, "wrong_same_part_other_mode": same_part,
        "mean_confidence_right": round(float(np.nanmean(conf[m["correct_llm"]])), 3),
        "mean_confidence_wrong": round(float(np.nanmean(conf[~m["correct_llm"]])), 3),
        "units_all_sessions_agree": int((m["session_agreement"] == 1.0).sum()),
        "units_all_sessions_differ": int((m["session_agreement"] < 0.5).sum()),
        "mean_effort_llm": round(float(m["cost"].mean()), 2),
        "mean_steps_llm": round(float(m["steps"].mean()), 2),
    }


def misses() -> dict[str, Any]:
    """Single-fault test units the full system got wrong: flagged 'no single fault fits'
    (a refusal to name) or a wrong group named, by circuit; and the faults flagged most."""
    d = pd.concat([pd.read_parquet(f) for f in sorted(RUNS.glob("hybrid__*__test.parquet"))])
    d = d[d["single_fault"]]
    wrong = d[~d["correct"]]
    flagged = wrong["top_hypothesis"] == "unmodeled"
    out: dict[str, Any] = {"n": len(d), "misses": len(wrong), "flagged": int(flagged.sum()),
                           "wrong_name": int((~flagged).sum()), "by_circuit": {}}
    for cid, g in wrong.groupby("circuit"):
        f = g["top_hypothesis"] == "unmodeled"
        out["by_circuit"][str(cid)] = {"misses": len(g), "flagged": int(f.sum()),
                                       "wrong_name": int((~f).sum())}
    top = wrong[flagged]["truth"].value_counts().head(6)
    out["most_flagged"] = {str(k): int(v) for k, v in top.items()}
    return out


def cost_ablation() -> dict[str, Any]:
    """The engine with and without effort weighting: which readings it takes, how it stops,
    and how often it is right when it stops confident (the stop threshold is 0.90)."""
    scope = ("ac", "ac20", "ac20k", "hum", "thd")
    out: dict[str, Any] = {}
    for system in ("engine_gen", "engine_eig_nocost"):
        d = pd.concat([pd.read_parquet(f) for f in sorted(RUNS.glob(f"{system}__*__test.parquet"))])
        d = d[d["single_fault"]]
        keys = d["keys"].map(json.loads)
        steps = int(keys.map(len).sum())
        conf = d[d["stop_reason"] == "confident"]
        out[system] = {
            "n": len(d),
            "scope_step_share": round(sum(sum(1 for k in ks if k.split(":")[0] in scope) for ks in keys) / steps, 3),
            "lift_step_share": round(sum(sum(1 for k in ks if k.startswith("lift")) for ks in keys) / steps, 3),
            "stopped_confident_share": round(len(conf) / len(d), 3),
            "accuracy_when_confident": round(float(conf["correct"].mean()), 3),
        }
    return out


def main() -> None:
    result = {"t13_by_kind": t13_by_kind(), "agent_vs_engine": agent_vs_engine(),
              "redteam": redteam(), "llm_only": llm_only_vs_system(),
              "misses": misses(), "cost_ablation": cost_ablation()}
    (RESULTS / "m3_analysis.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
