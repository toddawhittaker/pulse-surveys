# E0-20 — Gate fidelity: make four gates catch what they claim

**ID:** E0-20
**Branch:** `e0/gate-fidelity`
**Depends on:** E0-04

## Status — where this ticket's items went

**Not built as written. Every item below has moved.** The scope, the measurement
tables and the reasoning stay here because the batch tickets link to them rather
than copying them — a copy in six places drifts in five.

| Item | Now |
|---|---|
| 1 — the aggregate `CI` check is blind to a `migration-drift` failure | [E0-36](E0-36-ci-gate-fidelity.md) |
| 2 — the drift job's two-role shape is unasserted | [E0-36](E0-36-ci-gate-fidelity.md) |
| 3 — server-default drift | **Closed in E0-05**, and the criterion below is ticked |
| 3 — generated column expression drift | [E0-33](E0-33-catalog-drift-assertions.md) |
| 3a — check-constraint expressions and exclusion constraints | [E0-33](E0-33-catalog-drift-assertions.md) |
| 3b — roles, grants, views and functions | [E0-33](E0-33-catalog-drift-assertions.md) |
| 4 — `echo=False` is not what keeps SQL out of the log | [E0-37](E0-37-small-corrections.md) item 1 |
| also — delete the `ALEMBIC_DATABASE_URL` hedge | [E0-37](E0-37-small-corrections.md) item 7 |
| also — ADR 0013's argument overstates its support | [E0-37](E0-37-small-corrections.md) item 8 |
| out of scope — database TLS | unchanged: **E13's operator guide** |

One item arrived here from elsewhere and left again in the same move:
[E0-28](E0-28-review-debt-from-e0-15.md) item 8 routed `make docker-build`'s
health wait to this ticket. **It is closed** — the Makefile now waits on `api
worker beat mock-lms mock-idp`, matching `ci.yml`.


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

**Six open: three of the original four, plus three this ticket gained.** Item 3
landed in E0-05, which is where the first server defaults arrived; it is kept
below with what it settled, because the reasoning is worth finding. Closing it
exposed a narrower gap in the same place, which this ticket now carries as a
fourth item — a generated column's expression can drift with `alembic check`
green, because Alembic cannot `ALTER` a generated column and so warns instead of
failing.

The fifth arrived from E0-07 and E0-08 (item 3a): `alembic check` compares
neither check-constraint expressions nor exclusion constraints. That one is no
longer hypothetical — E0-06 shipped a check constraint that refused six of the
twenty start positions §2.2 seeds, and nobody found out until E0-07 wrote code
that needed one. It is the clearest evidence this ticket's subject is worth more
than its "blocks nothing" label suggests: **every serious defect found while
building E0-07 and E0-08 was sitting behind a test or a gate that was green.**

The sixth arrived from E0-10 (item 3b), and it is the widest of the three: the
drift gate reads tables and columns and nothing else, so every role, grant, view
and function that ticket added is invisible to it. `GRANT SELECT ON user_identity
TO pulse_app` and `ALTER ROLE pulse_care SUPERUSER` are each one statement, each
voids the confidentiality model, and `alembic check` calls both clean.

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

### 3. `alembic check` is blind to server-default drift — **closed in E0-05**

`backend/migrations/env.py`, both the online path and the offline path.
`context.configure` set `compare_type=True` but not `compare_server_default`,
which defaults to `False`.

From E0-05 the models carry server defaults — `gen_random_uuid()` on every
containment primary key, and later `created_at` defaulting to `now()`, flags on
`moderation_action`, the append-only `classification` and `audit_log` rows.
Editing one without writing the migration reported no drift, so the acceptance
criterion E0-04 exists to establish did not hold for that class of change.

**E0-05 turned it on**, on both paths, with the reasoning in `env.py`'s docstring
and `tests/integration/test_migration_comparison_settings.py` asserting both
settings so it cannot be switched off silently. The feared false positives from
Postgres normalising `text()` defaults did not appear against the six new tables;
if they do later, the answer is to spell the model's default the way the server
stores it, not to switch the comparison back off.

