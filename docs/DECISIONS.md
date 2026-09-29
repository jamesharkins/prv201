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

## ADR-030 - Round-2 fixes: tube-model artifact, bench population, fresh pilot, live chassis

- **Context.** Review round 2 (docs/grading/M1_round2.md) questioned the hazard
  example "TP8, near 1.4 V in normal operation, reaches 147 V when its cathode
  resistor opens": a cut-off 12AX7 cathode floats only a few volts. It also
  found that the test set dropped whole faults that cause a symptom in fewer than
  half of units, that the pilot reused the validation units that had exposed an
  engine bug and tuned the ambiguity groups, and that the safety rules looked only
  at the probed point.
- **Decision.**
  1. *Tube model.* The Koren subcircuit carried a 1 GOhm plate-cathode resistor;
     with the cathode resistor "open" (1 GOhm) the cathode sat on a divider at
     half the plate voltage. Simulating R204:open gave 134 V with the resistor and
     6 V without it; healthy readings did not change. The resistor is removed; the
     channel strip and the triode block are re-simulated (train and validation)
     and retrained; the hazard map is re-audited. The old results are kept outside
     the repository until the new ones are verified.
  2. *Bench population.* Every evaluation and pilot set is a uniform sample of
     symptomatic units: each case draws a hypothesis and a unit, and keeps it only
     if the unit shows a symptom, otherwise it draws a new hypothesis. Each fault
     therefore appears in proportion to how often it causes a symptom; faults that
     never did in 400 training draws are left out. Calibration negatives follow the
     same population (a uniform sample of symptomatic validation units).
  3. *Fresh pilot.* The pilot is its own simulated split (seed stream 9) built
     with the test protocol; it is used for nothing but setting bars. The old
     validation-based pilot and `eval/pilot_split.py` are retired.
  4. *Live chassis.* In a unit with a high-voltage supply every powered step
     carries a live-chassis notice (leads clipped with power off, one hand clear,
     no probe slips, rated meter, variac or series-lamp limiter at first power-up),
     not only steps at high-voltage points; oscilloscope steps carry a ground-clip
     warning in every circuit. T15's sweep checks the notice on every such step.
  5. *Effort for fault-conditioned hazards.* A point that can exceed 50 V under a
     catalog fault needs the same hands-off protocol as a normally high-voltage
     point, so it carries the same extra effort (2 units) in measurement selection
     and in every effort comparison.
- **Consequences.** Calibration, the pilot and all pilot-derived bars are redone
  after these changes, before the targets are locked. The test set drawn before
  this change was never evaluated (apart from the CI smoke check disclosed in
  ADR-029) and is replaced.

## ADR-031 - Evaluation lock in every script; T19 test photos; exact intervals; screening fixes

- **Context.** A code audit before M2 found: (1) only `eval/run_eval.py` checked the
  `targets-locked` tag; the agent, NLP, language-model and meter-photo evaluations
  could score test data at any time. (2) T19 was judged on the synthetic photo set
  the offline reader was developed on; the "held-out" set (seed 20261001) had also
  been scored during development. (3) M1 promised exact intervals for zero-event
  targets, but only bootstrap intervals existed, which collapse to a point at 0 or
  100 %. (4) Request screening refused ordinary audio vocabulary: "AC voltage" and
  "line input" as mains-side work, "crackle" and "cracked joint" as out of scope
  (the pattern `crack\w*` was meant for software cracking). (5) The meter-photo
  plausibility check existed but nothing called it. (6) The ticket told the
  technician to confirm 0 V while the unsoldering lock opens below 2 V.
