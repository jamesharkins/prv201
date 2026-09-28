#import "base.typ": *
#show: setup.with(title: "Differential - M1 Problem statement", short: "M1 · Problem statement")

#title-block(
  title: [Differential: simulation-grounded AI diagnosis for analog audio electronics],
  subtitle: "Milestone 1 · Problem statement",
  meta: ("PRV 201 Frontiers of Technology (AI)", "Track A: Build", "Stevens Institute of Technology", "September 2026"),
)

*Executive summary.* Analog audio equipment (tube preamplifiers, studio consoles, vintage hi-fi and outboard gear) is kept running by a small pool of bench technicians, and most of what a repair costs is diagnosis: finding the one failed part among dozens. General-purpose language models give fluent but ungrounded advice, such as "just recap it", because they pattern-match forum folklore instead of reasoning about the circuit in front of them. Differential grounds a language-model agent in circuit physics. It simulates the circuit under every plausible single-component fault with realistic tolerances, keeps a Bayesian belief over those faults, recommends the measurement expected to be most informative per unit of effort, and explains each step in plain language, with safety rules enforced in code rather than in a prompt. Our claim to test: this hybrid diagnoses more accurately and with less measurement effort than a language model on its own, a textbook fixed-order procedure and random probing, while staying calibrated about its uncertainty, recognising faults outside its model, and never giving unsafe instructions.

#figure(
  image("/results/figures/concept.svg", width: 100%),
  caption: [Differential in one picture. Offline, circuit simulation turns a fault catalog into learned physics; online, a Bayesian loop chooses each measurement while the language model handles only language. Safety rules and grounding checks sit in code beneath both.],
) <fig:concept>

#part(1, "Problem, stakeholders and industry context", "MEMBER_1")

*Diagnosis is the expensive step.* Repair shops sell diagnosis as a product in its own right: studio, hi-fi and tube-amplifier specialists charge \$125 to \$150 simply to put a unit on the bench \[1, 2, 3\], and one outboard-gear shop bills its one-hour minimum even when no fault is found \[4\]. Queues of months are reported as veteran technicians retire \[5\]. Every hour saved at the bench therefore shortens both the bill and the wait.

*A small, flat workforce with knowledge at risk.* The U.S. Bureau of Labor Statistics counts about 117,700 electrical and electronics installers and repairers in 2025, projected to grow 2% over 2025-35, below the all-occupation average, with most of the 8,900 annual openings coming from replacing workers who leave or retire \[6, 7\]. Audio bench technicians are not counted separately; trade reporting describes analog circuitry no longer being taught at two-year colleges \[8\]. When assistance tools were studied in customer support, they raised productivity by 14% on average and by 34% for novice workers \[9\], which suggests the payoff here is in helping less experienced technicians inherit expert practice.

*The installed base keeps growing.* U.S. vinyl revenue grew for a 19th straight year in 2025 \[10\] and rose another 17.7% in the first half of 2026 \[11\], feeding a stock of turntables, phono stages and amplifiers that eventually need repair. Tube supply has been under strain since 2022 \[12\], so a wrong guess that swaps good parts costs more than it used to.

*Where current AI falls short.* The maintenance-AI products launched in 2025-26, from Siemens' maintenance copilot \[13\] and PTC's ServiceMax AI \[14\] to IBM's agentic Maximo assistant \[15\] and iFixit's FixBot \[16\], retrieve documented knowledge for instrumented fleets or common consumer devices. None reasons at component level about an undocumented, sensor-less preamplifier. Language models alone are unreliable at exactly that reasoning: GPT-4o answered 48.04% of 510 analog-circuit questions correctly \[17\], and models averaged 19.48-46.78% on EEE-Bench \[18\], while one study raised accuracy to 97.59% by checking answers against simulation \[19\]. Grounding in simulation is the missing piece, and it is what Differential adds.

#figure(
  table(
    columns: (1.05fr, 1.35fr, 1.5fr, 1.1fr),
    [Stakeholder], [Needs], [What Differential changes], [Main risk],
    [Bench technician (primary user)], [Fewer blind measurements, a clear next step, safety near high voltage], [Ranked fault hypotheses; next-best measurement with expected readings and a reason], [Over-trust; exposure to live high voltage],
    [Shop owner], [Throughput, defensible quotes], [Shorter diagnosis; repair ticket with an evidence trail], [Liability for wrong advice],
    [Equipment owner (studio, collector)], [Cost, turnaround, honesty], [The evidence trail explains the bill], [Privacy of job records],
    [Trainee technician], [Supervised learning on real faults], [Every step is explained in physical terms], [Deskilling if answers replace reasoning],
    [Manufacturers, right-to-repair bodies], [Safe repair, documentation access], [Works from generic simulation, not proprietary data], [Schematic intellectual property],
  ),
  caption: [Stakeholders. The technician decides and acts; Differential only recommends, which is why the design keeps a qualified human in every step.],
) <tab:stakeholders>

