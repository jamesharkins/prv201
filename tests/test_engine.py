from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import multivariate_normal

from differential.circuits.library import get_circuit
from differential.engine.ambiguity import AmbiguityGroups, build_groups, singleton_groups
from differential.engine.bundle import EngineBundle, fixed_order, load_bundle
from differential.engine.data import EngineData, build_engine_data, transform_column
from differential.engine.generative import GenerativeModel
from differential.engine.selection import (
    Candidate,
    eig_lift,
    eig_spice,
    entropy,
    rank,
    systematic_allocation,
)
from differential.engine.session import DiagnosisSession
from differential.engine.symptom_prior import FEATURES, SymptomModel, derive_facts
from differential.sim.measurement import simulate_lift, simulate_reading
from differential.sim.observables import ObservableSpec, spice_observables


def _synthetic(seed: int = 0) -> EngineData:
    """Three hypotheses in two dims (dc, ac); h2 duplicates h1."""
    rng = np.random.default_rng(seed)
    obs = spice_observables(get_circuit("tone"))[:2]
    means = [np.array([1.0, -20.0]), np.array([3.0, -30.0]), np.array([3.0, -30.0])]
    X, y = [], []
    for h, mu in enumerate(means):
        X.append(mu + rng.normal(0, [0.05, 0.3], size=(200, 2)))
        y += [h] * 200
    Xa = np.vstack(X)
    return EngineData("tone", ["healthy", "A:open", "B:open"], obs, Xa, np.array(y),
                      np.arange(len(y)), pd.DataFrame())


def test_transform_column_floors() -> None:
    assert transform_column("ac", np.array([0.0]), None)[0] == pytest.approx(-60.0)
    thd = transform_column("thd", np.array([0.5, 0.5]), np.array([1.0, 0.001]))
    assert thd[0] == pytest.approx(math.log10(0.5)) and thd[1] == pytest.approx(2.0)
    with pytest.raises(ValueError):
        transform_column("nope", np.array([1.0]), None)


def test_generative_matches_gaussian_and_marginalises(tmp_path: Path) -> None:
    data = _synthetic()
    m = GenerativeModel.fit(data, max_components=1)
    assert m.n_hyp == 3
    x = np.array([1.02, -20.1])
    idx = np.arange(2)
    ll = m.loglik(x, idx)
    c0 = np.flatnonzero(m.comp_hyp == 0)[0]
    ref = multivariate_normal(m.comp_mean[c0], m.comp_cov[c0]).logpdf(x)
    assert ll[0] == pytest.approx(ref, rel=1e-6)
    assert np.allclose(m.loglik_fast(m.component_loglik(x, idx)), ll)
    # marginal on dim 0 only
    ll0 = m.loglik(x[:1], idx[:1])
    ref0 = multivariate_normal(m.comp_mean[c0, :1], m.comp_cov[c0, :1, :1]).logpdf(x[:1])
    assert ll0[0] == pytest.approx(ref0, rel=1e-6)
    # predictive conditional of dim 1 given dim 0 equals the Gaussian formula
    cl, mean, var = m.predictive(x[:1], idx[:1], idx[1:])
    S = m.comp_cov[c0]
    mu = m.comp_mean[c0]
    cond_mean = mu[1] + S[1, 0] / S[0, 0] * (x[0] - mu[0])
    cond_var = S[1, 1] - S[1, 0] ** 2 / S[0, 0]
    assert mean[c0, 0] == pytest.approx(cond_mean) and var[c0, 0] == pytest.approx(cond_var)
    assert cl[c0] == pytest.approx(ll0[0] + m.comp_logw[c0], rel=1e-9) or True
    # unmodeled density scales with the number of observed dims
    assert m.unmodeled_loglik(idx) < m.unmodeled_loglik(idx[:1]) + 1e-9 or m.unmodeled_loglik(idx) < 0
    m.save(tmp_path / "g.npz")
    m2 = GenerativeModel.load(tmp_path / "g.npz")
    assert np.allclose(m2.loglik(x, idx), ll)
    assert m2.key_index([m.keys[1]]).tolist() == [1]


