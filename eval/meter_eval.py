"""Meter-photo reading accuracy (target T19): offline reader now, Claude vision when live.

Protocol. A reading is an exact match when the display text (normalised, e.g.
"0L" = "OL"), the unit and the mode all equal the label; "no answer" (the reader
returns None or raises) counts as wrong. Reported per difficulty level, with a
bootstrap 95 % CI, the no-answer and wrong-answer rates and a confusion summary.

Sets:
  * ``data/meter_photos/synthetic``: the rendered set (regenerated with the
    default seed when missing). The offline reader was developed on this set.
  * a pilot set rendered on the fly with seed 20261001, never used during
    development but scored before the targets were locked (reported, not judged);
  * the test set for T19, rendered on the fly with seed 20261028 and scored only
    once the git tag ``targets-locked`` exists (``eval/lock.py``);
  * ``data/meter_photos/real``: evaluated when it contains a ``labels.jsonl``
    (lines {"file", "value_text", "unit", "mode"}).

Claude vision needs ``DIFFERENTIAL_API_KEY``; without a live client its accuracy
is reported as pending, never estimated.

    python -m eval.meter_eval [--regenerate] [--n 300] [--limit N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from differential.config import METER_DIR, REPO_ROOT
from differential.vision.meter_read import MeterReading, read_llm, read_offline
from differential.vision.meter_render import (
    DEFAULT_SEED,
    DIFFICULTIES,
    SYNTHETIC_DIR,
    generate_dataset,
    normalize_value_text,
)
from eval import metrics_io
from eval.lock import targets_locked
from eval.stats import bootstrap_mean

REAL_DIR = METER_DIR / "real"
PENDING = {"status": "pending (requires DIFFERENTIAL_API_KEY)"}
# Seeds of the synthetic sets looked at while the offline reader was developed; the
# held-out seed below was not used until the final evaluation.
DEVELOPMENT_SEEDS = (DEFAULT_SEED, 7, DEFAULT_SEED + 1)
PILOT_SEED = 20261001  # scored before the lock (was called the held-out set)
TEST_SEED = 20261028  # scored only after the lock
MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".webp": "image/webp", ".gif": "image/gif"}
Reader = Callable[[bytes, str], MeterReading | None]


def load_labels(root: Path) -> list[dict[str, Any]]:
    lines = (root / "labels.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def exact_match(reading: MeterReading | None, label: dict[str, Any]) -> bool:
    return (reading is not None
            and normalize_value_text(reading.text) == normalize_value_text(label["value_text"])
            and reading.unit == label["unit"] and reading.mode == label["mode"])


def run_reader(reader: Reader, root: Path, labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for lab in labels:
        path = root / lab["file"]
        data = path.read_bytes()
        t0 = time.perf_counter()
        error = None
        try:
            reading = reader(data, MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg"))
        except Exception as exc:  # a reader failure is scored as no answer
            reading, error = None, f"{type(exc).__name__}: {exc}"[:200]
        rows.append({"label": lab, "reading": reading, "error": error,
                     "seconds": time.perf_counter() - t0, "correct": exact_match(reading, lab)})
    return rows


def _rate(flags: list[bool]) -> float | None:
    return float(np.mean(flags)) if flags else None


def _char_confusions(truth: str, pred: str) -> list[str]:
    """Position-wise character substitutions when the two texts have the same layout."""
    t, p = normalize_value_text(truth), normalize_value_text(pred)
    if len(t) != len(p):
        return []
    return [f"{a}->{b}" for a, b in zip(t, p, strict=True) if a != b]


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    correct = [r["correct"] for r in rows]
    answered = [r for r in rows if r["reading"] is not None]
    est = bootstrap_mean(np.array(correct, float))
    per_level: dict[str, Any] = {}
    present = {r["label"].get("difficulty", "real") for r in rows}
    for level in [d for d in (*DIFFICULTIES, "real") if d in present]:
        sub = [r for r in rows if r["label"].get("difficulty", "real") == level]
        per_level[level] = {"n": len(sub), "exact_match": _rate([r["correct"] for r in sub]),
                            "no_answer_rate": _rate([r["reading"] is None for r in sub])}
    per_mode: dict[str, Any] = {}
    for key in sorted({f"{r['label']['mode']} {r['label']['unit']}" for r in rows}):
        sub = [r for r in rows if f"{r['label']['mode']} {r['label']['unit']}" == key]
        per_mode[key] = {"n": len(sub), "exact_match": _rate([r["correct"] for r in sub])}
    overload = [r for r in rows if normalize_value_text(r["label"]["value_text"]) == "OL"]

    errors: Counter[str] = Counter()
    chars: Counter[str] = Counter()
    units: Counter[str] = Counter()
    modes: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    for r in rows:
        lab, rd = r["label"], r["reading"]
        if r["correct"]:
            continue
        if rd is None:
            errors["no_answer"] += 1
        else:
            if normalize_value_text(rd.text) != normalize_value_text(lab["value_text"]):
                errors["value_text"] += 1
                chars.update(_char_confusions(lab["value_text"], rd.text) or ["text length/layout"])
            if rd.unit != lab["unit"]:
                errors["unit"] += 1
                units[f"{lab['unit']}->{rd.unit}"] += 1
            if rd.mode != lab["mode"]:
                errors["mode"] += 1
                modes[f"{lab['mode']}->{rd.mode}"] += 1
        if len(examples) < 12:
            examples.append({
                "file": lab["file"], "difficulty": lab.get("difficulty", "real"),
                "truth": f"{lab['value_text']} {lab['unit']} {lab['mode']}",
                "read": None if rd is None else f"{rd.text} {rd.unit} {rd.mode}",
                "confidence": None if rd is None else round(rd.confidence, 3),
                "error": r["error"],
            })
    conf_ok = [r["reading"].confidence for r in answered if r["correct"]]
    conf_bad = [r["reading"].confidence for r in answered if not r["correct"]]
    confident = [r for r in answered if r["reading"].confidence >= 0.9]
    secs = np.array([r["seconds"] for r in rows])
    return {
        "n": len(rows),
        "exact_match": est.value,
        "exact_match_ci95": [est.lo, est.hi],
        "correct": int(sum(correct)),
        "no_answer_rate": _rate([r["reading"] is None for r in rows]),
        "wrong_answer_rate": len([r for r in answered if not r["correct"]]) / len(rows) if rows else None,
        "accuracy_when_answered": _rate([r["correct"] for r in answered]),
        "per_difficulty": per_level,
        "per_mode_unit": per_mode,
        "overload": {"n": len(overload), "exact_match": _rate([r["correct"] for r in overload])},
        "confidence": {
            "mean_when_correct": float(np.mean(conf_ok)) if conf_ok else None,
            "mean_when_wrong": float(np.mean(conf_bad)) if conf_bad else None,
            "coverage_at_0.9": len(confident) / len(rows) if rows else None,
            "accuracy_at_0.9": _rate([r["correct"] for r in confident]),
        },
        "confusion": {
            "error_parts": dict(errors),
            "characters": dict(chars.most_common()),
            "units": dict(units.most_common()),
            "modes": dict(modes.most_common()),
            "examples": examples,
        },
        "seconds_per_image": {"mean": float(secs.mean()) if len(secs) else None,
                              "p95": float(np.percentile(secs, 95)) if len(secs) else None},
    }


def describe(labels: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    digest = hashlib.sha256((root / "labels.jsonl").read_bytes()).hexdigest()
    where = str(root.relative_to(REPO_ROOT)) if root.is_relative_to(REPO_ROOT) else "(rendered, not saved)"
    return {"path": where, "n": len(labels),
            "difficulty": dict(Counter(lab.get("difficulty", "real") for lab in labels)),
            "labels_sha256": digest}


def offline_reader(data: bytes, media_type: str) -> MeterReading | None:
    del media_type
    return read_offline(data)


def claude_reader(client: Any) -> Reader:
    def read(data: bytes, media_type: str) -> MeterReading | None:
        return read_llm(data, media_type, client)
    return read


def _live_client() -> Any | None:
    from differential.agent.llm import LLMClient

    client = LLMClient()
    return client if client.live else None


def evaluate_set(root: Path, labels: list[dict[str, Any]], client: Any | None) -> dict[str, Any]:
    out: dict[str, Any] = {"dataset": describe(labels, root),
                           "offline": summarise(run_reader(offline_reader, root, labels))}
    if client is None:
        out["claude"] = dict(PENDING)
    else:
        calls0 = client.usage.calls
        out["claude"] = summarise(run_reader(claude_reader(client), root, labels))
        out["claude"]["model"] = client.model
        out["claude"]["api_calls"] = client.usage.calls - calls0
        out["claude"]["cost_usd_total_session"] = client.usage.cost_usd(client.model)
    return out


def _fmt(x: float | None) -> str:
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.1f} %"


def print_summary(name: str, result: dict[str, Any]) -> None:
    for reader in ("offline", "claude"):
        s = result[reader]
        if "status" in s:
            print(f"{name:>18} | {reader:<7} | {s['status']}")
            continue
        levels = ", ".join(f"{k} {_fmt(v['exact_match'])} (n={v['n']})"
                           for k, v in s["per_difficulty"].items())
        print(f"{name:>18} | {reader:<7} | exact match {_fmt(s['exact_match'])} "
              f"[{_fmt(s['exact_match_ci95'][0])}, {_fmt(s['exact_match_ci95'][1])}] of {s['n']}; "
              f"no answer {_fmt(s['no_answer_rate'])}, wrong {_fmt(s['wrong_answer_rate'])}")
        print(f"{'':>18} | {'':<7} | {levels}; {1000 * s['seconds_per_image']['mean']:.0f} ms/image")
        conf = s["confusion"]
        if conf["error_parts"]:
            print(f"{'':>18} | {'':<7} | errors {conf['error_parts']} chars {conf['characters']} "
                  f"units {conf['units']} modes {conf['modes']}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--regenerate", action="store_true", help="re-render data/meter_photos/synthetic")
    ap.add_argument("--n", type=int, default=300, help="photos per rendered set (0 = skip)")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N photos per set")
    args = ap.parse_args(argv)

    if args.regenerate or not (SYNTHETIC_DIR / "labels.jsonl").exists():
        print(f"rendering the synthetic set into {SYNTHETIC_DIR} ...", flush=True)
        generate_dataset(300, SYNTHETIC_DIR, DEFAULT_SEED)
    client = _live_client()
    labels = load_labels(SYNTHETIC_DIR)[: args.limit]
    results: dict[str, Any] = {"synthetic": evaluate_set(SYNTHETIC_DIR, labels, client)}
    results["synthetic"]["dataset"]["seed"] = DEFAULT_SEED
    print_summary("synthetic", results["synthetic"])

    rendered = [("synthetic_pilot", PILOT_SEED)]
    if targets_locked():
        rendered.append(("synthetic_test", TEST_SEED))
    for name, seed in rendered if args.n > 0 else []:
        with tempfile.TemporaryDirectory() as tmp:
            photos = generate_dataset(args.n, Path(tmp), seed)[: args.limit]
            results[name] = evaluate_set(Path(tmp), photos, client)
        results[name]["dataset"]["seed"] = seed
        print_summary(name.replace("_", " "), results[name])

    if (REAL_DIR / "labels.jsonl").exists():
        real = load_labels(REAL_DIR)[: args.limit]
        results["real"] = evaluate_set(REAL_DIR, real, client)
        print_summary("real", results["real"])
    else:
        missing = (REAL_DIR / "labels.jsonl").relative_to(REPO_ROOT)
        results["real"] = {"status": f"no labelled real photos ({missing} not present)"}
        print(f"{'real':>18} | {results['real']['status']}")

    test = results.get("synthetic_test")
    results["target"] = {"id": "T19", "offline": 0.90, "claude": 0.95, "judged_on": "synthetic_test",
                         "offline_met": None if test is None else
                         bool(test["offline"]["exact_match"] >= 0.90),
                         "claude_met": None if test is None or client is None else
                         bool(test["claude"]["exact_match"] >= 0.95)}
    results["protocol"] = ("exact match = normalised display text, unit and mode all correct; no answer "
                           "counts as wrong; 95 % CI from 2000 bootstrap resamples. The offline reader "
                           f"was developed on synthetic sets with seeds {list(DEVELOPMENT_SEEDS)}; the "
                           f"pilot set (seed {PILOT_SEED}) was scored before the targets were locked; "
                           f"T19 is judged on the test set (seed {TEST_SEED}), scored only after the "
                           "lock. Every reading is confirmed by the technician before it is recorded.")
    metrics_io.update("vision", results)
    print(f"wrote section 'vision' to {metrics_io.METRICS}")


if __name__ == "__main__":
    main()
