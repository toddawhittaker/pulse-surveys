# E0-37 — Thirteen small corrections, none of which is worth a ticket alone

**ID:** E0-37
**Branch:** `e0/small-corrections`
**Depends on:** E0-05, E0-13, E0-17, E0-36, E0-38

## Context

Nine items from five tickets to begin with, each between one line and about
twenty, batched because tracking them separately costs more than fixing them.
They were [E0-20](E0-20-gate-fidelity.md) item 4 and its two "also worth
doing" entries, [E0-21](E0-21-review-debt.md) item 2,
[E0-25](E0-25-review-debt-from-e0-09-to-e0-14.md) items 2 and 3,
[E0-31](E0-31-review-debt-from-e0-17.md) items 3 and 4, and
[E0-36](E0-36-ci-gate-fidelity.md)'s security review.

**Items 10 and 11 were added on 2026-08-20**, from E0-38's third review pass.
Both are LOW, neither has a live instance, and both are defects in E0-38's
guards rather than in the gate those guards protect — which is why they are
here rather than held against that ticket.

**Items 12 and 13 were added on 2026-08-20 as well**, from
[E0-29](E0-29-review-debt-from-e0-13.md) items 1a and 1b. Both were answered
by Todd on 2026-08-18 and neither had a place to be built; Batch H is where
they land.

**The count said "seven" until 2026-08-19 and item 8 was already here**, added
without it. That is `docs/MISTAKES.md` entry 1 in the file whose own subject
is small corrections, so it is worth saying rather than quietly renumbering: a
count in a heading is a record, and this one had been false for as long as
item 8 had existed.

They are not one subject and this file does not pretend they are. What they
share is size and the fact that each is a trap already sprung once somewhere
in this repository. Every item below was re-verified open on the epic branch
on 2026-08-21; line references are current as of that check.

Read first: `docs/MISTAKES.md` entries 1, 2 and 3.

## Build order — one branch, commits grouped by file, records last

Todd batches CI waits: one branch, several coherent commits, one push, one PR.
The grouping below exists because several items share files, and because the
record-correcting items must come after the code they describe has stopped
moving (a record swept mid-round certifies claims the next commit falsifies):

1. **Item 12 first** — the largest and the only one that changes a supported
   deployment shape. If it grows past its description it leaves the batch per
   the out-of-scope rule, and finding that out first protects the rest.
2. **Items 1 and 2 together** — both touch `backend/app/db.py`, and item 2's
   constant is what item 1's environment check reads.
3. **Item 9** — `.dockerignore` plus `scripts/ci/check_image_contents.sh`,
   verified by building the image.
4. **Items 10 and 11** — both in E0-38's test module.
5. **Items 3, 4, 5, 7** — test-side corrections; item 7 is its own commit by
   its own requirement.
6. **Items 6, 8, 13 last** — documentation and ADR corrections, after the
   code commits, so each describes the tree it lands on.

Mutation verification (items 1, 2, 3, 4, 10, 11, 12) runs after the last
content commit, with each mutation confirmed to have landed before its result
is believed.

**Two items are not cosmetic and should be read before the rest** — items 1
and 9 are the ones with a confidentiality consequence, and item 9 is the
sharper: item 1 needs somebody to configure a logger by name before it bites;
item 9 is true of the image on disk today.

## Scope

### 1. `echo=False` is not what keeps SQL out of the log

`backend/app/db.py`. Narrowed from a MED during E0-04's review, and the
narrowing matters.

`Connection.__init__` sets `self._echo` from `logger.isEnabledFor(INFO)` on
`sqlalchemy.engine.Engine`, not from the `echo` flag. With that logger
explicitly at INFO and `echo=False`, both the statement and its bound
parameters are logged. Measured on the pinned SQLAlchemy 2.0.52.

