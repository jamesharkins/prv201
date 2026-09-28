"""Check the requirements traceability matrix (docs/requirements.yaml).

Every component and verification path must exist, every target must be defined
in results/targets.json, and every target must be traced by some requirement.
Usage: python tools/check_requirements.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def check() -> list[str]:
    reqs = yaml.safe_load((ROOT / "docs" / "requirements.yaml").read_text())["requirements"]
    targets = {t["id"] for t in json.loads((ROOT / "results" / "targets.json").read_text())["targets"]}
    problems, traced = [], set()
    for r in reqs:
        for path in [*r["components"], *r["verification"]]:
            if not (ROOT / path).exists():
                problems.append(f"{r['id']}: missing path {path}")
        for t in r["targets"]:
            if t not in targets:
                problems.append(f"{r['id']}: unknown target {t}")
            traced.add(t)
    problems += [f"target {t} is traced by no requirement" for t in sorted(targets - traced)]
    return problems


def main() -> int:
    problems = check()
    for p in problems:
        print(p)
    print(f"requirements: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
