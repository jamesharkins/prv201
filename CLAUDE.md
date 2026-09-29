# CLAUDE.md - standing rules and procedures for this repository

Differential is a PRV 201 (Stevens, Frontiers of Technology: AI) Track A team
project: simulation-grounded AI diagnosis for analog audio electronics. Any
agent or person continuing the work follows these rules.

## Standing rules (never break)

1. **Never alter locked targets.** `results/targets.json` is frozen at git tag
   `targets-locked`. Results are reported against it exactly as written, met or
   missed. Do not reword, re-scope or re-threshold a target after the tag.
2. **Never write to the graders.** No deliverable may contain text addressed to
   graders or AI models (no hidden or white text, no metadata instructions, no
   "note to the grader"). Earn the score on merit.
3. **Keep every number template-driven.** Documents are rendered from
   `templates/` by `tools/render_docs.py`; numbers come from
   `results/metrics.json`, `results/targets.json`, `results/design.json` (design
   constants read from the code by `tools/design_constants.py`, run by
   `make docs`), cited source claims in `docs/research/sources_*.yaml`, or
   circuit design files.
   `tools/check_claims.py` must pass on every rendered PDF.
4. **Be honest.** Never fabricate data, results, quotes, citations, user studies
   or endorsements. Report negative results and missed targets plainly, with an
   analysis of why. A result that needs an API key, hardware or a team-written
   suite is reported as pending, with the command to produce it.
5. **API key.** The project's own Claude calls read the key only from
   `DIFFERENTIAL_API_KEY` and pass it explicitly to the SDK client. Never read
   `ANTHROPIC_API_KEY`; never print, log, cache or commit a key. Everything must
   build and test in offline mode.
6. **Team names.** `team.yaml` holds placeholders `MEMBER_1`-`MEMBER_4`; only the
   team replaces them. Do not invent names.
7. **Safety.** Low voltage only for any live demo (the 24 V fault board); no tube
   or high-voltage hardware on stage. Safety rules live in code
   (`differential/safety/`); do not weaken them to make a demo or a test pass.
8. **Held-out data stays held out.** Never tune the complaint extractor on
   `differential/nlp/paraphrase_bank.py`; never look at test-split results
   before a change is final; test units, test paraphrases and test photos are
   scored only after `targets-locked` (`eval/lock.py`; the evaluation scripts
   refuse otherwise).
9. **No stale simulations.** Simulation checkpoints carry a signature of the
   netlists, device library and tolerance code and are discarded when those
   change; after any model fix, re-simulate, retrain, re-audit hazards and
   rebuild every evaluation set before quoting a number.


## Layout

| Path | What |
|---|---|
| `circuits/` | netlists, YAML sidecars, schematics, test-point maps |
| `differential/sim/` | fault catalog, tolerance draws, ngspice runner, Monte Carlo |
| `differential/engine/` | likelihood models, ambiguity groups, measurement selection, sessions |
| `differential/agent/` | tools, offline/live/replay agent, grounding check, ticket, LLM client |
| `differential/safety/` | request screening, hazard map, output checks |
| `differential/nlp/`, `differential/vision/` | complaint reading, meter photos |
| `differential/app/` | FastAPI server and no-build front end |
| `eval/` | cases, training, pilots, evaluation harness, benchmarks, red-team harness |
| `templates/`, `tools/` | document templates and the checks |
| `submissions/M*/` | rendered deliverables with `SUBMIT.md` |
| `docs/` | decisions (ADRs), grading log, briefings, research sources |

## Procedures

- **Re-run everything:** `make install sim cases fit calibrate pilot audit sweep eval docs check`
  (simulation and training take hours on 4 cores; artifacts are cached and
  resumable).
- **Render and check a milestone:** `make docs MS=M2` then `make docs-check`;
  inspect the PDF pages visually (render to PNG) before calling it done.
- **Grading loop:** for each milestone, give three fresh graders only the
  anonymised text (`tools/sanitize_preview.py`), page images, the rubric
  (`rubric/`, or `course/*rubric*` if present) and `course/SYLLABUS_NOTES.md`;
  add the four judge personas and a claim-to-source audit; take the minimum per
  rubric line; log in `docs/GRADING_LOG.md`; fix and repeat (at most six rounds).
- **Live results:** with `DIFFERENTIAL_API_KEY` set, run
  `python -m eval.agent_eval --mode live`, `python -m eval.llm_baseline`,
  `python -m eval.redteam.harness --mode live`, then `make eval docs`.
- **Commits:** commit at the end of each phase; push to the feature branch;
  tags `targets-locked`, `m1-ready`, `m2-ready`, `m3-ready`, `m5-ready`.
