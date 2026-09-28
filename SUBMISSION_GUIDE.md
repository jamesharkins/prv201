# Submission guide - what the team must do

Everything that could be built and checked without people, an API key or
hardware is done. This page lists what only the team can do, in the order that
matters, with the exact commands. Each milestone folder (`submissions/M*/`) also
has its own `SUBMIT.md`.

## 1. Before any submission

1. **Put your names in `team.yaml`** (replace `MEMBER_1` ... `MEMBER_4`; keep the
   roles or adjust them). Then re-render: `make docs` and `make docs-check`.
   The names appear only as "Section lead: <name>" on each signed part.
2. **Each section lead reads their briefing** (`docs/briefings/member_N.md`) and
   their parts, and can explain every number without notes.
3. **If the course publishes an official rubric**, put it in `course/` (a file
   whose name contains `rubric`). It replaces `rubric/derived_rubric.md`; re-run
   the review round described in `CLAUDE.md` and `docs/GRADING_LOG.md`.

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
python -m eval.redteam.harness --mode live # T16 live (after step 4)
make eval docs                             # re-render documents with the new numbers
```

Responses are cached under `data/llm_cache/`, so a rerun replays them exactly
(replay mode works without the key once the cache exists). Commit the cache if
you want graders to be able to replay live sessions.

## 4. Write the red-team suite (T16)

The build could not author adversarial prompts (see `docs/DECISIONS.md`,
ADR-025). Two team members who have not read `differential/safety/rules.py`
write at least 40 attacks and 12 benign controls in `eval/redteam/cases.yaml`
following `eval/redteam/README.md`, then:

```bash
python -m eval.redteam.harness --mode offline
```

## 5. Hardware check (T7)

Build the low-voltage fault board (`hardware/fault_board/`, 24 V maximum). One
person inserts at least 20 faults blind; another runs Differential on each and
records the readings. Report group-aware top-3 accuracy against T7.
Low voltage only for any live demo: no tube or high-voltage hardware on stage.

## 6. Planned human studies (not locked targets)

- Time one transcription of a documented commercial schematic into a netlist
  and test-point map (M2 promise).
- Interview two or three working technicians about how much of a repair bill
  diagnosis takes and time the bench actions behind the effort weights.

Report what you did; do not report studies you did not run.

## 7. Demo Day

Rehearse with `submissions/M5/` (talk script in four slices, runbook, Q&A bank).
Record the presentation following the recorded-presentation package there.
