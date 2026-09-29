# M1 grading round 5 (submission rendered 2026-09-29, commit f096854)

Same kit as round 4 (`tools/review_kit.py`): anonymised text, page images, milestone
description, derived rubric and the syllabus notes, now including the official course
outcomes. Fresh reviewers: three graders, the four judge personas of the brief, a
claim-to-source audit, a signed-part audit and a red team against the running demo app
(restarted on the round-5 code and models).

P = Problem definition (5), S = Stakeholders (3), A = AI/ML approach (5),
O = Scope/objectives/criteria (5), E = Ethics/risk/regulation (4), C = Clarity/references (3).

| Reviewer | P | S | A | O | E | C | Total /25 |
|---|---|---|---|---|---|---|---|
| Grader A (preliminary reader) | 4 | 2.5 | 4.5 | 4 | 3.5 | 2.5 | 21.0 |
| Grader B (strict instructor) | 3.5 | 2.5 | 4 | 3.5 | 3 | 2 | 18.5 |
| Grader C (calibrated TA) | 4 | 2.5 | 4.5 | 4.5 | 3.5 | 2.5 | 21.5 |
| Judge: course professor | 4 | 2.5 | 4.5 | 4 | 3.5 | 2.5 | 21.0 |
| Judge: audio-electronics engineer | 3.5 | 2.5 | 4 | 4 | 3.5 | 2.5 | 20.0 |
| Judge: ML PhD student | 4 | 2.5 | 4 | 3.5 | 3.5 | 2.5 | 20.0 |
| Judge: ethics and policy scholar | 4 | 2.5 | 4.5 | 4.5 | 3 | 2.5 | 21.0 |

**Minimum per line across the three graders: 3.5 + 2.5 + 4 + 3.5 + 3 + 2 = 18.5 / 25**
(round 4: 17.5). Graders 21.0, 18.5 and 21.5 (round 4: 21.0, 17.5, 22.0); the professor and
the ethics scholar rose to 21, the engineer and the ML PhD student stayed at 20. Signed-part audit: all four parts Full (Part 2 the shortest and most
exposed; Part 3 cites nothing). Nothing addressed to graders or models. Source audit: 52
cited statements, 46 supported, 4 partly, 2 overstated, none unsupported or unverifiable
(round 4: 41/2/2/1 of 47, plus 1 unverifiable).

## Themes (reviewers in brackets)

1. **Pass counts contradict the stated bound** [all graders, ML PhD, professor]. The
   caption names the exact bound; the printed counts (952 of 1,000, 924 of 1,000, at most
   49 of 500) come from a normal approximation. Exact counts would be 953, 926 and 47.
2. **Success defined two ways** [all graders, ML PhD, professor]. The summary said success
   "needs" every count; Part 3 judges each primary alone and prints a 6% joint chance.
3. **Bars pass only about 61% of the time by construction** [ML PhD]. With a test set
   barely larger than the pilot, a bar 1.5 pilot standard errors below the estimate is a
   coin toss, although simulated test units are cheap. T7's 70% is explained only through
   its pass count (circular) [all].
4. **Significance and needs still asserted** [all]. No sizing of shops, hours or money;
   effort units never converted to minutes; the fault-isolation premise rests on defence
   guidance; needs unvalidated until interviews; no schedule with fallbacks [professor].
5. **Realism of the simulation and baselines** [engineer, professor, ML PhD, grader B].
   Uniform fault catalog without leaky coupling capacitors or heater-to-cathode leakage;
   no unpowered checks (resistance, diode, in-circuit ESR); no healthy-channel comparison,
   the usual reference in stereo and multichannel gear; hardware only on the 24 V line
   driver; aged test units drawn from the training distribution.
6. **Risk register and ethics** [ethics, graders B and C, professor]. Several checks
   cannot fail (privacy "checked" by T15-T19, manuals by the terms of use, work
   intensification by interviews); the fatal-risk rule contradicts locks that act on typed
   readings; bias gets one sentence and "three voices" is undefined; no data-protection
   law; no named ethical framework; owners are functions, not leads; no project risks.
