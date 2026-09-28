"""One matplotlib style for every figure (reports, slides, README).

Palette: the validated reference categorical order (blue, orange, aqua, yellow,
magenta, green, violet, red) on a white print surface; all hard checks pass;
aqua, yellow and magenta are below 3:1 contrast on white, so charts that use
them always carry direct value labels or a legend (relief rule).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7",
               "#e34948"]
SEQUENTIAL_BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
                   "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]
DIVERGING = {"neg": "#2a78d6", "mid": "#f0efec", "pos": "#e34948"}
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
INK = {"primary": "#0b0b0b", "secondary": "#52514e", "muted": "#898781", "grid": "#e1e0d9",
       "axis": "#c3c2b7", "surface": "#ffffff"}

# Fixed entity -> colour mapping (colour follows the entity in every figure).
SYSTEM_ORDER = [
    "hybrid",
    "engine_gen",
    "engine_disc",
    "fixed_order",
    "random",
    "llm_only",
]
SYSTEM_LABEL = {
    "hybrid": "Hybrid (symptom prior + engine)",
    "engine_gen": "Engine, generative",
    "engine_disc": "Engine, discriminative",
    "fixed_order": "Fixed-order procedure",
    "random": "Random probing",
    "llm_only": "LLM only",
}
SYSTEM_COLOR = {s: CATEGORICAL[i] for i, s in enumerate(SYSTEM_ORDER)}


def apply() -> None:
    plt.rcParams.update(
        {
            "font.family": ["Inter", "DejaVu Sans"],
            "font.size": 8.5,
            "axes.titlesize": 9.5,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.labelsize": 8.5,
            "axes.labelcolor": INK["secondary"],
            "axes.edgecolor": INK["axis"],
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": INK["grid"],
            "grid.linewidth": 0.7,
            "grid.linestyle": "-",
            "xtick.color": INK["muted"],
            "ytick.color": INK["muted"],
            "xtick.labelcolor": INK["secondary"],
            "ytick.labelcolor": INK["secondary"],
            "xtick.labelsize": 7.8,
            "ytick.labelsize": 7.8,
            "lines.linewidth": 1.6,
            "lines.solid_capstyle": "round",
            "lines.markersize": 5.5,
            "legend.frameon": False,
            "legend.fontsize": 7.8,
            "figure.facecolor": INK["surface"],
            "axes.facecolor": INK["surface"],
            "savefig.facecolor": INK["surface"],
            "savefig.dpi": 220,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.04,
            "text.color": INK["primary"],
        }
    )


def save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"))
    fig.savefig(path.with_suffix(".svg"))
    plt.close(fig)
