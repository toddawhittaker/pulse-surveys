# 0015 — Course level is a stored generated column, and the bands are its only authority

**Status:** Accepted
**Date:** 2026-08-14
**Tickets:** E0-05

## Context

[SPEC §8](../SPEC.md) fixes the behaviour: `course.level` derives from the course
number, is never set independently of it, and a number outside the bands is
"rejected at write time rather than stored with an absent or guessed level."
E0-05's scope fixes the class of mechanism — "a generated or trigger-maintained
column so it cannot drift from the number" — and deliberately leaves the choice
between the two open, along with what does the rejecting.

Two things about the bands make this less mechanical than it looks. The number
is `text`, because `MATH 040`'s leading zero is significant, so any arithmetic
has to cast. And the bands mix widths: three digits are valid only in `000`–`799`
and four only in `8000`–`9999`, so `850` is invalid while `8500` is doctoral, and
`0099` must not be read as `099`.

## Decision

`level` is a **stored generated column** over `lms_number`, typed as a Postgres
enum `course_level`, and `NOT NULL`. The generation expression is the single
authority for SPEC §8's bands: a number in no band derives `NULL`, and the
`NOT NULL` is what refuses the row.

There is no `CHECK` constraint restating the bands on `lms_number`.

Three details of the expression are forced rather than stylistic, and each is
commented where it appears in `backend/app/models/org.py`:

- **The enum cast is on every arm** (`'DEV'::course_level`), not around the whole
  `CASE`. A generation expression must be immutable; a run-time text→enum
  conversion goes through `enum_in`, which is only *stable* because labels can be
  added, and `CREATE TABLE` refuses it outright.
- **A nested `CASE` guards the integer cast with the width test**, so
  `lms_number::integer` is only reached for something already known to be all
  digits. `12A` derives `NULL` instead of raising.
- **The expression is spelled the way Postgres deparses it** — `>= … AND … <=`
  rather than `BETWEEN`, explicit `ELSE NULL` arms. Alembic cannot alter a
  generated column, so its entire response to a changed generation expression is
  one normalised string comparison and a `UserWarning`. Matched, that warning
  fires only on real drift instead of on every run.

## Alternatives rejected

**A `BEFORE INSERT OR UPDATE` trigger.** The only option that can raise a message
naming the number and the bands, which is a real advantage for a roster sync
defect (SPEC §8: "a defect to see"). Rejected because a generated column is
refused by the server for *anyone*, including a superuser session, a seed script
and a future admin console, while a trigger's guarantee is only as good as the
next `ALTER TABLE ... DISABLE TRIGGER`; and because the trigger has to be
written for both `INSERT` and `UPDATE`, and the version that ships is the one
that handles insert and lets the level drift later.

**A `CHECK` constraint on `lms_number` restating the bands, alongside the
derivation.** Better error messages, and the shape most reviewers expect.
Rejected because it is a second copy of SPEC §8's table that can drift from the
first while both look right, and it refuses exactly the same set of numbers the
`NOT NULL` already refuses. Duplication earns its place in this codebase on the
identity-separated read paths (SPEC §8), where the duplication *is* the
guarantee; here it would be two authorities for one rule.

**Deriving level in the application on read.** Rejected by SPEC §8 — the column
exists — and by the fact that leadership roll-ups group by it, so it has to be
in the database anyway.

**`level` as `text` with a `CHECK` naming the five values.** Rejected for the
enum: the closed set belongs in the database once, where every later view and
query reads it, rather than in a constraint each of them has to know about.

## Consequences

The error a bad number produces names the *level* column, not the number:
`null value in column "level" ... violates not-null constraint`, with the
offending row in the `DETAIL` line. That is the cost of having one authority, and
the row is in the message.

Changing the bands means a migration that rewrites the whole table, and pasting
the new deparsed expression back into the model so `alembic check` stays quiet.
`pg_get_expr` over `pg_attrdef` prints it.

**`alembic check` exits zero on generation-expression drift.** It warns and
carries on, because Alembic has no `ALTER` to emit for a computed column. So the
signal is a warning nobody's CI reads, which is precisely the shape
[E0-20](../tickets/e0/E0-20-gate-fidelity.md) collects; making that warning
meaningful is as far as E0-05 goes, and turning it into a gate is proposed
there rather than done here.

Adding a sixth level, or renaming one, is an `ALTER TYPE` in a migration rather
than an edit to a Python list, and *removing* one means recreating the type,
because Postgres has no `DROP VALUE`. That friction is wanted: the five levels
are a fact about the institution's catalogue, not a configuration knob.
