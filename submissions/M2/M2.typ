#import "base.typ": *
#show: setup.with(title: "Differential - M2 Design and approach", short: "M2 · Design and approach")

#title-block(
  title: [Differential: design and approach],
  subtitle: "Milestone 2 · Design / approach",
  meta: ("PRV 201 Frontiers of Technology (AI)", "Track A: Build", "Stevens Institute of Technology", "October 2026"),
)
*Executive summary.* Differential helps a qualified bench technician find the failed part in analog audio equipment. For a modeled circuit it simulates every cataloged single-part fault under part tolerances, keeps a probability for every suspect and for "no single fault fits", recommends the measurement expected to rule out the most suspects per unit of effort, and explains each step; a language model reads complaints and meter photos and writes explanations, while code enforces safety and checks that every number traces to a measurement. This document specifies that design and the plan that tests it against the success criteria locked in M1 (git tag `targets-locked`). Part 1 — Requirements, architecture and plan traces requirements to code and tests and sets the plan and risks; Part 2 — Circuits, simulation and data specifies circuits, faults, simulation and data; Part 3 — Diagnosis engine and evaluation plan the inference, measurement choice, calibration and evaluation statistics; Part 4 — Agent, safety, security and interface the agent, the safety layer, the injection defense and the interface. Every major choice has an alternatives table.

#part(1, "Requirements, architecture and plan", "MEMBER_1")

*What changed since M1.* Instructor feedback on M1 had not been returned when this document was prepared. Before the targets were locked, M1 went through five rounds of our own AI-assisted review, each with three rubric-based reads, four reviewer perspectives (the course professor, an audio-electronics engineer, an ML methods reviewer, an ethics and policy scholar), a claim-to-source audit and, from the fourth round, a red team attacking the running app. @tab:feedback lists the findings that changed the design rather than the wording; the full log, with the commit that closed each item, is `feedback/FEEDBACK_LOG.md`. The largest changes came late: aged units now make up half of training, a fault audit checks the simulator with an independent solver, every method is charged for confirming its answer, and the safety layer enforces bench practice.

#figure(
  table(
    columns: (1.55fr, 2.1fr, 0.6fr),
    table.header([M1 review finding], [Design change], [Where]),
    [A hazard example (147 V at a tube cathode) was physically implausible], [Traced to a leakage resistor in the tube model; removed; circuits re-simulated, retrained and the hazard map re-audited], [Part 2],
    [Units reaching a bench are aged, but the engine trained on as-new parts], [Half of the training and validation units aged; aged pilot and test sets on every circuit; aged accuracy a primary target (T6)], [Part 2],
    [Fault behavior never checked outside the simulator], [53 randomly drawn faults re-solved by an independent solver from published device equations; agreement reported with its interval], [Part 2],
    [Test sets dropped faults that rarely cause a symptom; the only hardware target was small], [Every set samples symptomatic units; 60 faults inserted blind into three 24 V boards as a primary target (T7)], [Parts 2, 3],
    [Effort comparison favored the engine, which rarely paid for unsoldering], [Effort to a confirmed answer: one confirming unsoldering test charged to every unconfirmed answer; probing and unsoldering reported apart], [Part 3],
    [Bars close to certain to pass; rounding could undo the margin], [Met only when the one-sided 95% bound clears the bar; rounding never past the pilot estimate; joint chance of the primaries stated], [Part 3],
    [Safety judged point by point; bench habits missing], [Per-point discharge below 2 V; owner approval; bring-up gate; rated meter; discharge check lapses; leads clipped with the power off], [Part 4],
    [The model could record attestations the technician never gave], [Discharge, approval and bring-up records accepted only from the technician's own words], [Part 4],
    [No control for deskilling, blame or worker monitoring], [Trainee mode, sign-off limited to readings and plan, tickets per job not per person; study S1 with ethics review], [Part 4],
  ),
  caption: [M1 review findings that changed the design (all five rounds). Text-only fixes are in the log.],
) <tab:feedback>

*Requirements.* 20 requirements trace the M1 objectives (O1-O5), safety (S) and engineering practice (P) to the code that implements them and the tests or evaluations that verify them (Appendix A, @tab:reqs). 14 of them are checked by at least one locked target; the others (circuit library, fault catalog, simulation, ticket, modes and the clean-clone build) by unit tests and continuous integration. Every locked target is traced by at least one requirement. The matrix lives in `docs/requirements.yaml`; `tools/check_requirements.py` fails if a listed file or target disappears or a target is traced by no requirement.


*Architecture.* @fig:arch shows the three layers. Offline, each circuit model and its fault catalog are simulated with ngspice under part tolerances and learned into a model bundle (likelihoods, ambiguity groups, calibrated thresholds). Online, one Python process serves the web interface: the agent (Claude in live mode, templates offline, recorded responses in replay) calls tools that act only on an engine session, and the safety layer sits between every step and the technician. The evaluation layer runs every system on held-out simulated units and writes `results/metrics.json`, from which every number in these documents is rendered. Three invariants hold throughout: the ranking shown and written on the ticket comes only from the engine; only code decides what is safe; and no number reaches the technician unless it traces to a tool result or a reading the technician confirmed.

#figure(
  image("/results/figures/architecture.svg", width: 94%),
  caption: [Architecture. Blue: simulation and inference; orange: language layer; red: safety layer (code, not prompt); green: instruments; gray: interface and evaluation. The `make` target that builds each layer is in its title.],
) <fig:arch>

#figure(
  image("/results/figures/dataflow.svg", width: 82%),
  caption: [One diagnosis. Steps 5 to 10 repeat for every measurement; the safety layer screens the request (3), adds hazard text and the unsoldering lock to each step (6) and checks every number before the ticket (11).],
) <fig:flow>

*Build and deployment.* A clean clone runs in three commands (`git clone`, `make install`, `make demo`; ngspice must be installed): the trained models and evaluation sets are in the repository, the default mode needs no network, and a container image packs the same. Continuous integration runs the linter, strict type checks on the core package, the tests with a coverage floor of 85% and an evaluation smoke run on pilot units, so no check ever touches a test unit before the lock.

