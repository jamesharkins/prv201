#import "base.typ": *
#show: setup.with(title: "Differential - M1 supplement", short: "M1 · Supplement")

#title-block(
  title: [Differential: M1 supplement],
  subtitle: "Milestone 1 · Industry watch and course coverage (not part of the problem statement)",
  meta: ("PRV 201 Frontiers of Technology (AI)", "Track A: Build", "Stevens Institute of Technology", "September 2026"),
)
This supplement accompanies the M1 problem statement. The statement stands on its own; nothing here is needed to read it.

#heading(level: 1, numbering: none)[Industry watch, September 2026]

- *Frontier models score highly on textbook analog questions.* The top Razavi-Bench model scored 95.50%, graded by another language model, and the benchmark has an experimental simulator-assisted mode \[1\]. A bench tool must add what textbooks do not test: tolerances, ambiguity between faults, the cost of each measurement and safety. T5 compares the full system with such a model working alone.
- *IBM Maximo 9.2 (June 2026)* adds agentic workflows and an MCP server through which customers can connect their own agents \[2\], a possible route for a diagnosis engine into industrial repair depots.
- *EU AI Act transparency rules apply from 2 August 2026* \[3\]; the 2026 amendments moved the Annex III high-risk rules to 2 December 2027 \[4\] and keep a duty on providers and deployers to support their staff's AI literacy \[5\]. They would bind Differential only once offered in the EU.
- *Colorado re-enacted its AI law* as a regime for automated decision-making technology in consequential decisions, approved on 14 May 2026 and in force from 1 January 2027 \[6\]. A shop that used repair tickets to decide about its staff could come within such rules; Differential's license forbids that use.
- *Claude Sonnet 5.5 was released on 28 September 2026* \[7\]. Models change quickly, so Differential pins its model, caches responses and re-runs its safety and grounding targets (T15-T19) on any change.

#heading(level: 1, numbering: none)[Course coverage map]
#figure(
  table(
    columns: (0.25fr, 1.0fr, 2.9fr, 0.62fr),
    table.header([Wk], [Topic], [Where the project uses it], [Depth]),
    [2], [AI/ML algorithms], [Bayesian inference, Gaussian mixtures, boosted trees, information-gain measurement choice (Part 4 — Preliminary AI approach, risks and ethics)], [Core],
    [3], [Python], [The simulation, engine and evaluation code that produces every number in the statement (repository); no code appears in the statement itself], [Core (code)],
    [4], [Large language models], [Chat-model benchmark scores (Part 1 — Problem, stakeholders and industry context); the language-model baselines (Part 3 — Objectives and measurable success criteria; T5); why language models guess (Part 4 — Preliminary AI approach, risks and ethics)], [Core],
    [5], [LLM-enhanced agents], [An assistant whose tools act only on the diagnosis session; complaint reading and explanation (Part 4 — Preliminary AI approach, risks and ethics)], [Supporting],
    [6], [Building ML systems], [Pilots, locked targets with confidence bounds, stress sets, hardware protocol (Part 3 — Objectives and measurable success criteria)], [Core],
    [7], [NLP], [Complaint reading with noise; sealed paraphrase bank (Part 3 — Objectives and measurable success criteria; T18)], [Supporting],
    [8], [Image recognition], [Meter-photo reading scored on value, unit and mode (T19)], [Supporting],
    [9], [Facial recognition (bias auditing)], [Error breakdown by who bears the errors: complaint writers, technicians, owners of undocumented gear (Part 4 — Preliminary AI approach, risks and ethics)], [Supporting],
    [10], [Autonomous transportation], [Five levels of diagnostic autonomy, L0 (the technician does everything) to L4 (an unattended fixture), defined by analogy to driving automation; Differential placed at L2 on safety and accountability grounds (Part 4 — Preliminary AI approach, risks and ethics)], [Supporting],
    [11], [Robotics], [Not covered. Reading bench instruments over SCPI is test automation, not robotics], [None],
    [12], [Cybersecurity], [Prompt injection, untrusted data, session-only tools, adversarial prompts (Part 4 — Preliminary AI approach, risks and ethics; T16)], [Core],
    [13], [Ethics and governance], [Hazard audit, OSHA, liability, EU AI Act and product liability, research ethics, NIST AI RMF (Part 1 — Problem, stakeholders and industry context, Part 4 — Preliminary AI approach, risks and ethics)], [Core],
  ),
  caption: [Course topics and where the project uses them, with parts named by title.],
)

#heading(level: 1, numbering: none)[References]
#ref-entry(1)[Zhishuai Zhang, “Razavi-Bench: An Expert-Curated Benchmark for Analog-Design Reasoning,” _Benchmark repository and leaderboard (GitHub Arcadia-1/razavi-bench)_, Sep. 2026. [Online]. Available: #link("https://github.com/Arcadia-1/razavi-bench")[https://github.com/Arcadia-1/razavi-bench] (accessed Sep. 28, 2026).]
#ref-entry(2)[IBM, “Introducing Maximo Application Suite 9.2: AI built for asset management that keeps operations running,” Press release, Jun. 25, 2026. [Online]. Available: #link("https://www.ibm.com/new/announcements/introducing-maximo-application-suite-9-2")[https://www.ibm.com/new/announcements/introducing-maximo-application-suite-9-2] (accessed Sep. 28, 2026).]
#ref-entry(3)[European Commission, “Commission starts enforcing AI Act rules and new transparency requirements on 2 August (IP/26/1714),” Press release, Jul. 31, 2026. [Online]. Available: #link("https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august")[https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august] (accessed Sep. 28, 2026).]
#ref-entry(4)[European Parliament and Council of the European Union, “Regulation (EU) 2026/1744 of 8 July 2026 amending Regulations (EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230 as regards the simplification of the implementation of harmonised rules on artificial intelligence (Digital Omnibus on AI),” _Official Journal of the European Union, OJ L, 2026/1744_, Jul. 24, 2026. [Online]. Available: #link("https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng")[https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng] (accessed Sep. 28, 2026).]
#ref-entry(5)[Publications Office of the European Union, “Regulation (EU) 2024/1689, consolidated text 02024R1689-20260727 (incorporating Regulation (EU) 2026/1744),” _EUR-Lex_, Jul. 27, 2026. [Online]. Available: #link("https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng")[https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng] (accessed Sep. 28, 2026).]
#ref-entry(6)[Colorado General Assembly, “SB26-189, Automated Decision-Making Technology,” May 14, 2026. [Online]. Available: #link("https://leg.colorado.gov/bills/sb26-189")[https://leg.colorado.gov/bills/sb26-189] (accessed Sep. 28, 2026).]
#ref-entry(7)[Anthropic, “Claude Sonnet 5.5 (model page),” _Claude Developer Platform documentation_, Sep. 28, 2026. [Online]. Available: #link("https://platform.claude.com/docs/en/models/sonnet-5-5/overview")[https://platform.claude.com/docs/en/models/sonnet-5-5/overview] (accessed Sep. 28, 2026).]
