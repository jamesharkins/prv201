#import "base.typ": *
#show: setup.with(title: "Differential - M1 Problem statement", short: "M1 · Problem statement")

#title-block(
  title: [Differential: simulation-grounded AI diagnosis for analog audio electronics],
  subtitle: "Milestone 1 · Problem statement",
  meta: ("PRV 201 Frontiers of Technology (AI)", "Track A: Build", "Stevens Institute of Technology", "September 2026"),
)
*Executive summary.* Analog audio equipment (tube preamplifiers, studio consoles, stand-alone studio processors and vintage hi-fi) is kept running by a small pool of bench technicians. Finding the failed part is a separately billed step that depends on experience: the specialist shops we sampled charge \$125 to \$150 just to evaluate a unit \[1, 2, 3\]. Differential assists a qualified technician. For a circuit it has a model of (@fig:concept), it simulates every plausible single-part fault under realistic part tolerances, keeps a probability for every suspect, recommends the measurement expected to rule out the most suspects per unit of effort, and explains each step in plain words. A language model reads the complaint and explains, but never produces a reading; safety rules and a check that every number traces to a measurement run in code. We will test four claims against targets locked before the full evaluation (@tab:targets): Differential names the failed part, or its group of indistinguishable faults, first in at least 93% of 1,000 simulated test units; it needs at most 0.35 times the measurement effort of a scripted troubleshooting chart; it is more accurate than a language model given the same bench; and it stays calibrated, flags faults outside its model and never issues an unsafe step. Scope: single static faults in preamplifier and line-level circuits, tested in simulation, on a tolerance stress set and on a low-voltage hardware board.

#figure(
  image("/results/figures/concept.svg", width: 88%),
  caption: [Differential in one picture. Offline, a circuit model and its fault catalog are simulated under part tolerances with SPICE (standard circuit-simulation software), and the results are learned as fault signatures. Online, a Bayesian loop picks each measurement while the language model (LLM) only reads and explains. Safety rules and the numeric grounding check run in code beneath both. Terms are explained in Appendix C.],
) <fig:concept>

#part(1, "Problem, stakeholders and industry context", "MEMBER_1")

*Finding the fault is a separately billed step.* Three specialist shops we sampled (studio, vintage hi-fi and tube amplifier) charge \$125 to \$150 for a bench evaluation; one fee covers the first hour of work and another is credited to the repair \[1, 2, 3\]. A shop servicing studio outboard gear bills its one-hour minimum even when no fault is found \[4\], and vintage-audio repair queues stretch to months or years as specialists reach retirement age \[5\]. These are single-shop examples; the share of a repair bill that diagnosis takes is not published, so we will ask working technicians.

*A small workforce, and trainees who need support.* The closest U.S. occupation, audiovisual equipment installers and repairers, employed 24,720 people in May 2023 \[6\], with faster-than-average growth projected \[7\]. The broader group of electrical and electronics installers and repairers (about 117,700 jobs in 2025) is mostly industrial, avionics and vehicle work \[8\]; it is the adjacent market for the same method. Trade reporting says analog circuitry is not taught at two-year colleges \[9\]. In a field study of 5,179 customer-support agents, an AI assistant raised productivity by 14% on average and by 34% for novice and low-skilled workers \[10\], so trainees and newly qualified technicians are the users likely to gain most. The equipment is old and wears in known ways: electrolytic capacitors dry out, losing capacitance and gaining resistance \[11\], and tube supply has been strained since early 2022 \[12\], so replacing good parts on a guess wastes scarce parts.

*Where current AI stands.* Maintenance AI serves instrumented fleets and common devices: PTC's ServiceMax AI grounds answers in each asset's documented history \[13\], Microsoft's field-service Copilot searches product manuals \[14\], Siemens pairs repair guidance with predictive maintenance \[15\], IBM's Maximo assistant plans multi-step maintenance tasks \[16\], and iFixit's FixBot draws on 125,000 repair guides \[17\]. None models the circuit of a unit without sensors (@tab:stakeholders lists who else is affected). Language models are now strong at textbook circuit analysis: the top model on the September 2026 Razavi-Bench scored 95.50% \[18\]. A unit on the bench is a different problem: parts sit anywhere within tolerance, different faults can give the same readings, measurements cost effort, and some points carry lethal voltage. One system reached 97.59% on undergraduate circuit problems only after adding a simulation loop that flags mismatches \[19\]; Differential is built around that kind of check.

#figure(
  table(
    columns: (1.15fr, 1.35fr, 1.45fr, 1.1fr),
    [Stakeholder], [Needs], [What Differential changes], [Main risk],
    [Bench technician (primary user)], [Fewer blind measurements, a clear next step, safety near high voltage], [Ranked suspects; next measurement with expected readings and a reason], [Over-trust; high-voltage exposure],
    [Trainee or newly qualified technician], [Supervised practice on real faults], [Each step explained in physical terms], [Deskilling if answers replace reasoning],
    [Shop owner (buyer)], [Throughput, defensible quotes], [Shorter diagnosis; ticket with an evidence trail], [Liability for wrong advice],
    [Equipment owner], [Cost, turnaround, honesty], [The evidence trail explains the bill], [Privacy of job records],
    [Manufacturers], [Control of documentation], [Uses schematics the shop already holds], [Misuse of service documents],
    [Repair advocates, training programs], [Access to repair skills], [A tutor that explains its reasoning], [Unequal access if the tool is costly],
    [LLM provider], [Clear data terms], [Receives complaints and photos in live mode only], [Data exposure],
  ),
  caption: [Stakeholders. The technician decides and acts; Differential recommends. Hobbyist owners are deliberately not served (Part 1 decision).],
) <tab:stakeholders>

