"""Render README.md from templates/README.md.j2 with the results in results/metrics.json.

Usage: python tools/render_readme.py

Every number in the results section comes from results/metrics.json (the
``targets_result`` section written by eval/run_eval.py and the sections it reads) or
from results/targets.json; this script only formats them. The target table lists every
locked target with its status exactly as run_eval reports it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doclib import RESULTS, ROOT, Metrics, fmt_pct, load_json
from render_docs import context, make_env

# How each target's value reads (presentation only).
KIND = {
    **dict.fromkeys(["T1", "T2", "T3", "T6", "T7", "T13", "T15", "T17", "T19", "T23"], "pct"),
    **dict.fromkeys(["T4", "T5", "T14"], "pts"),
    **dict.fromkeys(["T8", "T9", "T10", "T11", "T24"], "ratio"),
    **dict.fromkeys(["T12", "T18", "T22"], "dec"),
    "T16": "count", "T25": "count", "T26": "count", "T20": "sec", "T21": "usd",
}


def fmt(kind: str, x: Any) -> str:
    if x is None:
        return "—"
    x = float(x)
    if kind == "pct":
        return fmt_pct(x, 1)
    if kind == "pts":
        return f"{100 * x:+.1f} pts"
    if kind == "ratio":
        return f"{x:.3f}×"
    if kind == "dec":
        return f"{x:.3f}"
    if kind == "sec":
        return f"{x:.3f} s"
    if kind == "usd":
        return f"${x:.4f}"
    return f"{x:g}"


def bounds(kind: str, ci: dict[str, Any] | None) -> str:
    if not ci or ci.get("lo") is None or ci.get("lo") == ci.get("hi"):
        return "—"
    return f"{fmt(kind, ci['lo'])} to {fmt(kind, ci['hi'])}"


def note(tid: str, r: dict[str, Any], m: Any) -> str:
    """The other parts of a several-part target, and why a target is pending."""
    if tid == "T4":
        names = {"fixed_order": "fixed order", "half_split": "half-split", "random": "random"}
        return "; ".join(f"vs {names[k]} {fmt('pts', v['margin']['value'])}"
                         for k, v in r["margins"].items())
    if tid == "T14":
        return (f"catalog mix {fmt('pts', r['capacitor_heavy_prior_catalog_mix']['value'])}; "
                f"capacitor mix {fmt('pts', r['uniform_prior_capacitor_mix']['value'])}")
    if tid == "T18":
        return f"value is the rules; Claude {fmt('dec', r['claude']['value'])}"
    if tid == "T19":
        c = r["claude"]
        return f"value is offline; Claude {fmt('pct', c['value'])} ({bounds('pct', c)})"
    if tid == "T22":
        f = r["flag_rate"]
        return f"value is AUROC; flagged {fmt('pct', f['value'])} ({bounds('pct', f)})"
    if tid == "T23":
        a = r["accuracy_when_naming"]
        return f"value is named; right when naming {fmt_pct(a['value'], 2)} ({bounds('pct', a)})"
    if tid == "T16" and m.has("redteam_offline.n_attacks"):
        s = (f"{m.get('redteam_offline.n_attacks')} of the 300 attacks required; offline "
             f"{m.get('redteam_offline.unsafe')} not refused by keyword scoring")
        if m.has("redteam_live.unsafe"):
            s += f", live {m.get('redteam_live.unsafe')}"
        if m.has("redteam_review.offline.attacks.endorses"):
            s += (f"; reviewed: endorses {m.get('redteam_review.offline.attacks.endorses')} offline, "
                  f"{m.get('redteam_review.live.attacks.endorses')} live")
        return s
    if tid == "T17":
        s = "offline census; independent checker and human audit pending"
        if m.has("agent_live.ungrounded_final"):
            s += (f"; live {m.get('agent_live.ungrounded_final')} of "
                  f"{m.get('agent_live.numbers_checked'):,} numbers after the check, all withheld "
                  "before display (results/t17_live_review.json)")
        return s
    if r.get("status") == "pending":
        return str(r.get("note") or (r.get("detail") or {}).get("status") or "")
    return ""


def rows() -> tuple[list[dict[str, str]], dict[str, int]]:
    targets = load_json(RESULTS / "targets.json")["targets"]
    m = Metrics(load_json(RESULTS / "metrics.json"))
    res = m.get("targets_result")
    out, counts = [], {"met": 0, "missed": 0, "pending": 0}
    for t in targets:
        tid = t["id"]
        r = res[tid]
        kind = KIND[tid]
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        out.append({"id": tid, "role": t["role"], "plain": t["plain"], "bar": r["bar"],
                    "value": fmt(kind, r.get("value")), "bounds": bounds(kind, r.get("ci")),
                    "status": r["status"], "note": note(tid, r, m)})
    return out, counts


def main() -> int:
    env = make_env()
    ctx = context()
    table, counts = rows()
    text = env.get_template("README.md.j2").render(**ctx, rows=table, counts=counts)
    (ROOT / "README.md").write_text(text)
    print(f"README.md: {len(table)} targets ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
