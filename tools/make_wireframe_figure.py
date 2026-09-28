"""Interface wireframe for M2: the regions of the bench screen and what each shows."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval import figstyle  # noqa: E402

FIG_W, FIG_H = 6.5, 3.35
LINE, EDGE, FILL, INK, MUTED = "#c9c8c0", "#8c8b84", "#f7f7f4", "#0b0b0b", "#52514e"
RED, RED_T, AMBER, TEAL, BLUE = "#d03b3b", "#fbe9e9", "#eda100", "#1baf7a", "#2a78d6"
TITLE_PT, BODY_PT = 7.6, 6.6


def region(ax, x, y, w, h, title, lines=(), fill=FILL, edge=EDGE, title_color=INK):  # type: ignore[no-untyped-def]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.008",
                                linewidth=0.9, edgecolor=edge, facecolor=fill))
    ax.text(x + 0.008, y + h - 0.012, title, ha="left", va="top", fontsize=TITLE_PT,
            fontweight="bold", color=title_color)
    for i, t in enumerate(lines):
        ax.text(x + 0.008, y + h - 0.052 - i * 0.036, t, ha="left", va="top", fontsize=BODY_PT,
                color=MUTED)


def ring(ax, x, y, r, color, dashed=False, lw=1.4, alpha=1.0):  # type: ignore[no-untyped-def]
    """A circle of radius r (in figure widths), corrected for the figure's aspect ratio."""
    ax.add_patch(Ellipse((x, y), 2 * r, 2 * r * FIG_W / FIG_H, fill=False, lw=lw, ec=color,
                         ls="--" if dashed else "-", alpha=alpha))


def main() -> None:
    figstyle.apply()
    fig = plt.figure(figsize=(FIG_W, FIG_H))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(Rectangle((0.005, 0.005), 0.99, 0.99, linewidth=1.0, edgecolor=LINE, facecolor="white"))

    # Top bar
    ax.add_patch(Rectangle((0.005, 0.905), 0.99, 0.09, linewidth=0, facecolor="#f3f3ef"))
    ax.text(0.02, 0.95, "Differential", fontsize=8.4, fontweight="bold", va="center", color=INK)
    ax.text(0.125, 0.95, "│ AI assistant: it recommends, you decide", fontsize=BODY_PT, va="center",
            color=MUTED)
    for x, label in ((0.43, "Circuit ▾"), (0.53, "● offline"), (0.70, "+ New unit"),
                     (0.80, "Ticket"), (0.87, "Reveal (demo)")):
        ax.text(x, 0.95, label, fontsize=BODY_PT, va="center", color=INK,
                bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": LINE, "lw": 0.7})

    # Schematic panel with hazard rings
    region(ax, 0.02, 0.03, 0.52, 0.86, "Schematic",
           ["test points ringed by hazard: red = high voltage,",
            "amber dashed = high voltage under a fault, teal = low;",
            "the next test point pulses"])
    for (x, y), col, dashed in (((0.12, 0.62), RED, False), ((0.22, 0.48), AMBER, True),
                                ((0.33, 0.62), TEAL, False), ((0.43, 0.40), TEAL, False),
                                ((0.30, 0.30), TEAL, False)):
        ring(ax, x, y, 0.014, col, dashed)
    ring(ax, 0.43, 0.40, 0.024, TEAL, lw=0.8, alpha=0.6)
    ax.plot([0.06, 0.50], [0.52, 0.52], color=LINE, lw=0.8)
    ax.plot([0.06, 0.50], [0.36, 0.36], color=LINE, lw=0.8)
    for x in (0.12, 0.22, 0.33, 0.43):
        ax.plot([x, x], [0.36, 0.52], color=LINE, lw=0.8)

    # Right column
    x0, w = 0.555, 0.425
    region(ax, x0, 0.795, w, 0.095, "Safety banner", ["HIGH VOLTAGE: hands-off method; discharge form below 2 V"],
           fill=RED_T, edge=RED, title_color=RED)
    region(ax, x0, 0.575, w, 0.205, "Next measurement",
           ["what, where and how; expected readings per suspect",
            "information (bits), effort; Measure / Enter reading",
            "Why this? other options and each suspect's 95 % range",
            "unsoldering steps locked until discharge confirmed"], edge=BLUE)
    region(ax, x0, 0.375, w, 0.185, "Belief",
           ["bars by ambiguity group, with “no single fault fits”",
            "effort used against the budget; reading history"])
    for i, frac in enumerate((0.78, 0.12, 0.05)):
        ax.add_patch(Rectangle((x0 + 0.01, 0.416 - i * 0.017), 0.3 * frac, 0.011, lw=0,
                               facecolor=BLUE if i == 0 else "#9ec5f4"))
    region(ax, x0, 0.175, w, 0.185, "Chat",
           ["complaint in plain words; replies explain each step",
            "photo upload → proposed reading + plausibility check",
            "the technician confirms or edits before it counts"])
    region(ax, x0, 0.03, w, 0.13, "Readings and ticket",
           ["every reading with its source; ticket with evidence,",
            "AI disclosure and technician sign-off"])
    figstyle.save(fig, ROOT / "results" / "figures" / "wireframe")


if __name__ == "__main__":
    main()
