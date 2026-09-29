# Differential - common tasks. Every target runs from a fresh clone after `make install`.
PY      ?= .venv/bin/python
PIP     ?= .venv/bin/pip
MS      ?= all

.PHONY: help install test lint types check sim cases fit calibrate pilot eval eval-smoke sweep replay \
        demo docs docs-check citations screenshots deck clean-runs

help:        ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | sort

install:     ## create .venv and install pinned dependencies (needs ngspice on PATH)
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip uv
	.venv/bin/uv pip install -q --python $(PY) -e ".[dev,docs]"

test:        ## unit and integration tests with coverage
	$(PY) -m pytest -q --cov=differential --cov-report=term-missing:skip-covered

lint:        ## ruff
	$(PY) -m ruff check differential eval tools tests

types:       ## mypy (strict on the core packages)
	$(PY) -m mypy differential

sim:         ## Monte Carlo simulations (train 400 + val 100 draws per fault; resumable)
	$(PY) -m differential.cli sim --split train --draws 400
	$(PY) -m differential.cli sim --split val --draws 100

cases:       ## simulate the evaluation and pilot sets (symptomatic units only) and paraphrases
	$(PY) -m eval.cases --splits unmodeled_val,unmodeled_pilot,pilot,test,unmodeled_test
	$(PY) -m eval.cases --circuits channel_strip --splits pilot_wide,test_wide
	$(PY) -m eval.nlp_benchmark --render-only

fit:         ## fit every engine artifact into data/models/
	$(PY) -m eval.train
	$(PY) -m eval.hv_audit
	$(PY) -m eval.library_stats

calibrate:   ## "no single fault fits" thresholds, with and without a complaint (after fit, cases)
	$(PY) -m eval.recalibrate_unmodeled

pilot:       ## protocol-matched pilot (validation units only) and the bar rule (before the lock)
	$(PY) -m eval.pilot_v2
	$(PY) -m eval.set_bars

sweep:       ## exhaustive safety sweep (T15)
	$(PY) -m eval.safety_sweep

eval:        ## full evaluation -> results/metrics.json and results/figures/
	$(PY) -m eval.run_eval

eval-smoke:  ## quick end-to-end check (< 5 minutes)
	$(PY) -m eval.run_eval --smoke

demo:        ## web demo on http://localhost:8000 (offline unless DIFFERENTIAL_API_KEY is set)
	$(PY) -m differential.app.server

docs:        ## render milestone documents (MS=M1 ... or all)
	$(PY) tools/design_constants.py
	$(PY) tools/render_docs.py $(MS)

docs-check:  ## page limits, balance, claims and spelling for rendered documents
	$(PY) tools/check_pages.py
	for f in submissions/M*/M*.typ; do $(PY) tools/check_balance.py $$f || exit 1; done
	for f in submissions/M*/M*.pdf; do $(PY) tools/check_claims.py "$$PWD/$$f" || exit 1; done
	$(PY) tools/check_spelling.py submissions/M*/M*.pdf

citations:   ## probe every cited URL (run on an unrestricted network)
	$(PY) tools/check_citations.py --used-only submissions/M*/M*.typ

replay:      ## record the demo session played back by Shift+R (demo fallback)
	$(PY) tools/record_replay.py

screenshots: ## Playwright screenshots of the demo app (needs a running `make demo`)
	$(PY) tools/screenshots.py

deck:        ## build the Demo Day slide deck
	$(PY) tools/make_deck.py

check: lint types test docs-check  ## everything CI runs

clean-runs:  ## delete cached evaluation runs (forces a re-run)
	rm -rf data/eval/runs
