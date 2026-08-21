# 0072 — The single-institution rule is a unique index on a constant expression

**Status:** Accepted
**Date:** 2026-08-20
**Tickets:** E0-22
**Relates to:** [ADR 0017](0017-prefix-codes-are-unique-across-the-deployment.md),
whose latent assumption this makes enforceable, and
[ADR 0067](0067-schema-drift-outside-base-metadata-is-caught-by-a-probe-schema.md),
whose probe schema this object turned out not to need.

## Context

[SPEC §8](../SPEC.md) says a deployment serves exactly one institution and
requires "a constraint permitting at most one `institution` row rather than left
as an assumption". It does not say what that constraint is made of, and Postgres
has no `CHECK` that can count its own table: a check constraint sees one row at a
time, and a subquery in one is refused. So the rule has to be spelled as
something else, and which something is a choice a reasonable engineer could make
differently.

[E0-22](../tickets/e0/E0-22-spec-questions-from-e0-05.md) anticipated that the
shape might be one `alembic check` cannot compare — it names an expression index
and a check constraint — and asked for it to be named in
[E0-33](../tickets/e0/E0-33-catalog-drift-assertions.md)'s catalog assertions if
so. That turned out not to be needed, and the measurement is below.

## Decision

A unique index on an expression that is the same value in every row:

```sql
CREATE UNIQUE INDEX uq_institution_one_row ON institution ((true));
```

The second row collides with the first, and the error names this index rather
than a prefix code three tables away. It is declared in `app.models.org` as well
as in the migration, so `alembic check` has both sides to compare. The name is
written out in both places because the `ix` template on `Base.metadata`
interpolates a column name and a textual expression has none to give it.

**`alembic check` compares it, in both directions and including the expression.**
Measured on the pinned Alembic before the shape was chosen, against a database
built by the real migration chain:

| Mutation | `alembic check` |
|---|---|
| index dropped from the database | detected — `add_index` |
| `unique` removed | detected — `unique=False to unique=True` |
| expression changed to `(name)` | detected — `expression #1 'name' to '(true)'` |
| database and model agreeing | clean, no spurious `add_index` |

The last row is the one that makes the others worth having: an object Alembic
cannot reflect is reported as missing on a clean database, which would have made
the gate fail on every run instead of on drift.

## Alternatives rejected

**A `singleton boolean` column carrying `UNIQUE` and `CHECK (singleton)`.** The
same trick in three schema objects instead of one, and it puts a column with no
meaning in the domain table, where every reader of `institution` and every seed
meets it. Its one advantage is that all three objects are ordinary members of
`Base.metadata` — but the measurement above shows the index is compared too, so
that advantage is not real, and what is left is the extra column.

**A trigger.** It refuses the row and can say anything in the message, which is
the argument for it. Rejected because a trigger is invisible to `alembic check`
in both directions and would need a catalog assertion built for it, and because
this project already has one guard trigger and the reason it needed one
([ADR 0027](0027-supervision-edges-are-policed-by-one-row-level-trigger.md)) does
not apply here: there is no graph to walk, just a row to refuse.

**Leave it in application code.** Rejected by SPEC §8, which asks for a
constraint, and by the failure mode: a rule the database does not hold is one a
seed script, a migration or a future admin console can each go around.

## Consequences

**A second institution is refused at the institution.** ADR 0017's consequence —
a second institution's `BIOL` refused by `uq_prefix_code`, naming a constraint
and no institution — is retired.

**`scripts/seed.py` cannot run beside a real institution at all.** It used to
carry its own guard for the one natural key it shares (`prefix.code`), and that
guard still does its job inside the one institution. A database holding somebody
else's institution row now refuses the seed outright, before any key is matched.

**A test that builds two containment chains gets one institution.** Every chain
these fixtures build ends at an institution, so this rule reached 41 tests about
survey windows, supervision edges and identity columns. `chain_row` in
`tests/conftest.py` hands back the institution that is already there;
`SupervisionGraph.fresh_scope` had already refused to duplicate one and named
E0-22 as the reason.

**Multi-institution is now a three-object change rather than a one-object one.**
`prefix.code` would need rescoping, `INSTITUTION_TIMEZONE` would stop being a
deployment-level setting, and this index would have to go. ADR 0017 already said
the first two; this record adds the third, and the count is the honest signal
that the change is larger than a schema edit.

**The index is not a `pg_constraint` row.** Somebody auditing the schema for
SPEC §8's "constraint" by reading `pg_constraint` finds nothing, and has to look
at `pg_index`. `\d institution` shows it either way.

**What it enforces is *at most* one, not exactly one.** Zero rows is permitted
and nothing requires a row to exist, so "exactly one" is a property of a seeded
deployment rather than of the schema — which is what SPEC §8 says too, in one
sentence that uses both phrasings. The gap is the harmless half: a deployment
with no institution has no containment tree hanging off it either.

**A rule the database enforces needs a guard in `scripts/seed.py` as well.** PR
#54's security review found the first version of this shipping without one: the
constraint refused the row as designed, as an `IntegrityError`, which is not a
`SeedError`, so it escaped `main` and an operator who pointed `make seed` at a
real database got a forty-line traceback and exit 1 where every other deliberate
refusal prints a sentence and exits 2. Nothing was written and nothing leaked,
but the error arrived in the form the rule exists to replace. `seed_containment`
now checks for a standing institution before it writes, next to the prefix guard
that was already there for the same reason, and `SeedError`'s own docstring
records the general rule.

**`SINGLE_ROW_TABLES` in `tests/conftest.py` is a hand-maintained inventory of
one.** Nothing checks it against the schema, and the four modules carrying their
own copy of `seed_row` spell `"institution"` inline rather than reading it — so
the list governs one of five copies of the rule. Left as it is while it has one
correct entry, and the note sits at the list. **Done when** a second table needs
single-row treatment: derive the list from the constraints the schema carries, or
assert it against them, and make the four copies read it.
