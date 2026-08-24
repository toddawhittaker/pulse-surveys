# Batch: quality-review-cleanups (no ticket file; the dispatch brief is the ticket)

Branch `e0/quality-review-cleanups`. Eight behaviour-preserving cleanups from
the endorsed backend quality review. The existing suite is the only guard; no
test may be edited.

**Shell note, learned the hard way here.** The test-edit hook matches the whole
command text positionally, so a `cat > ... <<'EOF'` heredoc that merely *quotes*
a `tests/...` path in its prose is blocked as a write to a test file. Write this
attempts file with the Write tool, not from the shell.

## Item 1 — deduplicate the entry-door refusal scaffolding into `api/deps.py`

**Worked.** Commit `d7e3f95`.

`REFUSED`, `FOUND`, `refused()` and a new `landing_or_refusal()` now live in
`backend/app/api/deps.py`; `api/lti.py` and `api/auth.py` import them. The
varying parts are parameters: `door`, `cookie`, `no_role_reason`. Each door's
refusal sentence is unchanged, deliberately different from the other's.

Two things worth knowing for the later items:

- `HTMLResponse` became unused in both routers after the move, and so did
  `landing_page` / `refusal_page` / `landing_role_for`. Grep the names after a
  move; the imports stay syntactically valid and read as still-needed.
- The Care tripwire unit test asserts the flagged set **equals** its own
  `EXCEPTIONS`, so moving claim-handling code into a new module is safe only
  while that module never spells `CARE`. `deps.py` does not.

Gates: `.venv/bin/ruff format --check` on the three files (already formatted),
`.venv/bin/ruff check backend/app/api/` clean, `.venv/bin/mypy` clean (38
source files), the launch-door / web-login / OIDC-configuration modules → 148
passed, and the two landing-view invariant modules plus the Care tripwire → 37
passed.

## Item 2 — `resolve_scope` takes the Settings its caller holds

**Worked.** Commit `cb5ad50`.

Optional `settings: Settings | None = None`; `Settings()` when omitted, at call
time, uncached. Written as an explicit `Settings() if settings is None else
settings` rather than `settings or Settings()`, because the truthiness of a
pydantic model is not a thing to rely on.

**The plumbing half of the item had nothing to plumb.** The brief says to find
every production caller and pass the Settings through. There is no production
caller: `resolve_scope` is called from tests only, and the `app/api/reports.py`
that appears in a grep is a path inside a unit test's fixture list, not a file
that exists. Verified with
`grep -rn resolve_scope --include=*.py .` — every hit under `backend/` is the
definition, its `__all__` entry and one docstring cross-reference.

Gates: ruff format/check clean, mypy clean (38 files), and the four
scope/purview/org-view modules → 25 passed.

## Item 3 — one is-development predicate: RESOLVED, all four converted

**Settled in two rounds.** Three call sites in `3561cb1`, the fourth in
`aad947d` after the dispute was arbitrated. Everything below the line about
`db.py` is the state *before* the ruling and is kept because it explains why the
conversion is split across two commits.

**The ruling, and what it changed.** The objection succeeded: the detector was
amended (`7d805ae`) to accept `is_development` — imported, or read as an
attribute — as a third spelling alongside the constant. `db.py` then converted
exactly as originally briefed: `_is_development` deleted, the predicate
imported, three call sites each keeping their own polarity (echo requires
development; `hide_parameters` is its negation; the logging pin returns early in
development).

Two records in `config.py` went false the moment it landed and were corrected in
the same commit — the predicate's docstring said `db.py` did not call it yet and
pointed at the open dispute, and the constant's comment counted "all but two"
readers. It is "all but one" now, `scripts/seed.py`.

**The green was mutation-checked, because an amended detector is exactly the
thing that can be amended into blindness.** Restoring a bare `"development"`
literal to `db.py` fails the sweep naming the line it was added on; stripping
the predicate out so the module asks nothing at all fails it with "reads neither
`DEVELOPMENT_ENVIRONMENT` nor `is_development()`". Both restored from a copy
taken first.

---

### The pre-ruling state, kept for the reasoning

Objection `docs/disputes/QUALITY-REVIEW-CLEANUPS-01.md`.