*Interfaces.* The engine exposes a session (prior, record a reading, recommend, posterior, stop status); the agent sees it only through JSON tools with typed arguments (Part 4 — Agent, safety, security and interface). Instruments share one interface with three back ends: the simulated bench used in evaluation and the demo, SCPI meters for the 24 V fault board (high-voltage points and readings beyond the board's range refused), and typed or photo readings the technician confirms. The language model client reads its key only from `DIFFERENTIAL_API_KEY`, caches responses and can replay a recorded session with no network.

#figure(
  table(
    columns: (1.0fr, 1.25fr, 1.95fr, 1.4fr),
    table.header([Choice], [Options], [Chosen, because], [Cost accepted]),
    [Who plans the diagnosis], [LLM agent plans; engine plans and LLM explains], [Engine: its probabilities can be calibrated and its choices tested on every unit], [Less free-form conversation],
    [Where it runs], [Cloud service; local process], [Local: shop data stays on the bench computer and it works offline], [Updates are manual; no fleet data],
    [Language model], [Claude; local open model; none], [Claude in live mode, rules and templates offline, so every target has an offline result], [Live results need a key and cost money],
    [Where numbers in documents come from], [Written by hand; rendered from results], [Rendered: every number traces to `metrics.json` or a recorded source quote], [Template tooling to maintain],
  ),
  caption: [Architecture alternatives and trade-offs.],
) <tab:arch-alt>

*Plan.* @tab:plan lists the work by lead role. The critical path runs through the full evaluation, which waits for nothing but compute, and the hardware check (T7), which needs three fault boards built and 60 blind insertions under the sealed-draw protocol. Work only people can do is listed in `SUBMISSION_GUIDE.md`: technician interviews, the timing study behind the effort weights, the adversarial prompts written outside the rule author (T16), the live language-model runs that need an API key, the ethics-board determination, and the technician study.

#figure(
  table(
    columns: (1.15fr, 1.6fr, 1.6fr, 1.35fr),
    table.header([Workstream (lead)], [Done by M2], [By M3], [By M5]),
    [Problem, stakeholders, regulation (lead 1)], [M1; constraints (@tab:constraints)], [Interviews; model and system cards], [Final report, profile, Q&A bank],
    [Circuits, simulation, data (lead 2)], [6 circuits; 253,000 units; hand checks; meter loading and aged units], [Three fault boards built; 60 faults recorded; transcription timed], [Hardware demo, low voltage only],
    [Engine, evaluation (lead 3)], [Engine, baselines, pilot, locked bars], [Full evaluation, ablations, failure analysis], [Results on slides; replay fallback],
    [Agent, safety, interface (lead 4)], [Agent, safety layer, trainee mode, demo app, meter reader], [Outside adversarial suite; live runs; screenshots and demo GIF], [Live demo and 90 s capture],
  ),
  caption: [Project plan by workstream. Leads are named in each part's header.],
) <tab:plan>

*Risks.* @tab:risks2 updates the M1 register with what changed; the controls themselves are specified in Parts 2 to 4.

#figure(
  table(
    columns: (1.35fr, 0.35fr, 2.2fr, 0.8fr),
    table.header([Risk], [L/I], [Status at M2], [Trigger to act]),
    [Simulation-to-reality gap], [H/H], [Meter loading, mains and aged units simulated; fault-board protocol and replay tool written, boards not built], [T6 or T7 missed],
    [Unsafe step near high voltage], [M/H], [Fault-conditioned map, notices, owner approval and per-point discharge readings implemented; the sweep passes in development against an independently recomputed map], [Any T15 failure],
    [Simulator artifact], [M/H], [One found by hand checks and fixed; fault behavior now spot-checked by hand], [A reading no physics explains],
    [Confident wrong diagnosis], [M/H], [Calibrated threshold for "no single fault fits"; calibration target T12], [ECE above bar],
    [Human studies not done], [H/M], [Protocols written; need an ethics-board determination, people and consent], [No interviews by M3],
    [Damage to the owner's unit], [M/M], [Owner's approval before removal; removed-parts log on the ticket], [Good parts removed in S1],
    [Deskilling; blaming workers], [M/H], [Trainee mode; sign-off limited to readings and plan; per-job tickets], [S1 over-reliance],
    [Live results pending], [M/M], [Offline fallbacks meet their targets alone; live runs need a key], [No key by M3],
  ),
  caption: [Risk register at M2 (likelihood/impact before controls, our judgment).],
) <tab:risks2>

*Industry and regulatory constraints.* @tab:constraints turns the rules identified in M1 into design requirements.

#figure(
  table(
    columns: (1.6fr, 2.4fr, 0.6fr),
    table.header([Constraint], [Design response], [Req.]),
    [Only qualified persons test live parts; parts under 50 V exempt only if that adds no burn or arc-blast exposure \[1, 2\]], [Licensed to repair shops; hands-off steps above 50 V; trainees supervised on high voltage; mains-side work refused], [R11-R13],
    [People told when they deal with an AI \[3\]], [Every screen and ticket names the AI and its role], [R16],
    [Annex III: AI that evaluates workers or learners is high-risk \[3\]], [Sign-off records identify the job, not the technician's performance; the trainee log is for the trainee; the license forbids rating staff], [R16],
    [Software counts as a product; personal injury and damage to consumer property covered \[4\]], [Stated performance, warnings and change log kept with each release; model pinned; owner's approval before parts are removed], [R17],
    [Service manuals are copyrighted documents], [Circuit models transcribed by the shop stay with it; none shipped], [R1],
    [Shop and customer data], [Offline by default; photos stripped of metadata; key never logged], [R8, R17],
  ),
  caption: [Constraints on the design and where the requirements meet them.],
) <tab:constraints>

#decision("Code enforces three invariants the language model cannot change")[
*Options:* let an LLM agent plan and police itself with instructions, or put ranking, safety and number-checking in code around it. *Choice:* code. The engine alone ranks faults, the safety layer alone decides what a step must say or refuse, and the grounding check alone lets a number through. *Why:* each invariant can then be tested exhaustively (T15, T17) and holds in offline mode, where no model runs. *Consequence:* the language model is replaceable, and its failures cost explanation quality, not safety or accuracy.
]

#part(2, "Circuits, simulation and data", "MEMBER_2")

