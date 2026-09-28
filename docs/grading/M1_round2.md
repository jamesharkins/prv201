# M1 grading round 2 (submission rendered 2026-09-28, commit 71580d9)

Same kit as round 1, built by `tools/review_kit.py`: anonymised text, page
images, milestone description, derived rubric, syllabus notes. Judge personas now
follow the brief exactly (course professor, audio-electronics engineer, ML PhD
student, ethics and policy scholar); round 1 had used an investor in place of the
ML PhD student. A claim-to-source audit and a signed-part audit ran alongside.

P = Problem definition (5), S = Stakeholders (3), A = AI/ML approach (5),
O = Scope/objectives/criteria (5), E = Ethics/risk/regulation (4), C = Clarity/references (3).

| Reviewer | P | S | A | O | E | C | Total /25 |
|---|---|---|---|---|---|---|---|
| Grader A (preliminary reader) | 4 | 2.5 | 4.5 | 4 | 3.5 | 2 | 20.5 |
| Grader B (strict instructor) | 3.5 | 2 | 4 | 3.5 | 3 | 2 | 18.0 |
| Grader C (calibrated TA) | 4 | 2.5 | 4.5 | 4 | 3.5 | 2.5 | 21.0 |
| Judge: course professor | 3.5 | 2.5 | 4 | 4 | 3 | 2 | 19.0 |
| Judge: audio-electronics engineer | 3.5 | 2.5 | 4 | 3.5 | 3 | 2.5 | 19.0 |
| Judge: ML PhD student | 4 | 2.5 | 4 | 3.5 | 3.5 | 2.5 | 20.0 |
| Judge: ethics and policy scholar | 4 | 2.5 | 4.5 | 4 | 3 | 2.5 | 20.5 |

**Minimum per line across the three graders: 3.5 + 2 + 4 + 3.5 + 3 + 2 = 18.0 / 25**
(round 1: 19.0; the graders are fresh each round and grader B was the strictest).
Signed-part audit: all four parts Full. Nothing addressed to graders or models.
Source audit: 43 cited statements, 35 supported, 5 partly, 3 overstated, 0 unsupported.

## Findings that changed the system, not only the text

1. **TP8 = 147 V was a simulator artifact** (all three graders, engineer, professor,
   ML PhD). A 1 GOhm plate-cathode resistor in the triode model formed a divider
   with the 1 GOhm "open" cathode resistor. Verified by simulation (134 V with the
   resistor, 6 V without; healthy readings unchanged). Fixed in
   `circuits/lib/devices.lib`; channel strip and triode re-simulated and retrained;
   hazard map re-audited (ADR-030).
2. **Test population** (graders A and C, ML PhD, professor): dropping whole faults
   that are symptomatic in fewer than half of units was not justified; their
   symptomatic units do reach a bench. Every set now samples symptomatic units
   uniformly, so faults appear in proportion to how often they cause a symptom
   (ADR-030).
3. **Pilot reuse** (ML PhD): the pilot had used the validation units that exposed the
   engine bug and tuned the groups. The pilot is now its own simulated split.
4. **Safety scope** (engineer, professor, ethics): in a chassis with a high-voltage
   supply every powered step now carries a live-chassis notice; scope steps carry a
   ground-clip warning; points that can exceed 50 V under a fault carry the same
   effort surcharge as normally high-voltage points.

## Text issues (grouped; reviewers in brackets)

- Executive summary: fee "just to evaluate" contradicts Part 1; "depends on
  experience" unsupported; four claims do not match the seven primary targets;
  effort claim attributed to the full system but T8 measures the engine; "never
  issues an unsafe step" overclaims [A, B, C, all judges, sources].
- Part 1 lacks its own problem statement; workforce trend unreconciled (growth
  projection vs retiring specialists); 2025-26 dates only in references; 50 V
  threshold uncited; trainee extrapolation from a chat-support study [parts, A, B,
  C, prof, ethics].
- Landscape omits non-AI bench tools (signature testers, fault dictionaries) and
  generic chat models [C, engineer, prof].
- Part 2 practice paragraph uncited; "no public dataset" presented without a
  search; simulated unit, fault kinds and hand-check tolerance undefined [parts, B,
  C, sources].
- Table 3: metrics and units missing for several bars (T6, T12, T13, T14, T16,
  T18-T21); T4 read as covering half-split, so its bar looked inconsistent with the
  1.5-SE rule; pilot values not shown per bar; group sizes not reported; zero-event
  and non-inferiority targets need proper intervals [all graders, ML PhD, prof].
- No target or plan measures a technician using the tool; explanations unchecked
  [prof, ethics, ML PhD].
- Part 4: LLM role contradiction ("never produces a reading" vs meter photos);
  SAE analogy via a GitHub ontology and with the wrong level count; "about 50
  dimensions"; discharge lock described as self-report; PLD personal injury and
  foreseeable use omitted; RISE Act learned-professional condition; no
  jurisdiction; accountability placed on the technician; register missing bias,
  accountability, misuse, model mismatch, explanations, IP [all].
- Appendices after the references carry content the body depends on (glossary,
  autonomy table) and Appendix B has wrong locations [all graders, prof, ethics].
- Sources: [19] authors and claim wording, [10] version, [8] "broader/mostly",
  [31] overstated, [43] RISE conditions, missing access dates, weak sources for
  SAE and capacitor ageing [sources, graders].

## What only people can supply (listed in SUBMISSION_GUIDE.md)

Technician interviews (diagnosis share, in-scope share of bench work), a timing
study, and a technician-in-the-loop study. The build cannot fabricate these; the
revised M1 states them as planned work with named measures.
