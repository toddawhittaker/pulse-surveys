# E0-20 — Gate fidelity: make four gates catch what they claim

**ID:** E0-20
**Branch:** `e0/gate-fidelity`
**Depends on:** E0-04

## Context

E0-04 turned on the `migration-drift` and `test` gates. Its reviewer pass and
three security passes found no defect in what shipped — every finding was about
what the build can *catch*. Four of them are collected here because they are one
subject: a gate that reports green while the thing it exists to detect is
happening.

That is `docs/MISTAKES.md` entry 2 — behaviour shipped with nothing asserting it,
the entry with the highest catch count in the file — applied to the gates
themselves rather than to application code.

None of these blocks anything. All four were found on PR #17 and are recorded
here rather than fixed there, because the reviewer pass reports and the merge
decision chooses. Sizes differ a lot: the first is a few lines, the last is a
judgement call about logging that nothing yet depends on.

Read first: `.github/workflows/ci.yml`, `docs/adr/0002-ci-gates-ship-tolerant.md`,
and `docs/MISTAKES.md` entries 2 and 3.

## Scope

### 1. The aggregate `CI` check cannot see a `migration-drift` failure

`.github/workflows/ci.yml`, the `ci` job's verdict step. This is the single
required check branch protection points at, and it is the most consequential of
the four.

`ci` needs `[fast-gate, test, e2e, evals, docker, frontend-build, supply-chain]`.
`migration-drift`, `lint-python`, `lint-frontend` and `ci-selftest` reach it only
through `fast-gate`. A job whose dependency **failed** is reported `skipped`, not
`failure`. So a real `migration-drift` failure cascades: `fast-gate` is skipped,
everything downstream of it is skipped, `join(needs.*.result)` is
`skipped,skipped,…`, the step's `grep -qE 'failure|cancelled'` matches nothing,
and it prints "All gates green" and exits 0.

The step's own comment says "tolerant jobs report success, so this stays honest
as the tree fills in" — which is true, and is why `skipped` was not treated as a
failure. The two are now indistinguishable, and the tolerant case is shrinking
while the failure case just became reachable.

Treat `skipped` as a failure among `ci`'s needs, or put the four fast jobs in
`ci`'s `needs` directly, or both. Whatever the fix, it needs a test:
`scripts/ci/test_ci_scripts.py` and `tests/unit/test_ci_health_gate.py` are the
two existing patterns for asserting on the workflow.

### 2. The drift job's two-role shape has nothing asserting it

`.github/workflows/ci.yml`, the `migration-drift` job. E0-04's own context
required this: the job must use "the same *database* shape the stack deploys,
application role included, or `alembic check` cannot see a grant problem."

Demonstrated during review: delete the "Provision the application role" step and
revert the job's `DATABASE_URL` to `postgres:postgres@localhost:5432/pulse_ci`,
and all 86 unit tests still pass and the drift job itself still passes — because
a superuser can create tables. So ADR 0012's stated consequence, "CI's drift gate
now fails if `env.py` starts using `DATABASE_URL`'s identity", is a convention
rather than a guarantee.

The `env.py` half *is* guarded: reverting its `.set(username=…, password=…)`
turns three integration tests red and errors five more. Only the CI job's half is
unasserted.

### 3. `alembic check` is blind to server-default drift

`backend/migrations/env.py`, both the online path and the offline path.
`context.configure` sets `compare_type=True` but not `compare_server_default`,
which defaults to `False`.

From E0-05 the models carry server defaults — `created_at` defaulting to `now()`,
flags on `moderation_action`, the append-only `classification` and `audit_log`
rows. Editing one without writing the migration reports no drift, so the
acceptance criterion E0-04 exists to establish does not hold for that class of
change.

Either turn it on, or write down why not. The usual reason to leave it off is
false positives from Postgres normalising `text()` defaults — that is a real
cost, and if it is the answer it belongs in `env.py`'s docstring, because
otherwise a later ticket hits it and re-derives the whole question.

**Whoever builds E0-05 should settle this first**, since E0-05 is where the first
server default lands.

### 4. `echo=False` is not what keeps SQL out of the log

`backend/app/db.py`. Narrowed from a MED during review, and the narrowing matters
— read it before acting.