- **Decision.** (1) `eval/lock.py` holds the check; the agent, NLP, language-model
  and full evaluations refuse test data before the tag. (2) T19 is judged on a new
  test set (seed 20261028) rendered and scored only after the lock; the seed-20261001
  set is reported as a pilot. (3) `eval.stats.exact_binomial` (Clopper-Pearson)
  gives the intervals for T15, T16 and T17. (4) Screening now matches mains wiring,
  mains voltage and the transformer primary only; "mains hum", "AC voltage", "line
  input/level", "crackle" and "cracked joint" pass (regression tests in
  `tests/test_safety.py`). (5) A photo reading is checked against the step it is for
  (meter function, range, unit slips, reversed leads, and for DC the suspects'
  predicted intervals) and the result is shown with the proposal. (6) Ticket and
  refusal texts say "below 2 V", matching the lock. The interface header and every
  ticket now state that Differential is an AI assistant and that the technician
  decides. (7) Rebuilding the evaluation sets after the tube-model fix exposed that
  simulation checkpoints were keyed by job and tag only, so a rebuilt set could
  reuse rows simulated before a model change (it crashed on a duplicate instead).
  Every checkpoint now carries a signature of the netlists, the device library and
  the tolerance code, and is discarded when they differ; all evaluation-set
  checkpoints were deleted before the rebuild, so no set mixes old and new models.
- **Consequences.** No bar changes. T19's pre-lock numbers stay in `metrics.json`
  as the pilot; the test set's result is new at the full evaluation.

## ADR-032 - Meter loading, aged units, noisy held-out complaints, larger out-of-model set

- **Context.** M1 review round 3 (`docs/grading/M1_round3.md`): the reading model
  left out the meter, the one stress set widened tolerances symmetrically although
  parts age in one direction, the test complaints came from the template bank the
  rule-based reader was written against and always matched the unit's symptoms, and
  100 out-of-model units could not bound the misleading rate usefully.
- **Decision.** (1) *Meter loading.* Every DC observable is solved with the meter's
  10 MOhm input resistance from the node to ground (Fluke 117 manual, Table 7:
  "> 10 MOhm"), one operating point per reading, because a meter only ever loads the
  node it touches. The unloaded node voltages are kept (`open:` columns); the hazard
  audit takes the larger of the two, so it never sees less than a finger would.
  Oscilloscope loading is not modelled (a x10 probe presents about 10 MOhm; checked
  on hardware by T7). The mains level was already drawn per unit (+-5 %). (2)
  *Ageing.* Stress splits `pilot_aged`/`test_aged` age every part of an ageing kind
  before the fault: electrolytics lose 5-30 % capacitance and gain 1.2-3x ESR (inside
  the usual end-of-life limits), fixed resistors drift up 0-10 %, tube emission falls
  0-30 % (above the worn-tube fault range). Tolerance curves at 1.5x, 2x and 3x are
  simulated for reporting. (3) *Complaints.* Evaluation complaints are rendered from
  the held-out paraphrase bank after complaint noise (each shown symptom left out
  with probability 0.2, each other symptom added with probability 0.02; a dead unit is
  never misreported); the symptom model is calibrated on validation complaints with
  the same noise rendered from the development bank. A third bank (B), written by a
  separate model instance that never saw the reader, its rules or the other banks,
  is sealed for T18. (4) *Out-of-model units.* The test set grows to 500 (250 channel
  strip, 50 per block), the pilot set to 250.
- **Consequences.** Everything is re-simulated, retrained and recalibrated; the pilot
  and all pilot-derived bars are redone before the lock. Simulation checkpoints now
  also hash the deck builder and output parser.

## ADR-033 - Targets v3: one-sided bounds, fair comparators, hardware primary, release gates

- **Context.** Round 3 found the in-simulation primaries close to certain to pass
  (bars 1.5 pilot SE below the pilot, met on the point estimate), T4 omitting the
  strongest script and comparing a complaint-reading system with scripts that cannot
  read it, the only hardware target small and secondary, calibration measured on the
  top probability pooled over steps, T15/T17 scored by the code they check, and the
  pilot numbers not reconciled with the weights.
