"""Concept figure: how Differential grounds an LLM agent in circuit physics."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval import figstyle  # noqa: E402

BLUE, BLUE_T = "#2a78d6", "#e3effc"
ORANGE, ORANGE_T = "#eb6834", "#fdebe3"
AQUA, AQUA_T = "#1baf7a", "#e0f5ed"
GRAY, GRAY_T = "#52514e", "#f1f0ec"
INK = "#0b0b0b"
# Drawn at its printed size (full text width, shown at 100 %), so the type sizes
# below are the sizes on paper (round 5: at 56 % width the labels printed near 4 pt).
FIG_W, FIG_H = 6.5, 1.92
BODY_PT, TITLE_PT = 7.4, 8.2
LINE = BODY_PT * 1.3 / 72 / FIG_H  # body line height in axes units
TITLE = TITLE_PT / 72 / FIG_H


def inch(v: float) -> float:
    """A vertical distance in inches, in axes units."""
    return v / FIG_H


PAD_TOP, TITLE_GAP, PAD_BOTTOM = inch(0.085), inch(0.055), inch(0.08)


def box_height(n_lines: int) -> float:
    return PAD_TOP + TITLE + TITLE_GAP + n_lines * LINE + PAD_BOTTOM


def box(ax, x, y, w, title, body, edge, fill, h=None):  # type: ignore[no-untyped-def]
    """Box with its bottom-left corner at (x, y); height follows the text."""
    n = body.count("\n") + 1
    h = h or box_height(n)
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.014",
                                linewidth=1.1, edgecolor=edge, facecolor=fill))
    top = y + h - PAD_TOP
    ax.text(x + w / 2, top, title, ha="center", va="top", fontsize=TITLE_PT, fontweight="bold",
            color=INK)
    ax.text(x + w / 2, top - TITLE - TITLE_GAP, body, ha="center", va="top", fontsize=BODY_PT,
            color="#3a3936", linespacing=1.3)
    return h


def arrow(ax, a, b, color=GRAY, rad=0.0):  # type: ignore[no-untyped-def]
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=8, linewidth=1.1,
                                 color=color, connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=0, shrinkB=0))


def lane_label(ax, y, text):  # type: ignore[no-untyped-def]
    ax.text(0.03, y, text, fontsize=7.0, color="#6f6d68", fontweight="bold", rotation=90,
            ha="center", va="center")


def main() -> None:
    figstyle.apply()
    fig = plt.figure(figsize=(FIG_W, FIG_H))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Row 1: offline physics pipeline
    w1, gap = 0.2025, 0.027
    xs = [0.075 + i * (w1 + gap) for i in range(4)]
    row1 = [
        ("Circuit model", "netlist and test points"),
        ("Fault catalog", "every single-part fault"),
        ("SPICE Monte Carlo", "tolerances; new and aged"),
        ("Fault signatures", "likelihoods, groups"),
    ]
    h1 = box_height(1)
    y1 = 1 - inch(0.04) - h1
    for x, (t, b) in zip(xs, row1, strict=True):
        box(ax, x, y1, w1, t, b, BLUE, BLUE_T)
    for i in range(3):
        arrow(ax, (xs[i] + w1 + 0.004, y1 + h1 / 2), (xs[i + 1] - 0.004, y1 + h1 / 2), BLUE)
    lane_label(ax, y1 + h1 / 2, "OFFLINE")

    # Row 2: online diagnosis loop
    hb = box_height(3)
    yb = y1 - inch(0.24) - hb
    widths = [0.12, 0.15, 0.2, 0.2, 0.185]
    g2 = (0.91 - sum(widths)) / 4
    x2 = [0.075]
    for w in widths[:-1]:
        x2.append(x2[-1] + w + g2)
    h2 = box_height(2)
    yc = yb + (hb - h2) / 2
    box(ax, x2[0], yc, widths[0], "Complaint", "“hums and\nsounds thin”", GRAY, GRAY_T)
    box(ax, x2[1], yc, widths[1], "LLM reads it", "symptoms only;\nno fault guessing", ORANGE, ORANGE_T)
    box(ax, x2[2], yb, widths[2], "Bayesian belief",
        "every suspect and\n“no single fault fits”;\nat ≥ 90 %: repair ticket", BLUE, BLUE_T)
    box(ax, x2[3], yc, widths[3], "Next measurement", "rules out most suspects\nper unit of effort", BLUE, BLUE_T)
    box(ax, x2[4], yc, widths[4], "Technician", "measures and\nconfirms each reading", AQUA, AQUA_T)
    colors = [GRAY, ORANGE, BLUE, BLUE]
    for i in range(4):
        arrow(ax, (x2[i] + widths[i] + 0.003, yc + h2 / 2), (x2[i + 1] - 0.003, yc + h2 / 2), colors[i])
    # each reading goes back into the belief (under the row)
    arrow(ax, (x2[4] + widths[4] * 0.35, yc - 0.004), (x2[2] + widths[2] * 0.75, yb - 0.004), AQUA, rad=-0.12)
    # the learned physics feeds the belief
    arrow(ax, (xs[3] + w1 * 0.3, y1 - 0.004), (x2[2] + widths[2] * 0.62, yb + hb + 0.004), BLUE, rad=-0.05)
    lane_label(ax, yb + hb / 2, "ONLINE")

    # Guardrails band
    band_y, band_h = inch(0.03), inch(0.2)
    assert yb - inch(0.16) > band_y + band_h, (yb, band_y + band_h)
    ax.add_patch(FancyBboxPatch((0.075, band_y), 0.91, band_h,
                                boxstyle="round,pad=0.004,rounding_size=0.012",
                                linewidth=0.9, edgecolor="#c3c2b7", facecolor="#f7f6f3"))
    ax.text(0.53, band_y + band_h / 2, "Safety rules and locks  ·  every number traced  ·  retrieved text treated as data",
            ha="center", va="center", fontsize=BODY_PT, color="#3a3936")
    lane_label(ax, band_y + band_h / 2, "CODE")
    figstyle.save(fig, ROOT / "results" / "figures" / "concept")


if __name__ == "__main__":
    main()