**What is not true**, and was claimed during review: that wiring `LOG_LEVEL`
to the root logger opens this. SQLAlchemy pins its own `sqlalchemy` logger to
`WARNING` at import when it is `NOTSET`, so root-at-INFO leaves
`isEnabledFor(INFO)` false and logs nothing. Two of three security passes said
so independently and it was confirmed by running it.

So the residual risk is narrow: something configuring `sqlalchemy.engine` or
`sqlalchemy` **by name**, which a `dictConfig` plausibly would. It matters
because from E0-05 those bound parameters are survey answers and free-text
comments — material SPEC §10 keeps out of logs and §4.1's views and grants do
not reach.

The asymmetry is the argument for acting: `backend/alembic.ini` already pins
`[logger_sqlalchemy] level = WARNING`, so the migration side is closed and the
application side is not. The fix: the same pin applied where the engine is
built, plus `hide_parameters=True` outside development — **not** a change to
`_echoes_sql` (`db.py:72`), which is correct as written. "Outside development"
reads item 2's constant.

Also here: `tests/unit/test_db_engine_configuration.py` asserts
`not engine.echo`, which describes the ticket's wording rather than closing
the hole — it keeps passing while every statement is logged. Replace it with a
test that configures `sqlalchemy.engine` at INFO by name, runs a statement
carrying a marker value, and asserts the marker is absent from the captured
log outside development.

### 2. `DEVELOPMENT_ENVIRONMENT` is spelled in two files

`backend/app/db.py:59` and `scripts/seed.py:151` both carry the literal
`"development"`. It belongs beside the field in `backend/app/config.py`,
imported by both. E0-17 did not do it because it crosses a module boundary
that ticket did not touch — this ticket already touches `db.py` for item 1,
which is most of why the two are batched. Note: E0-18's `/docs` gating keys on
the same value; whichever lands second imports the constant rather than
spelling it a third time.

Two constants in two files with no test comparing them is the shape that
produced `docs/MISTAKES.md` entry 3's application-role incident: a fixture and
a migration naming the same role differently, where nothing noticed because
each was internally consistent.

### 3. Nothing asserts `prefix.department_id` is non-nullable

E0-05's scope says a department groups one or more prefixes and requires it
enforced as a database constraint. The column is non-nullable and does enforce
it; nothing asserts the non-nullability, so only the course-to-prefix half of
that sentence is tested. `ON DELETE RESTRICT` does not cover it — the
delete-restrict test asserts nothing about nullability, so the property could
be lost with that test reporting nothing about it, and a prefix belonging to
no department becomes writable. (The build measured what that test actually
does under the mutation: it does not stay green — it dies inside its own
seeding with `KeyError: 'department'`, because the suite's chain walkers build
an ancestor row only for a non-nullable foreign key. An error in a fixture,
naming neither the column nor the rule; the new test is what fails on the
property.)

One assertion against the catalog, in
`tests/integration/test_org_containment_schema.py`, which already holds the
containment tests.

### 4. The `"150"` course-number literal is still latent in three test modules

E0-09's dispute `E0-09-01` was a fixture pinning every seeded course to
`"150"` while the containment helper kept the shared `prefix`, so the second
course a test built violated `uq_course_prefix_id_lms_number`. Fixed there
with a per-call generator counting 100–799 that fails loudly on exhaustion.

The literal survives at `tests/integration/test_identity_schema.py:396`,
`tests/integration/test_term_calendar_schema.py:399` and
`tests/integration/test_section_date_derivation.py:411` — the same
`("course", COURSE_NUMBER_COLUMN)` default in each module's copy of the
builder table. None builds two courses today, so none is broken — the same
trap set and not yet sprung. Either draw distinct numbers per call or carry a
comment saying why a constant is safe there. **Copying E0-09's generator
wholesale is fine; copying the *section-code* pattern is not**, because
`graph_letters(1)` repeats every 26 calls.

### 5. `fresh_scope`'s docstring overclaims

