"""A diagnosis session: belief over faults, next-measurement recommendation, stopping.

Posterior over the catalog plus an explicit "unmodeled" hypothesis U:
  * modeled hypotheses: prior x likelihood of the SPICE readings (generative
    GMMs or the calibrated classifier) x likelihood of any lift-test verdicts;
  * U: prior ``unmodeled_prior`` x a broad per-dimension density whose level is
    calibrated on validation data (``GenerativeModel.unmod_offset``). U's
    posterior always uses the generative evidence, also for the classifier
    variant, because classifiers are not calibrated off their training support.
Stopping (ADR-010): stop when one ambiguity group (or U) holds >= 0.90 of the
posterior, when the budget cannot pay for any further measurement, or (for the
information-driven policies) when no measurement is expected to be informative.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from scipy.special import logsumexp

from differential.engine.bundle import EngineBundle
from differential.engine.selection import Candidate, eig_lift, eig_spice, entropy, rank
from differential.sim.faults import UNMODELED
from differential.sim.measurement import (
    LIFT_SENSITIVITY,
    LIFT_SPECIFICITY,
    from_engine,
    reading_to_engine,
)
from differential.sim.observables import ObservableSpec

POLICIES = ("eig_per_cost", "eig", "fixed_order", "half_split", "random")
SCRIPTED = ("fixed_order", "half_split")
NORMAL_BAND_SD = 3.0
LIKELIHOODS = ("generative", "discriminative")
DEFAULT_BUDGET = 40.0
STOP_THRESHOLD = 0.90


@dataclass
class Reading:
    key: str
    kind: str
    value: float
    engine_value: float | None
    cost: float
    step: int
    source: str = "instrument"


@dataclass
class Recommendation:
    obs: ObservableSpec
    eig_bits: float
    score: float
    alternatives: list[Candidate] = field(default_factory=list)
    entropy_bits: float = 0.0
    policy: str = "eig_per_cost"

    @property
    def key(self) -> str:
        return self.obs.key


@dataclass
class StepTrace:
    step: int
    key: str
    cost_spent: float
    top_group: int
    top_mass: float
    unmodeled: float
    seconds: float


@dataclass
class SessionResult:
    stop_reason: str
    top_group: int  # -1 means U (unmodeled)
    top_mass: float
    ranked_groups: list[tuple[int, float]]
    cost: float
    steps: int
    readings: list[Reading]
    trace: list[StepTrace]
    unmodeled_prob: float
    seconds: float


class DiagnosisSession:
    def __init__(
        self,
        bundle: EngineBundle,
        likelihood: str = "generative",
        policy: str = "eig_per_cost",
        prior: np.ndarray | None = None,
        budget: float = DEFAULT_BUDGET,
        stop_threshold: float = STOP_THRESHOLD,
        n_samples: int = 128,
        seed: int = 0,
        allow_lifts: bool = True,
        eig_min: float = 1e-3,
    ) -> None:
        if likelihood not in LIKELIHOODS:
            raise ValueError(likelihood)
        if policy not in POLICIES:
            raise ValueError(policy)
        if likelihood == "discriminative" and bundle.disc is None:
            raise ValueError("discriminative model not available for this circuit")
        self.bundle = bundle
        self.gen = bundle.gen
        self.likelihood = likelihood
        self.policy = policy
        H = self.gen.n_hyp
        p = np.full(H, 1.0 / H) if prior is None else np.asarray(prior, dtype=float)
        p = p / p.sum()
        self.log_prior = np.log(np.maximum(p, 1e-300))
        self.budget = budget
        self.stop_threshold = stop_threshold
        self.n_samples = n_samples
        self.rng = np.random.default_rng(seed)
        self.allow_lifts = allow_lifts
        self.eig_min = eig_min
        self.readings: list[Reading] = []
        self._obs = bundle.observables
        self._order = bundle.order()
        self._hyp_refs = [h.split(":")[0] if ":" in h else "" for h in self.gen.hypotheses]
        self._post: np.ndarray | None = None
        self._last_rec: Recommendation | None = None

    # ------------------------------------------------------------ evidence
    @property
    def cost_spent(self) -> float:
        return float(sum(r.cost for r in self.readings))

    @property
    def remaining(self) -> float:
        return self.budget - self.cost_spent

    def taken(self) -> set[str]:
        return {r.key for r in self.readings}

    def _spice_evidence(self) -> tuple[np.ndarray, np.ndarray]:
        spice = [r for r in self.readings if r.kind != "lift" and r.engine_value is not None]
        idx = self.gen.key_index([r.key for r in spice])
        x = np.array([r.engine_value for r in spice], dtype=float)
        return x, idx

    def _lift_ll(self) -> np.ndarray:
        ll = np.zeros(self.gen.n_hyp)
        refs = np.array(self._hyp_refs)
        for r in self.readings:
            if r.kind != "lift":
                continue
            ref = r.key.split(":", 1)[1]
            p_def = np.where(refs == ref, LIFT_SENSITIVITY, 1.0 - LIFT_SPECIFICITY)
            ll += np.log(p_def if r.value >= 0.5 else 1.0 - p_def)
        return ll

    def _unmodeled_lift_ll(self) -> float:
        """Lift verdicts under U: a double fault makes a given part defective with
        probability about 2 / (number of components)."""
        p_def = min(0.5, 2.0 / max(len(self.bundle.circuit.components), 1))
        ll = 0.0
        for r in self.readings:
            if r.kind == "lift":
                ll += math.log(p_def if r.value >= 0.5 else 1.0 - p_def)
        return ll

    def record(self, key: str, value: float, source: str = "instrument") -> Reading:
        obs = self._obs[key]
        engine_value = None if obs.kind == "lift" else reading_to_engine(obs.kind, value)
        r = Reading(key, obs.kind, float(value), engine_value, obs.cost, len(self.readings) + 1,
                    source)
        self.readings.append(r)
        self._post = None
        return r

    # ----------------------------------------------------------- posterior
    def _modeled_log_post(self, cl: np.ndarray, x: np.ndarray, idx: np.ndarray) -> np.ndarray:
        lift = self._lift_ll()
        if self.likelihood == "generative":
            return self.gen.loglik_fast(cl) + self.log_prior + lift
        disc = self.bundle.disc
        assert disc is not None
        row = np.full(len(self.gen.keys), np.nan)
        row[idx] = x
        lp = disc.log_proba(row[None, :])[0]
        return lp + math.log(self.gen.n_hyp) + self.log_prior + lift

    def posterior(self) -> np.ndarray:
        """Posterior over [catalog hypotheses..., U]."""
        if self._post is not None:
            return self._post
        x, idx = self._spice_evidence()
        cl = self.gen.component_loglik(x, idx)
        hyp_lp = self._modeled_log_post(cl, x, idx)
        gen_marg = logsumexp(self.gen.loglik_fast(cl) + self.log_prior + self._lift_ll())
        pu = self.bundle.unmodeled_prior
        log_u = math.log(pu) + self.gen.unmodeled_loglik(idx) + self._unmodeled_lift_ll()
        log_m = math.log(1.0 - pu) + gen_marg
        p_u = 1.0 / (1.0 + math.exp(min(700.0, log_m - log_u))) if np.isfinite(log_m) else 1.0
        modeled = np.exp(hyp_lp - logsumexp(hyp_lp)) * (1.0 - p_u)
        self._post = np.concatenate([modeled, [p_u]])
        return self._post

    def group_posterior(self) -> np.ndarray:
        """Mass per ambiguity group, with U as the final entry."""
        p = self.posterior()
        g = self.bundle.groups.group_mass(p[:-1])
        return np.concatenate([g, [p[-1]]])

    def ranked_groups(self, k: int = 5) -> list[tuple[int, float]]:
        g = self.group_posterior()
        order = np.argsort(-g)[:k]
        n = len(g) - 1
        return [(-1 if int(i) == n else int(i), float(g[i])) for i in order]

    def top_hypotheses(self, k: int = 5) -> list[tuple[str, float]]:
        p = self.posterior()
        names = [*self.gen.hypotheses, UNMODELED]
        order = np.argsort(-p)[:k]
        return [(names[i], float(p[i])) for i in order]

    def entropy_bits(self) -> float:
        return entropy(self.group_posterior())

    # ------------------------------------------------------------ stopping
    def candidates(self) -> list[ObservableSpec]:
        taken = self.taken()
        out = []
        for key, o in self._obs.items():
            if key in taken or o.cost > self.remaining + 1e-9:
                continue
            if o.is_lift and (not self.allow_lifts or self.policy in (*SCRIPTED, "random")):
                continue
            out.append(o)
        return out

    def status(self) -> tuple[bool, str]:
        g = self.group_posterior()
        if g.max() >= self.stop_threshold:
            return True, "confident"
        cands = self.candidates()
        if self.policy in SCRIPTED:
            cands = [c for c in cands if c.key in self._order]
        if not cands:
            return True, "budget" if self.remaining < max(o.cost for o in self._obs.values()) \
                else "exhausted"
        return False, ""

    # ------------------------------------------------------ recommendation
    def recommend(self) -> Recommendation | None:
        cands = self.candidates()
        if not cands:
            return None
        if self.policy in SCRIPTED:
            avail = {c.key for c in cands}
            nxt = self._half_split_next(avail) if self.policy == "half_split" else None
            if nxt is None:
                taken = self.taken()
                nxt = next((k for k in self._order if k not in taken and k in avail), None)
            return None if nxt is None else Recommendation(self._obs[nxt], 0.0, 0.0,
                                                           policy=self.policy)
        if self.policy == "random":
            pool = [c for c in cands if not c.is_lift]
            if not pool:
                return None
            pick = pool[int(self.rng.integers(len(pool)))]
            return Recommendation(pick, 0.0, 0.0, policy=self.policy)
        scored = self._score(cands)
        ranked = rank(scored)
        if not ranked:
            return None
        best = ranked[0]
        rec = Recommendation(best.obs, best.eig, best.score, ranked[1:4], self.entropy_bits(),
                             self.policy)
        self._last_rec = rec
        return rec

    def _score(self, cands: list[ObservableSpec]) -> list[Candidate]:
        post = self.posterior()
        modeled = post[:-1] / max(post[:-1].sum(), 1e-300)
        groups = self.bundle.groups
        G = groups.n_groups
        x, idx = self._spice_evidence()
        out: list[Candidate] = []
        spice = [c for c in cands if not c.is_lift]
        if spice:
            cidx = self.gen.key_index([c.key for c in spice])
            cl, mean, var = self.gen.predictive(x, idx, cidx)
            comp_h = self.gen.comp_hyp
            if self.likelihood == "generative":
                comp_lp = self.log_prior[comp_h] + self._lift_ll()[comp_h] + cl
                post_fn = None
            else:
                # Hypothesis masses from the classifier, within-hypothesis
                # component responsibilities from the generative evidence.
                hyp_ll = self.gen.loglik_fast(cl)
                within = cl - hyp_ll[comp_h]
                comp_lp = np.log(np.maximum(modeled[comp_h], 1e-300)) + within
                post_fn = self._disc_posterior_fn(x, idx, cidx)
            eig = eig_spice(comp_lp, groups.group_of[comp_h], G, mean, var, self.n_samples,
                            self.rng, posterior_fn=post_fn)
            for c, e in zip(spice, eig, strict=True):
                out.append(Candidate(c, float(e), self._score_value(float(e), c.cost)))
        for c in cands:
            if c.is_lift:
                assert c.ref is not None
                e = eig_lift(modeled, self._hyp_refs, groups.group_of, G, c.ref)
                out.append(Candidate(c, e, self._score_value(e, c.cost)))
        return out

    def _score_value(self, eig: float, cost: float) -> float:
        return eig / cost if self.policy == "eig_per_cost" else eig

    def _disc_posterior_fn(
        self, x: np.ndarray, idx: np.ndarray, cidx: np.ndarray
    ) -> Callable[[int, np.ndarray], np.ndarray]:
        disc = self.bundle.disc
        assert disc is not None
        base = np.full(len(self.gen.keys), np.nan)
        base[idx] = x
        extra = self.log_prior + math.log(self.gen.n_hyp) + self._lift_ll()
        groups = self.bundle.groups

        def fn(j: int, samples: np.ndarray) -> np.ndarray:
            rows = np.repeat(base[None, :], len(samples), axis=0)
            rows[:, cidx[j]] = samples
            lp = disc.log_proba(rows) + extra[None, :]
            lp -= lp.max(axis=1, keepdims=True)
            w = np.exp(lp)
            w /= w.sum(axis=1, keepdims=True)
            G = np.zeros((len(samples), groups.n_groups))
            np.add.at(G.T, groups.group_of, w.T)
            return G

        return fn

    def best_eig_available(self) -> float:
        if self._last_rec is None:
            return math.inf
        return self._last_rec.eig_bits

    # -------------------------------------------------------- half-split
    def _healthy_band(self, key: str) -> tuple[float, float]:
        """Healthy range of a reading in engine space (mixture mean +- 3 sd, noise included):
        what a technician reads off a service-manual chart with its tolerances."""
        if not hasattr(self, "_bands"):
            h = self.gen.hypotheses.index("healthy")
            sel = self.gen.comp_hyp == h
            w = np.exp(self.gen.comp_logw[sel] - logsumexp(self.gen.comp_logw[sel]))
            mu = self.gen.comp_mean[sel]
            var = np.diagonal(self.gen.comp_cov[sel], axis1=1, axis2=2)
            m = (w[:, None] * mu).sum(axis=0)
            v = (w[:, None] * (var + mu**2)).sum(axis=0) - m**2
            sd = np.sqrt(np.maximum(v, 1e-12))
            self._bands = {k: (float(m[i] - NORMAL_BAND_SD * sd[i]),
                               float(m[i] + NORMAL_BAND_SD * sd[i]))
                           for i, k in enumerate(self.gen.keys)}
        return self._bands[key]

    def _is_normal(self, r: Reading) -> bool:
        if r.engine_value is None or r.key not in self.gen.keys:
            return True
        lo, hi = self._healthy_band(r.key)
        return lo <= r.engine_value <= hi

    def _half_split_next(self, avail: set[str]) -> str | None:
        """Scripted expert practice: supply rails first; then, if the output is wrong,
        half-split the signal path with the 1 kHz test tone to find the first stage whose
        output is out of range; then that stage's (and the preceding stage's) DC points.
        Returns None to fall back to the fixed chart order."""
        c = self.bundle.circuit
        got = {r.key: r for r in self.readings}
        rails = [k for k in self._order if k.startswith("dc:")
                 and (c.test_point(k[3:]).stage.startswith("psu") or k[3:] in ("TP16", "TP23"))]
        for k in rails:
            if k not in got:
                return k if k in avail else None
        if any(not self._is_normal(got[k]) for k in rails):
            psu_dc = [f"dc:{tp.id}" for tp in c.test_points
                      if tp.stage.startswith("psu") and "dc" in tp.measurements]
            return next((k for k in psu_dc if k not in got and k in avail), None)
        sig = [f"ac:{tp.id}" for tp in c.test_points if "ac" in tp.measurements]
        if not sig:
            return None
        if sig[-1] not in got:
            return sig[-1] if sig[-1] in avail else None
        if self._is_normal(got[sig[-1]]):
            return None  # gain path fine: continue down the chart (DC, hum, response)
        lo, hi = 0, len(sig) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if sig[mid] not in got:
                return sig[mid] if sig[mid] in avail else None
            if self._is_normal(got[sig[mid]]):
                lo = mid + 1
            else:
                hi = mid
        first_bad = c.test_point(sig[hi][3:])
        stages = [first_bad.stage]
        if hi > 0:
            stages.insert(0, c.test_point(sig[hi - 1][3:]).stage)
        stage_dc = [f"dc:{tp.id}" for tp in c.test_points
                    if tp.stage in stages and "dc" in tp.measurements]
        return next((k for k in stage_dc if k not in got and k in avail), None)

    # --------------------------------------------------------- predictions
    def expected_reading(self, key: str, hypothesis: str) -> tuple[float, float, float] | None:
        """Predicted (mean, low, high) reading in natural units under one hypothesis,
        conditioned on everything measured so far (low/high = 95 % interval)."""
        obs = self._obs[key]
        if obs.is_lift:
            return None
        h = self.gen.hypotheses.index(hypothesis)
        x, idx = self._spice_evidence()
        cidx = self.gen.key_index([key])
        cl, mean, var = self.gen.predictive(x, idx, cidx)
        sel = self.gen.comp_hyp == h
        w = np.exp(cl[sel] - logsumexp(cl[sel]))
        m = float((w * mean[sel, 0]).sum())
        v = float((w * (var[sel, 0] + mean[sel, 0] ** 2)).sum() - m * m)
        sd = math.sqrt(max(v, 0.0))
        return (
            from_engine(obs.kind, m),
            from_engine(obs.kind, m - 1.96 * sd),
            from_engine(obs.kind, m + 1.96 * sd),
        )

    # ------------------------------------------------------------------ run
    def run(self, measure: Callable[[ObservableSpec], float], max_steps: int = 200) -> SessionResult:
        t0 = time.perf_counter()
        trace: list[StepTrace] = []
        reason = ""
        for _ in range(max_steps):
            stop, reason = self.status()
            if stop:
                break
            ts = time.perf_counter()
            rec = self.recommend()
            if rec is None:
                reason = "exhausted"
                break
            if self.policy in ("eig_per_cost", "eig") and rec.eig_bits < self.eig_min:
                reason = "uninformative"
                break
            value = measure(rec.obs)
            self.record(rec.key, value)
            g = self.group_posterior()
            top = int(np.argmax(g))
            trace.append(
                StepTrace(
                    len(self.readings),
                    rec.key,
                    self.cost_spent,
                    -1 if top == len(g) - 1 else top,
                    float(g[top]),
                    float(self.posterior()[-1]),
                    time.perf_counter() - ts,
                )
            )
        else:
            reason = "max_steps"
        ranked = self.ranked_groups(k=10)
        return SessionResult(
            stop_reason=reason or "exhausted",
            top_group=ranked[0][0],
            top_mass=ranked[0][1],
            ranked_groups=ranked,
            cost=self.cost_spent,
            steps=len(self.readings),
            readings=list(self.readings),
            trace=trace,
            unmodeled_prob=float(self.posterior()[-1]),
            seconds=time.perf_counter() - t0,
        )
