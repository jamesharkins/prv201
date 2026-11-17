# M3, round 1

Reviewers, each started fresh: a course TA, an ML PhD student checking methodology and
statistics, an industry audio-electronics engineer, and a claim-to-source audit. Each had the
document (text and page images), M2 as submitted, the rubric lines and the syllabus notes, and
read-only access to the repository. Rubric: M3.1 core runs (20), M3.2 scope versus M2 (15),
M3.3 inspectable artifact (25), M3.4 engineering (20), M3.5 alignment with M2 (10), M3.6 the
document explains what was built and how to run it (10).

| Line | TA | ML | Industry | Min |
|---|---|---|---|---|
| M3.1 | 16 | 17 | 18 | 16 |
| M3.2 | 10 | 11 | 12 | 10 |
| M3.3 | 18 | 18 | 19 | 18 |
| M3.4 | 15 | 16 | 16 | 15 |
| M3.5 | 7 | 7 | 8 | 7 |
| M3.6 | 7 | 8 | 7 | 7 |
| Total | 73 | 77 | 80 | 73 |

## What the reviewers found, and what changed

- **The submission pointed at code main did not have.** The document, the bench page and the
  analysis files were on a feature branch. `main` was fast-forwarded; the document now cites
  the branch and tag, not a commit it cannot contain. A branch `locks/targets-locked` points at
  the lock commit so the tag can be created on GitHub (tag pushes are blocked from the cloud
  sessions). Two reviewers concluded from a shallow local clone that the lock commit was not on
  GitHub; it is (checked with the GitHub API).
- **T16 was overstated.** The live result ("no reply gave or endorsed an unsafe step") rested
  on a review of only the replies the marker phrases flagged. A separately prompted reviewer
  then read all 145 live replies against the locked definition
  (`results/redteam_review_full.json`) and found 13 of 98 attack replies unsafe, most giving
  mains-side steps while declining. ADR-054 scores T16 on the reviewed replies, offline and
  live, and T17 on every transcript; both are now missed.
- **T17 was labelled pending** although the live count was above its 0% bar. It is now missed,
  with the cause (a rewrite request sent as a user turn) and the repeated slip (`range_95`
  written as "95%") stated.
- **Undisclosed limits:** the red-team suite covers 4 of 13 categories and has no injection
  case; the out-of-catalog test set is 80/20 rather than the locked 70/30 (reweighted, 13.5%
  misleading); every-step calibration error is 0.021; the live agent's gap to the engine is
  unexplained by ADR-052; caching saved 46%, while most of the drop from M2's $0.22 estimate came
  from fewer model calls. All are now in the document, with numbers from
  `results/m3_analysis.json`.
- **A mechanism overclaimed:** the cost-weighting ablation was presented as a design win; it
  shows overconfident sessions, now reported as a calibration finding with the split by
  oscilloscope use.
- **Readability:** terms defined, Figure 1 given its step key, Figure 2 cropped to the legible
  panel, "§" replaced (it rendered as "$"), commands that work from a clone (lock tag, replay
  from the cache branch), one-sided bounds labelled.
