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
import subprocess
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
from eval.harness import SYSTEMS, run_system, unmodeled_outcome
from eval.stats import (
    Estimate,
    auroc_ci,
    bootstrap_mean,
    bootstrap_ratio_of_means,
    ece,
    mcnemar,
    paired_diff,
    roc_curve,
)

CIRCUITS = [COMPOSITE_ID, *BLOCK_IDS]
MAIN = ["random", "fixed_order", "half_split", "engine_gen", "engine_disc", "hybrid"]
ABLATIONS = ["hybrid_oracle", "hybrid_paraphrase", "recap_prior", "engine_eig_nocost",
             "engine_n50", "engine_n100", "engine_n200", "engine_w_half", "engine_w_double",
             "fixed_order_w_half", "fixed_order_w_double", "half_split_w_half",
             "half_split_w_double"]
SMOKE_SYSTEMS = ["random", "fixed_order", "half_split", "engine_gen", "hybrid"]
SMOKE_LIMIT = 8
# The smoke test checks the pipeline, not the system: it runs on the pilot splits so
# that no check before the targets-locked tag ever touches a test unit.
SPLITS = {"test": "test", "unmodeled_test": "unmodeled_test", "test_wide": "test_wide"}
SMOKE_SPLITS = {"test": "pilot", "unmodeled_test": "unmodeled_pilot", "test_wide": "pilot_wide"}
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
    out["wide_hybrid"] = {COMPOSITE_ID: run_system(SYSTEMS["hybrid"], COMPOSITE_ID,
                                                   sp["test_wide"], limit=limit)}
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
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return Estimate(value, float(lo), float(hi)), bins


def boot_diff_indep(a: np.ndarray, b: np.ndarray, n_boot: int = 2000) -> Estimate:
    rng = np.random.default_rng(11)
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = [a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean()
         for _ in range(n_boot)]
    lo, hi = np.percentile(d, [2.5, 97.5])
    return Estimate(float(a.mean() - b.mean()), float(lo), float(hi))


# ----------------------------------------------------------------- targets
def judge(t: dict[str, Any], value: float | None) -> str:
    if value is None or not np.isfinite(value):
        return "pending"
    comp, bar = t["comparator"], float(t["value"])
    ok = {"≥": value >= bar, ">=": value >= bar, "<=": value <= bar, "==": abs(value - bar) < 1e-12,
          "margin>=": value >= bar}.get(comp)
    if ok is None:
        raise ValueError(comp)
    return "met" if ok else "missed"


def effort_target(eng: pd.DataFrame, base: pd.DataFrame) -> dict[str, Any]:
    a, b = aligned(eng, base)
    ratio = bootstrap_ratio_of_means(a["cost"].to_numpy(), b["cost"].to_numpy())
    acc_gap = float(a["correct"].mean() - b["correct"].mean())
    return {"ratio": est(ratio), "top1_system": float(a["correct"].mean()),
            "top1_baseline": float(b["correct"].mean()), "top1_gap": acc_gap,
            "accuracy_condition": acc_gap >= -0.02, "n": len(a)}


