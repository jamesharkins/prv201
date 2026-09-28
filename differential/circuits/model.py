"""Circuit specification: netlist + sidecar YAML metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from differential.circuits.netlist import Netlist, load_netlist
from differential.circuits.units import parse_value

PART_KINDS = (
    "resistor",
    "film_cap",
    "electrolytic",
    "potentiometer",
    "diode",
    "zener",
    "bjt",
    "triode",
    "opamp",
)

# Measurement types a test point may allow. "lift" tests are per component.
MEASUREMENT_TYPES = ("dc", "ac", "hum", "ac20", "ac20k", "thd")
HV_THRESHOLD_V = 50.0


@dataclass(frozen=True)
class ComponentSpec:
    ref: str
    kind: str
    value: str
    family: str
    stage: str
    elements: dict[str, str]
    hint: str
    tolerance: float | None = None
    params: dict[str, str] = field(default_factory=dict)
    model: str | None = None
    setting: float | None = None
    rating: str | None = None

    @property
    def nominal(self) -> float | None:
        if self.kind in {"resistor", "film_cap", "electrolytic", "potentiometer"}:
            return parse_value(self.value)
        return None

    @property
    def main_element(self) -> str:
        return self.elements.get("main") or next(iter(self.elements.values()))


@dataclass(frozen=True)
class TestPointSpec:
    id: str
    node: str
    name: str
    stage: str
    hv: bool
    measurements: tuple[str, ...]
    hint: str


@dataclass(frozen=True)
class SignalSpec:
    source: str
    output_node: str
    tran_amplitude: float | None
    frequency: float


@dataclass(frozen=True)
class RectifierSpec:
    id: str
    pk_source: str
    cres_source: str
    reservoir: str
    pk_nominal: float


@dataclass(frozen=True)
class HumSpec:
    reference_source: str
    rectifiers: tuple[RectifierSpec, ...]


@dataclass
class CircuitSpec:
    id: str
    name: str
    description: str
    netlist_path: Path
    netlist: Netlist
    stages: list[tuple[str, str]]
    signal: SignalSpec | None
    hum: HumSpec | None
    fixtures: list[str]
    infrastructure: list[str]
    components: list[ComponentSpec]
    test_points: list[TestPointSpec]
    service_notes: list[dict[str, Any]] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)

    # ---- lookups -------------------------------------------------------
    def component(self, ref: str) -> ComponentSpec:
        for c in self.components:
            if c.ref == ref:
                return c
        raise KeyError(ref)

    def test_point(self, tp_id: str) -> TestPointSpec:
        for tp in self.test_points:
            if tp.id == tp_id:
                return tp
        raise KeyError(tp_id)

    def stage_name(self, stage_id: str) -> str:
        for sid, name in self.stages:
            if sid == stage_id:
                return name
        return stage_id

    @property
    def refs(self) -> list[str]:
        return [c.ref for c in self.components]

    @property
    def hv_stages(self) -> set[str]:
        return {tp.stage for tp in self.test_points if tp.hv}

    def component_is_hv(self, ref: str) -> bool:
        """True when the component sits on a node that is above 50 V DC in normal operation."""
        comp = self.component(ref)
        hv_nodes = {tp.node for tp in self.test_points if tp.hv}
        for el_name in comp.elements.values():
            if self.netlist.has(el_name) and set(self.netlist.element(el_name).nodes) & hv_nodes:
                return True
        return False


def _component_from_dict(d: dict[str, Any]) -> ComponentSpec:
    return ComponentSpec(
        ref=str(d["ref"]),
        kind=str(d["kind"]),
        value=str(d["value"]),
        family=str(d["family"]),
        stage=str(d["stage"]),
        elements={str(k): str(v) for k, v in d["elements"].items()},
        hint=str(d.get("hint", "")),
        tolerance=float(d["tolerance"]) if d.get("tolerance") is not None else None,
        params={str(k): str(v) for k, v in (d.get("params") or {}).items()},
        model=d.get("model"),
        setting=float(d["setting"]) if d.get("setting") is not None else None,
        rating=d.get("rating"),
    )


def _test_point_from_dict(d: dict[str, Any]) -> TestPointSpec:
    return TestPointSpec(
        id=str(d["id"]),
        node=str(d["node"]),
        name=str(d["name"]),
        stage=str(d["stage"]),
        hv=bool(d.get("hv", False)),
        measurements=tuple(str(m) for m in d["measurements"]),
        hint=str(d.get("hint", "")),
    )


def load_circuit(yaml_path: Path) -> CircuitSpec:
    raw = yaml.safe_load(yaml_path.read_text())
    net_path = yaml_path.parent / raw["netlist"]
    netlist = load_netlist(net_path)
    sig = raw.get("signal")
    signal = (
        SignalSpec(
            source=str(sig["source"]),
            output_node=str(sig["output_node"]),
            tran_amplitude=(
                float(sig["tran_amplitude"]) if sig.get("tran_amplitude") is not None else None
            ),
            frequency=float(sig.get("frequency", 1000.0)),
        )
        if sig
        else None
    )
    hum_raw = raw.get("hum")
    hum = (
        HumSpec(
            reference_source=str(hum_raw["reference_source"]),
            rectifiers=tuple(
                RectifierSpec(
                    id=str(r["id"]),
                    pk_source=str(r["pk_source"]),
                    cres_source=str(r["cres_source"]),
                    reservoir=str(r["reservoir"]),
                    pk_nominal=float(r["pk_nominal"]),
                )
                for r in hum_raw["rectifiers"]
            ),
        )
        if hum_raw
        else None
    )
    return CircuitSpec(
        id=str(raw["id"]),
        name=str(raw["name"]),
        description=str(raw.get("description", "")).strip(),
        netlist_path=net_path,
        netlist=netlist,
        stages=[(str(s["id"]), str(s["name"])) for s in raw["stages"]],
        signal=signal,
        hum=hum,
        fixtures=[str(x) for x in raw.get("fixtures", [])],
        infrastructure=[str(x) for x in raw.get("infrastructure", [])],
        components=[_component_from_dict(c) for c in raw["components"]],
        test_points=[_test_point_from_dict(t) for t in raw["test_points"]],
        service_notes=list(raw.get("service_notes", [])),
        blocks=[str(b) for b in raw.get("blocks", [])],
    )
