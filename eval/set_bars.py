"""Set every pilot-estimable target bar by one rule, before the targets are locked.

Rule (ADR-029), fixed before the protocol-matched pilot was run:

    bar = pilot estimate moved against the system by K = 1.5 standard errors,
          rounded to the nearest reporting step

Decision rule (ADR-033): a target is met only when its one-sided 95% confidence bound
clears the bar. For every pilot-based target this script also reports the chance of
meeting the bar if the test units behave like the pilot units:
Phi(|estimate - bar| / SE_test - 1.645), with SE_test the pilot standard error scaled
by sqrt(n_pilot / n_test).

Steps: 1 point for accuracies, margins and rates; 0.05 for effort ratios; 0.01
for calibration error and AUROC. Pooled quantities are weighted like the test set
(channel strip one half, each block one tenth), because the pilot's mix
(200 + 5 x 60 units) differs from the test's (500 + 5 x 100). Standard errors of
proportions use the add-two (Agresti-Coull) estimate, so a stratum with no
errors still carries uncertainty; paired differences use the unit-level standard
deviation; ratios, calibration error and AUROC use a bootstrap over pilot units
(2,000 resamples, units resampled within each circuit).

Targets the pilot cannot estimate keep their drafted bars: T5 and T21 need an API
key, T7 the hardware board (its bar is fixed from what a pass must show, ADR-033),
T15-T17 are release gates, T18 was fixed before the first extraction run (ADR-028),
T19 before the first meter run, and T20 is an engineering limit.

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
from eval.effort import summary as effort_summary
from eval.effort import with_effort
from eval.harness import bundle_for, results_path, unmodeled_outcome
from eval.stats import auroc, brier_shown, ece, ece_equal_mass, log_loss, shown_calibration

K = 1.5
Z_ONE_SIDED = 1.6449
N_BOOT = 2000
SEED = 20260928
CIRCUITS = [COMPOSITE_ID, *BLOCK_IDS]
WEIGHTS = {COMPOSITE_ID: 0.5, **dict.fromkeys(BLOCK_IDS, 0.1)}  # test-set mix
TARGETS = RESULTS_DIR / "targets.json"
CAP_SHARE = 0.6  # capacitor-heavy prior and unit mix (T14)


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


def effort_ratio(num: dict[str, pd.DataFrame], den: dict[str, pd.DataFrame],
                 col: str = "confirmed_cost") -> tuple[float, float]:
    """Ratio of test-mix-weighted mean efforts; by default the effort to a confirmed
    answer (eval/effort.py, ADR-041)."""
    both = {c: num[c][["case_id", col]].merge(den[c][["case_id", col]], on="case_id",
                                              suffixes=("_n", "_d"))
            .rename(columns={f"{col}_n": "cost_n", f"{col}_d": "cost_d"}) for c in CIRCUITS}

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


def chance_met(est: float, se_pilot: float, b: float, higher_is_better: bool,
               n_pilot: float, n_test: float) -> float:
    """P(one-sided 95% bound clears the bar) if the test behaves like the pilot."""
    se_t = se_pilot * math.sqrt(n_pilot / n_test)
    gap = (est - b) if higher_is_better else (b - est)
    if se_t <= 0:
        return 1.0 if gap > 0 else 0.0
    return float(0.5 * (1 + math.erf((gap / se_t - Z_ONE_SIDED) / math.sqrt(2))))


def pts(x: float) -> str:
    v = round(100 * x)
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v)} points"


def shown_ece(d: dict[str, pd.DataFrame]) -> tuple[float, float, dict[str, float]]:
    """T12: equal-mass ECE of the probabilities shown for the first three groups at the stop,
    pooled over units weighted like the test mix (each circuit's pairs carry its weight)."""
    def pairs(dd: dict[str, pd.DataFrame]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        cs, ks, ws = [], [], []
        for c in CIRCUITS:
            r3 = [json.loads(x) for x in dd[c]["ranked3"]]
            conf, corr = shown_calibration(r3, list(dd[c]["truth_group"]))
            cs.append(conf)
            ks.append(corr)
            ws.append(np.full(len(conf), WEIGHTS[c] / max(len(conf), 1)))
        return np.concatenate(cs), np.concatenate(ks), np.concatenate(ws)

    def value(dd: dict[str, pd.DataFrame]) -> float:
        conf, corr, w = pairs(dd)
        # weighted resample to the test mix, then equal-mass ECE
        rng = np.random.default_rng(SEED)
        idx = rng.choice(len(conf), size=len(conf), p=w / w.sum())
        return ece_equal_mass(conf[idx], corr[idx])[0]

    est = value(d)
    se = stratified_boot(d, value, n_boot=N_BOOT // 4)
    pooled = pd.concat(d.values(), ignore_index=True)
    r3 = [json.loads(x) for x in pooled["ranked3"]]
    extra = {"brier": brier_shown(r3, list(pooled["truth_group"])),
             "log_loss": log_loss(pooled["p_truth"].to_numpy()),
             "step_ece_equal_width": step_ece(d)[0]}
    return est, se, extra


def cap_weights(bundle_cid: str, df: pd.DataFrame, share: float) -> np.ndarray:
    """Per-unit weights that turn a circuit's units into a mix with ``share`` capacitor faults."""
    is_cap = df["truth_kind"].isin(["film_cap", "electrolytic"]).to_numpy()
    n_cap, n_oth = int(is_cap.sum()), int((~is_cap).sum())
    if n_cap == 0 or n_oth == 0:
        return np.full(len(df), 1.0 / len(df))
    return np.where(is_cap, share / n_cap, (1 - share) / n_oth)


def wrong_prior_changes(eng: dict[str, pd.DataFrame], recap: dict[str, pd.DataFrame]) -> dict[str, float]:
    """T14: accuracy change from a wrong prior, both directions, weighted like the test mix."""
    def stat(dd: dict[str, pd.DataFrame]) -> tuple[float, float]:
        a = b = 0.0
        for c in CIRCUITS:
            m = dd[c]
            uni = np.full(len(m), 1.0 / len(m))
            capw = cap_weights(c, m, CAP_SHARE)
            ce, cr = m["correct_e"].astype(float).to_numpy(), m["correct_r"].astype(float).to_numpy()
            a += WEIGHTS[c] * float(np.sum(uni * (cr - ce)))    # capacitor-heavy prior, catalog mix
            b += WEIGHTS[c] * float(np.sum(capw * (ce - cr)))   # uniform prior, capacitor-heavy mix
        return a, b

    both = {c: eng[c][["case_id", "correct", "truth_kind"]].merge(
        recap[c][["case_id", "correct"]], on="case_id", suffixes=("_e", "_r")) for c in CIRCUITS}
    a, b = stat(both)
    se_a = stratified_boot(both, lambda dd: stat(dd)[0])
    se_b = stratified_boot(both, lambda dd: stat(dd)[1])
    return {"wrong_prior_catalog_mix": a, "wrong_prior_catalog_mix_se": se_a,
            "uniform_prior_capacitor_mix": b, "uniform_prior_capacitor_mix_se": se_b}


def selective(d: dict[str, pd.DataFrame]) -> dict[str, float]:
    """T23: share of single-fault units named (not flagged) and accuracy on those."""
    def named(dd: dict[str, pd.DataFrame]) -> float:
        return sum(WEIGHTS[c] * float((dd[c]["top_group"] != -1).mean()) for c in CIRCUITS)

    def acc(dd: dict[str, pd.DataFrame]) -> float:
        return sum(WEIGHTS[c] * float(dd[c].loc[dd[c]["top_group"] != -1, "correct"].mean())
                   for c in CIRCUITS)

    return {"named": named(d), "named_se": stratified_boot(d, named),
            "accuracy_named": acc(d), "accuracy_named_se": stratified_boot(d, acc)}


def main() -> None:
    hyb, eng = with_effort(runs("hybrid")), with_effort(runs("engine_gen"))
    fixed, half, rnd = (with_effort(runs(s)) for s in ("fixed_order", "half_split", "random"))
    recap = runs("recap_prior")
    disc = runs("engine_disc")
    aged = runs("hybrid", "pilot_aged")
    cs = COMPOSITE_ID
    n_pilot = {c: len(hyb[c]) for c in CIRCUITS}
    n_single_pilot, n_cs_pilot = sum(n_pilot.values()), n_pilot[cs]
    tj = json.loads(TARGETS.read_text())
    if tj.get("locked_on"):
        raise SystemExit("targets are locked; bars cannot change")
    ev = tj["evaluation_sets"]
    n_single, n_cs = ev["single_fault_cases"], ev["channel_strip_cases"]
    d: dict[str, dict[str, Any]] = {}

    def put(tid: str, est: float, se: float, hib: bool, step: float, n_p: float, n_t: float,
            **extra: Any) -> float:
        b = bar(est, se, hib, step)
        d[tid] = {"estimate": est, "se": se, "k": K, "direction": ">=" if hib else "<=",
                  "step": step, "bar": b, "n_pilot": n_p, "n_test": n_t,
                  "chance_met": chance_met(est, se, b, hib, n_p, n_t), **extra}
        return b

    put("T1", *weighted_prop(hyb, "correct"), True, 0.01, n_single_pilot, n_single)
    put("T2", float(hyb[cs]["correct"].mean()), ac_se(hyb[cs]["correct"].to_numpy()), True, 0.01,
        n_cs_pilot, n_cs)
    put("T3", *weighted_prop(hyb, "top3"), True, 0.01, n_single_pilot, n_single)
    margins = {name: paired(eng[cs], base[cs], "correct")
               for name, base in (("fixed_order", fixed), ("random", rnd), ("half_split", half))}
    t4: dict[str, Any] = {}
    for name, m in margins.items():
        est, se = float(m.mean()), float(m.std(ddof=1)) / math.sqrt(len(m))
        t4[f"estimate_vs_{name}"], t4[f"se_vs_{name}"] = est, se
        t4[f"bar_vs_{name}"] = bar(est, se, True, 0.01)
    b4 = min(t4[f"bar_vs_{n}"] for n in margins)
    t4["chance_met"] = float(np.prod([chance_met(t4[f"estimate_vs_{n}"], t4[f"se_vs_{n}"], b4, True,
                                                 n_cs_pilot, n_cs) for n in margins]))
    d["T4"] = {**t4, "k": K, "direction": ">=", "step": 0.01, "bar": b4, "n_pilot": n_cs_pilot,
               "n_test": n_cs, "rule": "the smallest of the three margin bars, met when every margin's "
                                        "lower bound clears it"}
    # T6: the same count as T1 on aged units (ADR-039); the drop from as-new units and the
    # split of the misses into "no single fault fits" calls and wrong names are context.
    n_aged_pilot = sum(len(f) for f in aged.values())
    flag = {c: f.assign(flag=(f["top_group"] == -1).astype(float)) for c, f in aged.items()}
    wrong = {c: f.assign(wrong=((f["top_group"] != -1) & ~f["correct"].astype(bool)).astype(float))
             for c, f in aged.items()}
    t1_new = weighted_prop(hyb, "correct")[0]
    t6_est, t6_se = weighted_prop(aged, "correct")
    put("T6", t6_est, t6_se, True, 0.01, n_aged_pilot, ev["aged_cases"],
        drop_from_new=t1_new - t6_est, aged_flag_rate=weighted_prop(flag, "flag")[0],
        aged_wrong_name_rate=weighted_prop(wrong, "wrong")[0],
        aged_cs_top1=float(aged[cs]["correct"].mean()), n_aged=n_aged_pilot)
    acc = {name: sum(WEIGHTS[c] * float(r[c]["correct"].mean()) for c in CIRCUITS)
           for name, r in (("engine", eng), ("fixed_order", fixed), ("half_split", half),
                           ("random", rnd), ("hybrid", hyb))}
    for tid, num, den, dname in (("T8", eng, fixed, "fixed_order"), ("T9", eng, half, "half_split"),
                                 ("T10", eng, rnd, "random"), ("T11", hyb, eng, "engine")):
        put(tid, *effort_ratio(num, den), False, 0.05, n_single_pilot, n_single,
            accuracy_gap=(acc["hybrid" if tid == "T11" else "engine"] - acc[dname]))
    e12, se12, extra12 = shown_ece(hyb)
    put("T12", e12, se12, False, 0.01, n_single_pilot, n_single, **extra12)
    us = unmodeled_stats("hybrid", hyb)
    n_u_pilot, n_u = us["n_unmodeled"], ev["unmodeled_cases"]
    put("T13", us["misleading"], us["misleading_se"], False, 0.01, n_u_pilot, n_u)
    b22f = bar(us["flagged"], us["flagged_se"], True, 0.01)
    b22a = bar(us["auroc"], us["auroc_se"], True, 0.01)
    d["T22"] = {"flagged_estimate": us["flagged"], "flagged_se": us["flagged_se"], "flagged_bar": b22f,
                "estimate": us["auroc"], "se": us["auroc_se"], "bar": b22a, "k": K, "direction": ">=",
                "step": 0.01, "n_pilot": n_u_pilot, "n_test": n_u,
                "chance_met": chance_met(us["flagged"], us["flagged_se"], b22f, True, n_u_pilot, n_u)
                * chance_met(us["auroc"], us["auroc_se"], b22a, True, n_u_pilot, n_u)}
    sel = selective(hyb)
    b23n = bar(sel["named"], sel["named_se"], True, 0.01)
    b23a = bar(sel["accuracy_named"], sel["accuracy_named_se"], True, 0.01)
    d["T23"] = {"estimate": sel["named"], "se": sel["named_se"], "bar": b23n,
                "accuracy_estimate": sel["accuracy_named"], "accuracy_se": sel["accuracy_named_se"],
                "accuracy_bar": b23a, "k": K, "direction": ">=", "step": 0.01,
                "n_pilot": n_single_pilot, "n_test": n_single,
                "chance_met": chance_met(sel["named"], sel["named_se"], b23n, True, n_single_pilot,
                                         n_single)
                * chance_met(sel["accuracy_named"], sel["accuracy_named_se"], b23a, True,
                             n_single_pilot, n_single)}
    wp = wrong_prior_changes(eng, recap)
    b14a = bar(wp["wrong_prior_catalog_mix"], wp["wrong_prior_catalog_mix_se"], True, 0.01)
    b14b = bar(wp["uniform_prior_capacitor_mix"], wp["uniform_prior_capacitor_mix_se"], True, 0.01)
    d["T14"] = {**wp, "bar": min(b14a, b14b), "bar_catalog_mix": b14a, "bar_capacitor_mix": b14b,
                "k": K, "direction": ">=", "step": 0.01, "n_pilot": n_single_pilot, "n_test": n_single}
    d["T14"]["chance_met"] = (
        chance_met(wp["wrong_prior_catalog_mix"], wp["wrong_prior_catalog_mix_se"], d["T14"]["bar"],
                   True, n_single_pilot, n_single)
        * chance_met(wp["uniform_prior_capacitor_mix"], wp["uniform_prior_capacitor_mix_se"],
                     d["T14"]["bar"], True, n_single_pilot, n_single))
    # context reported with the bars (no targets): the other likelihood model, the effort
    # of each method on the channel strip, accuracy per method (test-mix weights)
    context = {
        "accuracy_weighted": acc,
        "engine_disc_top1_weighted": sum(WEIGHTS[c] * float(disc[c]["correct"].mean()) for c in CIRCUITS),
        "engine_disc_top1_cs": float(disc[cs]["correct"].mean()),
        "cs_top1": {n: float(r[cs]["correct"].mean()) for n, r in
                    (("hybrid", hyb), ("engine", eng), ("engine_disc", disc), ("fixed_order", fixed),
                     ("half_split", half), ("random", rnd))},
        "cs_mean_effort": {n: float(r[cs]["cost"].mean()) for n, r in
                           (("hybrid", hyb), ("engine", eng), ("fixed_order", fixed),
                            ("half_split", half), ("random", rnd))},
        # effort parts and effort to a confirmed answer, test-mix weights (ADR-041)
        "effort": {n: effort_summary(r, WEIGHTS) for n, r in
                   (("hybrid", hyb), ("engine", eng), ("fixed_order", fixed),
                    ("half_split", half), ("random", rnd))},
        "raw_effort_ratio": {n: effort_ratio(eng, r, "cost")[0] for n, r in
                             (("fixed_order", fixed), ("half_split", half), ("random", rnd))},
        "n_pilot": n_pilot,
        # What reading the complaint did in the pilot (full system vs engine alone):
        "complaint_accuracy_change_pts": 100 * (acc["hybrid"] - acc["engine"]),
        "complaint_effort_saving_pct": 100 * (1 - d["T11"]["estimate"]),
    }

    text = {
        "T1": f"≥ {round(100 * d['T1']['bar'])}%", "T2": f"≥ {round(100 * d['T2']['bar'])}%",
        "T3": f"≥ {round(100 * d['T3']['bar'])}%", "T4": f"≥ {pts(d['T4']['bar'])} each",
        "T6": f"≥ {round(100 * d['T6']['bar'])}%",
        "T8": f"≤ {d['T8']['bar']:.2f}×", "T9": f"≤ {d['T9']['bar']:.2f}×",
        "T10": f"≤ {d['T10']['bar']:.2f}×", "T11": f"≤ {d['T11']['bar']:.2f}×",
        "T12": f"≤ {d['T12']['bar']:.2f}", "T13": f"≤ {round(100 * d['T13']['bar'])}%",
        "T22": f"≥ {round(100 * b22f)}% flagged; AUROC ≥ {b22a:.2f}",
        "T23": f"≥ {round(100 * b23n)}% named; ≥ {round(100 * b23a)}% right when naming",
        "T14": f"≥ {pts(d['T14']['bar'])} each",
    }
    for t in tj["targets"]:
        if t["id"] in d:
            v = d[t["id"]]
            t["value"] = v["bar"]
            t["text"] = text[t["id"]]
            t["pilot_dependent"] = True
            t["derivation"] = derivation(t["id"], v)
            t["pilot_text"] = pilot_text(t["id"], v)
            t["chance_met"] = round(float(v["chance_met"]), 3)
            if t["id"] == "T22":
                t["value_flag_rate"] = b22f
            if t["id"] == "T23":
                t["value_accuracy"] = b23a
    # How the primaries combine: each is reported on its own; if they were independent, the
    # chance that every pilot-estimable primary is met is the product of their chances.
    prim = [t for t in tj["targets"] if t.get("role") == "primary" and t["id"] in d]
    context["joint_chance_primaries"] = float(np.prod([d[t["id"]]["chance_met"] for t in prim]))
    tj["joint_chance_primaries"] = {
        "targets": [t["id"] for t in prim], "chance": round(context["joint_chance_primaries"], 3),
        "note": "product of the per-target chances of meeting the bar, as if the targets were "
                "independent; T5 and T7 have no pilot and are left out"}
    # T7 (hardware): the bar is fixed from what a pass must show; record the smallest pass count
    from eval.stats import exact_binomial

    for t in tj["targets"]:
        if t["id"] == "T7":
            n7 = int(ev["fault_board_min"])
            t["pass_count"] = next(k for k in range(n7 + 1) if exact_binomial(k, n7).lo1 >= float(t["value"]))
            t["pass_rule_note"] = (f"{t['pass_count']} of {n7} is the smallest count whose exact one-sided "
                                   f"95% lower bound clears {100 * float(t['value']):.0f}%")
    tj["bar_rule"] = ("Each pilot-estimable bar is the protocol-matched pilot's estimate moved against "
                      f"the system by {K} standard errors and rounded to the reporting step "
                      "(eval/set_bars.py, ADR-029); a bar is met only when the one-sided 95% bound "
                      "clears it (ADR-033).")
    TARGETS.write_text(json.dumps(tj, indent=2, ensure_ascii=False) + "\n")
    metrics_io.update("bars", {"k": K, "weights": WEIGHTS, "targets": d, "context": context})
    for tid, v in d.items():
        print(tid, text[tid], {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
    print(json.dumps(context, indent=1, default=float))


def derivation(tid: str, v: dict[str, Any]) -> str:
    """One sentence stating the pilot estimate and how the bar follows from it."""
    rule = (f"bar = estimate moved {K} standard errors against the system, rounded (ADR-029); "
            f"chance of meeting it if the test behaves like the pilot about {100 * v['chance_met']:.0f}%")
    pct = {"T1", "T2", "T3", "T6", "T13"}
    if tid == "T4":
        return ("Pilot margins of the engine alone: "
                f"{100 * v['estimate_vs_fixed_order']:+.1f} points over the fixed-order chart, "
                f"{100 * v['estimate_vs_random']:+.1f} over random probing and "
                f"{100 * v['estimate_vs_half_split']:+.1f} over half-split tracing; {rule}, taking the "
                "smallest of the three.")
    if tid == "T14":
        return (f"Pilot changes {100 * v['wrong_prior_catalog_mix']:+.1f} points (capacitor-heavy prior, "
                f"catalog mix) and {100 * v['uniform_prior_capacitor_mix']:+.1f} points (uniform prior, "
                f"capacitor-heavy mix); {rule}, taking the smaller.")
    if tid == "T22":
        return (f"Pilot flagged {100 * v['flagged_estimate']:.1f}% (SE {100 * v['flagged_se']:.1f}) and "
                f"AUROC {v['estimate']:.3f} (SE {v['se']:.3f}) on {int(v['n_pilot'])} units; {rule}.")
    if tid == "T23":
        return (f"Pilot named {100 * v['estimate']:.1f}% of single faults (SE {100 * v['se']:.1f}) and was "
                f"right on {100 * v['accuracy_estimate']:.1f}% of those (SE "
                f"{100 * v['accuracy_se']:.1f}); {rule}.")
    if tid in pct:
        est, se = f"{100 * v['estimate']:.1f}%", f"{100 * v['se']:.1f} points"
    else:
        est, se = f"{v['estimate']:.3f}", f"{v['se']:.3f}"
    return f"Pilot estimate {est} (standard error {se}, {int(v['n_pilot'])} units); {rule}."


def pilot_text(tid: str, v: dict[str, Any]) -> str:
    """The pilot estimate as printed next to its bar in the M1 targets table."""
    if tid in ("T1", "T2", "T3", "T6", "T13"):
        return f"{100 * v['estimate']:.1f}%"
    if tid == "T4":
        return (f"{100 * v['estimate_vs_fixed_order']:+.0f} / {100 * v['estimate_vs_random']:+.0f} / "
                f"{100 * v['estimate_vs_half_split']:+.0f} pts").replace("-", "−")
    if tid == "T14":
        return (f"{100 * v['wrong_prior_catalog_mix']:+.1f} / "
                f"{100 * v['uniform_prior_capacitor_mix']:+.1f} pts").replace("-", "−")
    if tid in ("T8", "T9", "T10", "T11"):
        return f"{v['estimate']:.2f}×"
    if tid == "T12":
        return f"{v['estimate']:.3f}"
    if tid == "T22":
        return f"{100 * v['flagged_estimate']:.0f}%; {v['estimate']:.2f}"
    if tid == "T23":
        return f"{100 * v['estimate']:.0f}%; {100 * v['accuracy_estimate']:.0f}%"
    raise KeyError(tid)


if __name__ == "__main__":
    main()