**One thing this does not reach, found while closing it.** A *generated* column
is compared differently: Alembic has no `ALTER` to emit for one, so
`_compare_computed_default` normalises both expressions, emits a `UserWarning`
when they differ, and `alembic check` still exits zero. E0-05 spells
`course.level`'s expression the way Postgres deparses it, so the warning now
fires only on real drift rather than on every run — but a warning is not a gate,
and a changed generation expression with no migration behind it still passes CI.
That is this ticket's own subject and is added to its criteria below.

### 3a. `alembic check` compares neither check-constraint expressions nor exclusion constraints

Found in E0-07, then measured in E0-08, on the pinned Alembic 1.19. Same class as
item 3 through a different door, and worth stating separately because both were
found the same way: a constraint that was wrong or missing while the gate said
clean.

E0-06 shipped `start_letter_map` with `CheckConstraint("letter ~ '^[A-Z]$'")`.
§2.2 numbers the 3-week sections 2 through 7, so **six of the twenty positions in
the spec's own Fall 2026 seed map could never be inserted**. Nothing caught it,
because nothing tried to write a numbered position until E0-07's parser existed.
Correcting the model alone would not have been caught either — autogenerate does
not compare `CheckConstraint` expressions, so E0-07's migration hand-writes the
drop and recreate in both directions.

E0-08 measured the boundary against a freshly upgraded container, mutating the
model only:

