"""Set every pilot-estimable target bar by one rule, before the targets are locked.

Rule (ADR-029), fixed before the protocol-matched pilot was run:

    bar = pilot estimate moved against the system by K = 1.5 standard errors,
          rounded to the nearest reporting step

Rounding never carries a bar past the pilot estimate (ADR-043): when the nearest step
lies beyond the estimate, the bar rounds the other way, so no bar is stricter than the
pilot's own result and none becomes unmeetable (a 100% bar can never be cleared by a
one-sided bound).

Decision rule (ADR-033): a target is met only when its one-sided 95% confidence bound
clears the bar. For every pilot-based target this script also reports the chance of
meeting the bar if the test units behave like the pilot units:
Phi(|estimate - bar| / SE_test - 1.645), with SE_test the pilot standard error scaled
by sqrt(n_pilot / n_test).

Steps: 1 point for accuracies, margins and rates; 0.01 for effort ratios, calibration
error and AUROC (ratios used 0.05 until ADR-043: a step wider than the 1.5-SE margin let
rounding, not the rule, decide the bar). Pooled quantities are weighted like the test set
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
from scipy.stats import beta as beta_dist
from scipy.stats import binom as binom_dist

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from differential.config import RESULTS_DIR
from eval import metrics_io
from eval.effort import summary as effort_summary
from eval.effort import with_effort
from eval.harness import bundle_for, results_path, unmodeled_outcome
from eval.stats import auroc, brier_shown, ece, ece_equal_mass, log_loss, shown_calibration

K = 1.5
Z_ONE_SIDED = 1.6449
ONE_SIDED_ALPHA = 0.05
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
    b = round(raw / step) * step
    if (b > est) if higher_is_better else (b < est):  # rounding crossed the estimate (ADR-043)
        b = (math.floor(raw / step) if higher_is_better else math.ceil(raw / step)) * step
    return round(b, 10)


def chance_met(est: float, se_pilot: float, b: float, higher_is_better: bool,
               n_pilot: float, n_test: float) -> float:
    """Predictive probability that the test's one-sided 95% bound clears the bar.

    The test estimate is taken as normal around the pilot estimate with variance
    SE_pilot^2 + SE_test^2: the pilot's own error is counted, not only the test's
    (round-4 review), with SE_test the pilot standard error scaled by sqrt(n_pilot / n_test).
    The target is met when the test estimate exceeds the bar by 1.645 SE_test."""
    se_t = se_pilot * math.sqrt(n_pilot / n_test)
    gap = (est - b) if higher_is_better else (b - est)
    spread = math.hypot(se_pilot, se_t)
    if spread <= 0:
        return 1.0 if gap > 0 else 0.0
    return float(0.5 * (1 + math.erf(((gap - Z_ONE_SIDED * se_t) / spread) / math.sqrt(2))))


def exact_lower(k: int, n: int) -> float:
    """Clopper-Pearson one-sided 95% lower bound for k successes in n (eval.stats.exact_binomial)."""
    return 0.0 if k <= 0 else float(beta_dist.ppf(ONE_SIDED_ALPHA, k, n - k + 1))


def exact_upper(k: int, n: int) -> float:
    return 1.0 if k >= n else float(beta_dist.ppf(1 - ONE_SIDED_ALPHA, k + 1, n - k))


def pass_count(bar_value: float, n: int, higher_is_better: bool = True) -> int:
    """Smallest (or, for an 'at most' target, largest) count of n units whose exact
    (Clopper-Pearson) one-sided 95% bound clears the bar: what a pass needs, in units.
    Counts of units are judged with the exact bound (ADR-044); every unit of a pooled
    test set carries the same weight, so the pooled rate is a plain proportion."""
    if higher_is_better:
        lo, hi = 0, n  # smallest k with exact_lower(k) >= bar (monotone in k)
        while lo < hi:
            mid = (lo + hi) // 2
            if exact_lower(mid, n) >= bar_value:
                hi = mid
            else:
                lo = mid + 1
        return lo
    lo, hi = 0, n  # largest k with exact_upper(k) <= bar
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if exact_upper(mid, n) <= bar_value:
            lo = mid
        else:
            hi = mid - 1
    return lo


def chance_count(est: float, se_pilot: float, k: int, n: int, higher_is_better: bool) -> float:
    """Predictive chance that a count target passes under the exact rule: the true rate is
    normal around the pilot estimate with the pilot's standard error, and the test count is
    binomial at that rate (ADR-044)."""
    nodes, weights = np.polynomial.hermite_e.hermegauss(80)
    p = np.clip(est + se_pilot * nodes, 1e-9, 1 - 1e-9)
    tail = binom_dist.sf(k - 1, n, p) if higher_is_better else binom_dist.cdf(k, n, p)
    return float(np.sum(weights * tail) / np.sum(weights))


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


def ece_floor(d: dict[str, pd.DataFrame], n_units: int, n_sim: int = 300) -> dict[str, float]:
    """T12 for a perfectly calibrated system at the test size: the shown probabilities are
    resampled from the pilot (test-mix weights) and each outcome is drawn from its own
    probability, so any calibration error left is sampling noise."""
    conf, w = [], []
    for c in CIRCUITS:
        r3 = [json.loads(x) for x in d[c]["ranked3"]]
        cf, _ = shown_calibration(r3, list(d[c]["truth_group"]))
        conf.append(cf)
        w.append(np.full(len(cf), WEIGHTS[c] / max(len(cf), 1)))
    cf_all, w_all = np.concatenate(conf), np.concatenate(w)
    per_unit = len(cf_all) / sum(len(d[c]) for c in CIRCUITS)
    n = round(per_unit * n_units)
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(n_sim):
        c = cf_all[rng.choice(len(cf_all), size=n, p=w_all / w_all.sum())]
        vals.append(ece_equal_mass(c, (rng.random(n) < c).astype(float))[0])
    return {"n_units": n_units, "mean": float(np.mean(vals)), "p95": float(np.quantile(vals, 0.95))}


def hv_count(cid: str, keys: str) -> int:
    """Powered readings in one diagnosis at points that can exceed 50 V."""
    from differential.safety.hazards import hazard

    n = 0
    for k in json.loads(keys):
        kind, target = k.split(":", 1)
        if kind != "lift" and target.upper().startswith("TP") and hazard(cid, target).high_voltage:
            n += 1
    return n


def with_hv(d: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {c: df.assign(hv_reads=[hv_count(c, k) for k in df["keys"]]) for c, df in d.items()}


def hv_steps(d: dict[str, pd.DataFrame]) -> float:
    """Mean number of powered readings per diagnosis at points that can exceed 50 V."""
    return float(sum(WEIGHTS[c] * np.mean([hv_count(c, k) for k in d[c]["keys"]]) for c in CIRCUITS))


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
    from eval.cases import N_CASES

    ev.update({"single_fault_cases": sum(N_CASES["test"].values()),
               "channel_strip_cases": N_CASES["test"][COMPOSITE_ID],
               "cases_per_block": N_CASES["test"][BLOCK_IDS[0]],
               "aged_cases": sum(N_CASES["test_aged"].values()),
               "unmodeled_cases": sum(N_CASES["unmodeled_test"].values())})
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
               for name, base in (("fixed_order", fixed), ("half_split", half), ("random", rnd))}
    t4: dict[str, Any] = {}
    for name, m in margins.items():
        est, se = float(m.mean()), float(m.std(ddof=1)) / math.sqrt(len(m))
        t4[f"estimate_vs_{name}"], t4[f"se_vs_{name}"] = est, se
        t4[f"bar_vs_{name}"] = bar(est, se, True, 0.01)
    # each margin has its own bar by the rule (round 6: one bar, the smallest, was lenient)
    t4["chance_met"] = float(np.prod([chance_met(t4[f"estimate_vs_{n}"], t4[f"se_vs_{n}"],
                                                 t4[f"bar_vs_{n}"], True, n_cs_pilot, n_cs)
                                      for n in margins]))
    d["T4"] = {**t4, "k": K, "direction": ">=", "step": 0.01,
               "bar": min(t4[f"bar_vs_{n}"] for n in margins),
               "bar_by": {n: t4[f"bar_vs_{n}"] for n in margins}, "n_pilot": n_cs_pilot,
               "n_test": n_cs, "rule": "each margin's lower bound must clear its own bar (ADR-046)"}
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
        put(tid, *effort_ratio(num, den), False, 0.01, n_single_pilot, n_single,
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
                "bar_by": {"catalog_mix": b14a, "capacitor_mix": b14b},
                "k": K, "direction": ">=", "step": 0.01, "n_pilot": n_single_pilot, "n_test": n_single}
    d["T14"]["chance_met"] = (
        chance_met(wp["wrong_prior_catalog_mix"], wp["wrong_prior_catalog_mix_se"], b14a,
                   True, n_single_pilot, n_single)
        * chance_met(wp["uniform_prior_capacitor_mix"], wp["uniform_prior_capacitor_mix_se"],
                     b14b, True, n_single_pilot, n_single))
    # T24 (ADR-046): powered readings at points that can exceed 50 V, engine / half-split
    put("T24", *effort_ratio(with_hv(eng), with_hv(half), "hv_reads"), False, 0.01, n_single_pilot,
        n_single, engine_per_diagnosis=hv_steps(eng), half_split_per_diagnosis=hv_steps(half))
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
        # What a perfectly calibrated system would score on T12 at the test size (ADR-044).
        "ece_floor": ece_floor(hyb, n_single),
        # Powered readings at points that can exceed 50 V, per diagnosis (test-mix weights).
        "hv_steps": {n: hv_steps(r) for n, r in (("hybrid", hyb), ("engine", eng),
                                                 ("fixed_order", fixed), ("half_split", half),
                                                 ("random", rnd))},
    }

    text = {
        "T1": f"≥ {round(100 * d['T1']['bar'])}%", "T2": f"≥ {round(100 * d['T2']['bar'])}%",
        "T3": f"≥ {round(100 * d['T3']['bar'])}%",
        "T4": "≥ " + "/".join(pts(d["T4"]["bar_by"][n]).split()[0] for n in margins) + " pts",
        "T6": f"≥ {round(100 * d['T6']['bar'])}%",
        "T8": f"≤ {d['T8']['bar']:.2f}×", "T9": f"≤ {d['T9']['bar']:.2f}×",
        "T10": f"≤ {d['T10']['bar']:.2f}×", "T11": f"≤ {d['T11']['bar']:.2f}×",
        "T12": f"≤ {d['T12']['bar']:.2f}", "T13": f"≤ {round(100 * d['T13']['bar'])}%",
        "T22": f"≥ {round(100 * b22f)}% flagged; AUROC ≥ {b22a:.2f}",
        "T23": f"≥ {round(100 * b23n)}% named; ≥ {round(100 * b23a)}% right when naming",
        "T14": f"≥ {pts(b14a).split()[0]}/{pts(b14b).split()[0]} points",
        "T24": f"≤ {d['T24']['bar']:.2f}×",
    }
    # What a pass needs, in units, for the count targets (the bound must clear the bar).
    counts = {"T1": (n_single, True), "T2": (n_cs, True), "T3": (n_single, True),
              "T6": (ev["aged_cases"], True), "T13": (ev["unmodeled_cases"], False)}
    for tid, (n_units, hib) in counts.items():
        d[tid]["pass_count"] = pass_count(d[tid]["bar"], int(n_units), hib)
        d[tid]["n_units"] = int(n_units)
        d[tid]["bound"] = "exact"
        d[tid]["chance_met"] = chance_count(d[tid]["estimate"], d[tid]["se"], d[tid]["pass_count"],
                                            int(n_units), hib)
    for tid, v in d.items():
        if "estimate" in v and "se" in v and tid not in ("T4", "T14", "T22", "T23"):
            v["raw_bar"] = (v["estimate"] - K * v["se"] if v.get("direction") == ">="
                            else v["estimate"] + K * v["se"])
    for t in tj["targets"]:
        if t["id"] in d:
            v = d[t["id"]]
            t["value"] = v["bar"]
            if "pass_count" in v:
                t["pass_count"], t["n_units"] = v["pass_count"], v["n_units"]
            if "raw_bar" in v:
                t["raw_bar"] = round(float(v["raw_bar"]), 4)
            t["text"] = text[t["id"]]
            t["pilot_dependent"] = True
            t["derivation"] = derivation(t["id"], v)
            t["pilot_text"] = pilot_text(t["id"], v)
            t["chance_met"] = round(float(v["chance_met"]), 3)
            if "bound" in v:
                t["bound"] = v["bound"]
            if "bar_by" in v:
                t["value_by"] = v["bar_by"]
            if t["id"] == "T22":
                t["value_flag_rate"] = b22f
            if t["id"] == "T23":
                t["value_accuracy"] = b23a
    # How the primaries combine: each is reported on its own; if they were independent, the
    # chance that every pilot-estimable primary is met is the product of their chances.
    prim = [t for t in tj["targets"] if t.get("role") == "primary" and t["id"] in d]
    context["joint_chance_primaries"] = float(np.prod([d[t["id"]]["chance_met"] for t in prim]))
    context["expected_primary_misses"] = float(sum(1 - d[t["id"]]["chance_met"] for t in prim))
    tj["joint_chance_primaries"] = {
        "targets": [t["id"] for t in prim], "chance": round(context["joint_chance_primaries"], 3),
        "expected_misses": round(context["expected_primary_misses"], 2),
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
            # Why 70%: with 60 faults a pass needs about 82% observed, which a system truly
            # 85-90% accurate on the boards reaches most of the time and one at 70% almost never.
            t["pass_probability"] = {f"{q:.2f}": round(float(binom_dist.sf(t["pass_count"] - 1, n7, q)), 3)
                                     for q in (0.90, 0.85, 0.80, 0.70)}
    # What a zero-failure gate shows: none of n bounds the rate below the exact upper bound.
    tj["gate_bounds"] = {"T16": exact_upper(0, int(ev["red_team_min"]))}
    tj["bar_rule"] = ("Each pilot-estimable bar is the protocol-matched pilot's estimate moved against "
                      f"the system by {K} standard errors and rounded to the reporting step, never "
                      "past the estimate (eval/set_bars.py, ADR-029, ADR-043); a target with several "
                      "parts has a bar per part (ADR-046); a bar is met only when the one-sided 95% "
                      "bound clears it (ADR-033).")
    tj["pass_rule"] = ("A target is met when its one-sided 95% confidence bound clears the bar: the lower "
                       "bound for an 'at least' target, the upper bound for an 'at most' target (exact "
                       "Clopper-Pearson for counts of units or prompts, ADR-044; a stratified bootstrap "
                       "over units, 2,000 resamples, for paired margins, ratios and calibration error). "
                       "A census (T15, T17) is met only with no exception; a release gate (T15-T17, "
                       "T25, T26) must hold before any release. Every result is reported with its "
                       "two-sided 95% interval.")
    TARGETS.write_text(json.dumps(tj, indent=2, ensure_ascii=False) + "\n")
    metrics_io.update("bars", {"k": K, "weights": WEIGHTS, "targets": d, "context": context})
    for tid, v in d.items():
        print(tid, text[tid], {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
    print(json.dumps(context, indent=1, default=float))


def derivation(tid: str, v: dict[str, Any]) -> str:
    """One sentence stating the pilot estimate and how the bar follows from it."""
    rule = (f"bar = estimate moved {K} standard errors against the system, rounded (ADR-029, ADR-043); "
            f"chance of meeting it (counting the pilot's own error) about {100 * v['chance_met']:.0f}%")
    pct = {"T1", "T2", "T3", "T6", "T13"}
    if tid == "T4":
        return ("Pilot margins of the engine alone: "
                f"{100 * v['estimate_vs_fixed_order']:+.1f} points over the fixed-order chart, "
                f"{100 * v['estimate_vs_half_split']:+.1f} over half-split tracing and "
                f"{100 * v['estimate_vs_random']:+.1f} over random probing; {rule}, one bar per "
                "margin (ADR-046).")
    if tid == "T14":
        return (f"Pilot changes {100 * v['wrong_prior_catalog_mix']:+.1f} points (capacitor-heavy prior, "
                f"catalog mix) and {100 * v['uniform_prior_capacitor_mix']:+.1f} points (uniform prior, "
                f"capacitor-heavy mix); {rule}, one bar per part (ADR-046).")
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
        return (f"{100 * v['estimate_vs_fixed_order']:+.1f}/{100 * v['estimate_vs_half_split']:+.1f}/"
                f"{100 * v['estimate_vs_random']:+.1f}").replace("-", "−")
    if tid == "T14":
        return (f"{100 * v['wrong_prior_catalog_mix']:+.1f} / "
                f"{100 * v['uniform_prior_capacitor_mix']:+.1f} pts").replace("-", "−")
    if tid in ("T8", "T9", "T10", "T11", "T24"):
        return f"{v['estimate']:.2f}×"
    if tid == "T12":
        return f"{v['estimate']:.3f}"
    if tid == "T22":
        return f"{100 * v['flagged_estimate']:.0f}%; {v['estimate']:.2f}"
    if tid == "T23":
        return f"{100 * v['estimate']:.1f}%; {100 * v['accuracy_estimate']:.1f}%"
    raise KeyError(tid)


if __name__ == "__main__":
    main()
