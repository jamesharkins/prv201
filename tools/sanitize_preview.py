"""Preview what the course's anonymising step leaves for the LLM reader (brief §5).

Removes every member name from team.yaml and every e-mail address from the
rendered text, writes <doc>.sanitized.txt next to the PDF, and checks that the
part structure ("Part N - Title" headers) is still intact.
Usage: python tools/sanitize_preview.py submissions/M1/M1.pdf [...]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def names() -> list[str]:
    team = yaml.safe_load((ROOT / "team.yaml").read_text())
    out = []
    for m in team["members"]:
        n = str(m.get("name", "")).strip()
        if n:
            out.append(n)
            out += [p for p in n.split() if len(p) > 2]
    return sorted(set(out), key=len, reverse=True)


def sanitize(text: str) -> str:
    text = EMAIL.sub("[email removed]", text)
    for n in names():
        text = re.sub(re.escape(n), "[name removed]", text)
    return text


def main(argv: list[str]) -> int:
    rc = 0
    for a in argv:
        pdf = Path(a)
        raw = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True,
                             text=True, check=True).stdout
        clean = sanitize(raw)
        out = pdf.with_suffix(".sanitized.txt")
        out.write_text(clean)
        headers = re.findall(r"Part (\d+) — ", clean)
        leftover = [n for n in names() if n in clean]
        print(f"{pdf.name}: part headers {sorted(set(headers))}; residual names {leftover}; "
              f"-> {out.relative_to(ROOT)}")
        if leftover:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
