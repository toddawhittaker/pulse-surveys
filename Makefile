# Pulse Surveys
#
# `make ci` runs the same gates as .github/workflows/ci.yml, in the same order,
# with the same tolerance for parts of the tree that do not exist yet. If it
# passes here it should pass there; when the two drift, the workflow is the
# source of truth and this file is the bug.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON ?= python3
COMPOSE ?= docker compose

RUFF_VERSION         ?= 0.6.9
MYPY_VERSION         ?= 1.11.2
PIP_AUDIT_VERSION    ?= 2.7.3
PIP_LICENSES_VERSION ?= 5.5.5
PIP_TOOLS_VERSION    ?= 7.6.1

# Green/dim only when attached to a terminal.
ifneq (,$(findstring xterm,$(TERM)))
	BOLD := $(shell tput bold)
	DIM  := $(shell tput dim)
	OFF  := $(shell tput sgr0)
endif

define banner
	@echo ""
	@echo "$(BOLD)==> $(1)$(OFF)"
endef

# Used inside shell if/else branches, so it expands to a bare `echo` — no `@`
# prefix and no leading tab, both of which would reach the shell as text.
skip = echo "$(DIM)    skipped — $(1)$(OFF)"

.PHONY: help
help: ## Show this help
	@echo "Pulse Surveys"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ---------------------------------------------------------------------------
# The whole pipeline
# ---------------------------------------------------------------------------

.PHONY: ci
ci: fast test-gates build-gates supply-chain ## Run every CI gate locally, in pipeline order
	@echo ""
	@echo "$(BOLD)All gates passed.$(OFF)"

.PHONY: fast
fast: selftest lint typecheck migration-check ## Fast gates: checker self-test, lint, typecheck, migration drift

.PHONY: selftest
selftest: ## Self-test the CI checker scripts
	$(call banner,CI checker self-test)
	@$(PYTHON) scripts/ci/test_ci_scripts.py
	@bash -n scripts/ci/wait_for_health.sh && echo "    wait_for_health.sh parses"

.PHONY: test-gates
test-gates: test e2e evals ## Test gates: pytest, Playwright, AI evals

.PHONY: build-gates
build-gates: docker-build frontend-build ## Build gates: images, Compose health, bundle budget

# ---------------------------------------------------------------------------
# Fast gates
# ---------------------------------------------------------------------------

.PHONY: lint
lint: ## ruff check + ruff format --check, eslint
	$(call banner,ruff)
	@ruff check . && ruff format --check .
	$(call banner,eslint)
	@if [ -f frontend/package.json ]; then \
		cd frontend && npx eslint . --max-warnings=0; \
	else \
		$(call skip,no frontend/package.json yet); \
	fi

.PHONY: typecheck
typecheck: ## mypy (strict on services/ and ai/contracts.py) + tsc --noEmit
	$(call banner,mypy)
	@mypy
	$(call banner,tsc --noEmit)
	@if [ -f frontend/package.json ]; then \
		cd frontend && npx tsc --noEmit; \
	else \
		$(call skip,no frontend/package.json yet); \
	fi

.PHONY: migration-check
migration-check: ## Fail if the models have drifted from the migrations
	$(call banner,alembic check)
	@if [ -f backend/alembic.ini ]; then \
		cd backend && alembic upgrade head && alembic check; \
	else \
		$(call skip,no backend/alembic.ini yet); \
	fi

# ---------------------------------------------------------------------------
# Test gates
# ---------------------------------------------------------------------------

.PHONY: invariants
invariants: ## Run the §4.1 invariant suite alone; a skip is a failure
	$(call banner,invariant suite (SPEC §4.1))
	@mkdir -p reports
	@if compgen -G "tests/unit/test_*.py" > /dev/null 2>&1 || compgen -G "tests/integration/test_*.py" > /dev/null 2>&1; then \
		pytest -m invariant --junitxml=reports/invariants.xml || true; \
		$(PYTHON) scripts/ci/check_invariants.py reports/invariants.xml --allow-empty; \
	else \
		$(call skip,no test suite yet); \
	fi

.PHONY: test
test: invariants ## pytest unit + integration with coverage
	$(call banner,pytest unit + integration)
	@if compgen -G "tests/unit/test_*.py" > /dev/null 2>&1 || compgen -G "tests/integration/test_*.py" > /dev/null 2>&1; then \
		pytest tests/unit tests/integration --cov=backend/app --cov-report=term-missing; \
	else \
		$(call skip,no test suite yet); \
	fi

.PHONY: e2e
e2e: ## Playwright against the Compose stack
	$(call banner,Playwright e2e)
	@if compgen -G "tests/e2e/*.spec.ts" > /dev/null 2>&1; then \
		npx playwright test; \
	else \
		$(call skip,no tests/e2e specs yet); \
	fi

.PHONY: evals
evals: ## AI eval runner with per-task precision/recall floors
	$(call banner,AI evals)
	@if [ -d tests/evals ] && compgen -G "tests/evals/**/*.py" > /dev/null 2>&1; then \
		$(PYTHON) -m tests.evals.runner --enforce-floors; \
	else \
		$(call skip,no tests/evals runner yet); \
	fi

