"""The environment every migration runs in — ticket E0-04, SPEC §13.

Two things this file decides, both recorded in
docs/adr/0012-the-migration-environment-builds-its-own-superuser-connection.md.

**Which identity it connects as.** The bootstrap superuser, never the
application role. `DATABASE_URL` points at a role that is granted `CONNECT` and
deliberately cannot create a table (docs/adr/0001 line 71, docs/adr/0009), so an
`env.py` wired to it fails on the first migration with `permission denied for
schema public` — and the fix that suggests itself, granting the application role
`CREATE`, is the thing ADR 0009 exists to forbid. The connection below takes the
*address* from `DATABASE_URL` — host, port, database, driver — and the
*identity* from `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD`. One variable says
where the database is, wherever it is being run from, and the pair says who is
allowed to change its shape.

**What it imports to autogenerate against.** `app.models`, and not `app.db`.
Importing `app.db` builds an engine out of a full `Settings()`, so a migration
would refuse to run without `AI_PROVIDER_BASE_URL`, `REDIS_URL`, and three more
variables that say nothing about a schema — and neither CI's `migration-drift`
job nor the testcontainers fixture sets them.

**No Alembic-only variable is read.** Not `ALEMBIC_DATABASE_URL`, not any other
spelling. The names above are ones `.env.example` already documents and other
readers already use, and a third name that only this file read could not earn a
line in that file (ADR 0008's rule that a reader is found, never named) — which
is how `SUPERUSER_DATABASE_URL` once put a superuser credential in three
containers with every test green (`tests/unit/test_env_example_sync.py` tells
that story). An operator who has copied `.env.example` can already run a
migration; there is nothing more to set.

**This file is the third reader of `.env`**, after `Settings` and the Compose
files, and ADR 0008 is amended to say so. `alembic` is not started by `Settings`
and is usually run from `backend/`, so without this a stock checkout answers
`make migrate` with "DATABASE_URL — not set" while the same variables are sitting
in the file every other part of the system reads. The process environment wins
over the file, which is the precedence ADR 0008 records for the other two.
"""

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL, make_url

from app.config import ConfigurationError
from app.models import Base

# The repository root, from `backend/migrations/env.py`. Named rather than
# searched for: `find_dotenv()` walks up from whichever frame calls it, and a
# migration reading a different `.env` depending on where it was invoked from is
# the kind of thing nobody notices until two databases disagree.
#
# `override=False` — anything already in the environment wins, so CI's job
# variables and the test fixture's container coordinates are not replaced by a
# developer's local file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

config = context.config

# `disable_existing_loggers=False` is not cosmetic. pytest runs `alembic upgrade
# head` in its own process (tests/conftest.py), and the default would switch off
# every logger configured before this point — including the suite's own capture,
# which would then report an absence of log records as evidence of a property
# rather than as evidence of nothing having been captured.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# What autogenerate compares the live database against. Importing `app.models`
# imports every model module with it, which is what puts their tables on this
# metadata; a table whose module nobody imports is invisible here, and
# `alembic check` reports no drift for a migration nobody wrote.
target_metadata = Base.metadata

ADDRESS_VARIABLE = "DATABASE_URL"
IDENTITY_VARIABLES = ("DB_SUPERUSER", "DB_SUPERUSER_PASSWORD")


def migration_url() -> URL:
    """The database `DATABASE_URL` names, addressed as the bootstrap identity.

    No value is quoted in the failure, for the reason `app.config` gives at
    length: this message goes to a startup or CI log, and two of the three
    variables it names carry credentials. Naming the variables is enough to act
    on and is all that is safe to print.
    """
    address = os.environ.get(ADDRESS_VARIABLE, "").strip()
    identity = {name: os.environ.get(name, "").strip() for name in IDENTITY_VARIABLES}

    missing = ([ADDRESS_VARIABLE] if not address else []) + [
        name for name, value in identity.items() if not value
    ]
    if missing:
        raise ConfigurationError(
            "A migration cannot be run without these variables:\n"
            + "\n".join(f"  {name} — not set" for name in missing)
            + "\nMigrations connect as the bootstrap superuser identity, which is not the "
            "role DATABASE_URL points at (docs/adr/0009). DATABASE_URL supplies the host, "
            "port and database; DB_SUPERUSER and DB_SUPERUSER_PASSWORD supply the identity. "
            ".env.example documents all three.\n"
            "No values are shown here on purpose: this message goes to a log."
        )

    return make_url(address).set(
        username=identity["DB_SUPERUSER"],
        password=identity["DB_SUPERUSER_PASSWORD"],
    )


def run_migrations_offline() -> None:
    """Render the migrations as SQL rather than running them (`alembic --sql`).

    The two comparison settings are inert on this path — offline mode emits SQL
    without a connection, so there is nothing to compare the models against.
    They are set anyway, because this call and the one in
    `run_migrations_online` are two copies of the same configuration, and a pair
    that drifts teaches whoever reads the wrong copy the wrong rule.
    """
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against a live database.

    `NullPool` because a migration opens one connection, uses it, and exits;
    pooling would keep a superuser connection open for a process that is done.

    `compare_type=True` and `compare_server_default=True` so that changing a
    column's type or its server default in a model without writing a migration
    is drift rather than something `alembic check` shrugs at. That is the gate
    E0-04 turned on: the point is that a *model change* breaks the build, and
    `alembic check` compares only what it is told to. Both are off by default,
    and a default of "compares less" is the shape E0-20 catalogues — a gate that
    reports green while the thing it exists to detect is happening.

    The server-default half was E0-20 item 3 and landed in E0-05, which is where
    the first server defaults did (`gen_random_uuid()` on every containment
    primary key). The usual reason to leave it off is that Postgres normalises a
    `text()` default and reports drift against a model that never changed; that
    is real, and the answer when it happens is to spell the model's default the
    way the server stores it, not to switch the comparison back off.
    `tests/integration/test_migration_comparison_settings.py` asserts both
    settings on both paths, so switching one off is a red test rather than a
    silent loss of coverage.
    """
    connectable = create_engine(migration_url(), poolclass=pool.NullPool)
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
