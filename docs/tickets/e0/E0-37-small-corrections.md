# E0-37 — Nine small corrections, none of which is worth a ticket alone

**ID:** E0-37
**Branch:** `e0/small-corrections`
**Depends on:** E0-05, E0-13, E0-17, E0-36

## Context

Nine items from five tickets, each between one line and about twenty, batched
because tracking them separately costs more than fixing them. They were
[E0-20](E0-20-gate-fidelity.md) item 4 and its two "also worth doing" entries,
[E0-21](E0-21-review-debt.md) item 2, [E0-25](E0-25-review-debt-from-e0-09-to-e0-14.md)
items 2 and 3, [E0-31](E0-31-review-debt-from-e0-17.md) items 3 and 4, and
[E0-36](E0-36-ci-gate-fidelity.md)'s security review.

**The count said "seven" until 2026-08-19 and item 8 was already here**, added
without it. That is `docs/MISTAKES.md` entry 1 in the file whose own subject is
small corrections, so it is worth saying rather than quietly renumbering: a count
in a heading is a record, and this one had been false for as long as item 8 had
existed.

They are not one subject and this file does not pretend they are. What they share
is size and the fact that each is a trap already sprung once somewhere in this
repository. Two of them land in the same two files.

**Two items are not cosmetic and should be read before the rest** — items 1 and 9
are the ones with a confidentiality consequence, and item 9 is the sharper of the
two. Item 1 needs somebody to configure a logger by name before it bites. Item 9
is true of the image on disk today.

Read first: `docs/MISTAKES.md` entries 1, 2 and 3.

## Scope

### 1. `echo=False` is not what keeps SQL out of the log

`backend/app/db.py`. Narrowed from a MED during E0-04's review, and the narrowing
matters.

`Connection.__init__` sets `self._echo` from `logger.isEnabledFor(INFO)` on
`sqlalchemy.engine.Engine`, not from the `echo` flag. With that logger explicitly
at INFO and `echo=False`, both the statement and its bound parameters are logged.
Measured on the pinned SQLAlchemy 2.0.52.

**What is not true**, and was claimed during review: that wiring `LOG_LEVEL` to
the root logger opens this. SQLAlchemy pins its own `sqlalchemy` logger to
`WARNING` at import when it is `NOTSET`, so root-at-INFO leaves
`isEnabledFor(INFO)` false and logs nothing. Two of three security passes said so
independently and it was confirmed by running it.

So the residual risk is narrow: something configuring `sqlalchemy.engine` or
`sqlalchemy` **by name**, which a `dictConfig` plausibly would. It matters
because from E0-05 those bound parameters are survey answers and free-text
comments — material SPEC §10 keeps out of logs and §4.1's views and grants do not
reach.

The asymmetry is the argument for acting: `backend/alembic.ini` already pins
`[logger_sqlalchemy] level = WARNING`, so the migration side is closed and the
application side is not. The cheap fix is the same pin plus `hide_parameters=True`
outside development — **not** a change to `_echoes_sql`, which is correct as
written.

Also here: `tests/unit/test_db_engine_configuration.py` asserts `not engine.echo`,
which describes the ticket's wording rather than closing the hole. It keeps
passing while every statement is being logged.

### 2. `DEVELOPMENT_ENVIRONMENT` is spelled in two files

`backend/app/db.py` line 59 and `scripts/seed.py` line 129 both carry the
literal. It belongs beside the field in `backend/app/config.py`, imported by
both. E0-17 did not do it because it crosses a module boundary that ticket does
not touch — **this ticket already touches `db.py` for item 1**, which is most of
why the two are batched.

Two constants in two files with no test comparing them is the shape that produced
`docs/MISTAKES.md` entry 3's application-role incident: a fixture and a migration
naming the same role differently, where nothing noticed because each was
internally consistent.

### 3. Nothing asserts `prefix.department_id` is non-nullable

