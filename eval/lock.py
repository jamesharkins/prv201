"""The evaluation lock (brief §7): no script may score a test unit, test photo or test
paraphrase before the git tag ``targets-locked`` exists and points at the lock commit."""

from __future__ import annotations

import subprocess

TAG = "targets-locked"
# "Lock the targets (v4): locked_on set; set_bars now refuses to change a bar", 2026-09-29
LOCK_COMMIT = "60cca12d14238dcedeb5f6b5de2e54f45dbbc061"


def targets_locked() -> bool:
    out = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{TAG}^{{commit}}"],
                         capture_output=True, text=True).stdout
    return out.strip() == LOCK_COMMIT


def require_lock(what: str) -> None:
    if not targets_locked():
        raise SystemExit(f"refusing to {what} before the {TAG} tag (it must point at {LOCK_COMMIT[:7]})")
