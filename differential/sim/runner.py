"""Run ngspice decks, parse tagged results, and retry convergence failures.

Every draw is simulated; a draw that still fails after the escalating retry
ladder (default -> more Newton iterations + gmin/source stepping -> relaxed
tolerances, Gear integration and node shunts) is returned with ``ok=False`` and
its failure reason. Callers must count and report failures; nothing is dropped.
"""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from differential.circuits.model import CircuitSpec
from differential.sim.builder import RETRY_OPTIONS, build_deck
from differential.sim.draws import Draw
from differential.sim.faults import Fault

PLOT_PREFIX = {"op": "op", "ac": "ac", "ac20": "ac", "ac20k": "ac", "hum": "ac", "thd": "tran"}
FAIL_PATTERNS = re.compile(
    r"(simulation\(s\) aborted|DC solution failed|Timestep too small|singular matrix|"
    r"doAnalyses|no convergence|Error:)",
    re.IGNORECASE,
)
THD_RE = re.compile(r"THD:\s*([0-9.eE+-]+)\s*%")
HARM_RE = re.compile(r"^\s*1\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+")


@dataclass
class DrawResult:
    draw_id: int
    values: np.ndarray  # SPICE observables, NaN where missing
    fundamental: float = math.nan  # output fundamental amplitude (V peak) from Fourier
    ok: bool = False
    attempt: int = 0
    reason: str = ""


@dataclass
class BatchResult:
    results: dict[int, DrawResult] = field(default_factory=dict)
    failures: list[dict[str, object]] = field(default_factory=list)


def ngspice_version() -> str:
    try:
        out = subprocess.run(["ngspice", "-v"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    for line in (out.stdout + out.stderr).splitlines():
        if "ngspice-" in line:
            m = re.search(r"ngspice-\S+", line)
            if m:
                return m.group(0).rstrip(":")
    return "unknown"


def _run_ngspice(deck_text: str, timeout: float) -> tuple[str, bool]:
    with tempfile.TemporaryDirectory(prefix="diffsim_") as tmp:
        path = Path(tmp) / "deck.cir"
        path.write_text(deck_text)
        try:
            proc = subprocess.run(
                ["ngspice", "-b", str(path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp,
            )
            return proc.stdout + "\n" + proc.stderr, False
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(
                "utf-8", "replace"
            )
            return partial, True


def parse_output(
    text: str, n_obs: int, draw_ids: tuple[int, ...], expected: dict[str, list[int]]
) -> dict[int, DrawResult]:
    """Parse tagged ngspice output into per-draw results.

    ``expected`` maps analysis tag -> observable indices that tag must produce.
    """
    results = {d: DrawResult(d, np.full(n_obs, np.nan)) for d in draw_ids}
    seen: dict[int, set[str]] = {d: set() for d in draw_ids}
    problems: dict[int, list[str]] = {d: [] for d in draw_ids}
    current: tuple[int, str] | None = None
    block: list[str] = []

    def close_block() -> None:
        if current is None:
            return
        did, tag = current
        body = "\n".join(block)
        m = FAIL_PATTERNS.search(body)
        if m:
            problems[did].append(f"{tag}: {m.group(0)}")
        if tag == "thd":
            thd = THD_RE.search(body)
            harm = None
            for line in block:
                hm = HARM_RE.match(line)
                if hm:
                    harm = hm
                    break
            idx = expected.get("thd", [None])[0]
            if thd and harm and idx is not None:
                results[did].values[idx] = float(thd.group(1))
                results[did].fundamental = float(harm.group(2))
            else:
                problems[did].append("thd: no Fourier result")

    for line in text.splitlines():
        if line.startswith("@@B "):
            close_block()
            parts = line.split()
            current = (int(parts[1]), parts[2])
            block = []
            continue
        if line.startswith("@@E "):
            close_block()
            current = None
            block = []
            continue
        if line.startswith("@@P "):
            parts = line.split()
            did, tag = int(parts[1]), parts[2]
            plot = parts[3] if len(parts) > 3 else ""
            if not plot.startswith(PLOT_PREFIX[tag]):
                problems[did].append(f"{tag}: wrong plot {plot or '(none)'}")
            seen[did].add(tag)
            continue
        if line.startswith("@@V "):
            parts = line.split()
            did = int(parts[1])
            for item in parts[3:]:
                if "=" not in item:
                    continue
                k, v = item.split("=", 1)
                try:
                    results[did].values[int(k)] = float(v)
                except ValueError:
                    problems[did].append(f"unparseable value {item}")
            continue
        if current is not None:
            block.append(line)
    close_block()

    for did, res in results.items():
        missing_tags = [t for t in expected if t not in seen[did]]
        missing_vals = [
            i for idxs in expected.values() for i in idxs if not math.isfinite(res.values[i])
        ]
        if missing_tags:
            problems[did].append("missing analyses: " + ",".join(missing_tags))
        if missing_vals:
            problems[did].append(f"{len(missing_vals)} missing values")
        res.ok = not problems[did]
        res.reason = "; ".join(problems[did])[:500]
    return results


def simulate_draws(
    circuit: CircuitSpec,
    fault: Fault | Sequence[Fault],
    draws: list[tuple[int, Draw]],
    with_thd: bool = True,
    base_timeout: float = 120.0,
) -> BatchResult:
    """Simulate a batch of draws for one hypothesis with the retry ladder."""
    batch = BatchResult()
    pending = list(draws)
    for attempt in range(len(RETRY_OPTIONS)):
        if not pending:
            break
        # First attempt runs the whole batch; retries run draws one at a time.
        groups = [pending] if attempt == 0 else [[d] for d in pending]
        next_pending: list[tuple[int, Draw]] = []
        for group in groups:
            deck = build_deck(circuit, fault, group, retry=attempt, with_thd=with_thd)
            expected: dict[str, list[int]] = {}
            for i, o in enumerate(deck.observables):
                tag = "op" if o.kind == "dc" else o.kind
                if o.kind == "thd" and not with_thd:
                    continue
                expected.setdefault(tag, []).append(i)
            timeout = base_timeout + 1.5 * len(group)
            text, timed_out = _run_ngspice(deck.text, timeout)
            parsed = parse_output(text, len(deck.observables), deck.draw_ids, expected)
            for did, draw in group:
                res = parsed[did]
                res.attempt = attempt
                if timed_out and not res.ok:
                    res.reason = (res.reason + "; timeout").strip("; ")
                if res.ok:
                    batch.results[did] = res
                else:
                    batch.results[did] = res
                    next_pending.append((did, draw))
        pending = next_pending
    hyp_id = fault.id if isinstance(fault, Fault) else "+".join(f.id for f in fault)
    for did, _ in pending:
        res = batch.results[did]
        batch.failures.append(
            {
                "circuit": circuit.id,
                "hypothesis": hyp_id,
                "draw": did,
                "reason": res.reason,
            }
        )
    return batch