- **Decision.** (1) A target is met only when its one-sided 95 % confidence bound
  clears the bar (exact for one proportion, a stratified bootstrap otherwise). Bars
  keep the 1.5-SE pilot rule, so none is lowered; `eval/set_bars.py` reports each
  bar's chance of being met if the test behaves like the pilot. (2) T4 compares the
  engine alone (same inputs as the scripts) with the chart, random probing and
  half-split tracing; the scripts may unsolder their leading suspect once it holds
  half the belief, and when their chart is used up, as technicians do. (3) T7 is
  primary: at least 60 faults inserted blind into three copies of the 24 V driver
  board, every test point recorded once per fault and every method replayed on the
  recordings; met when the exact lower bound clears 70 % (49 of 60). (4) Primaries:
  T1, T4, T5, T7, T9 (half-split effort), T12 (equal-mass ECE of the probabilities
  shown for the top three groups at the stop; Brier score and log loss reported) and
  T13 (misleading outcomes on 500 out-of-model units). New secondaries T22 (flag rate
  and AUROC) and T23 (share named and accuracy when naming); T6 moves to aged units;
  T14 tests a wrong prior in both directions by reweighting units to a
  capacitor-heavy mix. (5) T15-T17 become release gates with independent checks (a
  hazard set recomputed from raw simulations; at least 300 prompts written
  independently of the rules; an independent grounding checker and a human audit).
  (6) The technician study is pre-registered as S1, reported without a bar.
- **Consequences.** More targets can fail. A miss is reported as one; nothing is
  re-drafted after the lock.

## ADR-034 - Discharge readings at every high-voltage point, owner approval, unvalidated models, trainee mode

- **Context.** Round 3: the unsoldering lock trusted one reading at one filter
  capacitor, although a failed-open dropping resistor can leave a later capacitor
  charged; "guarantees" overstated what software can do; "live chassis" means a
  mains-connected chassis in vintage repair; damage to the customer's unit was not
  in the register; nothing controlled deskilling; the ticket's grounding check
  counted the ticket's own output as evidence.
- **Decision.** (1) Part removal in a high-voltage unit needs a reading below 2 V at
  every test point that can hold high voltage; one number counts for the main filter
  capacitor only, unless the technician says it holds for all points; any powered
  measurement clears the readings. The readings are logged on the ticket as the
  technician's attestation. (2) Every part removal first needs the owner's recorded
  approval; removed parts and their verdicts go on the ticket. (3) The chassis notice
  is renamed "high voltage inside". (4) A circuit model is trusted for hazard
  decisions only once validated against an independent reference; until then every
  point of a unit whose declared supply reaches 50 V is treated as high voltage. (5)
  Trainee mode: the recommendation is withheld until the trainee commits their own
  next measurement (both are logged), and in a high-voltage unit every step needs a
  named supervisor. (6) The ticket is grounded against the session's tool results
  without any generated ticket, the technician's messages and the engine's state at
  close. (7) The sign-off states that it confirms the readings and the plan, not the
  diagnosis, and that the record belongs to the job.
- **Consequences.** T15's sweep checks approval, per-point discharge and re-locking
  on every removal step, and compares the runtime hazard map with one recomputed
  from the raw simulations. The demo scripts, replay recorder and agent evaluation
  record approval and per-point readings.

## ADR-035 - M1 round 4 layout: five pages, supplement, regulation in Part 1

- **Context.** The round-3 fixes (one-sided bounds, fair comparators, hardware
  primary, safety and human-factors controls, U.S. liability, human-subjects plan)
  pushed the rewritten M1 to seven body pages against a limit of five, and a floated
  table could land after the reference heading, outside the page count.
- **Decision.** (1) The industry watch and course coverage map move to a separate
  `M1_supplement.pdf`; nothing but references follows M1's body. (2) Every paragraph
  is cut to its claim and evidence; no fix from `feedback/FEEDBACK_LOG.md` rows 35-50
  is dropped. (3) The EU AI Act classification, transparency date, amendments and
  AI-literacy duty move to Part 1 as regulatory context; Part 4 keeps accountability
  and liability. (4) Secondary targets become one full-width row of Table 3 (ID,
  target, bar), so every locked bar stays visible. (5) A circuit-library table gives
  Part 2 its own table and replaces several prose counts. (6) The methods table
  drops the "names the part" column (the caption states it once). (7)
  `tools/check_pages.py` now fails if any figure or table caption appears after the
  reference heading outside an appendix.
- **Consequences.** M1 is five body pages with the same targets and evidence; the
  supplement is optional background. Parts stay within the balance gate (each within
  20% of the mean length).

## ADR-036 - Levels of diagnostic autonomy (brief section 7)

