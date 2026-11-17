# M3, round 2

Reviewers, started fresh: a course TA (rubric M3.1-M3.6) and a claim-to-source audit with
the same materials as round 1, against `main` at d55cbe1.

| Line | Round 1 (min) | Round 2 (TA) |
|---|---|---|
| M3.1 | 16 | 17 |
| M3.2 | 10 | 10 |
| M3.3 | 18 | 19 |
| M3.4 | 15 | 16 |
| M3.5 | 7 | 8 |
| M3.6 | 7 | 8 |
| Total | 73 | 78 |

The numbers checked out; the remaining points were gaps and precision. Fixed after the
round:

- The lock check now requires the `targets-locked` tag to point at the lock commit
  (`eval/lock.py`).
- README notes for T16 and T17 now come from the scored results (ADR-054), not the earlier
  marker counts; `results/t17_live_review.json` no longer carries a stale offline count.
- T16 is reported by intent with an exact interval (13 of 98, 11 of 36 intents), and offline
  under both the locked definition and the suite's stricter rubric.
- Table 2 commands corrected: the full rebuild no longer includes `pilot` (it refuses after
  the lock), module commands use `.venv/bin/python`, the document checks need poppler and
  hunspell, the meter-photo run needs the key, the replay demo mostly falls back to offline.
- Text corrected: effort is probing plus unsoldering; the oracle is the true symptoms;
  T26's largest gap stated; T17 by source; both pre-lock exposures disclosed (ADR-028,
  ADR-029); the bring-up methods and the bleeder exception; the planted note was scored on
  the live red-team replies (none followed it), not on the diagnosis sessions; two
  commitments not met and two met in part, each marked; who did what.

Left for the person submitting (`submissions/M3/SUBMIT.md`): create the tags on GitHub, and
the human labeling of the live red-team replies. Left for M5: the LLM-with-simulator variant,
injection cases, T17's independent checker and human audit.