*Circuit library.* Six circuits are modeled (@tab:circuits): five original blocks with the standard topologies of preamplifier and line-level gear, and a channel strip that chains them. Each circuit is a SPICE netlist plus a sidecar file listing every part with its kind and tolerance, every test point with its node, stage, allowed measurements and hazard flag, and service notes. The channel strip joins the five netlists, keeps one signal source and load, and renumbers the test points; a test fails if the composed files fall out of date. Device models are Koren's published 12AX7 equations, with amplification factor and emission exposed so that tube wear can be simulated; a behavioral op-amp with controls for gain-bandwidth and a stuck output; and standard 2N3904, 1N4148 and 1N4745A models. The rectifiers are modeled as a quasi-static source plus a ripple current, which a full transient simulation of the rectifier and reservoir confirms within 2.4-5.4% (the model slightly overstates hum).

#figure(
  table(
    columns: (1.0fr, 2.4fr, 0.55fr, 0.55fr, 0.75fr, 0.8fr),
    table.header([Circuit], [Topology], [Parts], [Faults], [Test points (HV)], [Readings + lift tests]),
    [Supply], [Zener-regulated low-voltage rail and a 250 V tube supply], [14], [63], [6 (3)], [12 + 14],
    [Tube stage], [12AX7 common-cathode gain stage], [8], [31], [4 (2)], [11 + 8],
    [Tone stack], [Passive bass-and-treble tone stack], [9], [27], [3 (0)], [8 + 9],
    [Op-amp stage], [Op-amp gain stage], [13], [56], [6 (0)], [14 + 13],
    [Line driver], [Two-transistor line driver], [15], [73], [7 (0)], [16 + 15],
    [Channel strip], [The five blocks chained: supply, tube stage, tone stack, op-amp, driver], [59], [250], [23 (5)], [51 + 59],
  ),
  caption: [Circuit library. HV: test points that can exceed 50 V in normal operation or under a cataloged fault. Readings: DC voltages, gains at three frequencies, hum and distortion where the circuit allows them.],
) <tab:circuits>

*Fault catalog.* Every part can fail in each of the modes of its kind (@tab:faults), and each simulated unit draws the severity of its fault (a short's residual resistance, how far a value has drifted), so a cataloged fault is a distribution, not one number. Units outside the catalog test "no single fault fits": most carry two faults on different parts, drawn from faults that usually cause a symptom; the rest carry a solder bridge between two nodes of one stage, or a passive part fitted with a wrong value.

#figure(
  table(
    columns: (1.0fr, 3.2fr),
    table.header([Part kind], [Failure modes (severity drawn per unit)]),
    [Resistor], [Open; short (below an ohm); value drift to a half, double or ten times],
    [Film capacitor], [Open; short],
    [Electrolytic capacitor], [Open; short; capacitance down to a half or a tenth; series resistance up ten- to a hundredfold],
    [Potentiometer], [Wiper open; track open on either side],
    [Diode, zener], [Open; short],
    [Transistor], [Collector-emitter short; base open; gain down to a fifth; collector-base leakage],
    [Triode], [Low emission; heater open],
    [Op-amp], [Output stuck at a rail; gain-bandwidth down ten- to a hundredfold],
  ),
  caption: [Fault modes by part kind (18 in all). Every mode of every part is one hypothesis; with "healthy" and "no single fault fits" the channel strip has 252 hypotheses.],
) <tab:faults>

*Monte Carlo design.* A simulated unit draws every part within its tolerance: values from a normal distribution with a standard deviation of half the tolerance, truncated at the tolerance; electrolytic series resistance, transistor gain, tube amplification and emission and op-amp bandwidth from their own spreads, and the mains level within ±5% as a common factor on both rectifier peak voltages. Units that reach a bench are old, so every second training, validation and calibration unit (50%) first drifts the way parts age: electrolytic capacitance ×0.7-0.95 and series resistance ×1.2-3, resistors ×1.00-1.1, tube emission ×0.7-1.00 (ADR-039). A symptom is still judged against an as-new healthy unit. The aged pilot and test sets are aged throughout and have the same circuit mix as the as-new sets; units with every tolerance 1.5, 2.0, 3.0 times wider are reported as a curve. Each hypothesis gets 400 training and 100 validation units. Every unit's random numbers derive from a seed built from the base seed, circuit, split, hypothesis and draw, so any unit can be regenerated alone; a test re-simulates stored units and compares them to six significant figures. Units are simulated in ngspice batches of 50, with a three-step retry ladder (finer convergence settings, then a stiffer integration method) for batches that fail; failed units are kept with a reason and excluded from training. Of 253,000 units, 0 failed and 0 needed a retry. A manifest records the hashes of every netlist, the device library and the tolerance code, and the simulator version. Each unit is simulated at its DC operating point, for gain at 20 Hz, 1 kHz and 20 kHz, for hum at 120 Hz, and for distortion at 1 kHz from a transient and Fourier analysis.

*Measurement model.* Every DC reading is simulated with the meter's 10 MΩ input resistance across the node, one operating point per reading, as a real meter loads a high-impedance node \[5\]; the unloaded voltage is kept for the hazard audit and the hand checks. A simulated reading is that value plus instrument error: a meter of ±(0.5% + 2 counts) on 6,000-count ranges, rounded to the range's resolution; an oscilloscope of ±3%, with floors for tiny signals; a distortion reading of ±10%. An unsoldered part tested out of circuit returns only "within" or "out of tolerance", with sensitivity 0.97 and 1% false positives. The engine works in transformed units (DC voltages on a scale that is linear near zero and logarithmic above it, gains and hum in decibels), where instrument error is close to constant.

*Data splits.* @tab:splits lists every set. Evaluation sets sample symptomatic units uniformly: each case draws a hypothesis and a unit and keeps it only if the unit shows a symptom (up to 200 draws), so faults appear in proportion to how often they cause a symptom, which is not how often they fail in service; faults that never showed a symptom in training are left out.

