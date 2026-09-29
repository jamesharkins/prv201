# M1 grading round 6, the last (submission rendered 2026-09-29, commit d3bf2f2)

Same kit as rounds 4 and 5 (`tools/review_kit.py`): anonymised text, page images, milestone
description, derived rubric and the syllabus notes. Fresh reviewers: three graders, the four
judge personas of the brief, a claim-to-source audit, a signed-part audit and a red team
against the running demo app (round-5 code, with the round-5 fixes).

P = Problem definition (5), S = Stakeholders (3), A = AI/ML approach (5),
O = Scope/objectives/criteria (5), E = Ethics/risk/regulation (4), C = Clarity/references (3).

| Reviewer | P | S | A | O | E | C | Total /25 |
|---|---|---|---|---|---|---|---|
| Grader A (preliminary reader) | 4 | 2.5 | 4.5 | 4.5 | 3.5 | 2.5 | 21.5 |
| Grader B (strict instructor) | 3.5 | 2 | 4 | 3.5 | 3 | 2 | 18.0 |
| Grader C (calibrated TA) | 4 | 2.5 | 4.5 | 4.5 | 3.5 | 2.5 | 21.5 |
| Judge: course professor | 4 | 2.5 | 4.5 | 4 | 3.5 | 2.5 | 21.0 |
| Judge: audio-electronics engineer | 3.5 | 2.5 | 4.5 | 3.5 | 3 | 2.5 | 19.5 |
| Judge: ML PhD student | 4 | 2.5 | 4.5 | 4 | 3.5 | 2.5 | 21.0 |
| Judge: ethics and policy scholar | 4 | 2.5 | 4.5 | 4 | 3 | 2.5 | 20.5 |

**Minimum per line across the three graders: 3.5 + 2 + 4 + 3.5 + 3 + 2 = 18.0 / 25**
(round 5: 18.5). Graders 21.5, 18.0 and 21.5 (round 5: 21.0, 18.5, 21.5). The drop is one
half point on Stakeholders from grader B: the needs are the team's reading, not evidence, and
the survey of current AI tools is a list rather than an analysis. Judges: the professor 21
(21), the engineer 19.5 (20), the ML PhD student 21 (20), the ethics scholar 20.5 (21).
Signed-part audit: all four parts Full (Part 2 the shortest, at 0.69 of Part 3; Part 3 shows
11 of the 23 targets and cites nothing). All three graders found nothing addressed to graders
or models, in the visible text, hidden characters or wording. Source audit: 62 cited
statements, 59 supported, 3 partly, none overstated, unsupported or unverifiable (round 5:
46/4/2/0 of 52); for 7 of the 59 the recorded quote alone does not carry the claim, which held
only on the source itself.

## Themes (reviewers in brackets)

1. **Significance borrowed, not sized** [all graders, all judges]. The premise that fault
   isolation dominates repair time comes from defense maintenance guidance [1]; the cost
   evidence is shop price pages; the workforce figures are adjacent occupations from
   different years; the decline rests on press anecdotes. No estimate of units, hours or
   dollars, and the niche where the tool pays (consoles of identical channels) is never
   sized. The console maintenance engineer, the user in that niche, was missing from the
   interviews [professor, engineer, part audit].
2. **Needs assumed; the AI landscape a list** [grader B; all]. Every need is "our reading";
   the interview plan is small and recruited by convenience; the tool survey says nothing of
   evidence, adoption or investment, and the "best chat model" is unnamed.
3. **Targets softer than their own rule** [grader B, ML PhD, part audit]. T4 used one bar,
   the smallest of three, for every baseline, and its margins were unlabeled; standard errors
   and the rounding direction were not given, so T6 and T13 looked rounded in the system's
   favor (the pilot is weighted, which plain binomial errors ignore); O5 had no visible
   target, and T18 and T19 decided whether to keep the language model without being defined.
4. **Simulation grading simulation** [engineer, ML PhD, professor]. Ten of the eleven primary
   targets and gates are simulation or software checks; the only hardware is the 24 V line
   driver; the healthy-channel comparison has no bar; the fault prior is not stated; no
   model-error term; the effort units omit unpowered checks.
5. **Outcomes that matter ethically without a bar** [ethics scholar, ML PhD]. Powered readings
   at points above 50 V ("no bar"), over-reliance in S1 ("without a bar") and the gap between
   complaint voices were reported but not pre-registered with a rule.
6. **Privacy, consent and the register** [grader B, ethics scholar, professor]. Privacy gets
   two table cells; ticket consent covered technicians, not the customers the tickets
   describe; no data-protection law; the fatal-risk "After" rating rested on unverified
   qualification; some checks did not match their risk (T12 for invented readings), "Ticket
   test" and "Metadata test" are undefined, and fairness has no row.
