# Pulse Surveys
#
# `make ci` runs the same gates as .github/workflows/ci.yml, in the same order,
# with the same tolerance for parts of the tree that do not exist yet — the
# frontend and the eval sets. The migration and test gates lost theirs in E0-04,
# and E0-18 committed the e2e specs, so all three now run unconditionally in
# both places. The Node checkers read the root `package.json`, which E0-40 split
# from `frontend/package.json`: eslint, tsc and `npm audit` run over the
# TypeScript this repository holds today, and the production build and bundle
# budget still wait for the E1 scaffold — for its `build` script now rather than
# for its manifest, since E1-02 made `frontend/` a workspace member of the root
# package and the manifest is committed (ADR 0083). If it passes here
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
	@bash -n scripts/ci/check_image_contents.sh && echo "    check_image_contents.sh parses"

.PHONY: test-gates
test-gates: test e2e evals ## Test gates: pytest, Playwright, AI evals

.PHONY: build-gates
build-gates: docker-build frontend-build ## Build gates: images, Compose health, bundle budget

# ---------------------------------------------------------------------------
# Fast gates
# ---------------------------------------------------------------------------

# The pinned Node closure. Every target below that reaches for `npx` names this
# one as a prerequisite, and none of them installs for itself.
#
# **`npx` does not fail when nothing is installed**, which is what makes this a
# gate rather than a convenience. npm 10 downloads the package and runs it, so
# `npx eslint` on a clean clone is `eslint@latest` resolved from the registry at
# run time — unpinned, no lockfile integrity, and green. `node_modules` is
# gitignored, so the clean clone is the ordinary case and not the edge one.
# CLAUDE.md pins versions and commits lockfiles and writes no exception for a
# tool that resolves its own; `.github/workflows/ci.yml` runs `npm ci` before
# every `npx` it calls, and this is the Makefile's copy of that rule.
#
# **A prerequisite rather than a line in each recipe**, because make builds a
# phony prerequisite once per invocation: `make ci` installs once here where
# four inline copies would install four times.
.PHONY: node-deps
node-deps: ## Install the pinned Node closure — prerequisite of every npx gate
	$(call banner,npm ci)
	@if [ -f package.json ]; then \
		npm ci; \
	else \
		$(call skip,no package.json at the repository root); \
	fi

.PHONY: lint
lint: node-deps ## ruff check + ruff format --check, eslint (root and frontend workspace)
	$(call banner,ruff)
	@ruff check . && ruff format --check .
	$(call banner,eslint)
	@if [ -f package.json ]; then \
		npx eslint . --max-warnings=0; \
	else \
		$(call skip,no package.json at the repository root); \
	fi
	$(call banner,eslint (frontend workspace))
	@npm run lint --workspace frontend

# mypy runs four times, and it has to: `backend/app`, `mock-lms/app`,
# `mock-idp/app` and `mock-ai/app` are all packages called `app` (SPEC §13 names
# all four), and one run over two of them stops with "Duplicate module named app"
# having checked neither. Measured, not assumed. `.github/workflows/ci.yml` runs
# the same four in the same order. See
# docs/adr/0039-the-two-app-packages-are-typechecked-in-two-runs.md.
.PHONY: typecheck
typecheck: node-deps ## mypy over backend/, mock-lms/, mock-idp/ and mock-ai/ + tsc --noEmit (root and frontend workspace)
	$(call banner,mypy)
	@mypy
	$(call banner,mypy mock-lms/app)
	@mypy mock-lms/app
	$(call banner,mypy mock-idp/app)
	@mypy mock-idp/app
	$(call banner,mypy mock-ai/app)
	@mypy mock-ai/app
	$(call banner,tsc --noEmit)
	@if [ -f package.json ]; then \
		npx tsc --noEmit; \
	else \
		$(call skip,no package.json at the repository root); \
	fi
	$(call banner,tsc --noEmit (frontend workspace))
	@npm run typecheck --workspace frontend

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
#
# Two checkers, one gate, and they see different things. The first reads the
# JUnit XML the run produced, so it catches a skip, an xfail and an empty
# collection. It cannot see a marked test that ran and asserted nothing — the XML
# carries no assertion count, so that test is counted toward the "N invariant
# test(s) ran" the first one prints. The second reads the sources and refuses
# exactly that (E0-36 item 3). The workflow's invariant step runs both, in this
# order, and a caller that dropped either half would be greener than one that
# ran it tolerantly.
.PHONY: invariants
invariants: ## Run the §4.1 invariant suite alone; a skip, an empty run and a test that asserts nothing are all failures
	$(call banner,invariant suite (SPEC §4.1))
	@mkdir -p reports
	@pytest -m invariant --junitxml=reports/invariants.xml || true
	@$(PYTHON) scripts/ci/check_invariants.py reports/invariants.xml
	@$(PYTHON) scripts/ci/check_invariant_assertions.py tests

