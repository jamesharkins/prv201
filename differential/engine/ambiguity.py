"""Ambiguity groups: hypotheses that stay indistinguishable with every test point measured.

Method (brief §2.3, "classifier confusion" variant): for each validation draw of
hypothesis i, simulate one noisy reading of every test-point observable, compute
the posterior over all hypotheses under the generative model with a uniform
prior, and accumulate the mean posterior mass C[i, j] the draw assigns to j.
Pairs whose symmetric confusion (C[i, j] + C[j, i]) / 2 is at least ``threshold``
are linked, and groups are the connected components of that graph. Lift tests
are excluded: a group can often be split by lifting a part (cost 10), which the
agent offers as an optional next step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from differential.engine.data import EngineData
from differential.engine.generative import GenerativeModel
from differential.sim.measurement import engine_noise_sd

DEFAULT_THRESHOLD = 0.10


@dataclass
class AmbiguityGroups:
    hypotheses: list[str]
    group_of: np.ndarray  # (H,) group index per hypothesis
    confusion: np.ndarray  # (H, H) mean posterior mass
    threshold: float

    @property
    def n_groups(self) -> int:
        return int(self.group_of.max()) + 1 if len(self.group_of) else 0

    def members(self, g: int) -> list[str]:
        return [h for h, gi in zip(self.hypotheses, self.group_of, strict=True) if gi == g]

    def group_mass(self, posterior: np.ndarray) -> np.ndarray:
        out = np.zeros(self.n_groups)
        np.add.at(out, self.group_of, posterior[: len(self.group_of)])
        return out

    def nontrivial(self) -> list[list[str]]:
        return [m for g in range(self.n_groups) if len(m := self.members(g)) > 1]

    def to_json(self) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "hypotheses": self.hypotheses,
            "group_of": self.group_of.tolist(),
            "groups": [self.members(g) for g in range(self.n_groups)],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=1))
        np.save(path.with_suffix(".confusion.npy"), self.confusion.astype(np.float32))

    @classmethod
    def load(cls, path: Path) -> AmbiguityGroups:
        d = json.loads(path.read_text())
        conf_path = path.with_suffix(".confusion.npy")
        conf = np.load(conf_path) if conf_path.exists() else np.zeros((0, 0))
        return cls(d["hypotheses"], np.array(d["group_of"], dtype=np.int64), conf, d["threshold"])


def confusion_matrix(
    model: GenerativeModel, data: EngineData, rng: np.random.Generator, per_hyp: int = 40
) -> np.ndarray:
    H = model.n_hyp
    idx = np.arange(len(model.keys))
    conf = np.zeros((H, H))
    counts = np.zeros(H)
    for h in range(H):
        rows = np.flatnonzero(data.y == h)
        if len(rows) == 0:
            continue
        pick = rng.choice(rows, size=min(per_hyp, len(rows)), replace=False)
        for r in pick:
            x = data.X[r].copy()
            for j, k in enumerate(model.kinds):
                x[j] += rng.normal(0.0, engine_noise_sd(k, x[j]))
            ll = model.loglik_fast(model.component_loglik(x, idx))
            p = np.exp(ll - ll.max())
            conf[h] += p / p.sum()
            counts[h] += 1
    counts[counts == 0] = 1
    return conf / counts[:, None]


def build_groups(
    model: GenerativeModel,
    data: EngineData,
    threshold: float = DEFAULT_THRESHOLD,
    seed: int = 0,
    per_hyp: int = 40,
) -> AmbiguityGroups:
    rng = np.random.default_rng(seed)
    conf = confusion_matrix(model, data, rng, per_hyp=per_hyp)
    sym = 0.5 * (conf + conf.T)
    adj = csr_matrix(sym >= threshold)
    _, labels = connected_components(adj, directed=False)
    # Relabel groups in order of first member for stable output.
    order: dict[int, int] = {}
    group_of = np.array([order.setdefault(int(lbl), len(order)) for lbl in labels], dtype=np.int64)
    return AmbiguityGroups(list(model.hypotheses), group_of, conf, threshold)


def singleton_groups(hypotheses: list[str]) -> AmbiguityGroups:
    H = len(hypotheses)
    return AmbiguityGroups(list(hypotheses), np.arange(H), np.eye(H), 1.0)