- **Context.** The brief asks for levels of diagnostic autonomy L0-L4 defined by analogy
  to driving automation, with Differential placed and justified on safety and
  accountability grounds, for use in M2, M3 and M5. Round 3 criticised the earlier text
  for mapping our levels onto the SAE driving scale, which has six levels (0-5); the
  M1 rewrite then dropped the scale altogether.
- **Decision.** Our own five-level scale, stated as an analogy and not as SAE J3016:
  L0 the technician does everything (manual, chart, meter); L1 the tool supplies
  information (expected readings, the chart, service notes) but no recommendation;
  L2 the tool recommends the next measurement and names suspects, and the technician
  chooses, takes and confirms every measurement; L3 the tool takes measurements itself
  through instruments or a fixture while a technician supervises and can intervene;
  L4 an automated fixture diagnoses without a technician. Differential is L2. On the
  24 V fault board it can trigger an SCPI reading, but only after the technician has
  placed the probe and asked for it, so it stays L2 there too.
- **Why L2.** A wrong step near high voltage can injure the person holding the probe,
  and the measurements, precautions and repair decision must remain a qualified
  person's (OSHA qualified-person rules; accountability section of M1 Part 4). L3 would
  need fixtures that make contact safely and a different allocation of responsibility.
- **Consequences.** M1 Part 4 states the scale and the placement in two sentences; M2
  carries the full table; the coverage map lists it under autonomous transportation.

## ADR-037 - The tree engine chooses measurements with the mixtures' predictive update

- **Context.** The comparison engine (boosted trees, `engine_disc`) scored every sampled
  reading of every candidate measurement with the classifier: 128 samples times about 45
  candidates per step, through 33,383 trees for 251 classes on the channel strip, about
  45 s per step and several minutes per unit. The pilot could not finish in hours, and the
  1,000-unit test run would take days. No locked target depends on this engine; it is
  the comparison for the choice of likelihood model.
- **Decision.** The tree engine keeps the classifier's posterior for the belief, the
  naming and the stopping rule. To choose the next measurement it computes the expected
  information gain from the classifier's current belief with the Gaussian mixtures'
  predictive distribution and update, since the trees give no distribution over readings
  not yet taken. The exact variant stays available (`DiagnosisSession.disc_exact_eig`).
- **Consequences.** About 0.6 s per channel-strip unit on four workers. The comparison
  between the two engines is a comparison of the belief they hold and the names they give,
  with a shared way of choosing; M1 and M2 describe it that way. Decided before the lock
  and before any test unit was run.

## ADR-038 - Official syllabus received

- **Context.** On 2026-09-29 the team supplied the official PRV 201 syllabus (three
  pages). Until then `course/` was empty and the project worked from the brief
  (ADR-001). The repository is public and the syllabus carries the instructor's contact
  details.
- **Decision.** (1) The PDF is kept locally (`course/PRV201_Syllabus.pdf`, git-ignored);
  `course/SYLLABUS_NOTES.md` now restates the syllabus: the four course outcomes
  (quoted), the objectives, grading weights and points, the signed-part rule, the AI
  preliminary read (a reference only; a human grader enters the score) and the weekly
  schedule with milestone weeks. (2) The syllabus confirms the milestone point totals
  (25, 45, 64, 22, 84) and gives no per-line rubric, so the derived line items stay in
  use. (3) Reviewer kits from round 5 on carry the new notes, so the course-professor
  persona judges against the four stated outcomes. (4) The course objectives name
  "technological breakthroughs, regulatory actions and investment trends"; each
  milestone's industry watch now covers all three (M1: an investment item replaces
  the model-release item). (5) The coverage map uses the syllabus's week titles; week
  12 ("AI in cybersecurity / fraud detection": threats, anomalies, fraud) now also maps
  the "no single fault fits" detector as anomaly detection; week 11 is a partial link
  (sensing and decision without actuation).
- **Consequences.** Due weeks go into `SUBMISSION_GUIDE.md`: M1 at the start of week
  6's class, M2 week 8, M3 week 11, M4 week 13, final milestone and videos
  (non-finalists) at the end of week 13, presentations for finalists in week 14.

## ADR-039 - Aged units in training and a primary aged-unit target