`is_development(settings)` is in `backend/app/config.py` beside the constant.
`main.py`, `api/dev.py` and `api/deps.py` call it.

**`db.py` cannot be converted and stay green, and a future session should not
retry it without reading the ruling first.**
`tests/unit/test_development_environment_has_one_definition.py` has a detector
`reads_the_constant` that walks the AST of `backend/app/db.py` looking for the
identifier `DEVELOPMENT_ENVIRONMENT` as an import or an attribute. Calling
`is_development(settings)` mentions neither, so the sweep reads the conversion
as "db.py stopped asking which environment it is running in" and fails. Measured,
not reasoned:
`AssertionError: backend/app/db.py holds no 'development' literal and never reads DEVELOPMENT_ENVIRONMENT either`.

Three ways round it were considered and all three are gaming the detector: an
unused import (ruff F401), reaching the predicate as a module attribute (wrong
`attr` name), and a delegating one-line `_is_development` (leaves the
duplication). So `db.py` is reverted to its committed state and the objection is
filed.

**The forward-reference detail.** `is_development` sits at config.py line ~107
and `class Settings` is at ~345, and the module has no `from __future__ import
annotations`, so the parameter is annotated `"Settings"` in quotes. mypy is
happy; do not "tidy" the quotes away without adding the future import.

Gates: ruff format/check clean, mypy clean (38 files), and the
development-environment sweep plus config / db-engine / docs-exposure /
dev-console-exposure / dev-console / seed-target modules → 64 passed.

## Item 4 — `UuidPrimaryKey` mixin over all twenty tables

**Worked.** Commit `1e23331`.

All twenty declarations were byte-identical, confirmed by counting the exact
three-line block rather than by reading, and the twenty classes that inherit
`Base` are exactly the twenty that had one.

**`sort_order=-1` is the part a future session must not delete.** Without it the
mixin's `id` lands *last* in all twenty tables, not first: declarative copies a
mixin's `mapped_column` into each class and the copy takes a new creation order,
later than every column the class declared itself. Listing the mixin before
`Base` does not affect this. Measured both ways — 20 tables with `id` in the
wrong position without it, 0 with it.

**And `alembic check` cannot see that**, which is worth knowing next time it is
cited as the migration guard: it reported "No new upgrade operations detected"
over the schema with `id` misplaced in all twenty models. It compares columns by
name, not by position.

Ruff removed six now-unused imports (`Uuid`, `text`, `UUID`) across the model
modules; that is the linter, not a judgement call.

Gates: `alembic upgrade head && alembic check` from `backend/` → clean; ruff and
mypy clean; the five schema modules plus the seven `*_models_registered` /
column-marker modules → 94 passed.

## Item 5 — `term_value` accessor

**Worked.** Commit `ca4104b`.

`term_value(term, name)` in `app.models.term`; `_identity_and_length` and
`_term_dates` reimplemented on it, signatures unchanged. `Mapping` and `Any`
became unused in `section_codes` and ruff removed them.

Gates: ruff and mypy clean; section-code / date-derivation / term-calendar
modules → 73 passed.

## Item 6 — `OPAQUE_VALUE_BYTES` collision

**Worked.** Commit `80b0aed`. `app.lti.launch`'s 24 is now `STATE_NONCE_BYTES`;
`app.api.auth` keeps `OPAQUE_VALUE_BYTES = 32`. Nothing outside those two
modules names either, in code or in docs — grepped `.py`, `.md`, `.yml`, `.toml`.

Gates: ruff and mypy clean; launch-door and mock-LMS-launch modules → 54 passed.

## Item 7 — strict mypy over the entry doors

**Worked, and the stopping rule was never reached.** Commit `6f58518`.

Adding `app.api.*` and `app.lti.*` to the existing override produced **zero**
errors, against a stopping rule of 30. Nothing was annotated and no
`# type: ignore` was added.

**Zero errors is exactly the result a mis-scoped override also gives**
(`docs/MISTAKES.md` entry 9), so the override was executed against a planted
defect: an untyped `def` appended to `app/api/health.py` and another to
`app/lti/launch.py` both failed with `[no-untyped-def]`, and both files were
restored from copies. `mypy mock-lms/app` and `mypy mock-idp/app` still pass —
neither mock has an `api` or `lti` subpackage for the widened patterns to reach.