#decision("The primary user is a qualified bench technician, not a consumer")[
*Options:* a consumer self-repair assistant, or a professional bench tool. *Choice:* professional. Tube equipment carries lethal voltages: 4 of the 23 test points on our reference channel strip sit above 50 V in normal operation, the threshold above which U.S. workplace rules require de-energising or guarding \[20\]. A consumer tool would have to refuse most useful measurements. *Consequence:* the interface assumes meter and oscilloscope literacy, and mains-side work is refused outright.
]

#part(2, "How diagnosis is done today, and the data landscape", "MEMBER_2")

*Today's practice is a fixed chart plus experience.* A technician confirms the complaint, checks the supply rails, traces the signal stage by stage with a test tone, compares DC voltages against the service manual's voltage chart, and finally lifts a suspect part to test it out of circuit. The order is largely fixed; what varies is judgement about which reading is "off". When judgement runs out, heuristics fill the gap, most famously replacing every electrolytic capacitor ("recapping") in the hope that the fault goes with them.

*The information is uneven.* Service manuals with schematics and voltage charts exist for many classic models, but units are often modified, undocumented or covered by documentation the owner cannot obtain. U.S. state right-to-repair laws now oblige manufacturers to supply documentation for digital electronics, for example in New York since December 2023 \[21\] and Texas since 1 September 2026 \[22\], but they apply to digital products sold after cut-off dates, and the EU repair directive covers only listed product groups such as washing machines and displays \[23, 24\]. Vintage all-analog gear falls outside all of them.

*Labelled fault data is scarce, so we simulate it.* No public dataset pairs bench measurements with confirmed failed parts: repairs are rarely logged in structured form, every unit's tolerances differ, and a given fault on a given model is rare. The analog-test literature answered this decades ago with simulated fault dictionaries \[25\] and with the observation that some faults are indistinguishable at the available test points, forming ambiguity groups \[26\]. We follow that path with modern tools. Five original reference blocks and a composite channel strip (59 components, 250 catalog faults) are simulated in ngspice under every catalog fault with datasheet tolerances; the first pass produced 253,000 simulated units with 0 convergence failures. Hand calculations agree with every simulated bias point and gain within the stated tolerance (22 of 22 checks). Simulation also shows why technicians struggle: 120 of the channel strip's 250 catalog faults are latent, producing no symptom in most units, so a symptom alone rarely points at one part.

#figure(
  table(
    columns: (1.1fr, 0.9fr, 1.2fr, 1.4fr),
    [Data source], [Fault labels], [Coverage], [Bias or gap],
    [Shop repair logs], [Sparse, informal], [Common faults on popular models], [Unstructured; customer privacy],
    [Forum threads], [Unverified], [Anecdotal], [Folklore, e.g. over-blaming capacitors],
    [Service manuals], [None (nominal values only)], [One model at a time], [No fault behaviour; availability varies],
    [Circuit simulation], [Exact, by construction], [Every catalog fault, every tolerance draw], [Simulation-to-reality gap; single faults only],
    [Physical fault board], [Exact, few], [Chosen faults on one low-voltage block], [Small; validation only],
  ),
  caption: [Where labelled diagnostic data could come from. Simulation is the only source with exact labels and full coverage; its weakness, the gap to real hardware, is tested with a low-voltage fault board.],
) <tab:data>

#decision("Original generic circuits instead of commercial schematics")[
*Options:* model a specific commercial product from its service manual, or design original reference circuits that use the same topologies. *Choice:* original circuits (a supply with zener regulator and 250 V B+ chain, a 12AX7 stage, a passive Baxandall tone control, an op-amp stage and a two-transistor line driver). *Why:* no copyright exposure, full control of ground truth, and topologies common to thousands of real units. *Consequence:* transfer to real gear must be shown, first with a low-voltage breadboard of the driver block.
]

#part(3, "Objectives and measurable success criteria", "MEMBER_3")

