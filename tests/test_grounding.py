"""Numeric grounding check (target T9)."""

from __future__ import annotations

from differential.agent.grounding import check_grounding, find_numbers, redact_ungrounded


def test_grounded_readings_pass_with_rounding_and_rescaling() -> None:
    ev = [{"value": 12.34, "p": 0.873, "mean": 250.4, "hum": 0.0123, "gain_db": -6.24}]
    text = ("TP9 reads 12.3 V. C502 is the most likely fault (87%), expect about 250 V at TP1 "
            "and 12.3 mV of hum; the gain fell by -6.2 dB.")
    rep = check_grounding(text, ev)
    assert rep.ok, rep.ungrounded
    assert rep.checked == 5


def test_invented_reading_is_caught() -> None:
    rep = check_grounding("The plate of V201 should read 180 V.", [{"value": 250.4}])
    assert not rep.ok
    assert [m.text for m in rep.ungrounded] == ["180 V"]


def test_identifiers_and_small_counts_are_not_readings() -> None:
    text = "Check R203, TP9, the 12AX7 and 1N4148 next; two readings so far, step 3."
    assert [m for m in find_numbers(text) if m.reading_like] == []
    assert check_grounding(text, []).ok


def test_user_supplied_numbers_count_as_evidence() -> None:
    assert check_grounding("You measured 23.8 V at TP16.", ["I read 23.8 V at TP16"]).ok


def test_component_values_with_multipliers() -> None:
    assert check_grounding("R203 is 100k and C202 is 22 uF.", [{"R203": 100000.0,
                                                                 "C202": 22e-6}]).ok


def test_redaction_marks_ungrounded_numbers() -> None:
    text = "Expect 180 V at the plate."
    out = redact_ungrounded(text, check_grounding(text, []))
    assert "180" not in out and "withheld" in out