## Item 8 — split mock-lms `create_app`

**Worked.** Commit `5d4d6c1`. 442-line body → four locals and six
`_register_*` calls, plus the two lifted module-level helpers.

**How "pure move" was proved, rather than asserted.** The old file was kept as a
copy and both were imported side by side under `importlib`: 14 routes each, with
identical path, methods, name, summary and response class; 7 of the 14 handler
bodies byte-identical under `inspect.getsource`, and the other 7 differing by
exactly one line each — the `require_context` / `require_line_item` call site the
lift forces. Worth repeating for any later move of this shape; it costs about
twenty lines of throwaway script.

One clause of prose changed, because the move made it false: the Advantage
banner said the gradebook "is a closure over this application", and it is passed
in now. ADR 0049's own wording survives unedited.

Gates: ruff and mypy clean over `mock-lms/`; the six mock-LMS modules → 115
passed.

## Full suite

`.venv/bin/pytest -q` → **1339 passed** in 342.91s, and `pytest -m invariant -q`
→ 83 passed, 1256 deselected.

**The environment gap that looks like two regressions.** The first full run
failed `test_alembic_baseline.py::test_check_fails_when_the_models_carry_a_column_the_database_lacks`
and `test_generated_constraint_names.py::test_generated_constraint_names_follow_the_convention_and_not_postgres`,
both inside `load_base()` → `from app.db import Base` → `Settings()`, with
`OIDC_ISSUER — not set` and four more. The local `.env` predates E0-18 and carries
none of `OIDC_*`, `LTI_PLATFORM_AUTHORIZATION_ENDPOINT` or `PUBLIC_BASE_URL`.

Confirmed as pre-existing rather than assumed: a detached worktree at the branch
point `4a45d75` fails both identically, with the same `ConfigurationError`. Both
pass once the five names are supplied from `.env.example`:

    set -a; . ./.env
    . <(grep -E "^(OIDC_|LTI_PLATFORM_AUTHORIZATION_ENDPOINT|PUBLIC_BASE_URL)" .env.example)
    set +a

Use that line for any full-suite run on this machine until `.env` is refreshed.

## Follow-up round (after the ruling and the conftest split)

HEAD moved between rounds: `7d805ae` amended the sweep, `f8ba7d1` amended the
ADRs, and `0b21b9a` split the 6,634-line conftest into `tests/fixtures/`. Same
checkout, so nothing to pull — but re-read anything you are about to act on.

**Item 3 finished** — `aad947d`, written up under item 3 above.

**Four stale comments repointed at the fixtures package** — `3fb534f`. The
conftest split left four non-test files naming `tests/conftest.py` as the home
of something that had moved: both mock Dockerfiles and `mock-lms/app/main.py`
(→ `tests/fixtures/app_imports.py`) and `backend/migrations/env.py`
(→ `tests/fixtures/database.py`).

Two things worth carrying forward from it:

- **Check the destination holds the thing, not just that it exists.** Each of
  the three claims was grepped in its new module — the `sys.meta_path` insert,
  the environment set around the factory call, and
  `command.upgrade(alembic_config(), "head")` — before the comment was pointed
  at it.
- **A path substitution inside wrapped prose loses words.** Replacing a shorter
  path with a longer one in `mock-idp/Dockerfile` silently dropped "avoid. This"
  off the end of the line, because the replacement text ended where the old line
  did. Read the paragraph back after every such edit; the wrap is exactly where
  `docs/MISTAKES.md` entry 3 says surprises live.

"No executable line changed" was measured rather than eyeballed: both
Dockerfiles' non-comment lines compare byte-identical, and both Python files
parse to identical ASTs with the module docstring excluded. Twenty lines of
throwaway script, and it is the check to repeat for any comment-only commit.

**42 files under `docs/` still say `tests/conftest.py`.** Out of scope here —
records are the orchestrator's — but they are the largest remaining group, and
nothing outside `tests/` and `docs/` mentions the conftest at all any more.
