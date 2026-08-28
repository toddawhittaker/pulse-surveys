# 0104 — The unit and integration pass runs under xdist, with a Postgres per worker

## Context

CI's wall clock is one job. On the last green run before this change, `Test ·
pytest + invariants` took 20.6 minutes and everything else — Playwright at 2.4,
Docker at 4.6, the evals and the supply-chain gates — finished long before it.
Every pull request in the repository waits on that job, and it runs serially in
one process.

The suite provisions its own database rather than using a service container: a
session-scoped testcontainers Postgres, one alembic upgrade against it, and a
transaction rolled back per test (`tests/fixtures/database.py`). That is what
makes the pass parallelisable at all — there is no shared external database for
workers to collide in — and it is also what makes parallelism cost something,
because "session-scoped" is per pytest session, and each xdist worker is its own
session.

## Decision

The unit and integration pass runs under `pytest-xdist` with `-n 4`, in
`.github/workflows/ci.yml` and in the Makefile's `test` target, which mirrors
it. Four workers each start their own Postgres container and run their own
alembic upgrade. That duplicated setup — roughly a minute of runner time in
total, in parallel — is accepted as the price, and no machinery is built to
avoid it.

**The §4.1 invariant pass stays serial.** It is 90 tests, so there are no
minutes in it; its exit code is deliberately masked (`|| true`) and the verdict
comes from `scripts/ci/check_invariants.py` reading the JUnit XML, so a crashed
worker there could truncate the file the gate reads rather than fail loudly.
That is a bad trade for seconds, and the gate is the one thing in this pipeline
that may not be made less certain.

## Alternatives rejected

- **A template database cloned per worker.** One alembic run, then
  `CREATE DATABASE … TEMPLATE …` for each worker. It buys back most of the
  duplicated setup, but the duplicated setup is under a minute; the machinery is
  a new fixture layer with its own failure modes standing between every
  integration test and its database. If the per-worker containers turn out to
  cost more than the measurement suggests, this is the thing to build — with a
  measured number to justify it.
- **Sharding across matrix jobs.** `pytest --shard` or a matrix over test
  directories parallelises across runners instead of processes. It needs more
  runners, a coverage-combining step, and a change to the aggregate `ci` job's
  `needs` list for every shard. More configuration and more surface, for a split
  that `-n 4` already achieves inside one job.
- **Per-pull-request test selection.** Running only the tests reaching the
  changed modules is the largest possible saving and the least trustworthy: the
  selection graph follows imports, and this suite's real dependencies run
  through fixtures, migrations, and the SQL views, none of which an import graph
  sees. A pass that silently stops running a test is exactly the failure this
  repository's CI discipline exists to prevent. Deferred, and not as a
  near-term option.

## Consequences

- Test output is no longer in file order and a failure is reported with the
  worker that hit it. `-p no:randomly` is not in play here; ordering was never
  something this suite asserted, but a test that depended on running after
  another one will now fail, and that is a defect being surfaced rather than
  introduced.
- Four Postgres containers run at once on the runner. If the suite grows enough
  that memory becomes the constraint, `-n` comes down before anything else
  changes.
- Anything genuinely global to a session — a port bound, a file written to a
  fixed path, a module-level singleton assumed unique — now has four of it.
  Nothing in the suite does this today, which is why `-n 4` was reachable in one
  change; the constraint is now a live one for tests written from here on.
- `make test` and the workflow step carry the same flag, and the Makefile header
  already says the workflow is the source of truth when they drift.
