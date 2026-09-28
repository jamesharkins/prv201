# M1 grading round 1 (submission rendered 2026-09-28, commit 728fd18)

Reviewers read only the anonymised text (`M1.sanitized.txt`), page images, the
derived rubric and the syllabus notes. Scores per rubric line:
P = Problem definition (5), S = Stakeholders (3), A = AI/ML approach (5),
O = Scope/objectives/criteria (5), E = Ethics/risk/regulation (4), C = Clarity/references (3).

| Reviewer | P | S | A | O | E | C | Total /25 |
|---|---|---|---|---|---|---|---|
| Grader A (preliminary reader) | 3.5 | 2.5 | 4 | 3.5 | 3 | 2.5 | 19.0 |
| Grader B (strict instructor) | 4 | 2.5 | 4 | 3.5 | 3 | 2.5 | 19.5 |
| Grader C (calibrated) | 4.5 | 2.5 | 5 | 4 | 3.5 | 3 | 22.5 |
| Judge: course instructor | 4 | 2.5 | 4.5 | 4 | 3.5 | 2.5 | 21.0 |
| Judge: audio repair engineer | 4 | 2.5 | 4.5 | 4 | 3 | 2.5 | 20.5 |
| Judge: industrial-AI investor | 3.5 | 2 | 4.5 | 4 | 3.5 | 2.5 | 20 |
| Judge: AI ethics scholar | 4.5 | 2.5 | 4.5 | 4.5 | 3 | 2.5 | 21.5 |

**Minimum per line across the three graders: 3.5 + 2.5 + 4 + 3.5 + 3 + 2.5 = 19.0 / 25.**

All reviewers: every signed part Full; nothing addressed to a grader or
model; page limit met.

## Issues raised (grouped; reviewer initials in brackets)

1. Headline claim does not match the locked targets: T4/T5 test the engine
   (uniform prior) for non-inferiority, not the hybrid's superiority; no target
   compares effort with the LLM; T10 needs an API key [B, C, Inv].
2. LLM-only baseline protocol undefined (model, inputs, interactive or not,
   budget, strata); make it fair: same schematic, test points, budget and
   simulated readings [B, C, Inv].
3. Test-case generation unstated: fault sampling distribution, latent faults,
   complaint generator [B, C, Inv].
4. Evaluation is simulation-only; no hardware (fault-board) target; no
   out-of-distribution stress set; sim-to-real impact under-rated (should be H)
   [B, C, Inv].
5. Risk-register caption overclaims ("every risk ... measurable control");
   missing risks: no circuit model for the customer's unit (H/H), deskilling,
   over-trust, unqualified users; privacy claim ("no telemetry") conflicts with
   cloud LLM calls; no deployment jurisdiction; EU-only liability [B, C, Inv].
6. The unit's circuit model: the gap is framed as "undocumented" gear but the
   engine needs a netlist; say how a real unit gets modelled [B, Inv].
7. "4 of 23 test points above 50 V" does not support "a consumer tool would have
   to refuse most useful measurements"; argue from powered-chassis exposure and
   OSHA qualified-person rules instead [B, C, Inv].
8. Unsupported premises: "most of what a repair costs is diagnosis"; LLMs say
   "just recap it" (asserted); vinyl revenue as installed-base proxy; BLS
   category is mostly non-audio; Brynjolfsson gains were for novices [B, C, Inv].
9. "120 of 250 faults latent, so a symptom rarely points at one part" does not
   follow; use faults-per-symptom instead; latent faults never reach a bench [B, Inv].
10. Recap bias (T15): capacitors genuinely age; the reference share is set by
    the team's own sampling; state this and consider realistic failure rates [B, Inv].
11. Effort cost units unsourced; add a sensitivity analysis; O2's "today's
    practice" is a scripted baseline, rename it [B, C, Inv].
12. Table 3: add Objective and System columns; define set sizes (paraphrase set,
    synthetic photos), engine variant, pass rule (point estimate vs CI bound);
    T4 looser than the pilot; pilot sample size missing; T6 is almost a one-bin
    test; T8 with 40 cases cannot support "never" (upper bound about 7%) [B, C].
13. Regulatory accuracy: revised PLD applies to products placed on the market
    after 9 Dec 2026 ("now" is wrong); "not high-risk" unargued; OSHA
    1910.333/1910.334 qualified-person basis for live testing [B, C, Inv].
14. Alternatives incomplete (Table 4): retrieval over service documents, LLM
    calling the simulator (as in [19]), consistency-based diagnosis, post-2000
    analog fault-diagnosis ML; explain how boosted trees give likelihoods [B, Inv].
15. Competition: today's free toolkit (voltage chart, forums, comparing with the
    healthy channel), chat models with vision given the schematic, signature
    analysers (Huntron/ABI), ticket-trained field-service AI; state the moat [Inv].
16. Market sizing / buyer / price model absent; adjacent markets (guitar amps,
    rental/broadcast maintenance, industrial repair depots, a fault-finding trainer) [Inv].
17. Presentation: nested parentheses in Table 3; Table 4 caption "each fills one
    role" inaccurate; exec summary "rather than in a prompt" vs decision "both";
    jargon undefined (B+, Baxandall, 12AX7, AUROC, micro-F1, latent); build-process
    wording ("this build", "build day"); missing access dates on canonical URLs;
    [19] has no authors [B, C, Inv].