# The integration tests start their own Postgres through testcontainers, so this
# needs a running Docker daemon but not the Compose stack.
#
# `-n 4` is pytest-xdist, mirroring the workflow's "Unit + integration with
# coverage" step. Four workers means four pytest sessions, so four
# testcontainers Postgres instances and four alembic runs — accepted for the
# wall clock, and recorded in
# docs/adr/0104-the-unit-and-integration-pass-runs-under-xdist.md. The
# `invariants` target above stays serial in both places.
.PHONY: test
test: invariants ## pytest unit + integration with coverage, four workers
	$(call banner,pytest unit + integration)
	@pytest tests/unit tests/integration -n 4 --cov=backend/app --cov-report=term-missing

.PHONY: e2e
# Enforcing since E0-18: the specs exist, so this runs the suite unconditionally
# — an empty tests/e2e fails loudly rather than skipping. It assumes the Compose
# stack is already up (`make up`) and the database migrated and seeded
# (`make migrate seed`); it does not bring Docker up itself. README.md's
# "Running the e2e suite locally" walks the full sequence.
#
# `node-deps` installs the runner rather than a comment asking you to. This
# recipe said `npm ci` was a precondition in the sentence above and then ran
# `@npx playwright test`, which on a clean clone downloads a test runner at run
# time and points it at a stack that is up, migrated and seeded — the worst of
# the three instances the E0-40 security review found, because make does not
# run comments. The browser itself is still a separate step
# (`npx playwright install chromium`), since it lands outside the repository.
e2e: node-deps ## Playwright against the Compose stack (stack must be up and seeded)
	$(call banner,Playwright e2e)
	@npx playwright test

# **This target costs money, and it is the only one here that does.** It calls
# the real provider once per eval case — about a hundred requests — because SPEC
# §9.3's floors are measured against a model and nothing else. Every other test
# command in this file reaches the loopback stub or the in-repo mock and leaves
# neither the machine nor your account.
#
# The tolerance is gone with E2-12, which lands the runner and the sets: the
# recipe used to check whether `tests/evals/runner.py` existed and print a skip
# if it did not, and skipping a gate whose code has landed is what ADR 0002 makes
# an acceptance criterion to remove. A missing runner is a red now, saying which
# module is missing.
#
# `.env` is loaded here, and only here among the test targets. The runner builds
# its gateway `live=True`, which reads AI_PROVIDER_BASE_URL,
# AI_PROVIDER_MODEL_NAME and AI_PROVIDER_API_KEY in every environment (ADR
# 0118) — and `.env` is where a developer's real provider credential lives. The
# variables are exported into the recipe's own shell and nowhere else; nothing
# here echoes one, and the runner refuses plainly, naming the variable, when the
# key is absent or blank rather than reporting a pass over a run that reached
# nothing. README.md says what it costs and when CI fires it for you.
.PHONY: evals
evals: ## AI eval runner with per-task precision/recall floors (calls the real provider; costs money)
	$(call banner,AI evals)
	@set -a; . ./.env; set +a; \
		$(PYTHON) -m tests.evals.runner --enforce-floors

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
#
# One check runs before the stack comes up at all, and it is neither E0-02's nor
# E0-03's: `check_image_contents.sh` plants a file matching each of
# `.dockerignore`'s prompt-directory re-exclusions, builds, and looks inside the
# image for them (E0-36 item 4). It sits here rather than with the others because
# it is about what the build carried, not about what the stack does once it is
# running, and because it needs the plant to happen before anything reads the
# build context.
.PHONY: docker-build
docker-build: ## Build the images and check the stack against E0-02's and E0-03's criteria
	$(call banner,docker compose build)
	@test -f .env || { echo "    .env is missing — run: cp .env.example .env"; exit 1; }
	@$(COMPOSE) build
	$(call banner,image contents)
	@./scripts/ci/check_image_contents.sh
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

