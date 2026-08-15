"""The declarative base every ORM table hangs off, the names its constraints get, and the timestamp type.

**Nothing in this module reads configuration or opens a connection**, and that
is the reason it is a module of its own rather than three lines in `app.db`.
`backend/migrations/env.py` imports it to autogenerate against, and a migration
has to run with the database variables set and nothing else: `app.db` builds an
engine out of `Settings()` when it is imported, so an `env.py` that reached the
metadata through `app.db` would refuse to run without `AI_PROVIDER_BASE_URL` and
four other variables that have nothing to do with a schema. CI's
`migration-drift` job and the testcontainers fixture both supply the database
variables alone, so that `env.py` would not run in either.
`app.db` re-exports `Base`, so `from app.db import Base` is still the import the
application writes. See
docs/adr/0012-the-migration-environment-builds-its-own-superuser-connection.md.

**Why a naming convention at all.** Without one, an unnamed constraint is named
by Postgres at `CREATE TABLE` time and the name never appears in a migration —
so a later migration that wants to drop or alter it has nothing to name it by,
and `alembic check` cannot see it either. The failure does not arrive when the
convention is missing; it arrives one schema ticket later, on a migration nobody
can write without hand-copying a server-generated identifier.

SQLAlchemy's own default covers `ix` and nothing else, so "a convention is set"
is not the question — every kind SQLAlchemy can name has to have a template, or
that kind falls through to the server.

**Why the timestamp type is here too.** `AwareDateTime` below is a schema-wide
rule (SPEC §3.1: every moment in this product is a moment in the institution
timezone), and it belongs beside the other schema-wide rule for the same reason
this module exists at all — it needs no configuration and no connection, so any
model module can import it without dragging an engine in. E0-06 is the first
ticket with timestamp columns; the ones that follow use the same type rather than
a second copy of the same guard.
"""

from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

# One template per constraint kind SQLAlchemy names (`sqlalchemy/sql/naming.py`
# maps exactly these five to Index, PrimaryKeyConstraint, CheckConstraint,
# UniqueConstraint and ForeignKeyConstraint).
#
# `column_0_N_name` rather than `column_0_name` everywhere a constraint can span
# columns: with the single-column form, two indexes on `(a, b)` and `(a, c)`
# would both want to be called `ix_t_a`, and the collision surfaces as a
# migration that cannot be applied rather than as an error in the model.
#
# `ck` interpolates `constraint_name`, so a check constraint has to be given a
# name in the model — SQLAlchemy refuses an anonymous one under this template,
# deliberately, because there would be nothing to build a name out of. That is
# the documented way to use the convention, not a gap in it.
#
# Identifiers are truncated at 63 bytes by Postgres, silently. Long table and
# column names therefore have to be chosen with the foreign-key template in
# mind, since it concatenates two table names and a column name.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class AwareDateTime(TypeDecorator[datetime]):
    """`timestamp with time zone`, refusing a value that carries no offset.

    **Postgres will not refuse one for you.** A naive datetime bound to a
    `timestamptz` column is accepted and interpreted in the session's `TimeZone`,
    so the same value means two different instants on two differently configured
    connections — and the row that results looks perfectly ordinary. SPEC §3.1
    puts every survey window at a wall-clock time in the institution timezone, so
    a moment whose offset was guessed at write time is a wrong answer that never
    announces itself.

    The check is therefore at the bind boundary, where every writer passes:
    ORM, Core, a seed script, a Celery task. SQLAlchemy wraps what is raised here
    in `StatementError`, which quotes the statement — not the offending column,
    so the message below says what was wrong with the value.

    `utcoffset()` rather than `tzinfo is not None`, because a `tzinfo` whose
    `utcoffset` returns `None` is naive in every way that matters.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """Let an aware value through; refuse a naive one before it reaches the server."""
        if value is not None and value.utcoffset() is None:
            raise ValueError(
                f"{value!r} has no UTC offset. Every timestamp in this schema is a moment, "
                "not a wall-clock reading (SPEC §3.1): Postgres would accept this and resolve "
                "it against whatever timezone the connection happens to be set to. Attach the "
                "institution timezone, or UTC, at the point the value is created."
            )
        return value


class Base(DeclarativeBase):
    """The declarative base for every table in SPEC §8.

    `metadata` carries the naming convention, which is what makes autogenerate
    emit stable constraint names instead of leaving them to Postgres.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
