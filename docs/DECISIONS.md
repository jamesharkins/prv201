# Architecture and project decision records (ADRs)

Each record gives the context, the options considered, the decision and its
consequences. Records are append-only; a superseded decision is marked, not
deleted.

---

## ADR-001 - Rubric source when the course folder is empty

- **Context.** The brief says to read `course/` first and to use an official
  rubric from `course/*rubric*` when present. At build time (2026-09-28) the
  repository contained only a licence file; no syllabus, slides or rubric. The
  public catalogue page for PRV 201 was blocked by the sandbox's network policy.
- **Options.** (a) Stop and ask for the materials; (b) reconstruct the course
  structure from the brief and use the derived rubric in the brief's §10.
- **Decision.** (b). `rubric/derived_rubric.md` is the rubric everywhere;
  `course/SYLLABUS_NOTES.md` records what the brief says about the course and is
  labelled as a stand-in.
- **Consequences.** If an official rubric is added later, re-run the grading
  loop against it (CLAUDE.md, "Feedback arrives"). Graders' emulation uses the
  derived rubric plus the syllabus notes.

## ADR-002 - Offline-first build without an API key

- **Context.** `DIFFERENTIAL_API_KEY` was not set. The brief forbids reading
  `ANTHROPIC_API_KEY` and requires offline mode in that case.
- **Options.** (a) Block live-LLM features until a key exists; (b) build every
  live path behind an interface, test it against a recorded fake client, and
  ship deterministic offline substitutes (rule-based symptom extraction, a
  classical seven-segment reader, a template-driven agent).
- **Decision.** (b). Live-LLM results (LLM-only baseline, Claude symptom
  extraction, Claude vision, live-agent latency and cost, LLM-derived prior for
  the recap-bias study) are reported as *pending*, with the exact commands in
  `SUBMISSION_GUIDE.md`.
- **Consequences.** The headline comparison against an LLM on its own cannot be
  measured in this build. Everything that does not need a model call is
  measured now. No live-LLM number anywhere in the deliverables is estimated or
  simulated.

## ADR-003 - Default Claude model and API usage

- **Context.** The brief asks for a current Sonnet-class default, configurable
  through `DIFFERENTIAL_MODEL`. The live model documentation (fetched
  2026-09-28) lists Claude Sonnet 5.5 (`claude-sonnet-5-5`, released
  2026-09-28, $2 / $10 per million input / output tokens) as the current Sonnet
  model; Claude Sonnet 5 is now a legacy model.
- **Decision.** Default `claude-sonnet-5-5`. Constraints taken from the model's
  documentation: non-default `temperature`/`top_p` return an error, so
  reproducibility comes from caching every response by request hash; forced
  `tool_choice` is rejected, so tools use `auto` with `strict` schemas; the
  lowest thinking setting is `between_tools`, used for the agent loop;
  conversations are kept append-only because thinking blocks are bound to the
  conversation prefix.
- **Consequences.** Switching models may need the thinking setting changed;
  `differential/agent/llm.py` selects it per model family.

## ADR-004 - Circuit simulator integration

- **Context.** About 250 000 simulations are needed (catalog x draws x circuits).
- **Options.** (a) PySpice / ctypes binding to the ngspice shared library;
  (b) one `ngspice -b` subprocess per chunk of 50 draws, with a generated
  `.control` script that applies each draw with `alter`/`altermod` and echoes
  tagged results.
- **Decision.** (b). Measured throughput: 3 ms per draw for a 40-element
  benchmark with DC + four AC analyses; 5-44 ms per draw for the real circuits
  including the THD transient. Subprocesses isolate hangs (timeouts) and crashes.
- **Consequences.** Parsing is text-based, so every analysis echoes the active
  plot name and the parser rejects a draw whose plot does not match the
  analysis (guards against reading stale vectors after a failed analysis).

## ADR-005 - Rectifier and hum model

- **Context.** DC operating-point analysis cannot run a rectifier; hum needs the
  ripple on each unregulated rail.
- **Options.** (a) Full transient simulation of transformer + rectifier +
  reservoir for every draw (slow, needs long settling); (b) a quasi-static
  average model for DC plus a small-signal ripple source for hum.
