from __future__ import annotations

import math

import pytest

from differential.circuits.compose import compose
from differential.circuits.library import BLOCK_IDS, CIRCUIT_IDS, get_circuit, list_circuits
from differential.circuits.model import MEASUREMENT_TYPES, PART_KINDS
from differential.circuits.netlist import parse_netlist
from differential.circuits.units import format_si, parse_value, spice_number
from differential.config import CIRCUITS_DIR


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2200u", 2.2e-3),
        ("1Meg", 1e6),
        ("4.7k", 4700.0),
        ("22n", 22e-9),
        ("100", 100.0),
        ("1e-9", 1e-9),
        ("10uF", 10e-6),
        ("0.9p", 0.9e-12),
        ("3V", 3.0),
    ],
)
def test_parse_value(text: str, expected: float) -> None:
    assert parse_value(text) == pytest.approx(expected)


def test_parse_value_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_value("abc")


def test_format_si() -> None:
    assert format_si(2.2e-3, "F") == "2.2 mF"
    assert format_si(4700, "Ω") == "4.7 kΩ"
    assert format_si(0.0, "V") == "0 V"
    assert spice_number(1.5e-9) == "1.5e-09"


def test_parse_netlist_continuations_and_control() -> None:
    net = parse_netlist(
        "title\n.include x.lib\nR1 a b 1k ; comment\nB1 a 0 V = V(a)\n+ *2\n"
        "XU1 a b c SUB\nQ1 c b e MOD\n.control\nop\n.endc\n.end\n"
    )
    assert net.includes == ["x.lib"]
    assert net.element("R1").numeric_value == 1000.0
    assert net.element("B1").value == "V = V(a) *2"
    assert net.element("XU1").nodes == ("a", "b", "c")
    assert net.element("Q1").nodes == ("c", "b", "e")
    assert net.has("r1") and not net.has("R9")
    with pytest.raises(ValueError):
        parse_netlist("t\nZ1 a b 1\n")


def test_library_loads_all_circuits() -> None:
    circuits = list_circuits()
    assert [c.id for c in circuits] == list(CIRCUIT_IDS)
    composite = get_circuit("channel_strip")
    assert 50 <= len(composite.components) <= 90
    with pytest.raises(KeyError):
        get_circuit("nope")


@pytest.mark.parametrize("cid", CIRCUIT_IDS)
def test_sidecar_consistent_with_netlist(cid: str) -> None:
    c = get_circuit(cid)
    net = c.netlist
    accounted = set(c.fixtures) | set(c.infrastructure)
    refs = set()
    for comp in c.components:
        assert comp.kind in PART_KINDS
        assert comp.ref not in refs, f"duplicate ref {comp.ref}"
        refs.add(comp.ref)
        assert comp.stage in {s for s, _ in c.stages}
        for el in comp.elements.values():
            assert net.has(el), f"{cid}: {comp.ref} element {el} missing"
            accounted.add(el)
        for el in comp.params.values():
            assert net.has(el)
            accounted.add(el)
        if comp.kind in ("resistor", "film_cap", "electrolytic"):
            assert net.element(comp.main_element).numeric_value == pytest.approx(comp.nominal)
        if comp.kind == "potentiometer":
            upper = net.element(comp.elements["upper"]).numeric_value
            lower = net.element(comp.elements["lower"]).numeric_value
            assert upper is not None and lower is not None
            assert upper + lower == pytest.approx(comp.nominal)
            assert lower / (upper + lower) == pytest.approx(comp.setting)
    unaccounted = [el for el in net.names() if el not in accounted]
    assert not unaccounted, f"{cid}: netlist elements not described in the sidecar: {unaccounted}"
    nodes = net.nodes()
    for tp in c.test_points:
        assert tp.node in nodes, f"{cid}: {tp.id} node {tp.node} not in netlist"
        assert set(tp.measurements) <= set(MEASUREMENT_TYPES)
        assert tp.stage in {s for s, _ in c.stages}


def test_hv_flags_match_nominal_voltages() -> None:
    import json

    from differential.config import RESULTS_DIR

    calcs = json.loads((RESULTS_DIR / "hand_calcs.json").read_text())
    by_name = {r["quantity"]: r for r in calcs["rows"]}
    psu = get_circuit("psu")
    for tp in psu.test_points:
        match = [r for q, r in by_name.items() if f"({tp.id})" in q]
        assert match, tp.id
        assert tp.hv == (match[0]["sim"] > 50.0), tp.id
    plate = get_circuit("triode").test_point("TP9")
    assert plate.hv


def test_composite_is_up_to_date() -> None:
    net_text, yaml_text = compose(write=False)
    assert (CIRCUITS_DIR / "channel_strip" / "channel_strip.cir").read_text() == net_text
    assert (CIRCUITS_DIR / "channel_strip" / "channel_strip.yaml").read_text() == yaml_text


@pytest.mark.parametrize("bid", BLOCK_IDS)
def test_block_lines_identical_in_composite(bid: str) -> None:
    block = get_circuit(bid)
    comp = get_circuit("channel_strip")
    for el in block.netlist.elements:
        if el.name in block.fixtures:
            continue
        assert comp.netlist.element(el.name).line() == el.line()


def test_composite_hv_components() -> None:
    c = get_circuit("channel_strip")
    assert c.component_is_hv("C104")
    assert c.component_is_hv("R203")
    assert not c.component_is_hv("R501")
    assert c.hv_stages == {"psu_hv", "triode"}
    assert c.stage_name("tone") == "Passive tone control"
    assert c.stage_name("unknown") == "unknown"
    assert math.isclose(c.signal.tran_amplitude, 0.0221) if c.signal else False
    assert any(n.get("poisoned") for n in c.service_notes)
