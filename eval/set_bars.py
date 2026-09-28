"""Set every pilot-estimable target bar by one rule, before the targets are locked.

Rule (ADR-029), fixed before the protocol-matched pilot was run:

    bar = pilot estimate moved against the system by K = 1.5 standard errors,
          rounded to the nearest reporting step

Steps: 1 point for accuracies, margins and rates; 0.05 for effort ratios; 0.01
for calibration error and AUROC. Pooled quantities are weighted like the test set
(channel strip one half, each block one tenth), because the pilot's mix
(200 + 5 x 60 units) differs from the test's (500 + 5 x 100). Standard errors of
proportions use the add-two (Agresti-Coull) estimate, so a stratum with no
errors still carries uncertainty; paired differences use the unit-level standard
deviation; ratios, calibration error and AUROC use a bootstrap over pilot units
(2,000 resamples, units resampled within each circuit).

Targets the pilot cannot estimate keep their drafted bars: T5 and T21 need an API
key, T7 the hardware board, T15-T17 are absolute safety requirements, T18 was
fixed before the first extraction run (ADR-028), T19 before the first meter run,
and T20 is an engineering limit.

Reads the pilot runs in data/eval/runs/ (python -m eval.pilot_v2 makes them).
Writes the bars into results/targets.json and the metrics.json section "bars".
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from differential.config import RESULTS_DIR
from eval import metrics_io
from eval.harness import bundle_for, results_path, unmodeled_outcome
from eval.stats import auroc, ece

K = 1.5
N_BOOT = 2000
SEED = 20260928
CIRCUITS = [COMPOSITE_ID, *BLOCK_IDS]
WEIGHTS = {COMPOSITE_ID: 0.5, **dict.fromkeys(BLOCK_IDS, 0.1)}  # test-set mix
TARGETS = RESULTS_DIR / "targets.json"


def runs(system: str, split: str = "pilot") -> dict[str, pd.DataFrame]:
    return {cid: pd.read_parquet(results_path(system, cid, split)) for cid in CIRCUITS}


def ac_se(x: np.ndarray) -> float:
    """Add-two standard error of a proportion."""
    n = len(x)
    p = (float(np.sum(x)) + 2.0) / (n + 4.0)
    return math.sqrt(p * (1.0 - p) / (n + 4.0))


def weighted_prop(d: dict[str, pd.DataFrame], col: str) -> tuple[float, float]:
    est = sum(WEIGHTS[c] * float(d[c][col].mean()) for c in CIRCUITS)
    se = math.sqrt(sum(WEIGHTS[c] ** 2 * ac_se(d[c][col].to_numpy()) ** 2 for c in CIRCUITS))
    return est, se


def paired(a: pd.DataFrame, b: pd.DataFrame, col: str) -> np.ndarray:
    m = a[["case_id", col]].merge(b[["case_id", col]], on="case_id", suffixes=("_a", "_b"))
    return np.asarray(m[f"{col}_a"].astype(float) - m[f"{col}_b"].astype(float))


def weighted_paired_diff(a: dict[str, pd.DataFrame], b: dict[str, pd.DataFrame],
                         col: str) -> tuple[float, float]:
    ds = {c: paired(a[c], b[c], col) for c in CIRCUITS}
    est = sum(WEIGHTS[c] * float(ds[c].mean()) for c in CIRCUITS)
    se = math.sqrt(sum(WEIGHTS[c] ** 2 * float(ds[c].var(ddof=1)) / len(ds[c]) for c in CIRCUITS))
    return est, se


def stratified_boot(d: dict[str, pd.DataFrame], stat: Callable[[dict[str, pd.DataFrame]], float],
                    n_boot: int = N_BOOT) -> float:
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(n_boot):
        vals.append(stat({c: df.iloc[rng.integers(0, len(df), len(df))] for c, df in d.items()}))
    return float(np.std(vals, ddof=1))


def effort_ratio(num: dict[str, pd.DataFrame], den: dict[str, pd.DataFrame]) -> tuple[float, float]:
    both = {c: num[c][["case_id", "cost"]].merge(den[c][["case_id", "cost"]], on="case_id",
                                                 suffixes=("_n", "_d")) for c in CIRCUITS}

    def stat(d: dict[str, pd.DataFrame]) -> float:
        n = sum(WEIGHTS[c] * float(d[c]["cost_n"].mean()) for c in CIRCUITS)
        m = sum(WEIGHTS[c] * float(d[c]["cost_d"].mean()) for c in CIRCUITS)
        return n / m

    return stat(both), stratified_boot(both, stat)


def step_ece(d: dict[str, pd.DataFrame]) -> tuple[float, float]:
    df = pd.concat(d.values(), ignore_index=True)
    conf = [np.array(json.loads(m)) for m in df["trace_mass"]]
    corr = [np.array(json.loads(c), dtype=float) for c in df["trace_correct"]]

    def value(idx: np.ndarray) -> float:
        return ece(np.concatenate([conf[i] for i in idx]), np.concatenate([corr[i] for i in idx]))[0]

    rng = np.random.default_rng(SEED)
    boots = [value(rng.integers(0, len(conf), len(conf))) for _ in range(N_BOOT // 4)]
    return value(np.arange(len(conf))), float(np.std(boots, ddof=1))


def unmodeled_stats(system: str, singles: dict[str, pd.DataFrame]) -> dict[str, float]:
    u = runs(system, "unmodeled_pilot")
    oc = {c: np.array([unmodeled_outcome(bundle_for(c), t, int(g))
                       for t, g in zip(u[c]["truth"], u[c]["top_group"], strict=True)])
          for c in CIRCUITS}

    def rate(kind: str) -> tuple[float, float]:
        x = {c: oc[c] == kind for c in CIRCUITS}
        return (sum(WEIGHTS[c] * float(x[c].mean()) for c in CIRCUITS),
                math.sqrt(sum(WEIGHTS[c] ** 2 * ac_se(x[c]) ** 2 for c in CIRCUITS)))

    est, se = rate("misleading")
    flag, flag_se = rate("flagged")
    pos = np.concatenate([u[c]["unmodeled_prob"].to_numpy() for c in CIRCUITS])
    neg = np.concatenate([singles[c]["unmodeled_prob"].to_numpy() for c in CIRCUITS])
    rng = np.random.default_rng(SEED)
    boots = [auroc(pos[rng.integers(0, len(pos), len(pos))], neg[rng.integers(0, len(neg), len(neg))])
             for _ in range(N_BOOT)]
    return {"misleading": est, "misleading_se": se, "flagged": flag, "flagged_se": flag_se,
            "auroc": auroc(pos, neg),
            "auroc_se": float(np.std(boots, ddof=1)), "n_unmodeled": float(len(pos))}


def bar(est: float, se: float, higher_is_better: bool, step: float) -> float:
    raw = est - K * se if higher_is_better else est + K * se
    return round(round(raw / step) * step, 10)


def pts(x: float) -> str:
    v = round(100 * x)
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v)} points"


def derivation(tid: str, v: dict[str, Any]) -> str:
    """One sentence stating the pilot estimate and how the bar follows from it."""
    def f(x: float) -> str:
        if tid in ("T1", "T2", "T3", "T13_flagged", "T13_misleading"):
            return f"{100 * x:.1f}%"
        if tid in ("T4", "T6", "T14"):
            return f"{100 * x:+.1f} points" if tid != "T6" else f"{100 * x:.1f} points"
        return f"{x:.3f}"
    rule = f"bar = estimate moved {K} standard errors against the system, rounded (ADR-029)"
    if tid == "T4":
        return (f"Pilot margins {100 * v['estimate_vs_fixed_order']:+.1f} points over the fixed-order "
                f"chart and {100 * v['estimate_vs_random']:+.1f} over random probing; {rule}, "
                "taking the smaller of the two.")
    if tid == "T13":
        return (f"Pilot AUROC {v['estimate']:.3f} (SE {v['se']:.3f}), flagged "
                f"{100 * v['flagged_estimate']:.1f}% (SE {100 * v['flagged_se']:.1f}), misleading "
                f"{100 * v['misleading_estimate']:.1f}% (SE {100 * v['misleading_se']:.1f}) on "
                f"{int(v['n_unmodeled'])} units; {rule}.")
    se = f"{100 * v['se']:.1f} points" if tid in ("T1", "T2", "T3", "T4", "T6", "T14") \
        else f"{v['se']:.3f}"
    return f"Pilot estimate {f(v['estimate'])} (standard error {se}); {rule}."


def pilot_text(tid: str, v: dict[str, Any]) -> str:
    """The pilot estimate as printed next to its bar in the M1 targets table."""
    if tid in ("T1", "T2", "T3"):
        return f"{100 * v['estimate']:.1f}%"
    if tid == "T4":
        return (f"{100 * v['estimate_vs_fixed_order']:+.0f} / "
                f"{100 * v['estimate_vs_random']:+.0f} pts")
    if tid in ("T6", "T14"):
        sign = "+" if tid == "T14" else ""
        return f"{100 * v['estimate']:{sign}.1f} pts".replace("-", "−")
    if tid in ("T8", "T9", "T10", "T11"):
        return f"{v['estimate']:.2f}×"
    if tid == "T12":
        return f"{v['estimate']:.3f}"
    if tid == "T13":
        return (f"{v['estimate']:.2f}; {100 * v['flagged_estimate']:.0f}%; "
                f"{100 * v['misleading_estimate']:.0f}%")
    raise KeyError(tid)


def main() -> None:
    hyb, eng = runs("hybrid"), runs("engine_gen")
    fixed, half, rnd, recap = runs("fixed_order"), runs("half_split"), runs("random"), runs("recap_prior")
    wide = pd.read_parquet(results_path("hybrid", COMPOSITE_ID, "pilot_wide"))
    cs = COMPOSITE_ID
    d: dict[str, dict[str, Any]] = {}

    def put(tid: str, est: float, se: float, hib: bool, step: float, **extra: Any) -> float:
        b = bar(est, se, hib, step)
        d[tid] = {"estimate": est, "se": se, "k": K, "direction": ">=" if hib else "<=",
                  "step": step, "bar": b, **extra}
        return b

    t1 = put("T1", *weighted_prop(hyb, "correct"), True, 0.01)
    t2 = put("T2", float(hyb[cs]["correct"].mean()), ac_se(hyb[cs]["correct"].to_numpy()), True, 0.01)
    t3 = put("T3", *weighted_prop(hyb, "top3"), True, 0.01)
    m_fixed = paired(hyb[cs], fixed[cs], "correct")
    m_rand = paired(hyb[cs], rnd[cs], "correct")
    b_fixed = bar(float(m_fixed.mean()), float(m_fixed.std(ddof=1)) / math.sqrt(len(m_fixed)), True, 0.01)
    b_rand = bar(float(m_rand.mean()), float(m_rand.std(ddof=1)) / math.sqrt(len(m_rand)), True, 0.01)
    t4 = min(b_fixed, b_rand)
    d["T4"] = {"estimate_vs_fixed_order": float(m_fixed.mean()), "estimate_vs_random": float(m_rand.mean()),
               "bar_vs_fixed_order": b_fixed, "bar_vs_random": b_rand, "k": K, "direction": ">=",
               "step": 0.01, "bar": t4, "rule": "the smaller of the two margin bars"}
    a_cs, a_w = hyb[cs]["correct"].to_numpy(), wide["correct"].to_numpy()
    t6 = put("T6", float(a_cs.mean() - a_w.mean()), math.hypot(ac_se(a_cs), ac_se(a_w)), False, 0.01)
    t8 = put("T8", *effort_ratio(eng, fixed), False, 0.05)
    t9 = put("T9", *effort_ratio(eng, half), False, 0.05)
    t10 = put("T10", *effort_ratio(eng, rnd), False, 0.05)
    t11 = put("T11", *effort_ratio(hyb, eng), False, 0.05)
    t12 = put("T12", *step_ece(hyb), False, 0.01)
    us = unmodeled_stats("hybrid", hyb)
    t13 = put("T13", us["auroc"], us["auroc_se"], True, 0.01,
              flagged_estimate=us["flagged"], flagged_se=us["flagged_se"],
              flagged_bar=bar(us["flagged"], us["flagged_se"], True, 0.01),
              misleading_estimate=us["misleading"], misleading_se=us["misleading_se"],
              misleading_bar=bar(us["misleading"], us["misleading_se"], False, 0.01),
              n_unmodeled=us["n_unmodeled"])
    t14 = put("T14", *weighted_paired_diff(recap, eng, "correct"), True, 0.01)

    text = {
        "T1": f"≥ {round(100 * t1)}%", "T2": f"≥ {round(100 * t2)}%", "T3": f"≥ {round(100 * t3)}%",
        "T4": f"≥ {pts(t4)} each", "T6": f"≤ {round(100 * t6)} points",
        "T8": f"≤ {t8:.2f}×", "T9": f"≤ {t9:.2f}×", "T10": f"≤ {t10:.2f}×", "T11": f"≤ {t11:.2f}×",
        "T12": f"≤ {t12:.2f}",
        "T13": (f"AUROC ≥ {t13:.2f}; ≥ {round(100 * d['T13']['flagged_bar'])}% flagged; "
                f"≤ {round(100 * d['T13']['misleading_bar'])}% misleading"),
        "T14": f"≥ {pts(t14)}",
    }
    tj = json.loads(TARGETS.read_text())
    if tj.get("locked_on"):
        raise SystemExit("targets are locked; bars cannot change")
    for t in tj["targets"]:
        if t["id"] in d:
            t["drafted_value"] = t.get("drafted_value", t["value"])
            t["value"] = d[t["id"]]["bar"]
            t["text"] = text[t["id"]]
            t["pilot_dependent"] = True
            t["derivation"] = derivation(t["id"], d[t["id"]])
            t["pilot_text"] = pilot_text(t["id"], d[t["id"]])
            if t["id"] == "T13":
                t["value_flag_rate"] = d["T13"]["flagged_bar"]
                t["value_misleading"] = d["T13"]["misleading_bar"]
    tj["bar_rule"] = ("Each pilot-estimable bar is the protocol-matched pilot's estimate moved "
                      f"against the system by {K} standard errors and rounded to the reporting "
                      "step (eval/set_bars.py, ADR-029).")
    TARGETS.write_text(json.dumps(tj, indent=2, ensure_ascii=False) + "\n")
    metrics_io.update("bars", {"k": K, "weights": WEIGHTS, "targets": d})
    for tid, v in d.items():
        print(tid, text[tid], {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})


if __name__ == "__main__":
    main()
