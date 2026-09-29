"""Collect the design constants the documents quote into results/design.json.

Every value is read from the code that uses it (module constants and function
defaults), so a document can only quote what the system actually does.
Usage: python tools/design_constants.py
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def default(fn: Any, name: str) -> Any:
    return inspect.signature(fn).parameters[name].default


def collect() -> dict[str, Any]:
    from differential.agent import agent, grounding, tools
    from differential.engine import ambiguity, discriminative, generative, selection, session
    from differential.engine import symptom_prior as sp
    from differential.engine.bundle import DEFAULT_UNMODELED_PRIOR
    from differential.instruments import scpi
    from differential.nlp.benchmark import COMPLAINT_NOISE as noise
    from differential.safety import hazards, rules
    from differential.sim import draws as draws_mod
    from differential.sim import measurement as meas
    from differential.sim import montecarlo as mc
    from eval import cases, recalibrate_unmodeled, run_eval, set_bars, stats
    from eval import train as train_mod

    ds = session.DiagnosisSession.__init__
    return {
        "simulation": {
            "train_draws": 400, "val_draws": 100,  # cli/Makefile defaults, checked below
            "chunk_draws": mc.CHUNK, "base_seed": mc.BASE_SEED,
            "stress_tolerance_scale": mc.TOL_SCALE["test_wide"],
            "tolerance_curve": sorted({v for k, v in mc.TOL_SCALE.items() if k.startswith("test_")}),
            "mains_tol_pct": 100 * draws_mod.MAINS_TOL,
            "aging": {"electrolytic_c": list(draws_mod.AGE_ELECTROLYTIC_C),
                      "electrolytic_esr": list(draws_mod.AGE_ELECTROLYTIC_ESR),
                      "resistor": list(draws_mod.AGE_RESISTOR),
                      "triode_emission": list(draws_mod.AGE_TRIODE_EMISSION)},
        },
        "measurement": {
            "dmm_pct": 100 * meas.DMM_PCT, "dmm_counts": meas.DMM_DIGITS,
            "scope_pct": 100 * meas.SCOPE_REL, "thd_pct": 100 * meas.THD_REL,
            "lift_sensitivity": meas.LIFT_SENSITIVITY,
            "lift_false_positive_pct": round(100 * (1 - meas.LIFT_SPECIFICITY), 6),
            "hum_floor_uv": round(meas.HUM_FLOOR * 1e6, 6),
            "dmm_input_mohm": meas.DMM_INPUT_OHMS / 1e6,
        },
        "engine": {
            "gmm_max_components": default(generative.GenerativeModel.fit, "max_components"),
            "gmm_min_samples_per_component": generative.MIN_SAMPLES_PER_COMPONENT,
            "disc_masked_copies": default(discriminative.DiscriminativeModel.fit, "n_masks"),
            "disc_max_rounds": default(discriminative.DiscriminativeModel.fit, "num_boost_round"),
            "disc_early_stopping": discriminative.EARLY_STOPPING_ROUNDS,
            "disc_keep_p": list(discriminative.KEEP_P_RANGE),
            "disc_learning_rate": discriminative.LGB_PARAMS["learning_rate"],
            "disc_leaves": discriminative.LGB_PARAMS["num_leaves"],
            "group_threshold": ambiguity.DEFAULT_THRESHOLD,
            "group_draws_per_fault": default(ambiguity.build_groups, "per_hyp"),
            "eig_samples": default(ds, "n_samples"),
            "eig_min_bits": default(ds, "eig_min"),
            "tie_tolerance": selection.TIE_TOL,
            "stop_threshold": session.STOP_THRESHOLD,
            "budget": session.DEFAULT_BUDGET,
            "max_steps": default(session.DiagnosisSession.run, "max_steps"),
            "unmodeled_prior": DEFAULT_UNMODELED_PRIOR,
            "half_split_band_sd": session.NORMAL_BAND_SD,
            "scripts_confirm_at": session.CONFIRM_AT,
        },
        "symptoms": {
            "no_output_db": sp.NO_OUTPUT_DB, "low_gain_db": sp.LOW_GAIN_DB,
            "hum_margin_db": sp.HUM_MARGIN_DB, "distortion_factor": sp.DIST_FACTOR,
            "distortion_min_pct": sp.DIST_MIN_PCT, "dc_out_v": sp.DC_OUT_V,
            "bias_rel_pct": 100 * sp.BIAS_REL, "response_db": sp.RESPONSE_DB,
            "rail_dead_pct": 100 * sp.RAIL_DEAD_FRAC, "rail_drift_pct": 100 * sp.RAIL_DRIFT_REL,
            "n_features": len(sp.FEATURES),
        },
        "calibration": {
            "false_alarm_budget": recalibrate_unmodeled.FPR_BUDGET,
            "resolution": recalibrate_unmodeled.RESOLUTION,
            "single_units": dict(recalibrate_unmodeled.N_SINGLE),
            "provisional_grid_max": max(train_mod.OFFSETS),
        },
        "cases": {"n": {k: dict(v) for k, v in cases.N_CASES.items()},
                  "max_attempts": cases.MAX_ATTEMPTS,
                  "complaint_omit_pct": 100 * noise.p_omit, "complaint_add_pct": 100 * noise.p_add},
        "statistics": {
            "bootstrap_resamples": stats.N_BOOT, "seed": stats.SEED,
            "ece_bins": default(stats.ece, "n_bins"),
            "step_ece_case_resamples": default(run_eval.step_ece_ci, "n_boot"),
            "bar_k": set_bars.K, "bar_weights": dict(set_bars.WEIGHTS),
        },
        "agent": {
            "tools": len(tools.TOOL_NAMES), "modes": len(agent.MODES),
            "grounding_small_count_max": grounding.SMALL_COUNT_MAX,
        },
        "safety": {
            "refusal_categories": len(rules.REFUSAL_RULES),
            "injection_markers": len(rules.INJECTION_MARKERS),
            "hv_threshold_v": rules.HV_THRESHOLD_V,
            "discharge_verify_max_v": hazards.DISCHARGE_VERIFY_MAX_V,
            "scpi_max_v": scpi.MAX_BENCH_VOLTS,
        },
    }


def check_draw_defaults(d: dict[str, Any]) -> None:
    """The draw counts are CLI/Makefile defaults; fail if they drift from the manifest."""
    manifest = json.loads((ROOT / "data" / "sim" / "manifest.json").read_text())
    per = {k: v.get("draws_per_hypothesis") for k, v in manifest.get("datasets", {}).items()}
    train = {v for k, v in per.items() if k.endswith("__train")}
    val = {v for k, v in per.items() if k.endswith("__val")}
    assert train == {d["simulation"]["train_draws"]}, train
    assert val == {d["simulation"]["val_draws"]}, val


def main() -> int:
    d = collect()
    check_draw_defaults(d)
    out = ROOT / "results" / "design.json"
    out.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
