# Pulse Surveys
#
# `make ci` runs the same gates as .github/workflows/ci.yml, in the same order,
# with the same tolerance for parts of the tree that do not exist yet — the
# frontend, the e2e specs, and the eval sets. The migration and test gates lost
# theirs in E0-04 and now run unconditionally in both places. If it passes here
# it should pass there; when the two drift, the workflow is the source of truth
# and this file is the bug.
#
# Two gates need something running: `test` needs a Docker daemon for
# testcontainers, and `migration-check` needs a database this machine can reach
# (`make up`, with DATABASE_URL pointed at localhost — see README.md).

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
	@bash -n scripts/ci/check_job_runtime.sh && echo "    check_job_runtime.sh parses"

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

# mypy runs three times, and it has to: `backend/app`, `mock-lms/app` and
# `mock-idp/app` are all packages called `app` (SPEC §13 names all three), and
# one run over two of them stops with "Duplicate module named app" having
# checked neither. Measured, not assumed. `.github/workflows/ci.yml` runs the
# same three in the same order. See
# docs/adr/0039-the-two-app-packages-are-typechecked-in-two-runs.md.
.PHONY: typecheck
typecheck: ## mypy over backend/, mock-lms/ and mock-idp/ + tsc --noEmit
	$(call banner,mypy)
	@mypy
	$(call banner,mypy mock-lms/app)
	@mypy mock-lms/app
	$(call banner,mypy mock-idp/app)
	@mypy mock-idp/app
	$(call banner,tsc --noEmit)
	@if [ -f frontend/package.json ]; then \
		cd frontend && npx tsc --noEmit; \
	else \
		$(call skip,no frontend/package.json yet); \
	fi

# Needs a database to migrate: `make up` first. CI has its own Postgres service
# for this job, provisioned with the same two roles the stack deploys.
#
# `alembic` reads `.env` itself (backend/migrations/env.py), so nothing has to
# be exported here — but DATABASE_URL has to name a host this machine can
# resolve. `.env.example` names the Compose service `db`, which resolves inside
# the network and not on your laptop; README.md says where to point it.
.PHONY: migration-check
migration-check: ## Fail if the models have drifted from the migrations
	$(call banner,alembic upgrade head && alembic check)
	@cd backend && alembic upgrade head && alembic check

# ---------------------------------------------------------------------------
# Test gates
# ---------------------------------------------------------------------------

# No `--allow-empty`, from E0-10 on: the §4.1 invariants exist, so a run that
# collected none of them is a suite that has lost them rather than one that has
# not grown them yet. The workflow dropped the flag in the same change, and the
# two move together. `scripts/ci/check_invariants.py` keeps the flag as an
# option; what has gone is passing it.
.PHONY: invariants
invariants: ## Run the §4.1 invariant suite alone; a skip and an empty run are both failures
	$(call banner,invariant suite (SPEC §4.1))
	@mkdir -p reports
	@pytest -m invariant --junitxml=reports/invariants.xml || true
	@$(PYTHON) scripts/ci/check_invariants.py reports/invariants.xml

# The integration tests start their own Postgres through testcontainers, so this
# needs a running Docker daemon but not the Compose stack.
.PHONY: test
test: invariants ## pytest unit + integration with coverage
	$(call banner,pytest unit + integration)
	@pytest tests/unit tests/integration --cov=backend/app --cov-report=term-missing

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

