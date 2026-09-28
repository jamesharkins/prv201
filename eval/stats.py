"""Statistics for headline claims: bootstrap CIs, paired comparisons, ECE, AUROC."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import binomtest, wilcoxon

N_BOOT = 2000
SEED = 20260928


@dataclass(frozen=True)
class Estimate:
    value: float
    lo: float
    hi: float

    def as_dict(self) -> dict[str, float]:
        return {"value": self.value, "lo": self.lo, "hi": self.hi}


def bootstrap_mean(x: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED,
                   stat=np.mean) -> Estimate:  # type: ignore[no-untyped-def]
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return Estimate(float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    boots = stat(x[idx], axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return Estimate(float(stat(x)), float(lo), float(hi))


def bootstrap_ratio_of_means(a: np.ndarray, b: np.ndarray, n_boot: int = N_BOOT,
                             seed: int = SEED) -> Estimate:
    """Paired ratio mean(a)/mean(b) with a percentile bootstrap over cases."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(n_boot, len(a)))
    boots = a[idx].mean(axis=1) / b[idx].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return Estimate(float(a.mean() / b.mean()), float(lo), float(hi))


def paired_diff(a: np.ndarray, b: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> Estimate:
    """mean(a - b) over paired cases with a bootstrap CI."""
    return bootstrap_mean(np.asarray(a, float) - np.asarray(b, float), n_boot, seed)


def mcnemar(correct_a: np.ndarray, correct_b: np.ndarray) -> dict[str, float]:
    """Exact McNemar test on paired binary outcomes."""
    a, b = np.asarray(correct_a, bool), np.asarray(correct_b, bool)
    only_a = int((a & ~b).sum())
    only_b = int((~a & b).sum())
    n = only_a + only_b
    p = 1.0 if n == 0 else float(binomtest(only_a, n, 0.5).pvalue)
    return {"a_only": only_a, "b_only": only_b, "p_value": p}


def wilcoxon_paired(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a - b
    if np.allclose(d, 0):
        return {"statistic": 0.0, "p_value": 1.0}
    res = wilcoxon(a, b, zero_method="wilcox")
    return {"statistic": float(res.statistic), "p_value": float(res.pvalue)}


def ece(confidence: np.ndarray, correct: np.ndarray, n_bins: int = 10) -> tuple[float, list[dict[str, float]]]:
    """Expected calibration error with equal-width bins, plus the bin table."""
    conf = np.asarray(confidence, float)
    corr = np.asarray(correct, float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    bins = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        n = int(sel.sum())
        if n == 0:
            bins.append({"lo": lo, "hi": hi, "n": 0, "confidence": None, "accuracy": None})
            continue
        c, a = float(conf[sel].mean()), float(corr[sel].mean())
        total += n / len(conf) * abs(c - a)
        bins.append({"lo": lo, "hi": hi, "n": n, "confidence": c, "accuracy": a})
    return float(total), bins


def ece_ci(confidence: np.ndarray, correct: np.ndarray, n_boot: int = N_BOOT,
           seed: int = SEED) -> Estimate:
    conf, corr = np.asarray(confidence, float), np.asarray(correct, float)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot // 4):
        idx = rng.integers(0, len(conf), len(conf))
        vals.append(ece(conf[idx], corr[idx])[0])
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return Estimate(ece(conf, corr)[0], float(lo), float(hi))


def auroc(scores_pos: np.ndarray, scores_neg: np.ndarray) -> float:
    """Mann-Whitney estimate of the area under the ROC curve (ties count half)."""
    pos, neg = np.asarray(scores_pos, float), np.asarray(scores_neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    ranks = _rankdata(allv)
    r_pos = ranks[: len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def _rankdata(x: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata

    return np.asarray(rankdata(x))


def auroc_ci(pos: np.ndarray, neg: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> Estimate:
    rng = np.random.default_rng(seed)
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    vals = []
    for _ in range(n_boot):
        vals.append(auroc(pos[rng.integers(0, len(pos), len(pos))],
                          neg[rng.integers(0, len(neg), len(neg))]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return Estimate(auroc(pos, neg), float(lo), float(hi))


def roc_curve(pos: np.ndarray, neg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    thr = np.unique(np.concatenate([pos, neg]))[::-1]
    tpr = np.array([0.0] + [float((pos >= t).mean()) for t in thr] + [1.0])
    fpr = np.array([0.0] + [float((neg >= t).mean()) for t in thr] + [1.0])
    return fpr, tpr
