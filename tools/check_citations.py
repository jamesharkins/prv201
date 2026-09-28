"""Check that every cited source URL resolves (brief §5).

Classifies each URL as:
  ok          HTTP 2xx/3xx
  dead        HTTP 404/410 (fails the check)
  site-block  HTTP 401/403/429/5xx from the site itself (bot protection; recheck by hand)
  unreachable the network path refused the connection (e.g. this sandbox's egress
              policy); cannot be decided here - rerun on an unrestricted network
Both the reference-list URL (canonical: DOI or official page) and the URL that was
actually read during verification (``_source_url``, sometimes a mirror) are probed.
A cited entry whose reference would point at a mirror instead of the source fails.
Also lists sources whose support is only a search snippet, for human re-checking.
Usage: python tools/check_citations.py [--used-only submissions/M1/M1.typ ...]
(--used-only reads the <doc>.cites.json list written by tools/render_docs.py)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doclib import ROOT, is_mirror, load_bibliography  # noqa: E402

UA = "Mozilla/5.0 (Differential citation checker; +https://github.com/)"


def probe(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return "ok", str(resp.status)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return "dead", str(e.code)
        return "site-block", str(e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return "unreachable", type(e).__name__ + ": " + str(getattr(e, "reason", e))[:80]


def used_keys(typ_paths: list[Path]) -> list[str]:
    used: list[str] = []
    for p in typ_paths:
        for key in json.loads(p.with_suffix(".cites.json").read_text()):
            if key not in used:
                used.append(key)
    return used


def canonical_url(e: dict[str, object]) -> str | None:
    if e.get("doi"):
        return f"https://doi.org/{e['doi']}"
    url = e.get("url")
    return str(url) if url else None


def main(argv: list[str]) -> int:
    bib = load_bibliography()
    keys = list(bib)
    docs: list[str] = []
    if argv and argv[0] == "--used-only":
        docs = argv[1:]
        keys = used_keys([Path(a) for a in docs])
    jobs: dict[tuple[str, str], str] = {}
    for k in keys:
        e = bib[k]
        can = canonical_url(e)
        if can:
            jobs[(k, "canonical")] = can
        src = e.get("_source_url")
        if src and src != can:
            jobs[(k, "source")] = str(src)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = dict(zip(jobs, pool.map(probe, jobs.values()), strict=True))
    summary: dict[str, int] = {}
    report = []
    for (k, role), (status, detail) in sorted(results.items()):
        summary[f"{role}:{status}"] = summary.get(f"{role}:{status}", 0) + 1
        report.append({"key": k, "role": role, "url": jobs[(k, role)], "status": status,
                       "detail": detail, "verified": bib[k].get("verified")})
    snippet_only = sorted(k for k in keys if bib[k].get("verified") == "search_snippet_only")
    mirrors = sorted(k for k in keys if is_mirror(bib[k]))
    out = {"documents": docs, "n_sources": len(keys), "summary": summary,
           "reference_points_at_mirror": mirrors, "snippet_only": snippet_only,
           "results": report}
    name = "citation_check.json" if not docs else (
        "citation_check_" + "_".join(Path(d).stem for d in docs) + ".json")
    (ROOT / "results" / name).write_text(json.dumps(out, indent=1))
    print(f"citation check ({len(keys)} sources):", summary,
          f"(snippet-only: {len(snippet_only)}; mirror references: {len(mirrors)})")
    failed = False
    for r in report:
        if r["status"] == "dead":
            print("   DEAD", r["role"], r["key"], r["url"], r["detail"])
            failed = True
    for k in mirrors:
        print("   MIRROR REFERENCE", k, bib[k].get("url"))
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
