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
