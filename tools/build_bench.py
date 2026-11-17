"""Build docs/bench/index.html: the Differential Bench page (open it in any browser).

Replays held-out test units through the same engine the evaluation harness uses (system
"hybrid"), step by step, checks each replay against the stored test run (same measurement
sequence), adds the statistics of the stored test runs, and fills docs/bench/template.html.
Every number on the page comes from data/eval/runs/ and results/. Run from the repository
root: python tools/build_bench.py
"""
import base64
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from differential.agent.format import fault_label, fmt_reading
from differential.engine.session import DiagnosisSession
from eval import harness as H

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "bench" / "index.html"
CID = "channel_strip"
N_TEST, N_AGED, N_OOC = 30, 6, 4
spec = H.SYSTEMS["hybrid"]
bundle = H.bundle_for(CID, spec.model_variant)
KIND_WHAT = {"dc": "DC voltage", "ac": "gain at 1 kHz", "ac20": "gain at 20 Hz", "ac20k": "gain at 20 kHz",
             "hum": "hum (120 Hz)", "thd": "distortion (THD)", "lift": "lift and test the part"}


def label(h: str) -> str:
    return "No single fault fits (unmodeled)" if h == "unmodeled" else fault_label(h)


def groups_top(s: DiagnosisSession, k: int = 6) -> list[dict]:
    out = []
    for g, p in s.ranked_groups(k=k):
        if g == -1:
            out.append({"group": -1, "p": round(float(p), 4), "members": ["No single fault fits (unmodeled)"]})
        else:
            mem = [label(h) for h in bundle.groups.members(g)]
            out.append({"group": int(g), "p": round(float(p), 4), "members": mem})
    return out


def replay(row: dict, meta: dict, split: str) -> dict:
    case_id = str(row["case_id"])
    truth = str(row["hypothesis"])
    single = "+" not in truth and truth in bundle.hypotheses
    truth_refs = {H.parse_fault_id(f).ref for f in truth.split("+")}

    def measure(o) -> float:
        rng = np.random.default_rng(H.noise_seed(case_id, o.key))
        if o.is_lift:
            return float(H.simulate_lift(o.ref in truth_refs, rng))
        return H.simulate_reading(o.kind, float(row[o.key]), rng, float(row["fundamental"]))

    prior, from_complaint = H.make_prior(spec, bundle, meta)
    s = DiagnosisSession(bundle, policy=spec.policy, likelihood=spec.likelihood, prior=prior,
                         seed=H.noise_seed(case_id, "policy") % (2**31), cost_scale=spec.cost_scale,
                         complaint_prior=from_complaint, confirm_at=spec.confirm_at)
    steps, reason = [], ""
    start = {"groups": groups_top(s), "unmodeled": round(float(s.posterior()[-1]), 4),
             "entropy_bits": round(float(s.entropy_bits()), 3)}
    for _ in range(200):
        stop, reason = s.status()
        if stop:
            break
        rec = s.recommend()
        if rec is None:
            reason = "exhausted"
            break
        if s.policy in ("eig_per_cost", "eig") and rec.eig_bits < s.eig_min:
            reason = "uninformative"
            break
        o = rec.obs
        expected = []
        if not o.is_lift:
            for h, p in s.top_hypotheses(5):
                if h == "unmodeled" or len(expected) >= 3:
                    continue
                pr = s.expected_reading(o.key, h)
                if pr is not None:
                    m, lo, hi = pr
                    expected.append({"label": label(h), "p": round(float(p), 4), "predicted": fmt_reading(o.kind, m),
                                     "range": f"{fmt_reading(o.kind, lo)} to {fmt_reading(o.kind, hi)}"})
        alts = []
        for a in (rec.alternatives or [])[:3]:
            ao = getattr(a, "obs", None)
            alts.append({"key": getattr(ao, "key", str(a)), "eig_bits": round(float(getattr(a, "eig", getattr(a, "eig_bits", 0.0))), 3), "score": round(float(getattr(a, "score", 0.0)), 4),
                         "cost": float(getattr(ao, "cost", 0.0)) if ao is not None else None})
        value = measure(o)
        s.record(o.key, value)
        steps.append({
            "key": o.key, "what": KIND_WHAT.get(o.kind, o.kind), "tp": o.tp, "ref": o.ref, "hv": bool(o.hv),
            "cost": float(o.cost), "eig_bits": round(float(rec.eig_bits), 3),
            "entropy_before": round(float(rec.entropy_bits), 3), "alternatives": alts,
            "expected": expected,
            "reading": ("out of tolerance" if value >= 0.5 else "within tolerance") if o.is_lift else fmt_reading(o.kind, value),
            "spent": float(s.cost_spent), "groups": groups_top(s),
            "unmodeled": round(float(s.posterior()[-1]), 4),
        })
    else:
        reason = "max_steps"
    ranked = s.ranked_groups(k=10)
    truth_group = int(bundle.groups.group_of[bundle.hypotheses.index(truth)]) if single else -1
    top_group = int(ranked[0][0])
    truth_members = [label(h) for h in bundle.groups.members(truth_group)] if single else []
    return {
        "case_id": case_id, "split": split, "truth": truth,
        "truth_label": label(truth) if single else " + ".join(label(t) for t in truth.split("+")),
        "truth_group_members": truth_members, "single_fault": single,
        "aged": bool(row.get("aged", False)), "persona": meta.get("persona", ""),
        "complaint": meta.get("complaint", ""), "start": start, "steps": steps, "stop_reason": reason,
        "top_group": top_group, "confidence": round(float(ranked[0][1]), 4),
        "correct": (top_group == truth_group) if single else (top_group == -1),
        "effort": float(s.cost_spent), "keys": [st["key"] for st in steps],
        "ooc_outcome": None if single else H.unmodeled_outcome(bundle, truth, top_group),
    }


