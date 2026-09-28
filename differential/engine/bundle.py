"""Per-circuit engine artifacts and their on-disk layout (``data/models/<circuit>/``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from differential.circuits.library import get_circuit
from differential.circuits.model import CircuitSpec
from differential.config import MODELS_DIR
from differential.engine.ambiguity import AmbiguityGroups, singleton_groups
from differential.engine.discriminative import DiscriminativeModel
from differential.engine.generative import GenerativeModel
from differential.sim.observables import ObservableSpec, all_observables

DEFAULT_UNMODELED_PRIOR = 0.05


def model_dir(circuit_id: str, root: Path | None = None) -> Path:
    return (root or MODELS_DIR) / circuit_id


def fixed_order(circuit: CircuitSpec) -> list[str]:
    """Textbook troubleshooting chart: rails, output check, signal trace, stage DC,
    ripple, then frequency response and distortion at the output. Never adapts."""
    tps = circuit.test_points
    order: list[str] = []

    def add(key: str) -> None:
        if key not in order:
            order.append(key)

    psu_tps = [tp for tp in tps if tp.stage.startswith("psu") or tp.id in ("TP16", "TP23")]
    for tp in psu_tps:
        if "dc" in tp.measurements:
            add(f"dc:{tp.id}")
    sig = circuit.signal
    out_tp = next((tp for tp in tps if sig and tp.node == sig.output_node), None)
    if out_tp is not None and "ac" in out_tp.measurements:
        add(f"ac:{out_tp.id}")
    for tp in tps:
        if "ac" in tp.measurements:
            add(f"ac:{tp.id}")
    for tp in tps:
        if "dc" in tp.measurements:
            add(f"dc:{tp.id}")
    if out_tp is not None and "hum" in out_tp.measurements:
        add(f"hum:{out_tp.id}")
    for tp in tps:
        if "hum" in tp.measurements:
            add(f"hum:{tp.id}")
    for kind in ("ac20", "ac20k", "thd"):
        for tp in tps:
            if kind in tp.measurements:
                add(f"{kind}:{tp.id}")
    return order


@dataclass
class EngineBundle:
    circuit: CircuitSpec
    gen: GenerativeModel
    groups: AmbiguityGroups
    disc: DiscriminativeModel | None = None
    unmodeled_prior: float = DEFAULT_UNMODELED_PRIOR
    symptom_model: Any | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def observables(self) -> dict[str, ObservableSpec]:
        return {o.key: o for o in all_observables(self.circuit)}

    @property
    def hypotheses(self) -> list[str]:
        return self.gen.hypotheses

    def order(self) -> list[str]:
        return fixed_order(self.circuit)

    def save(self, root: Path | None = None) -> Path:
        d = model_dir(self.circuit.id, root)
        d.mkdir(parents=True, exist_ok=True)
        self.gen.save(d / "generative.npz")
        self.groups.save(d / "groups.json")
        if self.disc is not None:
            self.disc.save(d / "discriminative.txt")
        meta = dict(self.meta)
        meta["unmodeled_prior"] = self.unmodeled_prior
        (d / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
        return d


def load_bundle(circuit_id: str, root: Path | None = None, with_disc: bool = True) -> EngineBundle:
    d = model_dir(circuit_id, root)
    gen = GenerativeModel.load(d / "generative.npz")
    gpath = d / "groups.json"
    groups = AmbiguityGroups.load(gpath) if gpath.exists() else singleton_groups(gen.hypotheses)
    disc = None
    dpath = d / "discriminative.txt"
    if with_disc and dpath.exists():
        disc = DiscriminativeModel.load(dpath)
    meta_path = d / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    symptom_model = None
    spath = d / "symptom_model.json"
    if spath.exists():
        from differential.engine.symptom_prior import SymptomModel

        symptom_model = SymptomModel.load(spath)
    return EngineBundle(
        circuit=get_circuit(circuit_id),
        gen=gen,
        groups=groups,
        disc=disc,
        unmodeled_prior=float(meta.get("unmodeled_prior", DEFAULT_UNMODELED_PRIOR)),
        symptom_model=symptom_model,
        meta=meta,
    )


@lru_cache(maxsize=16)
def cached_bundle(circuit_id: str) -> EngineBundle:
    return load_bundle(circuit_id)
