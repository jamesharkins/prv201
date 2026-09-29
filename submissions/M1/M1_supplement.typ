#import "base.typ": *
#show: setup.with(title: "Differential - M1 supplement", short: "M1 · Supplement")

#title-block(
  title: [Differential: M1 supplement],
  subtitle: "Milestone 1 · Industry watch, course coverage and how each bar was set (not part of the problem statement)",
  meta: ("PRV 201 Frontiers of Technology (AI)", "Track A: Build", "Stevens Institute of Technology", "September 2026"),
)
This supplement accompanies the M1 problem statement. The statement stands on its own; nothing here is needed to read it.

#heading(level: 1, numbering: none)[Industry watch, September 2026: breakthroughs, launches, regulation and investment]

- *Frontier models score highly on textbook analog questions.* The top Razavi-Bench model scored 95.50%, graded by another language model, and the benchmark has an experimental simulator-assisted mode \[1\]. A bench tool must add what textbooks do not test: tolerances, ambiguity between faults, the cost of each measurement and safety. T5 compares the full system with such a model working alone.
- *IBM Maximo 9.2 (June 2026)* adds agentic workflows and an MCP server through which customers can connect their own agents \[2\], a possible route for a diagnosis engine into industrial repair depots.
- *EU AI Act transparency rules apply from 2 August 2026* \[3\]; the 2026 amendments moved the Annex III high-risk rules to 2 December 2027 \[4\] and keep a duty on providers and deployers to support their staff's AI literacy \[5\]. They would bind Differential only once offered in the EU.
- *Colorado re-enacted its AI law* as a regime for automated decision-making technology in consequential decisions, approved on 14 May 2026 and in force from 1 January 2027 \[6\]. A shop that used repair tickets to decide about its staff could come within such rules; Differential's terms of use forbid that use.
- *Investment is flowing to AI for the trades, starting with dispatch.* Probook announced \$40 million on 23 June 2026, a \$34 million Series A led by Andreessen Horowitz and a \$6 million seed round led by Sequoia, for an AI operating system for HVAC, plumbing and electrical contractors that it built dispatch-first \[7\]. Our reading: investors are funding AI for scheduling and dispatch in repair businesses, while the diagnosis a technician does at the bench is not what this money buys; that is the gap Differential addresses, and repair businesses may meet AI first in their front office.

#pagebreak(weak: true)
#heading(level: 1, numbering: none)[Course coverage map]
#figure(
  table(
    columns: (0.25fr, 1.0fr, 2.9fr, 0.62fr),
    table.header([Wk], [Topic], [Where the project uses it], [Depth]),
    [2], [Introduction to AI/ML algorithms], [Bayesian inference, Gaussian mixtures, boosted trees, information-gain measurement choice (Part 4 — Preliminary AI approach, risks and ethics)], [Core],
    [3], [Python, the AI/ML lingua franca], [The simulation, engine and evaluation code that produces every number in the statement (repository); no code appears in the statement itself], [Core (code)],
    [4], [Introduction to large language models], [Chat-model benchmark scores (Part 1 — Problem, stakeholders and industry context); the language-model baselines (Part 3 — Objectives and measurable success criteria; T5); why language models guess (Part 4 — Preliminary AI approach, risks and ethics)], [Core],
    [5], [Building LLM-enhanced agents], [An assistant whose tools act only on the diagnosis session; complaint reading and explanation (Part 4 — Preliminary AI approach, risks and ethics)], [Supporting],
    [6], [Building ML systems], [Pilots, locked targets with confidence bounds, stress sets, hardware protocol (Part 3 — Objectives and measurable success criteria)], [Core],
    [7], [Introduction to natural language processing], [Complaint reading with noise; sealed paraphrase bank (Part 3 — Objectives and measurable success criteria; T18)], [Supporting],
    [8], [Image recognition systems], [Meter-photo reading scored on value, unit and mode (T19)], [Supporting],
    [9], [Facial recognition systems (accuracy, bias, deployment)], [Error breakdown, as in face-recognition audits, by who bears the errors: complaint writers, technicians, owners of undocumented gear (Part 4 — Preliminary AI approach, risks and ethics)], [Supporting],
    [10], [Autonomous transportation], [Five levels of diagnostic autonomy, L0 (the technician does everything) to L4 (an unattended fixture), defined by analogy to driving automation; Differential placed at L2 on safety and accountability grounds (Part 4 — Preliminary AI approach, risks and ethics)], [Supporting],
    [11], [Introduction to robotics], [A sense-decide loop without actuation: instruments sense (SCPI on the 24 V boards), the engine decides the next measurement and a person acts; automated test fixtures (levels L3-L4) would add the actuation (Part 4 — Preliminary AI approach, risks and ethics)], [Partial],
    [12], [AI in cybersecurity and fraud detection], [Anomaly detection: the calibrated "no single fault fits" outcome flags units outside the catalog (Part 3 — Objectives and measurable success criteria; T13, T22); prompt injection, untrusted data, session-only tools and adversarial prompts (Part 4 — Preliminary AI approach, risks and ethics; T16)], [Core],
    [13], [Ethics of AI: risks, responsibility and governance], [Hazard audit, OSHA, liability, EU AI Act and product liability, research ethics, NIST AI RMF (Part 1 — Problem, stakeholders and industry context, Part 4 — Preliminary AI approach, risks and ethics)], [Core],
  ),
  caption: [Course topics and where the project uses them, with parts named by title.],
)