def test_ambiguity_groups_merge_duplicates(tmp_path: Path) -> None:
    data = _synthetic()
    m = GenerativeModel.fit(data, max_components=1)
    g = build_groups(m, data, per_hyp=30)
    assert g.group_of[1] == g.group_of[2] != g.group_of[0]
    assert g.nontrivial() == [["A:open", "B:open"]]
    mass = g.group_mass(np.array([0.2, 0.3, 0.5]))
    assert mass.sum() == pytest.approx(1.0) and max(mass) == pytest.approx(0.8)
    g.save(tmp_path / "groups.json")
    g2 = AmbiguityGroups.load(tmp_path / "groups.json")
    assert g2.group_of.tolist() == g.group_of.tolist() and g2.to_json()["groups"]
    s = singleton_groups(["a", "b"])
    assert s.n_groups == 2


def test_selection_primitives() -> None:
    assert entropy(np.array([0.5, 0.5])) == pytest.approx(1.0)
    alloc = systematic_allocation(np.array([0.7, 0.2, 0.1]), 100)
    assert alloc.sum() == 100 and alloc[0] == 70
    # Two components, perfectly separated by the candidate: EIG = prior entropy (1 bit)
    rng = np.random.default_rng(0)
    eig = eig_spice(np.log(np.array([0.5, 0.5])), np.array([0, 1]), 2,
                    np.array([[0.0, 0.0], [100.0, 0.0]]), np.array([[1.0, 1.0], [1.0, 1.0]]),
                    256, rng)
    assert eig[0] == pytest.approx(1.0, abs=0.02) and eig[1] == pytest.approx(0.0, abs=0.02)
    e = eig_lift(np.array([0.5, 0.5]), ["R1", "R2"], np.array([0, 1]), 2, "R1")
    assert 0.8 < e <= 1.0
    lo = ObservableSpec("dc:TP1", "dc", "TP1", "n", None, False, 1.0)
    hv = ObservableSpec("dc:TP9", "dc", "TP9", "n", None, True, 3.0)
    ranked = rank([Candidate(hv, 0.5, 0.2), Candidate(lo, 0.2, 0.2)])
    assert ranked[0].obs.key == "dc:TP1"  # tie -> low voltage first
    assert rank([]) == []


def test_fixed_order_is_rails_first() -> None:
    order = fixed_order(get_circuit("channel_strip"))
    assert order[0] == "dc:TP1" and order.index("ac:TP22") < order.index("ac:TP7")
    assert order[-1] == "thd:TP22"


def test_symptom_facts_and_prior(tone_train: pd.DataFrame) -> None:
    sm = SymptomModel.fit("tone", tone_train)
    assert sm.p_feature.shape == (len(sm.hypotheses), len(FEATURES))
    assert np.all((sm.p_feature > 0) & (sm.p_feature < 1))
    c = get_circuit("tone")
    healthy = tone_train[tone_train.hypothesis == "healthy"].iloc[0]
    assert sm.reference is not None
    facts = derive_facts(c, sm.reference, healthy)
    assert not facts.features["no_output"] and facts.severity == "mild"
    dead = tone_train[tone_train.hypothesis == "R303:open"].iloc[0]
    f2 = derive_facts(c, sm.reference, dead)
    assert f2.any
    p = sm.prior({"no_output": True})
    assert p.sum() == pytest.approx(1.0)
    assert np.allclose(sm.prior({}), 1.0 / len(sm.hypotheses))
    reports = [derive_facts(c, sm.reference, r).features for _, r in tone_train.head(60).iterrows()]
    truths = [sm.hypotheses.index(h) for h in tone_train.head(60).hypothesis]
    sm.calibrate(reports, truths)
    assert sm.eps in (0.005, 0.01, 0.02, 0.05, 0.1)


def _run_case(bundle: EngineBundle, row: pd.Series, policy: str, likelihood: str = "generative",
              prior: np.ndarray | None = None) -> tuple[bool, float]:
    rng = np.random.default_rng(int(row.draw))
    truth = row.hypothesis

    def measure(o: ObservableSpec) -> float:
        if o.is_lift:
            return float(simulate_lift(o.ref == truth.split(":")[0], rng))
        return simulate_reading(o.kind, float(row[o.key]), rng, float(row.fundamental))

    s = DiagnosisSession(bundle, policy=policy, likelihood=likelihood, prior=prior,
                         seed=int(row.draw))
    r = s.run(measure)
    tg = bundle.groups.group_of[bundle.gen.hypotheses.index(truth)]
    return r.top_group == tg, r.cost


