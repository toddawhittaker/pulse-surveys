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
