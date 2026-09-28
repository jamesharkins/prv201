"""Command-line entry point: ``python -m differential.cli <command>`` (or ``differential``)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from differential.circuits.library import CIRCUIT_IDS
from differential.config import SIM_DIR


def _progress_logger(path: Path):  # type: ignore[no-untyped-def]
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    def report(done: int, total: int) -> None:
        if done % 20 == 0 or done == total:
            rate = done / max(time.time() - t0, 1e-9)
            eta = (total - done) / max(rate, 1e-9)
            with path.open("a") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} {done}/{total} jobs, ETA {eta/60:.1f} min\n")

    return report


def cmd_sim(args: argparse.Namespace) -> int:
    from differential.sim import montecarlo as mc

    circuits = CIRCUIT_IDS if args.circuits == "all" else tuple(args.circuits.split(","))
    progress_log = SIM_DIR / "progress.log"
    entries: dict[str, dict[str, object]] = {}
    for cid in circuits:
        jobs = mc.catalog_jobs(cid, args.split, args.draws)
        tag = f"{cid}__{args.split}"
        with progress_log.open("a") as fh:
            fh.write(f"=== {tag}: {len(jobs)} jobs ===\n")
        df, failures = mc.run_jobs(jobs, tag, workers=args.workers,
                                   progress=_progress_logger(progress_log))
        path = mc.save_dataset(df, cid, args.split)
        summary = mc.summarise(df)
        summary.update({"draws_per_hypothesis": args.draws, "path": str(path.name),
                        "failures_logged": len(failures)})
        entries[tag] = summary
        (SIM_DIR / f"failures__{tag}.jsonl").write_text(
            "".join(json.dumps(f) + "\n" for f in failures)
        )
        with progress_log.open("a") as fh:
            fh.write(f"=== {tag} done: {summary} ===\n")
    mc.write_manifest({"datasets": entries})
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(prog="differential")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sim", help="run Monte Carlo simulation for the fault catalog")
    p.add_argument("--split", default="train", choices=["train", "val"])
    p.add_argument("--draws", type=int, default=400)
    p.add_argument("--circuits", default="all")
    p.add_argument("--workers", type=int, default=None)
    p.set_defaults(func=cmd_sim)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
