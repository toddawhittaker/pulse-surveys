# 0019 — A naive datetime is refused by the column type

**Status:** Accepted
**Date:** 2026-08-14
**Tickets:** E0-06

## Context

[SPEC §3.1](../SPEC.md) puts every survey window at a wall-clock time in the
institution timezone — opens Friday 18:00, closes Sunday 23:59:59, default
`America/New_York` — and E0-06's fourth criterion says "a naive datetime cannot
be written to any timestamp column". Neither says where that is enforced.

**Postgres will not enforce it.** Measured against the pinned server: a naive
value bound to a `timestamptz` column is accepted, resolved against the session's
`TimeZone`, and stored as whatever instant that names. The same value on two
differently configured connections is two different moments, and the row that
results looks entirely ordinary. So the rule has to hold client-side, and the
question is only where.

The criterion quantifies over *columns*, not over callers. A guard that a writer
steps around by using Core rather than the ORM does not make the sentence true,
and the writers here are plural already: the ORM, Core inserts, Alembic, the
E0-17 seed script, Celery tasks.

## Decision

`AwareDateTime` in `backend/app/models/base.py`: a `TypeDecorator` over
`DateTime(timezone=True)` whose `process_bind_param` raises when
`value.utcoffset()` is `None`. Every timestamp column in the schema uses it, and
`survey_window.opens_at` and `closes_at` are the first two.

`utcoffset()` rather than `tzinfo is not None`, because a `tzinfo` whose
`utcoffset` returns `None` is naive in every way that matters.

Measured, inserting through `Base.metadata` into the migrated database with the
session pinned to UTC: an aware value keeps its instant (`18:00-04:00` read back
as `22:00+00:00`), the same instant with its offset stripped is refused with a
`StatementError` wrapping the `ValueError`, and that same naive value written to
an unguarded `timestamptz` column in the same session is accepted.

Migrations write `sa.DateTime(timezone=True)` instead. The DDL is identical, so
`alembic check` stays silent, and a revision records the DDL it applied rather
than importing an application class that can change under it.

## Alternatives rejected

**Subclass `sqlalchemy.DateTime` and override `bind_processor`.** The obvious
shape, and it **silently ships no guard**: psycopg's `colspecs` maps
`sqltypes.DateTime` to `_PGTimeStamp`, so `dialect_impl` adapts the type away,
`_cached_bind_processor` returns `None`, and the naive value goes in. Caught by
running it rather than reading it. It does not pass E0-06's tests either — the
module goes 1 failed, 17 passed, on the assertion that the column accepted a
naive value ([E0-06-01](../disputes/E0-06-01.md)'s ruling establishes that, and
corrects an earlier claim of mine that it would have passed).

**`class AwareDateTime(TypeDecorator[datetime], DateTime)`.** Satisfies
`isinstance` against both parents and behaves like neither: `bind processor:
None`, same as above. The most dangerous of the options, because the check a
reader would run to reassure themselves is the one it passes.

**Subclass the dialect's own `_PGTimeStamp`.** This one *works*, and it is here
because it works. Measured: `isinstance(t, DateTime)` is `True`, `dialect_impl`
is the class itself so `adapt_type` leaves it alone, the bind processor runs, and
aware and naive are told apart. Rejected on portability. `_PGTimeStamp` is
private — leading underscore, not exported from
`sqlalchemy.dialects.postgresql` — and psycopg-specific, so a schema-wide
timestamp type built on it would have to be rewritten if the driver ever changed.
`TypeDecorator` is the documented, driver-independent way to intervene at the
bind boundary. Found by the E0-06-01 arbitrator, not by me; my objection had
claimed no such option existed, which was four options enumerated and called
exhaustive.

**The guard in `app/services/` or in an ORM `@validates`.** Both are bypassed by
a Core insert, which is what migrations, seed scripts and this ticket's own tests
use. Placing the rule where only one class of writer meets it answers a different
sentence than the criterion.

## Consequences

**Every timestamp column carries a decorated type, and anything reading declared
types has to resolve through it.** A `TypeDecorator` is not an instance of what
it decorates, so an `isinstance(column.type, DateTime)` check against
`Base.metadata` silently sees nothing. That is not hypothetical: it stopped
E0-06's own test fixture and cost a dispute round
([E0-06-01](../disputes/E0-06-01.md), `docs/MISTAKES.md` entry 13). Anything
later that introspects declared types — a serializer generator, an admin
scaffold, another test helper — has to unwrap first, in a loop, since decorators
nest.

**Autogenerate needs an edit on any migration touching a timestamp column.** It
renders the type as `app.models.base.AwareDateTime(timezone=True)` and emits no
import for it, so the revision does not run as generated. Observed on this
ticket's own revision; writing `sa.DateTime(timezone=True)` by hand is the fix,
and `alembic check` confirms the two agree.

**The guard covers writers that go through SQLAlchemy, and nothing else.** A
`psql` session or a `COPY` reaches the column without passing the bind boundary.
This is an application rule, not a schema constraint, and the difference is worth
knowing before someone cites it as one. Reads are unaffected: `timestamptz`
always hands back an aware value.

**The error message is the developer-facing artifact.** `StatementError` quotes
the statement but not the offending column, so the raised message says what was
wrong with the value and what to attach instead.
