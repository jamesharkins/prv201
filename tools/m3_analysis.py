"""Failure analysis for the M3 report, computed from committed evaluation runs.

Writes results/m3_analysis.json with:
  - t13_by_kind: outcome of every out-of-catalog test unit (hybrid system) by kind of
    alteration (double fault, wrong-value part, solder bridge) and by circuit;
  - agent_vs_engine: the offline agent's sessions next to the engine's stored run on the
    same test units, including sessions that ended without a measurement;
  - redteam: replies of the red-team harness by kind (refused, diagnosis started instead
    of answering, other), offline and live, from results/redteam_<mode>.json.

Usage: python tools/m3_analysis.py   (after `make eval` and the agent and red-team runs)
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
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


def main() -> None:
    result = {"t13_by_kind": t13_by_kind(), "agent_vs_engine": agent_vs_engine(),
              "redteam": redteam()}
    (RESULTS / "m3_analysis.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
