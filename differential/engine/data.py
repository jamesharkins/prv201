"""Engine-space datasets built from the Monte Carlo cache."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from differential.circuits.library import get_circuit
from differential.sim.faults import fault_catalog
from differential.sim.measurement import (
    DC_SCALE,
    GAIN_FLOOR,
    HUM_FLOOR,
    THD_FLOOR,
    THD_MIN_FUNDAMENTAL,
    THD_NO_SIGNAL,
)
from differential.sim.observables import ObservableSpec, spice_observables


def transform_column(kind: str, values: np.ndarray, fundamental: np.ndarray | None) -> np.ndarray:
    v = np.asarray(values, dtype=np.float64)
    if kind == "dc":
        return np.asarray(np.arcsinh(v / DC_SCALE))
    if kind in ("ac", "ac20", "ac20k"):
        return np.asarray(20.0 * np.log10(np.sqrt(np.clip(v, 0, None) ** 2 + GAIN_FLOOR**2)))
    if kind == "hum":
        return np.asarray(20.0 * np.log10(np.sqrt(np.clip(v, 0, None) ** 2 + HUM_FLOOR**2)))
    if kind == "thd":
        out = np.clip(v, THD_FLOOR, THD_NO_SIGNAL)
        if fundamental is not None:
            f = np.asarray(fundamental, dtype=np.float64)
            no_sig = ~np.isfinite(f) | (f < THD_MIN_FUNDAMENTAL)
            out = np.where(no_sig, THD_NO_SIGNAL, out)
        return np.asarray(np.log10(out))
    raise ValueError(kind)


def to_engine_matrix(df: pd.DataFrame, observables: list[ObservableSpec]) -> np.ndarray:
    fund = df["fundamental"].to_numpy() if "fundamental" in df.columns else None
    cols = [transform_column(o.kind, df[o.key].to_numpy(), fund) for o in observables]
    return np.column_stack(cols) if cols else np.zeros((len(df), 0))


@dataclass
class EngineData:
    circuit_id: str
    hypotheses: list[str]
    observables: list[ObservableSpec]
    X: np.ndarray  # (n, D) engine space, noise-free simulation
    y: np.ndarray  # (n,) hypothesis index into ``hypotheses``
    draw: np.ndarray  # (n,)
    frame: pd.DataFrame

    @property
    def keys(self) -> list[str]:
        return [o.key for o in self.observables]

    @property
    def kinds(self) -> list[str]:
        return [o.kind for o in self.observables]


def build_engine_data(
    circuit_id: str, df: pd.DataFrame, max_draws: int | None = None
) -> EngineData:
    circuit = get_circuit(circuit_id)
    hyps = [f.id for f in fault_catalog(circuit)]
    index = {h: i for i, h in enumerate(hyps)}
    obs = spice_observables(circuit)
    d = df[df["ok"]].copy()
    d = d[d["hypothesis"].isin(index)]
    if max_draws is not None:
        d = d[d["draw"] < max_draws]
    d = d.sort_values(["hyp_index", "draw"], kind="stable").reset_index(drop=True)
    X = to_engine_matrix(d, obs)
    y = d["hypothesis"].map(index).to_numpy(dtype=np.int64)
    return EngineData(circuit_id, hyps, obs, X, y, d["draw"].to_numpy(), d)