*Objectives.* Differential must (O1) name the faulty part or its ambiguity group accurately; (O2) get there with less measurement effort than today's practice; (O3) be honest about uncertainty: calibrated confidence, visible ambiguity groups and an explicit "no single-fault model fits" outcome; (O4) never issue an unsafe instruction or invent a reading; and (O5) stay practical in speed and cost. @tab:targets lists the targets we will commit to before running the full evaluation; they will be reported exactly as written, met or missed.

#figure(
  table(
    columns: (0.3fr, 2.35fr, 1.0fr),
    [ID], [Metric (system)], [Target],
    [T1], [Top-1 accuracy, ambiguity-group aware, all 1000 single-fault test cases (Full system (symptom prior + engine))], [≥ 95%],
    [T2], [Top-1 accuracy, ambiguity-group aware, 500 channel-strip cases (Full system)], [≥ 93%],
    [T3], [Top-3 accuracy, ambiguity-group aware, all 1000 cases (Full system)], [≥ 99%],
    [T4], [Mean measurement cost of the engine (uniform prior) relative to the fixed-order procedure (same inference), with top-1 no more than 2 points lower (Engine vs fixed-order)], [≤ 0.40 × (≥ 60% less effort)],
    [T5], [Mean measurement cost of the engine (uniform prior) relative to random probing, with top-1 no more than 2 points lower (Engine vs random)], [≤ 0.40 × (≥ 60% less effort)],
    [T6], [Expected calibration error of the full system's stopping confidence (10 equal-width bins) (Full system)], [≤ 0.03],
    [T7], [AUROC of the unmodeled-fault score: 100 double-fault / out-of-catalog cases vs single-fault cases (Engine)], [≥ 0.90],
    [T8], [Unsafe outputs on the red-team suite (at least 40 adversarial cases) (Agent (offline now; live when a key is provided))], [0 unsafe outputs],
    [T9], [Hallucinated-reading rate: numbers in agent messages or tickets not traceable to a tool result (Differential agent)], [0%],
    [T10], [Top-1 accuracy margin over the LLM-only baseline on the stratified 150-case subset (Full system vs LLM only (requires API key))], [≥ +30 points],
    [T11], [Symptom-extraction micro-F1 on the held-out paraphrase set (Claude extraction (requires API key); offline rules)], [≥ 0.90 (Claude); ≥ 0.80 (offline rules)],
    [T12], [Exact-match meter-reading accuracy on at least 200 synthetic photos (Claude vision (requires API key); offline reader)], [≥ 95% (Claude); ≥ 90% (offline reader)],
    [T13], [95th-percentile engine time per recommendation step on the channel strip, 4-core CPU (Engine)], [≤ 0.5 s],
    [T14], [Mean API cost per diagnosis at list prices (Live agent (requires API key))], [≤ \$0.10],
    [T15], [Share of top-1 diagnoses that are capacitor faults minus the true capacitor share of the test set (Full system (LLM-only share reported when a key is provided))], [within ±5 points],
    [T16], [Mean cost of the full system relative to the engine with a uniform prior, with top-1 no more than 2 points lower (Symptom prior ablation)], [≤ 0.75 × (≥ 25% less effort)],
  ),
  caption: [Success criteria, locked before the full evaluation. "Group aware" means a diagnosis counts as correct when it names the true fault's ambiguity group. Targets marked "requires API key" are measured once a key is available; all others are measured in this build.],
) <tab:targets>

*How success will be measured.* The test set holds 1000 held-out single-fault cases (500 on the channel strip and 100 per block) drawn with random seeds disjoint from training, plus 100 double-fault or out-of-catalog cases. Each case is diagnosed by six systems: random probing, the fixed-order procedure, the engine with each of two likelihood models, the full hybrid and a language model alone (on a stratified subset of 150 cases). Every headline claim carries a bootstrap 95% confidence interval and a paired comparison.

*A pilot shaped the bars.* Before locking the targets we ran a feasibility pilot on held-out training draws (never the test set). On the channel strip, information-driven probing identified the fault group in 99.0% of cases at a mean cost of 6.4 units, against 77.0% and 25.0 units for the fixed-order procedure. The accuracy targets sit a few points below these pilot values because the full evaluation adds errors from reading free-text complaints and spans a larger test set; the effort targets demand savings of at least 60%.

*Scope and non-goals.* In scope: single static faults (opens, shorts, drift, degradation) in the five blocks and the channel strip. Out of scope: intermittent and thermal faults, mains-side work, autonomous probing, and replacing the technician's judgement.

#decision("Score accuracy by ambiguity group and effort in weighted cost units")[
*Options:* per-part accuracy and a count of measurements, or group-aware accuracy and weighted cost. *Choice:* the latter. Some faults produce identical readings at every test point; scoring per part would reward lucky guesses and punish honest ties. Costs weight what the technician actually spends: a DC probe costs 1 unit, a scope measurement 3, a high-voltage point 2 extra, and lifting a part 10, within a budget of 40 units per diagnosis.
]

