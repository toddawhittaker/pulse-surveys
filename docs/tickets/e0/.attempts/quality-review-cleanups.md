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

## Item 3 — one is-development predicate: THREE of the four converted, one disputed

**Partly worked, and stopped on the rest.** Commit `3561cb1`, objection
`docs/disputes/QUALITY-REVIEW-CLEANUPS-01.md`.

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
