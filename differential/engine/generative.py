"""Generative likelihood model: one Gaussian mixture per hypothesis (brief §2.3).

Fitting: for each hypothesis, Gaussian mixtures with 1-3 full-covariance
components are fitted to the noise-free Monte Carlo samples in engine space and
the component count is chosen by BIC. Each component covariance is then
convolved with the instrument noise evaluated at the component mean (the
measurement model is Gaussian in engine space, so convolution adds its
variance) and a per-kind variance floor is added (ADR-008).

Inference: unmeasured observables are marginalised by dropping their rows and
columns (exact for Gaussians). Predictive distributions for candidate
measurements are the Gaussian conditionals given what has been measured, with
component weights updated by the evidence.
"""

from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from sklearn.mixture import GaussianMixture

from differential.engine.data import EngineData
from differential.sim.measurement import VAR_FLOOR, engine_noise_sd

LOG_2PI = math.log(2.0 * math.pi)
MIN_SAMPLES_PER_COMPONENT = 25  # a k-component mixture needs at least 25 k draws
REG_COVAR = 1e-5
EM_MAX_ITER = 300


def _fit_one(args: tuple[np.ndarray, int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    X, max_k, seed = args
    n = len(X)
    best: tuple[float, GaussianMixture] | None = None
    for k in range(1, max_k + 1):
        if n < MIN_SAMPLES_PER_COMPONENT * k:
            break
        gm = GaussianMixture(
            n_components=k,
            covariance_type="full",
            reg_covar=REG_COVAR,
            n_init=2 if k > 1 else 1,
            random_state=seed,
            max_iter=EM_MAX_ITER,
        )
        gm.fit(X)
        bic = float(gm.bic(X))
        if best is None or bic < best[0]:
            best = (bic, gm)
    if best is None:  # too few samples: moment estimate
        mean = X.mean(axis=0, keepdims=True)
        cov = np.cov(X.T).reshape(1, X.shape[1], X.shape[1]) + REG_COVAR * np.eye(X.shape[1])
        return np.array([1.0]), mean, cov, 1
    gm = best[1]
    return gm.weights_, gm.means_, gm.covariances_, gm.n_components


@dataclass
class GenerativeModel:
    circuit_id: str
    hypotheses: list[str]
    keys: list[str]
    kinds: list[str]
    comp_hyp: np.ndarray  # (C,) hypothesis index of each component
    comp_logw: np.ndarray  # (C,) log mixture weight within its hypothesis
    comp_mean: np.ndarray  # (C, D)
    comp_cov: np.ndarray  # (C, D, D) including measurement noise and floor
    unmod_width: np.ndarray  # (D,) support width for the unmodeled density
    unmod_offset: float = 0.0  # calibrated log-density offset per observed dimension
    # Offset for sessions whose prior carries no complaint information (uniform or
    # folklore prior): a complaint concentrates the prior on consistent faults, so
    # the two regimes need separately calibrated levels (ADR-029). NaN = same.
    unmod_offset_nocomplaint: float = float("nan")
    n_train: int = 0

    # ------------------------------------------------------------------ fit
    @classmethod
    def fit(
        cls,
        data: EngineData,
        max_components: int = 3,
        seed: int = 0,
        workers: int = 1,
    ) -> GenerativeModel:
        H = len(data.hypotheses)
        tasks = []
        for h in range(H):
            Xh = data.X[data.y == h]
            if len(Xh) == 0:
                raise ValueError(f"no training samples for {data.hypotheses[h]}")
            tasks.append((Xh, max_components, seed + h))
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                fits = list(pool.map(_fit_one, tasks, chunksize=4))
        else:
            fits = [_fit_one(t) for t in tasks]
        kinds = data.kinds
        D = len(kinds)
        floor = np.array([VAR_FLOOR[k] for k in kinds])
        comp_hyp, comp_logw, comp_mean, comp_cov = [], [], [], []
        for h, (w, mu, cov, _k) in enumerate(fits):
            for c in range(len(w)):
                noise = np.array([engine_noise_sd(kinds[j], float(mu[c, j])) ** 2 for j in range(D)])
                comp_hyp.append(h)
                comp_logw.append(math.log(max(float(w[c]), 1e-12)))
                comp_mean.append(mu[c])
                comp_cov.append(cov[c] + np.diag(noise + floor))
        lo = data.X.min(axis=0)
        hi = data.X.max(axis=0)
        max_noise = np.array(
            [max(engine_noise_sd(kinds[j], float(lo[j])), engine_noise_sd(kinds[j], float(hi[j])))
             for j in range(D)]
        )
        width = (hi - lo) * 1.2 + 6.0 * max_noise + 1e-6
        return cls(
            circuit_id=data.circuit_id,
            hypotheses=list(data.hypotheses),
            keys=data.keys,
            kinds=kinds,
            comp_hyp=np.array(comp_hyp, dtype=np.int64),
            comp_logw=np.array(comp_logw),
            comp_mean=np.array(comp_mean),
            comp_cov=np.array(comp_cov),
            unmod_width=width,
            n_train=len(data.X),
        )

    # ------------------------------------------------------------ inference
    @property
    def n_hyp(self) -> int:
        return len(self.hypotheses)

    def key_index(self, keys: list[str]) -> np.ndarray:
        pos = {k: i for i, k in enumerate(self.keys)}
        return np.array([pos[k] for k in keys], dtype=np.int64)

    def component_loglik(self, x: np.ndarray, idx: np.ndarray) -> np.ndarray:
        """log w_c + log N(x_S; mu_cS, Sigma_cSS) for every component c."""
        if len(idx) == 0:
            return self.comp_logw.copy()
        mu = self.comp_mean[:, idx]
        cov = self.comp_cov[:, idx][:, :, idx]
        L = np.linalg.cholesky(cov)
        diff = (x[None, :] - mu)[..., None]
        z = np.linalg.solve(L, diff)[..., 0]
        maha = np.einsum("ci,ci->c", z, z)
        logdet = 2.0 * np.log(np.diagonal(L, axis1=1, axis2=2)).sum(axis=1)
        return np.asarray(self.comp_logw - 0.5 * (maha + logdet + len(idx) * LOG_2PI))

    def loglik(self, x: np.ndarray, idx: np.ndarray) -> np.ndarray:
        """log p(x_S | h) for every hypothesis h."""
        cl = self.component_loglik(x, idx)
        out = np.full(self.n_hyp, -np.inf)
        for h in range(self.n_hyp):
            sel = self.comp_hyp == h
            out[h] = logsumexp(cl[sel])
        return out

    def loglik_fast(self, cl: np.ndarray) -> np.ndarray:
        """Per-hypothesis log-likelihood from component log-likelihoods."""
        m = np.full(self.n_hyp, -np.inf)
        np.maximum.at(m, self.comp_hyp, cl)
        safe = np.where(np.isfinite(m), m, 0.0)
        s = np.zeros(self.n_hyp)
        np.add.at(s, self.comp_hyp, np.exp(cl - safe[self.comp_hyp]))
        with np.errstate(divide="ignore"):
            return safe + np.log(s)

    def predictive(
        self, x: np.ndarray, idx: np.ndarray, cand: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Conditional predictive of candidate dims given the observed ones.

        Returns (component log-likelihood of the evidence incl. weight, cond. mean
        (C, J), cond. variance (C, J)).
        """
        cl = self.component_loglik(x, idx)
        mu_c = self.comp_mean[:, cand]
        var_c = np.diagonal(self.comp_cov, axis1=1, axis2=2)[:, cand]
        if len(idx) == 0:
            return cl, mu_c, var_c
        cov_SS = self.comp_cov[:, idx][:, :, idx]
        cov_SJ = self.comp_cov[:, idx][:, :, cand]
        L = np.linalg.cholesky(cov_SS)
        z = np.linalg.solve(L, (x[None, :] - self.comp_mean[:, idx])[..., None])[..., 0]
        B = np.linalg.solve(L, cov_SJ)  # (C, s, J)
        mean = mu_c + np.einsum("csj,cs->cj", B, z)
        var = var_c - np.einsum("csj,csj->cj", B, B)
        return cl, mean, np.maximum(var, 1e-10)

    @property
    def unmod_center(self) -> np.ndarray:
        """Centre of U's support per dimension: midpoint of the component means' range
        (U's width already spans the training data range with a margin)."""
        return np.asarray((self.comp_mean.min(axis=0) + self.comp_mean.max(axis=0)) / 2.0)

    def unmodeled_loglik(self, idx: np.ndarray) -> float:
        return self.unmodeled_loglik_at(idx, self.unmod_offset)

    def offset_for(self, complaint: bool) -> float:
        """Calibrated offset for a session with (or without) a complaint prior."""
        if complaint or math.isnan(self.unmod_offset_nocomplaint):
            return self.unmod_offset
        return self.unmod_offset_nocomplaint

    def unmodeled_loglik_at(self, idx: np.ndarray, offset: float) -> float:
        return float(-np.log(self.unmod_width[idx]).sum() + offset * len(idx))

    # ------------------------------------------------------------- storage
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            circuit_id=self.circuit_id,
            hypotheses=np.array(self.hypotheses),
            keys=np.array(self.keys),
            kinds=np.array(self.kinds),
            comp_hyp=self.comp_hyp,
            comp_logw=self.comp_logw,
            comp_mean=self.comp_mean.astype(np.float64),
            comp_cov=self.comp_cov.astype(np.float64),
            unmod_width=self.unmod_width,
            unmod_offset=np.array(self.unmod_offset),
            unmod_offset_nocomplaint=np.array(self.unmod_offset_nocomplaint),
            n_train=np.array(self.n_train),
        )

    @classmethod
    def load(cls, path: Path) -> GenerativeModel:
        z = np.load(path, allow_pickle=False)
        return cls(
            circuit_id=str(z["circuit_id"]),
            hypotheses=[str(h) for h in z["hypotheses"]],
            keys=[str(k) for k in z["keys"]],
            kinds=[str(k) for k in z["kinds"]],
            comp_hyp=z["comp_hyp"],
            comp_logw=z["comp_logw"],
            comp_mean=z["comp_mean"],
            comp_cov=z["comp_cov"],
            unmod_width=z["unmod_width"],
            unmod_offset=float(z["unmod_offset"]),
            unmod_offset_nocomplaint=float(z["unmod_offset_nocomplaint"])
            if "unmod_offset_nocomplaint" in z.files else float("nan"),
            n_train=int(z["n_train"]),
        )
