"""Data-flow figure: one diagnosis step by step, as a sequence diagram (M2, M3, report)."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval import figstyle  # noqa: E402

INK, MUTED, LINE = "#0b0b0b", "#52514e", "#c3c2b7"
LANES = [  # (title, subtitle, edge, fill)
    ("Technician", "person at the bench", "#52514e", "#f1f0ec"),
    ("Web UI", "schematic, chat, ticket", "#52514e", "#f1f0ec"),
    ("Agent", "LLM or templates", "#eb6834", "#fdebe3"),
    ("Safety layer", "code, not prompt", "#e34948", "#fce8e8"),
    ("Engine", "belief + next step", "#2a78d6", "#e3effc"),
    ("Instrument", "simulated / SCPI / typed", "#1baf7a", "#e0f5ed"),
]
# (from lane, to lane, label, dashed=return)
STEPS = [
    (0, 1, "1  complaint: “hums and sounds thin”", False),
    (1, 2, "2  message", False),
    (2, 3, "3  screen request (mains-side, bypass: refuse)", False),
    (2, 4, "4  symptoms → prior over faults", False),
    (4, 2, "5  next measurement + expected readings", True),
    (2, 3, "6  hazard map: hands-off / discharge text; lift locked?", False),
    (3, 1, "7  step shown with safety banner", True),
    (0, 5, "8  technician measures (or confirms a photo reading)", False),
    (5, 4, "9  reading recorded → posterior updated", False),
    (4, 2, "10  stop at ≥ 0.90, budget, or no informative step", True),
    (2, 3, "11  grounding check: every number traced", False),
    (3, 0, "12  ticket: diagnosis, evidence, sign-off", True),
]


def main() -> None:
    figstyle.apply()
    fig = plt.figure(figsize=(7.2, 4.4))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    n = len(LANES)
    xs = [0.08 + i * (0.84 / (n - 1)) for i in range(n)]
    top, bottom = 0.86, 0.04
    for x, (title, sub, edge, fill) in zip(xs, LANES, strict=True):
        ax.add_patch(FancyBboxPatch((x - 0.07, top), 0.14, 0.11,
                                    boxstyle="round,pad=0.003,rounding_size=0.012",
                                    linewidth=1.0, edgecolor=edge, facecolor=fill))
        ax.text(x, top + 0.072, title, ha="center", va="center", fontsize=7.2,
                fontweight="bold", color=INK)
        ax.text(x, top + 0.030, sub, ha="center", va="center", fontsize=5.6, color=MUTED)
        ax.plot([x, x], [bottom, top], color=LINE, lw=0.8, ls=(0, (2, 2)), zorder=0)
    dy = (top - bottom - 0.04) / len(STEPS)
    for i, (a, b, label, ret) in enumerate(STEPS):
        y = top - 0.035 - i * dy
        x0, x1 = xs[a], xs[b]
        color = MUTED if ret else INK
        ax.add_patch(FancyArrowPatch((x0, y), (x1, y), arrowstyle="-|>", mutation_scale=7,
                                     linewidth=0.9, color=color, shrinkA=2, shrinkB=2,
                                     linestyle="--" if ret else "-"))
        lx = min(x0, x1) + 0.006
        ax.text(lx, y + 0.012, label, ha="left", va="bottom", fontsize=5.8, color=INK,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6, "alpha": 0.9})
    ax.text(0.5, 0.012, "Solid: request or data; dashed: result returned. Steps 5–10 repeat "
            "for every measurement.", ha="center", va="bottom", fontsize=5.8, color=MUTED)
    figstyle.save(fig, ROOT / "results" / "figures" / "dataflow")


if __name__ == "__main__":
    main()
