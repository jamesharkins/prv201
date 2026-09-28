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
# below are the sizes on paper.
FIG_W, FIG_H = 6.5, 2.76
BODY_PT, TITLE_PT = 7.4, 8.4
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
        ("Circuit model", "netlist and test points\nfrom the schematic"),
        ("Fault catalog", "every single-part fault\n× part tolerances"),
        ("SPICE Monte Carlo", "readings at every test\npoint, for every unit"),
        ("Fault signatures", "learned likelihoods,\nambiguity groups"),
    ]
    h1 = box_height(2)
    y1 = 1 - inch(0.045) - h1
    for x, (t, b) in zip(xs, row1, strict=True):
        box(ax, x, y1, w1, t, b, BLUE, BLUE_T)
    for i in range(3):
        arrow(ax, (xs[i] + w1 + 0.004, y1 + h1 / 2), (xs[i + 1] - 0.004, y1 + h1 / 2), BLUE)
    lane_label(ax, y1 + h1 / 2, "OFFLINE")

    # Row 2: online diagnosis loop
    hb = box_height(3)
    yb = y1 - inch(0.3) - hb
    xb, wb = 0.47, 0.215
    box(ax, xb, yb, wb, "Bayesian belief", "every suspect, plus\n“no single fault fits”,\nupdated per reading",
        BLUE, BLUE_T)
    h3 = box_height(2)
    yc = yb + (hb - h3) / 2
    box(ax, 0.075, yc, 0.165, "Complaint", "“hums and\nsounds thin”", GRAY, GRAY_T)
    box(ax, 0.27, yc, 0.17, "LLM reads it", "symptoms only;\nno fault guessing", ORANGE, ORANGE_T)
    arrow(ax, (0.244, yc + h3 / 2), (0.266, yc + h3 / 2))
    arrow(ax, (0.444, yc + h3 / 2), (0.466, yc + h3 / 2), ORANGE)

    xr, wr = 0.715, 0.27
    yn = yb + hb - h3
    box(ax, xr, yn, wr, "Next measurement", "most suspects ruled out\nper unit of effort, explained",
        BLUE, BLUE_T)
    h2 = box_height(2)
    yt = yn - inch(0.22) - h2
    box(ax, xr, yt, wr, "Technician measures", "meter, scope or photo;\nconfirms every reading",
        AQUA, AQUA_T)
    arrow(ax, (xb + wb + 0.004, yn + h3 / 2), (xr - 0.004, yn + h3 / 2), BLUE)
    arrow(ax, (xr + wr / 2, yn - 0.004), (xr + wr / 2, yt + h2 + 0.004), GRAY)
    arrow(ax, (xr - 0.004, yt + h2 / 2), (xb + wb + 0.004, yb + inch(0.15)), AQUA)
    # the learned physics feeds the belief (route passes above the right column)
    arrow(ax, (xs[3] + 0.03, y1 - 0.004), (xb + wb * 0.62, yb + hb + 0.004), BLUE, rad=-0.08)
    lane_label(ax, yb + hb / 2 - inch(0.09), "ONLINE")

    # stop -> repair ticket
    ht = box_height(2)
    yk = yb - inch(0.17) - ht
    band_y, band_h = inch(0.04), inch(0.22)
    assert yk > band_y + band_h + inch(0.035), yk
    box(ax, xb, yk, wb, "Repair ticket", "at ≥ 90 %: diagnosis,\nevidence, sign-off", GRAY, GRAY_T)
    arrow(ax, (xb + wb / 2, yb - 0.004), (xb + wb / 2, yk + ht + 0.004), GRAY)

    # Guardrails band
    ax.add_patch(FancyBboxPatch((0.075, band_y), 0.91, band_h,
                                boxstyle="round,pad=0.004,rounding_size=0.012",
                                linewidth=0.9, edgecolor="#c3c2b7", facecolor="#f7f6f3"))
    ax.text(0.53, band_y + band_h / 2, "Safety rules and locks  ·  every number traced  ·  retrieved text treated as data",
            ha="center", va="center", fontsize=BODY_PT, color="#3a3936")
    lane_label(ax, band_y + band_h / 2, "CODE")
    figstyle.save(fig, ROOT / "results" / "figures" / "concept")


if __name__ == "__main__":
    main()
