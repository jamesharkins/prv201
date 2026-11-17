"""Re-measure prompt characterisation (ADR-053), on pilot units only.

A scripted technician runs the offline agent on pilot units (single faults, aged parts
and unmodeled double faults) exactly as eval/agent_eval.py does, taking each reading on
the simulated bench. Before each reading is recorded, the check that holds a typed
reading (DiagnosisSession.far_outside_suspects) is asked, read-only, about

* the genuine reading: a hold here is a false prompt (an extra step for the technician);
* common slips made from it: volts typed as millivolts and the reverse (x1000, x0.001),
  a decade range slip (x10, x0.1) and, for DC, a reversed lead (sign flip).

The session itself proceeds with the simulated reading, so nothing in the diagnosis
changes. Writes results/remeasure_check.json; it touches no test unit and no other result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from differential.agent.agent import DifferentialAgent
from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from differential.engine.session import FAR_Z, SUSPECT_MIN_P
from differential.instruments.simulated import SimulatedBench
from differential.safety.hazards import discharge_points
from eval.cases import load_cases

SPLITS = ("pilot", "pilot_aged", "unmodeled_pilot")
SLIPS = {"x1000": 1000.0, "x0.001": 0.001, "x10": 10.0, "x0.1": 0.1, "sign": -1.0}
OUT = Path("results/remeasure_check.json")


def run_unit(row: dict[str, Any], complaint: str, tally: dict[str, list[int]]) -> None:
    bench = SimulatedBench.from_case_row(row)
    agent = DifferentialAgent(str(row["circuit"]), mode="offline", instrument=bench)
    agent.user_message(complaint)
    for _ in range(30):
        key = agent.pending_key
        if key is None or key in ("supervisor", "guess"):
            break
        if key == "bring_up":
            agent.record_bring_up("variac", "evaluation: brought up on a variac")
            continue
        if key == "approval":
            agent.record_owner_approval("evaluation: the owner agreed")
            continue
        if key == "discharge":
            agent.record_discharge(dict.fromkeys(discharge_points(str(row["circuit"])), 0.3),
                                   meter_proved=True)
            continue
        engine = agent.tb.engine
        obs = engine._obs[key]
        reading = bench.measure(obs)
        if not obs.is_lift:
            value = reading.value
            tally["genuine"].append(int(engine.far_outside_suspects(key, value) is not None))
            for name, f in SLIPS.items():
                if name == "sign" and obs.kind != "dc":
                    continue
                slipped = value * f
                if obs.kind != "dc" and slipped <= 0:
                    continue
                # a slip that leaves the value where it was is not a slip (a reading near 0 V)
                if abs(slipped - value) <= max(0.05 * abs(value), 1e-3):
                    continue
                tally.setdefault(name, []).append(
                    int(engine.far_outside_suspects(key, slipped) is not None))
        agent.reading_event(key, reading.value, source=reading.source)  # as agent.measure does


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--units", type=int, default=20, help="pilot units per circuit and split")
    args = ap.parse_args(argv)
    out: dict[str, Any] = {"suspect_min_probability": SUSPECT_MIN_P, "far_sd": FAR_Z,
                           "splits": {}, "note": "pilot units only; read-only check"}
    for split in SPLITS:
        tally: dict[str, list[int]] = {"genuine": []}
        for cid in [COMPOSITE_ID, *BLOCK_IDS]:
            try:
                df, meta = load_cases(cid, split)
            except FileNotFoundError:
                continue
            by_id = {m["case_id"]: m for m in meta}
            ok = df[df["ok"]]
            rng = np.random.default_rng([20261117, len(cid), len(split)])
            idx = rng.choice(len(ok), size=min(args.units, len(ok)), replace=False)
            for i in sorted(idx):
                row = ok.iloc[int(i)].to_dict()
                run_unit(row, str(by_id[row["case_id"]]["complaint"]), tally)
        out["splits"][split] = {
            name: {"n": len(v), "held": int(sum(v)), "rate": (sum(v) / len(v)) if v else None}
            for name, v in tally.items()}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
