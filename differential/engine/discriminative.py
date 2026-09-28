"""Discriminative likelihood model: gradient-boosted classifier (brief §2.3).

Training rows are Monte Carlo samples with simulated instrument noise, replicated
``n_masks`` times with a random subset of observables hidden (set to NaN; the
per-row keep probability is drawn from U(0.05, 0.95)), so the classifier learns
p(h | any subset of measurements). LightGBM routes missing values natively.
Probabilities are calibrated by temperature scaling on masked validation rows
(Guo et al., 2017). The classifier's implicit prior is uniform over the catalog,
so a symptom prior is applied by multiplying and renormalising.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import log_softmax

from differential.engine.data import EngineData
from differential.sim.measurement import engine_noise_sd


def add_noise(X: np.ndarray, kinds: list[str], rng: np.random.Generator) -> np.ndarray:
    out = X.copy()
    for j, k in enumerate(kinds):
        sd = np.array([engine_noise_sd(k, float(t)) for t in X[:, j]]) if k == "dc" else \
            np.full(len(X), engine_noise_sd(k, 0.0))
        out[:, j] += rng.normal(0.0, 1.0, len(X)) * sd
    return out


KEEP_P_RANGE = (0.05, 0.95)  # per-row probability that a reading is kept
LGB_PARAMS = {"learning_rate": 0.08, "num_leaves": 15, "min_data_in_leaf": 20,
              "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0}
EARLY_STOPPING_ROUNDS = 20


def random_masks(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    keep_p = rng.uniform(*KEEP_P_RANGE, size=(n, 1))
    mask = rng.uniform(size=(n, d)) < keep_p
    return mask


def masked_rows(
    data: EngineData, n_masks: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    Xs, ys = [], []
    for _ in range(n_masks):
        Xn = add_noise(data.X, data.kinds, rng)
        m = random_masks(len(Xn), Xn.shape[1], rng)
        Xn[~m] = np.nan
        Xs.append(Xn)
        ys.append(data.y)
    return np.vstack(Xs), np.concatenate(ys)


@dataclass
class DiscriminativeModel:
    circuit_id: str
    hypotheses: list[str]
    keys: list[str]
    booster_text: str
    temperature: float = 1.0
    _booster: object | None = None

    @property
    def booster(self):  # type: ignore[no-untyped-def]
        if self._booster is None:
            import lightgbm as lgb

            self._booster = lgb.Booster(model_str=self.booster_text)
        return self._booster

    @classmethod
    def fit(
        cls,
        train: EngineData,
        val: EngineData,
        n_masks: int = 3,
        seed: int = 0,
        num_boost_round: int = 300,
        num_threads: int = 4,
    ) -> DiscriminativeModel:
        import lightgbm as lgb

        rng = np.random.default_rng(seed)
        Xtr, ytr = masked_rows(train, n_masks, rng)
        Xva, yva = masked_rows(val, 1, rng)
        params = {
            "objective": "multiclass",
            "num_class": len(train.hypotheses),
            **LGB_PARAMS,
            "verbose": -1,
            "seed": seed,
            "deterministic": True,
            "force_row_wise": True,
            "num_threads": num_threads,
        }
        dtr = lgb.Dataset(Xtr, label=ytr, free_raw_data=True)
        dva = lgb.Dataset(Xva, label=yva, reference=dtr)
        booster = lgb.train(
            params,
            dtr,
            num_boost_round=num_boost_round,
            valid_sets=[dva],
            callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False)],
        )
        model = cls(train.circuit_id, list(train.hypotheses), train.keys,
                    booster.model_to_string(), 1.0, booster)
        # Temperature scaling on masked validation rows.
        raw = model._raw_logits(Xva)
        yv = yva

        def nll(t: float) -> float:
            lp = log_softmax(raw / t, axis=1)
            return float(-lp[np.arange(len(yv)), yv].mean())

        res = minimize_scalar(nll, bounds=(0.3, 5.0), method="bounded")
        model.temperature = float(res.x)
        return model

    def _raw_logits(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self.booster.predict(X, raw_score=True))

    def log_proba(self, X: np.ndarray) -> np.ndarray:
        """Calibrated log p(h | observed features); NaN marks unmeasured features."""
        raw = self._raw_logits(np.atleast_2d(X))
        return np.asarray(log_softmax(raw / self.temperature, axis=1))

    def row(self, values: dict[int, float]) -> np.ndarray:
        x = np.full(len(self.keys), np.nan)
        for j, v in values.items():
            x[j] = v
        return x

    # ------------------------------------------------------------- storage
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "circuit_id": self.circuit_id,
            "hypotheses": self.hypotheses,
            "keys": self.keys,
            "temperature": self.temperature,
        }
        text = json.dumps(meta) + "\n" + self.booster_text
        if path.suffix == ".gz":  # the trained trees compress about tenfold
            path.write_bytes(gzip.compress(text.encode(), mtime=0))
        else:
            path.write_text(text)

    @classmethod
    def load(cls, path: Path) -> DiscriminativeModel:
        text = gzip.decompress(path.read_bytes()).decode() if path.suffix == ".gz" \
            else path.read_text()
        head, body = text.split("\n", 1)
        meta = json.loads(head)
        return cls(meta["circuit_id"], meta["hypotheses"], meta["keys"], body,
                   float(meta["temperature"]))


def log_uniform(n: int) -> float:
    return -math.log(n)