#figure(
  table(
    columns: (1.05fr, 2.3fr, 1.45fr),
    table.header([Split], [Used for], [Size]),
    [Train], [Fitting likelihood models and the symptom model], [400 units per hypothesis],
    [Validation], [Ambiguity groups, calibration of the classifier, the symptom model and "no single fault fits"], [100 units per hypothesis; 60 + 20 per block outside the catalog],
    [Pilot], [Setting bars only], [200 + 60 per block, as-new and aged; 125 + 25 outside; 150 wide],
    [Test], [Locked targets, once, after the lock], [500 + 100 per block, as-new and aged; 250 + 50 outside; 300 each at three widths],
  ),
  caption: [Data splits. Seed streams are disjoint; "+ n per block" counts each of the five blocks; "wide": channel strip with tolerances 1.5 times wider.],
) <tab:splits>

*Data quality.* Five checks guard the data. (1) Independent hand calculations reproduce every healthy bias point and gain (22 of 22 within tolerance). (2) Fault behavior is audited: 53 faults drawn at random (up to two of each fault type per circuit) are re-solved without ngspice and without the netlist builder, by a solver written for the audit with the published device equations, and all 53 agree within twice the meter's accuracy (ADR-040; the first run's disagreements, all in the audit solver, are on record); an earlier spot check found the tube-model artifact, where a leakage resistor put an open-circuit cathode at half the plate voltage, fixed before any bar was set. (3) Stored units regenerate from their seeds, and the manifest ties every dataset to the code that produced it. (4) Complaint texts pass a leakage filter that rejects any text naming a part or a fault. Evaluation complaints come from a held-out paraphrase bank never used to write or tune the reader, with each shown symptom left out with probability 20% and each other symptom added with 2%; a second bank, written by a separate author who never saw the rules and sealed until the lock, tests T18. (5) Ambiguity groups and symptom rates are reported per circuit, so a reader can see how often faults are indistinguishable or silent.

#figure(
  table(
    columns: (1.0fr, 1.5fr, 2.0fr, 1.35fr),
    table.header([Choice], [Options], [Chosen, because], [Cost accepted]),
    [Simulator], [ngspice; LTspice; Xyce; analytic models], [ngspice: open source, batch-scriptable, installs in CI], [Slower than analytic models],
    [Part spread], [Uniform over the band; truncated normal], [Truncated normal: parts cluster near nominal; the stress set widens it], [Real batches may be skewed],
    [Fault set], [Nominal fault dictionary; catalog under tolerances; repair logs], [Catalog under tolerances: gives spreads, not points; no logs exist], [Single static faults only],
    [Units per hypothesis], [50 to 400], [400, with 50, 100 and 200 as an ablation], [253,000 simulations],
  ),
  caption: [Simulation and data alternatives and trade-offs.],
) <tab:sim-alt>

#decision("Simulate every fault under tolerances instead of one nominal fault dictionary")[
*Options:* the classic fault dictionary (one nominal simulation per fault, then nearest match) or many simulated units per fault with every part inside its tolerance. *Choice:* many units per fault. *Why:* tolerance spread is exactly what makes bench diagnosis hard, and probabilities need the spread of each fault's readings, not one point. *Consequence:* 253,000 simulations and learned likelihoods, and ambiguity groups measured from data rather than assumed.
]

#part(3, "Diagnosis engine and evaluation plan", "MEMBER_3")

*Likelihoods.* The engine needs the probability of any subset of readings under every hypothesis, because the technician measures one thing at a time. The core model fits, for each hypothesis, a Gaussian mixture of one to 3 full-covariance components on its training units in transformed units, choosing the number by the Bayesian information criterion (k components only with at least 25k units), and adds instrument noise to each component. Any subset of readings is then handled exactly, by keeping only the observed dimensions. The alternative, a LightGBM classifier, is trained on 3 copies of the training units with readings hidden at random (each row keeps each reading with a probability drawn between 0.05 and 0.95) and temperature-scaled on masked validation units; its posterior divided by the training class frequencies is a likelihood up to a constant, so both models feed the same update. The trees give no distribution over readings not yet taken, so the tree engine chooses measurements with the mixtures' predictive update, starting from its own current belief.

*"No single fault fits".* A further hypothesis with prior 0.05 gives every reading a flat density over its plausible range. Its level per observed reading is calibrated on validation units: the largest level that flags at most 5% of symptomatic single faults (200 channel-strip units, 80 per block) against double-fault and modified units. It is calibrated twice, for sessions whose prior was read from a complaint and for all others, because a complaint concentrates the prior and changes what "no fit" competes with.

*Ambiguity groups.* Some faults give the same readings at every test point. Each hypothesis's 40 validation units are scored with every reading; hypotheses confused with each other at a mean rate of at least 0.1 are joined, and groups are the connected sets. On the channel strip 251 hypotheses form 217 groups, 191 of size one and none larger than 4. The engine reports groups, and accuracy is scored on them.

*Measurement choice and stopping.* For every affordable measurement the engine estimates the expected information gain over the group posterior and "no single fault fits", from 128 readings sampled from the current predictive mixture, and divides it by the measurement's effort; for a lift test the two outcomes are enumerated exactly. Near-ties go to the low-voltage, then the cheaper, measurement. A session stops when one group or "no single fault fits" reaches 90%, when the budget of 40 effort units cannot pay for another measurement, or when no measurement promises 0.001 bit.

*Complaint prior.* 8 symptom features (no output, low gain, hum, distortion, DC at the output, bias drift, bass or treble loss, a dead or drifted rail) are computed from every simulated unit with fixed thresholds, for example gain more than 3 dB low or hum 6 dB above the healthy spread. How often each fault shows each feature gives a likelihood for the features a complaint reports; two smoothing parameters are chosen on validation complaints. A complaint that reports nothing recognized leaves the prior uniform.

