"""E0-17 — the demo seed script, run the way `make seed` runs it.

These are the first fixtures here that run a *process* rather than a function.
`demo_database` and `seeded_demo` are about running the script the way `make
seed` does: it invokes `scripts/seed.py` as a program and the program reaches a
database on its own, so the fixture gives it a database of its own — created in
the session container, migrated to head, and dropped afterwards — and starts it
the way the Makefile does. They are shared rather than written in the test module
because E0-17's definition of done says the seeded institution "is also the
fixture E9 will reuse", and because `seed_environment` below is the third place
in this suite that answers "which variables could a program need to reach this
container", which is a question `docs/MISTAKES.md` entry 13 says to answer once.

The other three each arrived from something that went wrong, and each says so
where it sits. `seed_module` imports the script instead of starting it, because
the guard in it reads *resolved* configuration — the process environment with
`.env` filling in what it does not set (ADR 0063) — and a subprocess cannot be
asked about that resolution, since the fixture starting it supplies one of the two
sources and the developer's working tree supplies the other (entry 30).
`demo_databases` and `plant_in` exist so that rows can be put in front of the seed
rather than only after it: a database only the seed has written cannot pose the
question idempotency is about (entry 31).
"""

import importlib.util
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.database import (
    TEST_APP_CREDENTIAL,
    TEST_APP_USER,
    TEST_CARE_CREDENTIAL,
    TEST_CARE_USER,
    TEST_SUPERUSER,
    TEST_SUPERUSER_CREDENTIAL,
    DatabaseUnderTest,
    alembic_config,
    application_environment,
    container_url,
    environment,
    migration_environment,
    whole_environment_restored,
)
from fixtures.repo import ENV_EXAMPLE_PATH, REPO_ROOT, parse_dotenv
from fixtures.supervision import seed_row

# E0-17 — the demo seed script, run the way `make seed` runs it.
# ---------------------------------------------------------------------------

# SPEC §13 spells the path and E0-17's scope repeats it: `scripts/seed.py`.
SEED_SCRIPT_PATH = REPO_ROOT / "scripts" / "seed.py"

# How long one run may take before this stops waiting. **This file's choice**,
# and a bound rather than a requirement: E0-17 seeds an institution, a term, a
# people graph and some sections, which is thousands of rows at the outside. A
# run that passes this is a hang — most likely a script waiting on a connection
# it cannot open — and a test that reported it as a failed criterion would send
# the reader to the wrong place.
SEED_TIMEOUT_SECONDS = 180


class SeedRun(NamedTuple):
    """One execution of `scripts/seed.py`, as the shell sees it.

    `make seed` runs the script and takes its exit status as the answer, so that
    is what a test asserts against. Both streams are kept because a non-zero exit
    is only useful with the traceback that produced it.
    """

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0

    def report(self) -> str:
        """The run, rendered for a failure message, with both streams tailed."""
        return (
            f"`{' '.join(self.argv)}` exited {self.returncode}.\n"
            f"stdout:\n{self.stdout[-2000:]}\nstderr:\n{self.stderr[-2000:]}"
        )


def seed_environment(database: DatabaseUnderTest) -> dict[str, str]:
    """Every variable `scripts/seed.py` could need to reach `database`.

    Three layers, and the over-supply is the same choice `application_environment`
    above makes for the same reason. E0-17 says the script "runs as the superuser
    identity (ADR 0009)" and spells no variable for it, so the layers are:

      - every documented `.env.example` entry, at its placeholder value, so that
        a script which builds an `app.config.Settings` constructs at all — that
        object requires `AI_PROVIDER_BASE_URL` and others which have nothing to
        do with seeding. Entries whose value is an unexpanded `${...}` reference
        are dropped, because a literal `${DB_APP_USER}` is not a value; the
        entries that carry one are the database URLs, and the layers below supply
        those properly.
      - `migration_environment`, which is how everything else in this repository
        addresses a database as the bootstrap identity: `DATABASE_URL` for the
        address plus `DB_SUPERUSER`/`DB_SUPERUSER_PASSWORD` for the identity
        (ADR 0012, and `backend/migrations/env.py` reads exactly those three).
        It set a whole `ALEMBIC_DATABASE_URL` beside them until E0-37 item 7:
        that spelling is the one ADR 0012 rejected, so a seed preferring it
        would be reading a variable `.env.example` cannot document.
      - `application_environment`, so a script that connects as the application
        role, or that opens the Care connection, finds those too. It sets
        `DATABASE_URL` to the same value the layer above does, so the two agree.

    Nothing here decides which of those a seed script should use. Supplying only
    one would decide it, by failing the others.
    """
    documented = (
        parse_dotenv(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))
        if ENV_EXAMPLE_PATH.is_file()
        else {}
    )
    values = {name: value for name, value in documented.items() if "${" not in value}
    values.update(migration_environment(database))
    values.update(application_environment(database))
    return values


