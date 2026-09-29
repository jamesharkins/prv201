"""Document build tools: the page check and the renderer's text filters."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tools.check_pages import appendix_after_references, body_pages, floats_after_references
from tools.render_docs import lower_first

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="needs poppler")


def _pdf(tmp_path: Path, body: str) -> Path:
    typst = pytest.importorskip("typst")
    src = tmp_path / "doc.typ"
    src.write_text("#set page(height: 12cm)\n" + body)
    out = tmp_path / "doc.pdf"
    typst.compile(str(src), output=str(out))
    return out


def test_lower_first_keeps_acronyms() -> None:
    assert lower_first("Named first, 500 units") == "named first, 500 units"
    assert lower_first("AUROC of the flag") == "AUROC of the flag"
    assert lower_first("T3 top-3") == "T3 top-3"
    assert lower_first("95th-percentile time") == "95th-percentile time"


def test_float_after_references_is_caught(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path, "Body text.\n\n= References\n[1] A source.\n\n"
                         "#figure(table(columns: 1, [x]), caption: [A stray table.])\n")
    assert floats_after_references(pdf) == ["Table 1"]


def test_appendix_tables_are_allowed(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path, "Body text.\n\n= References\n[1] A source.\n\n= Appendix A\n"
                         "#figure(table(columns: 1, [x]), caption: [An appendix table.])\n")
    assert floats_after_references(pdf) == []
    assert appendix_after_references(pdf)


def test_body_pages_stop_at_references(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path, "Body.\n#pagebreak()\nMore body.\n#pagebreak()\n= References\n[1] A source.\n")
    assert body_pages(pdf) == (2, 3)