E0-05's scope says a department groups one or more prefixes and requires it
enforced as a database constraint rather than an application convention. The
column is non-nullable and does enforce it; nothing asserts the non-nullability,
so only the course-to-prefix half of that sentence is tested.

`ON DELETE RESTRICT` does not cover it — the delete-restrict test passes whether
or not the column is nullable, so a later change making it nullable turns nothing
red and a prefix belonging to no department becomes writable.

One assertion, in the module that already holds the containment tests.

### 4. The `"150"` course-number literal is still latent in three test modules

E0-09's dispute `E0-09-01` was a fixture pinning every seeded course to `"150"`
while the containment helper kept the shared `prefix`, so the second course a
test built violated `uq_course_prefix_id_lms_number`. Fixed there with a per-call
generator counting 100–799 that fails loudly on exhaustion.

The literal survives in `tests/integration/test_identity_schema.py`,
`tests/integration/test_section_date_derivation.py` and
`tests/integration/test_term_calendar_schema.py`. None builds two courses today,
so none is broken — the same trap set and not yet sprung. Confirmed still present
on this branch.

Either draw distinct numbers per call or carry a comment saying why a constant is
safe there. **Copying E0-09's generator wholesale is fine; copying the
*section-code* pattern is not**, because `graph_letters(1)` repeats every 26
calls.

### 5. `fresh_scope`'s docstring overclaims

`tests/conftest.py`. It says the fixture never writes a second institution. True
of that method, false of the builder — `seed_row` on an empty chain creates one
freely, which is how the canonical-chain test already produces several. Its
author noticed and left it, since it was outside the fix in hand.
`docs/MISTAKES.md` entry 1's shape.

Say what is true of the builder, not only of the method.

### 6. `Institution.name`'s protection is unstated where the loader is edited

`scripts/seed.py`. `Institution.name` is matched unscoped, so a collision would
be **adopted** rather than refused — and three role assignments are scoped to
`("institution", INSTITUTION_NAME)`, so the blast radius would exceed the prefix
case E0-17 fixed.

It is not reachable, because `Pulse Demo University` is not a name a real
institution uses, and that is the whole of the protection. The reviewer checked
it and deliberately did not report it as a finding. [ADR 0064](../../adr/0064-the-demo-seed-is-idempotent-by-natural-key.md)
now carries the rule that makes it safe — every natural key is either scoped to a
row the seed created, or a root matched by a value this file invented — and the
module docstring should say **which of the two** `Institution.name` relies on.

### 7. Delete the `ALEMBIC_DATABASE_URL` hedge

`tests/conftest.py` sets `ALEMBIC_SUPERUSER_URL_VARIABLE = "ALEMBIC_DATABASE_URL"`
and companion `DB_APP_USER` / `DB_APP_PASSWORD` / `DB_NAME` entries, written
before ADR 0012 chose among three options. It keeps alive the one ADR 0012
rejected: a future `env.py` reading `ALEMBIC_DATABASE_URL` would pass the whole
integration suite while being a variable `.env.example` cannot document under
[ADR 0008](../../adr/0008-env-has-two-readers-and-the-database-credential-is-split.md)'s
reader rule.

**Its own commit, saying why.**

### 8. ADR 0013's argument overstates its support

Architecture review found the ADR cites [ADR 0010](../../adr/0010-the-celery-application-is-built-at-import-time.md)
as precedent for building the engine at import, but Celery's case is forced by a
mechanical constraint — `celery -A` resolves by attribute lookup and no form of
it calls a factory — and FastAPI's is not: `create_app()` exists precisely so
configuration failure lands in one startup. The alternative never weighed is to
build the engine inside `create_app()`, attach it to `app.state`, and let Celery
keep its module-level engine for its own reason. Separately, one of the two
reasons given for rejecting a lazy engine cites a test written in the same
ticket, which is circular; the other reason stands on its own.

**The decision may well be right. The record should stop overstating its
support.** This item corrects the argument, not the decision — if the correction
turns out to change the decision, that is a separate ticket and a new ADR.

