"""Measure the repository's engineering facts for the milestone documents.

Runs the test suite once with coverage and counts code, tests and decision records, so
the numbers a document quotes about the code trace to a results file like every other
number (CLAUDE.md, rule 3). Writes results/engineering.json.

Usage: python tools/engineering_facts.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "engineering.json"


def python_lines(folder: str) -> dict[str, int]:
    files = sorted((ROOT / folder).rglob("*.py"))
    lines = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in files)
    return {"files": len(files), "lines": lines}


def run_tests() -> dict[str, float | int]:
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        cov = Path(tmp) / "coverage.json"
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}",
             "--cov=differential", f"--cov-report=json:{cov}"],
            cwd=ROOT, check=False, capture_output=True, text=True)
        root = ET.parse(junit).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        assert suite is not None
        total = int(suite.get("tests", 0))
        failed = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        skipped = int(suite.get("skipped", 0))
        pct = json.loads(cov.read_text())["totals"]["percent_covered"]
    return {"collected": total, "passed": total - failed - skipped, "failed": failed,
            "skipped": skipped, "line_coverage_pct": round(float(pct), 1)}


def main() -> None:
    decisions = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    facts = {
        "tests": run_tests(),
        "code": {name: python_lines(name) for name in ("differential", "eval", "tools", "tests")},
        "decision_records": len(re.findall(r"^## ADR-\d+", decisions, flags=re.M)),
        "agent_tools": json.loads(subprocess.run(
            [sys.executable, "-c",
             "import json; from differential.agent import tools as t; print(json.dumps("
             "{'all': len(t.TOOL_NAMES), 'model': len(t.MODEL_TOOL_SPECS), "
             "'form_only': len(t.FORM_ONLY_TOOLS)}))"],
            cwd=ROOT, check=True, capture_output=True, text=True).stdout),
    }
    OUT.write_text(json.dumps(facts, indent=1) + "\n")
    print(json.dumps(facts, indent=1))


if __name__ == "__main__":
    main()
