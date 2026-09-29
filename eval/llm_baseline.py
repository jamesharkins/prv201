"""LLM baselines (target T5): the same bench, the same budget, no Differential engine.

Protocol (identical for both variants, fixed before any live run):
  * Model: ``DIFFERENTIAL_MODEL`` (default claude-sonnet-5-5), default sampling; every
    response is cached by request hash, so a rerun replays exactly.
  * Inputs: the complaint text; the circuit description (stages, every part with its
    value, the SPICE netlist of the healthy circuit, every test point with its node,
    stage and whether it is high voltage); the healthy reading and tolerance range of
    every measurement (the service-manual voltage chart); the list of catalog faults it
    may name; the effort cost of every measurement and the 40-unit budget. The prompt
    was written once, before any run, and is not tuned on any unit.
  * Interaction: the model calls ``measure(key)`` and receives exactly the reading the
    other systems receive for that unit (same noise seed). It ends with
    ``diagnose(ranked_faults, confidence)``. If it overspends or stops without a
    diagnosis, the case is scored as wrong at the effort spent.
  * ``llm_sim`` adds ``simulate_fault(fault_id)``: the median reading of every
    measurement under that fault, from the same simulations the engine learned from
    (an LLM agent with simulator access, the rival approach of [19]).
  * Sessions: three independent sessions per unit (the attempt number is part of the
    request, so cached responses are not reused across attempts); the unit's answer is
    the group named first most often (ties: the first session's), its effort the mean.
  * Scoring: group-aware top-1 and top-3, exactly as for every other system.
Cases: a stratified subset of the test set (``SUBSET``): per circuit, cases are
chosen evenly across part kinds with a fixed seed.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from differential.agent.format import fault_label, fmt_reading
from differential.agent.llm import LLMClient, LLMUnavailable
from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from differential.engine.bundle import EngineBundle
from differential.engine.session import DEFAULT_BUDGET, DiagnosisSession
from differential.instruments.simulated import noise_seed
from differential.sim.faults import parse_fault_id, part_kind
from differential.sim.measurement import from_engine, simulate_lift, simulate_reading
from differential.sim.montecarlo import load_dataset
from differential.sim.observables import KIND_LABEL

SUBSET = {COMPOSITE_ID: 150, **dict.fromkeys(BLOCK_IDS, 30)}  # 300 paired units: about +-6 points on the margin
MAX_TURNS = 40
SESSIONS_PER_UNIT = 3

SYSTEM = (
    "You are an experienced audio electronics technician diagnosing a unit on the bench. "
    "Exactly one component has failed. Use the measure tool to take readings (each costs "
    "effort; stay within the budget), then call diagnose with your ranked list of the most "
    "likely faults, naming them exactly as in the fault list. Think like a technician: "
    "compare readings with the healthy values and their tolerances."
)


def select_subset(cid: str, df: pd.DataFrame, bundle: EngineBundle, n: int) -> list[str]:
    """Stratify by part kind: round-robin over kinds in a seeded random order."""
    rng = np.random.default_rng(20260928 + len(cid))
    ok = df[df["ok"]]
    by_kind: dict[str, list[str]] = {}
    for _, r in ok.iterrows():
        k = part_kind(bundle.circuit, parse_fault_id(str(r["hypothesis"])))
        by_kind.setdefault(k, []).append(str(r["case_id"]))
    for v in by_kind.values():
        rng.shuffle(v)
    out: list[str] = []
    kinds = sorted(by_kind)
    while len(out) < min(n, len(ok)):
        for k in kinds:
            if by_kind[k] and len(out) < n:
                out.append(by_kind[k].pop())
    return out


@lru_cache(maxsize=8)
def signatures(cid: str) -> dict[str, dict[str, float]]:
    """Median natural-unit reading of every SPICE observable under every fault."""
    df = load_dataset(cid, "train")
    df = df[df["ok"]]
    cols = [c for c in df.columns if ":" in c and not c.startswith("liftval:")]
    med = df.groupby("hypothesis")[cols].median()
    return {h: {k: float(v) for k, v in row.items()} for h, row in med.iterrows()}


def bench_description(bundle: EngineBundle) -> str:
    c = bundle.circuit
    s = DiagnosisSession(bundle)
    lines = [f"Circuit: {c.name}. {c.description}", "", "Stages: " +
             "; ".join(f"{sid} = {name}" for sid, name in c.stages), "", "Parts:"]
    lines += [f"- {p.ref}: {p.kind} {p.value} (stage {p.stage})" for p in c.components]
    lines += ["", "Netlist of the healthy circuit (SPICE; node names as in the test points):",
              c.netlist_path.read_text().strip(), "", "Test points:"]
    lines += [f"- {tp.id}: node {tp.node}, {tp.name} (stage {tp.stage})"
              f"{' (HIGH VOLTAGE)' if tp.hv else ''}" for tp in c.test_points]
    lines += ["", "Measurements (key | what | healthy reading and range | cost):"]
    for key, o in bundle.observables.items():
        if o.is_lift:
            continue
        lo, hi = s._healthy_band(key)
        mid = (lo + hi) / 2
        lines.append(f"- {key} | {KIND_LABEL[o.kind]} at {o.tp}{' (HIGH VOLTAGE)' if o.hv else ''}"
                     f" | {fmt_reading(o.kind, from_engine(o.kind, mid))} "
                     f"(range {fmt_reading(o.kind, from_engine(o.kind, lo))} to "
                     f"{fmt_reading(o.kind, from_engine(o.kind, hi))}) | cost {o.cost:g}")
    lines += ["- lift:<ref> | desolder one lead of a part and test it out of circuit | "
              "result: within or out of tolerance | cost 10 (12 for parts on high-voltage "
              "nodes)", "", "Fault list (name faults exactly like this):"]
    lines += [f"- {h}: {fault_label(h)}" for h in bundle.hypotheses if h != "healthy"]
    return "\n".join(lines)


def tools(with_sim: bool) -> list[dict[str, Any]]:
    t: list[dict[str, Any]] = [
        {"name": "measure", "description": "Take one measurement on the unit.",
         "input_schema": {"type": "object", "properties": {"key": {"type": "string"}},
                          "required": ["key"], "additionalProperties": False}},
        {"name": "diagnose", "description": "Finish with a ranked list of fault names.",
         "input_schema": {"type": "object", "properties": {
             "ranked_faults": {"type": "array", "items": {"type": "string"}},
             "confidence": {"type": "number"}},
             "required": ["ranked_faults", "confidence"], "additionalProperties": False}},
    ]
    if with_sim:
        t.append({"name": "simulate_fault",
                  "description": "Median reading of every measurement if this fault were present.",
                  "input_schema": {"type": "object", "properties": {
                      "fault": {"type": "string"}}, "required": ["fault"],
                      "additionalProperties": False}})
    return t


def run_case(client: LLMClient, bundle: EngineBundle, row: dict[str, Any], complaint: str,
             with_sim: bool, attempt: int = 0) -> dict[str, Any]:
    case_id = str(row["case_id"])
    truth = str(row["hypothesis"])
    truth_ref = parse_fault_id(truth).ref
    obs = bundle.observables
    spent = 0.0
    taken: list[str] = []
    result: dict[str, Any] = {"ranked": [], "confidence": None}

    def handler(name: str, args: dict[str, Any]) -> Any:
        nonlocal spent
        if name == "measure":
            key = str(args["key"])
            if key not in obs:
                return {"error": f"unknown measurement {key}"}
            o = obs[key]
            if spent + o.cost > DEFAULT_BUDGET:
                return {"error": "budget exceeded; call diagnose now"}
            spent += o.cost
            taken.append(key)
            rng = np.random.default_rng(noise_seed(case_id, key))
            if o.is_lift:
                v = float(simulate_lift(o.ref == truth_ref, rng))
                return {"key": key, "result": "out of tolerance" if v else "within tolerance",
                        "effort_spent": spent}
            v = simulate_reading(o.kind, float(row[key]), rng, float(row["fundamental"]))
            return {"key": key, "reading": fmt_reading(o.kind, v), "effort_spent": spent}
        if name == "simulate_fault" and with_sim:
            sig = signatures(bundle.circuit.id).get(str(args["fault"]))
            if sig is None:
                return {"error": "unknown fault"}
            return {k: fmt_reading(obs[k].kind, v) for k, v in sig.items() if k in obs}
        if name == "diagnose":
            result["ranked"] = [str(x) for x in args.get("ranked_faults", [])][:3]
            result["confidence"] = args.get("confidence")
            return {"ok": True}
        return {"error": f"unknown tool {name}"}

    user = (f"{bench_description(bundle)}\n\nBudget: {DEFAULT_BUDGET:g} effort units.\n\n"
            f"Customer complaint: {complaint}\n\nDiagnose the unit. (Session {attempt + 1} of "
            f"{SESSIONS_PER_UNIT}.)")
    msgs = [{"role": "user", "content": user}]
    for _ in range(MAX_TURNS):
        msgs, final = client.tool_loop(SYSTEM, msgs, tools(with_sim), handler, max_turns=1,
                                       purpose="llm_baseline")
        if result["ranked"] or final.get("stop_reason") != "tool_use":
            break
    groups = bundle.groups
    truth_group = int(groups.group_of[bundle.hypotheses.index(truth)])
    ranked_groups = [int(groups.group_of[bundle.hypotheses.index(h)])
                     for h in result["ranked"] if h in bundle.hypotheses]
    return {"case_id": case_id, "truth": truth, "ranked": json.dumps(result["ranked"]),
            "correct": bool(ranked_groups) and ranked_groups[0] == truth_group,
            "top3": truth_group in ranked_groups[:3], "cost": spent, "steps": len(taken),
            "confidence": result["confidence"],
            "top_kind": (part_kind(bundle.circuit, parse_fault_id(result["ranked"][0]))
                         if ranked_groups else "none")}


def majority(bundle: EngineBundle, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """The unit's answer: the group named first most often across its sessions (ties go to
    the earliest session); effort is the mean over sessions."""
    groups = bundle.groups

    def first_group(r: dict[str, Any]) -> int | None:
        ranked = [h for h in json.loads(r["ranked"]) if h in bundle.hypotheses]
        return int(groups.group_of[bundle.hypotheses.index(ranked[0])]) if ranked else None

    firsts = [first_group(r) for r in sessions]
    counts = {g: firsts.count(g) for g in firsts if g is not None}
    best = max(counts, key=lambda g: (counts[g], -firsts.index(g))) if counts else None
    chosen = next((r for r, g in zip(sessions, firsts, strict=True) if g == best), sessions[0])
    out = dict(chosen)
    out["cost"] = float(np.mean([r["cost"] for r in sessions]))
    out["sessions"] = json.dumps([{"ranked": r["ranked"], "correct": r["correct"], "cost": r["cost"]}
                                  for r in sessions])
    out["session_agreement"] = (counts.get(best, 0) / len(sessions)) if best is not None else 0.0
    return out


def run(system: str = "llm_only", client: LLMClient | None = None) -> pd.DataFrame | None:
    """Run a baseline over the stratified subset; None when no key and no cache."""
    from eval.harness import bundle_for, load_split
    from eval.lock import require_lock

    require_lock("run the language-model baselines on test units")
    client = client or LLMClient()
    rows = []
    try:
        for cid, n in SUBSET.items():
            bundle = bundle_for(cid)
            df, meta = load_split(cid, "test")
            by_id = {m["case_id"]: m for m in meta}
            for case_id in select_subset(cid, df, bundle, n):
                row = df[df["case_id"] == case_id].iloc[0].to_dict()
                sessions = [run_case(client, bundle, row, str(by_id[case_id]["complaint"]),
                                     with_sim=system == "llm_sim", attempt=a)
                            for a in range(SESSIONS_PER_UNIT)]
                res = majority(bundle, sessions)
                res.update({"system": system, "circuit": cid})
                rows.append(res)
    except LLMUnavailable:
        return None
    return pd.DataFrame(rows)


def main() -> None:
    """Run both LLM baselines and compare with the full system on the same units."""
    from eval import metrics_io
    from eval.harness import SYSTEMS, run_system
    from eval.stats import mcnemar, paired_diff

    for system in ("llm_only", "llm_sim"):
        df = run(system)
        if df is None:
            metrics_io.update(system, {"status": "pending: requires DIFFERENTIAL_API_KEY"})
            print(system, "pending: no API key and no cached responses")
            continue
        hyb = pd.concat([run_system(SYSTEMS["hybrid"], cid, "test") for cid in SUBSET],
                        ignore_index=True)
        m = df.merge(hyb[["case_id", "correct", "cost", "pred_kind", "truth_kind"]],
                     on="case_id", suffixes=("_llm", "_hybrid"))
        d = paired_diff(m["correct_hybrid"].to_numpy(float), m["correct_llm"].to_numpy(float))
        out = {"status": "measured", "n": len(m), "top1_llm": float(m["correct_llm"].mean()),
               "top1_hybrid": float(m["correct_hybrid"].mean()),
               "margin": d.as_dict(), "mcnemar": mcnemar(m["correct_hybrid"].to_numpy(),
                                                         m["correct_llm"].to_numpy()),
               "mean_cost_llm": float(m["cost_llm"].mean()),
               "mean_cost_hybrid": float(m["cost_hybrid"].mean()),
               "capacitor_share_llm": float(m["top_kind"].isin(("film_cap", "electrolytic")).mean()),
               "capacitor_share_true": float(m["truth_kind"].isin(("film_cap", "electrolytic")).mean())}
        metrics_io.update(system, out)
        print(system, json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