### 9. A `.pfx` beside a prompt reaches the runtime image, and no line stops it

Found by the independent security review of [E0-36](E0-36-ci-gate-fidelity.md)
(PR #45) and measured twice — once by the reviewer, once by the coordinator
reproducing it before acting.

`pyproject.toml` ships `prompts/**/*` as `app.ai` package data, so any non-hidden
file left in `backend/app/ai/prompts/` is packaged into the wheel and installed
into the runtime image. `.dockerignore` guards that directory with a **denylist of
suffixes**, and the file's own header admits what that costs: "a suffix nobody
thought of is in the context until someone remembers to add it."

The measurement, taken by planting four files and listing the installed prompts
directory from inside a built image:

| planted | reached the image |
|---|---|
| `probe.pem` | no — `backend/**/*.pem` holds |
| `probe.key` | no — `backend/**/*.key` holds |
| `probe.pfx` | **yes** |
| `probe.secret` | **yes** |

So a `signing.pfx` parked beside a prompt while debugging is in the image today,
untracked, invisible in review, with no line to delete and no gate that would
notice. E0-36 closed the *fidelity* half of this — `scripts/ci/check_image_contents.sh`
now plants a file per guarded suffix and fails if any arrives — and deliberately
did not touch the *coverage* half, because adding patterns changes what is
guarded rather than whether the guard works. This is that half.

**The fix is two lines in `.dockerignore` and two entries in `PLANTED_FILES`**, so
it belongs here by size. What it is not is a decision about the denylist itself:
an allowlist for that directory — permit `*.md` and nothing else — is the
structurally correct answer and is **out of scope here**, because ADR 0032 traded
exactly that away and reversing it needs the ADR, not a batch item. If the two
lines turn out to want that argument, this item comes out of the ticket per the
out-of-scope rule below.

The same measurement applies to `mock-lms/` and `mock-idp/`, which carry the same
`*.pem` and `*.key` re-exclusions and hold the signing keys — but neither ships
package data, so nothing there is a path into an image. Named so it is not
rediscovered.

## Out of scope

- **Database TLS.** Neither engine sets `sslmode`, so psycopg's default `prefer`
  applies. Fine on a private Compose network with no published port, and the spec
  says nothing about it. **E13's operator guide owns it** — noted so it is not
  rediscovered.
- Anything that turns out to be larger than it looks. An item here that grows
  past its description comes out of this ticket and gets its own, rather than
  quietly expanding the batch.

## Acceptance criteria

- [ ] With `sqlalchemy.engine` set to INFO **by name**, no bound parameter
      reaches the log outside development.
- [ ] `DEVELOPMENT_ENVIRONMENT` has one definition, or a test asserts the two
      copies agree.
- [ ] `prefix.department_id` being made nullable turns a test red.
- [ ] The three modules holding a literal course number either draw distinct
      numbers per call or carry a comment saying why a constant is safe there.
- [ ] `fresh_scope`'s docstring says what is true of the builder.
- [ ] The seed's module docstring states which half of ADR 0064's rule
      `Institution.name` relies on.
- [ ] The `ALEMBIC_DATABASE_URL` hedge is gone, in its own commit.
- [ ] ADR 0013's argument no longer cites ADR 0010 as precedent and no longer
      rests on a circular reason. The decision is unchanged.
- [ ] A file named `*.pfx` or `*.secret` left in `backend/app/ai/prompts/` does
      not reach the runtime image, **verified by building the image and listing
      the installed directory** rather than by reading `.dockerignore`.
- [ ] `scripts/ci/check_image_contents.sh` plants one file per newly guarded
      suffix, so deleting either new line turns the Docker gate red.
- [ ] Items 1, 2, 3 and 4 verified by mutation.

## Definition of done

**Tests apply** to items 1 through 5.

**Docs apply** to items 6 and 8.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light**, and item 1 is the only one it is about.
