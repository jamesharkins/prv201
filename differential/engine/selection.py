"""Next-measurement selection (brief §2.3).

Expected information gain (EIG) of a candidate measurement is the expected drop
in entropy of the posterior over *ambiguity groups* (the level at which the
stopping rule operates). It is estimated by sampling the posterior predictive:
samples are allocated to mixture components in proportion to their posterior
mass (systematic allocation, which lowers variance), drawn from each
component's Gaussian conditional given the evidence so far, and the posterior is
recomputed for every sample. Lift tests have two outcomes and are computed
exactly. Scores are EIG per unit cost; ties are broken toward low-voltage,
cheaper measurements.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from differential.sim.measurement import LIFT_SENSITIVITY, LIFT_SPECIFICITY
from differential.sim.observables import ObservableSpec

TIE_TOL = 1e-3


def entropy(p: np.ndarray) -> float:
    q = p[p > 0]
    return float(-(q * np.log2(q)).sum())


def entropy_rows(P: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        L = np.where(P > 0, np.log2(P), 0.0)
    return np.asarray(-(P * L).sum(axis=-1))


@dataclass(frozen=True)
class Candidate:
    obs: ObservableSpec
    eig: float
    score: float

    @property
    def key(self) -> str:
        return self.obs.key


def systematic_allocation(p: np.ndarray, m: int) -> np.ndarray:
    """Number of samples per component (sums to m) by systematic resampling."""
    c = np.cumsum(p / p.sum())
    u = (np.arange(m) + 0.5) / m
    idx = np.searchsorted(c, u, side="right")
    idx = np.minimum(idx, len(p) - 1)
    return np.bincount(idx, minlength=len(p))


def eig_spice(
    comp_logpost: np.ndarray,  # (C,) log posterior of (hypothesis, component)
    comp_group: np.ndarray,  # (C,) group index
    n_groups: int,
    mean: np.ndarray,  # (C, J)
    var: np.ndarray,  # (C, J)
    n_samples: int,
    rng: np.random.Generator,
    posterior_fn: Callable[[int, np.ndarray], np.ndarray] | None = None,
) -> np.ndarray:
    """EIG (bits) over groups for each of J candidate dims.

    ``posterior_fn(j, samples) -> (M, n_groups)`` overrides the Gaussian update
    (used by the discriminative model); by default the generative update is used.
    """
    p = np.exp(comp_logpost - comp_logpost.max())
    p /= p.sum()
    keep = p > 1e-7
    p_k, lp_k, g_k = p[keep], np.log(p[keep]), comp_group[keep]
    mean_k, var_k = mean[keep], var[keep]
    prior_groups = np.zeros(n_groups)
    np.add.at(prior_groups, g_k, p_k)
    h0 = entropy(prior_groups)
    if h0 <= 1e-9:
        return np.zeros(mean.shape[1])
    alloc = systematic_allocation(p_k, n_samples)
    src = np.repeat(np.arange(len(p_k)), alloc)  # (M,)
    J = mean.shape[1]
    out = np.zeros(J)
    sd_k = np.sqrt(var_k)
    for j in range(J):
        samples = mean_k[src, j] + sd_k[src, j] * rng.standard_normal(len(src))
        if posterior_fn is not None:
            G = posterior_fn(j, samples)
        else:
            z = (samples[:, None] - mean_k[None, :, j]) / sd_k[None, :, j]
            ll = lp_k[None, :] - 0.5 * z * z - np.log(sd_k[None, :, j])
            ll -= ll.max(axis=1, keepdims=True)
            w = np.exp(ll)
            w /= w.sum(axis=1, keepdims=True)
            G = np.zeros((len(samples), n_groups))
            for gi in np.unique(g_k):
                G[:, gi] = w[:, g_k == gi].sum(axis=1)
        out[j] = h0 - float(entropy_rows(G).mean())
    return np.maximum(out, 0.0)


def eig_lift(
    hyp_post: np.ndarray, hyp_refs: list[str], hyp_group: np.ndarray, n_groups: int, ref: str
) -> float:
    """Exact EIG over groups for a binary out-of-circuit test of component ``ref``."""
    is_ref = np.array([r == ref for r in hyp_refs])
    p_def = np.where(is_ref, LIFT_SENSITIVITY, 1.0 - LIFT_SPECIFICITY)
    prior_g = np.zeros(n_groups)
    np.add.at(prior_g, hyp_group, hyp_post)
    h0 = entropy(prior_g)
    total = 0.0
    for lik in (p_def, 1.0 - p_def):
        joint = hyp_post * lik
        pz = joint.sum()
        if pz <= 0:
            continue
        g = np.zeros(n_groups)
        np.add.at(g, hyp_group, joint / pz)
        total += pz * entropy(g)
    return max(h0 - total, 0.0)


def rank(cands: list[Candidate]) -> list[Candidate]:
    """Highest score first; near-ties go to low-voltage, then cheaper, then by key."""
    if not cands:
        return []
    best = max(c.score for c in cands)

    def keyf(c: Candidate) -> tuple[int, int, float, float, str]:
        near_top = c.score >= best - TIE_TOL * max(best, 1e-12)
        return (0 if near_top else 1, int(c.obs.hv), c.obs.cost, -c.score, c.obs.key)

    top = sorted([c for c in cands if c.score >= best - TIE_TOL * max(best, 1e-12)], key=keyf)
    rest = sorted([c for c in cands if c not in top], key=lambda c: -c.score)
    return top + rest
