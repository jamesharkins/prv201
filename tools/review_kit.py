"""Build the reading kit for one review round of a milestone (grading loop, docs/GRADING_LOG.md).

The kit holds only what the course's reader would see: the anonymised text, an
image of every page, the milestone description, the rubric and the syllabus
notes, plus the text split by signed part for the part audit.

Usage: python tools/review_kit.py M1 OUT_DIR
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PART = re.compile(r"^\s*Part (\d) [—-] ", re.M)
BACK = re.compile(r"^References\s*$", re.M)


def rubric_section(ms: str) -> str:
    """Preamble plus the milestone's table from the rubric in force."""
    official = sorted((ROOT / "course").glob("*rubric*"))
    text = (official[0] if official else ROOT / "rubric" / "derived_rubric.md").read_text()
    head = text.split("\n## ", 1)[0]
    m = re.search(rf"^## {ms}\b.*?(?=^## |\Z)", text, re.M | re.S)
    return head.strip() + "\n\n" + (m.group(0).strip() if m else text) + "\n"


def assignment_section(ms: str) -> str:
    text = (ROOT / "rubric" / "assignments.md").read_text()
    intro = text.split("### M1", 1)[0]
    m = re.search(rf"^### {ms} .*?(?=^### |\Z)", text, re.M | re.S)
    return intro.strip() + "\n\n" + (m.group(0).strip() if m else "") + "\n"


def split_parts(text: str) -> dict[str, str]:
    starts = [(int(m.group(1)), m.start()) for m in PART.finditer(text)]
    back = BACK.search(text)
    end_all = back.start() if back else len(text)
    out = {"front_and_back.txt": text[: starts[0][1]] if starts else text}
    for i, (n, s) in enumerate(starts):
        e = starts[i + 1][1] if i + 1 < len(starts) else end_all
        out[f"part{n}.txt"] = text[s:e]
    out["front_and_back.txt"] += "\n[...parts omitted...]\n\n" + text[end_all:]
    return out


def main(argv: list[str]) -> int:
    ms, out = argv[1], Path(argv[2])
    sub = ROOT / "submissions" / ms
    pdf, txt = sub / f"{ms}.pdf", sub / f"{ms}.sanitized.txt"
    if not txt.exists() or txt.stat().st_mtime < pdf.stat().st_mtime:
        subprocess.run([sys.executable, str(ROOT / "tools" / "sanitize_preview.py"), str(pdf)],
                       check=True)
    if out.exists():
        shutil.rmtree(out)
    (out / "pages").mkdir(parents=True)
    (out / "parts").mkdir()
    text = txt.read_text()
    (out / "submission.txt").write_text(text)
    subprocess.run(["pdftoppm", "-r", "110", "-png", str(pdf), str(out / "pages" / "page")],
                   check=True)
    (out / "rubric.md").write_text(rubric_section(ms))
    (out / "assignment.md").write_text(assignment_section(ms))
    shutil.copy(ROOT / "course" / "SYLLABUS_NOTES.md", out / "syllabus_notes.md")
    for name, body in split_parts(text).items():
        (out / "parts" / name).write_text(body)
    print(f"kit for {ms}: {out} ({len(list((out / 'pages').glob('*.png')))} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
