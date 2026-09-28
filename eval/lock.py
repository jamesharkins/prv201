"""The evaluation lock (brief §7): no script may score a test unit, test photo or test
paraphrase before the git tag ``targets-locked`` exists."""

from __future__ import annotations

import subprocess

TAG = "targets-locked"


def targets_locked() -> bool:
    out = subprocess.run(["git", "tag", "--list", TAG], capture_output=True, text=True).stdout
    return out.strip() == TAG


def require_lock(what: str) -> None:
    if not targets_locked():
        raise SystemExit(f"refusing to {what} before the {TAG} tag")