- **Decision.** (b). A behavioural source gives the average rectified voltage,
  `max(Vpk - I(Rw + 1/(4fC)), (2/pi)Vpk - I Rw)`, isolated from the ripple path
  by a large inductor. Hum is a separate AC analysis at 120 Hz in which a
  current source of amplitude 2 x I_dc (the fundamental of the rectifier's
  charging-pulse train) is injected into each reservoir node. This reproduces the
  sawtooth-ripple fundamental I/(120 pi C) exactly and responds physically to
  capacitance loss and ESR.
- **Consequences.** Regulator drop-out on ripple troughs and harmonics above
  120 Hz are not modelled. `docs/hand_calcs.md` compares the approximation with
  a full transient simulation.

## ADR-006 - Component tolerance distributions

- **Decision.** Passive values: truncated normal, sigma = tolerance/2,
  truncated at +-tolerance (manufacturing tolerances are limits; production
  spreads are centred). Electrolytic ESR: nominal (from the datasheet tan-delta
  limit at 120 Hz) x U(0.4, 1.0). Potentiometers: track +-20 %, rotation
  +-0.02. BJT beta: model BF scaled log-uniformly by 0.82-3.2 so the simulated
  hFE at 10 mA spans the onsemi datasheet window of 100-300.
  Zener voltage: +-5 % (sigma 2.5 %). Triode: MU x U(0.9, 1.1), KG1 x
  log-uniform(0.8, 1.25). Op-amp GBW: 3 MHz x U(0.7, 1.3). Mains: +-5 %,
  common to both rectifiers.
- **Consequences.** Tolerance spread defines how separable faults are; the
  sample-size ablation (50-400 draws) measures sensitivity to this choice.

## ADR-007 - Fault modelling conventions

- **Decision.** Opens: 1 GOhm for resistive paths, 1 fF for capacitors. Shorts:
  log-uniform 0.01-1 Ohm for resistors, 0.1-10 Ohm for capacitors and diodes,
  1-50 Ohm collector-emitter. Collector-base leakage: 47k-470k Ohm. High ESR:
  10-100 x nominal. Low triode emission: 30-60 % of nominal current. Op-amp
  dead: output stuck 1.5 V inside a randomly chosen rail. Degraded GBW:
  1-10 % of nominal. Severity parameters are sampled per draw and stored.
- **Consequences.** Some catalog faults are nearly invisible at the test points
  in this design (for example an open grid-leak resistor, because the triode
  model draws no grid current at negative bias). They are reported as latent
  faults and excluded from the symptomatic test set (ADR-013), not hidden.

## ADR-008 - Measurement model, observation space and variance floors

- **Decision.** DMM: +-(0.5 % + 2 counts), 6000-count autoranging, sigma =
  limit/2, readings rounded to display resolution. Scope: +-3 % (sigma 1.5 %),
  gain floor -60 dB re generator, hum floor 100 uV. THD: +-10 % relative, floor
  0.01 %, reads 100 % without a fundamental above 10 mV. Engine space: DC ->
  asinh(v / 50 mV); gains -> dB; hum -> dBV; THD -> log10 %. Variance floors:
  (0.004)^2 for DC, (0.05 dB)^2 for gains, (0.1 dB)^2 for hum, (0.01)^2 for
  log-THD.
- **Consequences.** Floors prevent zero-variance components (e.g. 0 V at a node
  that an open fault disconnects) from producing infinite likelihoods.

## ADR-009 - Scope of the THD simulation

- **Context.** THD needs a transient + Fourier analysis per draw.
- **Decision.** THD is simulated for every draw of every circuit with an active
  signal path (triode, op-amp, driver, composite), at the circuit's output test
  point, 7 ms at 1 kHz with Fourier over the last period. The passive tone
  control (linear, no THD mechanism) and the PSU (no signal path) are excluded.
  Measured cost: 5-44 ms per draw, about 20 minutes of the full run on 4 cores.
- **Consequences.** Distortion faults (bias shifts that clip) are observable
  everywhere they physically matter.

## ADR-010 - Stopping rule threshold

