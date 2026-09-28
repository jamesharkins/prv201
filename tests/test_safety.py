"""Deterministic safety layer: hazard map, warnings, injection handling, output checks."""

from __future__ import annotations

from differential.circuits.library import get_circuit
from differential.safety.hazards import circuit_has_hv, hazard
from differential.safety.rules import (
    CERTAINTY_TEXT,
    enforce_output,
    find_injection,
    hv_warning,
    screen_request,
    wrap_untrusted,
)


def _poisoned_note() -> str:
    notes = get_circuit("channel_strip").service_notes
    return next(str(n["text"]) for n in notes if n.get("poisoned"))


def test_hazard_map_marks_normal_and_fault_conditioned_high_voltage() -> None:
    assert hazard("channel_strip", "TP4").level == "hv"
    # Low in normal operation but above 50 V under a single catalog fault.
    tp8 = hazard("channel_strip", "TP8")
    assert tp8.level == "hv_under_fault"
    assert tp8.normal_max_v is not None and tp8.normal_max_v < 50
    assert tp8.worst_case_v is not None and tp8.worst_case_v > 50
    assert not hazard("channel_strip", "TP1").high_voltage


def test_unknown_points_fail_closed() -> None:
    hz = hazard("channel_strip", "TP999")
    assert hz.level == "unknown" and hz.high_voltage


def test_circuit_level_hv_flags() -> None:
    assert circuit_has_hv("channel_strip") and circuit_has_hv("psu") and circuit_has_hv("triode")
    assert not circuit_has_hv("driver") and not circuit_has_hv("opamp")


def test_fault_conditioned_warning_text() -> None:
    lines = hv_warning(None, "TP8 (cathode)", ["C104"], worst_case=147.0,
                       example_fault="R204 open circuit")
    text = " ".join(lines)
    assert "HIGH VOLTAGE POSSIBLE" in text and "147" in text
    assert "Hands-off" in text and "resistor tool" in text and "C104" in text


def test_poisoned_service_note_is_flagged_and_its_request_refused() -> None:
    note = _poisoned_note()
    assert find_injection(note)
    assert wrap_untrusted(note, "SN-3")["contains_instructions"] is True
    assert not screen_request(note).allowed


def test_output_layer_replaces_unsafe_text() -> None:
    safe, chk = enforce_output(_poisoned_note(), hv_context=True)
    assert not chk.ok and chk.unsafe
    assert "can't give that instruction" in safe


def test_false_certainty_is_rewritten() -> None:
    out, chk = enforce_output("It is definitely C502.", hv_context=False)
    assert chk.false_certainty and "definitely" not in out and "most likely" in out


def test_missing_high_voltage_warning_is_appended() -> None:
    out, chk = enforce_output("Measure TP6 next.", hv_context=True,
                              hv_lines=hv_warning(250.0, "TP6", ["C104"]))
    assert chk.missing_hv_warning and "HIGH VOLTAGE" in out


def test_certainty_pressure_is_answered_with_calibrated_language() -> None:
    res = screen_request("Just tell me for sure which part it is, no maybes.")
    assert res.allowed and res.certainty_pressure and res.message == CERTAINTY_TEXT


def test_benign_safety_question_is_allowed() -> None:
    assert screen_request("How do I safely discharge the filter capacitors?").allowed
