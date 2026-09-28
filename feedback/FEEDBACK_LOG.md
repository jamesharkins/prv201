# Feedback log

Every piece of feedback the project receives, what we changed, and where. Sources:
**R1** = structured review of the M1 draft (AI-assisted: three rubric-based reads,
four reviewer perspectives - instructor, repair engineer, industrial-AI investor,
AI-ethics scholar - and a claim-to-source audit; details in `docs/GRADING_LOG.md`).
Instructor and peer feedback will be added here with its date when received.

| # | Source | Feedback | Response | Where | Status |
|---|---|---|---|---|---|
| 1 | R1 | Headline claim not tested by the targets (effort vs. superiority; LLM effort) | Claim restated to match targets; superiority margins over scripted and random probing (T4) and over an LLM alone (T5) added | M1 exec summary, Table 3 | Done |
| 2 | R1 | LLM-only baseline undefined | Protocol fixed: same complaint, parts list, voltage chart, fault list, readings on request, budget; plus an LLM-with-simulator variant | M1 Part 3; `eval/llm_baseline.py`; ADR-023 | Done (runs need a key) |
| 3 | R1 | Test-case generation unstated (latent faults, complaint generator) | Stated: symptomatic faults only, redraw until a symptom shows, three writer voices, label-leakage check, held-out paraphrase bank | M1 Part 3 | Done |
| 4 | R1 | Simulation-only evaluation; no hardware target | Tolerance stress set (T6) and fault-board target (T7) added; fault-board package built | M1 Tables 2-3; `hardware/fault_board/` | Done (T7 needs hardware) |
| 5 | R1 | OSHA rule misread (energised testing exception) | Corrected with the verified 1910.333(a)(1) Note 2 and 1910.333(c)(2) text | M1 Part 1 decision | Done |
| 6 | R1 | Hazard classification by normal-operation voltage only | Worst-case voltage audit over all simulated faults; hands-off and discharge instructions; unsoldering lock | M1 Part 4; `eval/hv_audit.py`; ADR-020 | Done |
| 7 | R1 | Revised EU PLD said to apply "now" | Corrected: applies to products placed on the market after 9 Dec 2026; professional-property exclusion noted | M1 Part 4 | Done |
| 8 | R1 | "Not high-risk" under the AI Act unargued | Argued from Art. 6(1)/Annex I and Annex III; intended use excludes evaluating workers | M1 Part 4 | Done |
| 9 | R1 | LLM weakness argued from 2024-25 textbook benchmarks | Updated with Razavi-Bench (Sept 2026, top model 95.50%); argument now rests on tolerance, cost, look-alike faults and safety, tested by T5 | M1 Part 1, App. A | Done |
| 10 | R1 | Circuit model for a real unit unaddressed | What a unit needs is stated; documented units only; M2 times one transcription | M1 Part 2 | Partly (timing in M2) |
| 11 | R1 | Fixed-order baseline a straw man | Half-split tracing baseline (T9) | M1 Part 3; ADR-021 | Done |
| 12 | R1 | Effort weights unsourced | Stated as estimates; sensitivity with weights halved/doubled; timing on the fault board in M2 | M1 Part 3 | Partly (timing in M2) |
| 13 | R1 | T6 calibration nearly a one-bin test | Calibration after every step (T12) | M1 Table 3 | Done |
| 14 | R1 | Recap-bias target circular | Replaced by folklore-prior robustness (T14); capacitor share reported as analysis | M1 Table 3 | Done |
| 15 | R1 | 0 unsafe in 40 prompts proves little | Exhaustive safety sweep over every possible recommendation (T15); red-team bound stated (T16) | M1 Table 3 | Done |
| 16 | R1 | Risk register overclaims; missing risks | Rebuilt with measured controls, NIST function per row; no-circuit-model, deskilling, privacy, model change added | M1 Table 5 | Done |
| 17 | R1 | Unsupported premises (diagnosis share of cost, vinyl proxy, BLS scope) | Softened; closer occupation (SOC 49-2097) cited; vinyl removed | M1 Part 1 | Done |
| 18 | R1 | Jargon for a mixed audience | Plain-language glossary, figure caption key, plain-words target table | M1 App. C | Done |
| 19 | R1 | Coverage map claimed unsupported uses | Each row now points to where the document delivers it, with depth | M1 App. B | Done |
| 20 | R1 | Market sizing, buyer, price model | Buyer named (shop owner); sizing needs technician interviews - planned, not claimed | M1 Part 1; SUBMISSION_GUIDE | Open |
| 21 | R1 | Technician input on practice and needs | Planned interviews and timing study (team action) | SUBMISSION_GUIDE | Open |
| 22 | R1 | Competitors: signature analysers, ticket-trained field-service AI | Field-service AI (Microsoft, PTC) added; signature analysers not yet sourced | M1 Part 1 | Partly |