- **Decision.** Stop when one ambiguity group (or the unmodeled hypothesis)
  reaches posterior >= 0.90, when the 40-unit budget cannot pay for another
  measurement, or when no candidate has expected information gain above 0.001
  bits. 0.90 balances cost against error: every extra percentage point of
  confidence costs measurements, and a technician confirms the part anyway
  before replacing it (lift test or substitution). The threshold is a
  parameter; the evaluation reports the cost/accuracy trade-off around it.

## ADR-011 - Ambiguity groups

- **Decision.** Build groups from validation data: the mean posterior mass that
  noisy full-measurement readings of hypothesis i assign to hypothesis j, with
  pairs linked when the symmetric confusion is >= 0.10 and groups taken as
  connected components. Lift tests are excluded, and the agent offers the lift
  test that would split a group as an optional next step.

## ADR-012 - Symptom thresholds (physics-derived symptom facts)

- **Decision.** Output level down more than 30 dB -> no output; down 3-30 dB ->
  low gain; hum more than 6 dB above the healthy 99th percentile and above the
  measurement floor -> hum; THD above max(3 x healthy median, 1 %) with a
  fundamental present -> distortion; |DC at output| > 0.1 V -> DC at output; an
  internal DC point off by more than max(10 %, 3 x healthy half-spread, 50 mV)
  -> bias drift; 20 Hz or 20 kHz response down more than 3 dB relative to 1 kHz
  -> bass or treble loss. PSU block: a rail below 50 % -> no output; a rail off
  by more than 5 % -> bias drift. Classes the simulator cannot produce
  (hiss/noise, intermittent/crackle, thermal) carry no fault information in the
  prior and are flagged to the technician as outside the static model.

## ADR-013 - Test-set construction

- **Decision.** Single-fault test cases are drawn uniformly over each circuit's
  *symptomatic* catalog faults (a fault is symptomatic when at least half of its
  training draws show at least one symptom), then one draw is simulated with a
  seed from the disjoint test stream; a draw that shows no symptom is redrawn so
  every case has a complaint. 500 composite cases + 100 per block = 1000.
  Unmodeled cases: 70 double faults and 30 out-of-catalog modifications
  (wrong-value parts and solder bridges), in the same circuit proportions.
- **Consequences.** Latent faults are counted and reported separately. Uniform
  sampling over faults means base rates are the catalog's, not field failure
  rates; the recap-bias study compares against this known base rate.

## ADR-014 - What is committed to git

- **Decision.** Commit the circuits, code, fitted engine artifacts needed by the
  demo and `make eval-smoke`, test cases, results and documents. Do not commit
  the raw Monte Carlo cache (`data/sim/*.parquet`, regenerated by `make sim` in
  about 40 minutes on 4 cores); its manifest (netlist hashes, seeds, tolerance
  specification hash, ngspice version, failure counts) is committed.

## ADR-015 - Lift tests (out-of-circuit component checks)

- **Decision.** Model "requires lifting a component" (cost 10) as a binary
  verdict on one part (sensitivity 0.97, specificity 0.99). Lift tests are not
  used to form ambiguity groups; the agent suggests one when a group needs
  splitting.

## ADR-016 - Measurement budget

- **Decision.** 40 cost units per session for every system: roughly the cost of
  measuring every DC test point of the channel strip once (23 points + HV
  surcharges = 31) plus three scope measurements. Systems that have not
  converged by then report their best group.

## ADR-017 - Network restrictions and citation verification

- **Context.** The build sandbox's egress policy blocked nearly every primary
  source (bls.gov, eur-lex.europa.eu, nist.gov, arxiv.org, doi.org, publisher
  and manufacturer sites); the shared web-search budget was exhausted by the
  research pass.
- **Decision.** Every source in `docs/research/sources_*.yaml` records how it
  was verified (`fetched` or `search_snippet_only`, with the supporting quote).
  `tools/check_citations.py` distinguishes "resolves", "dead" and "cannot be
  checked from this network". Snippet-only sources are listed in
  `SUBMISSION_GUIDE.md` for a human re-check before submission.

## ADR-018 - Document toolchain

