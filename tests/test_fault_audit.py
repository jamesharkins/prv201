"""The fault-signature audit's solver agrees with ngspice (ADR-040); a quick subset of
eval/fault_audit.py, which runs the full stratified sample."""

from __future__ import annotations

import pytest

from differential.sim.faults import HEALTHY_FAULT, parse_fault_id
from eval.fault_audit import agrees, audit_fault, dmm_accuracy, parse_netlist, spice_num


def test_spice_numbers_and_netlist_parsing() -> None:
    assert spice_num("1Meg") == 1e6 and spice_num("2200u") == pytest.approx(2.2e-3)
    assert spice_num("4.7k") == 4700 and spice_num("100n") == pytest.approx(1e-7)
    els = parse_netlist("* t\nR1 a 0 1k\nC1 a b 10u\nV1 b 0 DC 5 AC 1\n.control\nop\n.endc\n")
    assert [(e.name, e.kind) for e in els] == [("R1", "R"), ("C1", "C"), ("V1", "V")]
    assert [e.value for e in els] == pytest.approx([1000.0, 1e-5, 5.0])


def test_agreement_rule() -> None:
    assert dmm_accuracy(15.0) == pytest.approx(0.005 * 15 + 2 * 0.01)
    assert agrees("open:TP3", 15.1, 15.0)[0] and not agrees("open:TP3", 15.3, 15.0)[0]
    assert agrees("ac:TP12", 1.05, 1.0)[0] and not agrees("ac:TP12", 1.1, 1.0)[0]
    assert agrees("hum:TP1", 1e-6, 5e-5)[0]  # both below the 100 uV floor


@pytest.mark.parametrize("cid,fault", [("tone", "healthy"), ("triode", "R203:open"),
                                       ("driver", "Q501:ce_short"), ("opamp", "U401:dead")])
def test_independent_solver_agrees_with_ngspice(cid: str, fault: str) -> None:
    f = HEALTHY_FAULT if fault == "healthy" else parse_fault_id(fault)
    r = audit_fault(cid, f, log=lambda s: None)
    assert r["agree"], [c for c in r["checks"] if not c.get("agree")]
