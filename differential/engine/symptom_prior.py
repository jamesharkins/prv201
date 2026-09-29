"""Symptom facts from simulated observables and the physics-derived symptom prior (§2.4).

1. ``SymptomReference`` holds healthy-unit statistics for a circuit (medians and
   spreads of the output level, hum, THD and every DC test point) computed from
   as-new healthy training draws.
2. ``derive_facts`` turns one simulated unit into symptom facts with fixed,
   documented thresholds (ADR-012), e.g. "output down more than 30 dB" ->
   no output; "down 3-30 dB" -> low gain.
3. ``SymptomModel`` learns P(feature | fault) as the fraction of that fault's
   Monte Carlo draws showing the feature, and turns a reported symptom set into
   a prior over faults:
       log L(h) = sum_{reported f} log(eps + (1 - 2 eps) P(f | h))
                + lam * sum_{unreported f} log(eps + (1 - 2 eps) (1 - P(f | h)))
   eps and lam are fitted on validation data. The language model only extracts
   which symptoms were reported; every number comes from simulation.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from differential.circuits.library import get_circuit
from differential.circuits.model import CircuitSpec
from differential.engine.data import transform_column
from differential.sim.faults import fault_catalog
from differential.sim.measurement import HUM_FLOOR, THD_MIN_FUNDAMENTAL

FEATURES = (
    "no_output",
    "low_gain",
    "hum",
    "distortion",
    "dc_at_output",
    "bias_drift",
    "bass_loss",
    "treble_loss",
)
NO_OUTPUT_DB = -30.0
LOW_GAIN_DB = -3.0
HUM_MARGIN_DB = 6.0
HUM_FLOOR_DBV = 20.0 * math.log10(HUM_FLOOR)
DIST_FACTOR = 3.0
DIST_MIN_PCT = 1.0
DC_OUT_V = 0.1
BIAS_REL = 0.10
RESPONSE_DB = 3.0
RAIL_DEAD_FRAC = 0.5
RAIL_DRIFT_REL = 0.05


def _output_tp(circuit: CircuitSpec) -> str | None:
    if circuit.signal is None:
        return None
    for tp in circuit.test_points:
        if tp.node == circuit.signal.output_node:
            return tp.id
    return None


@dataclass
class SymptomReference:
    circuit_id: str
    out_tp: str | None
    rail_tps: list[str]
    dc_median: dict[str, float]
    dc_halfspread: dict[str, float]
    gain_db: dict[str, float]  # kind -> healthy median output gain (dB)
    hum_p99_dbv: dict[str, float]
    thd_median: float | None

    @classmethod
    def from_healthy(cls, circuit: CircuitSpec, healthy: pd.DataFrame) -> SymptomReference:
        out_tp = _output_tp(circuit)
        rail_tps = [tp.id for tp in circuit.test_points if tp.node in ("vreg", "bplus")]
        dc_med, dc_hs = {}, {}
        for tp in circuit.test_points:
            if "dc" in tp.measurements:
                v = healthy[f"dc:{tp.id}"].to_numpy(dtype=float)
                dc_med[tp.id] = float(np.median(v))
                dc_hs[tp.id] = float((np.percentile(v, 99) - np.percentile(v, 1)) / 2.0)
        gain_db: dict[str, float] = {}
        hum_p99: dict[str, float] = {}
        thd_med = None
        if out_tp is not None:
            for kind in ("ac", "ac20", "ac20k"):
                col = f"{kind}:{out_tp}"
                if col in healthy.columns:
                    gain_db[kind] = float(np.median(transform_column(kind, healthy[col].to_numpy(), None)))
            if f"thd:{out_tp}" in healthy.columns:
                thd_med = float(np.median(healthy[f"thd:{out_tp}"].to_numpy(dtype=float)))
        for tp in circuit.test_points:
            col = f"hum:{tp.id}"
            if col in healthy.columns and (tp.id == out_tp or tp.id in rail_tps):
                hum_p99[tp.id] = float(np.percentile(transform_column("hum", healthy[col].to_numpy(), None), 99))
        return cls(circuit.id, out_tp, rail_tps, dc_med, dc_hs, gain_db, hum_p99, thd_med)

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> SymptomReference:
        return cls(**d)


@dataclass
class SymptomFacts:
    features: dict[str, bool]
    severity: str
    output_change_db: float | None
    hum_rise_db: float | None
    thd_pct: float | None
    output_dc_v: float | None
    drift_tps: list[str] = field(default_factory=list)
    stage_hint: str | None = None

    @property
    def any(self) -> bool:
        return any(self.features.values())

    def classes(self) -> list[str]:
        return [f for f in FEATURES if self.features.get(f) and f not in ("bass_loss", "treble_loss")]


def derive_facts(circuit: CircuitSpec, ref: SymptomReference, row: pd.Series) -> SymptomFacts:
    """Symptom facts for one simulated unit (noise-free observables in natural units)."""
    f = dict.fromkeys(FEATURES, False)
    out_db = hum_rise = thd = out_dc = None
    drift: list[str] = []
    fund = float(row.get("fundamental", np.nan))
    if ref.out_tp is not None:
        g = float(transform_column("ac", np.array([row[f"ac:{ref.out_tp}"]]), None)[0])
        out_db = g - ref.gain_db["ac"]
        if out_db < NO_OUTPUT_DB:
            f["no_output"] = True
        elif out_db < LOW_GAIN_DB:
            f["low_gain"] = True
        for kind, feat in (("ac20", "bass_loss"), ("ac20k", "treble_loss")):
            if kind in ref.gain_db and not f["no_output"]:
                gk = float(transform_column(kind, np.array([row[f"{kind}:{ref.out_tp}"]]), None)[0])
                if (gk - ref.gain_db[kind]) - out_db < -RESPONSE_DB:
                    f[feat] = True
        if ref.thd_median is not None and f"thd:{ref.out_tp}" in row.index:
            thd = float(row[f"thd:{ref.out_tp}"])
            if (
                math.isfinite(fund)
                and fund >= THD_MIN_FUNDAMENTAL
                and not f["no_output"]
                and thd > max(DIST_FACTOR * ref.thd_median, DIST_MIN_PCT)
            ):
                f["distortion"] = True
        if f"dc:{ref.out_tp}" in row.index:
            out_dc = float(row[f"dc:{ref.out_tp}"])
            if abs(out_dc) > DC_OUT_V:
                f["dc_at_output"] = True
    else:
        # Power-supply block: the rails are its outputs.
        for tp in ref.rail_tps:
            v, med = float(row[f"dc:{tp}"]), ref.dc_median[tp]
            if v < RAIL_DEAD_FRAC * med:
                f["no_output"] = True
            elif abs(v - med) > RAIL_DRIFT_REL * med:
                f["bias_drift"] = True
                drift.append(tp)
    for tp, p99 in ref.hum_p99_dbv.items():
        h = float(transform_column("hum", np.array([row[f"hum:{tp}"]]), None)[0])
        rise = h - max(p99, HUM_FLOOR_DBV)
        if h > p99 + HUM_MARGIN_DB and h > HUM_FLOOR_DBV + HUM_MARGIN_DB:
            f["hum"] = True
        hum_rise = rise if hum_rise is None else max(hum_rise, rise)
    if ref.out_tp is not None:
        for tp, med in ref.dc_median.items():
            if tp == ref.out_tp:
                continue
            v = float(row[f"dc:{tp}"])
            tol = max(BIAS_REL * abs(med), 3.0 * ref.dc_halfspread[tp], 0.05)
            if abs(v - med) > tol:
                drift.append(tp)
        if drift and not f["no_output"]:
            f["bias_drift"] = True
    severity = "mild"
    if f["no_output"] or (hum_rise is not None and hum_rise > 20.0 and f["hum"]):
        severity = "severe"
    elif (out_db is not None and out_db < -10.0) or (thd is not None and f["distortion"] and thd > 5.0) \
            or f["dc_at_output"]:
        severity = "moderate"
    return SymptomFacts(f, severity, out_db, hum_rise, thd, out_dc, drift)


@dataclass
class SymptomModel:
    circuit_id: str
    hypotheses: list[str]
    p_feature: np.ndarray  # (H, F)
    eps: float = 0.02
    lam: float = 0.5
    reference: SymptomReference | None = None
    symptomatic_rate: np.ndarray | None = None  # (H,) fraction of draws with any feature

    @classmethod
    def fit(cls, circuit_id: str, train: pd.DataFrame) -> SymptomModel:
        circuit = get_circuit(circuit_id)
        hyps = [f.id for f in fault_catalog(circuit)]
        ok = train[train["ok"]]
        # A symptom is judged against a healthy unit as built: the reference uses the
        # as-new healthy draws only (training also holds aged units, ADR-039).
        as_new = ~ok["aged"].astype(bool) if "aged" in ok.columns else np.ones(len(ok), dtype=bool)
        ref = SymptomReference.from_healthy(circuit, ok[(ok["hypothesis"] == "healthy") & as_new])
        P = np.zeros((len(hyps), len(FEATURES)))
        symp = np.zeros(len(hyps))
        for i, h in enumerate(hyps):
            rows = ok[ok["hypothesis"] == h]
            facts = [derive_facts(circuit, ref, r) for _, r in rows.iterrows()]
            if not facts:
                continue
            F = np.array([[fa.features[k] for k in FEATURES] for fa in facts], dtype=float)
            # Laplace smoothing keeps every probability strictly inside (0, 1).
            P[i] = (F.sum(axis=0) + 0.5) / (len(F) + 1.0)
            symp[i] = float(np.mean([fa.any for fa in facts]))
        return cls(circuit_id, hyps, P, reference=ref, symptomatic_rate=symp)

    def log_likelihood(self, reported: dict[str, bool], eps: float | None = None,
                       lam: float | None = None) -> np.ndarray:
        e = self.eps if eps is None else eps
        lm = self.lam if lam is None else lam
        out = np.zeros(len(self.hypotheses))
        for j, feat in enumerate(FEATURES):
            p = self.p_feature[:, j]
            if reported.get(feat):
                out += np.log(e + (1 - 2 * e) * p)
            else:
                out += lm * np.log(e + (1 - 2 * e) * (1 - p))
        return out

    def prior(self, reported: dict[str, bool]) -> np.ndarray:
        if not any(reported.get(f) for f in FEATURES):
            return np.full(len(self.hypotheses), 1.0 / len(self.hypotheses))
        ll = self.log_likelihood(reported)
        p = np.exp(ll - ll.max())
        return np.asarray(p / p.sum())

    def calibrate(self, reports: list[dict[str, bool]], truths: list[int]) -> None:
        best = (math.inf, self.eps, self.lam)
        for e in (0.005, 0.01, 0.02, 0.05, 0.1):
            for lm in (0.0, 0.25, 0.5, 0.75, 1.0):
                nll = 0.0
                for rep, t in zip(reports, truths, strict=True):
                    ll = self.log_likelihood(rep, e, lm)
                    nll -= ll[t] - float(np.log(np.exp(ll - ll.max()).sum()) + ll.max())
                if nll < best[0]:
                    best = (nll, e, lm)
        self.eps, self.lam = best[1], best[2]

    def save(self, path: Path) -> None:
        d = {
            "circuit_id": self.circuit_id,
            "hypotheses": self.hypotheses,
            "features": list(FEATURES),
            "p_feature": self.p_feature.round(6).tolist(),
            "eps": self.eps,
            "lam": self.lam,
            "reference": self.reference.to_json() if self.reference else None,
            "symptomatic_rate": None if self.symptomatic_rate is None
            else self.symptomatic_rate.round(4).tolist(),
        }
        path.write_text(json.dumps(d))

    @classmethod
    def load(cls, path: Path) -> SymptomModel:
        d = json.loads(path.read_text())
        return cls(
            d["circuit_id"],
            d["hypotheses"],
            np.array(d["p_feature"]),
            d["eps"],
            d["lam"],
            SymptomReference.from_json(d["reference"]) if d.get("reference") else None,
            np.array(d["symptomatic_rate"]) if d.get("symptomatic_rate") is not None else None,
        )