#decision("The primary user is a qualified bench technician")[
*Options:* a consumer self-repair assistant, or a professional bench tool. *Choice:* professional. Diagnosis means testing a powered, open chassis. Taking OSHA's electrical rules as our benchmark, live parts are normally de-energised before work, but testing that can only be done energised is an accepted exception, and only qualified persons may work on parts that have not been de-energised \[20\] or test circuits \[21\]. Our worst-case audit of the simulations found that 6 of the channel strip's 23 test points can exceed 50 V: 4 in normal operation and 2 only under a fault (Part 4). *Consequence:* the interface assumes meter and oscilloscope skills, mains-side work is refused, and the tool is not offered to consumers.
]

#part(2, "How diagnosis is done today, and the data landscape", "MEMBER_2")

*Today's practice.* A technician confirms the complaint, looks for burnt or bulging parts, and checks the supply voltages. A test tone is then followed through the circuit stage by stage, often halving the search each time ("half-splitting"). Voltages at marked points are compared with the service manual's chart or with the unit's healthy second channel, tubes are swapped, and finally a suspect part is unsoldered and tested on its own. What varies is judgement about which reading is really "off", since every part sits somewhere within its tolerance. When judgement runs out, a common fallback is replacing every electrolytic capacitor ("recapping"): sometimes justified by age, sometimes a substitute for diagnosis.

*The information is uneven.* Service manuals with schematics and voltage charts exist for many classic models, but units are often modified or arrive without documents. U.S. state repair laws now require manufacturers to supply documentation, in New York since 28 December 2023 \[22\] and Texas since 1 September 2026 \[23\], but only for products with digital electronics, and in New York only those first sold on or after 1 July 2023 \[24\]. The EU directive's obligation to repair covers only product groups listed in its Annex II, such as washing machines and displays \[25, 26\]. Vintage analog gear falls outside all of them.

*What Differential needs from a unit.* A circuit model: the netlist (the list of parts and how they connect), a map from test-point names to physical locations, and the operating conditions. For documented gear the model comes from the service-manual schematic, and M2 will time one transcription. Units modified away from their schematic are what the "no single fault fits" outcome is for; units with no schematic are out of scope.

*Labelled fault data is scarce, so we simulate it.* No public dataset pairs bench readings with confirmed failed parts (@tab:data). The analog-test literature answered this with simulated fault dictionaries \[27\] and showed that some faults cannot be told apart at the available test points; such faults form ambiguity groups \[28\]. Later work applied machine learning to analog fault diagnosis \[29, 30\] and found that normal tolerance variation hides drift faults \[31\]. We follow that path. Five original reference blocks and a composite channel strip (59 parts, 250 catalog faults) were simulated in ngspice under every catalog fault with datasheet tolerances: 253,000 simulated units with 0 convergence failures. Our hand calculations agree with every simulated bias point and gain (22 of 22 checks). The simulations also show why a complaint alone is weak evidence: on the channel strip, a hum complaint fits 25 faults and low output fits 21. 120 of the 250 faults produce no symptom in most units; such units never reach a bench, so the test set leaves those faults out (Part 3).

#figure(
  table(
    columns: (1.05fr, 0.95fr, 1.2fr, 1.4fr),
    [Data source], [Fault labels], [Coverage], [Bias or gap],
    [Shop repair logs], [Sparse, informal], [Common faults on popular models], [Unstructured; customer privacy],
    [Forum threads], [Unverified], [Anecdotal], [Folklore, e.g. blaming capacitors first],
    [Service manuals], [None (healthy values only)], [One model at a time], [No fault behaviour; availability varies],
    [Circuit simulation], [Exact, by construction], [Every catalog fault and tolerance draw], [Gap to real parts; single faults only],
    [Low-voltage fault board], [Exact, few], [Faults we insert by hand], [Small; validation only (T7)],
  ),
  caption: [Where labelled diagnostic data could come from. Simulation is the only source with exact labels and full coverage; its weakness, the gap to real hardware, is tested by the stress set (T6) and the fault board (T7).],
) <tab:data>

#decision("Original generic circuits instead of commercial schematics")[
*Options:* model a commercial product from its service manual, or design original circuits with the same topologies. *Choice:* original circuits: a supply with a zener regulator and a 250 V tube supply, a 12AX7 tube stage, a passive bass-and-treble (Baxandall) control, an op-amp stage and a two-transistor line driver. *Why:* no copying of service documents, full control of the ground truth, and the standard topologies of preamplifier and line-level gear. *Consequence:* transfer to real units must be shown: first on a low-voltage fault board of the driver block (T7), then by transcribing one documented product in M2.
]

#part(3, "Objectives and measurable success criteria", "MEMBER_3")

*Objectives.* (O1) Name the failed part or its ambiguity group accurately. (O2) Use less measurement effort than scripted troubleshooting. (O3) Be honest: calibrated probabilities, visible ambiguity groups, and an explicit "no single fault fits" outcome. (O4) Be safe: no unsafe step and no invented reading. (O5) Be practical: fast, cheap, and usable with plain-language complaints and meter photos.

*Effort units.* Effort is counted in units: 1 for a DC reading, 3 for an oscilloscope measurement, 2 extra at a point that is high voltage in normal operation, and 10 for unsoldering a part, within a budget of 40 per diagnosis. The weights are estimates, not timings: every effort comparison is repeated with the scope and lift weights halved and doubled, and M2 will time them on the fault board.