- **Context.** Round 4 (all four judges, two graders): units that reach a bench are
  old, yet the engine was trained on as-new tolerances only and aged units were a
  secondary target on the channel strip alone. The pilot's aged top-1 (66.7%, a
  25.8-point drop from as-new units) was not printed.
- **Decision.** (1) Training, validation and calibration draws mix as-new and aged
  units: every second draw (odd hypothesis index plus draw index) is aged with the
  model of the aged stress sets (`draws.age_draw`: electrolytic capacitance
  x U(0.70, 0.95) and ESR x logU(1.2, 3.0), resistors x U(1.00, 1.10), triode
  emission x U(0.70, 1.00)), so every fault has as many aged draws as as-new ones.
  Test and pilot units stay as-new; the aged sets are aged throughout. (2) A symptom is
  still judged against an as-new healthy unit: the symptom reference uses the as-new
  healthy draws only, so the definition of a unit that reaches the bench does not move.
  A probe before the change found aged healthy units rarely show a symptom against that
  reference (0-5% by circuit, 100 units each), so in the aged sets the fault, not the
  ageing, is almost always why the unit is on the bench; `eval/library_stats.py`
  reports the rate from the training data. (3) The aged sets cover every circuit with
  the test mix (pilot 200 + 5 x 60, test 500 + 5 x 100). (4) T6 becomes a primary
  target: T1's count (top-1 by ambiguity group, full system) on the 1,000 aged units,
  weighted like T1, bar by the ADR-029 rule from the aged pilot; the drop from T1 and
  the split of misses into wrong names and "no single fault fits" calls are reported
  without a bar. (5) The simulation signature now includes the split configuration and
  the draw code, so any change to the mix discards old checkpoints (standing rule 9).
  (6) `set_bars` records the chance that every pilot-estimable primary is met if the
  targets were independent, so the documents can state how the primaries combine.
- **Consequences.** Full rebuild: simulation, evaluation sets, training, calibration,
  pilot, bars and the safety sweep. As-new accuracy may fall a little because each
  fault's likelihood now spans both populations; the pilot shows by how much, and the
  bars follow from it.

## ADR-040 - Fault-signature audit with an independent solver

- **Context.** Round 4 (engineer, ML PhD and professor judges): the 22 hand checks are
  healthy bias points; fault behaviour, which is what the engine learns, was never
  checked outside ngspice, and an earlier close look at one fault found a model
  artifact (ADR-030).
- **Decision.** `eval/fault_audit.py` draws a stratified random sample of catalogued
  faults (up to two of each fault type per circuit, all five blocks and the channel
  strip, fixed seed) and re-solves three training units of each (two as-new, one aged,
  rebuilt from their seeds) without ngspice and without the simulator's netlist
  builder: the circuit is read from the healthy netlist, the fault is inserted from its
  catalog definition, and a nodal solver written for the audit (Newton with source
  stepping) evaluates the published device equations (Gummel-Poon with the onsemi
  2N3904 card, the Diodes Inc. diode and zener cards, Koren's triode equation, the
  op-amp macro-model) for the operating point, the AC gains and the 120 Hz hum. The
  agreement rule was fixed before the first comparison: DC within twice the bench
  meter's accuracy, AC and hum within 0.5 dB above the instrument floor, every reading
  of all three units. The result is reported with an exact interval, and the first
  run is kept (`results/fault_audit_run1.json`).
- **Result.** First run (blocks only): 36 of 42 faults agreed; all six disagreements
  were the audit solver's own omissions (no junction capacitances in its small-signal
  model; a Newton step limit that stalled with a saturated op-amp). With those fixed and
  the rule unchanged: 42 of 42; with the channel strip added under the same rule, 53 of
  53 faults and 3,159 of 3,159 readings (`docs/fault_audit.md`).
- **Consequences.** The simulator's fault insertion and ngspice's solutions are checked
  against an independent implementation. Not checked: whether the device equations
  describe real parts (hand calculations for healthy bias points; hardware T7), THD,
  and meter loading. The documents say so.

## ADR-041 - Effort to a confirmed answer