*Evaluation plan.* Every system runs on the same test units with the same instrument noise (common random numbers), so comparisons are paired (@tab:systems). Statistics: a target is met only when its one-sided 95% confidence bound clears the bar, so a point estimate above the bar is not enough. Proportions on one circuit (T2, T7, T19) use exact binomial bounds; rates pooled over circuits (T1, T3, T6, T13), paired differences, effort ratios, calibration and AUROC use percentile bootstrap bounds over units (2,000 resamples); paired accuracy also gets an exact McNemar test. Effort is the effort to a confirmed answer: every method is charged one unsoldering test of its named suspect unless it already unsoldered and confirmed one (ADR-041); raw effort and its probing and unsoldering parts are reported beside it. An effort ratio counts only if the system's top-1 accuracy is at most 2 points below the comparator's. Calibration (T12) is the expected calibration error over 10 equal-mass bins of the three probabilities shown when a diagnosis stops, with Brier score, log loss and every-step calibration reported. Misleading outcomes on out-of-model units (T13) are those that send the technician to a healthy part; flags and AUROC (T22) and the share of single faults named (T23) are reported beside them. Bars come from the pilot by the rule fixed in M1: the pilot estimate moved 1.5 standard errors against the system, pooled with the test set's circuit mix (channel strip 0.5, each block 0.1). The failure analysis breaks misses down by circuit, part kind, fault mode, symptom rate and group size, and separates wrong names from "no single fault fits" calls.

#figure(
  table(
    columns: (1.35fr, 2.6fr, 0.9fr),
    table.header([System], [What it is], [Targets]),
    [Random probing], [Uniformly random affordable readings; never unsolders], [T4, T10],
    [Fixed-order chart], [A textbook chart's order: rails, output, signal path, stage DC, hum, response; unsolders its leading suspect at 50% belief or when the chart is used up], [T4, T8],
    [Half-split tracing], [Rails first, then a binary search along the signal path with a test tone, then the first bad stage's DC points; unsolders like the chart], [T4, T9],
    [Engine], [Generative likelihoods, uniform prior, effort-weighted information gain], [T4, T8-T10, T14],
    [Engine, classifier likelihood], [The same with LightGBM likelihoods], [Ablation],
    [Full system], [Engine plus the complaint prior from the offline reader], [T1-T3, T5, T6, T11-T13, T22, T23],
    [Language model alone], [Sees what a technician sees; asks for readings; same budget], [T5],
    [Language model with simulator], [The same plus a tool returning each fault's median readings], [Reported],
    [Ablations], [Noise-free complaints; the development bank; a capacitor-heavy prior and test mix; 50-200 units per hypothesis; information gain without effort; each effort weight halved and doubled], [T14; analysis],
  ),
  caption: [Systems in the evaluation and the targets they serve (target definitions in M1, Table 3).],
) <tab:systems>

#figure(
  table(
    columns: (1.0fr, 1.55fr, 2.0fr, 1.3fr),
    table.header([Choice], [Options], [Chosen, because], [Cost accepted]),
    [Likelihood], [Gaussian mixtures; kernel density; normalizing flows; boosted trees; Bayesian network], [Mixtures: exact on any subset of readings, few parameters per fault; boosted trees kept as a check], [Assumes smooth, roughly unimodal spreads],
    [Measurement choice], [Fixed chart; half-splitting; information gain; multi-step lookahead], [Information gain per unit effort, one step ahead: cheap per step, the entropy rule of model-based diagnosis \[6\] with a cost term; optimal sequencing needs a search \[7\]], [Can be myopic on long plans],
    [Unmodeled units], [None; fixed threshold; calibrated flat hypothesis; learned detector], [Calibrated flat hypothesis: fits the Bayesian update, tunable to a false-alarm budget], [Flags only part of double faults],
    [Statistics], [Normal approximations; bootstrap; exact tests], [Bootstrap and exact tests: no normality assumption at 0 % or 100 %], [Compute],
  ),
  caption: [Engine and evaluation alternatives and trade-offs.],
) <tab:engine-alt>

#decision("Choose one measurement at a time by information per unit of effort")[
*Options:* follow a fixed chart, plan several steps ahead, or pick the single next measurement with the highest expected information gain per unit of effort. *Choice:* one step at a time, the one-step entropy rule of model-based diagnosis \[6\] with a cost per measurement, instead of the search an optimal test sequence needs \[7\]; it needs no plan to be revised when a reading surprises. *Why:* each recommendation takes a fraction of a second (T20) and adapts to every reading. *Consequence:* the engine can be myopic when two cheap readings together would beat one expensive one; the ablation without effort weights and the comparison with half-split tracing show how much this costs.
]

#part(4, "Agent, safety, security and interface", "MEMBER_4")

*Agent.* The agent runs in three modes: live (Claude, with the key read only from `DIFFERENTIAL_API_KEY` and every response cached), offline (the rule-based complaint reader and templated explanations, with no network) and replay (cached responses, falling back to offline on any miss). Each turn runs in a fixed order: request screening, then tool calls, then the grounding check, then the output check (@fig:flow). The model can call 14 tools (@tab:tools), all acting only on the current diagnosis session: none writes files, drives an instrument or reaches any service other than the language model itself. Its instructions say to use the tools for every fact, to report probabilities and ambiguity groups as the tools give them, and to treat service notes as untrusted data; no safety property depends on the model following them.