`tests/conftest.py:3465`. It says the fixture never writes a second
institution. True of that method, false of the builder — `seed_row` on an
empty chain creates one freely, which is how the canonical-chain test already
produces several. Its author noticed and left it, since it was outside the fix
in hand. `docs/MISTAKES.md` entry 1's shape. Say what is true of the builder,
not only of the method.

### 6. `Institution.name`'s protection is unstated where the loader is edited

`scripts/seed.py`. `Institution.name` is matched unscoped (line 964), so a
collision would be **adopted** rather than refused — and three role
assignments are scoped to `("institution", INSTITUTION_NAME)`, so the blast
radius would exceed the prefix case E0-17 fixed. It is not reachable, because
`Pulse Demo University` is not a name a real institution uses, and that is the
whole of the protection. The reviewer checked it and deliberately did not
report it as a finding.
[ADR 0064](../../adr/0064-the-demo-seed-is-idempotent-by-natural-key.md)
carries the rule that makes it safe — every natural key is either scoped to a
row the seed created, or a root matched by a value this file invented — and
the module docstring should say **which of the two** `Institution.name` relies
on.

### 7. Delete the `ALEMBIC_DATABASE_URL` hedge

`tests/conftest.py:552` sets
`ALEMBIC_SUPERUSER_URL_VARIABLE = "ALEMBIC_DATABASE_URL"` and companion
`DB_APP_USER` / `DB_APP_PASSWORD` / `DB_NAME` entries, written before ADR 0012
chose among three options. It keeps alive the one ADR 0012 rejected: a future
`env.py` reading `ALEMBIC_DATABASE_URL` would pass the whole integration suite
while being a variable `.env.example` cannot document under
[ADR 0008](../../adr/0008-env-has-two-readers-and-the-database-credential-is-split.md)'s
reader rule. **Its own commit, saying why.**

### 8. ADR 0013's argument overstates its support

Architecture review found the ADR cites
[ADR 0010](../../adr/0010-the-celery-application-is-built-at-import-time.md)
as precedent for building the engine at import, but Celery's case is forced by
a mechanical constraint — `celery -A` resolves by attribute lookup and no form
of it calls a factory — and FastAPI's is not: `create_app()` exists precisely
so configuration failure lands in one startup. The alternative never weighed
is to build the engine inside `create_app()`, attach it to `app.state`, and
let Celery keep its module-level engine for its own reason. Separately, one of
the two reasons given for rejecting a lazy engine cites a test written in the
same ticket, which is circular; the other reason stands on its own.

**The decision may well be right. The record should stop overstating its
support.** This item corrects the argument, not the decision — if the
correction turns out to change the decision, that is a separate ticket and a
new ADR.

### 9. A `.pfx` beside a prompt reaches the runtime image, and no line stops it

