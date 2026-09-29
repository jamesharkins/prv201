"""Circuit-library and simulation statistics -> metrics.json section "library"."""

from __future__ import annotations

import json
from collections import Counter

from differential.circuits.library import BLOCK_IDS, CIRCUIT_IDS, get_circuit
from differential.config import SIM_DIR
from differential.engine.bundle import DEFAULT_UNMODELED_PRIOR
from differential.engine.session import DEFAULT_BUDGET, STOP_THRESHOLD
from differential.safety.hazards import DISCHARGE_VERIFY_MAX_V
from differential.sim.faults import FAULT_MODES, fault_catalog
from differential.sim.observables import (
    COST_DC,
    COST_HV_EXTRA,
    COST_LIFT,
    COST_SCOPE,
    lift_observables,
    spice_observables,
)
from eval import metrics_io
from eval.recalibrate_unmodeled import FPR_BUDGET


def symptom_stats() -> dict[str, object]:
    """How much a complaint narrows the suspects (needs trained symptom models)."""
    from differential.config import MODELS_DIR
    from differential.engine.symptom_prior import FEATURES, SymptomModel

    out: dict[str, object] = {}
    for cid in CIRCUIT_IDS:
        path = MODELS_DIR / cid / "symptom_model.json"
        if not path.exists():
            continue
        sm = SymptomModel.load(path)
        faults = [i for i, h in enumerate(sm.hypotheses) if h != "healthy"]
        rate = sm.symptomatic_rate
        assert rate is not None
        per_feature = {f: int(sum(sm.p_feature[i, j] >= 0.5 for i in faults))
                       for j, f in enumerate(FEATURES)}
        out[cid] = {
            "faults": len(faults),
            "latent_faults": int(sum(rate[i] < 0.5 for i in faults)),
            "symptomatic_faults": int(sum(rate[i] >= 0.5 for i in faults)),
            "faults_per_symptom": per_feature,
            "max_faults_sharing_a_symptom": max(per_feature.values()),
        }
    return out


def aged_stats() -> dict[str, object]:
    """Training age mix, and how often ageing alone makes a healthy unit show a symptom
    (against the as-new reference): the aged sets assume the fault, not the ageing, is
    why a unit reaches the bench (ADR-039). Needs trained symptom models."""
    import numpy as np

    from differential.config import MODELS_DIR
    from differential.engine.symptom_prior import SymptomModel, derive_facts
    from differential.sim.montecarlo import load_dataset

    out: dict[str, object] = {}
    for cid in CIRCUIT_IDS:
        path = MODELS_DIR / cid / "symptom_model.json"
        tr = load_dataset(cid, "train")
        if not path.exists() or "aged" not in tr.columns:
            continue
        ref = SymptomModel.load(path).reference
        assert ref is not None
        ok = tr[tr["ok"]]
        circ = get_circuit(cid)
        ah = ok[(ok["hypothesis"] == "healthy") & ok["aged"].astype(bool)]
        facts = [derive_facts(circ, ref, r) for _, r in ah.iterrows()]
        out[cid] = {"train_aged_share": float(ok["aged"].astype(bool).mean()),
                    "aged_healthy_draws": len(ah),
                    "aged_healthy_symptomatic": float(np.mean([f.any for f in facts]))}
    if out:
        rates = [float(v["aged_healthy_symptomatic"]) for v in out.values()]  # type: ignore[index]
        out["max_aged_healthy_symptomatic"] = max(rates)
    return out


def group_stats() -> dict[str, object]:
    """Ambiguity groups per circuit (faults that no measurement can tell apart)."""
    from differential.config import MODELS_DIR

    out: dict[str, object] = {}
    for cid in CIRCUIT_IDS:
        path = MODELS_DIR / cid / "groups.json"
        if not path.exists():
            continue
        g = json.loads(path.read_text())
        sizes = [len(m) for m in g["groups"]]
        faults = sum(1 for h in g["hypotheses"] if h != "healthy")
        out[cid] = {"groups": len(sizes), "hypotheses": len(g["hypotheses"]), "faults": faults,
                    "mean_size": sum(sizes) / len(sizes), "max_size": max(sizes),
                    "singletons": sum(1 for n in sizes if n == 1)}
    return out


def setup_cost() -> dict[str, dict[str, float]]:
    """Machine time to build one circuit model: Monte Carlo simulation (from the sim logs'
    elapsed-time marks) and fitting (training summary), 4-core machine."""
    import re

    from differential.config import MODELS_DIR

    sim_s: dict[str, float] = {}
    for log in ("sim_train.log", "sim_val.log"):
        p = SIM_DIR / log
        if not p.exists():
            continue
        for m in re.finditer(r"(\w+)__(?:train|val): \d+/\d+ jobs \((\d+)s\)", p.read_text()):
            key = f"{m.group(1)}|{log}"
            sim_s[key] = max(sim_s.get(key, 0.0), float(m.group(2)))
    summary_p = MODELS_DIR / "training_summary.json"
    train = json.loads(summary_p.read_text()) if summary_p.exists() else {}
    out = {}
    for cid in CIRCUIT_IDS:
        sim = sum(v for k, v in sim_s.items() if k.startswith(cid + "|"))
        fit = float((train.get(cid) or {}).get("seconds") or 0.0)
        out[cid] = {"simulation_minutes": round(sim / 60, 1), "fitting_minutes": round(fit / 60, 1),
                    "total_minutes": round((sim + fit) / 60, 1)}
    return out


