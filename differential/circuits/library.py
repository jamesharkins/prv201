"""Circuit library access."""

from __future__ import annotations

from functools import cache

from differential.circuits.model import CircuitSpec, load_circuit
from differential.config import CIRCUITS_DIR

BLOCK_IDS = ("psu", "triode", "tone", "opamp", "driver")
COMPOSITE_ID = "channel_strip"
CIRCUIT_IDS = (*BLOCK_IDS, COMPOSITE_ID)
DEVICE_LIBRARY = CIRCUITS_DIR / "lib" / "devices.lib"


@cache
def get_circuit(circuit_id: str) -> CircuitSpec:
    if circuit_id not in CIRCUIT_IDS:
        raise KeyError(f"unknown circuit {circuit_id!r}; known: {', '.join(CIRCUIT_IDS)}")
    return load_circuit(CIRCUITS_DIR / circuit_id / f"{circuit_id}.yaml")


def list_circuits() -> list[CircuitSpec]:
    return [get_circuit(cid) for cid in CIRCUIT_IDS]
