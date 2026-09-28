"""Signed-part balance checker (brief §3).

For every part of a rendered milestone (.typ source), checks:
  * length within +-20 % of the mean part length (words of prose),
  * at least one design decision (#decision block),
  * at least one figure or table,
  * original analysis: at least one number drawn from results (the renderer
    records metric use per part in <doc>.parts.json).
Usage: python tools/check_balance.py submissions/M1/M1.typ [...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PART_RE = re.compile(r"^#part\((\d+),", flags=re.M)


def _remove_calls(text: str, names: tuple[str, ...]) -> str:
    """Remove #name(...) calls, matching nested (), [] and "..." properly."""
    out = []
    i = 0
    while i < len(text):
        hit = next((n for n in names if text.startswith(f"#{n}(", i)), None)
        if hit is None:
            out.append(text[i])
            i += 1
            continue
        j = i + len(hit) + 2
        depth, in_str = 1, False
        while j < len(text) and depth:
            ch = text[j]
            if in_str:
                if ch == "\\":
                    j += 1
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            j += 1
        # a trailing content block, e.g. #decision(..)[...], is kept (it is prose)
        i = j
    return "".join(out)


def strip_typst(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    text = _remove_calls(text, ("figure", "image", "table"))
    text = re.sub(r"#[a-zA-Z_.-]+", " ", text)
    text = re.sub(r"[\[\]{}()*_=<>@$\\]", " ", text)
    return text


def parts(typ: str) -> dict[int, str]:
    starts = [(int(m.group(1)), m.start()) for m in PART_RE.finditer(typ)]
    end_marker = typ.find("// END-PARTS")
    out = {}
    for i, (n, s) in enumerate(starts):
        e = starts[i + 1][1] if i + 1 < len(starts) else (end_marker if end_marker > 0 else len(typ))
        out[n] = typ[s:e]
    return out


def check(path: Path) -> list[str]:
    typ = path.read_text()
    ps = parts(typ)
    if not ps:
        return [f"{path.name}: no #part() sections found"]
    words = {n: len(strip_typst(t).split()) for n, t in ps.items()}
    mean = sum(words.values()) / len(words)
    meta_path = path.with_suffix(".parts.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    problems = []
    for n, t in ps.items():
        dev = (words[n] - mean) / mean
        if abs(dev) > 0.20:
            problems.append(f"part {n}: {words[n]} words, {100 * dev:+.0f} % vs mean {mean:.0f}")
        if "#decision(" not in t:
            problems.append(f"part {n}: no design decision block")
        if "#figure(" not in t and "table(" not in t:
            problems.append(f"part {n}: no figure or table")
        used = meta.get(str(n), {}).get("metrics", 0)
        if used < 1:
            problems.append(f"part {n}: no result-derived number (original analysis)")
    summary = ", ".join(f"P{n}={w}" for n, w in sorted(words.items()))
    print(f"{path.name}: words {summary} (mean {mean:.0f})")
    return problems


def main(argv: list[str]) -> int:
    rc = 0
    for a in argv:
        probs = check(Path(a))
        for p in probs:
            print("   ", p)
        rc |= 1 if probs else 0
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