- **Options.** pandoc + LaTeX (not installed; multi-GB), pandoc + HTML-to-PDF,
  or Typst.
- **Decision.** Jinja templates rendered to Typst and compiled with the pinned
  `typst` Python package. Numbers come only from `results/metrics.json`,
  `results/targets.json` and the cited sources; `tools/check_claims.py` fails a
  document that contains an untraceable number.

## ADR-019 - Device models and the pass transistor

- **Context.** The first build used a widely copied 2N3904 card of unclear
  provenance and placeholder BD139 and zener cards. The technical research pass
  recovered manufacturer-attributed models: onsemi 2N3904 and BD139 (from the
  onsemi model library), Diodes Inc. 1N4148 and the Diodes Inc. 1N4745A zener
  subcircuit, and Koren's own 12AX7 listing.
- **Options for the regulator pass device.** (a) onsemi BD139 model: its fitted
  emission coefficient (NF = 0.85) gives Vbe = 0.37 V at 22 mA, which a bench
  technician would flag as unphysical (a real BD139 reads about 0.6 V); no other
  attributable BD139 card was reachable. (b) onsemi 2N3904: verified model and
  datasheet; the regulator carries about 22 mA and dissipates about 0.2 W, about
  30 % of the TO-92 rating.
- **Decision.** (b). All transistors use the verified onsemi 2N3904 card; the
  zener uses the Diodes Inc. subcircuit with its internal 14.6 V source read
  from a parameter node (tolerance draws); the triode uses Koren's equations and
  grid-current branch verbatim. All simulations were re-run after the change
  (the earlier runs are not used anywhere).
- **Consequences.** Regulated rail is 15.15 V nominal. The service manual
  analogue (expected readings) now matches bench intuition at every test point.

## ADR-020 - Fault-conditioned hazard map and the unsoldering lock (M1 review)

- **Context.** Round-1 reviewers (repair engineer, ethics scholar) pointed out
  that a unit on the bench is faulted, and a fault can put B+ on a node that is
  low-voltage in normal operation. Classifying test points by their normal
  operating voltage alone under-warns.
- **Options.** (a) Keep the YAML `hv` flag (normal operation). (b) Treat every
  node of a tube chassis as high voltage (alarm fatigue on low-voltage blocks).
  (c) Classify every test point by its worst case over all simulated faults and
  tolerance draws.
- **Decision.** (c). `eval/hv_audit.py` writes `differential/safety/hv_map.json`
  (levels `hv`, `hv_under_fault`, `lv`; unknown points fail closed). Warnings for
  such points prescribe hands-off measurement, isolation and discharge through a
  resistor tool with re-check. In any circuit with high voltage, lift steps are
  locked until the technician reports a filter-capacitor reading below 2 V
  (`confirm_discharge`), and re-locked by the next powered measurement. Effort
  costs keep the normal-operation definition (+2), so earlier pilot numbers stay
  comparable.
- **Consequences.** On the channel strip 6 of 23 test points can exceed 50 V
  (4 normally, 2 only under a fault: TP8 with R204 open, TP10 with C203 shorted).
  T15 checks every possible recommendation against these rules exhaustively.

## ADR-021 - Half-split tracing baseline

- **Context.** Reviewers called the fixed-order chart a straw man: technicians
  check the rails, then half-split the signal path with a test tone.
- **Decision.** Add a scripted `half_split` policy: rails DC first; if a rail is
  outside its healthy band, the supply's DC points; otherwise check the output
  gain, binary-search the 1 kHz gain test points for the first out-of-band stage,
  then that stage's and the preceding stage's DC points; then the fixed chart.
  "Out of band" means outside the healthy mixture mean +- 3 sd (noise included),
  the analogue of a service-manual tolerance. It uses the same inference and
  stopping rule as the other scripted baseline. Target T9 compares against it.

## ADR-022 - Tolerance stress set (sim-to-real proxy)

- **Context.** All test units came from the same generator as the training data.
- **Decision.** Splits `pilot_wide` and `test_wide` (channel strip, 150 and 300
  units) draw every tolerance spread 1.5 times wider than the models assume
  (passives, transistor gain, zener voltage, tube constants, op-amp bandwidth,
  mains). At scale 1.0 the random stream and values are bit-identical to the
  training data (checked). Target T6 bounds the accuracy drop; T7 adds a real
  hardware check on the low-voltage fault board.

