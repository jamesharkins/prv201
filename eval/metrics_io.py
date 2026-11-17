"""Read/merge/write results/metrics.json (the single source of reported numbers)."""

from __future__ import annotations

import fcntl
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from differential.config import RESULTS_DIR

METRICS = RESULTS_DIR / "metrics.json"


def _clean(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 6)
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if hasattr(obj, "item"):  # numpy scalar
        return _clean(obj.item())
    return obj


def load() -> dict[str, Any]:
    return json.loads(METRICS.read_text()) if METRICS.exists() else {}


def update(section: str, data: dict[str, Any], path: Path | None = None) -> None:
    """Replace one top-level section atomically (other sections are untouched)."""
    path = path or METRICS
    path.parent.mkdir(parents=True, exist_ok=True)
    # Evaluations may run in parallel: the read-modify-write holds an exclusive lock so
    # one run's section is never lost to another's.
    with open(path.with_name(path.name + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = json.loads(path.read_text()) if path.exists() else {}
        current[section] = _clean(data)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(current, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