def compute_targets(R: dict[str, dict[str, pd.DataFrame]], targets: dict[str, Any]) -> dict[str, Any]:
    M = metrics_io.load()
    T = {t["id"]: t for t in targets["targets"]}
    out: dict[str, Any] = {}
    hyb = pooled(R["hybrid"])
    cs = R["hybrid"][COMPOSITE_ID]

    def put(tid: str, value: float | None, detail: dict[str, Any], status: str | None = None) -> None:
        st = status or judge(T[tid], value)
        out[tid] = {"id": tid, "bar": T[tid]["text"], "value": value, "status": st, **detail}

    e1 = bootstrap_mean(hyb["correct"].to_numpy(float))
    put("T1", e1.value, {"ci": est(e1), "n": len(hyb)})
    e2 = bootstrap_mean(cs["correct"].to_numpy(float))
    put("T2", e2.value, {"ci": est(e2), "n": len(cs)})
    e3 = bootstrap_mean(hyb["top3"].to_numpy(float))
    put("T3", e3.value, {"ci": est(e3), "n": len(hyb)})
    margins = {}
    for base in ("fixed_order", "random"):
        a, b = aligned(cs, R[base][COMPOSITE_ID])
        d = paired_diff(a["correct"].to_numpy(float), b["correct"].to_numpy(float))
        margins[base] = {"margin": est(d), "mcnemar": mcnemar(a["correct"].to_numpy(),
                                                               b["correct"].to_numpy())}
    worst = min(v["margin"]["value"] for v in margins.values())
    put("T4", worst, {"margins": margins})
    llm = M.get("llm_only")
    if isinstance(llm, dict) and "margin" in llm:
        put("T5", llm["margin"]["value"], {"detail": llm})
    else:
        put("T5", None, {"note": "requires DIFFERENTIAL_API_KEY; protocol in eval/llm_baseline.py"})
    wide = R["wide_hybrid"][COMPOSITE_ID]
    drop = boot_diff_indep(cs["correct"].to_numpy(float), wide["correct"].to_numpy(float))
    put("T6", drop.value, {"ci": est(drop), "wide_top1": float(wide["correct"].mean()),
                           "n_wide": len(wide)})
    put("T7", None, {"note": "requires the hardware fault board (hardware/fault_board)"})
    eng = pooled(R["engine_gen"])
    for tid, base in (("T8", "fixed_order"), ("T9", "half_split"), ("T10", "random")):
        d = effort_target(eng, pooled(R[base]))
        st = judge(T[tid], d["ratio"]["value"])
        if st == "met" and not d["accuracy_condition"]:
            st = "missed"
        put(tid, d["ratio"]["value"], d, st)
    d = effort_target(hyb, eng)
    st = judge(T["T11"], d["ratio"]["value"])
    put("T11", d["ratio"]["value"], d, "missed" if st == "met" and not d["accuracy_condition"] else st)
    e12, bins = step_ece_ci(hyb)
    put("T12", e12.value, {"ci": est(e12), "bins": bins,
                           "stop_ece": ece(hyb["confidence"].to_numpy(),
                                           hyb["correct"].to_numpy(float))[0]})
    unm = pooled(R["unmodeled_hybrid"])
    au = auroc_ci(unm["unmodeled_prob"].to_numpy(), hyb["unmodeled_prob"].to_numpy())
    oc = pd.Series([unmodeled_outcome(load_bundle(c, with_disc=False), t, int(g))
                    for c, t, g in zip(unm["circuit"], unm["truth"], unm["top_group"], strict=True)])
    flagged = bootstrap_mean((oc == "flagged").to_numpy(float))
    misleading = bootstrap_mean((oc == "misleading").to_numpy(float))
    false_flag = float((hyb["top_group"] == -1).mean())
    st = judge(T["T13"], au.value)
    if st == "met" and (flagged.value < float(T["T13"]["value_flag_rate"])
                        or misleading.value > float(T["T13"]["value_misleading"])):
        st = "missed"
    put("T13", au.value, {"ci": est(au), "flag_rate": est(flagged),
                          "faulty_part_rate": float((oc == "faulty_part").mean()),
                          "misleading_rate": est(misleading),
                          "single_false_flag_rate": false_flag, "n_unmodeled": len(unm)}, st)
    a, b = aligned(pooled(R["recap_prior"]), eng)
    d14 = paired_diff(a["correct"].to_numpy(float), b["correct"].to_numpy(float))
    put("T14", d14.value, {"ci": est(d14)})
    sweep = M.get("safety_sweep", {})
    put("T15", sweep.get("coverage"), {"steps_checked": sweep.get("steps_checked"),
                                       "lv_false_alarms": sweep.get("lv_false_alarms")})
    rt = M.get("redteam_offline", {})
    if rt.get("status") == "measured":
        put("T16", float(rt["unsafe"]), {"detail": rt})
    else:
        put("T16", None, {"note": "requires the team-written red-team suite (eval/redteam)"})
    ag = M.get("agent_offline", {})
    put("T17", ag.get("ungrounded_rate"), {"detail": ag})
    nlp = M.get("nlp", {})
    f1 = nlp.get("held_out_rules", {}).get("micro_f1")
    st18 = None if f1 is None else ("met" if f1 >= float(T["T18"]["value_offline"]) else "missed")
    put("T18", f1, {"part": "offline rules (Claude part pending a key)", "detail": nlp}, st18)
    vis = M.get("vision", {})
    acc = vis.get("offline_exact_match") if isinstance(vis, dict) else None
    st19 = None if acc is None else ("met" if acc >= float(T["T19"]["value_offline"]) else "missed")
    put("T19", acc, {"part": "offline reader (Claude part pending a key)"}, st19)
    steps = np.concatenate([json.loads(x) for x in cs["step_seconds"]])
    p95 = float(np.percentile(steps, 95)) if len(steps) else None
    put("T20", p95, {"mean": float(steps.mean()) if len(steps) else None})
    put("T21", None, {"note": "requires DIFFERENTIAL_API_KEY"})
    return out


# --------------------------------------------------------------- analyses
def analyses(R: dict[str, dict[str, pd.DataFrame]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    per_system = {}
    for s, frames in R.items():
        if s in ("unmodeled_engine", "unmodeled_hybrid", "wide_hybrid"):
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
    # Sensitivity of the effort results to the effort weights.
    sens = {}
    for w in ("half", "double"):
        e, f, h = (f"engine_w_{w}", f"fixed_order_w_{w}", f"half_split_w_{w}")
        if all(x in R for x in (e, f, h)):
            sens[w] = {"vs_fixed_order": effort_target(pooled(R[e]), pooled(R[f])),
                       "vs_half_split": effort_target(pooled(R[e]), pooled(R[h]))}
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
    # 3. reliability diagram over every step
    bins = tr["T12"]["bins"]
    fig, ax = plt.subplots(figsize=(3.4, 3.2))
    xs = [b["confidence"] for b in bins if b["n"]]
    ys = [b["accuracy"] for b in bins if b["n"]]
    ax.plot([0, 1], [0, 1], color="#c3c2b7", lw=1, ls="--")
    ax.plot(xs, ys, "o-", color=figstyle.SYSTEM_COLOR["hybrid"])
    ax.set_xlabel("Stated probability of the top group")
    ax.set_ylabel("Observed accuracy")
    ax.set_title(f"Calibration at every step (ECE {tr['T12']['value']:.3f})")
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
    ax.set_title(f"'No single fault fits' (AUROC {tr['T13']['value']:.3f})")
    figstyle.save(fig, FIGURES_DIR / "fig_unmodeled_roc")
    made.append("fig_unmodeled_roc")
    return made


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)
    targets = json.loads((RESULTS_DIR / "targets.json").read_text())
    if not args.smoke:
        tags = subprocess.run(["git", "tag", "--list", "targets-locked"], capture_output=True,
                              text=True).stdout.strip()
        if tags != "targets-locked":
            raise SystemExit("refusing to run the full evaluation before the targets-locked tag")
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
