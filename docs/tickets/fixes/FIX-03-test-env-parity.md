# FIX-03 — Every test starts from the documented environment

**ID:** FIX-03
**Branch:** `fix/test-env-parity`
**Depends on:** nothing open (the E3-06 pull request fixes the newest instance
the declared way; this ticket removes the class)
**Lane:** heavy — `tests/conftest.py` and `tests/fixtures/` are named rows in
`.claude/heavy-lane-paths.md` (the fixture chain the §4.1 invariant suite runs
on), and any Makefile target a CI gate depends on is another.
**Security-relevant:** no production code path changes; the risk is entirely
in the fixture chain the invariant suite stands on, which is why the lane is
heavy.

## Context

A recurring CI-only failure class, recorded as `docs/MISTAKES.md` entry 40 and
the xdist-reshuffle lesson, and hit again on E3-06: application modules build
`Settings()` at import time (`backend/app/db.py`; the Celery application, per
ADR 0010), so any test that reaches one through a transitive import needs the
environment laid down first. Locally the author's shell carries `.env`'s
values, so the gap is invisible; in CI there is no `.env`, and under
`pytest-xdist` the failure appears only on a worker where no earlier test
happened to run `configured_env` first. Today's rule — each test declares
`configured_env` (`tests/fixtures/repo.py`) — depends on every author noticing
a transitive import chain, which is exactly why it keeps recurring.

## Scope

1. **The documented environment becomes automatic.** A session-scoped autouse
   arrangement in `tests/conftest.py` lays `configured_env`'s documented
   `.env.example` values (over the real database coordinates, as that fixture
   already computes them) before any test runs, on every xdist worker. The
   existing per-test `configured_env` declarations stay valid and redundant;
   nothing requires their removal in this ticket.
2. **Refusal tests get an explicit bare environment.** The tests that assert
   "an unconfigured application refuses" (the `ConfigurationError` paths) get
   an opt-out fixture that clears the application variables for that test
   alone, so the autouse baseline cannot silently green them. Find them by
   what they assert, not by grep alone.
3. **CI's configuration is reproducible locally in one command.** A make
   target (or a documented flag on `make test`) that runs the pytest gate with
   the ambient application variables scrubbed to the documented values —
   mechanising the `.env`-moved-aside dance `CONTRIBUTING.md` currently leaves
   to hand — so this class fails on the author's machine, not an hour later
   in CI.

## Acceptance criteria

1. A test that imports `app.db` (directly or transitively) with no
   `configured_env` declaration passes on a bare xdist worker: proven by
   running the suite with the ambient application variables unset, not by
   argument.
2. Every existing refusal test still fails the way it did before when its
   assertion is inverted — the opt-out fixture is exercised, and a control
   proves the baseline did not green it by accident.
3. The full suite is green in CI and locally under item 3's command, and
   `scripts/ci/check_invariants.py`'s isolated pass still runs all invariant
   tests (the autouse arrangement must not disturb collection or isolation).
4. `docs/MISTAKES.md` entry 40's rule paragraph is updated to name the
   structural fix, keeping the rule for repositories where it still applies.

## Out of scope

- Removing import-time `Settings()` from `backend/app/db.py` or the Celery
  application — a production refactor to solve a test problem, and ADR 0010
  argues the Celery half must stay import-time.
- Sweeping out the now-redundant per-test `configured_env` declarations.
