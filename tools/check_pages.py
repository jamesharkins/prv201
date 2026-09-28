"""Enforce page limits (brief §4): body pages before the reference list.

Limits: M1 5, M2 10, M3 12, M5 report 15 (appendices and references excluded).
Usage: python tools/check_pages.py [M1 M2 ...]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIMITS = {"M1": 5, "M2": 10, "M3": 12, "M5": 15}
MAIN_DOC = {"M1": "M1.pdf", "M2": "M2.pdf", "M3": "M3.pdf", "M5": "M5_report.pdf"}


def body_pages(pdf: Path) -> tuple[int, int]:
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, check=True).stdout
    total = int(re.search(r"Pages:\s+(\d+)", info).group(1))  # type: ignore[union-attr]
    for page in range(1, total + 1):
        txt = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(pdf), "-"],
                             capture_output=True, text=True, check=True).stdout
        if re.search(r"^\s*References\s*$", txt, flags=re.M):
            # The page where references start counts as a body page only if body text
            # precedes the heading on that page.
            before = txt.split("References")[0].strip()
            return (page if len(before.split()) > 40 else page - 1), total
    return total, total


def main(argv: list[str]) -> int:
    rc = 0
    for ms in argv or list(LIMITS):
        pdf = ROOT / "submissions" / ms / MAIN_DOC[ms]
        if not pdf.exists():
            print(f"{ms}: {pdf.name} not rendered yet")
            continue
        body, total = body_pages(pdf)
        ok = body <= LIMITS[ms]
        print(f"{ms}: {body} body page(s) (limit {LIMITS[ms]}), {total} total -> {'OK' if ok else 'OVER'}")
        rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