# The checks after the health wait are E0-02's and E0-03's acceptance criteria,
# in the same order as the `docker` job in .github/workflows/ci.yml, plus the
# base-file-only pass that job ends with. Five services are named and seven are
# covered: `api` waits on a healthy `db` and a healthy `redis`, while `worker`,
# `beat`, `mock-lms` and `mock-idp` have nothing waiting on them and so have to
# be named here. The two mocks joined this list in E0-16; the workflow has named
# `mock-lms` since E0-14 and this file had not caught up, which is the drift
# CLAUDE.md means when it says the workflow is right and this file is the bug.
#
# The base-file-only pass is the one that runs the application as installed in
# the image; every other line here runs your checkout through the override's
# bind mount. Why that pass exists is docs/adr/0011; this recipe exists to match
# the workflow, and when the two disagree the workflow is right.
.PHONY: docker-build
docker-build: ## Build the images and check the stack against E0-02's and E0-03's criteria
	$(call banner,docker compose build)
	@test -f .env || { echo "    .env is missing — run: cp .env.example .env"; exit 1; }
	@$(COMPOSE) build
	$(call banner,compose stack health)
	@set -e; \
	trap '$(COMPOSE) down -v >/dev/null 2>&1 || true' EXIT; \
	$(COMPOSE) up -d; \
	./scripts/ci/wait_for_health.sh api worker beat mock-lms mock-idp; \
	code=$$(curl --silent --show-error --max-time 10 --output /dev/null \
		--write-out '%{http_code}' http://localhost:8000/healthz); \
	echo "    GET /healthz -> $$code"; \
	test "$$code" = "200"; \
	uid=$$($(COMPOSE) exec -T api id -u | tr -d '\r'); \
	echo "    api runs as uid $$uid"; \
	test "$$uid" != "0"; \
	./scripts/ci/check_job_runtime.sh; \
	echo "    base file alone (no override: no mounts, no host ports)"; \
	$(COMPOSE) -f docker-compose.yml down -v >/dev/null; \
	$(COMPOSE) -f docker-compose.yml up -d >/dev/null; \
	./scripts/ci/wait_for_health.sh api worker beat mock-lms mock-idp >/dev/null; \
	for attempt in 1 2; do \
		echo "    down -v && up -d (attempt $$attempt)"; \
		$(COMPOSE) down -v >/dev/null; \
		$(COMPOSE) up -d >/dev/null; \
		./scripts/ci/wait_for_health.sh api worker beat mock-lms mock-idp >/dev/null; \
	done

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

# `--no-build-isolation` is the second half of `--require-hashes`. Without it,
# pip builds this package in a throwaway environment into which it fetches the
# `[build-system].requires` backend straight from PyPI, unhashed — the one
# artifact the lockfiles would not cover. With it, the build uses the
# hash-verified setuptools the line above just installed.
.PHONY: install
install: ## Install the locked dependencies and the backend, editable
	pip install --require-hashes -r requirements-dev.txt
	pip install -e . --no-deps --no-build-isolation

# Run this after editing the dependencies in pyproject.toml, and commit both
# files with the change. See docs/adr/0005-dependency-locking.md.
#
# `--allow-unsafe` is named backwards: it pins the packages pip-tools otherwise
# leaves floating because pip itself depends on them — setuptools here. Pinning
# them is the stricter behaviour, and it is what lets the build backend be
# hash-verified. pip-tools' own documentation says it will become the default.
.PHONY: lock
lock: ## Recompile requirements.txt and requirements-dev.txt from pyproject.toml
	pip-compile --quiet --generate-hashes --strip-extras --allow-unsafe \
		--output-file=requirements.txt pyproject.toml
	pip-compile --quiet --generate-hashes --strip-extras --allow-unsafe --extra dev \
		--output-file=requirements-dev.txt pyproject.toml

.PHONY: fmt
fmt: ## Apply formatting (the only target that writes to your files)
	@ruff format . && ruff check --fix .

.PHONY: up
up: ## Bring the stack up with dev wiring
	@$(COMPOSE) up -d

.PHONY: down
down: ## Tear the stack down, including volumes
	@$(COMPOSE) down -v

.PHONY: logs
logs: ## Follow stack logs
	@$(COMPOSE) logs -f

# Same two conditions as `migration-check` above: a database to talk to, and a
# DATABASE_URL that resolves from here.
.PHONY: migrate
migrate: ## Apply migrations to the running database
	@cd backend && alembic upgrade head

# Same two conditions as `migrate` above — a database to talk to, and a
# DATABASE_URL that resolves from here — plus one of its own: the script refuses
# to run unless ENVIRONMENT is `development` (docs/adr/0063). It reads `.env`
# itself, as `backend/migrations/env.py` does, so nothing has to be exported.
#
# E0-17 removed this target's tolerance for an absent `scripts/seed.py`, which is
# the move every gate in the epic README's "How CI tightens" table makes when the
# thing it guards arrives (ADR 0002). While that guard was here, deleting the seed
# script left `make seed` printing "skipped" and exiting zero, so the demo
# institution every later epic develops against could go missing with nothing red.
.PHONY: seed
seed: ## Load the demo institution, hierarchy, term, and sections
	@$(PYTHON) scripts/seed.py

.PHONY: clean
clean: ## Remove build and report artifacts
	rm -rf reports/ coverage.xml .coverage .pytest_cache .mypy_cache .ruff_cache
	rm -rf frontend/dist playwright-report/
