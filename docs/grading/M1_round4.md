# M1 grading round 4 (submission rendered 2026-09-29, commit 2fa4800)

Same kit as round 3 (`tools/review_kit.py`): anonymised text, page images, milestone
description, derived rubric and the syllabus notes as they stood before the official
syllabus arrived (the course outcomes were not yet in them; ADR-038). Fresh reviewers;
judge personas as in the brief; a claim-to-source audit, a signed-part audit and, for
the first time, a red team against the running demo app (brief section 9 E).

P = Problem definition (5), S = Stakeholders (3), A = AI/ML approach (5),
O = Scope/objectives/criteria (5), E = Ethics/risk/regulation (4), C = Clarity/references (3).

| Reviewer | P | S | A | O | E | C | Total /25 |
|---|---|---|---|---|---|---|---|
| Grader A (preliminary reader) | 4 | 2.5 | 4.5 | 4 | 3.5 | 2.5 | 21.0 |
| Grader B (strict instructor) | 3.5 | 2 | 3.5 | 3.5 | 3 | 2 | 17.5 |
| Grader C (calibrated TA) | 4 | 2.5 | 5 | 4 | 4 | 2.5 | 22.0 |
| Judge: course professor | 3.5 | 2.5 | 4 | 4 | 3.5 | 2.5 | 20.0 |
| Judge: audio-electronics engineer | 3.5 | 2.5 | 4.5 | 3.5 | 3.5 | 2.5 | 20.0 |
| Judge: ML PhD student | 3.5 | 2.5 | 4 | 4 | 3.5 | 2.5 | 20.0 |
| Judge: ethics and policy scholar | 3.5 | 2 | 4.5 | 4 | 3 | 2.5 | 19.5 |

**Minimum per line across the three graders: 3.5 + 2 + 3.5 + 3.5 + 3 + 2 = 17.5 / 25**
(round 3: 18.0). Two graders and every judge scored higher than in round 3; the strict
grader, who sets every minimum, went deeper. Signed-part audit: all four parts Full
(Part 2 borderline; Parts 1-2 about 55-60% of the length of Parts 3-4). Nothing
addressed to graders or models. Source audit: 47 cited statements, 41 supported (5 only
after a web check), 2 partly, 2 overstated, 1 unsupported, 1 unverifiable (round 3:
42/6/1/0 of 49).

## Themes (reviewers in brackets)

1. **Aged units are the bench population but only a secondary target** [all judges,
   graders B and C]. The pilot's aged-unit accuracy (66.7%, a 25.8-point drop) was not
   printed; the engine is trained on as-new tolerances only.
2. **Fault behaviour unvalidated; hardware covers only the line driver** [engineer, ML
   PhD, professor]. The 22/22 hand checks are healthy bias points; one close look at a
   fault found an artifact. No tube or high-voltage hardware check.
3. **Wording beyond the evidence** [all]. "Failed part" where the target scores its
   ambiguity group; "an expert's probing effort" for a scripted half-split procedure;
   "honest probabilities" for calibration on simulated units; "never supplies a
   reading" beside meter-photo proposals; "chat models have no safety rules".
4. **Numbers that do not reconcile on the page** [all]. 93.8 - 92.1 printed as 1.8;
   T4's +10 for a 10.5-point margin; T9's 0.32x (weighted over all circuits) beside
   channel-strip efforts giving 0.29x; T7's 70% beside 49/60 unexplained; Table 2's
   block sums versus the channel strip; "all methods stop at 90% belief" including the
   language model; T5 and T7 bars with no stated origin; no rule for how the primaries
   combine (about a 22% joint chance if independent).
5. **Effort accounting favours the engine** [engineer, professor, ML PhD]. The scripts
   pay for unsoldering their leading suspect; the engine's mean effort (6.7) is below
   one unsoldering test, so it rarely pays for a confirming step.
6. **Significance and stakeholder needs still asserted** [all]. No audio-specific
   diagnosis-time evidence, market size, current labour data or interviews; the
   scarcity claim rests on an enthusiast site called a "trade report".
7. **Ethics gaps** [ethics, professor, graders B and C]. No stated jurisdiction;
   privacy and IP get no rows; responsibility split by role rather than by failure mode
   and legal route; residual ratings with no acceptance rule and no "fatal" level;
   labour effects beyond deskilling; fairness with no groups, sizes or disparity
   measure; the planted-error consent wording; NIST conformance overstated.
8. **Bench safety practice** [engineer]. No bring-up on a variac or dim-bulb tester, no
   CAT-rated meter requirement, no warning that a discharged capacitor recovers voltage
   (dielectric absorption), no clip-leads-with-power-off rule.
9. **Readability** [all]. The secondary-target paragraph is nearly unparseable; dense
   prose; Table 2 headers cryptic; weak or indirect sources for instruments (third-party
   copies), a bill (a press release), electrolytic ageing (course slides).

## Red team (fixed in a136fb9)

One critical finding (trainee mode's supervisor gate was only on screen; high-voltage
readings could be recorded unsupervised), three high (a refusal in chat recorded owner
approval; the approval-to-discharge step returned a 500 on every high-voltage circuit;
NaN in a request body gave a 500), five medium (names on the ticket carried numbers and
injected text; the export leaked the hidden fault; five screening evasions; "0.35 kV"
typed in chat was read as 0.35 V and verified a discharge; duplicate point keys let a
safe reading overwrite a charged one) and one low (comma decimals). Every finding is
fixed with a regression test. The defences that held are listed in the red-team
report: most unsafe requests refused, the per-point discharge lock and re-lock,
grounding in chat, photo confirmation, path traversal, malformed input and a 120-request
concurrency test.

## Changes before the lock (round 5)

The targets are still unlocked, so these go into the system and the target design:

1. **Ageing in training and an aged primary target.** Training and validation units
   mix as-new and aged parts; aged pilot and test sets cover every circuit; T6 becomes a
   primary target on aged units' top-1 accuracy.
2. **Fault-signature audit.** A random sample of catalogued faults across every block is
   checked against hand analysis, and the agreement is reported with its interval.
3. **Effort to a confirmed answer.** Probing and unsoldering effort are reported
   separately, and every method's effort is also reported with one confirming test
   charged to its answer.
4. **Bench practice in the safety layer.** Bring-up on a variac or dim-bulb tester,
   CAT-rated meters, dielectric absorption (re-check or bleeder right before contact)
   and clip leads attached with power off, each checked by the sweep.
5. **Text.** Every wording and number above corrected; the aged result, the joint chance
   of the primaries and the origin of the T5 and T7 bars stated; a jurisdiction,
   privacy and IP rows, a fatal level with an acceptance rule, a labour-impact row, a
   responsibility-by-failure-mode statement, a concrete interview plan; primary sources
   for instruments, laws and electrolytic ageing; the secondary targets laid out so they
   can be read.

## Needs the team

Interviews and ticket coding (with an ethics-board determination first), timing one
schematic transcription, building the fault boards, the outside adversarial prompts,
the live language-model runs (API key), and signing each part with real names.