#figure(
  table(
    columns: (1.25fr, 3.0fr),
    table.header([Tool], [What it returns or does]),
    [`list_circuits`, `describe_circuit`], [Available circuits; stages, test points and parts, with service notes wrapped as untrusted text],
    [`parse_symptoms`], [Symptom features read from the complaint (Claude, or the rules offline); sets the prior],
    [`get_belief`, `ambiguity_groups`], [Ranked fault groups, the probability that no single fault fits, effort spent, whether the engine would stop; groups the test points cannot separate],
    [`recommend_measurement`], [The next step: what, where and how, effort, information, alternatives, predictions and the safety text from code],
    [`expected_readings`], [Each suspect's predicted reading and 95 % range for a measurement],
    [`record_measurement`], [Stores a reading; accepted only if the technician typed or confirmed that value],
    [`safety_brief`, `confirm_discharge`, `approve_part_removal`, `confirm_bring_up`], [High-voltage and discharge instructions; records the owner's approval for removing parts; readings below 2 V at every point that can hold high voltage, which unlock part removal for 5 minutes (or until the next powered reading with a bleeder attached); how the unit was first powered],
    [`read_meter_photo`], [A proposed reading with plausibility checks; recorded only after confirmation],
    [`generate_repair_ticket`], [Diagnosis, evidence trail, actions and safety lines, for sign-off],
  ),
  caption: [The agent's tools.],
) <tab:tools>

*Grounding.* Every number in a reply that looks like a reading (it has a unit or a decimal point, or exceeds 12) must match a number in a tool result, the technician's messages or a confirmed photo reading, up to the rounding of the digits shown and allowing for units. In live mode the model gets one chance to rewrite; any number still unmatched is replaced by "[value withheld: not from a measurement or tool]". The ticket passes the same check (T17).

*Safety layer.* Code, not the prompt, decides what is safe. (1) Requests are screened before any model or tool sees them: 5 categories are refused with fixed texts (fuse bypass, ground lift, interlock defeat, mains-side work, hands-in work on live high voltage); out-of-scope equipment such as microwave ovens and CRTs is declined; pressure for certainty gets calibrated language. (2) Each step at a point that can exceed 50 V, normally or under any cataloged fault, carries hands-off clip-lead instructions and discharge through a resistor tool; in a chassis with a high-voltage supply every powered step carries a "high voltage inside" notice; oscilloscope steps carry a ground-clip warning; a point missing from the hazard map counts as high voltage, and so does every point of a unit whose model has not been checked against an independent reference when its supply can exceed 50 V. (3) Removing a part needs the owner's recorded approval and, in a high-voltage unit, a reading below 2 V at every point that can hold high voltage (one reading counts only for the main filter capacitor unless the technician states it holds for all points); the readings are logged as the technician's attestation; the check lapses after 5 minutes unless the technician records a bleeder across the main filter capacitor, because a discharged capacitor recovers some charge, and any later powered reading locks removal again. (4) Bench practice (ADR-042): in a unit with a high-voltage supply or its own mains rectifier, no powered step is shown and no powered reading accepted until the technician records how the unit was first powered (variac, series lamp, current-limited supply, or already running normally); powered steps in a high-voltage unit name a meter rated CAT II 600 V or better (IEC 61010) and say to clip the leads on with the power off. In live mode the model cannot make these attestations: its calls to record discharge readings, owner approval or bring-up are refused unless the technician's own words carry them. Non-finite readings are refused. (5) Outgoing text is checked: an unsafe instruction replaces the whole message, false certainty is reworded, and missing high-voltage text is appended. The exhaustive sweep behind T15 checks every possible step of every circuit; in development it checked 491 required steps with 0 false high-voltage alarms on low-voltage steps, and on the photos it was developed on the offline meter reader read 99.3% exactly.

*Prompt-injection defense.* Three layers. First, retrieved text is data: service notes carry a trust label and are flagged when they match any of 11 instruction patterns, and complaints reach the extractor inside tags as data. Second, a persuaded model still cannot act: its tools touch only the session, readings need the technician, and the grounding and output checks run after it. Third, testing: the channel strip ships a poisoned service note, which the sweep confirms is flagged and refused, and the adversarial suite for T16 (at least 300 prompts from team members, another PRV 201 team and a separately prompted model, none of whom saw the rules, each also posed inside attack styles, plus benign controls for over-refusal) is scored once, so the rules are not tuned to it. Each grading round also sends a fresh red-team agent against the running app.

#figure(
  image("/results/figures/wireframe.svg", width: 88%),
  caption: [Interface wireframe (the working interface is shown in M3). Hazard rings, the safety banner and the unsoldering lock come from the safety layer; every proposed photo reading waits for the technician.],
) <fig:wire>

*Human in the loop.* The technician measures, types or photographs each reading and confirms it; a photo reading comes with a plausibility check against the step it is for (meter function, range, unit slips, reversed leads and, for DC, the suspects' predicted range). "Why this?" shows the alternatives with their information and effort and each suspect's predicted range; the belief panel always shows runner-ups and "no single fault fits"; the ticket needs the technician's sign-off (@fig:wire). The header states that Differential is an AI assistant that recommends while the technician decides. Trainee mode withholds the recommended step until the trainee records their own choice (both are logged) and requires a named supervisor for high-voltage units. The sign-off confirms the readings and the plan, not the diagnosis, and tickets belong to the job, not to a person's record. Study S1 on the 24 V fault board is pre-registered with no bar: at least six technicians diagnose inserted faults with and without the tool in counterbalanced order (time to the correct part, parts unsoldered, wrong replacements), and one session plants a wrong recommendation on a non-hazardous step to measure over-reliance, only after an ethics-board determination, with consent that discloses it and a debrief.

#figure(
  table(
    columns: (0.35fr, 2.2fr, 1.6fr),
    table.header([Level], [Who does what], [Example]),
    [L0], [The technician does everything], [Chart, meter and experience],
    [L1], [The tool supplies information but recommends nothing], [Expected readings, service notes],
    [*L2*], [*The tool recommends the next measurement and names suspects; the technician chooses, takes and confirms every measurement*], [*Differential*, including SCPI readings the technician triggers on the 24 V board],
    [L3], [The tool measures through instruments or a fixture while a technician supervises], [Automated test station with an operator],
    [L4], [An automated fixture diagnoses without a technician], [Unattended production test],
  ),
  caption: [Levels of diagnostic autonomy, our own scale defined by analogy to driving automation (whose SAE scale has six levels). Differential stays at L2 because a wrong step near high voltage can injure the person holding the probe, and each measurement and repair decision must remain a qualified person's.],
) <tab:autonomy>

#figure(
  table(
    columns: (0.9fr, 2.55fr, 0.95fr),
    table.header([Value], [Design feature], [Checked by]),
    [Human agency], [The technician measures, confirms every reading and signs the ticket; trainee mode asks for the trainee's own step first], [T17; sign-off],
    [Transparency], [AI disclosure; "Why this?"; runner-ups and "no single fault fits" always shown; evidence trail], [T12, T13],
    [Safety], [Rules in code; hazards conditioned on faults; unknown points and unchecked models treated as high voltage; owner approval and per-point discharge readings before removal], [T15, T16],
    [Privacy], [Offline by default; photo metadata removed; no customer identity in tickets; key never logged], [Tests],
    [Fairness], [Complaint reading scored by writer voice; a wrong prior tested both ways; errors by circuit, part and who bears them], [T14, T18],
    [Accountability], [Logged tool calls, grounding and safety events; pinned model; signed tickets], [Export],
  ),
  caption: [Ethics by design.],
) <tab:ethics>

#figure(
  table(
    columns: (1.0fr, 1.55fr, 2.0fr, 1.3fr),
    table.header([Choice], [Options], [Chosen, because], [Cost accepted]),
    [Safety enforcement], [Prompt only; code; a second moderation model], [Code: deterministic, testable on every step, works offline], [Pattern lists need upkeep and can over-refuse],
    [Complaint reading], [Rules; language model; model with rules fallback], [Model with rules fallback: every target has an offline result], [Rules miss unusual phrasings (T18)],
    [Meter photos], [Generic OCR; vision model; purpose-built reader plus vision model], [Both readers propose; the technician confirms], [Offline reader knows one meter design],
    [Interface], [Chat only; panels plus chat], [Panels plus chat: the state is always visible, not buried in text], [More interface to maintain],
  ),
  caption: [Agent, safety and interface alternatives and trade-offs.],
) <tab:agent-alt>

#decision("A photo or model reading is a proposal until the technician confirms it")[
*Options:* let the vision model or the agent record readings directly, or treat every such reading as a proposal. *Choice:* proposal. *Why:* a misread digit would be an invented reading that the engine then trusts; the confirmation step, with its plausibility check, is where a technician catches it (T17, T19). *Consequence:* one more action per photo, and no reading reaches the engine that a person has not seen.
]