7. **Legal and factual points** [graders A and B, professor, ethics, source audit].
   Minnesota's repair law missing from "five other states"; "no U.S. AI statute covers
   such a tool" too absolute (Texas's AI act in force since January 2026); preemption
   stated without its "undue burden" scope; the self-employed claim cites a recordkeeping
   rule only; [20]'s 97.59% credited to the simulation loop alone; "mostly installs" an
   inference; "retrieves documents" too narrow for maintenance AI.
8. **Readability** [all]. Figure 1 prints at 4-6 pt; dense prose; terms used before
   definition ("group", "engine", "reader", "locks", "hazard map"); a bare "Part 1"
   cross-reference; the flag calibration described as a false-alarm budget on
   out-of-catalog units (it is set on single faults).

Claims checked and rebutted with data: the ML reviewer estimated that a perfectly
calibrated system would score 0.012-0.017 on T12 at 1,000 units. Resampling the pilot's
shown probabilities gives about 0.005 at 1,000 units and 0.002 at 5,000, so the 0.02 bar
is not at the noise floor; the floor is now reported (ADR-044).

## Red team (fixed in 06ae3f6)

One critical, two high, five medium and three low findings. The critical and high ones
share one cause: the offline chat's parsers for the three attestation gates accepted
questions, negations and conditionals ("if all points were at 0.5 V, could I unsolder?",
"the owner hasn't approved yet", "if I had a variac I would use it"), and the discharge
parser read durations, wattages and counts as volts. `differential/safety/attest.py` now
decides what free text may attest, for the offline chat and the live model's tool calls:
a plain affirmative statement, and for discharge only voltages with their units. Medium
and low: the trainee export leaked the withheld step; supervisor names such as "Nobody"
were accepted; screening missed leetspeak, spaced-out letters and some non-English
fuse-bypass requests; an empty photo gave a 500; a confirmed value the photo did not
show was labelled a photo reading; the state echoed a lapsed discharge check; the
agent's own example number was withheld. Each has a regression test (337 tests pass);
the safety sweep still covers every step. The structured API, path traversal, malformed
input, grounding, injection sanitising, photo-cannot-satisfy-discharge, pre-bring-up
gating, re-lock on power-up and a 200-request load test all held.

## Changes before the lock (round 6)

In the system and targets (ADR-044, committed c80b6ac):

1. Simulated test sets five times larger (5,000 single-fault, 5,000 aged, 2,500
   out-of-catalog); bars unchanged; each primary's chance of being met is now 81-88% and
   about one miss is expected.
2. Counts of units judged with the exact bound; pass counts and chances computed under it.
3. T7's 70% explained by what 60 faults can show (pass probabilities at 90, 85, 80 and 70%).
4. Reported without bars: high-voltage steps per diagnosis (pilot: engine 0.3, scripts
   1.5-1.9) and the calibration floor at the test size.
5. Checkpoint keys for evaluation cases fixed (a grown split could skip cases).

In the text: one success rule; the bound method per target; T7's rationale; a schedule
with fallbacks and a pre-registered S1 criterion; the healthy-channel comparison planned
as a reported baseline (not added before the lock: a fair version needs twin units
simulated on a shared supply); Minnesota, Texas's AI act and the preemption scope; the
OSH Act's definition of employer; [20] credited to its whole pipeline; Figure 1 at full
width; definitions before use; the practice paragraph with instruments and the limits of
simulation; aging bounds tied to end-of-life criteria; bias with named voices and an
interval rule; a named ethical framework (the moral crumple zone); register checks that
can fail and a project-risk row; owners by lead; terms of use instead of "license"; the FTC's action on
unsupported AI accuracy claims and California's bar on the "the AI did it" defense (AB 316); bench-practice
sources for the instruments and the healthy-channel comparison; the reference-list fixes the source audit
listed (EU dates and identifiers, the LEAD Act press release, LightGBM pages, name forms).

Not done, and stated as limits: leaky coupling capacitors and heater-to-cathode leakage
in the catalog, unpowered checks, hardware beyond the 24 V line driver.

## Needs the team

As in round 4: interviews and ticket coding (after an ethics-board determination),
timing one schematic transcription, building the fault boards, the outside adversarial
prompts, the live language-model runs (API key), and signing each part with real names.
