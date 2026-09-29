# Submission guide - what the team must do

Everything that could be built and checked without people, an API key or
hardware is done. This page lists what only the team can do, in the order that
matters, with the exact commands. Each milestone folder (`submissions/M*/`) also
has its own `SUBMIT.md`.

## 0. When each milestone is due (from the syllabus)

Work listed in a week is due by the start of the following class
(`course/SYLLABUS_NOTES.md`).

| Milestone | Listed in week | Due |
|---|---|---|
| M1 - Problem statement | 5 | start of week 6's class |
| M2 - Design / approach | 7 | start of week 8's class |
| M3 - Prototype / draft | 10 | start of week 11's class |
| M4 - Peer review | 12 | start of week 13's class |
| M5 - final milestone and video (non-finalist teams) | 13 | end of week 13; finalists present in week 14 |

Each milestone is graded as a team, then per signed part (100% for a full, meaningful
part, 50% for a partial one, 0% for none). An AI model reads each submission first,
after names and emails are stripped; its read is a reference only, and a human grader
enters the score that counts.

## 1. Before any submission

1. **Put your names in `team.yaml`** (replace `MEMBER_1` ... `MEMBER_4`; keep the
   roles or adjust them). Then re-render: `make docs` and `make docs-check`.
   The names appear only as "Section lead: <name>" on each signed part.
2. **Each section lead reads their briefing** (`docs/briefings/member_N.md`) and
   their parts, and can explain every number without notes.
3. **If the course publishes an official rubric**, put it in `course/` (a file
   whose name contains `rubric`). It replaces `rubric/derived_rubric.md`; re-run
   the review round described in `CLAUDE.md` and `docs/GRADING_LOG.md`.

## 1a. Push the milestone tags

The build environment could push the branch but not tags (the git proxy
answered HTTP 403 to every tag push). The targets were locked in commit
`60cca12` ("Lock the targets (v4)"), which sets `locked_on` in
`results/targets.json` and is on the pushed branch before any evaluation
result. Create the tags on that commit from any clone and push them:

```bash
git fetch origin claude/differential-build
git tag -a targets-locked 60cca12 -m "Targets v4 locked before the full evaluation (ADR-046, ADR-047); no test unit scored"
git tag -a m1-ready 60cca12 -m "M1 problem statement final after six review rounds"
git push origin targets-locked m1-ready
```

Later milestone tags (`m2-ready`, `m3-ready`, `m5-ready`) are listed in
`CHANGELOG.md` with their commits when they are made.

## 2. Re-check sources the build could only see as search snippets

The build container could not reach most publisher and government sites.
Every cited source records how it was verified (`verified: fetched` or
`search_snippet_only`) in `docs/research/sources_*.yaml`.

```bash
python tools/check_citations.py --used-only submissions/M1/M1.typ   # run on an unrestricted network
```

Open every source listed under `snippet_only` in
`results/citation_check_M1.json` (and the M2/M3/M5 equivalents) and confirm the
sentence that cites it. Fix or drop any claim that does not hold.

## 3. Results that need an API key

Set `DIFFERENTIAL_API_KEY` (the project never reads `ANTHROPIC_API_KEY`), then:

```bash
export DIFFERENTIAL_API_KEY=...            # never commit it
python -m eval.llm_baseline                # T5: LLM alone and LLM with simulator
python -m eval.agent_eval --mode live      # T17 live pre-check rate, T21 cost
python -m eval.nlp_benchmark               # T18 Claude part (sealed paraphrase bank B)
python -m eval.meter_eval                  # T19 Claude part (post-lock test photos)
python -m eval.redteam.harness --mode live # T16 live (after step 4)
make eval docs                             # re-render documents with the new numbers
```

Responses are cached under `data/llm_cache/`, so a rerun replays them exactly
(replay mode works without the key once the cache exists). Commit the cache if
you want graders to be able to replay live sessions.

## 4. Write the red-team suite (T16)

T16 needs at least 300 adversarial prompts written independently of the safety
rules (ADR-033). The build cannot author them for itself (ADR-025). Sources:

1. Two team members who have not read `differential/safety/rules.py` write at
   least 100 attacks and 20 benign controls in `eval/redteam/cases.yaml`, following
   `eval/redteam/README.md`.
2. During the M4 peer review, ask the team you review for at least 50 attacks of
   their own (same schema; record who wrote each case in `rationale`).
3. The rest may come from a separately prompted model that is given only the
   README (never the rules); mark those cases `source: model`.

Each case may also be posed inside attack styles from an open-source scanner;
report results by intent as well as by prompt, because prompts that share an
intent are not independent. Then:

```bash
python -m eval.redteam.harness --mode offline
DIFFERENTIAL_API_KEY=... python -m eval.redteam.harness --mode live
```

## 5. Hardware validation (T7, a primary target)

Follow `hardware/fault_board/validation_protocol.md` exactly: three socketed copies
of the 24 V driver board (one from used parts), a sealed random draw of 60 faults
(`python hardware/fault_board/draw_faults.py --seed <private number>`), a recorder
who does not know the draw, one full recording per fault, and the healthy check
before and after. Then:

```bash
python -m eval.fault_board --sheet recording_sheet.csv --key sealed_key.csv --healthy healthy.csv
```

T7 is met only if at least 49 of the 60 faults are named first by the engine. Report
the result whatever it is. Low voltage only, here and in any live demo: no tube or
high-voltage hardware on the bench or on stage.

## 6. Human studies (S1 is pre-registered; nothing may be invented)

These are the evidence the reviewers asked for and the build cannot produce.
Report what you did; never report studies you did not run.

0. **Ethics review first.** Before any interview, survey or study, ask the
   university's IRB for a determination (the study includes a planted wrong
   recommendation, which is a mild deception). Use a consent form that says some
   recommendations may be wrong on purpose, debrief every participant afterwards,
   keep the planted error on a non-hazardous step of a 24 V board, and store
   interview notes without names.

1. **Technician interviews and survey (before M2).** Talk to 3-5 working
   technicians and, if possible, survey 10 or more (or code 50 closed tickets from
   2-3 shops). Ask: diagnosis time and its share of the bill; the share of jobs
   that are single static faults in documented units (versus intermittent,
   contact/mechanical, noise, power stage, multiple aged parts, no fault found);
   what they would need from a tool. Anonymise, get consent, and update Table 1
   of M1/M2 and `feedback/FEEDBACK_LOG.md` (rows 30, 33).
2. **Timing study (M2).** Time the bench actions behind the effort weights
   (DC reading, scope reading, hands-off high-voltage reading, unsolder and test)
   on the fault board, and time one transcription of a documented schematic.
3. **Technician study S1 (pre-registered in `results/targets.json`, reported
   without a bar).** At least 6 technicians each diagnose 4 faults on a 24 V board,
   2 with the tool and 2 without, in counterbalanced order; one tool session per
   technician carries the planted wrong recommendation. Outcomes: minutes to a
   correct diagnosis (primary), correct diagnoses, good parts removed, planted error
   caught. Analysis: paired differences with exact sign-test intervals, no pooling
   across technicians.

## 7. Container check on an unrestricted network

The build sandbox's egress policy blocked `deb.debian.org`, so the Docker image
could not install ngspice there. On a normal network run `docker compose up`
and open http://localhost:8000 once before submitting M3.

## 8. Demo Day

Rehearse with `submissions/M5/` (talk script in four slices, runbook, Q&A bank).
Record the presentation following the recorded-presentation package there.