## ADR-023 - LLM baselines protocol

- **Decision.** Two baselines on a 150-unit subset stratified by part kind
  (75 channel strip, 15 per block): `llm_only` and `llm_sim`. Both receive the
  complaint, the parts list, the voltage chart with healthy ranges, the fault
  list, costs and the 40-unit budget; they call `measure(key)` and get exactly
  the readings the other systems get (same noise seed), and end with
  `diagnose(ranked_faults, confidence)`. `llm_sim` can also call
  `simulate_fault(fault)` for the median readings of any fault. Scored group
  aware like every other system. Implemented in `eval/llm_baseline.py`; pending
  an API key (no key in this build).

## ADR-024 - Target set v2 (before locking)

- **Context.** Round-1 grading (seven reviewers) found that the targets did not
  test the headline claims (superiority), omitted a hardware check, relied on a
  one-bin calibration test, a circular recap-bias metric and an unsized red-team
  claim. The targets had not been locked (no tag yet), so they were revised.
- **Decision.** 21 targets mapped to objectives O1-O5, 7 marked primary. New:
  superiority margins over scripted procedures (T4) and over the LLM alone
  (T5, bar lowered from +30 to +10 points because frontier models now score
  95.5% on textbook analog questions), the stress set (T6), the fault board (T7),
  the half-split effort ratio (T9), calibration after every step (T12), the
  unmodeled detector's operating point (T13), folklore-prior robustness (T14,
  replacing the circular capacitor-share metric), the exhaustive safety sweep
  (T15). Bars that depend on the new pilot (T6, T9, T12, T13, T14) are set from
  `eval/pilot_v2.py` on validation units before the tag.
- **Pass rule.** Point estimate meets the bar; bootstrap 95% CIs reported.

## ADR-025 - Red-team suite authorship

- **Context.** The brief asks for at least 40 adversarial cases, ideally written
  independently of the safety rules. A subagent commissioned to write them was
  stopped by a safety classifier and instructed not to produce that content,
  even reworded.
- **Decision.** The build does not author adversarial attack prompts. It ships
  the suite schema, the harness and the scoring rubric (`eval/redteam/`), an
  exhaustive rule sweep (T15), tests built only from content already in the repo
  (the poisoned service note), and benign-question checks. The adversarial suite
  (T16) is a team deliverable listed in `SUBMISSION_GUIDE.md`; T16 stays pending
  until the team adds it.

## ADR-026 - Pilot split from validation units

- **Decision.** Bars for new targets are set on a `pilot` split made from
  symptomatic validation units (200 channel strip, 60 per block) with complaints
  rendered like the test cases. Validation draws are used only for calibration
  (groups, symptom-prior smoothing, classifier temperature, unmodeled offset), so
  the pilot is mildly optimistic; bars are set below it. The test split is never
  touched before the `targets-locked` tag.

## ADR-027 - Branch for pushed work

- **Decision.** Work is committed per phase and pushed to the feature branch
  `claude/differential-build` (not `main`) so the ephemeral build container can
  be lost without losing work; tags are created on that branch. Merging to
  `main` is left to the team.

## ADR-028 - Complaint extractor updated after a first held-out score

- **Context.** The first run of `eval/nlp_benchmark.py` (before the targets
  were locked) scored the offline extraction rules at micro-F1 0.57 on the
  held-out paraphrase bank (recall 0.40) and 0.75 on the development templates:
  the rules missed common phrasings in the development bank itself.
- **Decision.** Extend the rules using only the development templates and
  general repair vocabulary, checked on the validation-based pilot split
  (development-bank F1 1.00 afterwards). No held-out text or per-case failure
  was looked at. The T18 bar (>= 0.80 offline, >= 0.90 Claude) was drafted
  before the first run and is locked unchanged.
- **Consequences.** Both the first held-out score and the final one are
  reported (`metrics.json`: `nlp_first_run_before_rule_update`, `nlp`). The
  symptom-model smoothing (eps, lambda) is re-calibrated with the updated rules
  on validation complaints.

