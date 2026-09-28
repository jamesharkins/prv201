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

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from differential.sim.measurement import LIFT_SENSITIVITY, LIFT_SPECIFICITY
from differential.sim.observables import ObservableSpec

TIE_TOL = 1e-3
LOG_2PI = math.log(2.0 * math.pi)


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


@dataclass(frozen=True)
class UnmodeledTerm:
    """The "no single fault fits" hypothesis U in the EIG computation.

    ``log_mass`` is U's log posterior mass on the same scale as the component
    log masses; under U a new reading of dim j has the flat likelihood level
    ``loglik[j]`` (the posterior's calibrated level) and is drawn uniformly from
    ``center[j] +- width[j] / 2`` when sampling the predictive.
    """

    log_mass: float
    loglik: np.ndarray  # (J,)
    center: np.ndarray  # (J,)
    width: np.ndarray  # (J,)


def eig_spice(
    comp_logpost: np.ndarray,  # (C,) log posterior of (hypothesis, component)
    comp_group: np.ndarray,  # (C,) group index
    n_groups: int,
    mean: np.ndarray,  # (C, J)
    var: np.ndarray,  # (C, J)
    n_samples: int,
    rng: np.random.Generator,
    posterior_fn: Callable[[int, np.ndarray], np.ndarray] | None = None,
    unmodeled: UnmodeledTerm | None = None,
) -> np.ndarray:
    """EIG (bits) for each of J candidate dims over the groups and, when given, U.

    ``posterior_fn(j, samples) -> (M, n_groups)`` overrides the Gaussian update
    among the modeled groups (used by the discriminative model); the split
    between U and the modeled faults always uses the generative update, as the
    posterior does. Without U, a session whose catalogued suspects all agree
    would see no informative measurement even while U holds most of the mass.
    """
    lp_all = comp_logpost if unmodeled is None else np.append(comp_logpost, unmodeled.log_mass)
    p = np.exp(lp_all - lp_all.max())
    p /= p.sum()
    C = len(comp_logpost)
    keep = p[:C] > 1e-7
    p_k, g_k = p[:C][keep], comp_group[keep]
    lp_k = np.log(p_k)
    p_u = float(p[-1]) if unmodeled is not None else 0.0
    use_u = unmodeled is not None and p_u > 1e-7
    mean_k, var_k = mean[keep], var[keep]
    prior_groups = np.zeros(n_groups + 1)
    np.add.at(prior_groups, g_k, p_k)
    prior_groups[-1] = p_u if use_u else 0.0
    h0 = entropy(prior_groups)
    if h0 <= 1e-9:
        return np.zeros(mean.shape[1])
    src_p = np.append(p_k, p_u) if use_u else p_k
    alloc = systematic_allocation(src_p, n_samples)
    src = np.repeat(np.arange(len(src_p)), alloc)  # (M,)
    from_u = src == len(p_k)  # samples drawn from U's predictive
    src_c = np.where(from_u, 0, src)
    J = mean.shape[1]
    out = np.zeros(J)
    sd_k = np.sqrt(var_k)
    for j in range(J):
        samples = mean_k[src_c, j] + sd_k[src_c, j] * rng.standard_normal(len(src))
        if use_u:
            assert unmodeled is not None
            n_u = int(from_u.sum())
            samples[from_u] = unmodeled.center[j] + unmodeled.width[j] * (rng.random(n_u) - 0.5)
        z = (samples[:, None] - mean_k[None, :, j]) / sd_k[None, :, j]
        ll = lp_k[None, :] - 0.5 * z * z - np.log(sd_k[None, :, j]) - 0.5 * LOG_2PI
        if use_u:
            assert unmodeled is not None
            ll_u = np.full((len(samples), 1), math.log(p_u) + float(unmodeled.loglik[j]))
            ll = np.concatenate([ll, ll_u], axis=1)
        ll -= ll.max(axis=1, keepdims=True)
        w = np.exp(ll)
        w /= w.sum(axis=1, keepdims=True)
        G = np.zeros((len(samples), n_groups + 1))
        if posterior_fn is not None:
            G[:, :n_groups] = posterior_fn(j, samples) * (1.0 - w[:, -1:] if use_u else 1.0)
        else:
            for gi in np.unique(g_k):
                G[:, gi] = w[:, : len(p_k)][:, g_k == gi].sum(axis=1)
        if use_u:
            G[:, -1] = w[:, -1]
        out[j] = h0 - float(entropy_rows(G).mean())
    return np.maximum(out, 0.0)


def eig_lift(
    hyp_post: np.ndarray, hyp_refs: list[str], hyp_group: np.ndarray, n_groups: int, ref: str,
    p_unmodeled: float = 0.0, p_def_unmodeled: float = 0.0,
) -> float:
    """Exact EIG over groups (and U) for a binary out-of-circuit test of ``ref``.

    ``hyp_post`` holds the modeled hypotheses' share of the posterior; U holds
    ``p_unmodeled`` and makes the lifted part read defective with probability
    ``p_def_unmodeled``.
    """
    is_ref = np.array([r == ref for r in hyp_refs])
    p_def = np.append(np.where(is_ref, LIFT_SENSITIVITY, 1.0 - LIFT_SPECIFICITY), p_def_unmodeled)
    post = np.append(np.asarray(hyp_post) * (1.0 - p_unmodeled), p_unmodeled)
    group = np.append(hyp_group, n_groups)
    prior_g = np.zeros(n_groups + 1)
    np.add.at(prior_g, group, post)
    h0 = entropy(prior_g)
    total = 0.0
    for lik in (p_def, 1.0 - p_def):
        joint = post * lik
        pz = joint.sum()
        if pz <= 0:
            continue
        g = np.zeros(n_groups + 1)
        np.add.at(g, group, joint / pz)
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