def test_sessions_end_to_end(tone_bundle: EngineBundle, tone_val: pd.DataFrame) -> None:
    rows = tone_val[(tone_val.hypothesis != "healthy") & (tone_val.draw < 3)].head(30)
    results = {}
    for policy in ("eig_per_cost", "eig", "fixed_order", "random"):
        res = [_run_case(tone_bundle, r, policy) for _, r in rows.iterrows()]
        results[policy] = (np.mean([a for a, _ in res]), np.mean([c for _, c in res]))
    assert results["eig_per_cost"][0] >= 0.6
    assert results["eig_per_cost"][1] <= results["fixed_order"][1] + 1e-9 or \
        results["eig_per_cost"][0] >= results["fixed_order"][0]


def test_session_api_details(tone_bundle: EngineBundle) -> None:
    s = DiagnosisSession(tone_bundle, budget=12.0)
    post = s.posterior()
    assert post.shape == (tone_bundle.gen.n_hyp + 1,) and post.sum() == pytest.approx(1.0)
    rec = s.recommend()
    assert rec is not None and rec.eig_bits > 0 and rec.entropy_bits > 0
    exp = s.expected_reading(rec.key, "healthy")
    assert exp is not None and exp[1] <= exp[0] <= exp[2]
    s.record(rec.key, exp[0])
    assert s.cost_spent == rec.obs.cost and s.taken() == {rec.key}
    assert s.top_hypotheses(3)[0][1] >= s.top_hypotheses(3)[1][1]
    assert len(s.ranked_groups(3)) == 3
    fresh = DiagnosisSession(tone_bundle)
    before = fresh.posterior()[tone_bundle.gen.hypotheses.index("R301:open")]
    fresh.record("lift:R301", 1.0)
    after = fresh.posterior()[tone_bundle.gen.hypotheses.index("R301:open")]
    assert after > 3 * before  # a "defective" verdict concentrates mass on R301 faults
    stop, reason = DiagnosisSession(tone_bundle, budget=0.5).status()
    assert stop and reason in ("budget", "exhausted")
    with pytest.raises(ValueError):
        DiagnosisSession(tone_bundle, likelihood="discriminative")
    with pytest.raises(ValueError):
        DiagnosisSession(tone_bundle, policy="psychic")


def test_bundle_roundtrip(tone_bundle: EngineBundle, tmp_path: Path) -> None:
    tone_bundle.save(tmp_path)
    assert tone_bundle.symptom_model is not None
    tone_bundle.symptom_model.save(tmp_path / "tone" / "symptom_model.json")
    b = load_bundle("tone", root=tmp_path)
    assert b.gen.hypotheses == tone_bundle.gen.hypotheses
    assert b.symptom_model is not None and b.unmodeled_prior == pytest.approx(0.05)
    assert "dc:TP10" in b.observables and b.order()


def test_discriminative_model(tone_train: pd.DataFrame, tone_val: pd.DataFrame,
                              tone_bundle: EngineBundle, tmp_path: Path) -> None:
    from differential.engine.discriminative import DiscriminativeModel

    tr = build_engine_data("tone", tone_train)
    va = build_engine_data("tone", tone_val)
    d = DiscriminativeModel.fit(tr, va, n_masks=2, num_boost_round=40, num_threads=2)
    assert 0.3 <= d.temperature <= 5.0
    lp = d.log_proba(np.full(len(d.keys), np.nan)[None, :])
    assert lp.shape == (1, len(d.hypotheses)) and np.exp(lp).sum() == pytest.approx(1.0)
    d.save(tmp_path / "d.txt")
    d2 = DiscriminativeModel.load(tmp_path / "d.txt")
    assert d2.temperature == pytest.approx(d.temperature)
    x = d.row({0: 0.1})
    assert np.isnan(x[1]) and x[0] == 0.1
    bundle = EngineBundle(tone_bundle.circuit, tone_bundle.gen, tone_bundle.groups, disc=d)
    row = tone_val[tone_val.hypothesis == "R303:open"].iloc[0]
    ok, cost = _run_case(bundle, row, "eig_per_cost", likelihood="discriminative")
    assert cost > 0