#part(4, "Preliminary AI approach, risks and ethics", "MEMBER_4")

*Why a hybrid and not a language model alone.* Language models guess confidently because training and evaluation reward guessing over admitting uncertainty \[27\], and they carry the folklore of their training text. A diagnosis needs numbers that obey Kirchhoff's laws and uncertainty that means something. We therefore split the work: simulation supplies the physics, Bayesian inference supplies calibrated belief and chooses measurements by expected information gain \[28, 29\], and the language model handles what it is good at: reading a free-text complaint, reading a meter photo, and explaining the next step. @tab:families compares the candidate families.

#figure(
  table(
    columns: (1.15fr, 1.3fr, 1.45fr, 1.0fr),
    [Approach], [Strength], [Weakness], [Role here],
    [Language model alone], [Language, broad knowledge], [Ungrounded numbers; folklore bias; uncalibrated], [Baseline; language layer],
    [Troubleshooting chart / rules], [Transparent, safe], [Brittle; no uncertainty; ignores the complaint], [Fixed-order baseline],
    [Fault dictionary, nearest match], [Simple, simulation-based], [Ignores tolerance spread; no measurement planning], [Superseded],
    [Generative Bayesian model (Gaussian mixtures)], [Handles any measurement subset; flags out-of-model faults], [Density estimation in about 50 dimensions], [Core engine],
    [Gradient-boosted classifier], [Accurate, fast], [Needs calibration; weak off-distribution], [Comparison engine],
  ),
  caption: [Candidate AI families. Each fills one role; no single family does the whole job.],
) <tab:families>

*Risks and first-pass ethics.* _Safety:_ U.S. workplace rules require capacitors to be discharged and live parts above 50 V to be de-energised or guarded \[20\]; Differential attaches discharge and isolation warnings to every high-voltage step and refuses mains-side procedures, in code. _Over-confidence:_ in the pilot the engine stopped with at least 90% confidence in 98% of cases and was right in 99.4% of those; calibration is therefore a measured target, not an assumption. _Bias:_ we will test for "recap bias" and break errors down by block, part kind and fault type, borrowing the disaggregated audit used on face recognition \[30\]. _Security:_ service notes are untrusted data, since indirect prompt injection is the top risk for LLM applications \[31, 32\]. _Accountability:_ the technician decides and confirms every reading; in the EU, software is now a product under the revised Product Liability Directive \[33\]. _Regulation:_ Differential is not a high-risk system under the EU AI Act, but its duty to disclose that users are talking to an AI has applied since 2 August 2026 \[34\]; we will map it onto the NIST AI Risk Management Framework's Govern, Map, Measure and Manage functions \[35\].

#figure(
  table(
    columns: (1.4fr, 0.45fr, 0.45fr, 2.1fr),
    [Risk], [L], [I], [Mitigation (owner part)],
    [Unsafe instruction near high voltage], [M], [H], [Deterministic safety layer; red-team suite with a zero target (Part 4)],
    [Invented or misread readings], [M], [H], [Numeric grounding check; human confirms each reading (Part 4)],
    [Confident wrong diagnosis], [M], [M], [Calibration target; ambiguity groups shown; unmodeled route (Part 3)],
    [Simulation-to-reality gap], [H], [M], [Hand-calculation checks; tolerance ablation; fault board (Part 2)],
    [No API key during the build], [H], [M], [Offline mode first; live results reported as pending (Part 3)],
    [Customer data exposure], [L], [M], [No telemetry by default; local-first storage (Part 1)],
  ),
  caption: [Initial risk register (L = likelihood, I = impact; H/M/L). Every risk has an owner and a measurable control.],
) <tab:risks>

#decision("Safety rules live in code, not in the prompt")[
*Options:* instruct the model to be safe, or enforce safety deterministically outside the model. *Choice:* both, with code as the authority. Prompts can be overridden by injected text or by user pressure; a rule that inspects every recommended test point and every outgoing message cannot. *Consequence:* the high-voltage warnings and refusals are identical in the live, offline and replay modes and can be tested exhaustively.
]

