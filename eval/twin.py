"""Healthy-channel comparison baseline ("twin"; promised in M1 for M2, reported without a bar).

In stereo and multichannel gear a technician compares the faulty channel with the healthy
one, point by point. Twin units: the stereo version of the channel strip, channel A the
test unit exactly as the other methods see it (its part values, age, mains and fault), and
channel B a healthy channel with its own tolerance draw and, for aged units, its own aging,
on the same supply: every supply part takes channel A's value, and a supply fault is in
both channels. Approximation: each channel is simulated with its own copy of that supply,
so a fault that loads a rail in channel A does not pull channel B's rail down with it, as
one shared supply would. That favors the comparison (a loaded rail then points at channel
A) and is stated wherever the result is reported.

Two variants, both scored like every other method (same units, budget, instrument noise
with channel A's seeds, unsoldering test and effort to a confirmed answer):

* ``twin`` (the baseline): a script like the chart and half-split tracing
  (``differential/engine/session.py``, policy "twin"). It shares the engine's inference,
  stopping rule and unsoldering rule, and differs only in where it measures next: the two
  outputs with the test tone; if they differ, a half-split of the stage outputs by
  comparison, the signal traced inside the first stage that differs, then that stage's
  DC points (the next stage's if they all agree, then the one before); with the outputs
  alike, the chart order, supply first. Both channels' readings are charged, except at the
  shared supply; ``twin_one_cost`` charges a comparison once, as a two-channel instrument
  would take it. Its unsoldering threshold is tuned on the pilot by the scripts' rule
  (ADR-046); "differs" is fixed in advance (``differential/engine/compare.py``: 10%).
* ``twin_model_free``: the same comparisons with no model at all, as a technician without
  Differential would work: the parts on the nodes that differ, ranked by the largest DC
  difference on their nodes, by where the signal first differs and by how often that kind
  of part fails, unsoldered and tested in turn until one tests defective; the supply is
  judged against the manual's chart. If the budget runs out, the leading untested suspect
  is named.

    python -m eval.twin simulate --split pilot     # channel B for every channel-strip unit
    python -m eval.twin tune                       # the twin's unsoldering threshold (pilot)
    python -m eval.twin run --split test           # after the targets-locked tag
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from differential.circuits.library import COMPOSITE_ID, get_circuit
from differential.circuits.model import CircuitSpec
from differential.config import EVAL_DATA_DIR
from differential.engine.compare import DIFFER_REL, channels_differ
from differential.engine.session import DEFAULT_BUDGET, SCRIPT_CONFIRM_AT, DiagnosisSession
from differential.instruments.simulated import noise_seed
from differential.sim.draws import Draw, age_draw, healthy_draw
from differential.sim.faults import Fault, parse_fault_id
from differential.sim.measurement import reading_to_engine, simulate_lift, simulate_reading
from differential.sim.montecarlo import SPLIT_INDEX, TOL_SCALE, is_aged, make_draw
from differential.sim.observables import lift_observables, spice_observables
from differential.sim.runner import simulate_draws
from eval import metrics_io
from eval.harness import bundle_for, results_path

CID = COMPOSITE_ID
TWIN_SEED = 20260929
SUPPLY_STAGES = ("psu_lv", "psu_hv")
# The op-amp's and the line driver's supply pins: the local rails the half-split script
# checks with the supply (differential/engine/session.py).
LOCAL_RAILS = ("TP16", "TP23")
CONFIRM_SWEEP = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
# How often each kind of part fails, as bench lore ranks them (electrolytics first); used
# only to order parts that the readings cannot separate.
KIND_ORDER = ("electrolytic", "triode", "bjt", "opamp", "zener", "diode", "resistor",
              "film_cap", "ceramic_cap", "pot")


# ------------------------------------------------------------------ simulation
def _supply_refs(circuit: CircuitSpec) -> set[str]:
    return {c.ref for c in circuit.components if c.stage in SUPPLY_STAGES}


def _is_supply_key(name: str, refs: set[str]) -> bool:
    """Whether a drawn element (or model clone) belongs to the shared supply: a supply
    part, one of its parasitic elements (``RESR_C101``, ``VPVZ_D101``) or the
    transformer and rectifier sources that carry the mains."""
    if name in refs or name.startswith(("VPK_", "VCRES_")):
        return True
    return name.rsplit("_", 1)[-1] in refs


def twin_draw(circuit: CircuitSpec, split: str, hyp_index: int, hypothesis: str,
              draw: int) -> tuple[Draw, Fault | list[Fault]]:
    """Channel B's parameter draw and the fault it carries (a supply fault is shared)."""
    a = make_draw(circuit.id, split, hyp_index, hypothesis, draw)
    rng = np.random.default_rng([TWIN_SEED, SPLIT_INDEX[split], hyp_index, draw])
    b = healthy_draw(circuit, rng, TOL_SCALE.get(split, 1.0))
    if is_aged(split, hyp_index, draw):
        age_draw(circuit, b, rng)
    refs = _supply_refs(circuit)
    for k, v in a.alters.items():
        if _is_supply_key(k, refs):
            b.alters[k] = v
    for (model, param), v in a.altermods.items():
        if _is_supply_key(model, refs):
            b.altermods[(model, param)] = v
    if "mains_factor" in a.severity:
        b.severity["mains_factor"] = a.severity["mains_factor"]
    shared = [parse_fault_id(f) for f in hypothesis.split("+")
              if hypothesis != "healthy" and parse_fault_id(f).ref in refs]
    if not shared:
        return b, parse_fault_id("healthy")
    return b, shared[0] if len(shared) == 1 else shared


