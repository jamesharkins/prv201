"""Fail when a rendered document contains a number that does not trace to evidence.

A number is accepted if it appears (in any common formatting) in:
  1. results/*.json (metrics, targets, hand calculations, pilot) - measured or locked
  2. docs/research/sources_*.yaml quotes/claims/titles - cited external facts
  3. circuits/*.yaml and *.cir - design constants (component values, ratings)
  4. the allowlist below (years, small counts, section/figure numbers, identifiers)
The reference list is excluded (it holds dates, volumes and DOIs).

Usage: python tools/check_claims.py submissions/M1/M1.pdf [more.pdf ...]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
NUM_RE = re.compile(r"(?<![\w.\-/])[-−]?\d[\d,]*(?:\.\d+)?(?![\w])")
ALLOW_SMALL_INT = set(range(0, 13))
YEAR_RE = re.compile(r"^(19[5-9]\d|20[0-3]\d)$")
BANNED = [
    "delve", "tapestry", "in today's rapidly evolving landscape", "it's important to note",
    "it is important to note", "game-changer", "game changer", "revolutionize",
    "revolutionise", "seamless",
]


def _variants(x: float) -> set[str]:
    out: set[str] = set()
    for v in (x, x * 100.0):
        if abs(v) > 1e9:
            continue
        for d in range(0, 4):
            s = f"{v:.{d}f}"
            out.add(s)
            out.add(f"{v:,.{d}f}")
            if "." in s:
                out.add(s.rstrip("0").rstrip("."))
        out.add(f"{v:g}")
    # engineering values: 2200e-6 -> 2200 (uF), 1e5 -> 100 (k)
    for scale in (1e-12, 1e-9, 1e-6, 1e-3, 1e3, 1e6):
        s = x / scale
        if 0.001 <= abs(s) < 100000:
            out.add(f"{s:g}")
            out.add(f"{s:.0f}")
            out.add(f"{s:.1f}")
    return {v.replace("-", "") for v in out}


def _walk_numbers(obj: Any, acc: set[str]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        acc |= _variants(float(obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk_numbers(v, acc)
            if isinstance(k, str):
                _text_numbers(k, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_numbers(v, acc)
    elif isinstance(obj, str):
        _text_numbers(obj, acc)


def _text_numbers(text: str, acc: set[str]) -> None:
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        tok = m.group(0)
        acc.add(tok)
        acc.add(tok.replace(",", ""))
        try:
            acc |= _variants(float(tok.replace(",", "")))
        except ValueError:
            pass


def known_numbers() -> set[str]:
    acc: set[str] = set()
    for p in (ROOT / "results").glob("*.json"):
        _walk_numbers(json.loads(p.read_text()), acc)
    for p in (ROOT / "docs" / "research").glob("sources_*.yaml"):
        for e in yaml.safe_load(p.read_text()) or []:
            for c in e.get("claims", []):
                _text_numbers(str(c.get("claim", "")), acc)
                _text_numbers(str(c.get("quote", "")), acc)
            _text_numbers(str(e.get("title", "")), acc)
    for p in list((ROOT / "circuits").rglob("*.yaml")) + list((ROOT / "circuits").rglob("*.cir")):
        _text_numbers(p.read_text(), acc)
    return {a.replace(",", "") for a in acc} | acc


def pdf_text(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True,
                          text=True, check=True).stdout


def body_text(text: str) -> str:
    # Drop the reference list (IEEE entries) - everything after the last "References" heading
    # up to an appendix heading, if any.
    m = list(re.finditer(r"^\s*References\s*$", text, flags=re.M))
    if not m:
        return text
    start = m[-1].start()
    tail = text[start:]
    app = re.search(r"^\s*Appendix", tail, flags=re.M)
    return text[:start] + (tail[app.start():] if app else "")


def check(pdf: Path, known: set[str]) -> tuple[list[str], list[str]]:
    text = body_text(pdf_text(pdf))
    bad: list[str] = []
    for line in text.splitlines():
        for m in NUM_RE.finditer(line):
            tok = m.group(0).replace("−", "-").lstrip("-")
            plain = tok.replace(",", "")
            if YEAR_RE.match(plain):
                continue
            try:
                val = float(plain)
            except ValueError:
                continue
            if val.is_integer() and int(val) in ALLOW_SMALL_INT:
                continue
            if plain in known or tok in known:
                continue
            bad.append(f"{tok!r} in: {line.strip()[:110]}")
    low = text.lower()
    style = [p for p in BANNED if p in low]
    return bad, style


def main(argv: list[str]) -> int:
    known = known_numbers()
    rc = 0
    for arg in argv:
        bad, style = check(Path(arg), known)
        print(f"{arg}: {len(bad)} untraceable number(s), {len(style)} banned phrase(s)")
        for b in bad:
            print("   NUMBER", b)
        for s in style:
            print("   STYLE ", s)
        if bad or style:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
