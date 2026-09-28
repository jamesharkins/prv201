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
FIG_W, FIG_H = 7.2, 3.4
LINE = 6.5 * 1.3 / 72 / FIG_H  # body line height in axes units
TITLE = 7.6 / 72 / FIG_H


def box_height(n_lines: int) -> float:
    return 0.028 + TITLE + 0.018 + n_lines * LINE + 0.026


def box(ax, x, y, w, title, body, edge, fill, h=None):  # type: ignore[no-untyped-def]
    """Box with its bottom-left corner at (x, y); height follows the text."""
    n = body.count("\n") + 1
    h = h or box_height(n)
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.014",
                                linewidth=1.1, edgecolor=edge, facecolor=fill))
    top = y + h - 0.028
    ax.text(x + w / 2, top, title, ha="center", va="top", fontsize=7.6, fontweight="bold",
            color=INK)
    ax.text(x + w / 2, top - TITLE - 0.018, body, ha="center", va="top", fontsize=6.5,
            color="#3a3936", linespacing=1.3)
    return h


def arrow(ax, a, b, color=GRAY, rad=0.0):  # type: ignore[no-untyped-def]
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=8, linewidth=1.1,
                                 color=color, connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=0, shrinkB=0))


def lane_label(ax, y, text):  # type: ignore[no-untyped-def]
    ax.text(0.03, y, text, fontsize=6.4, color="#6f6d68", fontweight="bold", rotation=90,
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
        ("Circuit model", "netlist from the schematic\n(here: 5 original blocks\n+ a channel strip)"),
        ("Fault catalog", "every single-part fault\n× part tolerances\n(datasheet spreads)"),
        ("Monte Carlo SPICE", "DC, gain, 120 Hz hum and\ndistortion at every test\npoint, for every unit"),
        ("Fault signatures", "learned likelihoods\n(GMM, boosted trees),\nambiguity groups"),
    ]
    h1 = box_height(3)
    y1 = 0.985 - h1
    for x, (t, b) in zip(xs, row1, strict=True):
        box(ax, x, y1, w1, t, b, BLUE, BLUE_T)
    for i in range(3):
        arrow(ax, (xs[i] + w1 + 0.004, y1 + h1 / 2), (xs[i + 1] - 0.004, y1 + h1 / 2), BLUE)
    lane_label(ax, y1 + h1 / 2, "OFFLINE PHYSICS")

    # Row 2: online diagnosis loop
    hb = box_height(4)
    yb = y1 - 0.105 - hb
    xb, wb = 0.47, 0.205
    box(ax, xb, yb, wb, "Bayesian belief", "a probability for every\nsuspect, updated after each\nreading; “no single fault\nfits” is a hypothesis too",
        BLUE, BLUE_T)
    h3 = box_height(3)
    yc = yb + (hb - h3) / 2
    box(ax, 0.075, yc, 0.165, "Complaint", "“the channel hums\nand sounds thin”\n(free text)", GRAY, GRAY_T)
    box(ax, 0.27, yc, 0.17, "LLM extraction", "symptom classes as\nvalidated JSON;\nno fault guessing", ORANGE, ORANGE_T)
    arrow(ax, (0.244, yc + h3 / 2), (0.266, yc + h3 / 2))
    arrow(ax, (0.444, yc + h3 / 2), (0.466, yc + h3 / 2), ORANGE)

    xr, wr = 0.715, 0.27
    yn = yb + hb - h3
    box(ax, xr, yn, wr, "Next measurement", "most suspects ruled out per\nunit of effort, with expected\nreadings; explained in plain words",
        BLUE, BLUE_T)
    h2 = box_height(2)
    yt = yn - 0.075 - h2
    box(ax, xr, yt, wr, "Technician measures", "DMM, scope or meter photo;\nthe technician confirms each reading",
        AQUA, AQUA_T)
    arrow(ax, (xb + wb + 0.004, yn + h3 / 2), (xr - 0.004, yn + h3 / 2), BLUE)
    arrow(ax, (xr + wr / 2, yn - 0.004), (xr + wr / 2, yt + h2 + 0.004), GRAY)
    arrow(ax, (xr - 0.004, yt + h2 / 2), (xb + wb + 0.004, yb + 0.05), AQUA)
    # the learned physics feeds the belief (route passes above the right column)
    arrow(ax, (xs[3] + 0.03, y1 - 0.004), (xb + wb * 0.62, yb + hb + 0.004), BLUE, rad=-0.08)
    lane_label(ax, yb + hb / 2 - 0.03, "ONLINE DIAGNOSIS")

    # stop -> repair ticket
    ht = box_height(2)
    yk = yb - 0.06 - ht
    assert yk > 0.125, yk
    box(ax, xb, yk, wb, "Repair ticket", "at ≥ 90% confidence: diagnosis,\nevidence trail, technician sign-off", GRAY, GRAY_T)
    arrow(ax, (xb + wb / 2, yb - 0.004), (xb + wb / 2, yk + ht + 0.004), GRAY)

    # Guardrails band
    ax.add_patch(FancyBboxPatch((0.075, 0.02), 0.91, 0.085, boxstyle="round,pad=0.004,rounding_size=0.012",
                                linewidth=0.9, edgecolor="#c3c2b7", facecolor="#f7f6f3"))
    ax.text(0.53, 0.0625, "Safety rules (worst-case high-voltage map, discharge lock, refusals)  ·  every number traced  ·  "
            "retrieved text treated as data",
            ha="center", va="center", fontsize=6.6, color="#3a3936")
    lane_label(ax, 0.0625, "IN CODE")
    figstyle.save(fig, ROOT / "results" / "figures" / "concept")


if __name__ == "__main__":
    main()
