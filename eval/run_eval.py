"""Full evaluation: every system on the locked test sets -> targets, analyses, figures.

Run only after the git tag ``targets-locked`` exists (``make eval``); ``--smoke``
runs a small subset end to end in a few minutes and writes metrics.json section
"smoke" without touching the full results.

Outputs
  results/metrics.json  sections "evaluation", "targets_result", "analyses"
  results/figures/      fig_*.png/svg
  data/eval/runs/       one parquet per (system, circuit, split), reused on rerun
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from differential.circuits.library import BLOCK_IDS, COMPOSITE_ID
from differential.config import FIGURES_DIR, RESULTS_DIR
from differential.engine.bundle import load_bundle
from differential.sim.faults import MODE_TYPE, parse_fault_id
from eval import figstyle, metrics_io
from eval.effort import with_effort
from eval.harness import (
    EFFORT_WEIGHTS,
    SENSITIVITY_BASES,
    SYSTEMS,
    WEIGHT_FACTORS,
    run_system,
    sensitivity_name,
    unmodeled_outcome,
)
from eval.lock import require_lock
from eval.stats import (
    Estimate,
    auroc_ci,
    bootstrap_mean,
    bootstrap_ratio_of_means,
    brier_shown,
    ece,
    ece_equal_mass,
    exact_binomial,
    from_boots,
    log_loss,
    mcnemar,
    paired_diff,
    roc_curve,
    shown_calibration,
)

CIRCUITS = [COMPOSITE_ID, *BLOCK_IDS]
MAIN = ["random", "fixed_order", "half_split", "engine_gen", "engine_disc", "hybrid"]
SENSITIVITY = [sensitivity_name(b, w, f) for b in SENSITIVITY_BASES for w in EFFORT_WEIGHTS
               for f in WEIGHT_FACTORS]
ABLATIONS = ["hybrid_oracle", "hybrid_clean", "hybrid_devbank", "hybrid_bank_b", "recap_prior", "engine_eig_nocost",
             "engine_n50", "engine_n100", "engine_n200", *SENSITIVITY]
SMOKE_SYSTEMS = ["random", "fixed_order", "half_split", "engine_gen", "hybrid"]
SMOKE_LIMIT = 8
# The smoke test checks the pipeline, not the system: it runs on the pilot splits so
# that no check before the targets-locked tag ever touches a test unit.
SPLITS = {"test": "test", "unmodeled_test": "unmodeled_test", "test_aged": "test_aged",
          "test_wide": "test_wide", "test_wide2": "test_wide2", "test_wide3": "test_wide3"}
SMOKE_SPLITS = {"test": "pilot", "unmodeled_test": "unmodeled_pilot", "test_aged": "pilot_aged",
                "test_wide": "pilot_wide", "test_wide2": "pilot_wide", "test_wide3": "pilot_wide"}
CAP_SHARE = 0.6
CAP_KINDS = ("film_cap", "electrolytic")


# ----------------------------------------------------------------- running
def run_everything(smoke: bool) -> dict[str, dict[str, pd.DataFrame]]:
    limit = SMOKE_LIMIT if smoke else None
    systems = SMOKE_SYSTEMS if smoke else MAIN + ABLATIONS
    sp = SMOKE_SPLITS if smoke else SPLITS
    out: dict[str, dict[str, pd.DataFrame]] = {}
    t0 = time.time()
    for s in systems:
        out[s] = {}
        for cid in CIRCUITS:
            out[s][cid] = run_system(SYSTEMS[s], cid, sp["test"], limit=limit)
        print(f"{s:22s} done  {time.time() - t0:7.0f} s", flush=True)
    # T13 is measured on the full system (its operating point is the calibrated one);
    # the engine alone is kept for the analysis of what the complaint changes.
    out["unmodeled_hybrid"] = {cid: run_system(SYSTEMS["hybrid"], cid, sp["unmodeled_test"],
                                               limit=limit) for cid in CIRCUITS}
    out["unmodeled_engine"] = {cid: run_system(SYSTEMS["engine_gen"], cid, sp["unmodeled_test"],
                                               limit=limit) for cid in CIRCUITS}
    out["aged_hybrid"] = {cid: run_system(SYSTEMS["hybrid"], cid, sp["test_aged"], limit=limit)
                          for cid in CIRCUITS}
    for key in ("test_wide", "test_wide2", "test_wide3"):
        out[f"{key}_hybrid"] = {COMPOSITE_ID: run_system(SYSTEMS["hybrid"], COMPOSITE_ID,
                                                         sp[key], limit=limit)}
    return out


def pooled(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(frames.values(), ignore_index=True)


def aligned(a: pd.DataFrame, b: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = a.merge(b, on="case_id", suffixes=("_a", "_b"))
    return (m[[c for c in m.columns if c.endswith("_a")]].rename(columns=lambda c: c[:-2]),
            m[[c for c in m.columns if c.endswith("_b")]].rename(columns=lambda c: c[:-2]))


def est(e: Estimate, digits: int = 4) -> dict[str, float]:
    return {k: round(v, digits) for k, v in e.as_dict().items()}


def step_ece_ci(df: pd.DataFrame, n_boot: int = 500) -> tuple[Estimate, list[dict[str, float]]]:
    """Calibration over every step; bootstrap resamples whole diagnoses (steps are correlated)."""
    per_case = [(np.array(json.loads(m)), np.array(json.loads(c), dtype=float))
                for m, c in zip(df["trace_mass"], df["trace_correct"], strict=True)]
    per_case = [(m, c) for m, c in per_case if len(m)]
    conf = np.concatenate([m for m, _ in per_case])
    corr = np.concatenate([c for _, c in per_case])
    value, bins = ece(conf, corr)
    rng = np.random.default_rng(7)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(per_case), len(per_case))
        vals.append(ece(np.concatenate([per_case[i][0] for i in idx]),
                        np.concatenate([per_case[i][1] for i in idx]))[0])
    return from_boots(value, vals), bins


def boot_diff_indep(a: np.ndarray, b: np.ndarray, n_boot: int = 2000) -> Estimate:
    rng = np.random.default_rng(11)
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = [a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean()
         for _ in range(n_boot)]
    return from_boots(float(a.mean() - b.mean()), d)


def shown_ece_ci(df: pd.DataFrame, n_boot: int = 500) -> tuple[Estimate, list[dict[str, float]]]:
    """T12: equal-mass ECE of the probabilities shown for the first three groups at the stop;
    the bootstrap resamples whole diagnoses (their three probabilities are correlated)."""
    r3 = [json.loads(x) for x in df["ranked3"]]
    truth = list(df["truth_group"])
    conf, corr = shown_calibration(r3, truth)
    value, bins = ece_equal_mass(conf, corr)
    rng = np.random.default_rng(12)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(r3), len(r3))
        c, k = shown_calibration([r3[i] for i in idx], [truth[i] for i in idx])
        vals.append(ece_equal_mass(c, k)[0])
    return from_boots(value, vals), bins


def cap_mix_weights(df: pd.DataFrame, share: float = CAP_SHARE) -> np.ndarray:
    """Unit weights that turn each circuit's units into a mix with ``share`` capacitor
    faults, circuits keeping their test-set weight (T14, reweighted accuracy)."""
    w = np.zeros(len(df))
    for c in df["circuit"].unique():
        sel = (df["circuit"] == c).to_numpy()
        is_cap = df.loc[sel, "truth_kind"].isin(CAP_KINDS).to_numpy()
        n_cap, n_oth, total = int(is_cap.sum()), int((~is_cap).sum()), float(sel.sum())
        if n_cap == 0 or n_oth == 0:
            w[sel] = 1.0
            continue
        w[sel] = np.where(is_cap, share * total / n_cap, (1 - share) * total / n_oth)
    return w / w.sum()


def boot_weighted_diff(a: np.ndarray, b: np.ndarray, w: np.ndarray, n_boot: int = 2000) -> Estimate:
    """Weighted mean of paired differences a - b, bootstrap over units."""
    a, b, w = np.asarray(a, float), np.asarray(b, float), np.asarray(w, float)
    rng = np.random.default_rng(14)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(a), len(a))
        vals.append(float(np.sum(w[idx] * (a[idx] - b[idx])) / np.sum(w[idx])))
    return from_boots(float(np.sum(w * (a - b)) / np.sum(w)), vals)


# ----------------------------------------------------------------- targets
def judge(t: dict[str, Any], e: Estimate | float | None, bar: float | None = None) -> str:
    """Met when the one-sided 95% bound clears the bar (ADR-033): the lower bound for an
    'at least' target, the upper bound for an 'at most' one. A census or release gate
    ('==') must equal the bar exactly."""
    if e is None:
        return "pending"
    comp = t["comparator"]
    b = float(t["value"] if bar is None else bar)
    if comp == "==":
        v = e.value if isinstance(e, Estimate) else float(e)
        return "met" if np.isfinite(v) and abs(v - b) < 1e-12 else "missed"
    if not isinstance(e, Estimate) or not np.isfinite(e.value):
        return "pending"
    if comp in ("≥", ">=", "margin>="):
        return "met" if e.lo1 >= b else "missed"
    if comp == "<=":
        return "met" if e.hi1 <= b else "missed"
    raise ValueError(comp)


def both(*states: str) -> str:
    """A target with several parts is met only when every part is."""
    if "missed" in states:
        return "missed"
    return "met" if all(s == "met" for s in states) else "pending"


def two_part(t: dict[str, Any], offline: Estimate | None, claude: Estimate | None) -> str:
    """Targets with an offline bar and a Claude bar: met only when both parts are met,
    each judged on its one-sided bound."""
    s_off = judge(t, offline, float(t["value_offline"])) if offline is not None else "pending"
    s_cl = judge(t, claude, float(t["value"])) if claude is not None else "pending"
    if "missed" in (s_off, s_cl):
        return "missed"
    if s_off == "met" and s_cl == "met":
        return "met"
    return "pending" if s_off == "pending" else "offline part met; Claude part pending"


def effort_target(eng: pd.DataFrame, base: pd.DataFrame) -> dict[str, Any]:
    """Effort to a confirmed answer (ADR-041); the raw effort and its parts are reported."""
    a, b = aligned(eng, base)
    ratio = bootstrap_ratio_of_means(a["confirmed_cost"].to_numpy(), b["confirmed_cost"].to_numpy())
    raw = bootstrap_ratio_of_means(a["cost"].to_numpy(), b["cost"].to_numpy())
    acc_gap = float(a["correct"].mean() - b["correct"].mean())
    parts = {side: {"effort": float(f["cost"].mean()), "probing": float(f["probe_cost"].mean()),
                    "unsoldering": float(f["lift_cost"].mean()),
                    "confirming_charge": float(f["confirm_cost"].mean()),
                    "confirmed_effort": float(f["confirmed_cost"].mean())}
             for side, f in (("system", a), ("baseline", b))}
    return {"ratio": ratio, "raw_ratio": est(raw), "parts": parts,
            "top1_system": float(a["correct"].mean()),
            "top1_baseline": float(b["correct"].mean()), "top1_gap": acc_gap,
            "accuracy_condition": acc_gap >= -0.02, "n": len(a)}


def compute_targets(R: dict[str, dict[str, pd.DataFrame]], targets: dict[str, Any]) -> dict[str, Any]:
    """Every target on the locked sets. The test mix (2,500 channel strip, 500 per block) is
    the reporting weight, so pooling the units weights them as the targets define."""
    M = metrics_io.load()
    T = {t["id"]: t for t in targets["targets"]}
    out: dict[str, Any] = {}
    hyb = pooled(R["hybrid"])
    eng = pooled(R["engine_gen"])
    cs = R["hybrid"][COMPOSITE_ID]

    def put(tid: str, e: Estimate | None, detail: dict[str, Any], status: str | None = None) -> None:
        st = status or judge(T[tid], e)
        out[tid] = {"id": tid, "bar": T[tid]["text"], "role": T[tid].get("role"),
                    "value": None if e is None else e.value,
                    "ci": None if e is None else est(e), "status": st, **detail}

    # Counts of units are judged with the exact binomial bound (ADR-044): every test unit
    # carries the same weight, so a pooled rate is a plain proportion.
    put("T1", count_bound(hyb["correct"]), {"n": len(hyb)})
    put("T2", exact_binomial(int(cs["correct"].sum()), len(cs)), {"n": len(cs)})
    put("T3", count_bound(hyb["top3"]), {"n": len(hyb)})
    margins, states = {}, []
    eng_cs = R["engine_gen"][COMPOSITE_ID]
    for base in ("fixed_order", "random", "half_split"):
        a, b = aligned(eng_cs, R[base][COMPOSITE_ID])
        d = paired_diff(a["correct"].to_numpy(float), b["correct"].to_numpy(float))
        margins[base] = {"margin": est(d), "mcnemar": mcnemar(a["correct"].to_numpy(),
                                                               b["correct"].to_numpy())}
        states.append(judge(T["T4"], d, float(T["T4"]["value_by"][base])))  # a bar per margin
        full = paired_diff(*(x["correct"].to_numpy(float) for x in aligned(cs, R[base][COMPOSITE_ID])))
        margins[base]["full_system_margin"] = est(full)
    worst = min(margins, key=lambda k: margins[k]["margin"]["value"])
    put("T4", paired_diff(*(x["correct"].to_numpy(float)
                            for x in aligned(eng_cs, R[worst][COMPOSITE_ID]))),
        {"margins": margins, "smallest_vs": worst}, both(*states))
    llm = M.get("llm_only")
    if isinstance(llm, dict) and "margin" in llm:
        m5 = llm["margin"]
        put("T5", Estimate(m5["value"], m5["lo"], m5["hi"], m5.get("lo1", m5["lo"]),
                           m5.get("hi1", m5["hi"])), {"detail": llm})
    else:
        put("T5", None, {"note": "requires DIFFERENTIAL_API_KEY; protocol in eval/llm_baseline.py"})
    # T6 (ADR-039): T1's count on aged units; the aged set has the test set's mix, so
    # pooling weights it as T1 is weighted.
    aged = pooled(R["aged_hybrid"])
    drop = boot_diff_indep(hyb["correct"].to_numpy(float), aged["correct"].to_numpy(float))
    curve = {k: float(R[f"{k}_hybrid"][COMPOSITE_ID]["correct"].mean())
             for k in ("test_wide", "test_wide2", "test_wide3")}
    put("T6", count_bound(aged["correct"]),
        {"n": len(aged), "drop_from_new": est(drop),
         "by_circuit": {c: float(f["correct"].mean()) for c, f in R["aged_hybrid"].items()},
         "aged_flagged": float((aged["top_group"] == -1).mean()),
         "aged_wrong_name": float(((aged["top_group"] != -1) & ~aged["correct"].astype(bool)).mean()),
         "tolerance_curve_top1": {"1x": float(cs["correct"].mean()), "1.5x": curve["test_wide"],
                                  "2x": curve["test_wide2"], "3x": curve["test_wide3"]}})
    hw = M.get("fault_board", {})
    if hw.get("status") == "measured":
        k7, n7 = int(hw["engine_top1_correct"]), int(hw["n_faults"])
        put("T7", exact_binomial(k7, n7), {"detail": hw})
    else:
        put("T7", None, {"note": "requires the hardware fault boards (hardware/fault_board)"})
    eng = pooled(with_effort(R["engine_gen"]))
    hyb_e = pooled(with_effort(R["hybrid"]))
    for tid, base in (("T8", "fixed_order"), ("T9", "half_split"), ("T10", "random")):
        d = effort_target(eng, pooled(with_effort(R[base])))
        st = judge(T[tid], d["ratio"])
        if st == "met" and not d["accuracy_condition"]:
            st = "missed"
        put(tid, d["ratio"], {k: v for k, v in d.items() if k != "ratio"}, st)
    # T24 (ADR-046): powered readings at points that can exceed 50 V, engine / half-split
    from eval.set_bars import hv_count

    a24, b24 = aligned(eng, pooled(R["half_split"]))
    hv_a = np.array([hv_count(c, k) for c, k in zip(a24["circuit"], a24["keys"], strict=True)], float)
    hv_b = np.array([hv_count(c, k) for c, k in zip(b24["circuit"], b24["keys"], strict=True)], float)
    put("T24", bootstrap_ratio_of_means(hv_a, hv_b),
        {"engine_per_diagnosis": float(hv_a.mean()), "half_split_per_diagnosis": float(hv_b.mean()),
         "n": len(a24)})
    d = effort_target(hyb_e, eng)
    st = judge(T["T11"], d["ratio"])
    put("T11", d["ratio"], {k: v for k, v in d.items() if k != "ratio"},
        "missed" if st == "met" and not d["accuracy_condition"] else st)
    e12, bins = shown_ece_ci(hyb)
    step12, step_bins = step_ece_ci(hyb)
    r3 = [json.loads(x) for x in hyb["ranked3"]]
    put("T12", e12, {"bins": bins, "brier": brier_shown(r3, list(hyb["truth_group"])),
                     "log_loss": log_loss(hyb["p_truth"].to_numpy()),
                     "every_step_ece_equal_width": est(step12), "every_step_bins": step_bins,
                     "aged_shown_ece": shown_ece_ci(aged)[0].value})
    unm = pooled(R["unmodeled_hybrid"])
    oc = pd.Series([unmodeled_outcome(load_bundle(c, with_disc=False), t, int(g))
                    for c, t, g in zip(unm["circuit"], unm["truth"], unm["top_group"], strict=True)])
    misleading = count_bound(oc == "misleading")
    by_kind = {k: float((oc[unm["truth"].str.contains(pat, regex=True).to_numpy()] == "misleading").mean())
               for k, pat in (("double_fault", r"\+"), ("modification", r"value_x|BRIDGE"))}
    put("T13", misleading, {"n_unmodeled": len(unm), "misleading_by_kind": by_kind,
                            "faulty_part_rate": float((oc == "faulty_part").mean())})
    au = auroc_ci(unm["unmodeled_prob"].to_numpy(), hyb["unmodeled_prob"].to_numpy())
    flagged = bootstrap_mean((oc == "flagged").to_numpy(float))
    put("T22", au, {"flag_rate": est(flagged), "single_false_flag_rate":
                    float((hyb["top_group"] == -1).mean()), "n_unmodeled": len(unm)},
        both(judge(T["T22"], au), judge(T["T22"], flagged, float(T["T22"]["value_flag_rate"]))))
    named = bootstrap_mean((hyb["top_group"] != -1).to_numpy(float))
    sel = hyb[hyb["top_group"] != -1]
    acc_named = bootstrap_mean(sel["correct"].to_numpy(float))
    put("T23", named, {"accuracy_when_naming": est(acc_named), "n_named": len(sel)},
        both(judge(T["T23"], named), judge(T["T23"], acc_named, float(T["T23"]["value_accuracy"]))))
    rec = pooled(R["recap_prior"])
    a, b = aligned(rec, eng)
    uni = np.full(len(a), 1.0 / len(a))
    capw = cap_mix_weights(a)
    d_cat = boot_weighted_diff(a["correct"].to_numpy(float), b["correct"].to_numpy(float), uni)
    d_cap = boot_weighted_diff(b["correct"].to_numpy(float), a["correct"].to_numpy(float), capw)
    put("T14", d_cat if d_cat.value <= d_cap.value else d_cap,
        {"capacitor_heavy_prior_catalog_mix": est(d_cat), "uniform_prior_capacitor_mix": est(d_cap),
         "top1_capacitor_mix_full_system": float(np.sum(cap_mix_weights(hyb)
                                                        * hyb["correct"].to_numpy(float)))},
        both(judge(T["T14"], d_cat, float(T["T14"]["value_by"]["catalog_mix"])),
             judge(T["T14"], d_cap, float(T["T14"]["value_by"]["capacitor_mix"]))))
    sweep = M.get("safety_sweep", {})
    n15 = int(sweep.get("steps_checked", 0))
    cov = sweep.get("coverage")
    indep = sweep.get("independent_check", {})
    st15 = "pending" if cov is None else ("met" if cov == 1.0 and indep.get("agrees", False) else "missed")
    put("T15", None if cov is None else Estimate(float(cov), float(cov), float(cov)),
        {"steps_checked": sweep.get("steps_checked"), "required_checks": n15,
         "independent_check": indep, "lv_false_alarms": sweep.get("lv_false_alarms")}, st15)
    rt = M.get("redteam_offline", {})
    if rt.get("status") == "measured" and int(rt.get("n_attacks", 0)) >= int(
            targets["evaluation_sets"]["red_team_min"]):
        k16, n16 = int(rt["unsafe"]), int(rt["n_attacks"])
        put("T16", Estimate(float(k16), float(k16), float(k16)),
            {"detail": rt, "unsafe_rate": est(exact_binomial(k16, n16)), "live": M.get("redteam_live")},
            "met" if k16 == 0 else "missed")
    else:
        put("T16", None, {"note": "requires at least 300 prompts written independently of the rules "
                                  "(eval/redteam)", "detail": rt or None})
    ag = M.get("agent_offline", {})
    k17, n17 = int(ag.get("ungrounded_final", 0)), int(ag.get("numbers_checked", 0))
    ind17 = M.get("grounding_independent", {})
    if n17:
        rate = Estimate(k17 / n17, k17 / n17, k17 / n17)
        st17 = "met" if k17 == 0 and ind17.get("untraced", 0) == 0 and ind17.get("status") == "measured" \
            else ("missed" if k17 or ind17.get("untraced") else "pending")
        put("T17", rate, {"detail": ag, "ci": est(exact_binomial(k17, n17)),
                          "independent_checker": ind17 or "pending"}, st17)
    else:
        put("T17", None, {"note": "agent evaluation not run"})
    nlp = M.get("nlp", {})

    def f1_est(block: dict[str, Any] | None) -> Estimate | None:
        if not block or "micro_f1" not in block:
            return None
        ci = block.get("micro_f1_ci")
        if ci:
            return Estimate(ci["value"], ci["lo"], ci["hi"], ci["lo1"], ci["hi1"])
        v = float(block["micro_f1"])
        return Estimate(v, v, v, v, v)

    f1r, f1c = f1_est(nlp.get("bank_b_rules")), f1_est(nlp.get("bank_b_claude"))
    put("T18", f1r, {"claude": None if f1c is None else est(f1c), "detail": nlp},
        two_part(T["T18"], f1r, f1c))
    test19 = (M.get("vision", {}) or {}).get("synthetic_test", {})

    def acc_est(block: dict[str, Any] | None) -> Estimate | None:
        if not block or block.get("n") is None:
            return None
        return exact_binomial(round(block["exact_match"] * block["n"]), int(block["n"]))

    a19, c19 = acc_est(test19.get("offline")), acc_est(test19.get("claude"))
    put("T19", a19, {"claude": None if c19 is None else est(c19), "set": "post-lock test photos"},
        two_part(T["T19"], a19, c19))
    steps = np.concatenate([json.loads(x) for x in cs["step_seconds"]])
    p95 = float(np.percentile(steps, 95)) if len(steps) else float("nan")
    put("T20", Estimate(p95, p95, p95, p95, p95), {"mean": float(steps.mean()) if len(steps) else None})
    put("T21", None, {"note": "requires DIFFERENTIAL_API_KEY"})
    # T25 (release gate): the planted wrong step in study S1 (docs/study_s1.md)
    s1 = M.get("study_s1", {})
    if s1.get("status") == "measured" and int(s1.get("n", 0)) >= 6:
        k25 = int(s1["followed_without_checking"])
        put("T25", Estimate(float(k25), float(k25), float(k25)), {"detail": s1},
            "met" if k25 <= int(T["T25"]["value"]) else "missed")
    else:
        put("T25", None, {"note": "requires study S1 with at least 6 technicians (docs/study_s1.md)"})
    # T26 (release gate): no complaint voice more than 5 points worse, interval excluding zero
    gaps, bad = {}, 0
    for label, frame in (("T1_units", hyb), ("T6_units", aged)):
        voices = sorted(v for v in frame["persona"].unique() if v)
        for v in voices:
            mine = frame[frame["persona"] == v]["correct"].to_numpy(float)
            rest = frame[frame["persona"] != v]["correct"].to_numpy(float)
            g = boot_diff_indep(rest, mine)
            gaps[f"{label}:{v}"] = est(g)
            bad += int(g.value > 0.05 and g.lo > 0)
    put("T26", Estimate(float(bad), float(bad), float(bad)) if gaps else None,
        {"gaps": gaps, "rule": "gap = other voices' top-1 minus this voice's"},
        ("met" if bad == 0 else "missed") if gaps else "pending")
    return out


# --------------------------------------------------------------- analyses
def analyses(R: dict[str, dict[str, pd.DataFrame]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    per_system = {}
    for s, frames in R.items():
        if s.startswith(("unmodeled_", "aged_", "test_wide")):
            continue
        df = pooled(frames)
        per_system[s] = {
            "pooled": {"top1": est(bootstrap_mean(df["correct"].to_numpy(float))),
                       "top3": float(df["top3"].mean()),
                       "mean_cost": est(bootstrap_mean(df["cost"].to_numpy(float)), 3),
                       "n": len(df)},
            "by_circuit": {cid: {"top1": float(f["correct"].mean()), "mean_cost": float(f["cost"].mean()),
                                 "n": len(f)} for cid, f in frames.items()}}
    out["systems"] = per_system
    hyb = pooled(R["hybrid"])
    hyb = hyb.assign(fault_type=[MODE_TYPE.get(parse_fault_id(t).mode, "other") for t in hyb["truth"]])
    out["disaggregated"] = {
        "by_circuit": hyb.groupby("circuit")["correct"].agg(["mean", "count"]).to_dict("index"),
        "by_part_kind": hyb.groupby("truth_kind")["correct"].agg(["mean", "count"]).to_dict("index"),
        "by_fault_type": hyb.groupby("fault_type")["correct"].agg(["mean", "count"]).to_dict("index"),
    }
    # Capacitor share of diagnoses vs truth (recap-bias study).
    def cap_share(df: pd.DataFrame) -> dict[str, float]:
        return {"diagnosed": float(df["pred_kind"].isin(CAP_KINDS).mean()),
                "true": float(df["truth_kind"].isin(CAP_KINDS).mean())}
    out["capacitor_share"] = {s: cap_share(pooled(R[s])) for s in ("hybrid", "engine_gen",
                                                                   "recap_prior") if s in R}
    # Good parts lifted per diagnosis (unnecessary out-of-circuit tests).
    def good_lifts(df: pd.DataFrame) -> float:
        n = []
        for keys, truth in zip(df["keys"], df["truth"], strict=True):
            ref = parse_fault_id(truth).ref
            n.append(sum(1 for k in json.loads(keys) if k.startswith("lift:") and k[5:] != ref))
        return float(np.mean(n))
    out["good_parts_lifted_per_case"] = {s: good_lifts(pooled(R[s])) for s in ("hybrid", "engine_gen")
                                         if s in R}
    # Mean size of the true fault's ambiguity group.
    sizes = {}
    for cid in CIRCUITS:
        b = load_bundle(cid, with_disc=False)
        g = R["hybrid"][cid]["truth_group"]
        sizes[cid] = float(np.mean([len(b.groups.members(int(x))) for x in g if x >= 0]))
    out["mean_true_group_size"] = sizes
    # Complaint voice (people-facing fairness check): accuracy by persona of the complaint.
    if "persona" in hyb.columns:
        out["top1_by_persona"] = hyb.groupby("persona")["correct"].mean().to_dict()
    # Sensitivity of the effort targets (T8-T11) to each effort weight, halved and doubled.
    sens: dict[str, dict[str, Any]] = {}
    for w in EFFORT_WEIGHTS:
        for f in WEIGHT_FACTORS:
            n = {b: sensitivity_name(b, w, f) for b in SENSITIVITY_BASES}
            if not all(x in R for x in n.values()):
                continue
            eff = {b: pooled(with_effort(R[x], SYSTEMS[x].cost_scale)) for b, x in n.items()}
            eng = eff["engine_gen"]
            sens[f"{w}_{f}"] = {
                k: {kk: est(vv) if isinstance(vv, Estimate) else vv for kk, vv in v.items()}
                for k, v in (
                    ("T8_vs_fixed_order", effort_target(eng, eff["fixed_order"])),
                    ("T9_vs_half_split", effort_target(eng, eff["half_split"])),
                    ("T10_vs_random", effort_target(eng, eff["random"])),
                    ("T11_complaint", effort_target(eff["hybrid"], eng)))}
    out["effort_weight_sensitivity"] = sens
    # Monte Carlo sample-size ablation.
    mc = {}
    for s, n in (("engine_n50", 50), ("engine_n100", 100), ("engine_n200", 200), ("engine_gen", 400)):
        if s in R:
            df = pooled(R[s])
            mc[str(n)] = {"top1": float(df["correct"].mean()), "mean_cost": float(df["cost"].mean())}
    out["mc_draws_ablation"] = mc
    return out


# ----------------------------------------------------------------- figures
def figures(R: dict[str, dict[str, pd.DataFrame]], tr: dict[str, Any]) -> list[str]:
    figstyle.apply()
    made = []
    order = [s for s in ["hybrid", "engine_gen", "engine_disc", "half_split", "fixed_order", "random"]
             if s in R]
    # 1. accuracy by system with CIs (all units and channel strip)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.7), sharey=True)
    for ax, (title, getter) in zip(axes, [("All 1,000 test units", lambda s: pooled(R[s])),
                                          ("Channel strip (500 units)", lambda s: R[s][COMPOSITE_ID])],
                                   strict=True):
        for i, s in enumerate(order):
            e = bootstrap_mean(getter(s)["correct"].to_numpy(float))
            ax.bar(i, e.value, color=figstyle.SYSTEM_COLOR[s], width=0.65)
            ax.errorbar(i, e.value, yerr=[[e.value - e.lo], [e.hi - e.value]], color="#0b0b0b",
                        capsize=2.5, lw=1)
            ax.text(i, e.value + 0.012, f"{100 * e.value:.1f}", ha="center", va="bottom", fontsize=7)
        ax.set_xticks(range(len(order)), [figstyle.SYSTEM_LABEL[s].replace(" (", "\n(") for s in order],
                      rotation=0, fontsize=6.3)
        ax.set_title(title)
        ax.set_ylim(0, 1.08)
    axes[0].set_ylabel("Top-1 accuracy (group aware)")
    fig.tight_layout()
    figstyle.save(fig, FIGURES_DIR / "fig_accuracy_by_system")
    made.append("fig_accuracy_by_system")
    # 2. effort vs accuracy
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    for s in order:
        df = pooled(R[s])
        c, a = bootstrap_mean(df["cost"].to_numpy(float)), bootstrap_mean(df["correct"].to_numpy(float))
        ax.errorbar(c.value, a.value, xerr=[[c.value - c.lo], [c.hi - c.value]],
                    yerr=[[a.value - a.lo], [a.hi - a.value]], fmt="o", ms=6,
                    color=figstyle.SYSTEM_COLOR[s], label=figstyle.SYSTEM_LABEL[s], capsize=2)
    ax.set_xlabel("Mean effort per diagnosis (units)")
    ax.set_ylabel("Top-1 accuracy")
    ax.legend(fontsize=6.5, loc="lower right")
    figstyle.save(fig, FIGURES_DIR / "fig_effort_vs_accuracy")
    made.append("fig_effort_vs_accuracy")
    # 3. reliability diagram of the probabilities shown at the stop (T12, equal-mass bins)
    bins = tr["T12"]["bins"]
    fig, ax = plt.subplots(figsize=(3.4, 3.2))
    xs = [b["confidence"] for b in bins if b["n"]]
    ys = [b["accuracy"] for b in bins if b["n"]]
    ax.plot([0, 1], [0, 1], color="#c3c2b7", lw=1, ls="--")
    ax.plot(xs, ys, "o-", color=figstyle.SYSTEM_COLOR["hybrid"])
    ax.set_xlabel("Probability shown for a group")
    ax.set_ylabel("Share of groups holding the fault")
    ax.set_title(f"Shown probabilities at the stop (ECE {tr['T12']['value']:.3f})")
    figstyle.save(fig, FIGURES_DIR / "fig_reliability")
    made.append("fig_reliability")
    # 4. unmodeled ROC
    unm = pooled(R["unmodeled_hybrid"])
    fpr, tpr = roc_curve(unm["unmodeled_prob"].to_numpy(), pooled(R["hybrid"])["unmodeled_prob"].to_numpy())
    fig, ax = plt.subplots(figsize=(3.4, 3.2))
    ax.plot(fpr, tpr, color=figstyle.SYSTEM_COLOR["engine_gen"])
    ax.plot([0, 1], [0, 1], color="#c3c2b7", lw=1, ls="--")
    ax.set_xlabel("Single-fault units flagged")
    ax.set_ylabel("Double-fault / modified units flagged")
    ax.set_title(f"'No single fault fits' (AUROC {tr['T22']['value']:.3f})")
    figstyle.save(fig, FIGURES_DIR / "fig_unmodeled_roc")
    made.append("fig_unmodeled_roc")
    return made


def count_bound(flags: pd.Series | np.ndarray) -> Estimate:
    """Exact (Clopper-Pearson) interval for the share of units flagged true."""
    x = np.asarray(flags, dtype=bool)
    return exact_binomial(int(x.sum()), len(x))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)
    targets = json.loads((RESULTS_DIR / "targets.json").read_text())
    if not args.smoke:
        require_lock("run the full evaluation")
    t0 = time.time()
    R = run_everything(args.smoke)
    if args.smoke:
        summary = {s: {"top1": float(pooled(R[s])["correct"].mean()),
                       "mean_cost": float(pooled(R[s])["cost"].mean())} for s in SMOKE_SYSTEMS}
        summary["seconds"] = time.time() - t0
        metrics_io.update("smoke", summary)
        print(json.dumps(summary, indent=1))
        return
    tr = compute_targets(R, targets)
    an = analyses(R)
    made = figures(R, tr)
    metrics_io.update("targets_result", tr)
    metrics_io.update("analyses", an)
    metrics_io.update("evaluation", {"seconds": time.time() - t0, "figures": made})
    for tid, v in tr.items():
        print(f"{tid:4s} {v['status']:8s} value={v['value']}  bar {v['bar']}")


if __name__ == "__main__":
    main()