class DemoSeed:
    """A database of its own, and the seed script pointed at it.

    **Nothing here asserts anything.** `run` hands back what the process did and
    lets the test decide what that means, so that a script which exits non-zero
    produces a failed assertion naming the exit status rather than an error inside
    a fixture. A script that is *absent* is reported the same way, as a run that
    failed with the reason in its stderr, for the same reason: while E0-17 is
    unbuilt every test in the module should be red on its own criterion rather
    than erroring in setup on somebody else's.

    **Why a subprocess rather than an import.** E0-17's criterion is about
    `make seed`, which runs the file as a program; a script that seeds from inside
    a `if __name__ == "__main__":` block would do nothing at all on import, and a
    test that imported it would report a green run of nothing. A subprocess also
    keeps the script's own `app.*` imports out of this interpreter, where
    `sys.modules` already holds modules built against a different `DATABASE_URL`
    (see `import_app_module` above for what that costs).
    """

    def __init__(self, database: DatabaseUnderTest) -> None:
        self.database = database
        self.environment = seed_environment(database)

    def run(self, **overrides: str | None) -> SeedRun:
        """Run `scripts/seed.py` against this database and report what happened.

        `overrides` go into the child's environment last, which is how a test asks
        what the script does under an environment that looks like a deployment.
        The parent's environment is inherited underneath everything, as it is for
        `make seed`, and then overwritten: `.env` in the repository root is read by
        the process with `override=False` everywhere else in this project, so the
        values here win over a developer's local file.

        **An override of `None` removes the variable** rather than setting it to
        an empty string, since those are different questions to ask of a guard:
        `ENVIRONMENT=` is a value somebody configured to nothing, and no
        `ENVIRONMENT` at all is a context nobody configured. It is removed from
        the assembled environment, so the parent's own copy and the
        `.env.example` layer go with it.

        **Removing a variable does not make the child unable to see it.** The
        child reads `.env` too, so absence here is absence in the *process* and
        not in the resolved configuration — which is exactly the distinction
        `docs/MISTAKES.md` entry 30 was filed for. A test about which source
        supplied a value belongs against `seed_module` below, where both sources
        are arguments; this keyword is for asking what a *process* started without
        something does.
        """
        argv = (sys.executable, str(SEED_SCRIPT_PATH))
        if not SEED_SCRIPT_PATH.is_file():
            # Reported as a run that failed rather than raised from here, and the
            # difference matters to whoever reads the output: a `pytest.fail`
            # inside a fixture is an *error* in setup, while this makes every
            # test in the module fail on its own assertion, naming its own
            # criterion, with this sentence attached. 127 is what a shell answers
            # when the command is not there.
            return SeedRun(
                argv=argv,
                returncode=127,
                stdout="",
                stderr=(
                    f"{SEED_SCRIPT_PATH} does not exist, so there was nothing to run. SPEC §13 "
                    "puts the demo seed there — 'seed.py — demo institution, hierarchy, term, "
                    "sample sections' — and E0-17 is the ticket that writes it. `make seed` "
                    "skips when the file is absent, so nothing else in this repository notices."
                ),
            )
        # Named for the child rather than `environment`, which is the context
        # manager further up this file — one of them setting `os.environ` and the
        # other building a child's is exactly the pair worth not confusing.
        child_environment = {**os.environ, **self.environment}
        for name, value in overrides.items():
            if value is None:
                child_environment.pop(name, None)
            else:
                child_environment[name] = value
        try:
            # S603: the command is this interpreter and a path built from the
            # repository root. Nothing in it comes from input.
            completed = subprocess.run(  # noqa: S603
                list(argv),
                cwd=REPO_ROOT,
                env=child_environment,
                capture_output=True,
                text=True,
                timeout=SEED_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"`{' '.join(argv)}` did not finish in {SEED_TIMEOUT_SECONDS} seconds against a "
                "database with nothing in it. That is a hang rather than a failed criterion — a "
                "script waiting on a connection it cannot open looks exactly like this."
            )
        return SeedRun(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    @contextmanager
    def connect(self) -> Iterator[Any]:
        """A connection to the seeded database, as the identity that migrated it.

        The bootstrap identity, for the reason `migrated_engine` gives: these
        tests read every table including `user_identity`, which `pulse_app` is
        refused by E0-10's grants. What a read path may reach is asserted by the
        modules that own that question, over `application_engine`.
        """
        from sqlalchemy import create_engine

        engine = create_engine(self.database.superuser_url)
        try:
            with engine.connect() as connection:
                yield connection
        finally:
            engine.dispose()


@contextmanager
def migrated_demo_database(
    postgres_container: Any, provisioned_database: DatabaseUnderTest
) -> Iterator[DemoSeed]:
    """One database of its own, at head, with all three roles, then dropped.

    A database of its own because a seed script commits: it opens its own
    connection, so `db_session`'s rollback cannot reach it, and rows left in the
    session database would fail somebody else's non-vacuity guard three tickets
    from now. Dropped `WITH (FORCE)` at the end, so a connection the script left
    open does not keep it alive.

    Roles are cluster-wide, so all three URLs name the three roles ADR 0009 and
    ADR 0001 separate, exactly as `empty_database` above does.

    A context manager rather than a fixture, because two fixtures want it: one
    database per module for the ordinary case, and a factory for the tests that
    need a database the seed has **not** run against — E0-17's idempotency
    criterion is a claim about a second run meeting rows that are already there,
    and a database only the seed has ever written cannot pose it
    (`docs/MISTAKES.md` entry 31).
    """
    from alembic import command
    from sqlalchemy import create_engine, text

    name = f"e0_17_{uuid4().hex[:12]}"
    admin = create_engine(provisioned_database.superuser_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        database = DatabaseUnderTest(
            superuser_url=container_url(
                postgres_container,
                username=TEST_SUPERUSER,
                credential=TEST_SUPERUSER_CREDENTIAL,
                database=name,
            ),
            application_url=container_url(
                postgres_container,
                username=TEST_APP_USER,
                credential=TEST_APP_CREDENTIAL,
                database=name,
            ),
            care_url=container_url(
                postgres_container,
                username=TEST_CARE_USER,
                credential=TEST_CARE_CREDENTIAL,
                database=name,
            ),
        )
        # `whole_environment_restored` for the same reason `migrated_database` uses
        # it: running Alembic in process executes `migrations/env.py`, which loads
        # the repository's `.env` into `os.environ` and would otherwise leave it
        # there for every test that follows (`docs/MISTAKES.md` entry 13 — the same
        # hazard, worked around in every place that faces it).
        with whole_environment_restored(), environment(migration_environment(database)):
            command.upgrade(alembic_config(), "head")
        yield DemoSeed(database)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="module")
def demo_database(
    postgres_container: Any, provisioned_database: DatabaseUnderTest
) -> Iterator[DemoSeed]:
    """The module's own migrated database, for the ordinary case.

    Module-scoped because migrating costs seconds and the seed run itself is the
    subject: a test that wants a *second* run asks for one, which is E0-17's
    idempotency criterion and is the whole reason this hands back a runner rather
    than a database that has already been seeded.
    """
    with migrated_demo_database(postgres_container, provisioned_database) as demo:
        yield demo


@pytest.fixture(scope="module")
def demo_databases(
    postgres_container: Any, provisioned_database: DatabaseUnderTest
) -> Iterator[Callable[[], DemoSeed]]:
    """A factory for more migrated databases, each fresh, all dropped together.

    For the tests that have to put rows in front of the seed rather than after it.
    The seed's idempotency is a claim about what a second run does to rows that
    are already there, and the module database cannot pose it: everything in it
    was written by the seed, so "the rows I find" and "the rows I wrote" are the
    same set by construction — which is how a loader that adopted a *real*
    institution's prefix passed every idempotency test in this suite
    (`docs/MISTAKES.md` entry 31, ADR 0064).

    Each call is a whole `alembic upgrade head`, so ask for one per scenario and
    not per assertion.
    """
    with ExitStack() as databases:

        def another() -> DemoSeed:
            return databases.enter_context(
                migrated_demo_database(postgres_container, provisioned_database)
            )

        yield another


@pytest.fixture(scope="session")
def plant_in(metadata_tables: dict[str, Any]) -> Callable[..., Any]:
    """Insert one row, with whatever ancestors it needs, into a database and commit.

    `seed_row` above, pointed at a database of the caller's choosing instead of at
    the session one, so that a test can put rows somewhere **before** the seed
    script runs. It commits, because the script is another process and sees
    nothing that has not.

    `chain` is `seed_row`'s, so two calls sharing one chain put both rows under
    one set of ancestors — which is how a prefix and a course under it are planted
    without naming either's parent.

    Nothing here asserts. A row the schema refuses raises from the insert, and
    that is a defect in the plant rather than in the script under test; the tests
    that use this say what they were planting in their own messages.

    Positional-only for the same reason `seed_row` is: an override called `name`
    is a column on four tables here and would otherwise collide with the table
    argument.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    def plant(
        demo: DemoSeed, name: str, chain: dict[str, Any] | None = None, /, **overrides: Any
    ) -> Any:
        engine = create_engine(demo.database.superuser_url)
        try:
            with Session(bind=engine) as session:
                row = seed_row(session, metadata_tables, name, chain, **overrides)
                session.commit()
                return row
        finally:
            engine.dispose()

    return plant


@pytest.fixture(scope="module")
def seeded_demo(demo_database: DemoSeed) -> SeedRun:
    """One run of `scripts/seed.py` against that database, whatever it did.

    Deliberately does not assert that the run succeeded. E0-17's third criterion
    is that it does, and that criterion is a test rather than a precondition of
    one; a fixture that asserted it would report every other failure in the module
    as the same failure.
    """
    return demo_database.run()


# The name `scripts/seed.py` is imported under. Not `seed`, which is a plausible
# name for something else on `sys.path` to own, and not `scripts.seed`, which
# would imply a package that does not exist.
SEED_MODULE_NAME = "pulse_demo_seed"

# What `ENVIRONMENT` holds while that import runs. **A safety net, and nothing
# asserts anything about it.** `scripts/seed.py` is a program: if its `main()`
# were ever called at import time rather than under `if __name__ == "__main__"`,
# importing it here would seed whatever `.env` on this machine names, as the
# developer running the suite. A value the script's own guard refuses makes such a
# module fail at import instead, which is the cheapest way to keep that mistake
# from being destructive. It is not evidence of anything: the guard is the net
# here rather than the subject, and the tests that measure it pass their own
# configuration in.
SEED_IMPORT_ENVIRONMENT = {"ENVIRONMENT": "not-a-development-environment"}


@pytest.fixture(scope="module")
def seed_module() -> Iterator[Any]:
    """`scripts/seed.py` as a module, for the question a subprocess cannot ask.

    ADR 0063's guard reads the process environment with `.env` filling in what it
    does not set, and **which of those two supplied a value is not something the
    suite can observe from outside**: `seed_environment` above lays every
    documented `.env.example` entry into the child, and whether an untracked
    `.env` exists in the working tree decides the rest. A test written that way
    measures the machine — green in CI, where no `.env` is created, and red on
    every developer's checkout (`docs/MISTAKES.md` entry 30).

    The script answers it directly instead: `resolved_configuration(environ,
    dotenv_path)` returns the merge as a value rather than mutating `os.environ`,
    and `main` takes both as optional arguments. This fixture is how a test
    reaches those.

    Imported by path, because `scripts/` is not a package and nothing puts it on
    `sys.path`. `sys.modules` is left as it was found afterwards, the way
    `import_app_module` above leaves it.
    """
    if not SEED_SCRIPT_PATH.is_file():
        pytest.fail(
            f"{SEED_SCRIPT_PATH} does not exist, so there is nothing to import. SPEC §13 puts the "
            "demo seed there and E0-17 is the ticket that writes it."
        )

    specification = importlib.util.spec_from_file_location(SEED_MODULE_NAME, SEED_SCRIPT_PATH)
    if specification is None or specification.loader is None:
        pytest.fail(
            f"Python cannot build an import specification for {SEED_SCRIPT_PATH}, so it cannot be "
            "imported as a module. That is a defect in this fixture or a file that is not Python."
        )

    module = importlib.util.module_from_spec(specification)
    saved = sys.modules.get(SEED_MODULE_NAME)
    sys.modules[SEED_MODULE_NAME] = module
    try:
        with environment(SEED_IMPORT_ENVIRONMENT):
            specification.loader.exec_module(module)
        yield module
    finally:
        if saved is None:
            sys.modules.pop(SEED_MODULE_NAME, None)
        else:
            sys.modules[SEED_MODULE_NAME] = saved
