# Differential

Simulation-grounded AI diagnosis for analog audio electronics (PRV 201 team project).

Differential helps a qualified bench technician find the failed part in analog audio
equipment. It simulates the circuit under every plausible single-part fault with
realistic part tolerances, keeps a probability for every suspect, recommends the
measurement expected to narrow the suspects most per unit of effort, and explains each step.
A language model reads the complaint and writes the explanations; it never supplies a
reading the technician has not confirmed. Safety rules and a numeric grounding check run in code.

## Quickstart

```bash
make install        # Python venv with pinned dependencies (needs ngspice on PATH)
make demo           # http://localhost:8000 - offline mode, no API key needed
# or: docker compose up
```

Set `DIFFERENTIAL_API_KEY` to run the live Claude agent (`DIFFERENTIAL_MODE=live`).

## Terms of use

The code is MIT-licensed (`LICENSE`). A running Differential is meant for qualified bench
technicians in repair businesses; the conditions under which the team would offer one (no rating
of staff, no mains-side work, trainees supervised) are in `docs/TERMS_OF_USE.md`.

This README is regenerated with results by `make docs` once the evaluation has run.
