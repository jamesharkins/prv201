"""Parallel Monte Carlo simulation with checkpointing and a reproducibility manifest.

Seeds: every draw uses ``SeedSequence([BASE_SEED, circuit_index, split_index,
hypothesis_index, draw_index])``. Splits have distinct ``split_index`` values, so
training, validation and test draws come from disjoint seed streams by
construction (``tests/test_sim.py`` also checks it on the stored seeds).

Outputs (``data/sim/``):
  <circuit>__<split>.parquet   one row per draw (observables, provenance, status)
  failures.jsonl               every draw that failed all retries
  manifest.json                netlist hashes, seeds, tolerance spec hash, ngspice
                               version, draw counts and failure counts
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import platform
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from differential.circuits.library import CIRCUIT_IDS, DEVICE_LIBRARY, get_circuit
from differential.config import SIM_DIR, n_workers
from differential.sim import builder as builder_module
from differential.sim import draws as draws_module
from differential.sim import runner as runner_module
from differential.sim.builder import fault_netlist
from differential.sim.draws import Draw, age_draw, apply_fault, healthy_draw
from differential.sim.faults import HEALTHY_FAULT, Fault, fault_catalog, parse_fault_id
from differential.sim.observables import lift_observables, spice_observables
from differential.sim.runner import ngspice_version, simulate_draws

BASE_SEED = 20260928
SPLIT_INDEX = {
    "train": 0,
    "val": 1,
    "test": 2,
    "unmodeled_val": 3,
    "unmodeled_test": 4,
    "demo": 5,
    "test_wide": 6,
    "pilot_wide": 7,
    "unmodeled_pilot": 8,
    "pilot": 9,
    "pilot_aged": 10,
    "test_aged": 11,
    "test_wide2": 12,
    "test_wide3": 13,
}
# Stress splits: every tolerance spread widened (a sensitivity curve, reported without bars).
TOL_SCALE = {"test_wide": 1.5, "pilot_wide": 1.5, "test_wide2": 2.0, "test_wide3": 3.0}
# Aged-unit splits: every part drifts the way parts age (draws.age_draw) before the fault.
AGED_SPLITS = frozenset({"pilot_aged", "test_aged"})
# Training, validation and calibration splits mix as-new and aged units (ADR-039): every
# second draw is aged (odd hypothesis index + draw index), so each fault has as many aged
# draws as as-new ones, and calibration cases alternate.
MIXED_AGE_SPLITS = frozenset({"train", "val", "unmodeled_val"})
MIXED_AGE_EVERY = 2
CHUNK = 50
log = logging.getLogger("differential.sim")


def circuit_index(circuit_id: str) -> int:
    return CIRCUIT_IDS.index(circuit_id)


def draw_rng(circuit_id: str, split: str, hyp_index: int, draw: int) -> np.random.Generator:
    seq = np.random.SeedSequence(
        [BASE_SEED, circuit_index(circuit_id), SPLIT_INDEX[split], hyp_index, draw]
    )
    return np.random.default_rng(seq)


def seed_label(circuit_id: str, split: str, hyp_index: int, draw: int) -> str:
    return f"{BASE_SEED}-{circuit_index(circuit_id)}-{SPLIT_INDEX[split]}-{hyp_index}-{draw}"


CASE_INDEX_BASE = 100_000  # hyp_index of evaluation case i is CASE_INDEX_BASE + i


@dataclass(frozen=True)
class Job:
    circuit_id: str
    split: str
    hypothesis: str  # fault id, or "+"-joined ids for a multi-fault case
    hyp_index: int
    draws: tuple[int, ...]
    with_thd: bool = True

    @property
    def key(self) -> str:
        base = f"{self.circuit_id}|{self.split}|{self.hypothesis}|{self.draws[0]}-{self.draws[-1]}"
        # Evaluation cases (numbered from CASE_INDEX_BASE by eval/cases.py) can repeat a
        # hypothesis, so their checkpoint key carries the case number; catalog jobs keep the
        # key their checkpoints were written with.
        return base if self.hyp_index < CASE_INDEX_BASE else f"{base}|{self.hyp_index}"


def is_aged(split: str, hyp_index: int, draw: int) -> bool:
    """Whether one draw is an aged unit."""
    return split in AGED_SPLITS or (split in MIXED_AGE_SPLITS
                                    and (hyp_index + draw) % MIXED_AGE_EVERY == 1)


def make_draw(circuit_id: str, split: str, hyp_index: int, hypothesis: str, draw: int) -> Draw:
    """Deterministically construct the parameter draw for one simulation."""
    circuit = get_circuit(circuit_id)
    rng = draw_rng(circuit_id, split, hyp_index, draw)
    d = healthy_draw(circuit, rng, TOL_SCALE.get(split, 1.0))
    if is_aged(split, hyp_index, draw):
        age_draw(circuit, d, rng)
    for fid in hypothesis.split("+"):
        apply_fault(circuit, d, parse_fault_id(fid), rng)
    return d


def _fault_for_structure(hypothesis: str) -> list[Fault]:
    return [parse_fault_id(f) for f in hypothesis.split("+")]


def run_job(job: Job) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Worker entry point: simulate one chunk of draws for one hypothesis."""
    circuit = get_circuit(job.circuit_id)
    faults = _fault_for_structure(job.hypothesis)
    batch_draws = [
        (i, make_draw(job.circuit_id, job.split, job.hyp_index, job.hypothesis, i))
        for i in job.draws
    ]
    target: Fault | list[Fault] = faults[0] if len(faults) == 1 else faults
    result = simulate_draws(circuit, target, batch_draws, with_thd=job.with_thd)
    obs = spice_observables(circuit)
    lifts = lift_observables(circuit)
    rows = []
    for i, d in batch_draws:
        r = result.results[i]
        row: dict[str, Any] = {
            "circuit": job.circuit_id,
            "split": job.split,
            "hypothesis": job.hypothesis,
            "hyp_index": job.hyp_index,
            "draw": i,
            "seed": seed_label(job.circuit_id, job.split, job.hyp_index, i),
            "ok": bool(r.ok),
            "attempt": int(r.attempt),
            "reason": r.reason,
            "fundamental": float(r.fundamental),
            "severity": json.dumps(d.severity, sort_keys=True),
            "aged": "aged" in d.severity,
        }
        for o, v in zip(obs, r.values, strict=True):
            row[o.key] = float(v)
        assert r.open_dc is not None
        for j, o in enumerate(obs):
            if o.kind == "dc":
                row[f"open:{o.tp}"] = float(r.open_dc[j])
        for lo in lifts:
            assert lo.ref is not None
            row[f"liftval:{lo.ref}"] = float(d.lift.get(lo.ref, np.nan))
        rows.append(row)
    return job.key, rows, result.failures


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def catalog_jobs(
    circuit_id: str, split: str, n_draws: int, hypotheses: Sequence[Fault] | None = None
) -> list[Job]:
    circuit = get_circuit(circuit_id)
    catalog = fault_catalog(circuit)
    index = {f.id: i for i, f in enumerate(catalog)}
    faults = list(hypotheses) if hypotheses is not None else catalog
    jobs = []
    for f in faults:
        for start in range(0, n_draws, CHUNK):
            draws = tuple(range(start, min(n_draws, start + CHUNK)))
            jobs.append(Job(circuit_id, split, f.id, index[f.id], draws))
    return jobs