- **Context.** Round 4 (engineer, professor, ML PhD): the scripted procedures pay for
  unsoldering their leading suspect before they stop (ADR-033), while the engine stops
  at 90% belief and its mean effort (6.7 units) is below the cost of one unsoldering
  test (10), so it almost never pays for confirming its answer. The effort targets
  compared a confirmed answer with an unconfirmed one.
- **Decision.** Effort is split into probing (in-circuit readings) and unsoldering
  (out-of-circuit tests), and every method is charged one confirming unsoldering test of
  its named group's leading part unless the session already unsoldered a part of that
  group and found it defective (`eval/effort.py`; lift readings recomputed with the
  harness's own noise seeds, so no new runs are needed). A "no single fault fits" call
  names no part and is charged nothing; the flag rate is reported beside the effort.
  T8-T11 become ratios of this effort to a confirmed answer, with bars from the pilot by
  the ADR-029 rule; the raw effort ratio and the probing, unsoldering and confirming
  parts are reported without bars. In the effort-weight sensitivity runs the confirming
  test is charged at the run's own weights.
- **Consequences.** A check on the round-4 block pilots showed the engine's advantage
  shrinking from about a third of the scripts' raw effort to roughly 0.7-0.9 of their
  confirmed effort; the new pilot sets the bars. The headline effort claim becomes
  smaller and fairer. T9's rationale no longer calls half-split tracing "expert
  practice": it is a textbook procedure.

## ADR-042 - Bench practice in the safety layer

- **Context.** Round 4 (audio-electronics engineer): the safety layer covered discharge,
  isolation and hands-off measurement but not four habits of a careful bench:
  bringing an unfamiliar unit up through a variac or series lamp, a meter rated for the
  voltage and category, re-checking a discharged capacitor right before contact
  (dielectric absorption), and clipping leads on with the power off.
- **Decision.** Each habit is a rule in code and a check in the exhaustive sweep (T15).
  (1) Bring-up: in a unit with a high-voltage supply or its own mains rectifier
  (`hazards.needs_bring_up`), every powered step is blocked and no powered reading is
  accepted until the technician records how the unit was first powered (variac, series
  lamp, current-limited bench supply, or already running normally before the
  complaint); the record goes on the ticket. (2) Meter: every powered step in a unit
  with a high-voltage supply names the rating (`rules.METER_RATING`, IEC 61010 CAT II
  600 V or better) and says to clip the leads on with the power off. (3) Dielectric
  absorption: a discharge check unlocks part removal for `rules.DISCHARGE_VALID_S`
  (5 minutes) or until the next power-up, whichever is first, unless the technician
  records a bleeder clipped across the main filter capacitor; an expired check says why.
  (4) Oscilloscope steps keep the scope-ground note, now also swept. Attestations are
  the technician's alone: in live mode the model's calls to record discharge readings,
  owner approval or bring-up are refused unless the technician's own words carry them.
- **Consequences.** The web app gains a bring-up form in the safety banner; the offline
  chat accepts plain answers ("brought it up on a variac") and, like owner approval,
  records nothing when the sentence contains a negation. Low-voltage bench boards are
  not gated. Tests cover each rule; the sweep reports each count.

## ADR-043 - Rounding never carries a bar past its pilot estimate

- **Context.** Setting the round-5 bars (ADR-029's rule: the pilot estimate moved 1.5
  standard errors against the system, rounded to the nearest reporting step) gave two
  bars the rule did not intend. T23's accuracy when naming (pilot 99.83%, raw bar 99.57%)
  rounded up to 100%, which no one-sided 95% bound can ever clear (ADR-033), so the
  target was unmeetable by construction. T9's effort ratio (pilot 0.651, raw bar 0.669)
  rounded to 0.65 on the 0.05 step used for ratios, a bar at the pilot's own result
  with a 16% chance of being met, while T8 and T10 rounded the other way. For ratios
  the 0.05 step was wider than the 1.5-standard-error margin (about 0.018), so rounding,
  not the rule, set the bar.
- **Decision.** Effort ratios round to 0.01, like calibration error and AUROC; and
  when the nearest step lies beyond the pilot estimate, the bar rounds the other way,
  so no bar is stricter than the pilot's own result. Found after the pilot, before the
  lock and before any test unit was run; recorded here with its effect. Against the
  earlier rounding, T8 tightens from 0.65 to 0.64, T10 from 0.60 to 0.59 and T11 from
  1.00 to 0.98; T9 loosens from 0.65 to 0.67 and T23's accuracy bar from 100% to 99%;
  no other bar moves. Each primary's chance of being met (counting the pilot's own
  error) is now 59-69%; if the six pilot-estimable primaries were independent, all
  would pass together with a chance near 6%, about two are expected to miss, and every
  miss is reported.