#[
#show figure: set block(breakable: true)
#figure(
  table(
    columns: (0.32fr, 0.3fr, 2.2fr, 0.95fr, 0.95fr),
    table.header([ID], [Obj.], [Target in plain words], [System], [Bar]),
    [T1#super[★]], [O1], [Names the failed part (or its indistinguishable group) first], [Full system], [≥ 93%],
    [T2], [O1], [Same, on the largest circuit], [Full system], [≥ 93%],
    [T3], [O1], [The true group is on the three-item short list], [Full system], [≥ 99%],
    [T4#super[★]], [O1], [More accurate than scripted or random probing on the largest circuit], [Full system], [≥ +12 points each],
    [T5#super[★]], [O1], [More accurate than an LLM given the same information and readings _(requires api key)_], [Full system vs LLM alone], [≥ +10 points],
    [T6], [O1], [Stays accurate when real parts are sloppier than the datasheets], [Full system], [≤ 10 points],
    [T7], [O1], [Works on real hardware, not just in simulation _(requires hardware)_], [Full system], [≥ 80%],
    [T8#super[★]], [O2], [Needs much less probing than a textbook troubleshooting chart], [Engine vs fixed order], [≤ 0.35×],
    [T9], [O2], [Needs less probing than a technician's half-split strategy], [Engine vs half-split], [≤ 0.40×],
    [T10], [O2], [Beats unguided probing clearly], [Engine vs random], [≤ 0.35×],
    [T11], [O2], [Reading the complaint saves measurements], [Full system vs engine], [≤ 0.75×],
    [T12#super[★]], [O3], [When it says 80% sure, it is right about 80% of the time, at every step], [Full system], [≤ 0.03],
    [T13], [O3], [Recognises units with two faults or a modification, and rarely points only at healthy parts when it does not], [Full system], [AUROC ≥ 0.62; ≥ 38% flagged; ≤ 21% misleading],
    [T14], [O3], [Evidence overrides a capacitor-heavy hunch], [Engine], [≥ −2 points],
    [T15#super[★]], [O4], [Every risky step comes with the right precautions, by construction], [Agent], [100%],
    [T16], [O4], [Cannot be talked into unsafe advice _(requires team suite)_], [Agent (offline and live)], [0 unsafe],
    [T17#super[★]], [O4], [Never invents a reading], [Agent], [0%],
    [T18], [O5], [Reads plain-language complaints correctly _(requires api key)_], [Claude / offline rules], [≥ 0.90 (Claude); ≥ 0.80 (rules)],
    [T19], [O5], [Reads a meter photo correctly, including units _(requires api key)_], [Claude vision / offline reader], [≥ 95% (Claude); ≥ 90% (offline)],
    [T20], [O5], [Fast enough not to slow the bench], [Engine], [≤ 0.5 s],
    [T21], [O5], [Cheap to run _(requires api key)_], [Live agent], [≤ \$0.10],
  ),
  caption: [Success criteria, locked (git tag `targets-locked`) before the full evaluation and reported as met or missed. ★ = primary. A diagnosis is correct when it names the true fault's ambiguity group. Effort ratios count only if top-1 accuracy is no more than 2 points lower. A target is met when its point estimate meets the bar; each is reported with a bootstrap 95% confidence interval. "Requires" marks targets that need an API key, a red-team suite written by the team, or the hardware board; they stay pending until then.],
) <tab:targets>
]

*How it will be measured.* The test set holds 1,000 single-fault units (500 on the channel strip, 100 per block). Each fault is drawn uniformly from the faults that produce a symptom in at least half of simulated units, a unit that shows no symptom is redrawn, and seeds are disjoint from training. Each unit gets a complaint written from templates in one of three voices (owner, musician, technician); a check rejects any complaint that names a part, and a separately written bank of paraphrases tests the complaint reader. Further sets: 100 double-fault or modified units, and 300 stress units with tolerances 1.5 times wider than the models assume. Each unit is diagnosed by random probing, a scripted fixed-order chart, scripted half-split tracing, the engine with each of two likelihood models (complaint ignored) and the full system. On a stratified 150-unit subset, a language model works alone, and again with our simulator as a tool; it sees what a technician sees (complaint, parts list, voltage chart with tolerances, fault list, the same readings on request, the same budget), with a pinned model and cached responses.

*Two pilots shaped the bars.* Neither touched the test set. The first, on held-out training units, named the fault group in 99% of channel-strip units but was optimistic: its "no single fault fits" outcome was not yet calibrated and never fired. A second pilot matched the test protocol (200 symptomatic channel-strip units and 60 per block, with complaints, on validation units) and exposed an engine bug, now fixed: measurement choice ignored that outcome, so some sessions stopped early. After the fix, the full system named the fault group in 95.5% of channel-strip units at a mean effort of 4.2, against 78.5% at 22.8 for the fixed-order chart, 83.0% at 19.7 for half-split tracing and 79.5% at 23.5 for random probing; with tolerances 1.5 times wider it reached 90.0%. Over all 500 pilot units, 24 of its 25 misses were false "no single fault fits" calls, the price of flagging 44% of double-fault and modified units. Each bar the pilot can estimate sits 1.5 standard errors on the cautious side of its pilot value, rounded (validation units also tuned the ambiguity groups, so the pilot is mildly optimistic); the others were fixed before any run.

*Scope and non-goals.* In scope: single static faults (opens, shorts, drift, wear) in the five blocks and the channel strip, all preamplifier and line-level circuits. Out of scope: power stages; intermittent, noise and mechanical faults; cascades (flagged by "no single fault fits", not diagnosed); mains-side work; units without a schematic; autonomous probing.

#decision("Score by ambiguity group and weighted effort")[
*Options:* per-part accuracy with a count of measurements, or accuracy by ambiguity group with weighted effort. *Choice:* the latter. Some faults give identical readings at every test point; scoring per part would reward lucky guesses and punish honest ties, and counting measurements would treat unsoldering a part like touching a probe. *Consequence:* every accuracy target is group aware, and every effort target uses the weighted units.
]

#part(4, "Preliminary AI approach, risks and ethics", "MEMBER_4")

*Why a hybrid.* Language models sometimes guess when uncertain, which Kalai et al. attribute to training and evaluation that reward guessing over admitting uncertainty \[32\]. A diagnosis needs readings consistent with the circuit and probabilities that mean what they say. So simulation supplies the physics, and Bayesian inference keeps a probability for every suspect and updates it after each reading. The next measurement is the one expected to rule out the most suspects per unit of effort, the logic of sequential fault diagnosis \[33\] and of measurement selection in analog testing \[27\]: the best next question in a game of twenty questions. The LLM reads complaints and meter photos and explains each step. @tab:families compares the options.

#figure(
  table(
    columns: (1.2fr, 1.2fr, 1.45fr, 1.0fr),
    [Approach], [Strength], [Weakness], [Role here],
    [LLM alone], [Language, broad knowledge], [Unchecked numbers; uncalibrated], [Baseline; language layer],
    [LLM with a simulator tool], [Checks against simulation], [No tolerance model or plan], [Stronger baseline],
    [Search over service manuals], [Uses documented fixes], [Needs fault histories; ignores readings], [Not used],
    [Chart or half-split script], [Transparent, safe], [Fixed; ignores complaint and odds], [Scripted baselines],
    [Consistency-based \[34\]], [Multiple faults], [Needs exact models], [Informs "no single fault fits"],
    [Classifier on simulated data], [Accurate, fast], [Weak off its training data], [Comparison engine],
    [Gaussian-mixture likelihoods], [Any subset of readings], [Density in about 50 dimensions], [Core engine],
  ),
  caption: [Candidate approaches. The comparison engine's boosted-tree scores, trained on randomly masked readings and calibrated, act as likelihoods once divided by class frequencies; the core engine fits one to three Gaussian components per fault.],
) <tab:families>

*Autonomy.* By analogy with the SAE levels of driving automation \[35\], Differential works at level L2 of five levels of diagnostic autonomy: it recommends each step, and the technician measures, confirms and decides (Appendix D).

*Risks and first-pass ethics.* _Safety:_ a unit on the bench is faulted, and a fault can put high voltage where there is normally none. Our audit of every simulated unit found that TP8, near 1.4 V in normal operation, reaches 147 V when its cathode resistor opens. Every step at such a point carries hands-off measurement, isolation and discharge instructions, unsoldering is locked until the technician reports a discharged filter capacitor, and mains-side work is refused. A step is unsafe if it bypasses a protection, directs hands-in work on a live or undischarged circuit, or omits these instructions (T15, T16). _Over-trust and deskilling:_ runner-up suspects and the reason for each step are always shown, and every ticket needs the technician's sign-off. _Bias:_ old electrolytics do fail often, but folklore blames them first; T14 tests that readings override a capacitor-heavy prior. Errors will be broken down by circuit, part kind and fault type, following the disaggregated audit of commercial gender classifiers \[36\], and complaint reading by writer voice. _Security:_ prompt injection ranks first in the OWASP Top 10 for LLM applications \[37\], and LLM-integrated applications blur data and instructions \[38\]. Service notes, complaints and photo text are therefore treated as data, the model's tools are read-only, and it controls no instrument. _Privacy:_ offline mode sends nothing out; live mode sends complaint text and meter photos to the model provider after removing names and serial numbers. _Liability and regulation:_ the technician decides. The revised EU Product Liability Directive treats software as a product only for products placed on the market after 9 December 2026, and it does not compensate damage to property used only for professional purposes \[39\]. Under the EU AI Act, a system is high-risk as a safety component of a product under Annex I legislation or when it falls in an Annex III area. Equipment diagnostics is neither, but Annex III covers AI that evaluates workers' performance \[40\], so our intended use excludes grading technicians. The duty to tell users they are talking to an AI has applied since 2 August 2026 \[41\]. In the U.S. no federal statute yet assigns AI liability: the proposed AI LEAD Act would treat AI systems as products \[42\], while the proposed RISE Act would shield developers when a learned professional uses the tool, if a model card and specification are published \[43\]; we will publish both. @tab:risks maps each control to a NIST AI Risk Management Framework function \[44\].

#[
#show figure: set block(breakable: true)
#figure(
  table(
    columns: (1.35fr, 0.38fr, 2.2fr, 0.62fr, 0.62fr),
    table.header([Risk], [L/I], [Control], [Measured by], [NIST RMF]),
    [Unsafe step near high voltage], [M/H], [Worst-case voltage map; hands-off and discharge steps; unsoldering lock], [T15, T16], [Manage],
    [Invented or misread reading], [M/H], [Grounding check; the technician confirms photo readings], [T17, T19], [Measure],
    [Confident wrong diagnosis], [M/H], [Calibration; runner-ups shown; "no single fault fits"], [T12, T13], [Measure],
    [Simulation-to-reality gap], [H/H], [Tolerance stress set; hardware fault board], [T6, T7], [Map],
    [No circuit model for the unit], [H/H], [Documented units only; M2 times one transcription], [M2], [Map],
    [Over-trust and deskilling], [M/M], [Reasons shown; sign-off; technician study planned], [M2], [Govern],
    [Prompt injection], [M/H], [Retrieved text treated as data; read-only tools], [T15, T16], [Manage],
    [Privacy (live mode, logs)], [M/M], [Offline default; redaction; no per-technician analytics], [M2], [Govern],
    [Model change], [M/M], [Model pinned; T15-T19 re-run on any change], [T15-T19], [Manage],
  ),
  caption: [Initial risk register. L/I = likelihood and impact before controls (H/M/L). "M2" marks a design control whose check is defined in M2.],
) <tab:risks>
]

#decision("Safety rules live in code, not only in the prompt")[
*Options:* instruct the model to be safe, or enforce safety deterministically outside it. *Choice:* code is the authority; the prompt repeats the rules but cannot override them, whereas injected text or user pressure can talk a model out of an instruction. *Consequence:* warnings, refusals and the lock behave identically in every mode, and T15 can test them exhaustively.
]

// END-PARTS

#heading(level: 1, numbering: none)[References]
#ref-entry(1)[“Audio Repair Los Angeles · Pro Studio Gear Service,” _The Studio Doctors_, n.d. [Online]. Available: #link("https://thestudiodoctors.com/audio-repair-los-angeles.html")[https://thestudiodoctors.com/audio-repair-los-angeles.html] (accessed Sep. 28, 2026).]
#ref-entry(2)[“Expert Vintage Stereo Repair,” _Archer High Fidelity_, n.d. [Online]. Available: #link("https://archerhifi.com/repair-and-service/vintage-stereo-repair/")[https://archerhifi.com/repair-and-service/vintage-stereo-repair/] (accessed Sep. 28, 2026).]
#ref-entry(3)[“Services & Rates — CW Guitar Audio - Amp Repair and Mods - Columbus Ohio,” _CW Guitar Audio_, n.d. [Online]. Available: #link("https://www.cwguitaraudio.com/services")[https://www.cwguitaraudio.com/services] (accessed Sep. 28, 2026).]
#ref-entry(4)[“Electronic Service Rates and Policies,” _British Audio_, n.d. [Online]. Available: #link("https://britishaudio.com/pages/electronic-repair-rates")[https://britishaudio.com/pages/electronic-repair-rates] (accessed Sep. 28, 2026).]
#ref-entry(5)[“The Vintage Audio Revival Is Running Out of People Who Can Keep It Alive and a Spare Parts Problem Is Making It Worse,” _Headphonesty_, Aug. 2026. [Online]. Available: #link("https://www.headphonesty.com/2026/08/vintage-audio-revival-running-out-people/")[https://www.headphonesty.com/2026/08/vintage-audio-revival-running-out-people/] (accessed Sep. 28, 2026).]
#ref-entry(6)[U.S. Bureau of Labor Statistics, “Occupational Employment and Wages, May 2023: 49-2097 Audiovisual Equipment Installers and Repairers,” _Occupational Employment and Wage Statistics (OEWS)_, May 2023. [Online]. Available: #link("https://www.bls.gov/oes/2023/may/oes492097.htm")[https://www.bls.gov/oes/2023/may/oes492097.htm] (accessed Sep. 28, 2026).]
#ref-entry(7)[National Center for O\*NET Development, “Bright Outlook Occupation: 49-2097.00 - Audiovisual Equipment Installers and Repairers,” _O\*NET OnLine_, n.d. [Online]. Available: #link("https://www.onetonline.org/help/bright/49-2097.00")[https://www.onetonline.org/help/bright/49-2097.00] (accessed Sep. 28, 2026).]
#ref-entry(8)[U.S. Bureau of Labor Statistics, “Electrical and Electronics Installers and Repairers,” _Occupational Outlook Handbook_, Aug. 27, 2026. [Online]. Available: #link("https://www.bls.gov/ooh/installation-maintenance-and-repair/electrical-and-electronics-installers-and-repairers.htm")[https://www.bls.gov/ooh/installation-maintenance-and-repair/electrical-and-electronics-installers-and-repairers.htm] (accessed Sep. 28, 2026).]
#ref-entry(9)[“Re-Tales \#13: Getting your hi-fi fix(ed),” _Stereophile_, n.d. [Online]. Available: #link("https://www.stereophile.com/content/re-tales-13-getting-your-hi-fi-fixed")[https://www.stereophile.com/content/re-tales-13-getting-your-hi-fi-fixed] (accessed Sep. 28, 2026).]
#ref-entry(10)[E. Brynjolfsson, D. Li, and L. R. Raymond, “Generative AI at Work,” _National Bureau of Economic Research, Working Paper 31161_, 2023. Published in The Quarterly Journal of Economics, vol. 140, no. 2, 2025. [Online]. Available: #link("https://www.nber.org/papers/w31161")[https://www.nber.org/papers/w31161] (accessed Sep. 28, 2026).]
#ref-entry(11)[University of Siegen, Institute of Automatic Control, “Power Electronics Devices and Components, Lecture 08: Capacitors (course slides),” _Course repository IAS-Uni-Siegen/PEDC\_course_, 2026. [Online]. Available: #link("https://github.com/IAS-Uni-Siegen/PEDC_course")[https://github.com/IAS-Uni-Siegen/PEDC\_course].]
#ref-entry(12)[“An Ongoing Tube Shortage Is Pushing High-End Audio to Its Breaking Point, Warns Industry Insider,” _Headphonesty_, Sep. 2025. [Online]. Available: #link("https://www.headphonesty.com/2025/09/ongoing-tube-shortage-breaking-high-end-audio/")[https://www.headphonesty.com/2025/09/ongoing-tube-shortage-breaking-high-end-audio/] (accessed Sep. 28, 2026).]
#ref-entry(13)[PTC Inc., “PTC Launches ServiceMax AI, a Generative AI-Powered Field Service Assistant,” Press release, Feb. 12, 2025. [Online]. Available: #link("https://www.ptc.com/en/news/2025/ptc-launches-servicemax-ai")[https://www.ptc.com/en/news/2025/ptc-launches-servicemax-ai] (accessed Sep. 28, 2026).]
#ref-entry(14)[Microsoft, “Field Service Management Software | Microsoft Dynamics 365,” n.d. [Online]. Available: #link("https://www.microsoft.com/en-us/dynamics-365/products/field-service")[https://www.microsoft.com/en-us/dynamics-365/products/field-service] (accessed Sep. 28, 2026).]
#ref-entry(15)[Siemens AG, “Siemens expands Industrial Copilot with New generative AI-powered Maintenance Offering,” Press release, Mar. 24, 2025. [Online]. Available: #link("https://press.siemens.com/global/en/pressrelease/siemens-expands-industrial-copilot-new-generative-ai-powered-maintenance-offering")[https://press.siemens.com/global/en/pressrelease/siemens-expands-industrial-copilot-new-generative-ai-powered-maintenance-offering] (accessed Sep. 28, 2026).]
#ref-entry(16)[IBM, “Introducing Maximo Application Suite 9.2: AI built for asset management that keeps operations running,” Press release, Jun. 25, 2026. [Online]. Available: #link("https://www.ibm.com/new/announcements/introducing-maximo-application-suite-9-2")[https://www.ibm.com/new/announcements/introducing-maximo-application-suite-9-2] (accessed Sep. 28, 2026).]
#ref-entry(17)[“iFixit launches FixBot AI repair helper, with free and paid versions,” _9to5Mac_, Dec. 9, 2025. [Online]. Available: #link("https://9to5mac.com/2025/12/09/ifixit-launches-fixbot-ai-repair-helper-with-free-and-paid-versions/")[https://9to5mac.com/2025/12/09/ifixit-launches-fixbot-ai-repair-helper-with-free-and-paid-versions/] (accessed Sep. 28, 2026).]
#ref-entry(18)[Zhishuai Zhang, “Razavi-Bench: An Expert-Curated Benchmark for Analog-Design Reasoning,” _Benchmark repository and leaderboard (GitHub Arcadia-1/razavi-bench)_, Sep. 2026. [Online]. Available: #link("https://github.com/Arcadia-1/razavi-bench")[https://github.com/Arcadia-1/razavi-bench] (accessed Sep. 28, 2026).]
#ref-entry(19)[“Enhancing Large Language Model-Based Systems for End-to-End Circuit Analysis Problem Solving,” _arXiv preprint arXiv:2512.10159_, Dec. 2025. [Online]. Available: #link("https://arxiv.org/abs/2512.10159")[https://arxiv.org/abs/2512.10159] (accessed Sep. 28, 2026).]
#ref-entry(20)[U.S. Occupational Safety and Health Administration, “29 CFR 1910.333, Selection and use of work practices,” _Code of Federal Regulations (eCFR text current in 2026)_, 2026. [Online]. Available: #link("https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.333")[https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.333].]
#ref-entry(21)[U.S. Occupational Safety and Health Administration, “29 CFR 1910.334, Use of equipment,” _Code of Federal Regulations (eCFR text current in 2026)_, 2026. [Online]. Available: #link("https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.334")[https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.334].]
#ref-entry(22)[New York State Office of the Attorney General, “Attorney General James Reminds Consumers It's Easier Than Ever to Get Electronics Repaired in New York,” Press release, Office of the New York State Attorney General, 2024. [Online]. Available: #link("https://ag.ny.gov/press-release/2024/attorney-general-james-reminds-consumers-its-easier-ever-get-electronics")[https://ag.ny.gov/press-release/2024/attorney-general-james-reminds-consumers-its-easier-ever-get-electronics] (accessed Sep. 28, 2026).]
#ref-entry(23)[Texas Legislature, “HB 2963 (2025), Tex. Bus. & Com. Code ch. 121, Diagnosis, Maintenance, and Repair of Certain Digital Electronic Equipment,” _Texas Legislature Online_, 2025. [Online]. Available: #link("https://capitol.texas.gov/tlodocs/89R/billtext/html/HB02963F.htm")[https://capitol.texas.gov/tlodocs/89R/billtext/html/HB02963F.htm] (accessed Sep. 28, 2026).]
#ref-entry(24)[New York State Legislature, “N.Y. General Business Law § 399-nn (Digital Fair Repair Act),” _New York State Senate (Laws of New York)_, Dec. 28, 2022. [Online]. Available: #link("https://www.nysenate.gov/legislation/laws/GBS/399-NN")[https://www.nysenate.gov/legislation/laws/GBS/399-NN] (accessed Sep. 28, 2026).]
#ref-entry(25)[European Parliament and Council of the European Union, “Directive (EU) 2024/1799 on common rules promoting the repair of goods,” _Official Journal of the European Union_, Jun. 13, 2024. [Online]. Available: #link("https://eur-lex.europa.eu/eli/dir/2024/1799/oj")[https://eur-lex.europa.eu/eli/dir/2024/1799/oj].]
#ref-entry(26)[European Commission, “Questions & Answers: Directive on repair of goods (obligation to repair),” Jul. 2024. [Online]. Available: #link("https://commission.europa.eu/document/download/2d443b31-dc2a-4e54-a9ec-5fbb61c895e9_en?filename=2024_07_18_QA_Right2repair_FINAL.pdf")[https://commission.europa.eu/document/download/2d443b31-dc2a-4e54-a9ec-5fbb61c895e9\_en?filename=2024\_07\_18\_QA\_Right2repair\_FINAL.pdf] (accessed Sep. 28, 2026).]
#ref-entry(27)[J. W. Bandler and A. E. Salama, “Fault diagnosis of analog circuits,” _Proceedings of the IEEE_, vol. 73, no. 8, pp. 1279–1325, Aug. 1985. doi: 10.1109/PROC.1985.13281.]
#ref-entry(28)[G. N. Stenbakken, T. M. Souders, and G. W. Stewart, “Ambiguity groups and testability,” _IEEE Transactions on Instrumentation and Measurement_, vol. 38, no. 5, pp. 941–947, Oct. 1989. doi: 10.1109/19.39034.]
#ref-entry(29)[W. He, Y. He, and B. Li, “Generative Adversarial Networks With Comprehensive Wavelet Feature for Fault Diagnosis of Analog Circuits,” _IEEE Transactions on Instrumentation and Measurement, vol. 69, no. 9, pp. 6640-6650_, Sep. 2020. doi: 10.1109/TIM.2020.2969008.]
#ref-entry(30)[T. Gao, J. Yang, and S. Jiang, “A Novel Incipient Fault Diagnosis Method for Analog Circuits Based on GMKL-SVM and Wavelet Fusion Features,” _IEEE Transactions on Instrumentation and Measurement, vol. 70, art. 9198907_, 2021. doi: 10.1109/TIM.2020.3024337.]
#ref-entry(31)[J. B. Cloete, T. Stander, and D. N. Wilke, “Parametric Circuit Fault Diagnosis Through Oscillation-Based Testing in Analogue Circuits: Statistical and Deep Learning Approaches,” _IEEE Access, vol. 10, pp. 15671-15680_, 2022. doi: 10.1109/ACCESS.2022.3149324.]
#ref-entry(32)[A. T. Kalai, O. Nachum, S. S. Vempala, and E. Zhang, “Why Language Models Hallucinate,” _arXiv preprint arXiv:2509.04664_, Sep. 2025. [Online]. Available: #link("https://arxiv.org/abs/2509.04664")[https://arxiv.org/abs/2509.04664] (accessed Sep. 28, 2026).]
#ref-entry(33)[K. R. Pattipati and M. G. Alexandridis, “Application of heuristic search and information theory to sequential fault diagnosis,” _IEEE Transactions on Systems, Man, and Cybernetics_, vol. 20, no. 4, pp. 872–887, Jul. 1990. doi: 10.1109/21.105086.]
#ref-entry(34)[J. de Kleer and B. C. Williams, “Diagnosing multiple faults,” _Artificial Intelligence_, vol. 32, no. 1, pp. 97–130, Apr. 1987. doi: 10.1016/0004-3702(87)90063-4.]
#ref-entry(35)[P. Kulicki and R. Trypuz, “Ontology of driving automation systems for on-road motor vehicles (encoding the SAE J3016 levels of driving automation),” _GitHub repository kul-ai/ontology-autonomous-driving_, 2021. [Online]. Available: #link("https://github.com/kul-ai/ontology-autonomous-driving")[https://github.com/kul-ai/ontology-autonomous-driving] (accessed Sep. 28, 2026).]
#ref-entry(36)[J. Buolamwini and T. Gebru, “Gender Shades: Intersectional Accuracy Disparities in Commercial Gender Classification,” _Proceedings of the 1st Conference on Fairness, Accountability and Transparency (PMLR 81)_, pp. 77–91, 2018. [Online]. Available: #link("https://proceedings.mlr.press/v81/buolamwini18a.html")[https://proceedings.mlr.press/v81/buolamwini18a.html].]
#ref-entry(37)[OWASP GenAI Security Project, “OWASP Top 10 for LLM Applications 2026,” _OWASP Foundation (official project repository)_, Aug. 4, 2026. [Online]. Available: #link("https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/tree/main/2026/final")[https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/tree/main/2026/final] (accessed Sep. 28, 2026).]
#ref-entry(38)[K. Greshake, S. Abdelnabi, S. Mishra, C. Endres, T. Holz, and M. Fritz, “Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection,” _Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security (AISec ’23)_, 2023. doi: 10.1145/3605764.3623985.]
#ref-entry(39)[European Parliament and Council of the European Union, “Directive (EU) 2024/2853 of 23 October 2024 on liability for defective products (Product Liability Directive),” _Official Journal of the European Union, OJ L, 2024/2853_, Oct. 23, 2024. [Online]. Available: #link("https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng")[https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng] (accessed Sep. 28, 2026).]
#ref-entry(40)[European Parliament and Council of the European Union, “Regulation (EU) 2024/1689 (Artificial Intelligence Act),” _Official Journal of the European Union_, Jun. 13, 2024. [Online]. Available: #link("https://eur-lex.europa.eu/eli/reg/2024/1689/oj")[https://eur-lex.europa.eu/eli/reg/2024/1689/oj].]
#ref-entry(41)[European Commission, “Commission starts enforcing AI Act rules and new transparency requirements on 2 August (IP/26/1714),” Press release, Jul. 31, 2026. [Online]. Available: #link("https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august")[https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august] (accessed Sep. 28, 2026).]
#ref-entry(42)[U.S. Senate, “S. 2937, AI LEAD Act (Aligning Incentives for Leadership, Excellence, and Advancement in Development Act), 119th Congress (introduced September 2025),” _Office of Sen. Hawley / Congress.gov_, Sep. 29, 2025. [Online]. Available: #link("https://www.hawley.senate.gov/hawley-durbin-introduce-legislation-empowering-americans-to-bring-liability-claims-against-ai-companies/")[https://www.hawley.senate.gov/hawley-durbin-introduce-legislation-empowering-americans-to-bring-liability-claims-against-ai-companies/] (accessed Sep. 28, 2026).]
#ref-entry(43)[U.S. Senate, “S. 2081, Responsible Innovation and Safe Expertise (RISE) Act of 2025, 119th Congress,” _Congress.gov / Office of Sen. Lummis_, 2025. [Online]. Available: #link("https://www.congress.gov/bill/119th-congress/senate-bill/2081/text")[https://www.congress.gov/bill/119th-congress/senate-bill/2081/text] (accessed Sep. 28, 2026).]
#ref-entry(44)[National Institute of Standards and Technology, “AI RMF Core, Section 5 of Artificial Intelligence Risk Management Framework (AI RMF 1.0), NIST AI 100-1,” _NIST AI Resource Center_, Jan. 26, 2023. [Online]. Available: #link("https://airc.nist.gov/airmf-resources/airmf/5-sec-core/")[https://airc.nist.gov/airmf-resources/airmf/5-sec-core/] (accessed Sep. 28, 2026).]
#ref-entry(45)[European Parliament and Council of the European Union, “Regulation (EU) 2026/1744 of 8 July 2026 amending Regulations (EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230 as regards the simplification of the implementation of harmonised rules on artificial intelligence (Digital Omnibus on AI),” _Official Journal of the European Union, OJ L, 2026/1744_, Jul. 8, 2026. [Online]. Available: #link("https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng")[https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng] (accessed Sep. 28, 2026).]
#ref-entry(46)[European Commission, “Right to repair: New consumer rights for easy and attractive repairs,” Jul. 31, 2026. [Online]. Available: #link("https://commission.europa.eu/news-and-media/news/right-repair-new-consumer-rights-easy-and-attractive-repairs-2026-07-31_en")[https://commission.europa.eu/news-and-media/news/right-repair-new-consumer-rights-easy-and-attractive-repairs-2026-07-31\_en] (accessed Sep. 28, 2026).]
#ref-entry(47)[Anthropic, “Claude Sonnet 5.5 (model page),” _Claude Developer Platform documentation_, Sep. 28, 2026. [Online]. Available: #link("https://platform.claude.com/docs/en/models/sonnet-5-5/overview")[https://platform.claude.com/docs/en/models/sonnet-5-5/overview] (accessed Sep. 28, 2026).]

#heading(level: 1, numbering: none)[Appendix A · Industry watch]
#set text(size: 9pt)
- *Frontier models ace textbook analog questions (September 2026).* The top Razavi-Bench model scored 95.50%, and the benchmark now has a simulator-assisted mode \[18\]. Textbook reasoning is no longer the bottleneck; grounding, calibration and safety are what a bench tool must add, and T5 tests that head-on.
- *IBM Maximo 9.2 (June 2026)* adds an agentic assistant and an MCP server for customers' own agents \[16\]. Asset-management platforms are becoming agent hosts, a possible route for a diagnosis engine into industrial repair depots.
- *EU AI Act transparency rules apply (2 August 2026)* \[41\], while the Digital Omnibus moved the Annex III high-risk rules to 2 December 2027 \[45\]. Differential's AI disclosure is due now; high-risk duties would arise only if it were used to evaluate workers.
- *Repair rights widen for new products.* EU repair rules began to apply on 31 July 2026 \[46\] and Texas's law took effect on 1 September 2026 \[23\]. Both help newer digital products, not the vintage analog gear Differential targets.
- *Claude Sonnet 5.5 released (28 September 2026)* \[47\]. Models change quickly, so Differential pins its model, caches responses and re-runs its safety and grounding targets on any change.

#heading(level: 1, numbering: none)[Appendix B · Course coverage map]
#figure(
  table(
    columns: (0.25fr, 0.95fr, 2.6fr, 0.55fr),
    [Wk], [Topic], [Where this document uses it], [Depth],
    [2], [AI/ML algorithms], [Bayesian inference, Gaussian mixtures, boosted trees, information-driven measurement choice (Part 4)], [Core],
    [3], [Python], [Simulation, engine and evaluation code behind every number (Parts 2, 3)], [Core],
    [4], [Large language models], [Why LLMs guess; LLM-alone and LLM-with-simulator baselines (Parts 1, 3, 4; T5)], [Core],
    [5], [LLM-enhanced agents], [Tool-using assistant with read-only tools that reads complaints and explains (Part 4)], [Supporting],
    [6], [Building ML systems], [Pilots, locked targets, confidence intervals, stress set (Part 3)], [Core],
    [7], [NLP], [Complaint reading in three voices; held-out paraphrases; label-leakage check (Part 3; T18)], [Supporting],
    [8], [Image recognition], [Meter-photo reading scored on value, unit and mode (T19)], [Supporting],
    [9], [Facial recognition (bias auditing)], [Disaggregated error audit; complaint reading by writer voice; folklore prior (Part 4; T14, T18)], [Supporting],
    [10], [Autonomous transportation], [Levels of diagnostic autonomy by analogy to driving automation (Part 4)], [Supporting],
    [11], [Robotics], [Sense-decide-act loop with the technician as actuator; instrument interface on the 24 V board (Part 4)], [Stretch],
    [12], [Cybersecurity], [Prompt injection, untrusted data, read-only tools, red-team suite (Part 4; T16)], [Core],
    [13], [Ethics and governance], [Worst-case safety audit, OSHA benchmark, EU AI Act and PLD, NIST mapping (Parts 1, 4)], [Core],
  ),
  caption: [Course topics and where this document uses them.],
)

#heading(level: 1, numbering: none)[Appendix C · Terms in plain words]
#table(
  columns: (0.9fr, 3.1fr),
  [Term], [Meaning],
  [Ambiguity group], [Faults that give the same readings at every test point within tolerance; a diagnosis names the group and an out-of-circuit test separates its members.],
  [AUROC], [How well a score separates two kinds of cases: 1 is perfect, 0.5 is a coin flip.],
  [B+], [The high-voltage supply rail of a tube circuit (about 250 V here).],
  [Bayesian belief], [A probability for every suspect, updated after each reading.],
  [Calibration error], [The gap between stated confidence and how often the system is right.],
  [DMM, oscilloscope], [Digital multimeter; an instrument that displays signals over time.],
  [Expected information gain], [How much a measurement is expected to narrow the suspects.],
  [Micro-F1], [The share of symptoms read correctly from complaints, counting misses and false alarms.],
  [Netlist, SPICE], [A text list of a circuit's parts and connections; standard software that simulates it.],
  [Recapping], [Replacing every electrolytic capacitor in a unit.],
  [Tolerance], [How far a real part may differ from the value printed on it.],
  [12AX7, Baxandall], [A common preamplifier vacuum tube; a standard bass-and-treble tone circuit.],
)

#heading(level: 1, numbering: none)[Appendix D · Levels of diagnostic autonomy]
#table(
  columns: (0.3fr, 2.2fr, 1.3fr),
  [Level], [Who does what], [Differential],
  [L0], [The technician works from the manual alone.], [],
  [L1], [The tool displays readings and probabilities.], [],
  [L2], [The tool recommends each step; the technician measures, confirms every reading and decides.], [This build],
  [L3], [The tool takes readings through instruments with the technician's approval.], [Only on the 24 V fault board],
  [L4], [The tool probes and concludes on its own.], [Non-goal],
)