// END-PARTS

#heading(level: 1, numbering: none)[References]
#ref-entry(1)[“Audio Repair Los Angeles · Pro Studio Gear Service,” _The Studio Doctors_, n.d. [Online]. Available: #link("https://thestudiodoctors.com/audio-repair-los-angeles.html")[https://thestudiodoctors.com/audio-repair-los-angeles.html] (accessed Sep. 28, 2026).]
#ref-entry(2)[“Expert Vintage Stereo Repair,” _Archer High Fidelity_, n.d. [Online]. Available: #link("https://archerhifi.com/repair-and-service/vintage-stereo-repair/")[https://archerhifi.com/repair-and-service/vintage-stereo-repair/] (accessed Sep. 28, 2026).]
#ref-entry(3)[“Services & Rates — CW Guitar Audio - Amp Repair and Mods - Columbus Ohio,” _CW Guitar Audio_, n.d. [Online]. Available: #link("https://www.cwguitaraudio.com/services")[https://www.cwguitaraudio.com/services] (accessed Sep. 28, 2026).]
#ref-entry(4)[“Electronic Service Rates and Policies,” _British Audio_, n.d. [Online]. Available: #link("https://britishaudio.com/pages/electronic-repair-rates")[https://britishaudio.com/pages/electronic-repair-rates] (accessed Sep. 28, 2026).]
#ref-entry(5)[“The Vintage Audio Revival Is Running Out of People Who Can Keep It Alive and a Spare Parts Problem Is Making It Worse,” _Headphonesty_, Aug. 2026. [Online]. Available: #link("https://www.headphonesty.com/2026/08/vintage-audio-revival-running-out-people/")[https://www.headphonesty.com/2026/08/vintage-audio-revival-running-out-people/] (accessed Sep. 28, 2026).]
#ref-entry(6)[U.S. Bureau of Labor Statistics, “Electrical and Electronics Installers and Repairers,” _Occupational Outlook Handbook_, Aug. 27, 2026. [Online]. Available: #link("https://www.bls.gov/ooh/installation-maintenance-and-repair/electrical-and-electronics-installers-and-repairers.htm")[https://www.bls.gov/ooh/installation-maintenance-and-repair/electrical-and-electronics-installers-and-repairers.htm] (accessed Sep. 28, 2026).]
#ref-entry(7)[U.S. Bureau of Labor Statistics, “Employment Projections: 2025-2035 Summary,” Economic News Release, Aug. 27, 2026. [Online]. Available: #link("https://www.bls.gov/news.release/ecopro.nr0.htm")[https://www.bls.gov/news.release/ecopro.nr0.htm] (accessed Sep. 28, 2026).]
#ref-entry(8)[“Re-Tales \#13: Getting your hi-fi fix(ed),” _Stereophile_, n.d. [Online]. Available: #link("https://www.stereophile.com/content/re-tales-13-getting-your-hi-fi-fixed")[https://www.stereophile.com/content/re-tales-13-getting-your-hi-fi-fixed] (accessed Sep. 28, 2026).]
#ref-entry(9)[E. Brynjolfsson, D. Li, and L. R. Raymond, “Generative AI at Work,” _National Bureau of Economic Research, Working Paper 31161_, 2023. Published in The Quarterly Journal of Economics, vol. 140, no. 2, 2025. [Online]. Available: #link("https://www.nber.org/papers/w31161")[https://www.nber.org/papers/w31161] (accessed Sep. 28, 2026).]
#ref-entry(10)[Recording Industry Association of America, “2025 Year-End Music Industry Revenue Report,” _RIAA_, Mar. 16, 2026. [Online]. Available: #link("https://www.riaa.com/reports/2025-year-end-music-industry-revenue-report-riaa/")[https://www.riaa.com/reports/2025-year-end-music-industry-revenue-report-riaa/] (accessed Sep. 28, 2026).]
#ref-entry(11)[“US recorded-music revenues grew by 6.9% in the first half of 2026,” _Music Ally_, Sep. 1, 2026. [Online]. Available: #link("https://musically.com/2026/09/01/us-recorded-music-revenues-grew-by-6-9-in-the-first-half-of-2026/")[https://musically.com/2026/09/01/us-recorded-music-revenues-grew-by-6-9-in-the-first-half-of-2026/] (accessed Sep. 28, 2026).]
#ref-entry(12)[“An Ongoing Tube Shortage Is Pushing High-End Audio to Its Breaking Point, Warns Industry Insider,” _Headphonesty_, Sep. 2025. [Online]. Available: #link("https://www.headphonesty.com/2025/09/ongoing-tube-shortage-breaking-high-end-audio/")[https://www.headphonesty.com/2025/09/ongoing-tube-shortage-breaking-high-end-audio/] (accessed Sep. 28, 2026).]
#ref-entry(13)[Siemens AG, “Siemens expands Industrial Copilot with New generative AI-powered Maintenance Offering,” Press release, Mar. 24, 2025. [Online]. Available: #link("https://press.siemens.com/global/en/pressrelease/siemens-expands-industrial-copilot-new-generative-ai-powered-maintenance-offering")[https://press.siemens.com/global/en/pressrelease/siemens-expands-industrial-copilot-new-generative-ai-powered-maintenance-offering] (accessed Sep. 28, 2026).]
#ref-entry(14)[PTC Inc., “PTC Launches ServiceMax AI, a Generative AI-Powered Field Service Assistant,” Press release, Feb. 12, 2025. [Online]. Available: #link("https://www.ptc.com/en/news/2025/ptc-launches-servicemax-ai")[https://www.ptc.com/en/news/2025/ptc-launches-servicemax-ai] (accessed Sep. 28, 2026).]
#ref-entry(15)[IBM, “Introducing Maximo Application Suite 9.2: AI built for asset management that keeps operations running,” Press release, Jun. 25, 2026. [Online]. Available: #link("https://www.ibm.com/new/announcements/introducing-maximo-application-suite-9-2")[https://www.ibm.com/new/announcements/introducing-maximo-application-suite-9-2] (accessed Sep. 28, 2026).]
#ref-entry(16)[“iFixit launches FixBot AI repair helper, with free and paid versions,” _9to5Mac_, Dec. 9, 2025. [Online]. Available: #link("https://9to5mac.com/2025/12/09/ifixit-launches-fixbot-ai-repair-helper-with-free-and-paid-versions/")[https://9to5mac.com/2025/12/09/ifixit-launches-fixbot-ai-repair-helper-with-free-and-paid-versions/] (accessed Sep. 28, 2026).]
#ref-entry(17)[L. Skelic et al., “CIRCUIT: A Benchmark for Circuit Interpretation and Reasoning Capabilities of LLMs,” _arXiv preprint arXiv:2502.07980_, Feb. 2025. [Online]. Available: #link("https://arxiv.org/abs/2502.07980")[https://arxiv.org/abs/2502.07980] (accessed Sep. 28, 2026).]
#ref-entry(18)[M. Li, J. Zhong, T. Chen, Y. Lai, and K. Psounis, “EEE-Bench: A Comprehensive Multimodal Electrical And Electronics Engineering Benchmark,” _Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)_, 2025. [Online]. Available: #link("https://openaccess.thecvf.com/content/CVPR2025/html/Li_EEE-Bench_A_Comprehensive_Multimodal_Electrical_And_Electronics_Engineering_Benchmark_CVPR_2025_paper.html")[https://openaccess.thecvf.com/content/CVPR2025/html/Li\_EEE-Bench\_A\_Comprehensive\_Multimodal\_Electrical\_And\_Electronics\_Engineering\_Benchmark\_CVPR\_2025\_paper.html] (accessed Sep. 28, 2026).]
#ref-entry(19)[“Enhancing Large Language Model-Based Systems for End-to-End Circuit Analysis Problem Solving,” _arXiv preprint arXiv:2512.10159_, Dec. 2025. [Online]. Available: #link("https://arxiv.org/abs/2512.10159")[https://arxiv.org/abs/2512.10159] (accessed Sep. 28, 2026).]
#ref-entry(20)[U.S. Occupational Safety and Health Administration, “29 CFR 1910.333, Selection and use of work practices,” _Code of Federal Regulations_, Jul. 22, 2026. [Online]. Available: #link("https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.333")[https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.333].]
#ref-entry(21)[New York State Legislature, “N.Y. General Business Law § 399-nn (Digital Fair Repair Act),” _New York State Senate (Laws of New York)_, Dec. 28, 2022. [Online]. Available: #link("https://www.nysenate.gov/legislation/laws/GBS/399-NN")[https://www.nysenate.gov/legislation/laws/GBS/399-NN] (accessed Sep. 28, 2026).]
#ref-entry(22)[Texas Legislature, “HB 2963 (2025), Tex. Bus. & Com. Code ch. 121, Diagnosis, Maintenance, and Repair of Certain Digital Electronic Equipment,” _Texas Legislature Online_, 2025. [Online]. Available: #link("https://capitol.texas.gov/tlodocs/89R/billtext/html/HB02963F.htm")[https://capitol.texas.gov/tlodocs/89R/billtext/html/HB02963F.htm] (accessed Sep. 28, 2026).]
#ref-entry(23)[European Parliament and Council of the European Union, “Directive (EU) 2024/1799 on common rules promoting the repair of goods,” _Official Journal of the European Union_, Jun. 13, 2024. [Online]. Available: #link("https://eur-lex.europa.eu/eli/dir/2024/1799/oj")[https://eur-lex.europa.eu/eli/dir/2024/1799/oj].]
#ref-entry(24)[European Commission, “Questions & Answers: Directive on repair of goods (obligation to repair),” Jul. 30, 2024. [Online]. Available: #link("https://commission.europa.eu/document/download/2d443b31-dc2a-4e54-a9ec-5fbb61c895e9_en?filename=2024_07_18_QA_Right2repair_FINAL.pdf")[https://commission.europa.eu/document/download/2d443b31-dc2a-4e54-a9ec-5fbb61c895e9\_en?filename=2024\_07\_18\_QA\_Right2repair\_FINAL.pdf] (accessed Sep. 28, 2026).]
#ref-entry(25)[J. W. Bandler and A. E. Salama, “Fault diagnosis of analog circuits,” _Proceedings of the IEEE_, vol. 73, no. 8, pp. 1279–1325, Aug. 1985. doi: 10.1109/PROC.1985.13281.]
#ref-entry(26)[G. N. Stenbakken, T. M. Souders, and G. W. Stewart, “Ambiguity groups and testability,” _IEEE Transactions on Instrumentation and Measurement_, vol. 38, no. 5, pp. 941–947, Oct. 1989. doi: 10.1109/19.39034.]
#ref-entry(27)[A. T. Kalai, O. Nachum, S. S. Vempala, and E. Zhang, “Why Language Models Hallucinate,” _arXiv preprint arXiv:2509.04664_, Sep. 2025. [Online]. Available: #link("https://arxiv.org/abs/2509.04664")[https://arxiv.org/abs/2509.04664] (accessed Sep. 28, 2026).]
#ref-entry(28)[D. V. Lindley, “On a measure of the information provided by an experiment,” _The Annals of Mathematical Statistics_, vol. 27, no. 4, pp. 986–1005, 1956. doi: 10.1214/aoms/1177728069.]
#ref-entry(29)[J. de Kleer and B. C. Williams, “Diagnosing multiple faults,” _Artificial Intelligence_, vol. 32, no. 1, pp. 97–130, Apr. 1987. doi: 10.1016/0004-3702(87)90063-4.]
#ref-entry(30)[J. Buolamwini and T. Gebru, “Gender Shades: Intersectional Accuracy Disparities in Commercial Gender Classification,” _Proceedings of the 1st Conference on Fairness, Accountability and Transparency (PMLR 81)_, pp. 77–91, 2018. [Online]. Available: #link("https://proceedings.mlr.press/v81/buolamwini18a.html")[https://proceedings.mlr.press/v81/buolamwini18a.html].]
#ref-entry(31)[OWASP GenAI Security Project, “OWASP Top 10 for LLM Applications 2026,” _OWASP Foundation (official project repository)_, Aug. 4, 2026. [Online]. Available: #link("https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/tree/main/2026/final")[https://github.com/GenAI-Security-Project/GenAI-LLM-Top10/tree/main/2026/final] (accessed Sep. 28, 2026).]
#ref-entry(32)[K. Greshake, S. Abdelnabi, S. Mishra, C. Endres, T. Holz, and M. Fritz, “Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection,” _Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security (AISec '23)_, 2023. doi: 10.1145/3605764.3623985.]
#ref-entry(33)[European Parliament and Council of the European Union, “Directive (EU) 2024/2853 of 23 October 2024 on liability for defective products (Product Liability Directive),” _Official Journal of the European Union, OJ L, 2024/2853_, Oct. 23, 2024. [Online]. Available: #link("https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng")[https://eur-lex.europa.eu/eli/dir/2024/2853/oj/eng] (accessed Sep. 28, 2026).]
#ref-entry(34)[European Commission, “Commission starts enforcing AI Act rules and new transparency requirements on 2 August (IP/26/1714),” Press release, Jul. 31, 2026. [Online]. Available: #link("https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august")[https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august] (accessed Sep. 28, 2026).]
#ref-entry(35)[National Institute of Standards and Technology, “Artificial Intelligence Risk Management Framework (AI RMF 1.0),” _NIST AI 100-1_, Jan. 26, 2023. [Online]. Available: #link("https://airc.nist.gov/airmf-resources/airmf/5-sec-core/")[https://airc.nist.gov/airmf-resources/airmf/5-sec-core/] (accessed Sep. 28, 2026).]
#ref-entry(36)[“Flux nabs \$37M to automate printed circuit board development with AI,” _SiliconANGLE_, Feb. 27, 2026. [Online]. Available: #link("https://siliconangle.com/2026/02/27/flux-nabs-37m-automate-printed-circuit-board-development-ai/")[https://siliconangle.com/2026/02/27/flux-nabs-37m-automate-printed-circuit-board-development-ai/] (accessed Sep. 28, 2026).]
#ref-entry(37)[European Parliament and Council of the European Union, “Regulation (EU) 2026/1744 of 8 July 2026 amending Regulations (EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230 as regards the simplification of the implementation of harmonised rules on artificial intelligence (Digital Omnibus on AI),” _Official Journal of the European Union, OJ L, 2026/1744_, Jul. 8, 2026. [Online]. Available: #link("https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng")[https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng] (accessed Sep. 28, 2026).]
#ref-entry(38)[Anthropic, “Claude Sonnet 5.5 (model page),” _Claude Developer Platform documentation_, Sep. 28, 2026. [Online]. Available: #link("https://platform.claude.com/docs/en/models/sonnet-5-5/overview")[https://platform.claude.com/docs/en/models/sonnet-5-5/overview] (accessed Sep. 28, 2026).]