| Mutation | `alembic check` |
|---|---|
| exclusion constraint removed | **clean** |
| check-constraint expression changed | **clean** |
| check constraint renamed | detected (1.19's `checkconstraint_byname`) |
| column dropped | detected — the canary, so "clean" is distinguishable from a comparison that has gone blind |

The rename half is closed by the pinned version; the expression half is not, and
an exclusion constraint is invisible entirely. Both matter now rather than
theoretically: E0-08's enrollment overlap rule *is* an exclusion constraint and
its window-ordering rule *is* a check constraint.

The trap to name in whatever this ticket builds: **a constraint rendered into the
migration that creates its table reads like coverage and is not.** E0-08 asserts
both of its rules against a real server instead, which is the pattern to
generalise.

### 3b. `alembic check` reads no roles, no grants, no views and no functions

Found in E0-10, measured on a freshly upgraded container on the pinned Alembic
1.19. Same class as 3 and 3a and the widest of the three: those two are about a
*rule on a table* the comparison does not reach, and this is about four whole
kinds of object it never looks at. `alembic check` compares `Base.metadata`
against the database, and `Base.metadata` holds tables and columns — so
`pg_roles`, ACLs, `pg_class` entries for views and `pg_proc` are all outside it
in both directions.

E0-10 is what makes that expensive rather than merely true. Its confidentiality
guarantee is not a table at all: it is two roles, one function's owner, a handful
of grants, and the absence of any grant on `user_identity` for the two connection
roles. Mutating the database only, with a dropped column last as the canary so
that "clean" is distinguishable from a comparison that has gone blind:

| Mutation | `alembic check` |
|---|---|
| `GRANT SELECT ON public.user_identity TO pulse_app` | **clean** |
| `ALTER ROLE pulse_care SUPERUSER` | **clean** |
| the reveal function's owner set back to the migration superuser | **clean** |
| the reveal function dropped | **clean** |
| `public.section_roster` dropped | **clean** |
| a column dropped from `audit_log` | detected — the canary |

Rows one and two are each a single statement that voids the whole scheme: the
first hands every instructor screen a student's name, the second gives the Care
role every privilege in the cluster. Row three re-opens the escalation
[ADR 0043](../../adr/0043-the-reveal-function-has-an-owner-of-its-own.md) closes,
where a `SECURITY DEFINER` body reads `pg_authid`.

**What stands there today is the integration suite**, and it is genuinely
load-bearing rather than a consolation: `tests/integration/test_identity_grants.py`
provokes each refusal *and* asserts the grant model as stated out of
`has_table_privilege`, and three of its tests are `invariant`-marked so a skip is
a build failure. Two things that suite did not have were named here as worth this
ticket's attention — that nothing asserted the *owner* of a `SECURITY DEFINER`
function is not a superuser, and that nothing asserted the set of grants is
*exactly* what the migration wrote rather than a superset.

**Both were closed by E0-10's own later review round, after this paragraph was
written, and this paragraph went on asserting otherwise until E0-33 was built on
2026-08-18.** `test_no_security_definer_function_is_owned_by_a_superuser` and
`test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs` are
both live, and ADR 0043's closing paragraph records them landing. E0-33 item 3
was written from the sentence above and inherited the error; both are corrected
in the same pull request, and `docs/MISTAKES.md` entry 1 carries the instance.
What remained genuinely unasserted — a fourth grantee in an ACL, whether on a
relation or on a `SECURITY DEFINER` function; the runtime roles' privileges on
base tables other than `user_identity`; a privilege held on a *column* rather
than on a table, which is recorded in `pg_attribute.attacl` and answers neither
`has_table_privilege` nor `pg_class.relacl`; a membership granted `WITH INHERIT
FALSE`; and the file-to-catalog direction on **both the view set and the function
set** — is listed in E0-33 item 3 and is what E0-33 built.

**This sentence said "on views" until 2026-08-18 and that was a second stale
claim inside a correction.** The function half of item 3's fourth property had
not been built, and the wording quietly narrowed to match what had been
delivered — in a paragraph whose whole purpose was to stop a stale claim being
believed. `spec-conformance` found it on PR #40; the function half is built and
the sentence now names both. The column route was not in the original list at
all; `privacy-authz` found that one, and it is the sharpest of the set, because
`SELECT *` stays refused while `SELECT identity_name` succeeds.

The trap to name here is the one item 3a names in a different place: **a grant
written into the migration that creates the object reads like coverage and is
not.** Nothing re-reads it, in either direction.

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
- [x] A model whose `server_default` changed without a migration fails
      `alembic check`, or `env.py` records why that is deliberate. **Done in
      E0-05**, and verified by mutation both ways: with the flag on, adding a
      `server_default` to `institution.name` fails `alembic check`; with the
      online path's flag removed, the same drift reports "No new upgrade
      operations detected".
- [ ] A model whose *generated* column expression changed without a migration
      fails something. It does not today: `alembic check` warns and exits zero
      (see item 3). The cheap form is a test that reads `pg_get_expr` off the
      migrated database and compares it, normalised, with the model's
      `Computed` text — one assertion, and it is the only drift signal a
      generated column has.
- [ ] A model whose *check-constraint expression* changed without a migration
      fails something, and a *removed exclusion constraint* fails something.
      Neither does today (see item 3a), and both rules exist in E0-08's schema
      now. The cheap form is the one E0-08 already uses for its own two: read
      the constraint out of the catalog — `get_check_constraints`, and `pg_constraint`
      for `contype = 'x'` — and assert against it, rather than trusting the gate.
      Do not accept "it is in the creating migration" as coverage.
- [ ] A database whose **roles, grants, view set or function set** drift from
      what the migrations wrote fails something. None of it does today (see item
      3b): `GRANT SELECT ON user_identity TO pulse_app` and `ALTER ROLE
      pulse_care SUPERUSER` are each one statement that voids E0-10's whole
      scheme with `alembic check` clean. The cheap form is the one E0-10 already
      uses for the rules it does assert — read the catalog and compare — extended
      to the two properties it has no assertion for: that the owner of every
      `SECURITY DEFINER` function in `public` is not a superuser, and that the
      grant set is *exactly* what the migrations wrote rather than a superset.
      Do not accept "it is in the creating migration" as coverage.
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
