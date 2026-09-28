# Feedback log

Every piece of feedback the project receives, what we changed, and where. Sources:
**R1** = structured review of the M1 draft (AI-assisted: three rubric-based reads,
four reviewer perspectives - instructor, repair engineer, industrial-AI investor,
AI-ethics scholar - and a claim-to-source audit; details in `docs/GRADING_LOG.md`).
**R2** = the second round, with the reviewer perspectives of the brief (course professor,
audio-electronics engineer, ML PhD student, ethics scholar). Instructor and peer feedback will be
added here with its date when received. *Triage*: accepted, accepted but needing
the team (people, hardware or a key), or declined with a reason. *Commit*: where the
change landed (later refinements are in the commits that follow).

| # | Source | Feedback | Triage | Response | Where | Status | Commit |
|---|---|---|---|---|---|---|---|
| 1 | R1 | Headline claim not tested by the targets (effort vs. superiority; LLM effort) | Accepted | Claim restated to match targets; superiority margins over scripted and random probing (T4) and over an LLM alone (T5) added | M1 exec summary, Table 3 | Done | 81f13ed |
| 2 | R1 | LLM-only baseline undefined | Accepted | Protocol fixed: same complaint, parts list, voltage chart, fault list, readings on request, budget; plus an LLM-with-simulator variant | M1 Part 3; `eval/llm_baseline.py`; ADR-023 | Done (runs need a key) | 81f13ed |
| 3 | R1 | Test-case generation unstated (latent faults, complaint generator) | Accepted | Stated: symptomatic faults only, redraw until a symptom shows, three writer voices, label-leakage check, held-out paraphrase bank | M1 Part 3 | Done | 81f13ed |
| 4 | R1 | Simulation-only evaluation; no hardware target | Accepted | Tolerance stress set (T6) and fault-board target (T7) added; fault-board package built | M1 Tables 2-3; `hardware/fault_board/` | Done (T7 needs hardware) | 81f13ed |
| 5 | R1 | OSHA rule misread (energised testing exception) | Accepted | Corrected with the verified 1910.333(a)(1) Note 2 and 1910.333(c)(2) text | M1 Part 1 decision | Done | 81f13ed |
| 6 | R1 | Hazard classification by normal-operation voltage only | Accepted | Worst-case voltage audit over all simulated faults; hands-off and discharge instructions; unsoldering lock | M1 Part 4; `eval/hv_audit.py`; ADR-020 | Done | 81f13ed |
| 7 | R1 | Revised EU PLD said to apply "now" | Accepted | Corrected: applies to products placed on the market after 9 Dec 2026; professional-property exclusion noted | M1 Part 4 | Done | 81f13ed |
| 8 | R1 | "Not high-risk" under the AI Act unargued | Accepted | Argued from Art. 6(1)/Annex I and Annex III; intended use excludes evaluating workers | M1 Part 4 | Done | 81f13ed |
| 9 | R1 | LLM weakness argued from 2024-25 textbook benchmarks | Accepted | Updated with Razavi-Bench (Sept 2026, top model 95.50%); argument now rests on tolerance, cost, look-alike faults and safety, tested by T5 | M1 Part 1, App. A | Done | 81f13ed |
| 10 | R1 | Circuit model for a real unit unaddressed | Accepted; needs the team | What a unit needs is stated; documented units only; one transcription will be timed (team action) | M1 Part 2; SUBMISSION_GUIDE | Partly (timing needs the team) | 81f13ed |
| 11 | R1 | Fixed-order baseline a straw man | Accepted | Half-split tracing baseline (T9) | M1 Part 3; ADR-021 | Done | 81f13ed |
| 12 | R1 | Effort weights unsourced | Accepted; needs the team | Stated as estimates; each weight (scope, unsoldering, high-voltage) halved and doubled in every effort comparison; timing on the fault board (team action) | M1 Part 3; `eval/harness.py` | Partly (timing needs the board) | 81f13ed |
| 13 | R1 | T6 calibration nearly a one-bin test | Accepted | Calibration after every step (T12) | M1 Table 3 | Done | 81f13ed |
| 14 | R1 | Recap-bias target circular | Accepted | Replaced by folklore-prior robustness (T14); capacitor share reported as analysis | M1 Table 3 | Done | 81f13ed |
| 15 | R1 | 0 unsafe in 40 prompts proves little | Accepted | Exhaustive safety sweep over every possible recommendation (T15); red-team bound stated (T16) | M1 Table 3 | Done | 81f13ed |
| 16 | R1 | Risk register overclaims; missing risks | Accepted | Rebuilt with measured controls, NIST function per row; no-circuit-model, deskilling, privacy, model change added | M1 Table 5 | Done | 81f13ed |
| 17 | R1 | Unsupported premises (diagnosis share of cost, vinyl proxy, BLS scope) | Accepted | Softened; closer occupation (SOC 49-2097) cited; vinyl removed | M1 Part 1 | Done | 81f13ed |
| 18 | R1 | Jargon for a mixed audience | Accepted | Plain-language glossary, figure caption key, plain-words target table | M1 App. C | Done | 81f13ed |
| 19 | R1 | Coverage map claimed unsupported uses | Accepted | Each row now points to where the document delivers it, with depth | M1 App. B | Done | 81f13ed |
| 20 | R1 | Market sizing, buyer, price model | Accepted; needs the team | Buyer named (shop owner); sizing needs technician interviews - planned, not claimed | M1 Part 1; SUBMISSION_GUIDE | Open | 81f13ed |
| 21 | R1 | Technician input on practice and needs | Accepted; needs the team | Planned interviews and timing study (team action) | SUBMISSION_GUIDE | Open | 81f13ed |
| 22 | R1 | Competitors: signature analysers, ticket-trained field-service AI | Accepted; needs the team | Field-service AI (Microsoft, PTC, Siemens, IBM, iFixit) added; power-off signature testers named as a bench alternative, not yet sourced | M1 Part 1 | Partly | 81f13ed |
| 23 | R2 | TP8 "147 V under an open cathode resistor" is physically implausible | Accepted | Confirmed as a simulator artifact (1 GOhm plate-cathode resistor in the tube model); removed, affected circuits re-simulated and retrained, hazard map re-audited; the example is now chosen by the audit | `circuits/lib/devices.lib`; ADR-030; M1 Part 4 | Done | ad08a1f |
| 24 | R2 | Dropping faults symptomatic in under half of units biases the test set | Accepted | Every set now samples symptomatic units uniformly (faults weighted by how often they cause a symptom) | `eval/cases.py`; ADR-030; M1 Part 3 | Done | ad08a1f |
| 25 | R2 | Pilot reused the validation units that exposed the bug and tuned the groups | Accepted | Pilot is its own simulated split, used for nothing else | ADR-030; M1 Part 3 | Done | ad08a1f |
| 26 | R2 | T4 bar looked inconsistent with the 1.5-SE rule; several bars lacked a metric or unit | Accepted | Table 3 states each metric precisely and shows the pilot estimate next to each bar; T4's baselines named | M1 Table 3 | Done | ad08a1f |
| 27 | R2 | Safety works per test point; discharge lock read as self-report | Accepted | Live-chassis notice on every powered step in a high-voltage chassis; scope ground-clip warning; lock opens only on an entered reading below the threshold; fault-conditioned hazards carry the effort surcharge | `differential/safety/`, `differential/agent/tools.py`; ADR-030; M1 Part 4 | Done | ad08a1f |
| 28 | R2 | Accountability placed on the technician; PLD, RISE Act, AI Act framing; no jurisdiction | Accepted | Responsibility allocated (team, shop, technician); EU law as benchmark; RISE Act condition quoted; Art. 6(1) and Art. 50 stated as written | M1 Part 4 | Done | ad08a1f |
| 29 | R2 | Risk register incomplete (misuse, model mismatch, explanations, bias, liability, IP) | Accepted | Six rows added | M1 Table 5 | Done | ad08a1f |
| 30 | R2 | No target measures a technician using the tool; explanations unchecked | Accepted; needs the team | Technician study (planted wrong recommendation, time to correct part) planned, not locked; explanation audit planned | M1 Parts 3, 4; SUBMISSION_GUIDE | Planned | ad08a1f |
| 31 | R2 | Photos sent with metadata in live mode | Accepted | Photos re-encoded without metadata before upload (tested) | `differential/vision/__init__.py` | Done | ad08a1f |
| 32 | R2 | Appendices carry content the body depends on; Figure 1 text too small; cross-references by number | Accepted | Glossary and autonomy table folded into the body; figure redrawn at print size; parts cross-referenced by title | M1 | Done | ad08a1f |
| 33 | R2 | Significance not sized; stakeholder needs not evidenced | Accepted; needs the team | Needs a technician survey and interviews (team action); stated as unknown in the text | SUBMISSION_GUIDE | Open | ad08a1f |
| 34 | R2 | LLM-alone comparison underpowered at 150 units | Accepted | Subset doubled to 300 paired units | `eval/llm_baseline.py`; targets | Done | ad08a1f |
