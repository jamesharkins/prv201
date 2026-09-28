"""Circuit-library and simulation statistics -> metrics.json section "library"."""

from __future__ import annotations

import json
from collections import Counter

from differential.circuits.library import BLOCK_IDS, CIRCUIT_IDS, get_circuit
from differential.config import SIM_DIR
from differential.engine.bundle import DEFAULT_UNMODELED_PRIOR
from differential.engine.session import DEFAULT_BUDGET, STOP_THRESHOLD
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
        },
    }
    metrics_io.update("library", data)
    hc_path = SIM_DIR.parent.parent / "results" / "hand_calcs.json"
    if hc_path.exists():
        hc = json.loads(hc_path.read_text())
        checked = [r for r in hc["rows"] if r["ok"] is not None]
        ratios = [h["ratio"] for h in hc["hum_validation"] if h["ratio"] is not None]
        metrics_io.update("hand_calcs", {
            "rows_checked": len(checked),
            "rows_ok": sum(1 for r in checked if r["ok"]),
            "hum_model_overstatement_min_pct": 100 * (min(ratios) - 1) if ratios else None,
            "hum_model_overstatement_max_pct": 100 * (max(ratios) - 1) if ratios else None,
            "rows": {r["quantity"]: {"hand": r["hand"], "sim": r["sim"], "unit": r["unit"]}
                     for r in hc["rows"]},
        })
    print(json.dumps({k: v for k, v in data.items() if k != "circuits"}, indent=1)[:1500])


if __name__ == "__main__":
    main()