## ADR-029 - Pilot 2: engine fix, calibration population and the bar rule

- **Context.** The first pilot (`eval/pilot.py`: engine fitted on training
  draws 0-299, scored on held-out training draws 300-399 of the symptomatic
  faults) reached 99% top-1 on the channel strip. It was optimistic mainly
  because it ran with U's threshold still at zero, where U flags no genuine
  single fault (calibration grid, offset 0). It also built its ambiguity groups
  from the draws it scored, a small effect (one unit moves a confusion rate by
  at most 1/30) that the second pilot shares, since the production groups use
  all validation draws (1/40). A protocol-matched pilot
  (symptomatic validation units with rendered complaints, calibrated
  threshold) gave 92% for the full system and 88.5% for the engine, and most
  misses ended as "no single fault fits" on a genuine single fault. Tracing
  those sessions found two causes. (1) A bug: expected information gain was
  computed over the catalogued faults only, so when the catalogued suspects
  agreed the session stopped as "uninformative" after one or two readings,
  even with U holding 50-90% of the probability. (2) U's threshold had been
  calibrated on random validation units, most of which show no symptom.
- **Decision.** (1) U enters the information-gain computation, for readings
  (a flat predictive over each reading's range at U's calibrated level) and
  for lift tests, so the engine keeps measuring until U or a fault group is
  resolved (`differential/engine/selection.py`, regression test in
  `tests/test_engine.py`). (2) U's threshold is recalibrated on symptomatic
  single-fault validation units (draws 0-49) against the `unmodeled_val` units:
  the offset that flags the most unmodeled units while flagging at most 5% of
  single faults (`eval/recalibrate_unmodeled.py`). A complaint concentrates the
  prior on the faults that fit it, so one level cannot serve both kinds of
  session: calibrated for the full system, it made the engine alone (uniform
  prior) call "no single fault fits" on 29% of genuine single faults in the
  pilot. Two levels are therefore calibrated, each with its own protocol: one
  for sessions whose prior was read from a complaint with at least one
  recognised symptom, one for all others (engine alone, scripted baselines,
  folklore prior). (3) The pilot uses only validation draws
  50-99 and a new `unmodeled_pilot` split, so no pilot unit was used to set the
  threshold. (4) T13 is extended before the rerun: most double faults look like
  one of their two faults within the budget, so besides recognition (AUROC and
  the share flagged at the operating point) it now bounds misleading outcomes
  on units outside the catalog (neither "no single fault fits" nor a group
  containing an altered part), the case that sends a technician to a healthy
  part. It is measured on the full system, whose threshold is calibrated.
  (5) One rule sets every bar the
  pilot can estimate, fixed before the rerun: the pilot estimate moved against
  the system by 1.5 standard errors, rounded to the reporting step, with the
  pilot weighted to the test set's circuit mix (`eval/set_bars.py`). Bars the
  pilot cannot estimate (T5, T7, T15-T21) keep their drafted values.
- **Consequences.** After the fixes the protocol-matched pilot gives 95.0%
  top-1 for the full system and 93.4% for the engine alone (pooled), and
  nearly every remaining full-system miss is a false "no single fault fits"
  (4.8% of units): the 5% false-alarm budget trades directly against top-1
  accuracy in exchange for flagging about 44% of double-fault and modified
  units. By the rule, five bars tightened (T4, T8, T9, T10, T12), five kept
  their drafted values (T2, T3, T6, T11, T14), T1 moved from 95% to 93% and T13
  from AUROC 0.90 / 60% flagged to
  AUROC 0.62 / 38% flagged / at most 21% misleading; `targets.json` keeps each
  drafted value and a derivation sentence next to the bar. The first pilot's
  numbers stay in `metrics.json` (`pilot`) as a record but set no bar.
- **Disclosure.** Until commit f410b1d the CI smoke test (`eval.run_eval
  --smoke`) ran on the first 8 test units per circuit; that commit was the
  first with trained models, so its CI run may have diagnosed those units once
  before the lock. Its output was not read and nothing was tuned on it. The
  smoke test now runs on the pilot splits.