def case_jobs(circuit_id: str, split: str, cases: Sequence[tuple[str, int]]) -> list[Job]:
    """Jobs for individually specified cases: (hypothesis id, case index)."""
    jobs = []
    for hyp, case_idx in cases:
        jobs.append(Job(circuit_id, split, hyp, 100000 + case_idx, (case_idx,)))
    return jobs


def _checkpoint_dir(tag: str) -> Path:
    return SIM_DIR / "parts" / tag


def run_jobs(
    jobs: list[Job],
    tag: str,
    workers: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Run jobs in parallel with resumable checkpoints under data/sim/parts/<tag>/.

    A checkpoint is reused only if it was produced by the same simulation inputs
    (netlists, device library and tolerance code); otherwise it is discarded, so a
    model fix can never be mixed with results simulated before it."""
    ckpt = _checkpoint_dir(tag)
    signature = simulation_signature(sorted({j.circuit_id for j in jobs}))
    sig_path = ckpt / "signature.txt"
    if ckpt.exists() and (not sig_path.exists() or sig_path.read_text().strip() != signature):
        log.info("%s: discarding a checkpoint made with other simulation inputs", tag)
        shutil.rmtree(ckpt)
    ckpt.mkdir(parents=True, exist_ok=True)
    sig_path.write_text(signature + "\n")
    ledger_path = ckpt / "ledger.json"
    done: set[str] = set(json.loads(ledger_path.read_text())) if ledger_path.exists() else set()
    todo = [j for j in jobs if j.key not in done]
    workers = workers or n_workers()
    buffer: list[dict[str, Any]] = []
    fails: list[dict[str, Any]] = []
    part_no = len(list(ckpt.glob("part_*.parquet")))
    completed = len(jobs) - len(todo)

    def flush() -> None:
        nonlocal part_no, buffer
        if buffer:
            pd.DataFrame(buffer).to_parquet(ckpt / f"part_{part_no:05d}.parquet", index=False)
            part_no += 1
            buffer = []
        ledger_path.write_text(json.dumps(sorted(done)))
        if fails:
            with (ckpt / "failures.jsonl").open("a") as fh:
                for f in fails:
                    fh.write(json.dumps(f) + "\n")
            fails.clear()

    t0 = time.time()
    if todo:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_job, j): j for j in todo}
            for fut in as_completed(futures):
                key, rows, failures = fut.result()
                buffer.extend(rows)
                fails.extend(failures)
                done.add(key)
                completed += 1
                if progress:
                    progress(completed, len(jobs))
                if len(buffer) >= 5000:
                    flush()
                if completed % 50 == 0:
                    log.info("%s: %d/%d jobs (%.0fs)", tag, completed, len(jobs), time.time() - t0)
    flush()
    parts = sorted(ckpt.glob("part_*.parquet"))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True) if parts else pd.DataFrame()
    job_keys = {j.key for j in jobs}
    all_fail: list[dict[str, Any]] = []
    fpath = ckpt / "failures.jsonl"
    if fpath.exists():
        all_fail = [json.loads(line) for line in fpath.read_text().splitlines() if line.strip()]
    if not df.empty:
        df = df.sort_values(["hyp_index", "draw"], kind="stable").reset_index(drop=True)
        df = df.drop_duplicates(subset=["hyp_index", "hypothesis", "draw", "split"], keep="last")
    del job_keys
    return df, all_fail


def dataset_path(circuit_id: str, split: str) -> Path:
    return SIM_DIR / f"{circuit_id}__{split}.parquet"


def save_dataset(df: pd.DataFrame, circuit_id: str, split: str) -> Path:
    path = dataset_path(circuit_id, split)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    float_cols = [c for c in out.columns if out[c].dtype == np.float64]
    out[float_cols] = out[float_cols].astype(np.float32)
    out.to_parquet(path, index=False, compression="zstd")
    return path


def load_dataset(circuit_id: str, split: str) -> pd.DataFrame:
    return pd.read_parquet(dataset_path(circuit_id, split))


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _sha256(text: str | bytes) -> str:
    data = text.encode() if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def netlist_hashes() -> dict[str, str]:
    out = {}
    for cid in CIRCUIT_IDS:
        circuit = get_circuit(cid)
        out[cid] = _sha256(fault_netlist(circuit, HEALTHY_FAULT))
    out["devices.lib"] = _sha256(DEVICE_LIBRARY.read_bytes())
    return out


def tolerance_spec_hash() -> str:
    return _sha256(Path(draws_module.__file__).read_bytes())


def simulation_signature(circuit_ids: Sequence[str]) -> str:
    """Hash of everything a simulated row depends on besides its seed."""
    parts = [DEVICE_LIBRARY.read_bytes(), Path(draws_module.__file__).read_bytes(),
             Path(builder_module.__file__).read_bytes(), Path(runner_module.__file__).read_bytes()]
    parts.append(json.dumps({"tol_scale": TOL_SCALE, "aged": sorted(AGED_SPLITS),
                             "mixed_aged": sorted(MIXED_AGE_SPLITS), "every": MIXED_AGE_EVERY,
                             "make_draw": inspect.getsource(make_draw) + inspect.getsource(is_aged)},
                            sort_keys=True).encode())
    parts += [fault_netlist(get_circuit(cid), HEALTHY_FAULT).encode() for cid in circuit_ids]
    return _sha256(b"\x00".join(parts))


def write_manifest(entries: dict[str, Any], path: Path | None = None) -> Path:
    path = path or (SIM_DIR / "manifest.json")
    existing: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}
    existing.setdefault("datasets", {})
    existing["datasets"].update(entries.get("datasets", {}))
    existing.update({k: v for k, v in entries.items() if k != "datasets"})
    existing.update(
        {
            "base_seed": BASE_SEED,
            "split_index": SPLIT_INDEX,
            "seed_scheme": "SeedSequence([base_seed, circuit_index, split_index, "
            "hypothesis_index, draw_index])",
            "ngspice_version": ngspice_version(),
            "netlist_sha256": netlist_hashes(),
            "tolerance_spec_sha256": tolerance_spec_hash(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "git_commit": git_commit(),
            "workers": n_workers(),
            "host_cpus": os.cpu_count(),
        }
    )
    path.write_text(json.dumps(existing, indent=2, sort_keys=True))
    return path


def summarise(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "rows": len(df),
        "hypotheses": int(df["hypothesis"].nunique()) if len(df) else 0,
        "failed_draws": int((~df["ok"]).sum()) if len(df) else 0,
        "retried_draws": int((df["attempt"] > 0).sum()) if len(df) else 0,
    }


def iter_catalog(circuit_id: str) -> Iterable[Fault]:
    return fault_catalog(get_circuit(circuit_id))
