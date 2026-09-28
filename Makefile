# Differential - common tasks. Every target runs from a fresh clone after `make install`.
PY      ?= .venv/bin/python
PIP     ?= .venv/bin/pip
MS      ?= all

.PHONY: help install test lint types check sim cases fit pilot eval eval-smoke sweep \
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

cases:       ## simulate the evaluation cases and the pilot split
	$(PY) -m eval.cases
	$(PY) -m eval.cases --circuits channel_strip --splits pilot_wide,test_wide
	$(PY) -m eval.pilot_split

fit:         ## fit every engine artifact into data/models/
	$(PY) -m eval.train
	$(PY) -m eval.hv_audit
	$(PY) -m eval.library_stats

pilot:       ## second pilot (validation units only) used to set target bars
	$(PY) -m eval.pilot_v2

sweep:       ## exhaustive safety sweep (T15)
	$(PY) -m eval.safety_sweep

eval:        ## full evaluation -> results/metrics.json and results/figures/
	$(PY) -m eval.run_eval

eval-smoke:  ## quick end-to-end check (< 5 minutes)
	$(PY) -m eval.run_eval --smoke

demo:        ## web demo on http://localhost:8000 (offline unless DIFFERENTIAL_API_KEY is set)
	$(PY) -m differential.app.server

docs:        ## render milestone documents (MS=M1 ... or all)
	$(PY) tools/render_docs.py $(MS)

docs-check:  ## page limits, claims, balance and anonymised preview for rendered documents
	$(PY) tools/check_pages.py
	for f in submissions/M*/M*.typ; do $(PY) tools/check_balance.py $$f || exit 1; done
	for f in submissions/M*/M*.pdf; do $(PY) tools/check_claims.py "$$PWD/$$f" || exit 1; done

citations:   ## probe every cited URL (run on an unrestricted network)
	$(PY) tools/check_citations.py --used-only submissions/M*/M*.typ

screenshots: ## Playwright screenshots of the demo app (needs a running `make demo`)
	$(PY) tools/screenshots.py

deck:        ## build the Demo Day slide deck
	$(PY) tools/make_deck.py

check: lint types test docs-check  ## everything CI runs

clean-runs:  ## delete cached evaluation runs (forces a re-run)
	rm -rf data/eval/runs