def main() -> None:
    circuits = {}
    for cid in CIRCUIT_IDS:
        c = get_circuit(cid)
        circuits[cid] = {
            "components": len(c.components),
            "hypotheses": len(fault_catalog(c)),  # healthy + every catalog fault
            "faults": len(fault_catalog(c)) - 1,
            "test_points": len(c.test_points),
            "hv_test_points": sum(tp.hv for tp in c.test_points),
            "spice_observables": len(spice_observables(c)),
            "observables_by_kind": dict(Counter(o.kind for o in spice_observables(c))),
            "lift_tests": len(lift_observables(c)),
            "kinds": dict(Counter(comp.kind for comp in c.components)),
        }
    manifest = json.loads((SIM_DIR / "manifest.json").read_text()) \
        if (SIM_DIR / "manifest.json").exists() else {}
    sims = {k: v for k, v in manifest.get("datasets", {}).items()}
    total_rows = sum(int(v.get("rows", 0)) for v in sims.values())
    total_failed = sum(int(v.get("failed_draws", 0)) for v in sims.values())
    total_retried = sum(int(v.get("retried_draws", 0)) for v in sims.values())
    data = {
        "blocks": len(BLOCK_IDS),
        "circuits": circuits,
        "fault_modes_per_kind": {k: len(v) for k, v in FAULT_MODES.items()},
        "fault_mode_count": len({m for v in FAULT_MODES.values() for m in v}),
        "total_hypotheses": sum(circuits[c]["hypotheses"] for c in CIRCUIT_IDS),
        "simulations": {"datasets": sims, "total_draws": total_rows,
                        "failed_draws": total_failed, "retried_draws": total_retried,
                        "ngspice": manifest.get("ngspice_version")},
        "design": {
            "cost_dc": COST_DC, "cost_scope": COST_SCOPE, "cost_hv_extra": COST_HV_EXTRA,
            "cost_lift": COST_LIFT, "budget": DEFAULT_BUDGET, "stop_threshold": STOP_THRESHOLD,
            "unmodeled_prior": DEFAULT_UNMODELED_PRIOR, "train_draws": 400, "val_draws": 100,
            "discharge_verify_max_v": DISCHARGE_VERIFY_MAX_V, "false_alarm_budget": FPR_BUDGET,
        },
    }
    sym = symptom_stats()
    if sym:
        data["symptoms"] = sym
    data["groups"] = group_stats()
    aged = aged_stats()
    if aged:
        data["aged"] = aged
    from differential.engine.session import CONFIRM_AT
    from differential.nlp.benchmark import COMPLAINT_NOISE
    from differential.sim import draws as dr
    from differential.sim.measurement import DMM_DIGITS, DMM_INPUT_OHMS, DMM_PCT, SCOPE_REL

    data["instrument"] = {"dmm_pct": 100 * DMM_PCT, "dmm_counts": DMM_DIGITS,
                          "scope_pct": 100 * SCOPE_REL, "dmm_input_mohm": DMM_INPUT_OHMS / 1e6,
                          "mains_tol_pct": 100 * dr.MAINS_TOL}
    data["aging"] = {"electrolytic_c_loss_max_pct": 100 * (1 - dr.AGE_ELECTROLYTIC_C[0]),
                     "electrolytic_c_loss_min_pct": 100 * (1 - dr.AGE_ELECTROLYTIC_C[1]),
                     "electrolytic_esr_max_x": dr.AGE_ELECTROLYTIC_ESR[1],
                     "resistor_drift_max_pct": 100 * (dr.AGE_RESISTOR[1] - 1),
                     "triode_emission_loss_max_pct": 100 * (1 - dr.AGE_TRIODE_EMISSION[0])}
    data["complaint_noise"] = {"p_omit_pct": 100 * COMPLAINT_NOISE.p_omit,
                               "p_add_pct": 100 * COMPLAINT_NOISE.p_add}
    data["design"]["confirm_at"] = CONFIRM_AT
    data["setup_cost"] = setup_cost()
    metrics_io.update("library", data)
    hc_path = SIM_DIR.parent.parent / "results" / "hand_calcs.json"
    if hc_path.exists():
        hc = json.loads(hc_path.read_text())
        checked = [r for r in hc["rows"] if r["ok"] is not None]
        ratios = [h["ratio"] for h in hc["hum_validation"] if h["ratio"] is not None]
        tols = [100 * r["rel_tol"] for r in checked if r.get("rel_tol")]
        metrics_io.update("hand_calcs", {
            "rows_checked": len(checked),
            "rows_ok": sum(1 for r in checked if r["ok"]),
            "rel_tol_min_pct": min(tols) if tols else None,
            "rel_tol_max_pct": max(tols) if tols else None,
            "abs_tol_db": max((r["abs_tol"] for r in checked
                               if r.get("abs_tol") and r["unit"] == "dB"), default=None),
            "hum_model_overstatement_min_pct": 100 * (min(ratios) - 1) if ratios else None,
            "hum_model_overstatement_max_pct": 100 * (max(ratios) - 1) if ratios else None,
            "rows": {r["quantity"]: {"hand": r["hand"], "sim": r["sim"], "unit": r["unit"]}
                     for r in hc["rows"]},
        })
    print(json.dumps({k: v for k, v in data.items() if k != "circuits"}, indent=1)[:1500])


if __name__ == "__main__":
    main()