# ---------------------------------------------------------------------------
# Build gates
# ---------------------------------------------------------------------------

.PHONY: docker-build
docker-build: ## Build all images and check the stack comes up healthy
	$(call banner,docker compose build)
	@if [ -f docker-compose.yml ]; then \
		$(COMPOSE) build && $(COMPOSE) up -d && \
		./scripts/ci/wait_for_health.sh api worker beat; \
		status=$$?; $(COMPOSE) down -v >/dev/null 2>&1 || true; exit $$status; \
	else \
		$(call skip,no docker-compose.yml yet); \
	fi

.PHONY: frontend-build
frontend-build: ## Production build + bundle budget
	$(call banner,frontend production build)
	@if [ -f frontend/package.json ]; then \
		cd frontend && npm run build && cd .. && \
		$(PYTHON) scripts/ci/check_bundle_size.py frontend/dist --budget ci/bundle-budget.json; \
	else \
		$(call skip,no frontend/package.json yet); \
	fi

# ---------------------------------------------------------------------------
# Supply chain
# ---------------------------------------------------------------------------

.PHONY: supply-chain
supply-chain: audit licenses ## pip-audit, npm audit, license compatibility

.PHONY: audit
audit: ## Fail on high/critical dependency vulnerabilities
	$(call banner,pip-audit)
	@pip-audit --strict --desc -r requirements.txt -r requirements-dev.txt
	$(call banner,npm audit)
	@if [ -f frontend/package.json ]; then \
		cd frontend && npm audit --audit-level=high; \
	else \
		$(call skip,no frontend/package.json yet); \
	fi

.PHONY: licenses
# pip-licenses reads whatever is installed in the active environment. In CI
# that is the runtime lock plus pip-audit and pip-licenses themselves; locally
# it is your whole virtual environment, dev dependencies included. So this can
# report more packages than CI does, and never fewer.
licenses: ## Fail on dependencies incompatible with MIT distribution
	$(call banner,license compatibility)
	@mkdir -p reports
	@pip-licenses --format=json --with-urls > reports/py-licenses.json
	@args="--python-json reports/py-licenses.json"; \
	if [ -f frontend/package.json ]; then \
		(cd frontend && npx --yes license-checker-rseidelsohn@4.3.0 --json > ../reports/npm-licenses.json); \
		args="$$args --npm-json reports/npm-licenses.json"; \
	fi; \
	$(PYTHON) scripts/ci/check_licenses.py $$args

# ---------------------------------------------------------------------------
# Developer conveniences (SPEC §13)
# ---------------------------------------------------------------------------

.PHONY: tools
tools: ## Install the pinned CI tools locally
	pip install "ruff==$(RUFF_VERSION)" "mypy==$(MYPY_VERSION)" \
		"pip-audit==$(PIP_AUDIT_VERSION)" "pip-licenses==$(PIP_LICENSES_VERSION)" \
		"pip-tools==$(PIP_TOOLS_VERSION)"

.PHONY: install
install: ## Install the locked dependencies and the backend, editable
	pip install --require-hashes -r requirements-dev.txt
	pip install -e . --no-deps

# Run this after editing the dependencies in pyproject.toml, and commit both
# files with the change. See docs/adr/0005-dependency-locking.md.
.PHONY: lock
lock: ## Recompile requirements.txt and requirements-dev.txt from pyproject.toml
	pip-compile --quiet --generate-hashes --strip-extras \
		--output-file=requirements.txt pyproject.toml
	pip-compile --quiet --generate-hashes --strip-extras --extra dev \
		--output-file=requirements-dev.txt pyproject.toml

.PHONY: fmt
fmt: ## Apply formatting (the only target that writes to your files)
	@ruff format . && ruff check --fix .

.PHONY: up
up: ## Bring the stack up with dev wiring
	@if [ -f docker-compose.yml ]; then $(COMPOSE) up -d; \
	else $(call skip,no docker-compose.yml yet); fi

.PHONY: down
down: ## Tear the stack down, including volumes
	@if [ -f docker-compose.yml ]; then $(COMPOSE) down -v; \
	else $(call skip,no docker-compose.yml yet); fi

.PHONY: logs
logs: ## Follow stack logs
	@$(COMPOSE) logs -f

.PHONY: migrate
migrate: ## Apply migrations to the running database
	@if [ -f backend/alembic.ini ]; then cd backend && alembic upgrade head; \
	else $(call skip,no backend/alembic.ini yet); fi

.PHONY: seed
seed: ## Load the demo institution, hierarchy, term, and sections
	@if [ -f scripts/seed.py ]; then $(PYTHON) scripts/seed.py; \
	else $(call skip,no scripts/seed.py yet); fi

.PHONY: clean
clean: ## Remove build and report artifacts
	rm -rf reports/ coverage.xml .coverage .pytest_cache .mypy_cache .ruff_cache
	rm -rf frontend/dist playwright-report/
