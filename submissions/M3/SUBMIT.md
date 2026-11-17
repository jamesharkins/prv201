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
python tools/m3_analysis.py            # failure analysis -> results/m3_analysis.json
                                       # (the LLM-alone part replays data/llm_cache from
                                       #  branch claude/m3-live-results; without it, pending)
python tools/build_bench.py            # docs/bench/index.html
python templates/M3/build.py . submissions/M3/M3.pdf "<signer>"
python tools/check_claims.py "$PWD/submissions/M3/M3.pdf"
```

## Human actions before submitting

1. Create the tag `m3-ready` on the commit submitted (GitHub, Releases, "Create a new
   release", tag `m3-ready`, target `main`); tag pushes are blocked from the cloud
   sessions. Also create `targets-locked` on `60cca12` if it is not on GitHub yet.
2. Render the Canvas copy with your name as the signer (third argument above).
3. Optional, recommended: read the flagged red-team replies in
   `results/redteam_review.json` as the second, human reviewer the suite's README asks for,
   and the 15 live numbers in `results/t17_live_review.json`.
