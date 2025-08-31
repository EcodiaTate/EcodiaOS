# Makefile — Simula CI wiring (fast, deterministic)

PYTHON ?= python3
PIP ?= pip3
VENV ?= .venv
ACTIVATE = . $(VENV)/bin/activate

REQ_CORE = pytest==8.2.0 ruff==0.5.6 mypy==1.10.0 bandit==1.7.9
REQ_EXTRAS = coverage==7.5.4 pytest-cov==5.0.0 safety==3.2.4

# ------- Hygiene -------
.PHONY: help
help:
	@echo "Targets:"
	@echo "  setup          - create venv and install tooling"
	@echo "  lint           - ruff + mypy + bandit"
	@echo "  test           - pytest -q (unit only)"
	@echo "  eval           - run simula evaluate on examples/step_basic.json"
	@echo "  fix-retrieval  - propose retrieval/context.py patch (writes patch to artifacts)"
	@echo "  ci             - full local CI (lint, test, eval)"
	@echo "  clean          - remove caches and artifacts"

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE); $(PIP) install -U pip
	$(ACTIVATE); $(PIP) install -U $(REQ_CORE) $(REQ_EXTRAS)

.PHONY: setup
setup: $(VENV)/bin/python
	@echo "✅ venv ready"

.PHONY: lint
lint: setup
	$(ACTIVATE); ruff check .
	$(ACTIVATE); mypy --hide-error-context --pretty .
	$(ACTIVATE); bandit -q -r systems || true

.PHONY: test
test: setup
	$(ACTIVATE); pytest -q

ARTIFACTS ?= artifacts
SPEC ?= examples/step_basic.json
OUT ?= $(ARTIFACTS)/eval_report.json

$(ARTIFACTS):
	mkdir -p $(ARTIFACTS)

.PHONY: eval
eval: setup $(ARTIFACTS)
	$(ACTIVATE); $(PYTHON) scripts/run_simula.py --spec $(SPEC) --out $(OUT) --json
	@echo "📦 wrote $(OUT)"

.PHONY: fix-retrieval
fix-retrieval: setup $(ARTIFACTS)
	$(ACTIVATE); $(PYTHON) scripts/run_simula.py --spec $(SPEC) --propose-retrieval --patch-out $(ARTIFACTS)/retrieval.patch
	@echo "📦 patch at $(ARTIFACTS)/retrieval.patch (apply with: git apply -p0 artifacts/retrieval.patch)"

.PHONY: ci
ci: lint test eval

.PHONY: clean
clean:
	rm -rf $(VENV) .pytest_cache .mypy_cache $(ARTIFACTS)