- **Consequences.** `eval/set_bars.py` states the rule, and `results/targets.json`
  records the expected number of primary misses beside the joint chance.

## ADR-044 - Larger simulated test sets, exact bounds for counts, and three reported quantities

- **Context.** Round 5 of the M1 review. Every grader found that the printed pass counts
  (952 of 1,000, 924 of 1,000, at most 49 of 500) came from a normal approximation while
  the caption named the exact bound, which needs 953, 926 and at most 47. The ML reviewer
  noted that bars set 1.5 pilot standard errors below the estimate pass only about 61% of
  the time by construction when the test set is barely larger than the pilot, although
  simulated test units cost only computer time. T7's 70% was explained only through its
  pass count. Reviewers asked how often the tool sends a technician to a high-voltage
  point, and whether T12's 0.02 bar sits at the noise floor of the calibration measure.
- **Decision.** (1) The simulated test sets grow fivefold: 5,000 single-fault units (2,500
  channel strip, 500 per block), 5,000 aged units with the same mix and 2,500 out-of-catalog
  units. The pilot, and so every bar, is unchanged; a larger test set only measures each
  bar more precisely. Each primary's predictive chance of being met is now 81-88%; if the
  six pilot-estimable primaries were independent, all would pass with a chance near 36%,
  and about one miss is expected. (2) Targets that count units (T1, T2, T3, T6, T13) are
  judged with the exact (Clopper-Pearson) one-sided bound, as the caption says; every unit
  of a pooled test set carries the same weight, so a pooled rate is a plain proportion.
  Pass counts and chances are computed under that rule. (3) T7 keeps its 70% bar, now
  explained by what 60 faults can show: a pass needs 49 right, which a system truly 90%
  accurate on the boards reaches 99% of the time, one at 85% 82%, and one at 70% 3%.
  (4) Reported without bars: powered readings per diagnosis at points that can exceed
  50 V, for every method (pilot: the engine 0.3, the scripts 1.5-1.9); and the calibration
  error a perfectly calibrated system would show at the test size (about 0.002 at 5,000
  units, against T12's 0.02 bar).
- **Also fixed.** Simulation checkpoints keyed a job by circuit, split, hypothesis and
  draw, so two evaluation cases that drew the same fault on the same attempt shared a key;
  growing a split then skipped new cases whose key the old ledger already held. Case jobs
  now carry their case number in the key (`montecarlo.CASE_INDEX_BASE`); catalog jobs keep
  their keys, so training checkpoints stay valid. The earlier sets were built fresh after
  the ADR-039 signature change and were not affected.
- **Consequences.** The full evaluation takes longer (about two hours on four cores with
  the effort-weight sensitivity runs); the LLM comparison keeps its 300 stratified units.

## ADR-045 - Safety records only through the forms (red team, round 6)

- **Context.** Rounds 4, 5 and 6 of the red team each found free text that the attestation
  parsers read as the technician's record: in round 6, hearsay ("the previous tech told me
  he brought it up on a variac"), quoted text, a statement followed by "(I made these up)",
  sarcasm, and the tool's own instruction ("all points below 2 V") read as a 2.0 V reading.
  In live mode the discharge guard matched stated values without their test points, so one
  reading could stand for every high-voltage point. Rules for "plain affirmative
  statements" cannot tell a record from a report of one.
- **Decision.** The four safety records (how a high-voltage unit was first powered, the
  owner's approval to remove parts, discharge readings, a trainee's supervisor) are made
  only by the technician in the app's forms, i.e. the server's structured endpoints. The
  offline chat never makes them from text; it answers with the form to use. The live model
  has no tool for them (`tools.MODEL_TOOL_SPECS`) and any call is refused
  (`agent._guarded_tool`). A discharge record needs a reading at every point that can hold
  high voltage: one number counts for the first point only, and "below 2 V" is strict (a
  2.0 V reading is still charged). `attest.py` keeps only the check that a diagnostic
  reading typed in chat is a plain statement.
- **Also fixed.** Screening reads letters spaced across words ("b y p a s s   t h e
  f u s e") and conductive-foil fuse defeats ("wrap the fuse in foil"); the hidden fault is
  revealed only after the diagnosis stops, or with an explicit end of the session, never
  early in trainee mode, and a revealed session takes no further step; timestamps are not
  checked as readings by the grounding check.
- **Consequences.** Typing "the owner approves" in chat no longer unlocks anything: the
  technician presses the approval button. The documents say attestations come from the
  technician's form entries. Regression tests cover every round-6 finding; the safety
  sweep still covers all 491 checks.

## ADR-046 - Targets v4 before the lock (M1 review, round 6)

- **Context.** Round 6 of the M1 review (the last) found three places where the targets were
  softer or looser than their own rules said, and two release rules that lived only in the
  text: T4 used one bar, the smallest of its three per-baseline bars (+4 points), for every
  baseline; T14 did the same with its two parts; the scripts' unsoldering threshold (50%) was
  a fixed choice while the engine's rules were designed; the one safety-relevant result
  with no declared comparison was the number of powered readings at points that can exceed
  50 V; and the S1 over-reliance rule and the complaint-voice fairness rule could be relaxed
  after the results.
- **Decision.**
  1. A target with several parts has a bar per part, each by the rule: T4 needs at least
     +10 points over the fixed-order chart, +8 over half-split tracing and +4 over random
     probing; T14 has a bar per prior mismatch.
  2. Each script's unsoldering threshold is tuned on the pilot by a rule fixed before the
     sweep (`eval/tune_scripts.py`): the lowest effort to a confirmed answer among
     thresholds within 1 point of that script's best top-1. The fixed-order chart moves to
     40%, half-split tracing stays at 50%. Tuning a baseline can only make the engine's
     targets harder.
  3. New secondary T24: powered readings per diagnosis at points that can exceed 50 V,
     engine relative to half-split tracing (pilot 0.17×, bar 0.19×).
  4. New release gates: T25, at most one of at least six S1 participants carries out the
     planted wrong step without checking (a lower bound on over-reliance, since they are
     forewarned; `docs/study_s1.md`); T26, no complaint voice more than 5 points below the
     other two on the T1 or T6 units with the interval of the gap excluding zero.
  5. The pass rule names the exact bound for counts (ADR-044) and the new gates.
- **Consequences.** T4's chance of being met falls to about 59% (the product of three
  margins, as if independent, which understates it); the six pilot-estimable primaries are
  all met together with a chance near 25%, and about one miss is expected. The pilot
  summary and every bar were recomputed; no test unit has been run.

## ADR-047 - Hazard map checked on units outside the catalog (M1 review, round 6)

- **Context.** The hazard map is built from single catalog faults under tolerances and
  aging (`eval/hv_audit.py`). The round-6 engineer judge pointed out that a double fault, a
  wrong-value part or a solder bridge could put B+ on a point the map calls low voltage,
  and asked how often that happens. In a unit with a high-voltage supply every powered step
  already carries the high-voltage notice, the meter rating and the clip-with-the-power-off
  instruction (T15), so a miss would lose only the point-specific hands-off and discharge
  warnings; it is still a gap in the map.
- **Decision.** `python -m eval.hv_audit --out-of-catalog` counts units outside the catalog
  with a point above 50 V that the map marks as low voltage. On the validation and pilot
  sets it found none of 410 units. The same count on the 2,500 out-of-catalog test units is
  pre-registered as a quantity reported with T13, without a bar; `eval/run_eval.py` computes
  it after the lock, and the check refuses test units before the `targets-locked` tag. A
  miss found there is reported and the point added to the map.
- **Also.** T7's pass probabilities are stored to four decimals: rounded to three and then
  printed as a whole percent, 98.54% appeared as 98%.
- **Consequences.** No bar, pilot estimate or test unit changes.
