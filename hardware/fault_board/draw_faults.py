"""Sealed random draw of the T7 hardware faults (hardware/fault_board/validation_protocol.md).

Run once by the fault setter, with a private seed:

    python hardware/fault_board/draw_faults.py --seed 81723 --out-dir fault_run/

Writes ``sealed_key.csv`` (unit, board, fault: kept by the setter until every reading is
recorded) and ``recording_sheet.csv`` (unit, board, measurement key, empty value and
notes columns) for the recorder. Faults are drawn without replacement within a board
from every catalogued driver-block fault that can be built from the fault kit.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BOARDS = ("A", "B", "C")
PER_BOARD = 20
NOT_BUILDABLE = {"beta_low"}  # no part with a controlled low gain is at hand


def buildable_faults() -> list[str]:
    from differential.circuits.library import get_circuit
    from differential.sim.faults import fault_catalog

    return [f.id for f in fault_catalog(get_circuit("driver"))
            if not f.is_healthy and f.mode not in NOT_BUILDABLE]


def measurement_keys() -> list[str]:
    from differential.circuits.library import get_circuit
    from differential.sim.observables import spice_observables

    return [o.key for o in spice_observables(get_circuit("driver"))]


def draw(seed: int, per_board: int = PER_BOARD) -> list[tuple[str, str, str]]:
    faults = buildable_faults()
    rng = np.random.default_rng(seed)
    units = []
    n = 0
    for board in BOARDS:
        for f in rng.choice(len(faults), size=per_board, replace=False):
            n += 1
            units.append((f"U{n:03d}", board, faults[int(f)]))
    order = rng.permutation(len(units))  # recording order mixes the boards
    return [units[int(i)] for i in order]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, required=True, help="the fault setter's private number")
    ap.add_argument("--out-dir", type=Path, default=Path("fault_run"))
    ap.add_argument("--per-board", type=int, default=PER_BOARD)
    a = ap.parse_args(argv)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    units = draw(a.seed, a.per_board)
    with (a.out_dir / "sealed_key.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["unit", "board", "fault"])
        w.writerows(units)
    keys = measurement_keys()
    with (a.out_dir / "recording_sheet.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["unit", "board", "key", "value", "notes"])
        for unit, board, _ in units:
            for k in keys:
                w.writerow([unit, board, k, "", ""])
    print(f"{len(units)} units, {len(keys)} readings each; give recording_sheet.csv to the recorder "
          "and keep sealed_key.csv closed until every reading is in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
