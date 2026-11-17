# M3 - Prototype: submission sheet

**Submit:** the repository link (branch `main`, tag `m3-ready`) and `M3.pdf`, the design
document: what was built, how to run and inspect it, results against the locked targets,
failure analysis, and changes from M2.

| File | What it is |
|---|---|
| `M3.pdf` | The design document, rendered with the signer from `team.yaml` |
| `../../templates/M3/build.py` | Its source: every number is read from `results/` at build time |

## Regenerate

```bash
python tools/engineering_facts.py      # tests, coverage, code size -> results/engineering.json
python -m eval.run_eval                # targets_result, after the agent and red-team runs
python tools/m3_analysis.py            # failure analysis -> results/m3_analysis.json
                                       # (the LLM-alone part replays data/llm_cache from
                                       #  branch claude/m3-live-results; without it, pending)
python tools/build_bench.py            # docs/bench/index.html
python templates/M3/build.py . submissions/M3/M3.pdf "<signer>"
python tools/check_claims.py "$PWD/submissions/M3/M3.pdf"
```

## Human actions before submitting

1. Create the tags on GitHub (tag pushes are blocked from the cloud sessions). For each, open
   the repository's Releases page, choose "Draft a new release", type the tag name under
   "Choose a tag" and pick its target, then publish:
   - `targets-locked`, target branch `locks/targets-locked` (the lock commit `60cca12`);
   - `m2-ready`, target branch `claude/differential-build` (`81267dd`);
   - `m3-ready`, target branch `main`.
2. Render the Canvas copy with your name as the signer (third argument above) and submit it
   with the repository link.
3. Recommended: read the live red-team replies in `results/redteam_review_full.json` as the
   second, human labeler the suite's README asks for, and the live numbers in
   `results/t17_live_review.json` (the start of T17's human audit).