// END-PARTS

#heading(level: 1, numbering: none)[References]
#ref-entry(1)[U.S. Occupational Safety and Health Administration, “29 CFR 1910.333, Selection and use of work practices,” _Code of Federal Regulations (eCFR text current in 2026)_, 2026. [Online]. Available: #link("https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.333")[https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.333].]
#ref-entry(2)[U.S. Occupational Safety and Health Administration, “29 CFR 1910.334, Use of equipment,” _Code of Federal Regulations (eCFR text current in 2026)_, 2026. [Online]. Available: #link("https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.334")[https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.334].]
#ref-entry(3)[European Parliament and Council of the European Union, “Regulation (EU) 2024/1689 of 13 June 2024 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act), original text,” _Official Journal of the European Union, OJ L, 2024/1689_, Jul. 12, 2024. [Online]. Available: #link("https://eur-lex.europa.eu/eli/reg/2024/1689/oj")[https://eur-lex.europa.eu/eli/reg/2024/1689/oj].]
#ref-entry(4)[European Parliament and Council of the European Union, “Directive (EU) 2024/2853 of 23 October 2024 on liability for defective products and repealing Council Directive 85/374/EEC,” _Official Journal of the European Union, OJ L, 2024/2853, 18 Nov. 2024_, Oct. 23, 2024. [Online]. Available: #link("https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng")[https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng].]
#ref-entry(5)[Fluke Corporation, “Fluke 114, 115, 116 and 117 Digital Multimeters: Extended specifications,” _Fluke specification sheet (document 2793260, 6116-ENG Rev A, per file name)_, n.d. [Online]. Available: #link("https://dam-assets.fluke.com/s3fs-public/2793260_6116_ENG_A_W.PDF")[https://dam-assets.fluke.com/s3fs-public/2793260\_6116\_ENG\_A\_W.PDF] (accessed Sep. 29, 2026).]
#ref-entry(6)[J. de Kleer and B. C. Williams, “Diagnosing multiple faults,” _Artificial Intelligence_, vol. 32, no. 1, pp. 97–130, Apr. 1987. doi: 10.1016/0004-3702(87)90063-4.]
#ref-entry(7)[K. R. Pattipati and M. G. Alexandridis, “Application of heuristic search and information theory to sequential fault diagnosis,” _IEEE Transactions on Systems, Man, and Cybernetics_, vol. 20, no. 4, pp. 872–887, Jul./Aug. 1990. doi: 10.1109/21.105086.]
#ref-entry(8)[Boston Consulting Group, “Executive Perspectives June 2026: Field Service Operations (The Future of Field Service with Applied AI),” Jun. 2026. [Online]. Available: #link("https://www.bcg.com/assets/2026/executive-perspectives-future-of-field-service-with-applied-ai.pdf")[https://www.bcg.com/assets/2026/executive-perspectives-future-of-field-service-with-applied-ai.pdf] (accessed Sep. 28, 2026).]
#ref-entry(9)[“US recorded-music revenues grew by 6.9% in the first half of 2026,” _Music Ally_, Sep. 1, 2026. [Online]. Available: #link("https://musically.com/2026/09/01/us-recorded-music-revenues-grew-by-6-9-in-the-first-half-of-2026/")[https://musically.com/2026/09/01/us-recorded-music-revenues-grew-by-6-9-in-the-first-half-of-2026/] (accessed Sep. 28, 2026).]
#ref-entry(10)[H. Bastani, O. Bastani, A. Sungu, H. Ge, Ö. Kabakcı, and R. Mariman, “Generative AI without guardrails can harm learning: Evidence from high school mathematics,” _Proceedings of the National Academy of Sciences_, vol. 122, no. 26, 2025. [Online]. Available: #link("https://doi.org/10.1073/pnas.2422633122")[https://doi.org/10.1073/pnas.2422633122] (accessed Sep. 28, 2026).]
#ref-entry(11)[European Parliament and Council of the European Union, “Regulation (EU) 2026/1744 of 8 July 2026 amending Regulations (EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230 as regards the simplification of the implementation of harmonised rules on artificial intelligence (Digital Omnibus on AI),” _Official Journal of the European Union, OJ L, 2026/1744, 24 Jul. 2026_, Jul. 8, 2026. [Online]. Available: #link("https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng")[https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng].]
#ref-entry(12)[European Commission, “Commission starts enforcing AI Act rules and new transparency requirements on 2 August (IP/26/1714),” Press release, Jul. 31, 2026. [Online]. Available: #link("https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august")[https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august] (accessed Sep. 28, 2026).]