Found by the independent security review of
[E0-36](E0-36-ci-gate-fidelity.md) (PR #45) and measured twice — once by the
reviewer, once by the coordinator reproducing it before acting.

`pyproject.toml` ships `prompts/**/*` as `app.ai` package data, so any
non-hidden file left in `backend/app/ai/prompts/` is packaged into the wheel
and installed into the runtime image. `.dockerignore` guards that directory
with a **denylist of suffixes**, and the file's own header admits what that
costs. The measurement, planting four files and listing the installed prompts
directory inside a built image:

| planted | reached the image |
|---|---|
| `probe.pem` | no — `backend/**/*.pem` holds |
| `probe.key` | no — `backend/**/*.key` holds |
| `probe.pfx` | **yes** |
| `probe.secret` | **yes** |

So a `signing.pfx` parked beside a prompt while debugging is in the image
today, untracked, invisible in review, with no gate that would notice. E0-36
closed the *fidelity* half — `scripts/ci/check_image_contents.sh` plants a
file per guarded suffix (`PLANTED_FILES`, line 68) and fails if any arrives —
and deliberately did not touch the *coverage* half. This is that half.

**The fix is two lines in `.dockerignore` and two entries in
`PLANTED_FILES`**, so it belongs here by size. What it is not is a decision
about the denylist itself: an allowlist for that directory — permit `*.md` and
nothing else — is the structurally correct answer and is **out of scope
here**, because ADR 0032 traded exactly that away and reversing it needs the
ADR, not a batch item. If the two lines turn out to want that argument, this
item comes out of the ticket per the out-of-scope rule below.

The same measurement applies to `mock-lms/` and `mock-idp/`, which carry the
same `*.pem` and `*.key` re-exclusions and hold the signing keys — but
neither ships package data, so nothing there is a path into an image. Named so
it is not rediscovered.

### 10. "Subject" is enforced only for a sweep rooted at the repository

`tests/unit/test_a_documentation_only_diff_does_not_run_the_expensive_gates.py`.
E0-38's inert set treats `docs/` as a build input, which is right, and its
guard covers the other half — a test that *asserts about* a file the
classifier calls inert. That guard fires only for a sweep whose root is the
repository. A module walking `REPO_ROOT / "docs" / "adr"` is invisible to both
halves: the path reader requires `is_file()` so a directory chain drops, and
the walk detector requires a root receiver so a `BinOp` drops.

No live instance. The likeliest arrival is a test asserting that every
`docs/MISTAKES.md` entry links to a real file under `docs/mistakes/` — exactly
this shape, and a reasonable thing for somebody to write. Make a sweep rooted
at a directory *inside* the inert set count as repository-wide for the purpose
of that guard.

### 11. `EXPENSIVE_GATES` is hand-kept, in the module that says inventories must not be

Same module. E0-38's second review pass found `frontend-build` guarded but
missing from `EXPENSIVE_GATES`, so the one job just guarded was the one job
the coverage test did not check. That was fixed by adding a sixth key — and
the comment added in the same commit cites `docs/MISTAKES.md` entry 35, which
says an inventory has to come from somewhere the guarded structure cannot
shrink. A seventh expensive job added to `ci.yml` is still not noticed: the
third pass added one running pytest, unguarded and wired into `ci`'s needs,
and the suite stayed green.

Direction is safe — an uninventoried job runs rather than being skipped —
which is why this is LOW and not a hole. The pattern to copy is in the same
file: the sweep detector derives its set from the tree and forces triage
through an exception set that is itself validated. Derive the candidate gates
from the workflow the same way — any job whose steps run one of the expensive
commands is a candidate, and every candidate must be inventoried or exempted
with a reason.

### 12. Cleartext to an off-machine model endpoint is permitted when no credential is set

`backend/app/config.py`, the `a_credentialled_endpoint_is_encrypted` validator
(line 408). From [E0-29](E0-29-review-debt-from-e0-13.md) item 1a, **decided
2026-08-18: refuse it.**

The validator returns early when `ai_provider_api_key` is `None` (line 435),
so a base URL naming another host over plain `http` is accepted whenever no
key is configured. That is the vLLM-in-a-cluster case, and it is documented as
supported in `README.md`, in `.env.example`, and in the validator's own
docstring — which argues for it at length under a paragraph headed "What this
deliberately does not refuse", citing ADR 0056. Student comment text crosses
that link in the clear, which is what §10 does not allow. The decision: an
encrypted transport is required whenever the model is on another host, with or
without a credential; the cluster case is served by terminating TLS at the
model or running it alongside the app.

The change is small — the early return goes, the rule becomes "off this
machine means `https`" — and four things move with it or the tree contains a
record of a rule that is no longer the rule: the validator's name (it is no
longer about credentialled endpoints), its docstring, `README.md`, and
`.env.example`.

**Done when** a settings object built with no key and an off-machine
`http://` URL raises, the same URL over `https` does not, an on-this-machine
`http://` URL still does not, and no wording anywhere in the repository still
offers the cleartext cluster deployment. The repository-wide wording check is
a grep across `README.md`, `.env.example`, `config.py` and the ADRs, run as
the last step, after every other commit in this batch.

### 13. ADR 0056 does not say why 429 and 500 are outside the fail-open set

