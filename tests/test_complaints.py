from __future__ import annotations

import numpy as np

from differential.engine.symptom_prior import FEATURES, SymptomFacts
from differential.nlp.benchmark import COMPLAINT_NOISE, NO_NOISE, noisy_facts, render
from differential.nlp.paraphrase_bank import PARAPHRASE_BANK, SEVERITY_TAG_P


def _facts(*present: str) -> SymptomFacts:
    return SymptomFacts(features={f: f in present for f in FEATURES}, severity="moderate",
                        output_change_db=-6.0, hum_rise_db=None, thd_pct=None, output_dc_v=None)


def test_complaint_noise_rates_and_rules() -> None:
    rng = np.random.default_rng(0)
    f = _facts("hum", "low_gain")
    n = 20000
    kept = added = 0
    for _ in range(n):
        r = noisy_facts(f, rng).features
        kept += r["hum"]
        added += r["distortion"]
        assert not r["no_output"]
    assert abs(kept / n - (1 - COMPLAINT_NOISE.p_omit)) < 0.015
    assert abs(added / n - COMPLAINT_NOISE.p_add) < 0.005
    dead = _facts("no_output")
    for _ in range(2000):
        r = noisy_facts(dead, rng).features
        assert r["no_output"] and sum(r.values()) == 1  # a dead unit is never "also humming"
    assert noisy_facts(f, rng, NO_NOISE).features == f.features


def test_noise_is_a_stable_stream() -> None:
    a = [noisy_facts(_facts("hum"), np.random.default_rng(5)).features for _ in range(3)]
    assert a[0] == a[1] == a[2]


def test_heldout_bank_renders_reported_symptoms_only() -> None:
    rng = np.random.default_rng(1)
    text = render(_facts("hum"), "studio_client", rng, {}, PARAPHRASE_BANK, SEVERITY_TAG_P)
    quiet = render(_facts(), "studio_client", rng, {}, PARAPHRASE_BANK, SEVERITY_TAG_P)
    assert text and quiet and text != quiet