7. **Bench safety** [engineer]. The hazard map covers single catalog faults only, so a
   double fault or solder bridge could put B+ on a point it calls safe; bleeders fail and
   dielectric absorption recharges capacitors; "off" is not unplugged; scope ground clips and
   hot chassis are the usual incidents; NFPA 70E, safety-marked parts and the post-repair
   leakage check are missing.
8. **Legal precision** [grader B, ethics scholar]. No pinpoints for the AI Act's high-risk
   annex or Article 50's exception; Colorado cited to a bill page; regulation split between
   Parts 1 and 4 without a cross-reference.
9. **Unreconciled numbers** [graders A and B, ML PhD]. "91.8% against 94.3%" matched neither
   pilot figure; "(5.2% flagged, 1.6% misnamed)" sat on the 2.4-point cost of aging, not on
   the aged miss rate; a phrase bank "not developed on" whose score "was seen once"; T7's
   98.5% printed as 98%; "all 491 checks" and "253,000 units" unexplained.
10. **Readability and references** [all]. Prose too compressed; a key sentence split around
    Table 3; terms used before definition; weak sources for load-bearing claims (a leaderboard
    README, a lecture's source files, a 1996 FAQ); missing access dates on web legal texts.

## Red team (fixed in 80f776e, ADR-045)

Three critical, one high, two medium and three low findings. The critical and high ones share
one cause, the third round running: the parsers that read the three safety attestations from
free text accepted hearsay ("the previous tech told me he brought it up on a variac"), quoted
text, a statement followed by "(I made these up)", sarcasm, and the tool's own instruction
("all points below 2 V") read as a 2.0 V reading; in live mode the discharge guard matched
values without their test points, so one reading stood for every high-voltage point. Rules for
"plain affirmative statements" cannot tell a record from a report of one, so the records
(bring-up, the owner's approval, discharge readings, a trainee's supervisor) are now made only
through the app's forms: the offline chat answers with the form to use, the live model has no
tool for them and any call is refused, a discharge record needs a reading at every point that
can hold high voltage, and 2.0 V counts as still charged. Medium and low: spaced letters across
words and foil fuse defeats passed screening; the hidden fault could be revealed at any time
(now only after the diagnosis stops or with an explicit end of the session, never early for a
trainee); natural approval phrasings were refused (moot now that approval is a button); a
timestamp's seconds were withheld by the grounding check. Each has a regression test; the
safety sweep covers all 491 checks. Structured endpoints, path traversal, malformed input,
uploads, grounding, injection sanitizing, the discharge state machine and a 200-request load
test all held.

## Changes before the lock

In the targets (ADR-046, 50cfffb; ADR-047):

1. A bar per part: T4 needs +10, +8 and +4 points over the chart, half-split tracing and
   random probing; T14 has a bar per prior mismatch.
2. The scripts' unsoldering thresholds tuned on the pilot by a rule fixed before the sweep
   (chart 40%, half-split 50%); tuning a baseline can only make the engine's targets harder.
3. T24 (secondary): powered readings per diagnosis at points that can exceed 50 V, engine
   relative to half-split tracing, at most 0.19x (pilot 0.17x).
4. Release gates T25 (at most one of at least six S1 participants follows the planted wrong
   step without checking) and T26 (no complaint voice more than 5 points worse on the T1 or T6
   units, with the interval of the gap excluding zero).
5. The out-of-catalog test units are checked against the hazard map and the count is reported
   with T13 (none of 410 validation and pilot units put more than 50 V on a point the map
   calls low voltage); T7's pass probabilities kept to four decimals.

The six pilot-estimable primaries are now all met together with a chance near 25%; about one
miss is expected. No test unit has been run.

In the text (acdfc03; not re-graded, since round 6 was the last): the studio maintenance
engineer among the interviewees and the IRB determination before them; ticket data stripped of
customer and technician identities by the shop, consent sought privately; the fault prior
stated (suspects start equal); the secondaries listed with O5's targets, T18 and T19 glossed;
bars with their standard errors and a bar per baseline; effort to become bench minutes once
step times are measured; S1's rule as gate T25 and the voice rule as T26; the comparison figure
and the aging split explained; forms-only safety records, a clipped bleeder, the unpowered
checks named as a limit; how each rule in Part 1 is met, in Part 4; the register at 12 rows
with checks that can fail and a fatal-risk rating that stays at M/F for the unqualified user.

Not done, and stated as limits or left for M2: sizing the need in units, hours or dollars
(the ticket coding and S1 will give times); an analysis of tool adoption and investment;
data-protection law and a fairness row in the register; NFPA 70E, hot-chassis and
scope-ground rules beyond the scope-ground note, safety-marked parts and the post-repair
leakage check; pinpoint citations for the AI Act's annexes; leaky coupling capacitors,
heater-to-cathode leakage and hardware beyond the 24 V line driver.

## Needs the team

As in round 5: the IRB determination, interviews and ticket coding; timing one schematic
transcription; building the fault boards; the outside adversarial prompts; the live
language-model runs (API key); S1; and signing each part with real names.
