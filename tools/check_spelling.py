"""Spelling gate for rendered documents (brief §9 A).

Checks the body text of each rendered PDF (everything before the reference list,
which quotes titles and names verbatim) with hunspell's en_US dictionary plus the
project word list `docs/wordlist.txt`, and with codespell for common typos.
Usage: python tools/check_spelling.py submissions/M1/M1.pdf [...]
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDLIST = ROOT / "docs" / "wordlist.txt"
REFS = re.compile(r"^\s*References\s*$", re.M)
TOKEN = re.compile(r"(?<![\w'’-])[A-Za-z][A-Za-z'’-]*(?![\w'’-])")  # whole tokens without digits


def body_text(pdf: Path) -> str:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True,
                         check=True).stdout  # -layout keeps line-end hyphens
    m = REFS.search(txt)
    body = txt[: m.start()] if m else txt
    appendix = re.search(r"^\s*Appendix\b", txt[m.end():], re.M) if m else None
    if m and appendix:  # appendices after the references are prose too
        body += "\n" + txt[m.end() + appendix.start():]
    body = re.sub(r"https?://\S+|`[^`]*`|\S+\.(?:py|json|yaml|md|csv|pdf|typ)\b", " ", body)
    return _join_line_breaks(body)


def _hunspell_unknown(ws: list[str]) -> set[str]:
    res = subprocess.run(["hunspell", "-d", "en_US", "-l"], input="\n".join(ws), capture_output=True,
                         text=True, check=True).stdout
    return set(res.split())


def _join_line_breaks(text: str) -> str:
    """A word broken at a line end is either typeset hyphenation ("diag-/nosis", joined)
    or a real compound broken at its hyphen ("per-/part", kept)."""
    text = re.sub(r"\u00ad\n\s*", "", text)  # soft hyphen: always typeset hyphenation
    pairs = re.findall(r"([A-Za-z]+)-\n\s*([a-z]+)", text)
    unknown = _hunspell_unknown([a + b for a, b in pairs]) if pairs else set()

    def fix(m: re.Match[str]) -> str:
        a, b = m.group(1), m.group(2)
        return a + b if (a + b) not in unknown else f"{a}-{b}"

    return re.sub(r"([A-Za-z]+)-\n\s*([a-z]+)", fix, text)


def words(text: str, ok: set[str] | None = None) -> list[str]:
    """Words to check: tokens with digits (12AX7, 95th) and all-capital acronyms are
    skipped; a hyphenated compound in the word list counts as one word."""
    ok = ok if ok is not None else allowed()
    out = []
    for tok in TOKEN.findall(text.replace("’", "'")):
        tok = tok.strip("'-")
        if tok.endswith("'s"):
            tok = tok[:-2]
        if "-" in tok and tok.lower() in ok:
            continue
        for part in tok.split("-"):
            part = part.strip("'")
            if len(part) > 1 and not part.isupper():
                out.append(part)
    return out


def allowed() -> set[str]:
    if not WORDLIST.exists():
        return set()
    return {w.strip().lower() for w in WORDLIST.read_text().splitlines() if w.strip() and not w.startswith("#")}


def unknown_words(text: str) -> Counter[str]:
    ok = allowed()
    ws = words(text, ok)
    bad = _hunspell_unknown(ws)
    return Counter(w for w in ws if w in bad and w.lower() not in ok)


def typos(text: str) -> list[str]:
    if shutil.which("codespell") is None:
        return []
    res = subprocess.run(["codespell", "-"], input=text, capture_output=True, text=True)
    return [line.strip() for line in res.stdout.splitlines() if "==>" in line]


def main(argv: list[str]) -> int:
    rc = 0
    for arg in argv:
        pdf = Path(arg)
        text = body_text(pdf)
        bad = unknown_words(text)
        tp = typos(text)
        print(f"{pdf.name}: {len(bad)} unknown word(s), {len(tp)} likely typo(s)")
        for w, n in sorted(bad.items()):
            print(f"    {w} ({n})")
        for t in tp:
            print(f"    typo: {t}")
        rc |= 1 if (bad or tp) else 0
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