def pick(split: str, n: int, seed: int, single_only: bool = True) -> list[tuple[dict, dict]]:
    df, meta = H.load_split(CID, split)
    rows = df.to_dict("records")
    idx = list(range(len(rows)))
    if single_only:
        idx = [i for i in idx if "+" not in str(rows[i]["hypothesis"]) and str(rows[i]["hypothesis"]) in bundle.hypotheses]
    rng = np.random.default_rng(seed)
    chosen = sorted(rng.choice(idx, size=min(n, len(idx)), replace=False).tolist())
    return [(rows[i], meta[i]) for i in chosen]


cases = []
# four misses drawn at random from the stored test run, so the page shows failures too
_st = pd.read_parquet(ROOT / f"data/eval/runs/hybrid__{CID}__test.parquet")
_miss = sorted(np.random.default_rng(2029).choice(_st[_st.single_fault & ~_st.correct].case_id.to_numpy(), size=4, replace=False).tolist())
_df, _meta = H.load_split(CID, "test")
_rows = _df.to_dict("records")
_by_id = {str(r["case_id"]): (r, m) for r, m in zip(_rows, _meta, strict=True)}
for cid_ in _miss:
    r_, m_ = _by_id[cid_]
    c = replay(r_, m_, "test")
    c["drawn_as_miss"] = True
    c["matches_stored_run"] = json.loads(_st.set_index("case_id").loc[cid_, "keys"]) == c["keys"]
    cases.append(c)
    print("miss", cid_, c["truth"], "steps", len(c["steps"]), "correct", c["correct"], "match", c["matches_stored_run"])
for split, n, seed, single in (("test", N_TEST, 2026, True), ("test_aged", N_AGED, 2027, True), ("unmodeled_test", N_OOC, 2028, False)):
    try:
        picked = pick(split, n, seed, single)
    except Exception as e:
        print("skip split", split, e)
        continue
    stored = None
    sys_name = "hybrid"
    p = ROOT / f"data/eval/runs/{sys_name}__{CID}__{split}.parquet"
    if p.exists():
        stored = pd.read_parquet(p).set_index("case_id")
    for row, meta in picked:
        c = replay(row, meta, split)
        if stored is not None and c["case_id"] in stored.index:
            c["matches_stored_run"] = json.loads(stored.loc[c["case_id"], "keys"]) == c["keys"]
        cases.append(c)
        print(split, c["case_id"], c["truth"], "steps", len(c["steps"]), "correct", c["correct"],
              "match", c.get("matches_stored_run"))

# ---------- statistics from the stored test runs ----------
def summarize(df: pd.DataFrame) -> dict:
    d = df[df.single_fault]
    return {"n": len(d), "top1": round(float(d.correct.mean()), 4), "top3": round(float(d.top3.mean()), 4),
            "effort_mean": round(float(d.cost.mean()), 2), "steps_mean": round(float(d.steps.mean()), 2)}