# Enforcing since E1-04, and the workflow's copy of this recipe lost the same
# condition in the same change. It carried the `frontend` probe in shell — a
# `[ -f frontend/package.json ]` and a `grep` for the `build` script, with a skip
# notice in the `else` — because CLAUDE.md requires `make ci` to run the gates the
# workflow runs.
#
# The Makefile is the worse of the two to forget. A workflow that skips a gate at
# least skips it on a pull request somebody looks at; `make ci` prints its skip
# line to the one person who was told to run it before pushing, and reports
# success.
.PHONY: frontend-build
frontend-build: node-deps ## Production build + bundle budget
	$(call banner,frontend production build)
	@npm run build --workspace frontend
	$(call banner,bundle budget)
	@$(PYTHON) scripts/ci/check_bundle_size.py frontend/dist --budget ci/bundle-budget.json

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
	@if [ -f package.json ]; then \
		npm audit --audit-level=high; \
	else \
		$(call skip,no package.json at the repository root); \
	fi

.PHONY: licenses
# pip-licenses reads whatever is installed in the active environment. In CI
# that is the runtime lock plus pip-audit and pip-licenses themselves; locally
# it is your whole virtual environment, dev dependencies included. So this can
# report more packages than CI does, and never fewer.
#
# The `npm ci` this recipe used to run inline moved to `node-deps`, which is now
# its prerequisite. The behaviour is the same and `make ci` installs once rather
# than twice — this target was the only one that had the install right, and the
# other three reaching it through a prerequisite is what let it stop repeating.
licenses: node-deps ## Fail on dependencies incompatible with MIT distribution
	$(call banner,license compatibility)
	@mkdir -p reports
	@pip-licenses --format=json --with-urls > reports/py-licenses.json
	@args="--python-json reports/py-licenses.json"; \
	if [ -f package.json ]; then \
		npx license-checker-rseidelsohn --json > reports/npm-licenses.json; \
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
#
# **The order of these two is load-bearing, and so is `-c requirements.txt`.**
# The runtime compile runs first and the dev compile is then resolved *under* its
# result rather than beside it. Without the constraint they are two independent
# solves over overlapping requirement sets, free to pick different versions of
# the same package — and they did: `charset-normalizer` skewed to two versions
# during E0-13, every test passed, and only `pip-audit` saw it
# (docs/MISTAKES.md entry 25). The suite installs the dev closure and the image
# ships the runtime one, so a skew means every test in this repository is green
# against a version of a package that no deployment has.
#
# There is no `pip-compile` in .github/workflows/ci.yml to keep this in step
# with. Locking is a developer's step; CI only ever installs what was committed.
# What has to stay true across the two is that every lockfile CI installs from is
# a file this target writes, which
# `tests/unit/test_the_lockfiles_resolve_together.py` asserts in that direction.
.PHONY: lock
lock: ## Recompile requirements.txt and requirements-dev.txt from pyproject.toml
	pip-compile --quiet --generate-hashes --strip-extras --allow-unsafe \
		--output-file=requirements.txt pyproject.toml
	pip-compile --quiet --generate-hashes --strip-extras --allow-unsafe \
		-c requirements.txt --extra dev \
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