#heading(level: 1, numbering: none)[Secondary targets]
#figure(
  table(
    columns: (0.3fr, 2.1fr, 1.1fr, 0.3fr, 2.1fr, 1.1fr),
    table.header([ID], [Secondary target], [Bar], [ID], [Secondary target], [Bar]),
    [T2], [Named first, channel strip only], [≥ 94%], [T24], [Powered readings above 50 V per diagnosis ÷ half-split's], [≤ 0.19×],    [T3], [True group among the first three shown], [≥ 99%], [T14], [Accuracy change with a wrong prior, either way], [≥ −1/−1 points],    [T8], [Confirmed-answer effort ÷ fixed-order chart's], [≤ 0.64×], [T18], [Symptom-reading micro-F1 on a sealed bank (API key)], [≥ 0.90 (Claude); ≥ 0.80 (rules)],    [T10], [Confirmed-answer effort ÷ random probing's], [≤ 0.59×], [T19], [Exact reading of ≥ 200 meter photos (API key)], [≥ 95% (Claude); ≥ 90% (offline)],    [T11], [Confirmed-answer effort, complaint read ÷ ignored], [≤ 0.98×], [T20], [95th-percentile time per recommendation], [≤ 0.5 s],    [T22], [Out-of-model units flagged; separation (AUROC)], [≥ 51% flagged; AUROC ≥ 0.77], [T21], [Mean API cost per diagnosis at list prices (API key)], [≤ \$0.10],    [T23], [Single faults named; accuracy when naming], [≥ 94% named; ≥ 99% right when naming], [], [], [],  ),
  caption: [Secondary targets: same rule, reported, not deciding success. Micro-F1: symptom reading scored over all (complaint, symptom) pairs; AUROC: chance an out-of-catalog unit gets a higher "no single fault fits" probability than a single-fault unit.],
) <tab:secondary>

#heading(level: 1, numbering: none)[How each bar was set]
Every bar that a pilot can estimate follows one rule, fixed before the pilot ran: the pilot estimate moved 1.5 standard errors against the system, rounded to the reporting step. One refinement came after the pilot and before any test unit: rounding never carries a bar past the pilot estimate, and effort ratios round to 0.01 instead of 0.05. The coarser step had rounded T9's bar onto its own pilot estimate, and nearest rounding had set T23's accuracy bar at 100%, which no confidence bound can clear; the refinement loosened those two and tightened T8, T10 and T11. A target is met only when the test's one-sided 95% confidence bound clears the bar. The chance column counts both the pilot's own error and the test's. T4, T14, T22 and T23 have two or three parts; their derivations are in `results/targets.json`. T5 (no pilot without an API key) and T7 (hardware) were fixed in advance; T15-T17 are release gates.
#figure(
  table(
    columns: (0.4fr, 1.9fr, 0.85fr, 0.75fr, 0.85fr, 0.7fr, 1.1fr, 0.65fr),
    align: (left, left, right, right, right, right, right, right),
    table.header([ID], [Target], [Pilot], [SE], [Raw bar], [Bar], [A pass needs], [Chance]),
    [T1], [Failed part's group named first], [95.6%], [1.0], [94.0%], [≥ 94%], [at least 4728 of 5,000], [83%],
    [T2], [Named first, channel strip only], [96.5%], [1.4], [94.3%], [≥ 94%], [at least 2370 of 2,500], [88%],
    [T3], [True group among the first three shown], [99.7%], [0.6], [98.7%], [≥ 99%], [at least 4962 of 5,000], [76%],
    [T6], [Failed part's group named first, aged units], [93.2%], [1.2], [91.3%], [≥ 91%], [at least 4584 of 5,000], [88%],
    [T13], [Out-of-catalog units sent only to healthy parts], [8.8%], [2.0], [11.8%], [≤ 12%], [at most 272 of 2,500], [84%],
    [T9], [Confirmed-answer effort ÷ half-split tracing's], [0.651], [0.012], [0.669], [≤ 0.67×], [bound clears the bar], [85%],
    [T8], [Confirmed-answer effort ÷ fixed-order chart's], [0.625], [0.012], [0.643], [≤ 0.64×], [bound clears the bar], [76%],
    [T10], [Confirmed-answer effort ÷ random probing's], [0.572], [0.011], [0.588], [≤ 0.59×], [bound clears the bar], [86%],
    [T11], [Confirmed-answer effort, complaint read ÷ ignored], [0.965], [0.010], [0.980], [≤ 0.98×], [bound clears the bar], [84%],
    [T12], [Calibration error of the shown probabilities at the stop], [0.012], [0.006], [0.020], [≤ 0.02], [bound clears the bar], [81%],
  ),
  caption: [Bar derivations from the pilot (weighted like the test set). SE: standard error (points for rates). Raw bar: estimate moved 1.5 SE against the system; the bar rounds it to the reporting step, never past the estimate. For rates, "a pass needs" is the count whose one-sided bound clears the bar. The chance that every pilot-estimable primary is met, if they were independent, is about 25%; about 1 are expected to miss.],
)

#heading(level: 1, numbering: none)[References]
#ref-entry(1)[Z. Zhang, “Razavi-Bench: An Expert-Curated Benchmark for Analog-Design Reasoning,” _Benchmark repository and leaderboard (GitHub Arcadia-1/razavi-bench), README at commit c8bce43, September 29 snapshot_, Sep. 2026. [Online]. Available: #link("https://github.com/Arcadia-1/razavi-bench")[https://github.com/Arcadia-1/razavi-bench] (accessed Sep. 29, 2026).]
#ref-entry(2)[IBM, “Introducing Maximo Application Suite 9.2: AI built for asset management that keeps operations running,” Press release, Jun. 25, 2026. [Online]. Available: #link("https://www.ibm.com/new/announcements/introducing-maximo-application-suite-9-2")[https://www.ibm.com/new/announcements/introducing-maximo-application-suite-9-2] (accessed Sep. 28, 2026).]
#ref-entry(3)[European Commission, “Commission starts enforcing AI Act rules and new transparency requirements on 2 August (IP/26/1714),” Press release, Jul. 31, 2026. [Online]. Available: #link("https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august")[https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august] (accessed Sep. 28, 2026).]
#ref-entry(4)[European Parliament and Council of the European Union, “Regulation (EU) 2026/1744 of 8 July 2026 amending Regulations (EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230 as regards the simplification of the implementation of harmonised rules on artificial intelligence (Digital Omnibus on AI),” _Official Journal of the European Union, OJ L, 2026/1744_, Jul. 24, 2026. [Online]. Available: #link("https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng")[https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng].]
#ref-entry(5)[Publications Office of the European Union, “Regulation (EU) 2024/1689, consolidated text 02024R1689-20260727 (incorporating Regulation (EU) 2026/1744),” _EUR-Lex, consolidated text 02024R1689-20260727_, Jul. 27, 2026. [Online]. Available: #link("https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727")[https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727].]
#ref-entry(6)[Colorado General Assembly, “SB26-189, Automated Decision-Making Technology,” May 14, 2026. [Online]. Available: #link("https://leg.colorado.gov/bills/sb26-189")[https://leg.colorado.gov/bills/sb26-189] (accessed Sep. 28, 2026).]
#ref-entry(7)[Probook, “Probook Raises \$40M from Andreessen Horowitz and Sequoia to Scale the AI Operating System for Home Services,” Press release, GlobeNewswire, Jun. 23, 2026. [Online]. Available: #link("https://www.globenewswire.com/news-release/2026/6/23/3316215/0/en/Probook-Raises-40M-from-Andreessen-Horowitz-and-Sequoia-to-Scale-the-AI-Operating-System-for-Home-Services.html")[https://www.globenewswire.com/news-release/2026/6/23/3316215/0/en/Probook-Raises-40M-from-Andreessen-Horowitz-and-Sequoia-to-Scale-the-AI-Operating-System-for-Home-Services.html] (accessed Sep. 29, 2026).]