def _simulate_chunk(args: tuple[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    split, cases = args
    circuit = get_circuit(CID)
    obs = spice_observables(circuit)
    out = []
    for c in cases:
        d, target = twin_draw(circuit, split, int(c["hyp_index"]), str(c["hypothesis"]),
                              int(c["draw"]))
        r = simulate_draws(circuit, target, [(0, d)], with_thd=True).results[0]
        row: dict[str, Any] = {"case_id": c["case_id"], "hypothesis": c["hypothesis"],
                               "ok": bool(r.ok), "reason": r.reason,
                               "fundamental": float(r.fundamental)}
        for o, v in zip(obs, r.values, strict=True):
            row[o.key] = float(v)
        out.append(row)
    return out


def twin_path(split: str) -> Any:
    return EVAL_DATA_DIR / f"twins__{CID}__{split}.parquet"


def simulate(split: str, workers: int = 4, chunk: int = 25) -> pd.DataFrame:
    if "test" in split:
        from eval.lock import require_lock

        require_lock("simulate twins of test units")
    df = pd.read_parquet(EVAL_DATA_DIR / f"cases__{CID}__{split}.parquet")
    cases = df[["case_id", "hyp_index", "draw", "hypothesis"]].to_dict("records")
    parts = [(split, cases[i:i + chunk]) for i in range(0, len(cases), chunk)]
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, got in enumerate(ex.map(_simulate_chunk, parts), 1):
            rows += got
            print(f"twins {split}: {min(i * chunk, len(cases))}/{len(cases)}", flush=True)
    out = pd.DataFrame(rows)
    out.to_parquet(twin_path(split), index=False, compression="zstd")
    return out


# ------------------------------------------------------------------- procedure
@lru_cache(maxsize=1)
def _chart() -> DiagnosisSession:
    """A session used only for its healthy bands: the manual chart the scripts read."""
    return DiagnosisSession(bundle_for(CID), policy="half_split")


def _normal(kind: str, key: str, reading: float) -> bool:
    s = _chart()
    if key not in s.gen.keys:
        return True
    lo, hi = s._healthy_band(key)
    return lo <= reading_to_engine(kind, reading) <= hi


class _Budget(Exception):
    pass


class TwinProcedure:
    """One diagnosis of one twin unit."""

    def __init__(self, bundle: Any, row_a: Mapping[str, Any], row_b: Mapping[str, Any],
                 rel: float = DIFFER_REL, budget: float = DEFAULT_BUDGET,
                 charge_both: bool = True) -> None:
        self.bundle = bundle
        self.c: CircuitSpec = bundle.circuit
        self.obs = bundle.observables
        self.a, self.b = row_a, row_b
        self.case_id = str(row_a["case_id"])
        self.truth = str(row_a["hypothesis"])
        self.truth_refs = ({parse_fault_id(f).ref for f in self.truth.split("+")}
                           if self.truth != "healthy" else set())
        self.rel, self.budget, self.charge_both = rel, budget, charge_both
        self.spent = 0.0
        self.keys: list[str] = []
        self.trace_cost: list[float] = []
        self.differing: dict[str, float] = {}  # node -> largest relative difference
        self.differing_dc: dict[str, float] = {}  # the same, DC readings only
        self.first_node: str | None = None  # where the signal first differs
        self.prev_node: str | None = None  # the signal point before it (still alike)
        self.tested: dict[str, int] = {}
        self.tp = {t.id: t for t in self.c.test_points}
        self.nodes = self._part_nodes()

    # readings
    def _charge(self, key: str, cost: float) -> None:
        if self.spent + cost > self.budget + 1e-9:
            raise _Budget
        self.spent += cost
        self.keys.append(key)
        self.trace_cost.append(self.spent)

    def read_a(self, key: str) -> float:
        o = self.obs[key]
        self._charge(key, o.cost)
        rng = np.random.default_rng(noise_seed(self.case_id, key))
        return simulate_reading(o.kind, float(self.a[key]), rng, float(self.a["fundamental"]))

    def compare(self, key: str) -> tuple[bool, float]:
        o = self.obs[key]
        if self.spent + o.cost * (2 if self.charge_both else 1) > self.budget + 1e-9:
            raise _Budget
        va = self.read_a(key)
        if self.charge_both:
            self._charge(f"twin|{key}", o.cost)
        rng = np.random.default_rng(noise_seed(self.case_id + "|twin", key))
        vb = simulate_reading(o.kind, float(self.b[key]), rng, float(self.b["fundamental"]))
        diff, score = channels_differ(o.kind, va, vb, self.rel)
        if diff and o.tp is not None:
            node = self.tp[o.tp].node
            self.differing[node] = max(self.differing.get(node, 0.0), score)
            if o.kind == "dc":
                self.differing_dc[node] = max(self.differing_dc.get(node, 0.0), score)
        return diff, score

    def lift(self, ref: str) -> bool:
        key = f"lift:{ref}"
        self._charge(key, self.obs[key].cost)
        rng = np.random.default_rng(noise_seed(self.case_id, key))
        v = simulate_lift(ref in self.truth_refs, rng)
        self.tested[ref] = v
        return v == 1

    # topology
    def _part_nodes(self) -> dict[str, set[str]]:
        els = {e.name: e for e in self.c.netlist.elements}
        out = {}
        for comp in self.c.components:
            nodes: set[str] = set()
            for name in comp.elements.values():
                if name in els:
                    nodes |= {n for n in els[name].nodes if n != "0"}
            out[comp.ref] = nodes
        return out

    def suspects(self, stages: Sequence[str]) -> list[str]:
        """Parts to unsolder, in order: those on the nodes that differ most (DC before AC,
        since a DC difference sits at the part), then by how often the kind fails; parts on
        a differing node come first whatever their stage, then the rest of ``stages``."""
        def dev(p: Any, d: dict[str, float]) -> float:
            return max((d[n] for n in self.nodes[p.ref] if n in d), default=0.0)

        def key(p: Any) -> tuple[float, float, int, str]:
            kind = KIND_ORDER.index(p.kind) if p.kind in KIND_ORDER else len(KIND_ORDER)
            nodes = self.nodes[p.ref]
            at = float(self.first_node in nodes) + 0.5 * float(self.prev_node in nodes)
            return (-(dev(p, self.differing_dc) + at), -dev(p, self.differing), kind, p.ref)

        touching = sorted((p for p in self.c.components if self.nodes[p.ref] & set(self.differing)),
                          key=key)
        rest = sorted((p for p in self.c.components
                       if p.stage in stages and not self.nodes[p.ref] & set(self.differing)), key=key)
        return [p.ref for p in touching] + [p.ref for p in rest]

    # procedure
    def _compare_dc(self, stages: Sequence[str]) -> bool:
        hit = False
        for t in self.c.test_points:
            if t.stage in stages and "dc" in t.measurements and f"dc:{t.id}" not in self.keys:
                hit = self.compare(f"dc:{t.id}")[0] or hit
        return hit

    def _chart_supply(self, kind: str) -> bool:
        """Supply points against the manual's chart (the supply is shared, so the other
        channel is no reference); marks the ones out of range."""
        bad = False
        for t in self.c.test_points:
            if t.stage in SUPPLY_STAGES and kind in t.measurements:
                k = f"{kind}:{t.id}"
                if not _normal(kind, k, self.read_a(k)):
                    self.differing[t.node] = max(self.differing.get(t.node, 0.0), 1.0)
                    if kind == "dc":
                        self.differing_dc[t.node] = max(self.differing_dc.get(t.node, 0.0), 1.0)
                    bad = True
        return bad

    def localize(self) -> list[str]:
        """Narrow the search; ``self.focus`` always holds the stages to search if the
        budget runs out. Returns the stages, most likely first (empty: nothing differs)."""
        c = self.c
        chan = [s for s, _ in c.stages if s not in SUPPLY_STAGES]
        # each stage's output: its last signal point, in signal order (signal tracing)
        outs = [k for k in (next((f"ac:{t.id}" for t in reversed(c.test_points)
                                  if t.stage == st and "ac" in t.measurements), None)
                            for st in chan) if k]
        self.focus = chan[::-1]
        if outs and self.compare(outs[-1])[0]:  # one channel's output differs
            lo, hi = 0, len(outs) - 1
            while lo < hi:
                self.focus = [self.tp[k[3:]].stage for k in outs[lo:hi + 1]][::-1]
                mid = (lo + hi) // 2
                if self.compare(outs[mid])[0]:
                    hi = mid
                else:
                    lo = mid + 1
            first = chan.index(self.tp[outs[hi][3:]].stage)
            # trace the signal inside that stage to the first point that differs
            pts = [f"ac:{t.id}" for t in c.test_points
                   if t.stage == chan[first] and "ac" in t.measurements]
            a, b = 0, len(pts) - 1
            self.focus = [chan[first]]
            while a < b:
                m = (a + b) // 2
                if self.compare(pts[m])[0]:
                    b = m
                else:
                    a = m + 1
            self.first_node = self.tp[pts[b][3:]].node
            before = pts[b - 1] if b > 0 else (outs[hi - 1] if hi > 0 else None)
            self.prev_node = self.tp[before[3:]].node if before else None
            # the first stage whose output differs; if its DC points agree, the next stage
            # may be loading it, then the one before may be feeding it wrong
            for i in (first, first + 1, first - 1):
                if 0 <= i < len(chan):
                    self.focus = [chan[i]]
                    if self._compare_dc([chan[i]]):
                        return [chan[i]]
            return [chan[first]]
        # Both outputs alike: a shared (supply) fault, or one that leaves the gain alone.
        self.focus = list(SUPPLY_STAGES)
        if self._chart_supply("dc"):
            return list(SUPPLY_STAGES)
        for stage in chan:  # DC points stage by stage, in chart order
            self.focus = [stage]
            if self._compare_dc([stage]):
                return [stage]
        out = next((t for t in reversed(c.test_points) if "ac20" in t.measurements), None)
        if out is None:
            return []
        self.focus = ["tone", *[s for s in chan if s != "tone"]]
        if any(self.compare(f"{k}:{out.id}")[0] for k in ("ac20", "ac20k")):
            return self.focus  # the frequency response: the tone stack first
        self.focus = chan[::-1]
        if any(k in out.measurements and self.compare(f"{k}:{out.id}")[0] for k in ("hum", "thd")):
            return self.focus
        self.focus = list(SUPPLY_STAGES)
        if self._chart_supply("hum"):  # ripple in both channels
            return list(SUPPLY_STAGES)
        return []

    def run(self) -> dict[str, Any]:
        stages: list[str] = []
        answer: str | None = None
        confirmed = False
        self.focus: list[str] = []
        try:
            stages = self.localize()
            for ref in self.suspects(stages):
                if self.lift(ref):
                    answer, confirmed = ref, True
                    break
        except _Budget:
            stages = stages or self.focus
        if answer is None and (stages and (self.differing or self.tested)):
            answer = next((r for r in self.suspects(stages) if r not in self.tested), None)
        return self._row(answer, confirmed, stages)

    def _row(self, answer: str | None, confirmed: bool, stages: list[str]) -> dict[str, Any]:
        groups, hyps = self.bundle.groups, self.bundle.hypotheses
        single = "+" not in self.truth and self.truth in hyps
        truth_group = int(groups.group_of[hyps.index(self.truth)]) if single else -1
        truth_refs_group = ({parse_fault_id(h).ref for h in groups.members(truth_group)
                             if h != "healthy"} if single else set())
        if answer is None:
            top_group, top_hyp = -2, "healthy"  # no answer: nothing named, nothing flagged
        else:
            modes = [h for h in hyps if h != "healthy" and parse_fault_id(h).ref == answer]
            in_truth = [h for h in modes if int(groups.group_of[hyps.index(h)]) == truth_group]
            top_hyp = (in_truth or modes or ["healthy"])[0]
            top_group = int(groups.group_of[hyps.index(top_hyp)]) if top_hyp != "healthy" else -2
        return {
            "system": "twin", "case_id": self.case_id, "circuit": self.c.id, "truth": self.truth,
            "truth_group": truth_group, "single_fault": single, "top_group": top_group,
            "top_hypothesis": top_hyp, "answer_part": answer or "",
            "correct": top_group == truth_group and answer is not None,
            "correct_part": answer is not None and (answer in self.truth_refs
                                                    or answer in truth_refs_group),
            "confirmed": confirmed, "stages": json.dumps(stages),
            "cost": self.spent, "steps": len(self.keys),
            "stop_reason": "confirmed" if confirmed else ("budget" if answer else "nothing_differs"),
            "keys": json.dumps(self.keys), "trace_cost": json.dumps(self.trace_cost),
            "hv_reads": sum(1 for k in self.keys if not k.startswith("lift:")
                            and self.obs[k.split("|")[-1]].hv),
        }


def _model_free_chunk(args: tuple[bool, list[tuple[dict[str, Any], dict[str, Any]]]]
                      ) -> list[dict[str, Any]]:
    charge_both, pairs = args
    bundle = bundle_for(CID)
    return [TwinProcedure(bundle, a, b, charge_both=charge_both).run() for a, b in pairs]


def _session_one(args: tuple[str, dict[str, Any], dict[str, Any], float, bool]) -> dict[str, Any]:
    """The twin script on one unit, in the harness's result format (eval/harness.py)."""
    name, row, twin_row, confirm_at, charge_both = args
    bundle = bundle_for(CID)
    case_id, truth = str(row["case_id"]), str(row["hypothesis"])
    single = "+" not in truth and truth in bundle.hypotheses
    truth_refs = {parse_fault_id(f).ref for f in truth.split("+")} if truth != "healthy" else set()

    def measure(o: Any) -> float:
        rng = np.random.default_rng(noise_seed(case_id, o.key))
        if o.is_lift:
            return float(simulate_lift(o.ref in truth_refs, rng))
        return simulate_reading(o.kind, float(row[o.key]), rng, float(row["fundamental"]))

    def other(o: Any) -> float:
        rng = np.random.default_rng(noise_seed(case_id + "|twin", o.key))
        return simulate_reading(o.kind, float(twin_row[o.key]), rng, float(twin_row["fundamental"]))

    s = DiagnosisSession(bundle, policy="twin", seed=noise_seed(case_id, "policy") % (2**31),
                         confirm_at=confirm_at, twin_reading=other, twin_charge_both=charge_both)
    res = s.run(measure)
    groups = bundle.groups
    truth_group = int(groups.group_of[bundle.hypotheses.index(truth)]) if single else -1
    top_hyp = s.top_hypotheses(1)[0][0]
    named = ({parse_fault_id(h).ref for h in groups.members(res.top_group) if h != "healthy"}
             if res.top_group >= 0 else set())
    obs = bundle.observables
    return {
        "system": name, "case_id": case_id, "circuit": CID, "truth": truth,
        "truth_group": truth_group, "single_fault": single, "top_group": res.top_group,
        "top_hypothesis": top_hyp, "correct": res.top_group == truth_group,
        "correct_part": bool(truth_refs & named),
        "top3": truth_group in [g for g, _ in res.ranked_groups[:3]],
        "confidence": res.top_mass, "unmodeled_prob": res.unmodeled_prob,
        "cost": res.cost, "steps": res.steps, "stop_reason": res.stop_reason,
        "keys": json.dumps([r.key for r in res.readings]),
        "trace_cost": json.dumps([t.cost_spent for t in res.trace]),
        "hv_reads": sum(1 for r in res.readings if r.kind != "lift" and obs[r.key].hv),
    }


def _pairs(split: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    a = pd.read_parquet(EVAL_DATA_DIR / f"cases__{CID}__{split}.parquet")
    b = pd.read_parquet(twin_path(split)).set_index("case_id")
    return [(ra, b.loc[ra["case_id"]].to_dict() | {"case_id": ra["case_id"]})
            for ra in a.to_dict("records") if bool(ra["ok"]) and bool(b.loc[ra["case_id"], "ok"])]


def run_sessions(split: str, name: str = "twin", confirm_at: float | None = None,
                 charge_both: bool = True, workers: int = 4, write: bool = True) -> pd.DataFrame:
    if "test" in split:
        from eval.lock import require_lock

        require_lock("score test units")
    c = SCRIPT_CONFIRM_AT["twin"] if confirm_at is None else confirm_at
    args = [(name, a, b, c, charge_both) for a, b in _pairs(split)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        out = pd.DataFrame(list(ex.map(_session_one, args, chunksize=4)))
    if write:
        out.to_parquet(results_path(name, CID, split), index=False)
    return out


def run_model_free(split: str, charge_both: bool = True, workers: int = 4,
                   write: bool = True) -> pd.DataFrame:
    if "test" in split:
        from eval.lock import require_lock

        require_lock("score test units")
    pairs = _pairs(split)
    n = max(1, len(pairs) // (workers * 4))
    chunks = [(charge_both, pairs[i:i + n]) for i in range(0, len(pairs), n)]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        out = pd.DataFrame([r for got in ex.map(_model_free_chunk, chunks) for r in got])
    if write:
        out.to_parquet(results_path("twin_model_free", CID, split), index=False)
    return out


def model_free_effort(df: pd.DataFrame) -> pd.DataFrame:
    """Effort to a confirmed answer (ADR-041) for the model-free rows: an answer the
    procedure did not confirm is charged one unsoldering test of the named part."""
    obs = {o.key: o for o in lift_observables(get_circuit(CID))}
    charge = [0.0 if (r.confirmed or not r.answer_part) else obs[f"lift:{r.answer_part}"].cost
              for r in df.itertuples(index=False)]
    return df.assign(confirm_cost=charge, confirmed_cost=df["cost"] + np.array(charge))


def summarize(df: pd.DataFrame, model_free: bool = False) -> dict[str, float]:
    if model_free:
        d = model_free_effort(df)
    else:
        from eval.effort import breakdown

        d = breakdown(df, CID)
    return {"n": len(d), "top1": float(d["correct"].mean()),
            "top1_part": float(d["correct_part"].mean()),
            "confirmed_effort": float(d["confirmed_cost"].mean()),
            "effort": float(d["cost"].mean()), "hv_reads": float(d["hv_reads"].mean())}


def tune(workers: int = 4) -> dict[str, Any]:
    """The twin script's unsoldering threshold, by the scripts' rule (ADR-046), on the pilot."""
    rows = {}
    for c in CONFIRM_SWEEP:
        rows[c] = summarize(run_sessions("pilot", confirm_at=c, workers=workers, write=False))
        print(c, rows[c], flush=True)
    best = max(v["top1"] for v in rows.values())
    pick = min((c for c, v in rows.items() if v["top1"] >= best - 0.01),
               key=lambda c: rows[c]["confirmed_effort"])
    res = {"rule": "lowest effort to a confirmed answer within 1 point of the best top-1 (ADR-046)",
           "sweep": {str(k): v for k, v in rows.items()}, "confirm_at": pick}
    metrics_io.update("twin_tuning", res)
    return res


def comparison(split: str) -> dict[str, Any]:
    """The twin variants beside the engine and the scripts on the same channel-strip units."""
    from eval.effort import breakdown

    out: dict[str, Any] = {}
    for name in ("twin", "twin_one_cost", "twin_model_free"):
        p = results_path(name, CID, split)
        if p.exists():
            out[name] = summarize(pd.read_parquet(p), model_free=name == "twin_model_free")
    obs = bundle_for(CID).observables
    for name in ("engine_gen", "half_split", "fixed_order", "random"):
        p = results_path(name, CID, split)
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        keep = set(pd.read_parquet(results_path("twin", CID, split))["case_id"]) if "twin" in out else None
        if keep is not None:
            df = df[df["case_id"].isin(keep)]
        d = breakdown(df, CID)
        named = [({parse_fault_id(h).ref for h in bundle_for(CID).groups.members(int(g)) if h != "healthy"}
                  if int(g) >= 0 else set()) for g in d["top_group"]]
        truth = [{parse_fault_id(f).ref for f in t.split("+")} for t in d["truth"]]
        hv = [sum(1 for k in json.loads(ks) if not k.startswith("lift:") and obs[k].hv) for ks in d["keys"]]
        out[name] = {"n": len(d), "top1": float(d["correct"].mean()),
                     "top1_part": float(np.mean([bool(a & b) for a, b in zip(named, truth, strict=True)])),
                     "confirmed_effort": float(d["confirmed_cost"].mean()),
                     "effort": float(d["cost"].mean()), "hv_reads": float(np.mean(hv))}
    metrics_io.update(f"twin_{split}", out)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("simulate", "tune", "run"))
    ap.add_argument("--split", default="pilot")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    if args.action == "simulate":
        df = simulate(args.split, args.workers)
        print(f"{int(df['ok'].sum())} of {len(df)} twins simulated")
    elif args.action == "tune":
        print(json.dumps(tune(args.workers), indent=1))
    else:
        run_sessions(args.split, workers=args.workers)
        run_sessions(args.split, name="twin_one_cost", charge_both=False, workers=args.workers)
        run_model_free(args.split, workers=args.workers)
        print(json.dumps(comparison(args.split), indent=1))


if __name__ == "__main__":
    main()
