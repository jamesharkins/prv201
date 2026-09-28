"""Architecture figure: components and data flow (M2, M3, report)."""

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
RED, RED_T = "#e34948", "#fce8e8"
INK = "#0b0b0b"
FIG_W, FIG_H = 7.2, 4.6


def box(ax, x, y, w, h, title, body, edge, fill, fs=6.2):  # type: ignore[no-untyped-def]
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.003,rounding_size=0.01",
                                linewidth=1.0, edgecolor=edge, facecolor=fill))
    ax.text(x + w / 2, y + h - 0.022, title, ha="center", va="top", fontsize=7.0,
            fontweight="bold", color=INK)
    if body:
        ax.text(x + w / 2, y + h - 0.058, body, ha="center", va="top", fontsize=fs,
                color="#3a3936", linespacing=1.25)


def arrow(ax, a, b, color=GRAY, style="-|>", rad=0.0, ls="-"):  # type: ignore[no-untyped-def]
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=7, linewidth=0.9,
                                 color=color, connectionstyle=f"arc3,rad={rad}", linestyle=ls,
                                 shrinkA=0, shrinkB=0))


def band(ax, y, h, label):  # type: ignore[no-untyped-def]
    ax.add_patch(FancyBboxPatch((0.01, y), 0.98, h, boxstyle="round,pad=0.002,rounding_size=0.01",
                                linewidth=0.6, edgecolor="#d8d7cf", facecolor="#fbfaf8"))
    ax.text(0.02, y + h - 0.012, label, fontsize=6.2, color="#6f6d68", fontweight="bold",
            va="top")


def main() -> None:
    figstyle.apply()
    fig = plt.figure(figsize=(FIG_W, FIG_H))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # --- Offline build band
    band(ax, 0.70, 0.29, "OFFLINE: SIMULATE AND LEARN  (make sim cases fit)")
    y, h = 0.72, 0.165
    xs = [0.03, 0.222, 0.414, 0.606, 0.798]
    w = 0.172
    items = [
        ("Circuit model", "netlist + YAML sidecar:\nparts, tolerances, test\npoints, hazard flags"),
        ("Fault catalog", "every single-part fault;\nseverity drawn per unit;\ntolerance draws per part"),
        ("ngspice runner", "batch decks, retry ladder,\nDC / gain / hum / THD;\nParquet + manifest"),
        ("Training", "Gaussian mixtures, masked\nboosted trees, ambiguity\ngroups, symptom model"),
        ("Model bundle", "data/models/<circuit>:\nlikelihoods, groups,\ncalibrated thresholds"),
    ]
    for x, (t, b) in zip(xs, items, strict=True):
        box(ax, x, y, w, h, t, b, BLUE, BLUE_T)
    for i in range(4):
        arrow(ax, (xs[i] + w + 0.002, y + h / 2), (xs[i + 1] - 0.002, y + h / 2), BLUE)

    # --- Online band
    band(ax, 0.215, 0.465, "ONLINE: DIAGNOSE ONE UNIT  (make demo)")
    box(ax, 0.03, 0.465, 0.15, 0.165, "Web UI", "schematic, belief,\nnext step, chat,\nphoto, ticket", GRAY, GRAY_T)
    box(ax, 0.215, 0.465, 0.15, 0.165, "FastAPI server", "sessions, simulated\nbench, export,\nreplay", GRAY, GRAY_T)
    box(ax, 0.40, 0.44, 0.20, 0.19, "Agent", "live (Claude), offline\n(templates) or replay;\nreads complaints and\nexplains each step", ORANGE, ORANGE_T)
    box(ax, 0.635, 0.465, 0.165, 0.165, "Tools", "belief, next step,\nexpected readings,\nsafety brief, ticket", ORANGE, ORANGE_T)
    box(ax, 0.83, 0.465, 0.15, 0.165, "Engine session", "posterior, expected\ninformation per\neffort, stopping", BLUE, BLUE_T)
    box(ax, 0.40, 0.235, 0.20, 0.15, "LLM client", "Claude API; key from\nDIFFERENTIAL_API_KEY;\nresponse cache", ORANGE, ORANGE_T, fs=5.8)
    box(ax, 0.635, 0.235, 0.165, 0.15, "NLP + vision", "complaint to symptoms;\nmeter photo to reading", ORANGE, ORANGE_T, fs=5.8)
    box(ax, 0.83, 0.235, 0.15, 0.15, "Instruments", "simulated bench,\nSCPI (24 V board),\nmanual entry", AQUA, AQUA_T, fs=5.8)
    box(ax, 0.03, 0.235, 0.335, 0.15, "Safety layer (code)", "request screening, fault-conditioned hazard map,\nunsoldering lock, output checks, grounding check",
        RED, RED_T, fs=5.8)
    arrow(ax, (0.182, 0.547), (0.213, 0.547), GRAY, style="<|-|>")
    arrow(ax, (0.367, 0.547), (0.398, 0.547), GRAY, style="<|-|>")
    arrow(ax, (0.602, 0.547), (0.633, 0.547), ORANGE, style="<|-|>")
    arrow(ax, (0.802, 0.547), (0.828, 0.547), BLUE, style="<|-|>")
    arrow(ax, (0.50, 0.438), (0.50, 0.387), ORANGE, style="<|-|>")
    arrow(ax, (0.717, 0.463), (0.717, 0.387), ORANGE, style="<|-|>")
    arrow(ax, (0.905, 0.463), (0.905, 0.387), AQUA, style="<|-|>")
    arrow(ax, (0.30, 0.387), (0.398, 0.46), RED, style="<|-|>")
    # models feed the engine
    arrow(ax, (0.884, 0.718), (0.905, 0.632), BLUE, rad=0.0)

    # --- Evaluation band
    band(ax, 0.01, 0.19, "EVALUATION AND REPORTING  (make pilot eval docs)")
    ex = [0.03, 0.27, 0.51, 0.75]
    ew = 0.215
    evals = [
        ("Held-out cases", "1,000 single-fault, 100\nunmodeled, 300 stress units"),
        ("Harness", "8 systems + ablations,\ncommon random numbers"),
        ("metrics.json", "targets met / missed /\npending with 95% CIs"),
        ("Documents", "templates: every number\nfrom metrics or sources"),
    ]
    for x, (t, b) in zip(ex, evals, strict=True):
        box(ax, x, 0.022, ew, 0.125, t, b, GRAY, GRAY_T, fs=5.8)
    for i in range(3):
        arrow(ax, (ex[i] + ew + 0.002, 0.085), (ex[i + 1] - 0.002, 0.085), GRAY)
    figstyle.save(fig, ROOT / "results" / "figures" / "architecture")


if __name__ == "__main__":
    main()