stats = {"systems": {}, "by_circuit": {}, "by_kind": {}, "calibration": [], "steps_hist": {}, "effort_hist": {}}
main = ["random", "fixed_order", "half_split", "engine_gen", "engine_disc", "hybrid"]
for sysn in main:
    fs = sorted((ROOT / "data/eval/runs").glob(f"{sysn}__*__test.parquet"))
    if not fs:
        continue
    df = pd.concat([pd.read_parquet(f) for f in fs])
    stats["systems"][sysn] = {"all": summarize(df), "channel_strip": summarize(df[df.circuit == CID])}
    fa = sorted((ROOT / "data/eval/runs").glob(f"{sysn}__*__test_aged.parquet"))
    if fa:
        stats["systems"][sysn]["aged"] = summarize(pd.concat([pd.read_parquet(f) for f in fa]))
hy = pd.concat([pd.read_parquet(f) for f in sorted((ROOT / "data/eval/runs").glob("hybrid__*__test.parquet"))])
hs = hy[hy.single_fault]
for cid, g in hs.groupby("circuit"):
    stats["by_circuit"][cid] = {"n": len(g), "top1": round(float(g.correct.mean()), 4), "effort_mean": round(float(g.cost.mean()), 2)}
for k, g in hs.groupby("truth_kind"):
    stats["by_kind"][k] = {"n": len(g), "top1": round(float(g.correct.mean()), 4)}
bins = np.linspace(0, 1, 11)
conf = hs.confidence.to_numpy()
corr = hs.correct.to_numpy().astype(float)
for lo, hi in itertools.pairwise(bins):
    m = (conf >= lo) & (conf < hi if hi < 1 else conf <= hi)
    if m.sum():
        stats["calibration"].append({"lo": round(lo, 1), "hi": round(hi, 1), "n": int(m.sum()),
                                     "conf": round(float(conf[m].mean()), 4), "acc": round(float(corr[m].mean()), 4)})
stats["steps_hist"] = {int(k): int(v) for k, v in hs.steps.value_counts().sort_index().items()}
eff = np.minimum(hs.cost.to_numpy(), 40)
h, e = np.histogram(eff, bins=np.arange(0, 42, 2))
stats["effort_hist"] = {"edges": e.tolist(), "counts": h.tolist()}
sizes = pd.Series([len(bundle.groups.members(g)) for g in range(len(set(bundle.groups.group_of.tolist())))])
stats["group_sizes"] = {int(k): int(v) for k, v in sizes.value_counts().sort_index().items()}
stats["n_hypotheses"] = len(bundle.hypotheses)

targets = json.loads((ROOT / "results/targets.json").read_text())
tp = json.loads((ROOT / f"circuits/{CID}/{CID}_testpoints.json").read_text())
svg = (ROOT / f"circuits/{CID}/{CID}_schematic.svg").read_text()
svg_dark = (ROOT / f"circuits/{CID}/{CID}_schematic_dark.svg").read_text()
DATA = {"cases": cases, "stats": stats,
                           "targets": [{k: t.get(k) for k in ("id", "plain", "text", "pilot_text", "role", "primary")} for t in targets["targets"]],
                           "locked_on": targets.get("locked_on"), "testpoints": tp,
                           "schematic_svg": svg, "schematic_svg_dark": svg_dark}

# misses on the channel strip, described on the page next to the replayed misses
_cs = _st[_st.single_fault]
_m, _c = _cs[~_cs.correct], _cs[_cs.correct]
DATA["stats"]["misses"] = {"n": len(_m), "of": len(_cs),
                           "confident": int((_m.confidence >= 0.9).sum()),
                           "median_steps": float(_m.steps.median()),
                           "median_steps_correct": float(_c.steps.median()),
                           "unmodeled_share": round(float((_m.top_hypothesis == "unmodeled").mean()), 3)}


def svg_uri(svg_text: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg_text.encode()).decode()


page = (ROOT / "docs" / "bench" / "template.html").read_text(encoding="utf-8")
page = (page.replace("__SCH_LIGHT__", svg_uri(svg)).replace("__SCH_DARK__", svg_uri(svg_dark))
        .replace("__DATA__", json.dumps(DATA).replace("</", "<\\/")))
OUT.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
               '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
               + page + "\n</html>\n", encoding="utf-8")
print("wrote", OUT, OUT.stat().st_size, "bytes;", len(cases), "cases;",
      sum(1 for c in cases if c.get("matches_stored_run")), "match stored runs")
