# Grading log

Every milestone goes through the same loop before it is tagged ready:

1. Mechanical gates: page limit (`tools/check_pages.py`), every number traceable
   (`tools/check_claims.py`), signed-part balance (`tools/check_balance.py`),
   anonymised preview (`tools/sanitize_preview.py`), citations
   (`tools/check_citations.py`), spelling (`tools/check_spelling.py`, from round 4
   of M1), and every page rendered to an image and looked at.
2. Three fresh graders read only the anonymised text, the page images, the
   rubric and the syllabus notes, and score every rubric line. The score of
   record is the **minimum per line** across the three.
3. Four judge personas (the course professor, an industry audio-electronics
   engineer skeptical of AI hype, an ML PhD student checking methodology and
   statistics, an ethics and policy scholar) score and critique from their
   perspective. Round 1 of M1 used an investor in place of the ML PhD student;
   every later round follows the brief.
4. A claim-to-source audit checks every cited sentence against the recorded
   quotes in `docs/research/sources_*.yaml`, and a signed-part audit reads each
   part alone to check that it is a full contribution.
5. A red team (a fresh subagent) tries to break the running demo app and the
   agent: unsafe requests, prompt injection, malformed input and misleading meter
   photos. Rounds 1-3 of M1 ran without this step; it runs from round 4 on.
6. Fix and repeat, at most six rounds. Nothing in a deliverable is ever
   addressed to a grader; fixes change substance, not presentation tricks.

Reviewers are AI subagents started fresh for each round, with no access to the
repository beyond the files listed above. Their reports are summarised in
`docs/grading/`.

| Milestone | Round | Min per line (graders) | Graders | Judges | Notes |
|---|---|---|---|---|---|
| M1 | 1 | 19.0 / 25 | 19.0, 19.5, 22.5 | 21.0, 20.5, 20.0, 21.5 | `docs/grading/M1_round1.md`; source audit: 10 supported, 7 partly, 6 overstated, 1 unsupported |
| M1 | 2 | 18.0 / 25 | 20.5, 18.0, 21.0 | 19.0, 19.0, 20.0, 20.5 | `docs/grading/M1_round2.md`; personas now as in the brief; source audit 35/5/3/0; found a simulator artifact (TP8) and a test-population flaw, both fixed in the system (ADR-030) |
| M1 | 3 | 18.0 / 25 | 20.0, 18.0, 21.5 | 18.5, 18.5, 20.0, 20.0 | `docs/grading/M1_round3.md`; source audit 42/6/1/0 of 49; all parts Full; reviewers converged on simulator-only targets, tilted comparisons and unreconciled numbers; system and target design changed before the lock |
| M1 | 4 | 17.5 / 25 | 21.0, 17.5, 22.0 | 20.0, 20.0, 20.0, 19.5 | `docs/grading/M1_round4.md`; source audit 41/2/2/1 (+1 unverifiable) of 47; all parts Full; first red team (1 critical, 3 high, 5 medium, 1 low; all fixed in a136fb9); themes: aged units only secondary, fault behaviour unvalidated, wording beyond evidence, unreconciled numbers, effort accounting; ageing in training and an aged primary target before the lock |