#heading(level: 1, numbering: none)[Appendix A · Industry watch]
#set text(size: 9pt)
- *IBM Maximo Application Suite 9.2 (June 2026)* adds an agentic assistant and an MCP server \[15\]. Incumbent asset-management platforms are becoming agent hosts; a component-level diagnosis engine could plug into them as a tool.
- *Flux raises \$37M for AI circuit design (February 2026)* \[36\]. Investors are funding AI that reasons about circuits, not just documents.
- *EU AI Act transparency duties apply (2 August 2026)* \[34\], while the Digital Omnibus postponed the high-risk rules for Annex III systems to December 2027 \[37\]. Differential's disclosure design must be ready now.
- *Texas right-to-repair law in force (1 September 2026)* \[22\], the latest of several state laws that give repairers access to documentation for digital products.
- *Claude Sonnet 5.5 released (28 September 2026)* \[38\]. The model family Differential's agent defaults to changed on build day; the design pins the model by configuration and caches responses so results stay reproducible.

#heading(level: 1, numbering: none)[Appendix B · Course coverage map]
#figure(
  table(
    columns: (0.25fr, 1.0fr, 2.9fr),
    [Wk], [Topic], [Where Differential uses it],
    [2], [AI/ML algorithms], [Bayesian inference, Gaussian-mixture likelihoods, gradient boosting, information-theoretic measurement selection],
    [3], [Python], [Entire stack: simulation driver, engine, agent, web app, evaluation],
    [4], [Large language models], [Symptom extraction, explanations, and the LLM-only baseline with an analysis of its failure modes],
    [5], [LLM-enhanced agents], [Tool-using diagnostic agent that remembers the session's evidence],
    [6], [Building ML systems], [Simulation pipeline, caching, calibration, evaluation harness, CI, cost and latency budgets],
    [7], [NLP], [Free-text complaints to structured symptoms; paraphrase benchmark; label-leakage checks],
    [8], [Image recognition], [Reading multimeter displays from photos],
    [9], [Facial recognition (bias auditing)], [Disaggregated error analysis by circuit, topology, part kind and fault type],
    [10], [Autonomous transportation], [Levels of diagnostic autonomy (L0-L4) by analogy to driving automation],
    [11], [Robotics], [Sense-decide-act loop; instrument interface; path to automated test fixtures],
    [12], [Cybersecurity], [Prompt-injection defence, untrusted-data handling, red-team suite],
    [13], [Ethics and governance], [Safety, accountability, bias, privacy, right to repair, NIST AI RMF, EU AI Act],
  ),
  caption: [Course topics and where Differential uses them.],
)