18. Course coverage map claims uses not shown in the body (L0-L4 autonomy, CI,
    label-leakage checks, automated test fixtures vs "autonomous probing" out of scope) [B].
19. Spot-check [11] (17.7% vinyl vs headline 6.9%) and [19] (97.59%) [B].

### Audio repair engineer (additional technical points)

20. OSHA 1910.333(a)(1) is misread: de-energising is required unless infeasible,
    and its Note 2 names testing that can only be done energised; guarding is an
    installation rule (1910.303). Live testing is legitimate for qualified persons
    using safe work practices; supporting those practices is the design duty.
21. High-voltage classification uses normal-operation voltages; a faulted unit can
    put B+ on other nodes (leaky coupling cap, cut-off tube). Classify every test
    point by its worst case across the simulated fault catalog.
22. Stored energy under-treated: discharge through a resistor tool, verify, recheck
    (dielectric absorption), bleeders fail open; hands-off measurement (clip on
    with power off, power on, read, power off). Replace repeated warnings with an
    interlock: no "lift part" step until a verified near-zero filter-cap reading.
23. Cost model: setup and access dominate real bench time; a DC sweep of the whole
    voltage chart takes minutes; add batch DC entry. Missing actions: visual/smell
    inspection, tube substitution, in-circuit ESR, powered-off resistance checks,
    comparison with the good channel.
24. Fixed-order baseline is a straw man; competent technicians inspect, swap tubes,
    compare channels and half-split the signal path. Add a half-split baseline.
25. Cascades are the norm (the victim vs the cause); no power stage in the circuits,
    so the market claim is wider than the circuits built; dead / fuse-blowing units
    start on the mains side (excluded).
26. Tolerances: mains now 120-125 V on gear designed for 110-117 V; tube spread;
    DMM loading on high-impedance nodes; the good channel as a reference.
27. T15 is circular (and implied by T1 for the full system); T7 needs an operating
    point; T12 must score range, unit and AC/DC mode, not just digits; missing
    shop metrics: good parts replaced unnecessarily, false alarms on healthy units.
28. Most valuable next product per the judge: a library of pre-modelled units and
    a trainee simulator; state the cost of getting a unit into the system.

## Claim-to-source audit (24 cited sentences)

Supported 10, partly supported 7, overstated 6, not supported 1.
Most serious: (a) OSHA legal effect overstated (see 20); (b) the LLM-alone case
rests on 2024-25 textbook benchmarks and omits `razavi_bench_2026` (top Sept-2026
models 95.5% on textbook questions); the 97.59% result came from a vision detector
plus a simulation loop on a different problem set; (c) revised PLD applies only to
products placed on the market after 9 Dec 2026. Also: rate cards generalised from
three shops; vinyl-to-installed-base link is inference; maintenance-AI products
described as retrieval only (IBM plans tasks; Siemens predictive); [28, 29] have no
recorded content quotes (cite Pattipati & Alexandridis / Bandler & Salama for
measurement selection); Gender Shades audited commercial gender classifiers;
OWASP ranks prompt injection overall (LLM01), not indirect injection specifically;
"not high-risk" needs the Annex III basis; NY date needs `ny_ag_repair_2024`;
Texas "latest of several laws" unsupported as cited; reference fixes for [7] (stable
archive URL), [20] (corpus date), [24] (date), [32] (apostrophe), [35] (Core section).

### Grader A, instructor and ethics judge (additional points)

29. A: the appendices read as padding; Appendix B claims features the body never
    describes; Figure 1 and Tables 1, 2, 5, 6 are never cited in the text; the
    executive summary has no numbers.
30. A: T8/T9 on the offline agent are close to met by construction; report how
    often the grounding check had to block a number; define "unsafe" with a rubric.
31. A/Instructor: add an "LLM + simulator tool" rival (the approach behind [19]) to
    Table 4 and to the tested systems; retrieval over service manuals too.
32. Instructor: plain-language rewrite for a mixed class: glossary, figure key,
    "in plain words" column for Table 3, define cost units before Table 3,
    intuitive sentences for Bayesian belief and information gain.
33. Instructor: coverage-map rows must link to where the body delivers them
    (core/supporting/stretch); Week 9 needs a people-focused test (e.g. symptom
    extraction for lay and non-native writers); autonomy levels need a body table.
34. Ethics: AI Act argument in three steps (scope Art. 2; Art. 6(1)/Annex I;
    Annex III incl. 4(b) worker evaluation and 3(b) grading trainees) plus an
    intended-purpose statement; Art. 50(1) "obvious" exception and Art. 50(2)
    marking; PLD nuances (professional-property exclusion; human confirmation is
    no shield); NIST AI RMF first mapping with release gates; AI 600-1 profile.
35. Ethics: register needs defined scales, residual ratings, role owners, and rows
    for automation bias, deskilling, injection per channel, prior
    misspecification, worker monitoring, evidence-trail integrity, post-repair
    safety, model drift, overclaiming; data inventory and redaction for live mode;
    offline tier quality vs paying for the API (report T1 by tier).
36. Ethics: EU repair directive only limits the obligation to repair to Annex II;
    copyright exposure is about copying manuals into a corpus / sending them to an
    API, not about netlists.
