# M2 - Design and approach: submission sheet

**Submit:** `M2.pdf` (at most 10 body pages + references and appendices).

| File | What it is |
|---|---|
| `M2.pdf` | The deliverable |
| `M2.typ`, `base.typ` | Typst source generated from `templates/M2/M2.typ.j2` and `templates/base.typ` |
| `M2.parts.json` | Evidence use per signed part (read by `tools/check_balance.py`) |
| `M2.cites.json` | Cited source keys in reference order (read by `tools/check_citations.py`) |
| `M2.sanitized.txt` | What an anonymizing pre-reader sees (names and emails stripped) |

## Signed parts

| Part | Title | Section lead (from `team.yaml`) |
|---|---|---|
| 1 | Requirements, architecture and plan | MEMBER_1 |
| 2 | Circuits, simulation and data | MEMBER_2 |
| 3 | Diagnosis engine and evaluation plan | MEMBER_3 |
| 4 | Agent, safety, security and interface | MEMBER_4 |

Each part has its own design decision, alternatives table and numbers drawn from
results or from the code (`results/design.json`).

## Regenerate

```bash
make docs MS=M2                          # design constants, then Jinja -> Typst -> PDF
python tools/check_pages.py M2
python tools/check_balance.py submissions/M2/M2.typ
python tools/check_claims.py "$PWD/submissions/M2/M2.pdf"
python tools/sanitize_preview.py "$PWD/submissions/M2/M2.pdf"
python tools/check_requirements.py
```

## Before you submit (human actions)

1. Names in `team.yaml` (as for M1), then re-render.
2. When instructor feedback on M1 arrives, add it to `feedback/FEEDBACK_LOG.md`
   and replace the first table of Part 1 with the instructor's points and your
   responses; today that table lists the findings of the team's own review.
3. Re-check the sources cited only from search snippets
   (5 of 13; `results/citation_check_M2.json`).