#heading(level: 1, numbering: none)[Appendix A · Requirements traceability matrix]
#[
#show figure: set block(breakable: true)
#figure(
  table(
    columns: (0.3fr, 2.5fr, 0.42fr, 1.6fr, 0.75fr),
    table.header([ID], [Requirement], [From], [Verified by], [Targets]),
    [R1], [Model six circuits (five blocks and a channel strip) with netlists, part tolerances, test points and hazard flags], [O1], [test\_circuits.py, tools/hand\_calcs.py], [—],
    [R2], [Enumerate every plausible single-part fault per part kind, with severity drawn per unit], [O1], [test\_sim.py], [—],
    [R3], [Simulate at least 200 Monte Carlo draws per fault hypothesis with ngspice, reproducibly], [O1], [test\_reproducibility.py, test\_sim.py], [—],
    [R4], [Keep a calibrated probability for every fault group and for "no single fault fits"], [O1, O3], [test\_engine.py, run\_eval.py], [T1, T2, T3, T12, T13, T22, T23],
    [R5], [Recommend the measurement with the most expected information per unit of effort], [O2], [test\_engine.py, run\_eval.py], [T8, T9, T10],
    [R6], [Beat scripted, random and LLM-only baselines at the same budget], [O1], [run\_eval.py, llm\_baseline.py], [T4, T5],
    [R7], [Turn a plain-language complaint into symptom features and a prior, offline or with Claude], [O5], [nlp\_benchmark.py, test\_agent.py], [T11, T18],
    [R8], [Read a meter photo as a proposal the technician must confirm], [O5], [test\_vision.py, test\_server.py, meter\_eval.py], [T19],
    [R9], [Hold up on parts outside their nominal spread and on real hardware], [O1], [run\_eval.py, hardware/fault\_board/procedure.md], [T6, T7],
    [R10], [Stay robust to a wrong prior, in either direction], [O3], [run\_eval.py], [T14],
    [R11], [Attach hands-off and discharge instructions wherever a point can exceed 50 V, normally or under any fault], [S], [test\_safety.py, safety\_sweep.py], [T15],
    [R12], [Lock unsoldering in high-voltage circuits until a discharge below 2 V is confirmed], [S], [test\_agent.py, test\_server.py], [T15],
    [R13], [Refuse mains-side work, protection bypasses and unsafe requests in every mode], [S], [test\_safety.py, redteam/harness.py], [T16],
    [R14], [Treat retrieved text (service notes, photos) as data, never as instructions], [S], [test\_safety.py], [T16],
    [R15], [Trace every number in a message or ticket to a tool result or the technician], [O4], [test\_grounding.py, agent\_eval.py], [T17],
    [R16], [Produce a repair ticket with diagnosis, evidence trail and technician sign-off], [O3], [test\_agent.py, test\_server.py], [—],
    [R17], [Offer live, offline and replay modes; read the key only from DIFFERENTIAL\_API\_KEY], [P], [test\_agent.py], [—],
    [R18], [Talk to real instruments over SCPI at 24 V or less, refusing high-voltage points], [S], [test\_instruments.py], [T7],
    [R19], [Answer each step fast and each diagnosis cheaply], [O5], [run\_eval.py, agent\_eval.py], [T20, T21],
    [R20], [Run from a clean clone in three commands, offline, with tests, types and coverage in CI], [P], [.github/workflows/ci.yml], [—],
  ),
  caption: [Requirements traceability. "From": M1 objective (O1 accuracy, O2 effort, O3 honesty, O4 safety, O5 practicality), safety (S) or engineering practice (P). Test files are in `tests/`, evaluation scripts in `eval/`.],
) <tab:reqs>
]

#heading(level: 1, numbering: none)[Appendix B · Industry watch]
#set text(size: 9pt)
- *Field-service AI grows with a technician shortage (BCG, June 2026).* BCG reports that a shortage of technician talent keeps intensifying field-service pain points and describes technician copilots as "creating knowledge bases across technology generations" \[8\]. Differential's explanations in physical terms and the planned technician study address whether a tool transfers skill or replaces it.
- *Analog playback keeps growing (RIAA, first half of 2026).* U.S. vinyl revenue rose 17.7% to \$554 million and physical revenue 25.9% \[9\]. More analog playback in use suggests more analog gear to repair, although no source measures repair demand directly.
- *Unguarded AI can harm learning.* Students who practiced with a plain chat interface scored 17% worse than those who never had access once it was removed, while tutor-style hints largely prevented the harm \[10\]. This supports showing reasons and runner-ups rather than bare answers, and measuring over-reliance in the technician study.
- *EU high-risk rules move (Digital Omnibus, July 2026).* The Omnibus sets the high-risk rules to apply from 2 December 2027 for Annex III systems and 2 August 2028 for Annex I systems \[11\]; the transparency duty our interface meets applies from 2 August 2026 \[12\].

#heading(level: 1, numbering: none)[Appendix C · Course coverage map]
#figure(
  table(
    columns: (0.25fr, 0.95fr, 2.6fr, 0.55fr),
    [Wk], [Topic], [Where this design uses it], [Depth],
    [2], [AI/ML algorithms], [Gaussian mixtures, boosted trees, Bayesian updating, information-gain measurement choice (Part 3)], [Core],
    [3], [Python], [Simulation, engine, agent and evaluation code; requirements traced to it (Parts 1, 2)], [Core],
    [4], [Large language models], [Language layer and its limits; LLM-alone baselines (Parts 3, 4)], [Core],
    [5], [LLM-enhanced agents], [Tool design, turn order, grounding check (Part 4)], [Core],
    [6], [Building ML systems], [Splits, data-quality checks, calibration, bar rule, ablations (Parts 2, 3)], [Core],
    [7], [NLP], [Complaint reading with rules and Claude; leakage filter; paraphrase bank (Parts 2, 3, 4)], [Supporting],
    [8], [Image recognition], [Meter-photo reading with plausibility checks (Part 4)], [Supporting],
    [9], [Facial recognition (bias auditing)], [Errors by circuit, part and writer voice (Parts 3, 4)], [Supporting],
    [10], [Autonomous transportation], [Human in the loop: the tool recommends, the technician acts (Part 4)], [Supporting],
    [11], [Robotics], [Instrument interface with SCPI back end limited to 24 V (Part 1)], [Stretch],
    [12], [Cybersecurity], [Injection defense in three layers; red-team suite (Part 4)], [Core],
    [13], [Ethics and governance], [Regulatory constraints as requirements; ethics by design (Parts 1, 4)], [Core],
  ),
  caption: [Course topics and where this document uses them.],
)

