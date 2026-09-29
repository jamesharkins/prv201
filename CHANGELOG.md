# Changelog

Stated performance, warnings and known limitations travel with each release
(`docs/` and the milestone documents). The language model is pinned in
`differential/config.py` (`DIFFERENTIAL_MODEL`); a change of model re-runs the
safety and grounding targets T15-T19 before release.

## 0.1.0 (unreleased, September 2026)

- Circuit library (five blocks and a channel strip), fault catalog, ngspice Monte
  Carlo simulation and independent hand calculations.
- Diagnosis engine: Gaussian-mixture and boosted-tree likelihoods, ambiguity
  groups, information gain per unit of effort, calibrated "no single fault fits".
- Agent with live, offline and replay modes; safety layer in code; numeric
  grounding check; meter-photo reading with confirmation; web interface.
- Fixed before any bar was set (ADR-030): a leakage resistor in the 12AX7 model
  put an open-circuit cathode at half the plate voltage; removed, affected
  circuits re-simulated and retrained, hazard map re-audited.
- Fixed (ADR-031): request screening refused "AC voltage", "line input" and
  "crackle"; unsoldering texts now say "below 2 V" everywhere; photo readings are
  checked against the step they are for; the interface and tickets state that
  Differential is an AI assistant; simulation checkpoints are tied to the model
  that produced them.
- Before the targets were locked (ADR-032 to ADR-034): DC readings simulated with
  the meter's 10 MOhm input across the node; an aged-unit stress set and a 1.5-3x
  tolerance curve; evaluation complaints from the held-out bank with omission and
  addition noise, and a sealed bank for the complaint-reading target; 500
  out-of-model units. Targets are met only when their one-sided 95% bound clears the
  bar; the hardware target is primary, with a sealed-draw protocol and a replay tool;
  the scripted baselines may unsolder their leading suspect. Part removal needs the
  owner's approval and, in a high-voltage unit, a reading below 2 V at every point
  that can hold high voltage (logged as the technician's attestation); unvalidated
  circuit models make every point of a high-voltage unit hands-off; the chassis
  notice reads "high voltage inside"; a trainee mode withholds the recommendation
  until the trainee commits a choice and needs a named supervisor on high-voltage
  units; the ticket is no longer grounded against its own text.
- Before the lock, after M1 review rounds 4 to 6 (ADR-035 to ADR-047): half of the
  training units aged, with an aged primary target (T6); a fault audit against an
  independent solver; effort counted to a confirmed answer; bench-practice gates
  (bring-up method, rated meter, leads clipped with the power off, a discharge check
  that lapses); test sets of 5,000 single-fault, 5,000 aged and 2,500 out-of-catalog
  units judged with exact bounds; a bar per part; the scripts' thresholds tuned on the
  pilot; hazard exposure (T24) and release gates for over-reliance (T25) and complaint
  voices (T26); the hazard map checked on units outside the catalog. Safety records
  (bring-up, the owner's approval, discharge readings, a trainee's supervisor) are made
  only in the app's forms, never from chat or by the model (ADR-045).

## Tags

| Tag | Commit | What |
|---|---|---|
| `targets-locked` | `60cca12` | Targets v4 locked before the full evaluation; no test unit scored |
| `m1-ready` | `60cca12` | M1 final after six review rounds |

The tags were created in the build environment, which could not push tags; the
commands to recreate them on these commits are in `SUBMISSION_GUIDE.md`.
