"""End-to-end agent evaluation (target T17, plus agent-level accuracy).

For a stratified sample of test units, a scripted technician talks to the agent
exactly as a user of the demo would: sends the unit's complaint, takes every
recommended measurement on the simulated bench (same noise seeds as the engine
evaluation), records the owner's approval and a discharge reading at every
high-voltage point whenever a part removal is locked,
and finally asks for the repair ticket. Every assistant message and the ticket go
through the grounding check; the numbers it could not trace are counted.
In live or replay mode the same script drives Claude (needs a key or a cache).
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import numpy as np

from differential.agent.agent import DifferentialAgent
from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from differential.instruments.simulated import SimulatedBench
from differential.safety.hazards import discharge_points
from eval import metrics_io
from eval.cases import load_cases
from eval.lock import require_lock

SAMPLE = {COMPOSITE_ID: 40, **dict.fromkeys(BLOCK_IDS, 12)}
MAX_TURNS = 30


def run_case(row: dict[str, Any], complaint: str, mode: str) -> dict[str, Any]:
    bench = SimulatedBench.from_case_row(row)
    agent = DifferentialAgent(str(row["circuit"]), mode=mode, instrument=bench)
    t0 = time.perf_counter()
    agent.user_message(complaint)
    for _ in range(MAX_TURNS):
        key = agent.pending_key
        if key is None:
            break
        # safety records come from the app's forms, never from chat text (red team, round 6)
        if key == "bring_up":
            agent.record_bring_up("variac", "evaluation: brought up on a variac")
            continue
        if key == "approval":
            agent.record_owner_approval("evaluation: the owner agreed")
            continue
        if key == "discharge":
            pts = discharge_points(str(row["circuit"]))
            agent.record_discharge(dict.fromkeys(pts, 0.3), meter_proved=True)
            continue
        if key in ("supervisor", "guess"):  # trainee mode only; the evaluation is a technician
            break
        agent.measure(key)
    ticket = agent.ticket()
    groups = agent.tb.bundle.groups
    hyps = agent.tb.bundle.hypotheses
    truth = str(row["hypothesis"])
    belief = agent.tb.t_get_belief()
    top = belief["ranked_groups"][0]["group"]
    msgs = [g for g in agent.grounding_log if g["where"] == "message"]
    return {
        "case_id": row["case_id"], "circuit": row["circuit"], "truth": truth,
        "correct": top == int(groups.group_of[hyps.index(truth)]),
        "messages": len(msgs),
        "numbers_checked": sum(g["checked"] for g in msgs) + ticket["grounding"]["checked"],
        "ungrounded_final": sum(len(g["ungrounded"]) for g in msgs)
        + len(ticket["grounding"]["ungrounded"]),
        "ungrounded_before_check": sum(len(g["ungrounded"]) for g in agent.grounding_log
                                       if g["where"] == "live_first_draft"),
        "safety_events": len(agent.safety_log),
        "effort": agent.tb.engine.cost_spent,
        "seconds": time.perf_counter() - t0,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="offline", choices=["offline", "live", "replay"])
    ap.add_argument("--split", default="test")
    ap.add_argument("--scale", type=float, default=1.0, help="fraction of the sample to run")
    args = ap.parse_args(argv)
    if args.split == "test":
        require_lock("run the agent on test units")
    results = []
    for cid, n in SAMPLE.items():
        df, meta = load_cases(cid, args.split)
        by_id = {m["case_id"]: m for m in meta}
        ok = df[df["ok"]]
        rng = np.random.default_rng(20260928 + len(cid))
        k = max(1, round(n * args.scale))
        idx = rng.choice(len(ok), size=min(k, len(ok)), replace=False)
        for i in sorted(idx):
            row = ok.iloc[int(i)].to_dict()
            results.append(run_case(row, str(by_id[row["case_id"]]["complaint"]), args.mode))
    checked = sum(r["numbers_checked"] for r in results)
    ungrounded = sum(r["ungrounded_final"] for r in results)
    out = {"mode": args.mode, "split": args.split, "n_sessions": len(results),
           "messages": sum(r["messages"] for r in results), "numbers_checked": checked,
           "ungrounded_final": ungrounded,
           "ungrounded_rate": ungrounded / checked if checked else 0.0,
           "ungrounded_before_check": sum(r["ungrounded_before_check"] for r in results),
           "agent_top1": float(np.mean([r["correct"] for r in results])),
           "mean_seconds_per_session": float(np.mean([r["seconds"] for r in results])),
           "safety_events": sum(r["safety_events"] for r in results)}
    section = f"agent_{args.mode}" + ("" if args.split == "test" else f"_{args.split}")
    metrics_io.update(section, out)
    (metrics_io.METRICS.parent / f"{section}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in results) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
