"""Render milestone documents: Jinja templates -> Typst source -> PDF.

Usage: python tools/render_docs.py M1 [M2 ...] | all

Templates live in templates/<MS>/*.typ.j2 and use custom delimiters so they do
not collide with Typst syntax:
    << expr >>      value            <% stmt %>   control      <# ... #>  comment
Context available in every template:
    cite(*keys)     numbered IEEE citation, e.g. [3]
    references()    the reference list (call once, at the end)
    m(path)         value from results/metrics.json (KeyError if missing)
    has(path)       whether a metric exists
    target(id)      locked target from results/targets.json
    lead(n)         "Section lead" name for part n (from team.yaml)
    pct(x, d), num(x, d)   number formatting
    requirements    the traceability matrix from docs/requirements.yaml
    design          code-derived design constants (results/design.json)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import jinja2
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doclib import (
    RESULTS,
    ROOT,
    Citer,
    Metrics,
    fmt_num,
    fmt_pct,
    load_bibliography,
    load_json,
    load_team,
    typst_str,
)

MILESTONES = ("M1", "M2", "M3", "M4", "M5")


def make_env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")),
        variable_start_string="<<",
        variable_end_string=">>",
        block_start_string="<%",
        block_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


class PartTracker:
    """Records which part is being rendered and what evidence it uses."""

    def __init__(self) -> None:
        self.current = 0
        self.usage: dict[int, dict[str, int]] = {}

    def bump(self, kind: str) -> None:
        u = self.usage.setdefault(self.current, {"metrics": 0, "citations": 0, "targets": 0})
        u[kind] += 1


def context(tracker: PartTracker | None = None) -> dict[str, object]:
    tracker = tracker or PartTracker()
    bib = load_bibliography()
    citer = Citer(bib)
    # A layout dry run may point at a scratch copy; documents are always rendered from the real file.
    metrics = Metrics(load_json(Path(os.environ.get("DIFFERENTIAL_DRYRUN_METRICS", RESULTS / "metrics.json"))))
    targets = load_json(Path(os.environ.get("DIFFERENTIAL_DRYRUN_TARGETS", RESULTS / "targets.json")))
    team = load_team()
    tmap = {t["id"]: t for t in targets.get("targets", [])}

    def lead(n: int) -> str:
        if n - 1 < len(team):
            return str(team[n - 1]["name"])
        return "(unassigned)"

    def target(tid: str) -> dict[str, object]:
        if tid not in tmap:
            raise KeyError(f"unknown target {tid}")
        tracker.bump("targets")
        return tmap[tid]

    def m(path: str) -> object:
        tracker.bump("metrics")
        return metrics.get(path)

    def cite(*keys: str) -> str:
        tracker.bump("citations")
        return citer.cite(*keys)

    def part(n: int, title: str) -> str:
        tracker.current = n
        return f'#part({n}, "{title}", "{lead(n)}")'

    reqs_path = ROOT / "docs" / "requirements.yaml"
    requirements = yaml.safe_load(reqs_path.read_text())["requirements"] if reqs_path.exists() else []

    design_path = RESULTS / "design.json"
    design = load_json(design_path) if design_path.exists() else {}

    return {
        "design": design,
        "requirements": requirements,
        "cite": cite,
        "references": citer.references,
        "part": part,
        "m": m,
        "has": metrics.has,
        "target": target,
        "targets": targets,
        "lead": lead,
        "team": team,
        "n_members": len(team),
        "pct": fmt_pct,
        "num": fmt_num,
        "_citer": citer,
    }


def lower_first(text: str) -> str:
    """Lower-case a leading capital for use mid-sentence, leaving acronyms alone."""
    first = text.split(" ", 1)[0]
    if any(c.isupper() for c in first[1:]) or any(c.isdigit() for c in first):
        return text
    return text[:1].lower() + text[1:]


def render(ms: str) -> Path:
    env = make_env()
    env.filters["esc"] = typst_str
    env.filters["lower_first"] = lower_first
    tpl_dir = ROOT / "templates" / ms
    out_dir = Path(os.environ["DIFFERENTIAL_DRYRUN_OUT"]) / ms if os.environ.get("DIFFERENTIAL_DRYRUN_OUT") else ROOT / "submissions" / ms
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "templates" / "base.typ", out_dir / "base.typ")
    produced = None
    for tpl in sorted(tpl_dir.glob("*.typ.j2")):
        tracker = PartTracker()
        ctx = context(tracker)
        text = env.get_template(f"{ms}/{tpl.name}").render(**ctx)
        out = out_dir / tpl.name.removesuffix(".j2")
        out.write_text(text)
        out.with_suffix(".parts.json").write_text(
            json.dumps({str(k): v for k, v in tracker.usage.items()}, indent=1))
        citer = ctx["_citer"]
        assert isinstance(citer, Citer)
        out.with_suffix(".cites.json").write_text(json.dumps(citer.order, indent=1))
        pdf = out.with_suffix(".pdf")
        import typst

        typst.compile(str(out), output=str(pdf), root=str(ROOT))
        produced = pdf
        print(f"rendered {out.relative_to(ROOT)} -> {pdf.relative_to(ROOT)}")
    if produced is None:
        raise FileNotFoundError(f"no templates in {tpl_dir}")
    for tpl in sorted(tpl_dir.glob("*.md.j2")):  # submission sheets and other Markdown
        text = env.get_template(f"{ms}/{tpl.name}").render(
            **context(), citation_check=load_json(RESULTS / f"citation_check_{ms}.json"))
        (out_dir / tpl.name.removesuffix(".j2")).write_text(text)
        print(f"rendered {(out_dir / tpl.name.removesuffix('.j2')).relative_to(ROOT)}")
    return produced


def main(argv: list[str]) -> int:
    targets = MILESTONES if (not argv or argv == ["all"]) else argv
    for ms in targets:
        if (ROOT / "templates" / ms).exists():
            render(ms)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