`Connection.__init__` sets `self._echo` from `logger.isEnabledFor(INFO)` on
`sqlalchemy.engine.Engine`, not from the `echo` flag. With that logger explicitly
at INFO and `echo=False`, both the statement and its bound parameters are logged.
Measured on the pinned SQLAlchemy 2.0.52.

**What is not true**, and was claimed during review: that wiring `LOG_LEVEL` to
the root logger opens this. SQLAlchemy pins its own `sqlalchemy` logger to
`WARNING` at import when it is `NOTSET`, so root-at-INFO leaves
`isEnabledFor(INFO)` false and logs nothing. Two of the three security passes
said so independently, and it was confirmed by running it.

So the residual risk is narrow: something configuring `sqlalchemy.engine` or
`sqlalchemy` **by name**, which a `dictConfig` plausibly would. It matters
because from E0-05 those bound parameters are survey answers and free-text
comments — material SPEC §10 keeps out of logs and §4.1's views and grants do not
reach.

The asymmetry is the argument for doing something: `backend/alembic.ini` already
pins `[logger_sqlalchemy] level = WARNING`, so the migration side is closed and
the application side is not. The cheap fix is the same pin plus
`hide_parameters=True` outside development — not a change to `_echoes_sql`, which
is correct as written.

Also here: `tests/unit/test_db_engine_configuration.py` asserts `not engine.echo`,
which describes the ticket's wording rather than closing the hole. It keeps
passing while every statement is being logged.

## Also worth doing, smaller

- **Delete the `ALEMBIC_DATABASE_URL` hedge.** `tests/conftest.py` sets
  `ALEMBIC_SUPERUSER_URL_VARIABLE = "ALEMBIC_DATABASE_URL"` and companion
  `DB_APP_USER`/`DB_APP_PASSWORD`/`DB_NAME` entries, written before ADR 0012
  chose among three options. It keeps alive the one ADR 0012 rejected: a future
  `env.py` reading `ALEMBIC_DATABASE_URL` would pass the whole integration suite
  while being a variable `.env.example` cannot document under ADR 0008's reader
  rule. Its own commit, saying why.
- **ADR 0013's argument, not its decision.** Architecture review found the ADR
  cites ADR 0010 as precedent for building the engine at import, but Celery's
  case is forced by a mechanical constraint (`celery -A` resolves by attribute
  lookup; no form of it calls a factory) and FastAPI's is not — `create_app()`
  exists precisely so configuration failure lands in one startup. The
  alternative never weighed: build the engine inside `create_app()`, attach it to
  `app.state`, and let Celery keep its module-level engine for its own reason.
  Separately, one of the two reasons given for rejecting a lazy engine cites a
  test written in the same ticket, which is circular; the other reason stands on
  its own. **The decision may well be right — the record should stop
  overstating its support.**

## Out of scope

- **Database TLS.** Neither engine sets `sslmode`, so psycopg's default `prefer`
  applies: TLS optional, certificate unverified. Fine on a private Compose
  network with no published port, and the spec says nothing about it. It matters
  before a managed or remote Postgres, because that connection carries the
  superuser credential during migrations. `?sslmode=verify-full` on
  `DATABASE_URL` would reach both engines with no code change, since query
  parameters survive `make_url(...).set(...)`. **E13's operator guide owns this**
  — noted here only so it is not rediscovered.
- Anything about what the gates check. This ticket changes whether they can
  detect it, not what "it" is.

## Acceptance criteria

- [ ] A deliberately failing `migration-drift` makes the aggregate `CI` check
      report failure. Verify by pushing a real drift to a scratch branch, not by
      reading the YAML.
- [ ] Deleting the drift job's provisioning step, or repointing its
      `DATABASE_URL` at the superuser, fails something.
- [ ] A model whose `server_default` changed without a migration fails
      `alembic check`, or `env.py` records why that is deliberate.
- [ ] With `sqlalchemy.engine` set to INFO by name, no bound parameter reaches
      the log outside development.
- [ ] Every fix above is verified by mutation — reintroduce the defect and watch
      something go red. `docs/MISTAKES.md` entry 2's rule, applied to its own
      subject matter.

## Definition of done

**Tests apply**, and they are most of the ticket.

**Docs apply** only if item 3 or 4 is answered with "deliberately not" — then the
reason goes in the module docstring, not in a commit message.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light** — item 4 is the only one with a
confidentiality surface, and its analysis is above.