From [E0-29](E0-29-review-debt-from-e0-13.md) item 1b, **affirmed as built
2026-08-18**: both stay outside the set. Nothing changes in the taxonomy or in
the code. What is missing is the reasoning, which lives in a review thread
rather than in the record: a rate limit is a capacity decision an operator has
to see, and a 500 means our own request is the problem, so flooring either
hides a condition that never resolves — one comment at a time.

E0-13's implementer named this as the row it expected an argument about. An
affirmed decision with its argument only in the thread that raised it is
indistinguishable, a year later, from one nobody examined. **Done when** ADR
0056 carries the reasoning for both codes and no longer reads as though the
row were unexamined. Note item 12 removes a different citation *of* ADR 0056
(the validator docstring's); check the two edits against each other before
committing either record.

## Out of scope

- **Database TLS.** Neither engine sets `sslmode`, so psycopg's default
  `prefer` applies. Fine on a private Compose network with no published port,
  and the spec says nothing about it. **E13's operator guide owns it** — noted
  so it is not rediscovered.
- Anything that turns out to be larger than it looks. An item here that grows
  past its description comes out of this ticket and gets its own, rather than
  quietly expanding the batch. Item 12 is the one to watch.

## Acceptance criteria

- [ ] With `sqlalchemy.engine` set to INFO **by name**, no bound parameter
      reaches the log outside development — asserted by capturing the log
      around a marker statement, not by reading `engine.echo`.
- [ ] `DEVELOPMENT_ENVIRONMENT` has one definition, imported by `db.py` and
      `scripts/seed.py`.
- [ ] `prefix.department_id` being made nullable turns a test red.
- [ ] The three modules holding a literal course number either draw distinct
      numbers per call or carry a comment saying why a constant is safe there.
- [ ] `fresh_scope`'s docstring says what is true of the builder.
- [ ] The seed's module docstring states which half of ADR 0064's rule
      `Institution.name` relies on.
- [ ] The `ALEMBIC_DATABASE_URL` hedge is gone, in its own commit.
- [ ] ADR 0013's argument no longer cites ADR 0010 as precedent and no longer
      rests on a circular reason. The decision is unchanged.
- [ ] A file named `*.pfx` or `*.secret` left in `backend/app/ai/prompts/`
      does not reach the runtime image, **verified by building the image and
      listing the installed directory** rather than by reading
      `.dockerignore`; `check_image_contents.sh` plants one file per newly
      guarded suffix, so deleting either new line turns the Docker gate red.
- [ ] A test module sweeping a directory inside the inert set — `REPO_ROOT /
      "docs" / "adr"` is the case to use — is reported by E0-38's guard, and
      is either run in the unconditional job or recorded in the exception set.
      Planting such a module turns the guard red naming the file.
- [ ] A seventh expensive job added to `ci.yml`, running an expensive command
      and wired into `ci`'s needs, turns the suite red unless inventoried or
      exempted with a reason; the candidate set comes from the workflow rather
      than from a hand-written dict.
- [ ] With no credential configured, an off-machine `http://`
      `ai_provider_base_url` is refused at startup; the same URL over `https`
      and an on-machine `http://` URL are accepted; no wording anywhere in the
      repository still describes the cleartext-in-a-cluster case as supported.
- [ ] ADR 0056 states why HTTP 429 and 500 are outside the fail-open set. The
      taxonomy itself does not change.
- [ ] Items 1, 2, 3, 4, 10, 11 and 12 verified by mutation, after the last
      content commit.

## Definition of done

**Tests apply** to items 1 through 5, to items 10 and 11, which are tests, and
to item 12. **Docs apply** to items 6, 8, 12 and 13. **AI evals do not apply.
Accessibility does not apply.** **Security review applies.** It is light for
most of the batch; items 1, 9 and 12 are what it is about — item 12 is a
transport rule for text SPEC §10 protects, and item 9 is true of the image on
disk today.
