"""Shared helpers for rendering milestone documents (Jinja -> Typst -> PDF).

Every number that appears in a document must come from one of:
  * results/metrics.json      (measured results, via ``m()``)
  * results/targets.json      (the locked success criteria, via ``target()``)
  * docs/research/sources_*.yaml claim/quote text (external facts, cited)
  * design constants in circuits/*.yaml and *.cir (component values)
  * the explicit allowlist in tools/check_claims.py (years, counts of parts, ...)
tools/check_claims.py enforces this on the rendered text.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "docs" / "research"
RESULTS = ROOT / "results"
MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.",
          "Nov.", "Dec."]


# ---------------------------------------------------------------------------
# Bibliography
# ---------------------------------------------------------------------------


PERSONAL_NAME_TYPES = ("paper", "article", "book")
MIRROR_HOSTS = ("github.com", "raw.githubusercontent.com")


def load_bibliography(canonical: bool = True) -> dict[str, dict[str, Any]]:
    """Merge docs/research/sources_*.yaml; apply citation_overrides.yaml if ``canonical``.

    The source files record how each claim was verified (``url`` is the page that
    was read, sometimes a mirror). The override layer supplies the canonical form
    used in reference lists. ``_source_url`` always keeps the verification URL.
    """
    bib: dict[str, dict[str, Any]] = {}
    for path in sorted(RESEARCH.glob("sources_*.yaml")):
        entries = yaml.safe_load(path.read_text()) or []
        for e in entries:
            key = e["key"]
            if key in bib:
                raise ValueError(f"duplicate source key {key} in {path.name}")
            e["_file"] = path.name
            e["_source_url"] = e.get("url")
            bib[key] = e
    if canonical:
        overrides_path = RESEARCH / "citation_overrides.yaml"
        overrides = yaml.safe_load(overrides_path.read_text()) if overrides_path.exists() else {}
        for key, fields in (overrides or {}).items():
            if key not in bib:
                raise KeyError(f"citation_overrides.yaml: unknown key {key}")
            e = bib[key]
            if "url" in fields and fields["url"] != e.get("url"):
                # a substituted canonical URL was not itself opened: no access date
                e.pop("accessed", None)
            e.update(fields)
            e["_override"] = True
    return bib


def is_mirror(entry: dict[str, Any]) -> bool:
    """True when the reference would point at a verification mirror, not the source."""
    url = entry.get("url")
    if entry.get("doi") or not url or entry.get("url_is_canonical"):
        return False
    return any(f"//{h}/" in str(url) for h in MIRROR_HOSTS)


def _escape_typst(text: str) -> str:
    out = str(text)
    for ch in ("\\", "#", "$", "*", "_", "@", "<", ">", "`", "[", "]"):
        out = out.replace(ch, "\\" + ch)
    return out


NAME_PARTICLES = {"de", "van", "von", "der", "den", "da", "di", "del", "du", "le", "la"}


def _abbreviate(name: str) -> str:
    """'Dennis V. Lindley' -> 'D. V. Lindley'; 'J. de Kleer' stays; orgs are not passed here."""
    tokens = name.split()
    cut = next((i for i, t in enumerate(tokens) if t in NAME_PARTICLES and i > 0), len(tokens) - 1)
    given, surname = tokens[:cut], tokens[cut:]
    initials = [
        t if t.endswith(".") else "-".join(q[0] + "." for q in t.split("-") if q)
        for t in given
        if t[0].isalpha()
    ]
    return " ".join(initials + surname)


def _author_list(authors: list[str], personal: bool = True) -> str:
    """IEEE author list. Personal names are reduced to initials; organisations and
    "et al." forms stay as written."""

    def fmt(a: str) -> str:
        if not personal or len(a.split()) < 2 or "(" in a or "et al" in a:
            return a
        return _abbreviate(a)

    names = [fmt(a) for a in authors if a]
    if not names:
        return ""
    if len(names) > 6:
        return names[0] + " et al."
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def _date_text(date: str | None) -> str:
    if not date or date == "n.d.":
        return "n.d."
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", str(date))
    if not m:
        return str(date)
    y, mo, d = m.group(1), m.group(2), m.group(3)
    if mo and d:
        return f"{MONTHS[int(mo) - 1]} {int(d)}, {y}"
    if mo:
        return f"{MONTHS[int(mo) - 1]} {y}"
    return y


def _accessed_text(date: str | None) -> str:
    if not date:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(date))
    if not m:
        return str(date)
    return f"{MONTHS[int(m.group(2)) - 1]} {int(m.group(3))}, {m.group(1)}"


def _dash_ranges(text: str) -> str:
    return re.sub(r"(?<=\d)-(?=\d)", "–", text)


def ieee_reference(e: dict[str, Any]) -> str:
    """Typst markup for one IEEE-style reference entry (without the [n] label)."""
    typ = e.get("type", "web")
    raw_authors = [a for a in (e.get("authors") or []) if a]
    container_raw = (e.get("container") or "").strip()
    publisher_raw = (e.get("publisher") or "").strip()
    # an outlet that is also the only "author" is named once: as the container when
    # there is one, otherwise as the author (and the publisher is not repeated)
    if len(raw_authors) == 1 and raw_authors[0] == container_raw:
        raw_authors = []
    elif len(raw_authors) == 1 and raw_authors[0] == publisher_raw:
        publisher_raw = ""
    personal = typ in PERSONAL_NAME_TYPES or bool(e.get("personal_authors"))
    authors = _author_list(raw_authors, personal=personal)
    title = _escape_typst(e.get("title", ""))
    container = _escape_typst(container_raw)
    publisher = _escape_typst(publisher_raw)
    date = _date_text(e.get("date")).rstrip(".")
    parts: list[str] = []
    if authors:
        parts.append(_escape_typst(authors) + ",")
    if typ in ("paper", "article") and container:
        parts.append(f"“{title},” _{container}_,")
        if e.get("volume"):
            parts.append(_escape_typst(_dash_ranges(str(e["volume"]))) + ",")
        parts.append(f"{date}.")
    elif typ == "book":
        parts.append(f"_{title}_.")
        if publisher:
            parts.append(f"{publisher},")
        parts.append(f"{date}.")
    elif typ == "standard":
        parts.append(f"_{title}_,")
        if container:
            parts.append(f"{container},")
        parts.append(f"{date}.")
    elif typ == "press_release":
        parts.append(f"“{title},”")
        parts.append(f"{container or 'Press release'},")
        if publisher:
            parts.append(f"{publisher},")
        parts.append(f"{date}.")
    else:
        parts.append(f"“{title},”")
        where = container or publisher
        if where:
            parts.append(f"_{where}_,")
        parts.append(f"{date}.")
    if e.get("note"):
        parts.append(_escape_typst(str(e["note"])))
    doi = e.get("doi")
    url = e.get("url")
    if doi:
        parts.append(f"doi: {_escape_typst(doi)}.")
    elif url:
        acc = _accessed_text(e.get("accessed"))
        link = f"#link(\"{url}\")[{_escape_typst(url)}]"
        parts.append(f"[Online]. Available: {link}" + (f" (accessed {acc})." if acc else "."))
    return " ".join(parts)


@dataclass
class Citer:
    bib: dict[str, dict[str, Any]]
    order: list[str] = field(default_factory=list)

    def number(self, key: str) -> int:
        if key not in self.bib:
            raise KeyError(f"unknown citation key: {key}")
        if key not in self.order:
            self.order.append(key)
        return self.order.index(key) + 1

    def cite(self, *keys: str) -> str:
        nums = sorted({self.number(k) for k in keys})
        return "\\[" + ", ".join(str(n) for n in nums) + "\\]"

    def references(self) -> str:
        lines = []
        for i, key in enumerate(self.order, start=1):
            lines.append(f"#ref-entry({i})[{ieee_reference(self.bib[key])}]")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Results, targets, team
# ---------------------------------------------------------------------------


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


class Metrics:
    """Dotted-path accessor over results/metrics.json; missing values fail loudly."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    def get(self, path: str) -> Any:
        cur: Any = self.data
        for part in path.split("."):
            if isinstance(cur, list):
                cur = cur[int(part)]
            elif isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                raise KeyError(f"metric not found: {path}")
        return cur

    def has(self, path: str) -> bool:
        try:
            self.get(path)
            return True
        except (KeyError, IndexError, ValueError):
            return False


def fmt_num(x: float, digits: int = 1) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    return f"{x:,.{digits}f}"


def fmt_pct(x: float, digits: int = 1) -> str:
    """Fraction -> percentage text (0.873 -> '87.3%')."""
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    return f"{100.0 * x:.{digits}f}%"


def load_team() -> list[dict[str, Any]]:
    return list(yaml.safe_load((ROOT / "team.yaml").read_text())["members"])


def typst_str(s: str) -> str:
    return _escape_typst(s)
