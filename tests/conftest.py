"""Fixtures shared by the test suite.

The tests under `tests/unit/` for tickets E0-01 and E0-02 are written from those
tickets' acceptance criteria, not from the implementation. Where a criterion
needs a name the ticket does not spell — an environment variable, a JSON key —
the choice is made once, in a named constant, and marked as the test's choice so
it is cheap to change.

`.env` has two readers from E0-02 onwards: `app.config.Settings` and Compose.
The helpers below parse both sides of that, and they parse the Compose files
once, here, so that two test modules cannot end up disagreeing about what a
Compose file says.

E0-03 adds two fixtures of a different kind — `import_app_module` and
`celery_application_in`. They are here for the same reason as the parsers: the
unit tests and the integration test both need them, and two copies of a rule
about how a module is imported, or about where a Celery application is found,
could drift apart and leave the two suites checking different things.

E0-04 adds the database fixtures, at the bottom of this file: a testcontainers
Postgres on the image the stack deploys, the application role provisioned into
it, `alembic upgrade head` applied once per session, and a transaction-rollback
fixture for per-test isolation. They are the ticket's own deliverable, so what
they choose and what they refuse to choose is written on each one. Two things
are worth knowing before using them:

  - **The container carries production's role shape**, a bootstrap superuser and
    a separate application role that cannot create a table, because
    [ADR 0009](../docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
    names this fixture as the owner of its own provisioning. Without it, tests
    pass under privileges no deployment has.
  - **The environment a migration runs under is assembled in one function**,
    `migration_environment` below, and the name it invents for the Alembic
    superuser URL is **this suite's choice** rather than the ticket's — E0-04
    leaves the mechanism open between a `Settings` field, an Alembic-only
    variable, and something `env.py` assembles. So the function supplies the
    container's coordinates under every spelling those three could read, and
    changing the name is one constant.

E0-07 adds one more, `section_codes`, at the very bottom. It is here rather than
in a test module because two modules ask the same question of it — the parsing
unit tests and the derivation integration tests — and E0-07 spells the service's
*file* and none of its callables, so "which function parses a code" is a rule
that would drift if it were written twice (`docs/MISTAKES.md` entry 13). What it
does and what it deliberately refuses to decide is written on the class.

E0-14 adds `mock_platform` and `mock_platforms`, below `section_codes`, plus the
JSON Web Signature helpers they hand back results in. Its definition of done asks
for "a reusable fixture that mints a signed launch — E1's launch-validation tests
depend on it, so its interface matters", so the fixture is the ticket's own
deliverable rather than a convenience, and it lives here for the reason every
other shared thing does: E1 will import it, and a second copy would drift. Like
`SectionCodeService`, it discovers the mock platform rather than naming its
parts — what it discovers and what it refuses to decide is written on the class.

E0-15 extends that class rather than adding another, because its subject is the
same platform: the LTI Advantage services it now serves are reached through the
claims a launch carries, which is how a tool reaches them and which means no URL
is hardcoded here either. `link_relations_in` and `instant_of` sit beside
`signed_launch` and exist so that a test module can exercise the paging-header
parser and the timestamp comparison without importing this file by name.
E0-09 adds `supervision_graph`, at the very bottom, for the same reason and with
one more of its own. Two modules ask it the same question — the schema tests and
the Hypothesis properties over generated graphs — and E0-09's definition of done
asks for "a fixture builder for the assistant-dean shape that E9 will reuse", so
a copy in a test module would be a copy E9 has to find. It carries a fourth copy
of the row-seeding helper that `tests/integration/test_org_containment_schema.py`,
`test_term_calendar_schema.py` and `test_identity_schema.py` each hold; merging
the other three is a refactor that would edit three tickets' modules, so this one
is written here rather than imported from any of them. What the builder refuses
to decide — what a scope node is made of, and how a role is spelled — is written
on the class.

E0-10 adds three, all at the bottom. `seed_rows` sits beside `supervision_graph`
and is built out of the same helper: its Care reveal can only be asserted against
an identity that exists, and the seeding it needs is "one row of whatever table,
with its ancestors" rather than a graph shape. `committed_rows` and
`care_service_environment` exist for the one thing the rest of this file cannot
do — `app.services.safety` opens its **own** connection from `CARE_DATABASE_URL`,
so it sees nothing written inside `db_session`'s transaction, and a test that
calls it needs committed rows and an environment pointing at this container. The
Care role itself is provisioned beside the application role now, mirroring
`scripts/db-init/02-care-role.sh`: a login and no grant.

E0-16 adds `mock_idp` and `mock_idps` below those, and they are the mock
LMS's fixtures again for the other entry door (SPEC §2, §9.2). Two things about
them are worth knowing before use. They **share** what the two mocks genuinely
have in common rather than copying it — the meta-path finder that resolves a
second package called `app`, the fresh-import machinery, the RS256 verifier and
the form reader are one implementation each, with the per-ticket failure messages
staying with the ticket (`docs/MISTAKES.md` entry 13). And, like `MockPlatform`,
the provider is **driven the way a client drives one**: the endpoints come out of
the discovery document, the identities come out of the login form, and the one
thing E0-16 does not say — how a client learns the seeded `client_id` and
redirect URI — is looked for in three places and then failed on by name rather
than guessed at.

Two things arrived with the review round. That question is settled: the provider
publishes a registration document, and [ADR 0058](../docs/adr/0058-the-registration-document-is-the-contract-between-the-mocks.md)
makes `roles`, `launch_only_roles`, `lms_user_id` and `roles_claim` contract
members of it — so the driver now reads the *people* out of that document as well
as the client, which is what lets a test name one seeded person instead of
asserting over whoever happens to be seeded. And `mock_idp_settings` imports a
class rather than driving a route, because one rule — a redirect URI may carry no
fragment — is enforced when the settings are built and has no request that can
ask it.

E0-17 adds a group at the very bottom, and they are the first fixtures here that
run a *process* rather than a function. `demo_database` and `seeded_demo` are
about running the script the way `make seed` does: it invokes `scripts/seed.py` as
a program and the program reaches a database on its own, so the fixture gives it a
database of its own — created in the session container, migrated to head, and
dropped afterwards — and starts it the way the Makefile does. They are here rather
than in the test module because E0-17's definition of done says the seeded
institution "is also the fixture E9 will reuse", and because `seed_environment`
below is the third place in this file that answers "which variables could a
program need to reach this container", which is a question `docs/MISTAKES.md`
entry 13 says to answer once.

The other three each arrived from something that went wrong, and each says so
where it sits. `seed_module` imports the script instead of starting it, because
the guard in it reads *resolved* configuration — the process environment with
`.env` filling in what it does not set (ADR 0063) — and a subprocess cannot be
asked about that resolution, since the fixture starting it supplies one of the two
sources and the developer's working tree supplies the other (entry 30).
`demo_databases` and `plant_in` exist so that rows can be put in front of the seed
rather than only after it: a database only the seed has written cannot pose the
question idempotency is about (entry 31).

E0-11 adds fixtures further up, and one of them is unlike everything
above it. `authz` reaches the authorization chokepoint **by name**: E0-11's
surface was settled before any code was written, so there is nothing to discover,
and the class exists only to turn an absent module or an absent symbol into a
failed assertion instead of a collection error. `application_session` is a
session on the connection production serves requests over — `pulse_app`, holding
only what the migrations grant it — because from E0-11 on, "the resolver could
read that" is a claim about a grant and not only about a query. It also adds
`supervision_graph_on`, beside `supervision_graph` rather than at the bottom,
which is the same builder pointed at a database standing at an earlier revision:
the ticket's migration has to answer for rows that were already stored when it
runs, and no fixture here could reach that state before.
"""

import base64
import hashlib
import hmac
import importlib
import importlib.util
import inspect
import itertools
import json
import os
import re
import secrets
import string
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from importlib.machinery import PathFinder
from itertools import count
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from uuid import uuid4

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
BASE_COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
OVERRIDE_COMPOSE_PATH = REPO_ROOT / "docker-compose.override.yml"
COMPOSE_PATHS = (BASE_COMPOSE_PATH, OVERRIDE_COMPOSE_PATH)
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

BACKEND_DIR = REPO_ROOT / "backend"
ALEMBIC_INI_PATH = BACKEND_DIR / "alembic.ini"
MIGRATIONS_DIR = BACKEND_DIR / "migrations"

# Compose interpolation. The alternatives are ordered so that `$$` is consumed
# first and registers nothing, which matters: the `$$POSTGRES_USER` in the `db`
# health check reaches the container as a literal `$POSTGRES_USER` and is
# expanded by the shell inside it, out of the environment Compose has already
# built. Compose never looks that name up in `.env`, so counting it would let a
# health check vouch for an entry nothing supplies.
#
# `${NAME}`, `${NAME:-default}`, `${NAME:?error}`, `${NAME:+alt}` and the bare
# `$NAME` all read NAME, so the name is taken and the rest of the expression is
# not parsed.
COMPOSE_INTERPOLATION = re.compile(
    r"\$\$|\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)"
)


def strip_inline_comment(value: str) -> str:
    """Remove a trailing ` # ...` comment, matching dotenv and Compose behaviour.

    A `#` that is not preceded by whitespace is part of the value, which is how
    `docker compose --env-file` and `python-dotenv` both read it.
    """
    if value[:1] in {"'", '"'}:
        quote = value[0]
        closing = value.find(quote, 1)
        return value[1:closing] if closing != -1 else value[1:]
    head, separator, _ = value.partition(" #")
    return head.rstrip() if separator else value


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse dotenv text into an ordered mapping of variable name to value."""
    entries: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        entries[name.strip()] = strip_inline_comment(value.strip())
    return entries


def load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a mapping.

    Returns an empty mapping when the file is absent or holds something other
    than a mapping, so a test reports a failed assertion naming the missing
    deliverable rather than a fixture error. Every test that consumes one of
    these asserts it is non-empty first, because "nothing in this file is wrong"
    is true of a file that could not be read.
    """
    if not path.is_file():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else {}


def load_compose(path: Path) -> dict[str, Any]:
    """Parse one Compose file on its own, with no override merged over it.

    Reading the files separately is deliberate and `docker compose config` is
    not a substitute: it merges the override back in, which hides the one
    property `tests/unit/test_compose_stack.py` exists to check.
    """
    return load_yaml(path)


def interpolated_variables(node: Any) -> set[str]:
    """Every environment variable name a parsed Compose document interpolates.

    Walks the parsed document rather than the file text, and that is the point.
    A parser has already discarded the comments, so a `${DB_NAME}` that someone
    commented out stops counting as a reader at the moment it stops being one.
    Scanning raw text would let a commented-out interpolation go on vouching for
    an `.env.example` entry that nothing supplies.

    Names are uppercased, matching how `test_env_example_sync.py` compares them.
    """
    found: set[str] = set()
    if isinstance(node, str):
        for match in COMPOSE_INTERPOLATION.finditer(node):
            name = match.group("braced") or match.group("bare")
            if name:
                found.add(name.upper())
    elif isinstance(node, dict):
        for key, value in node.items():
            found |= interpolated_variables(key)
            found |= interpolated_variables(value)
    elif isinstance(node, list):
        for item in node:
            found |= interpolated_variables(item)
    return found


@pytest.fixture
def base_compose_path() -> Path:
    """Where the base Compose file must live (SPEC §13). Asserted by the test, not here."""
    return BASE_COMPOSE_PATH


@pytest.fixture
def base_compose() -> dict[str, Any]:
    """`docker-compose.yml` parsed alone, with no override merged in."""
    return load_compose(BASE_COMPOSE_PATH)


@pytest.fixture
def override_compose_path() -> Path:
    """Where the development override lives. Asserted by the test, not here."""
    return OVERRIDE_COMPOSE_PATH


@pytest.fixture
def override_compose() -> dict[str, Any]:
    """`docker-compose.override.yml` parsed alone, with no base file under it.

    Added in E0-03, after a reviewer found that nothing read this file at all
    while `worker` and `beat` configuration had moved into it. Parsed on its own
    for the same reason as the base file: the merged view is what every dynamic
    check already sees, and the questions worth asking here are about what this
    file says by itself.

    YAML anchors are resolved by the parser, so a service that merges
    `<<: *development-source` arrives here holding those keys. That is what makes
    a rule about services reach a shared anchor without this fixture knowing
    anchors exist.
    """
    return load_compose(OVERRIDE_COMPOSE_PATH)


@pytest.fixture
def ci_workflow_path() -> Path:
    """Where the CI workflow lives. Asserted by the test, not here."""
    return CI_WORKFLOW_PATH


@pytest.fixture
def ci_workflow() -> dict[str, Any]:
    """`.github/workflows/ci.yml`, parsed rather than grepped.

    A regex over the text cannot tell a job service's `image:` from any other
    line that spells the same word, and it keeps passing against a workflow
    whose shape has changed underneath it — which is the failure the test that
    uses this exists to make impossible.

    One quirk to know before adding anything that reads a top-level key here:
    PyYAML implements YAML 1.1, so the workflow's `on:` parses to the boolean
    `True` rather than to the string `"on"`. Nothing currently needs it.
    """
    return load_yaml(CI_WORKFLOW_PATH)


@pytest.fixture
def compose_read_variables() -> set[str]:
    """Every variable the Compose files read out of `.env`, uppercased.

    Deliberately asserts nothing, and the direction of that choice matters here.
    An empty set makes the test that consumes it *stricter* rather than weaker —
    it falls back to requiring a `Settings` field — so a Compose file that has
    gone missing or stopped parsing cannot quietly turn an assertion into a
    vacuous pass.
    """
    found: set[str] = set()
    for path in COMPOSE_PATHS:
        found |= interpolated_variables(load_compose(path))
    return found


@pytest.fixture
def interpolated_variables_in() -> Callable[[Any], set[str]]:
    """Hand `interpolated_variables` to a test that needs it on one service.

    `compose_read_variables` above answers "what does the whole stack read", and
    a rule about one service holding one credential needs the same question
    asked of one subtree. The same walker answers both, so the two cannot end up
    disagreeing about what counts as reading a variable — `$$` escaped, defaults
    and error forms unwrapped, commented-out interpolations already discarded by
    the parser.
    """
    return interpolated_variables


@pytest.fixture
def env_example_path() -> Path:
    """Where `.env.example` must live (SPEC §13). Asserted by the test, not here."""
    return ENV_EXAMPLE_PATH


@pytest.fixture
def documented_env() -> dict[str, str]:
    """Every variable documented in `.env.example`, with its placeholder value.

    Deliberately asserts nothing: a missing `.env.example` yields an empty
    mapping, so the test that cares reports a failed assertion rather than a
    fixture error. Tests that could pass vacuously on an empty mapping assert it
    is non-empty themselves.
    """
    if not ENV_EXAMPLE_PATH.is_file():
        return {}
    return parse_dotenv(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def import_app_module() -> Iterator[Callable[[str], ModuleType | None]]:
    """Import an `app.*` module against the environment the test has just set.

    A module that builds something out of `Settings` reads the environment once,
    at import time, and `sys.modules` then keeps the result for the rest of the
    session. So a test that sets `REDIS_URL` and imports `app.jobs.celery_app`
    gets the value it set only if nothing imported that module earlier — and if
    something did, the test passes or fails for a reason it did not choose,
    which is `docs/MISTAKES.md` entry 3 in its purest form. Every `app.*` module
    is therefore dropped from `sys.modules` before the test body runs, and the
    set that was there is put back afterwards, so the interpreter is left as it
    was found.

    The returned callable answers `None` for a module that does not exist, so a
    test reports a failed assertion naming the missing deliverable rather than a
    collection error — the same choice `load_yaml` makes above, for the same
    reason. An `ImportError` raised *inside* a module that does exist propagates
    untouched: a module that is broken and a module that was never written need
    different fixes, and a test must not report them as the same thing.
    """
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name == "app" or name.startswith("app.")
    }
    for name in saved:
        sys.modules.pop(name, None)

    def import_module(name: str) -> ModuleType | None:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            absent = exc.name
            if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                return None
            raise

    try:
        yield import_module
    finally:
        for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


@pytest.fixture
def celery_application_in() -> Callable[[ModuleType], Any]:
    """Find the Celery application a module exposes, whatever it is named.

    This mirrors what `celery -A <module>` itself does — `celery.app.utils.
    find_app` looks for an attribute called `app`, then one called `celery`,
    and failing both scans the module for a `Celery` instance — because the
    worker and beat services reach the application that way and the E0-03 ticket
    names no attribute. Pinning a name here would turn the ticket's silence into
    this test suite's decision.

    What is *not* left open is that the application has to be reachable at module
    level: a factory that has to be called is not something `-A` can use, so a
    module that exposes only one answers `None` here and the test that asked
    fails saying so.

    Returns `None` rather than asserting, so the test does the asserting.
    """
    from celery import Celery

    def find(module: ModuleType) -> Any:
        for name in ("app", "celery", "celery_app"):
            candidate = getattr(module, name, None)
            if isinstance(candidate, Celery):
                return candidate
        for name in sorted(vars(module)):
            candidate = getattr(module, name, None)
            if isinstance(candidate, Celery):
                return candidate
        return None

    return find


@pytest.fixture
def configured_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    documented_env: dict[str, str],
) -> dict[str, str]:
    """A process environment that satisfies every documented variable.

    The working directory is moved to an empty temporary directory first, so a
    developer's own `.env` in the repository root cannot supply a value that the
    test believes it removed.
    """
    monkeypatch.chdir(tmp_path)
    for name, value in documented_env.items():
        monkeypatch.setenv(name, value)
    return dict(documented_env)


# ---------------------------------------------------------------------------
# E0-04 — a real Postgres, with production's role shape, migrated once.
# ---------------------------------------------------------------------------

# The service whose image the container runs. Read out of `docker-compose.yml`
# rather than pinned here for the reason `test_image_pins_agree.py` gives: a
# schema proved against a Postgres the project does not deploy is a proof about
# a different system.
DB_SERVICE_NAME = "db"
POSTGRES_CONTAINER_PORT = 5432

# Credentials for a container that exists for the length of one pytest session
# and is then destroyed. Nothing here was copied from a working `.env` and
# nothing here resembles a real credential (CLAUDE.md, secrets). Named
# `...CREDENTIAL` rather than `...PASSWORD` so ruff's S105 keeps flagging the
# real thing; `tests/unit/test_config_settings.py` made the same choice.
TEST_SUPERUSER = "pulse_test_admin"
TEST_SUPERUSER_CREDENTIAL = "test-only-admin-9d41c7ba"

# **`pulse_app`, not a test-only name, and E0-10 is what changed it.** E0-04 chose
# `pulse_test_app` when no grant existed anywhere for the name to be wrong about;
# from E0-10 on, every grant in the schema belongs to `pulse_app` — the name
# `.env.example` gives `DB_APP_USER` and the name the migration establishes — so a
# fixture connecting as anything else holds nothing, and `application_engine`
# stops being able to tell a missing grant from a present one. That is precisely
# the failure this fixture exists to prevent: "tests that pass under privileges
# production does not have", now in its mirror image.
#
# It works because the order here is the Compose stack's order exactly:
# `provision_application_role` creates the role before any migration runs, as
# `scripts/db-init` does at `initdb`, and E0-10's migration guards its
# `CREATE ROLE` with a `pg_roles` lookup and applies its `ALTER`/`GRANT`/`REVOKE`
# unconditionally — which is the ticket's "Reconcile first" requirement, asserted
# by `test_alembic_upgrade_head_succeeds_where_the_roles_already_exist`.
TEST_APP_USER = "pulse_app"
TEST_APP_CREDENTIAL = "test-only-app-4b8e0257"

# The Care role, provisioned here for the same reason and by the same route as
# the application role. `scripts/db-init/02-care-role.sh` creates it with a login
# and a password on a Compose volume; a testcontainers Postgres runs no init hook,
# so this file is its provisioning (ADR 0009's table gives this fixture its own
# row). The E0-10 migration creates the role too, guarded, and writes every
# privilege it holds — the script and this fixture only hand it a way to log in,
# which a migration cannot do without keeping a password in the repository.
TEST_CARE_USER = "pulse_care"
TEST_CARE_CREDENTIAL = "test-only-care-71c3f2ad"

TEST_DATABASE = "pulse_test"

DATABASE_URL_VARIABLE = "DATABASE_URL"

# The Care connection's own URL. Not this file's invention and not a choice left
# open: `.env.example` documents it, and its comment says it is "read by
# `app.services.safety` and by nothing else".
CARE_DATABASE_URL_VARIABLE = "CARE_DATABASE_URL"

# **This suite's choice**, and the one name in this file that a construction
# decision could displace. E0-04 settles *which identity* runs migrations —
# `DB_SUPERUSER`, never `Settings.database_url` (ADR 0009) — and deliberately
# leaves the mechanism open: a new `Settings` field, an Alembic-only variable,
# or something `env.py` assembles from the parts. `migration_environment` below
# therefore sets this *and* the parts *and* `DATABASE_URL`, so an `env.py`
# written any of those three ways finds the container. If the implementation
# spells the variable differently, change this constant; nothing else moves.
ALEMBIC_SUPERUSER_URL_VARIABLE = "ALEMBIC_DATABASE_URL"


class DatabaseUnderTest(NamedTuple):
    """One database in the test container, addressed as each of the three roles.

    All three URLs name the same database on the same server. Which one a caller
    reaches for is the whole subject of ADR 0009 and ADR 0001: migrations and
    bootstrap use `superuser_url`, everything the application does uses
    `application_url`, and `care_url` is the one connection in the cluster that
    can execute the audited reveal (SPEC §6.2). The third arrived with E0-10, and
    `.env.example` documents its variables as `CARE_DATABASE_URL`, `DB_CARE_USER`
    and `DB_CARE_PASSWORD`.
    """

    superuser_url: str
    application_url: str
    care_url: str


def container_url(container: Any, *, username: str, credential: str, database: str) -> str:
    """A `postgresql+psycopg://` URL for one role against one database."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(POSTGRES_CONTAINER_PORT)
    return f"postgresql+psycopg://{username}:{credential}@{host}:{port}/{database}"


def migration_environment(database: DatabaseUnderTest) -> dict[str, str]:
    """Every environment variable an `env.py` could need to reach `database`.

    Deliberately over-supplies. E0-04 leaves it open whether Alembic learns the
    superuser connection from a whole URL or assembles one from the parts
    `.env.example` already declares, and a fixture that supplied only one of
    those would make that choice for the implementer — quietly, by failing the
    other option. So the parts and the URL are both set, and they agree: same
    host, same port, same database.

    `DATABASE_URL` is set to the *application* role, exactly as it is in
    production. An `env.py` that uses it to connect will fail to create a table,
    which is the failure ADR 0009 exists to keep visible.
    """
    superuser = urlsplit(database.superuser_url)
    application = urlsplit(database.application_url)
    return {
        ALEMBIC_SUPERUSER_URL_VARIABLE: database.superuser_url,
        DATABASE_URL_VARIABLE: database.application_url,
        "DB_SUPERUSER": superuser.username or "",
        "DB_SUPERUSER_PASSWORD": superuser.password or "",
        "DB_APP_USER": application.username or "",
        "DB_APP_PASSWORD": application.password or "",
        "DB_NAME": superuser.path.lstrip("/"),
    }


def application_environment(database: DatabaseUnderTest) -> dict[str, str]:
    """Every variable an `app.*` module could need to reach `database` at run time.

    The same over-supply `migration_environment` above makes, for the same reason
    and one ticket later. `.env.example` gives the Care connection a URL of its
    own *and* a user/password pair, and `app.services.safety` could reasonably
    read either — a whole `CARE_DATABASE_URL`, or the pair against the address in
    `DATABASE_URL`, which is the shape ADR 0012 chose for Alembic. Supplying only
    one would make that choice for the implementer by failing the other, so both
    are set and they agree.

    `DATABASE_URL` names the application role and `CARE_DATABASE_URL` names the
    Care role, never each other and never the superuser — `.env.example` calls
    pointing both at one role "the separation undone in one line", and a fixture
    that did it would test the separation against a database that does not have
    one.
    """
    application = urlsplit(database.application_url)
    care = urlsplit(database.care_url)
    return {
        DATABASE_URL_VARIABLE: database.application_url,
        CARE_DATABASE_URL_VARIABLE: database.care_url,
        "DB_APP_USER": application.username or "",
        "DB_APP_PASSWORD": application.password or "",
        "DB_CARE_USER": care.username or "",
        "DB_CARE_PASSWORD": care.password or "",
        "DB_NAME": care.path.lstrip("/"),
    }


@contextmanager
def environment(values: dict[str, str]) -> Iterator[None]:
    """Set `values` in `os.environ` and put the previous contents back after.

    `monkeypatch` would be the idiom, and it is function-scoped, so the
    session-scoped fixture that applies migrations once cannot use it.
    """
    saved = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, previous in saved.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def alembic_config() -> Any:
    """The project's own Alembic configuration, pointed at its script directory.

    `script_location` is set rather than read, and that is not the test choosing
    where migrations live: SPEC §13 and E0-04 both put them at
    `backend/migrations/`. A relative `script_location` in `alembic.ini`
    resolves against the working directory, which is `backend/` for
    `make migrate` and the repository root for pytest, so leaving it unset would
    fail on where pytest happens to be standing rather than on anything the
    ticket is about.
    """
    from alembic.config import Config

    if not ALEMBIC_INI_PATH.is_file():
        pytest.fail(
            f"{ALEMBIC_INI_PATH} does not exist. E0-04 ships `backend/alembic.ini` and "
            "`backend/migrations/` with `env.py` wired to `Base.metadata` and to the "
            "superuser connection (SPEC §13, ADR 0009)."
        )
    if not MIGRATIONS_DIR.is_dir():
        pytest.fail(
            f"{MIGRATIONS_DIR} does not exist. E0-04 ships the migration environment and one "
            "baseline revision that creates nothing, establishing the revision chain."
        )

    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def provision_application_role(superuser_url: str, database: str) -> None:
    """Create the role the application connects as, as `scripts/db-init` does.

    ADR 0009's provisioning table gives this fixture its own row, and E0-04 owns
    it: `scripts/db-init` runs only where the Compose `initdb` hook exists, and
    a container started by testcontainers has no such hook. Without this, every
    test would run as the cluster superuser — bypassing every grant and every
    row-level security policy — and the suite would be measuring privileges no
    deployment has.

    `NOSUPERUSER` and `CONNECT` and nothing else, matching
    `scripts/db-init/01-application-role.sh`. The credential is inlined into the
    statement because Postgres does not accept bind parameters in `CREATE ROLE`;
    that script uses `\\password` instead, for a reason that does not apply to a
    throwaway container whose credential is in this file.
    """
    from sqlalchemy import create_engine, text

    create_role = (
        f'CREATE ROLE "{TEST_APP_USER}" LOGIN'
        f" PASSWORD '{TEST_APP_CREDENTIAL}'"
        " NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )
    grant_connect = f'GRANT CONNECT ON DATABASE "{database}" TO "{TEST_APP_USER}"'

    engine = create_engine(superuser_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(create_role))
            connection.execute(text(grant_connect))
    finally:
        engine.dispose()


def provision_care_role(superuser_url: str) -> None:
    """Create the role the Care queue connects as, as `scripts/db-init` does.

    The counterpart to `provision_application_role` above, and it mirrors
    `scripts/db-init/02-care-role.sh` line for line in what it does *and* in what
    it refuses to do: a login, and **no grant of any kind**. Every privilege
    `pulse_care` holds is written by the E0-10 migration, which is the one
    mechanism that runs in all four environments ADR 0009's table lists; a
    fixture that granted anything here would be a second place the grant model
    lives, and the §4.1 assertions would be measuring it rather than the
    migration.

    No `GRANT CONNECT` either, and that is the script's choice rather than an
    omission: Postgres grants `CONNECT` to `PUBLIC` by default, so the role can
    reach the database without one, and the E0-10 grants are what decide what it
    can do once there.
    """
    from sqlalchemy import create_engine, text

    create_role = (
        f'CREATE ROLE "{TEST_CARE_USER}" LOGIN'
        f" PASSWORD '{TEST_CARE_CREDENTIAL}'"
        " NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )

    engine = create_engine(superuser_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(text(create_role))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[Any]:
    """A Postgres container on the image `docker-compose.yml` deploys.

    Session-scoped: starting one costs seconds, and the isolation every test
    needs comes from `db_session` rolling its transaction back rather than from
    a fresh server. The `with` block is what tears it down, on the way out of a
    passing run and out of a failing one alike.

    `testcontainers.community.postgres`, not `testcontainers.postgres`: on the
    locked testcontainers 4.15.0 the shorter path raises a DeprecationWarning at
    import, and `filterwarnings = ["error::DeprecationWarning"]` in
    `pyproject.toml` turns that into a collection error.
    """
    from testcontainers.community.postgres import PostgresContainer

    services = load_compose(BASE_COMPOSE_PATH).get("services") or {}
    service = services.get(DB_SERVICE_NAME) or {}
    image = service.get("image") if isinstance(service, dict) else None

    if not isinstance(image, str) or not image:
        pytest.fail(
            f"{BASE_COMPOSE_PATH} declares no image for the `{DB_SERVICE_NAME}` service, so "
            "these tests have no Postgres image to run and cannot fall back to one without "
            "checking the schema against a server the project never deploys."
        )

    with PostgresContainer(
        image=image,
        username=TEST_SUPERUSER,
        password=TEST_SUPERUSER_CREDENTIAL,
        dbname=TEST_DATABASE,
        driver="psycopg",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def provisioned_database(postgres_container: Any) -> DatabaseUnderTest:
    """The container's database, with all three roles, before any migration runs.

    The two runtime roles are created *before* the migration, which is the
    Compose stack's order exactly — `initdb` runs `scripts/db-init` against an
    empty data directory, and the migration meets roles that already exist. E0-10
    requires it to tolerate that (`CREATE ROLE` guarded by a `pg_roles` lookup,
    the `ALTER`/`GRANT`/`REVOKE` applied unconditionally), so this ordering is
    also what exercises the requirement rather than working around it.
    """
    urls = DatabaseUnderTest(
        superuser_url=container_url(
            postgres_container,
            username=TEST_SUPERUSER,
            credential=TEST_SUPERUSER_CREDENTIAL,
            database=TEST_DATABASE,
        ),
        application_url=container_url(
            postgres_container,
            username=TEST_APP_USER,
            credential=TEST_APP_CREDENTIAL,
            database=TEST_DATABASE,
        ),
        care_url=container_url(
            postgres_container,
            username=TEST_CARE_USER,
            credential=TEST_CARE_CREDENTIAL,
            database=TEST_DATABASE,
        ),
    )
    provision_application_role(urls.superuser_url, TEST_DATABASE)
    provision_care_role(urls.superuser_url)
    return urls


@pytest.fixture(scope="session")
def migrated_database(provisioned_database: DatabaseUnderTest) -> DatabaseUnderTest:
    """`alembic upgrade head`, applied once for the whole session."""
    from alembic import command

    with environment(migration_environment(provisioned_database)):
        command.upgrade(alembic_config(), "head")
    return provisioned_database


@pytest.fixture
def empty_database(
    postgres_container: Any,
    provisioned_database: DatabaseUnderTest,
) -> Iterator[DatabaseUnderTest]:
    """A database with nothing in it at all, for one test, then dropped.

    "`alembic upgrade head` succeeds against an empty database" is a claim about
    an empty one, and the session database stops being empty the moment the
    first migration lands on it. A second database in the same container is far
    cheaper than a second container, and roles are cluster-wide, so all three
    URLs still name the three roles ADR 0009 and ADR 0001 separate.
    """
    from sqlalchemy import create_engine, text

    name = f"e0_04_{uuid4().hex[:12]}"
    admin = create_engine(provisioned_database.superuser_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        yield DatabaseUnderTest(
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
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def alembic_config_pointed_at(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[DatabaseUnderTest], Any]:
    """Point Alembic at one database and hand back a `Config` to run commands with.

    The commands stay in the test — `command.upgrade`, `command.check` — because
    which one is being run is the subject of the test that runs it, and a
    fixture that ran them would move the assertion's verb into this file.
    """

    def prepare(database: DatabaseUnderTest) -> Any:
        for name, value in migration_environment(database).items():
            monkeypatch.setenv(name, value)
        return alembic_config()

    return prepare


@pytest.fixture(scope="session")
def migrated_engine(migrated_database: DatabaseUnderTest) -> Iterator[Any]:
    """An engine on the migrated database, connected as the bootstrap identity.

    The bootstrap identity and not the application one, and the reason is worth
    stating because it looks like the wrong choice. Tests seed the rows they
    read back, and the application role deliberately holds nothing but `CONNECT`
    (ADR 0001 line 71, ADR 0009) — so a fixture that seeded as the application
    role would either fail or need a grant this project does not make.
    `app.db`'s own engine connects as the application role, which is what
    `tests/integration/test_db_session.py` exercises.
    """
    from sqlalchemy import create_engine

    engine = create_engine(migrated_database.superuser_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Any) -> Iterator[Any]:
    """A session whose every write is rolled back when the test ends.

    The transaction is opened on the connection *outside* the session, and the
    session joins it by creating a savepoint, so a test that commits still ends
    up inside a transaction this fixture can roll back. That is what makes the
    isolation hold against test code that does not know about it — which is the
    only kind of isolation worth having, since a test that has to cooperate to
    stay isolated will eventually not.

    Postgres puts DDL inside the transaction too, so a table created in a test
    is gone with the rest of it.
    """
    from sqlalchemy.orm import Session

    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="session")
def application_engine(provisioned_database: DatabaseUnderTest) -> Iterator[Any]:
    """An engine connected as the application role, holding only what it is granted."""
    from sqlalchemy import create_engine

    engine = create_engine(provisioned_database.application_url)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# E0-07 — reaching the section-code service without naming what it is made of.
# ---------------------------------------------------------------------------

# Spelled by E0-07's scope: "`backend/app/services/section_codes.py`". The
# package root is `backend/`, so the import path is `app.services....`.
SECTION_CODE_MODULE = "app.services.section_codes"

# What a value the tests can supply is *for*, matched against a parameter's
# name. E0-07 says the derivation takes "the code and the section's term" and
# says nothing about whether a session is passed, whether the term arrives as a
# model instance or a key, or what any of it is called — so the tests offer
# every value they have and let the signature take what it wants. Matching is by
# exact name or by `_`-suffix, longest alias first, so `section_code` is a code
# and `course_week` is a course week rather than a bare week.
SERVICE_ROLES: dict[str, tuple[str, ...]] = {
    "session": ("session", "db"),
    "code": ("code", "section_code"),
    "term": ("term",),
    "term_id": ("term_id",),
    "section": ("section",),
    "course_week": ("course_week", "week"),
}


class SectionCodeService:
    """E0-07's service, found rather than named.

    **Every identifier inside the module is discovered.** The ticket names the
    file and the four values the derivation produces — `length_weeks`,
    `start_date`, `end_date`, `modality` — and nothing else: not the parse
    function, not the derivation function, not the offset function, not the error
    classes, not the shape a parsed code comes back in. Naming any of them here
    would make the implementer build to this fixture instead of to the ticket,
    which is the failure `tests/integration/test_term_calendar_schema.py`'s
    `week_producer` avoids the same way.

    So a callable is looked up by a fragment of its name, and the answer has to
    be unambiguous: none, or two that this cannot choose between, is a failure
    that lists what the module defines and says which choice would settle it.
    Module-level functions and the `classmethod`/`staticmethod` members of
    module-level classes both count, because `SectionCode.parse` and
    `parse_section_code` are equally reasonable and the ticket rules out neither.

    **What this does not do is decide anything.** Where a test needs a name that
    E0-07 leaves open it fails saying so, rather than guessing quietly and
    passing against a design the ticket never asked for.
    """

    def __init__(self) -> None:
        self._module: ModuleType | None = None

    # -- reaching the module and its callables ------------------------------

    @property
    def module(self) -> ModuleType:
        """`app.services.section_codes`, or a failure naming the missing file.

        A `ModuleNotFoundError` for some *other* module is re-raised untouched:
        a service that exists and imports something absent and a service that
        was never written need different fixes, and a test must not report them
        as the same thing. `import_app_module` above makes the same distinction
        for the same reason.
        """
        if self._module is None:
            try:
                self._module = importlib.import_module(SECTION_CODE_MODULE)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is None or not (
                    absent == SECTION_CODE_MODULE or SECTION_CODE_MODULE.startswith(f"{absent}.")
                ):
                    raise
                pytest.fail(
                    f"There is no `{SECTION_CODE_MODULE}` module. E0-07's scope puts the parser "
                    "and the date derivation in `backend/app/services/section_codes.py` (SPEC "
                    "§13 gives `services/` that job, and the ticket names the file)."
                )
        return self._module

    def defined_callables(self) -> dict[str, Any]:
        """Every public callable the service module defines itself.

        Defines *itself*: a function imported from somewhere else is not part of
        this module's surface, and counting one would let an imported `parse`
        from the standard library answer for the ticket's deliverable.
        """
        found: dict[str, Any] = {}
        for name, value in vars(self.module).items():
            if name.startswith("_"):
                continue
            if getattr(value, "__module__", None) != SECTION_CODE_MODULE:
                continue
            if inspect.isfunction(value):
                found[name] = value
            elif inspect.isclass(value):
                for attribute, member in vars(value).items():
                    if attribute.startswith("_") or not isinstance(
                        member, classmethod | staticmethod
                    ):
                        continue
                    bound = getattr(value, attribute, None)
                    if callable(bound):
                        found[f"{name}.{attribute}"] = bound
        return found

    def callable_named_after(self, fragments: tuple[str, ...], purpose: str, quoting: str) -> Any:
        """The one callable whose name carries one of `fragments`.

        Fragments are tried in order, so a module that spells the derivation
        `derive_section_calendar` is found by "deriv" without "calendar" ever
        being consulted. A fragment matching more than one callable stops rather
        than picking: two candidates mean this cannot tell which one the ticket
        is about, and choosing would be the test deciding. A module-level
        function is preferred over a class member of the same name, since a
        `SectionCode.parse` that delegates to `parse` is one deliverable and not
        two.
        """
        defined = self.defined_callables()
        for fragment in fragments:
            matches = {
                name: value
                for name, value in defined.items()
                if fragment in name.rsplit(".", maxsplit=1)[-1].lower()
            }
            if len(matches) > 1:
                unqualified = {name: value for name, value in matches.items() if "." not in name}
                if len(unqualified) == 1:
                    return next(iter(unqualified.values()))
                pytest.fail(
                    f"`{SECTION_CODE_MODULE}` defines more than one callable whose name carries "
                    f"{fragment!r} ({sorted(matches)}), so this cannot tell which one {purpose}. "
                    "Naming one here would pin an interface E0-07 leaves open — say in the pull "
                    "request which it is, and `SectionCodeService` in tests/conftest.py is the "
                    "one place that changes."
                )
            if matches:
                return next(iter(matches.values()))
        pytest.fail(
            f"`{SECTION_CODE_MODULE}` defines no callable whose name carries any of "
            f"{list(fragments)} — it defines {sorted(defined)}. E0-07's scope: {quoting} The "
            "callable is looked for by name rather than imported under an agreed one because no "
            "ticket spells it; if it is there under a name none of these fragments reaches, that "
            "is a defect in this fixture rather than in the service."
        )

    @property
    def parse(self) -> Any:
        """The callable that turns a section code into its three parts."""
        return self.callable_named_after(
            ("parse", "from_code"),
            "parses a section code",
            "'parse a code into start letter, ordinal, and modality; reject malformed codes with "
            "a specific error naming what failed'.",
        )

    @property
    def derive(self) -> Any:
        """The callable that turns a code plus a term into a section's calendar."""
        return self.callable_named_after(
            ("deriv", "calendar", "dates"),
            "derives a section's calendar",
            "'Derive `length_weeks`, `start_date`, `end_date`, and `modality` from the code and "
            "the section's term, reading `start_letter_map`'.",
        )

    @property
    def writer(self) -> Any:
        """The callable that puts a derived calendar onto a section.

        E0-07's scope: "Add the derived section columns and populate them through
        this service, so there is exactly one path that sets them." That sentence
        names a writer and, like everything else here, does not name the
        function — so it is found the same way, by a fragment of its name, with
        "apply" first because applying a code to a section is what the ticket
        describes it doing.
        """
        return self.callable_named_after(
            ("apply", "populate", "assign", "fill", "write"),
            "writes a derived calendar onto a section",
            "'Add the derived section columns and populate them through this service, so there "
            "is exactly one path that sets them'.",
        )

    @property
    def offset(self) -> Any:
        """The callable that relates a section's course weeks to its term's weeks."""
        return self.callable_named_after(
            ("offset", "term_week", "week"),
            "converts between the course-week and term-week axes",
            "'The offset arithmetic belongs here', and the last acceptance criterion: "
            "'Course-week to term-week offset is computed and tested for a section that starts "
            "five weeks into a term'.",
        )

    # -- calling one --------------------------------------------------------

    @staticmethod
    def role_of(parameter_name: str) -> str | None:
        """Which of `SERVICE_ROLES` a parameter called `parameter_name` wants."""
        best: tuple[int, str] | None = None
        for role, aliases in SERVICE_ROLES.items():
            for alias in aliases:
                if (parameter_name == alias or parameter_name.endswith(f"_{alias}")) and (
                    best is None or len(alias) > best[0]
                ):
                    best = (len(alias), role)
        return None if best is None else best[1]

    def call(self, function: Any, **available: Any) -> Any:
        """Call `function`, filling each parameter from the roles offered.

        Binding by parameter name rather than by position, and never by
        `try: ... except TypeError:`, is deliberate. A helper that retried
        several call shapes until one stopped raising would swallow a `TypeError`
        raised *inside* the service, and would report a design the ticket never
        chose as working — the shape of `docs/MISTAKES.md` entry 3. This way a
        parameter that no offered role matches stops the test with a message
        naming it, which is a defect in this fixture or an interface question for
        the ticket, and either way something to see rather than route around.

        One narrow accommodation: a single-parameter callable is handed the one
        value the caller offered, whatever it is named. `parse(raw)` and
        `parse(code)` are the same deliverable, and the parameter's name is not
        something E0-07 decides.
        """
        signature = inspect.signature(function)
        parameters = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]
        if len(parameters) == 1 and len(available) == 1:
            only = next(iter(available.values()))
            if parameters[0].kind is parameters[0].POSITIONAL_ONLY:
                return function(only)
            return function(**{parameters[0].name: only})

        positional: list[Any] = []
        keyword: dict[str, Any] = {}
        for parameter in parameters:
            role = self.role_of(parameter.name)
            if role is None or role not in available:
                if parameter.default is not parameter.empty:
                    continue
                pytest.fail(
                    f"`{getattr(function, '__qualname__', function)}` requires a parameter "
                    f"`{parameter.name}` that this test has nothing to fill from. It is offering "
                    f"{sorted(available)}. E0-07 says the derivation takes 'the code and the "
                    "section's term' and spells no signature, so a parameter outside that is an "
                    "interface question for the ticket — add the role to `SERVICE_ROLES` in "
                    "tests/conftest.py once the pull request says what it is for."
                )
            if parameter.kind is parameter.POSITIONAL_ONLY:
                positional.append(available[role])
            else:
                keyword[parameter.name] = available[role]
        return function(*positional, **keyword)

    # -- reading what came back ---------------------------------------------

    @staticmethod
    def part(subject: Any, candidates: tuple[str, ...], label: str) -> Any:
        """One named part of a parsed or derived result, however it is carried.

        A mapping key or an attribute, because E0-07 does not say whether the
        result is a dataclass, a Pydantic model, a `NamedTuple` or a dict, and
        all four answer to a name. A plain tuple does not, and is a failure here
        rather than an index this file invents an order for.
        """
        for candidate in candidates:
            if isinstance(subject, Mapping) and candidate in subject:
                return subject[candidate]
            if hasattr(subject, candidate):
                return getattr(subject, candidate)
        pytest.fail(
            f"{subject!r} carries none of {list(candidates)}, so this test cannot read the "
            f"{label} out of it. E0-07 names the parts — 'start letter, ordinal, and modality', "
            "and `length_weeks`, `start_date`, `end_date`, `modality` — without saying what "
            "carries them; the candidates are a constant in the test module and a deliberate "
            "rename is a one-line change there."
        )

    @staticmethod
    def raised_by_the_service(failure: BaseException) -> bool:
        """Whether `failure` is an error this project defines, not one that leaked.

        E0-07's definition of done: section codes arrive from the LMS, so confirm
        "no exception type that escapes as a 500". A `KeyError` off a letter-map
        lookup, an `IndexError` off a short string and a `ValueError` out of
        `int()` are all what an unguarded parser raises, and none of them is
        something a caller can catch on purpose.
        """
        return type(failure).__module__.split(".")[0] == "app"


@pytest.fixture
def section_codes() -> SectionCodeService:
    """E0-07's service, reached by discovery. See `SectionCodeService` above."""
    return SectionCodeService()


# ---------------------------------------------------------------------------
# E0-14 — the mock LTI 1.3 platform, driven the way a tool drives one.
# ---------------------------------------------------------------------------

# SPEC §13 spells the directory and the package inside it: `mock-lms/` holding a
# `Dockerfile` and an `app/`. Nothing else about the module layout is written
# down, so the application object is discovered rather than imported by name.
MOCK_LMS_DIR = REPO_ROOT / "mock-lms"
MOCK_LMS_SERVICE = "mock-lms"

# The package name **both** mocks use, because SPEC §13 gives each of them an
# `app/` beside a Dockerfile. It is the whole reason `MockPackageFinder` below
# exists, and it is one constant rather than one per mock so that the collision
# is described once.
MOCK_PACKAGE = "app"

# Where the ASGI application might sit inside that package, most likely first.
# `backend/` puts its own in `app.main`, so a mock written beside it probably
# does too; the rest are here so that a different arrangement is found rather
# than reported as a missing deliverable.
MOCK_LMS_MODULES = ("app.main", "app", "app.platform", "app.server", "app.api")

# Names a zero-argument application factory might carry, if the mock exposes one
# instead of a module-level instance. `backend/app/main.py` uses `create_app`,
# and `uvicorn --factory` is what makes that legal, so the mock may well too.
APPLICATION_FACTORY_NAMES = ("create_app", "get_app", "make_app", "build_app")

# How many launches a page offering several users, contexts or roles is walked
# for. **This suite's choice**, and a bound rather than a rule: the seeded data
# is meant to be small (E0-15: "this seed data belongs to the mock platform and
# stays small"), and a page offering more combinations than this is still walked,
# just not exhaustively. Raise it if a seed grows and a test starts missing a
# shape it names.
MAX_LAUNCH_VARIANTS = 32

# The parameters a tool sends to a platform's authorization endpoint for a plain
# resource-link launch. These are the OIDC and LTI 1.3 required values, not this
# suite's preferences: `id_token` with `form_post` and `prompt=none` is what the
# LTI 1.3 security framework specifies, and a platform that answered anything
# else would not be strict LTI 1.3 core (SPEC §7.3).
AUTHORIZATION_REQUEST_CONSTANTS = {
    "scope": "openid",
    "response_type": "id_token",
    "response_mode": "form_post",
    "prompt": "none",
}

# The DigestInfo prefix PKCS#1 v1.5 puts in front of a SHA-256 digest, from
# RFC 8017 appendix B.1. Nineteen bytes, and the whole of what makes an RS256
# verification a verification rather than a decode.
SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def base64url_decode(value: str) -> bytes:
    """Decode one base64url segment, supplying the padding JWS omits."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class JsonWebSignature(NamedTuple):
    """A compact JWS, split into the parts a verification needs.

    `signing_input` is the exact bytes that were signed — the encoded header and
    payload with the dot between them — and it is kept rather than recomputed so
    that a caller checking a *tampered* token compares against what the tamper
    produced.
    """

    header: dict[str, Any]
    claims: dict[str, Any]
    signing_input: bytes
    signature: bytes


def split_jws(token: str) -> JsonWebSignature:
    """Split a compact JWS, failing with the token in hand if it is not one."""
    parts = token.split(".")
    if len(parts) != 3:
        pytest.fail(
            f"The mock platform issued a value with {len(parts)} dot-separated segments rather "
            "than the three a compact JSON Web Signature has, so it is not a signed `id_token`. "
            f"It begins {token[:64]!r}."
        )
    encoded_header, encoded_claims, encoded_signature = parts
    try:
        header = json.loads(base64url_decode(encoded_header))
        claims = json.loads(base64url_decode(encoded_claims))
    except ValueError as failure:
        # `json.JSONDecodeError` and `binascii.Error` are both `ValueError`
        # subclasses, so this one clause covers a segment that is not base64url
        # and a segment that decodes to something that is not JSON.
        pytest.fail(f"The `id_token`'s header or payload is not base64url-encoded JSON: {failure}")
    return JsonWebSignature(
        header=header,
        claims=claims,
        signing_input=f"{encoded_header}.{encoded_claims}".encode("ascii"),
        signature=base64url_decode(encoded_signature),
    )


def verify_rs256(signing_input: bytes, signature: bytes, key: Mapping[str, Any]) -> bool:
    """Whether `signature` is an RS256 signature over `signing_input` under `key`.

    Written out of `pow` and `hashlib` rather than taken from a library, because
    nothing in this project's locked dependency set verifies a JWS and adding one
    to satisfy a test would decide, from the test side, which JOSE library the
    mock signs with. RSA *verification* is public-exponent modular
    exponentiation and a padding comparison, so the whole of it is below.

    The comparison is against the full PKCS#1 v1.5 encoded message, padding
    included, which is what makes this a real check: a verifier that compared
    only the trailing digest would accept a signature with forged padding, and a
    verifier that only decoded the token would accept anything at all. The tests
    that hand this a wrong key and a tampered payload are what prove it says no.
    """
    if key.get("kty") != "RSA":
        return False
    try:
        modulus = int.from_bytes(base64url_decode(str(key["n"])), "big")
        exponent = int.from_bytes(base64url_decode(str(key["e"])), "big")
    except (KeyError, ValueError, TypeError):
        return False
    if modulus <= 0 or exponent <= 0:
        return False

    width = (modulus.bit_length() + 7) // 8
    if len(signature) != width:
        return False
    numeric = int.from_bytes(signature, "big")
    if numeric >= modulus:
        return False

    encoded = pow(numeric, exponent, modulus).to_bytes(width, "big")
    digest_info = SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(signing_input).digest()
    if width < len(digest_info) + 11:
        return False
    expected = b"\x00\x01" + b"\xff" * (width - len(digest_info) - 3) + b"\x00" + digest_info
    return hmac.compare_digest(encoded, expected)


def verifying_key(signature: JsonWebSignature, key_set: Mapping[str, Any]) -> dict[str, Any] | None:
    """The key in `key_set` that verifies `signature`, or `None` if none does.

    Every key is tried, not just the one the header's `kid` names. That is
    deliberate: whether the header selects the right key and whether the key set
    contains a key that works are two different claims, and one test asserts each.
    Trying only the named key would fold them together, so a mock that published
    the right key under the wrong `kid` would fail both tests with one cause.
    """
    keys = key_set.get("keys")
    if not isinstance(keys, list):
        return None
    for key in keys:
        if isinstance(key, dict) and verify_rs256(
            signature.signing_input, signature.signature, key
        ):
            return key
    return None


class FormReader(HTMLParser):
    """Every form on an HTML page, with the fields it would submit.

    A parser rather than a regular expression, because what is being read is the
    launch page's contract with a browser — a form's action, its method, and the
    named values it carries — and a pattern over markup answers a different
    question that happens to look the same (`docs/MISTAKES.md` entry 3).

    `<select>` options are collected separately from fixed fields, because a
    launch page offering a choice of seeded users is one form with several
    outcomes, and the tests about "an arbitrary seeded user" need each outcome.

    **E0-16 widened what counts as a choice, and added `controls` and `labels`.**
    A login form offering six seeded identities is the same shape as a launch page
    offering several users, and it can legitimately be written three ways: a
    `<select>`, a set of same-named radio buttons, or a set of same-named submit
    buttons. All three are now read as choices, so the provider can be driven
    whichever the implementer picked — none of the launch pages has a radio or a
    named button, so nothing E0-14 or E0-15 asserts changes. `controls` and
    `labels` answer a different question again: whether a Playwright test could
    address the form without a brittle selector, which needs each control's
    attributes rather than the value it would submit.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.open_select: str | None = None
        self.open_option: str | None = None
        self.option_text: str = ""

    def current(self) -> dict[str, Any] | None:
        return self.forms[-1] if self.forms else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        if tag == "form":
            self.forms.append(
                {
                    "action": attributes.get("action", ""),
                    "method": (attributes.get("method") or "get").lower(),
                    "fields": {},
                    "choices": {},
                    "controls": [],
                    "labels": [],
                }
            )
            return
        form = self.current()
        if form is None:
            return
        if tag == "label":
            form["labels"].append(attributes.get("for", ""))
            return
        if tag in {"input", "textarea", "select", "button"}:
            form["controls"].append({"tag": tag, **attributes})
        if tag in {"input", "textarea"}:
            name = attributes.get("name")
            kind = attributes.get("type", "text").lower()
            if not name:
                return
            if kind in {"radio", "checkbox"}:
                # One of several values under one name: a choice, not a fixed
                # field. Recording it as a field would keep only the last one and
                # silently shrink the set of identities a login form offers.
                form["choices"].setdefault(name, []).append(attributes.get("value", "on"))
            else:
                form["fields"][name] = attributes.get("value", "")
        elif tag == "button":
            name = attributes.get("name")
            kind = (attributes.get("type") or "submit").lower()
            if name and kind == "submit":
                form["choices"].setdefault(name, []).append(attributes.get("value", ""))
        elif tag == "select":
            self.open_select = attributes.get("name") or None
            if self.open_select:
                form["choices"].setdefault(self.open_select, [])
        elif tag == "option" and self.open_select:
            # Closed here as well as on `</option>`, because HTML permits the
            # end tag to be omitted and a page that omits it would otherwise
            # lose every option but the last — which would silently shrink the
            # set of seeded launches the tests walk.
            self.close_option()
            self.open_option = attributes.get("value")
            self.option_text = ""

    def handle_data(self, data: str) -> None:
        if self.open_option is None and self.open_select:
            self.option_text += data

    def close_option(self) -> None:
        form = self.current()
        if form is None or not self.open_select:
            return
        value = self.open_option if self.open_option is not None else self.option_text.strip()
        if value:
            form["choices"][self.open_select].append(value)
        self.open_option = None
        self.option_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            self.close_option()
        elif tag == "select":
            self.close_option()
            self.open_select = None


def forms_in(markup: str) -> list[dict[str, Any]]:
    """Parse `markup` and hand back every form it declares."""
    reader = FormReader()
    reader.feed(markup)
    reader.close()
    return reader.forms


def form_submissions(form: Mapping[str, Any]) -> list[dict[str, str]]:
    """Every set of values `form` could submit, one per combination of choices."""
    choices = form.get("choices") or {}
    names = sorted(name for name, options in choices.items() if options)
    if not names:
        return [dict(form.get("fields") or {})]
    submissions: list[dict[str, str]] = []
    for combination in itertools.islice(
        itertools.product(*(choices[name] for name in names)), MAX_LAUNCH_VARIANTS
    ):
        values = dict(form.get("fields") or {})
        values.update(dict(zip(names, combination, strict=True)))
        submissions.append(values)
    return submissions


class LaunchOffer(NamedTuple):
    """One launch the platform's launch page offers a browser.

    `posts_to` is the form's action — the tool's third-party login-initiation
    URL — and `parameters` is what the form would send it. Those parameters are
    the OIDC third-party-initiated login request, so they are also where a test
    learns the seeded registration's issuer, client ID and deployment ID without
    any endpoint being invented to publish them.
    """

    page: str
    posts_to: str
    method: str
    parameters: dict[str, str]


class SignedLaunch(NamedTuple):
    """The result of driving one launch to the point the tool would receive it."""

    offer: LaunchOffer
    authorization_request: dict[str, str]
    id_token: str
    state: str | None
    posted_to: str | None
    signature: JsonWebSignature

    @property
    def claims(self) -> dict[str, Any]:
        return self.signature.claims

    @property
    def header(self) -> dict[str, Any]:
        return self.signature.header


def local_target(url: str) -> str:
    """`url` as an in-process test client can request it: its path and query.

    A mock advertises itself with absolute URLs built from whatever public base
    it is configured with, and that host is one a `TestClient` neither can nor
    should resolve — what is under test is the mock's own routing. Both mocks ask
    this question, so it is answered once (`docs/MISTAKES.md` entry 13).
    """
    split = urlsplit(url)
    target = split.path or "/"
    return f"{target}?{split.query}" if split.query else target


def url_with_query(url: str, query: Mapping[str, Any]) -> str:
    """`url` with `query` appended to whatever it already carries.

    Both mocks ask this — the platform to filter a line-item container, the
    provider to send a parameter in the query as well as in the body — so it is
    answered once (`docs/MISTAKES.md` entry 13). Appends rather than replaces: a
    name already in the URL and the same name added here is a URL carrying it
    twice, which for the provider is the whole question.
    """
    if not query:
        return url
    split = urlsplit(url)
    merged = parse_qsl(split.query) + [(name, str(value)) for name, value in query.items()]
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(merged), split.fragment))


def declared_paths(application: Any, method: str = "GET") -> list[str]:
    """Every path `application` declares that answers `method` and takes no parameter.

    No path parameter, so a caller can fetch every one of them without inventing
    a value — which is what makes "walk what this service serves" safe to do at
    all. Shared by both mocks for the reason `local_target` above is.
    """
    found: list[str] = []
    for route in application.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if isinstance(path, str) and "{" not in path and method in methods:
            found.append(path)
    return sorted(set(found))


class MockPackageFinder:
    """Resolve the `app` package out of one mock's directory for the length of an import.

    A mock is a second application whose package is *also* called `app`
    (SPEC §13), and this repository's own `app` is importable in the test
    process. Putting `mock-lms/` on `sys.path` is not enough to win that
    collision: an editable install of the backend registers a meta-path finder,
    and `sys.meta_path` is consulted before `sys.path` is, so a plain
    `import app` would return the backend's package on a developer's machine and
    possibly the mock's in CI — the same test measuring two different programs
    depending on how the project was installed.

    So the resolution is made explicit and temporary: this finder goes on the
    front of `sys.meta_path`, answers for `app` and everything under it out of
    the directory it was given, and comes off again. Nothing outside the import
    sees it.

    **It takes the directory as an argument**, which it did not when E0-14 wrote
    it, because E0-16 adds a second mock with exactly the same collision. Two
    copies of this class would be two copies of one rule about `sys.meta_path`,
    which is the shape `docs/MISTAKES.md` entry 13 is about.
    """

    def __init__(self, root: Path, package: str = MOCK_PACKAGE) -> None:
        self.root = root
        self.package = package

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname != self.package and not fullname.startswith(f"{self.package}."):
            return None
        parts = fullname.split(".")
        if len(parts) == 1:
            search = [str(self.root)]
        else:
            parent = sys.modules.get(".".join(parts[:-1]))
            search = list(getattr(parent, "__path__", []))
        return PathFinder.find_spec(fullname, search)


@contextmanager
def mock_package_resolved(root: Path, package: str = MOCK_PACKAGE) -> Iterator[None]:
    """Resolve `package` out of `root` for the body, and put `sys.modules` back after.

    Split out of `import_mock_application` below when E0-16 needed to import a
    *class* out of a mock rather than its application — the settings object whose
    redirect-URI validation has no HTTP surface to be tested through. The finder
    dance is the same either way and a second copy of it would be two copies of
    one rule about `sys.meta_path` (`docs/MISTAKES.md` entry 13).

    **Held open for the whole of the caller's work, not just the import.** A class
    taken out of a mock and used after the resolution closed would re-resolve any
    lazy import against this repository's own `app`, which is a different program;
    keeping the finder in place until the caller is finished means a method that
    imports something at call time still gets the mock's module.
    """
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name == package or name.startswith(f"{package}.")
    }
    for name in saved:
        sys.modules.pop(name, None)

    finder = MockPackageFinder(root, package)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        for name in [n for n in list(sys.modules) if n == package or n.startswith(f"{package}.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def import_mock_application(
    root: Path,
    modules: Sequence[str],
    values: Mapping[str, str],
    *,
    absent_directory: str,
    nothing_found: str,
    package: str = MOCK_PACKAGE,
) -> Any:
    """Import one mock fresh, under `values`, and return its ASGI application.

    Fresh every time, and that is the property the per-run key tests on both
    mocks rest on: "keys are generated per run" is only observable if a second
    start really is a second start. Every module of the mock's package is dropped
    before the import and the previous set is put back after, exactly as
    `import_app_module` does above and for the same reason — a module cached in
    `sys.modules` answers with the environment some earlier test set.

    What is found is a `FastAPI` instance at module level, or a factory that
    returns one. Both are legal — `uvicorn --factory` is how this repository
    starts its own — and neither mock's ticket names one, so naming one here
    would make the implementer build to this fixture instead of to the ticket.

    The two failure messages are arguments rather than text written here, because
    the mechanism is shared between the mocks and the *ticket* a missing
    deliverable belongs to is not.
    """
    from fastapi import FastAPI

    if not root.is_dir():
        pytest.fail(absent_directory)

    imported: list[ModuleType] = []
    with mock_package_resolved(root, package), environment(dict(values)):
        for name in modules:
            try:
                module = importlib.import_module(name)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                    continue
                raise
            imported.append(module)
            for attribute in sorted(vars(module)):
                candidate = getattr(module, attribute, None)
                if isinstance(candidate, FastAPI):
                    return candidate
            for attribute in APPLICATION_FACTORY_NAMES:
                factory = getattr(module, attribute, None)
                if callable(factory) and not inspect.isclass(factory):
                    built = factory()
                    if isinstance(built, FastAPI):
                        return built

    pytest.fail(nothing_found.format(imported=[m.__name__ for m in imported] or "nothing"))


def import_mock_lms_application(values: Mapping[str, str]) -> Any:
    """The mock platform's ASGI application. See `import_mock_application` above."""
    return import_mock_application(
        MOCK_LMS_DIR,
        MOCK_LMS_MODULES,
        values,
        absent_directory=(
            f"{MOCK_LMS_DIR} does not exist. E0-14's scope is a `mock-lms/` FastAPI application "
            "with a Dockerfile, added to Compose as `mock-lms` (SPEC §13 puts it at "
            "`mock-lms/app/`, and §9.2 says what it is for)."
        ),
        nothing_found=(
            "Nothing under `mock-lms/app/` exposes a FastAPI application. Looked for a "
            f"module-level instance, then a factory named one of {list(APPLICATION_FACTORY_NAMES)}"
            f", in {list(MOCK_LMS_MODULES)}; imported {{imported}}. E0-14's scope is a "
            "`mock-lms/` FastAPI application; if it is reachable under a spelling none of those "
            "covers, that is a defect in `MockPlatform` in tests/conftest.py rather than in the "
            "mock, and MOCK_LMS_MODULES there is the one line that changes."
        ),
    )


# ---------------------------------------------------------------------------
# E0-15 — the LTI Advantage services, reached the way a tool reaches them.
# ---------------------------------------------------------------------------

# The two service claims, **spelled as the IMS specifications spell them and not
# this suite's choice in any part**. In LTI Advantage a platform advertises its
# services inside the launch it has just signed: the NRPS claim carries the
# context memberships URL, and the AGS endpoint claim carries the line-items URL
# together with the scopes a token may be requested for. Reading them out of the
# token is how a real tool finds these services, which is why nothing below
# hardcodes a path — and a mock that serves them at fixed paths while putting no
# claim in the token has built something `pylti1p3` (SPEC §7.1) cannot find.
NRPS_CLAIM = "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice"
AGS_CLAIM = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"

# The context claim, from the same specification. `tests/integration/
# test_mock_lms_launch.py` spells it too, and both are transcriptions of one
# published constant rather than two copies of a decision: a launch spelling it
# differently fails there first, by name.
CONTEXT_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/context"

# The media types the Advantage services exchange, from NRPS 2.0 and AGS 2.0.
# Sent rather than assumed, because sending them is what a tool does. All four
# end in `+json`, which is also what lets a FastAPI endpoint declaring a JSON
# body parse them — FastAPI reads any `application/…+json` subtype as JSON — so
# using the specification's media type cannot fail a mock that expected plain
# `application/json`, while the reverse could.
NRPS_MEDIA_TYPE = "application/vnd.ims.lti-nrps.v2.membershipcontainer+json"
LINE_ITEM_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitem+json"
LINE_ITEM_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitemcontainer+json"
RESULT_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.resultcontainer+json"
SCORE_MEDIA_TYPE = "application/vnd.ims.lis.v1.score+json"

# Where a test reads back what the tool posted. **E0-15's spelling, not this
# suite's** (ADR 0047): a mock-only route outside the AGS namespace, answering
# `{"scores": [{"lineItem": …, "score": {…}}]}` in arrival order. It is named
# here rather than discovered, and the `/mock/` prefix is the reason — a fixture
# that went looking for a route whose path carries "score" would accept an AGS
# route serving the same thing, which is the one arrangement the prefix exists to
# rule out. A tool that learned this route would have learned something no real
# platform serves.
MOCK_POSTED_SCORES_PATH = "/mock/posted-scores"

# The two AGS scopes SPEC §3.4 needs: one line item per section, and a score
# posted to it. Specification constants, not preferences.
AGS_LINE_ITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
AGS_SCORE_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"

# How many pages of one paged container are walked before the walk is called
# broken. **This suite's choice**, and a bound rather than a rule: E0-15 keeps
# its seed small ("this seed data belongs to the mock platform and stays
# small"), so a container running past this is a `Link` header that never says
# stop rather than a large collection. Raise it if a seed grows.
MAX_PAGES_WALKED = 25

# One `<url>; rel="next"` entry of an RFC 8288 `Link` header. The parameter tail
# stops at a comma so that two entries in one header are read as two, which is
# the shape a platform sends when it offers `next` and `last` together.
LINK_HEADER_ENTRY = re.compile(r"<(?P<url>[^>]*)>(?P<parameters>(?:\s*;[^,;]*)*)")


def link_relations(header: str | None) -> dict[str, str]:
    """Every `rel` an RFC 8288 `Link` header declares, mapped to its URL.

    A parser rather than a substring search, for the reason `FormReader` above
    is a parser: what is being read is the platform's contract with a paging
    client, and `"next" in header` answers a different question that happens to
    look the same (`docs/MISTAKES.md` entry 3). A header carrying
    `rel="first next"` declares both relations on one URL, which is legal and
    which a substring search gets right for the wrong reason.

    The first URL declared for a relation wins, so a repeated `rel="next"` is
    read the way a client reads it rather than silently taking the last.
    """
    relations: dict[str, str] = {}
    if not header:
        return relations
    for entry in LINK_HEADER_ENTRY.finditer(header):
        url = entry.group("url").strip()
        for parameter in entry.group("parameters").split(";"):
            name, _, value = parameter.partition("=")
            if name.strip().lower() != "rel":
                continue
            for relation in value.strip().strip('"').split():
                relations.setdefault(relation.lower(), url)
    return relations


def instant(value: Any) -> datetime | None:
    """`value` as a moment in time, or `None` if it is not one.

    Timestamps are compared as instants rather than as strings, because
    `2026-09-14T18:30:00+00:00` and `2026-09-14T18:30:00Z` are one moment
    written two ways and a service that normalises between them has lost
    nothing. What the comparison is for is the near miss — a score recorder that
    stored the value it was sent and stamped its own clock over the timestamp —
    and that survives normalisation.

    A date with no time is accepted, at midnight: NRPS carries enrollment
    windows (SPEC §3.4, §7.3) and a window's edges are days.
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        # RFC 3339 §5.6 notes that `Z` may be written in lower case, and
        # `datetime.fromisoformat` does not accept the lower-case form — so a
        # conformant timestamp would read as "not a moment" and a test about
        # enrollment windows would report that the roster carries no dates.
        # Rewritten by position rather than by `replace`, which would also
        # rewrite a `Z` that was not the designator.
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class MembershipPage(NamedTuple):
    """One page of an NRPS membership container, with the header that pages it.

    `link_header` is kept raw as well as parsed, because the criterion is about
    the header — "a roster larger than one page returns `Link` headers" — and a
    failure that can print what was actually sent is worth more than one that
    can only say a relation was missing.
    """

    url: str
    status_code: int
    document: dict[str, Any]
    link_header: str | None
    relations: dict[str, str]
    members: list[dict[str, Any]]
    next_url: str | None


class SeededContext(NamedTuple):
    """One seeded section, and every launch the platform offers into it.

    `subjects` is the independent ground truth the paging tests need. Each is a
    user this platform will sign a launch for in this context, learned by
    driving the launch rather than by reading the roster, so a roster that has
    lost one has lost a member that demonstrably exists. It is a **lower bound**
    on the membership rather than the whole of it — the launch page offers a
    handful of users and a roster is bigger than that — and the test that leans
    on it says so.
    """

    context_id: str
    memberships_url: str
    launches: list[SignedLaunch]

    @property
    def subjects(self) -> set[str]:
        return {
            str(launch.claims["sub"])
            for launch in self.launches
            if isinstance(launch.claims.get("sub"), str)
        }


class MockPlatform:
    """E0-14's platform, driven the way a tool drives one rather than by name.

    **Nothing about the mock's URLs is written down**, so nothing here is
    hardcoded that the protocol can supply instead:

      - The launch page is found by *what it serves*: the page carrying a form
        with the OIDC third-party-initiated login parameters. That is the
        definition of a launch page rather than a guess at a path.
      - The registration values a test compares claims against — issuer, client
        ID, deployment ID, target link URI — are read out of that form, because
        those are exactly the parameters the initiation request carries.
      - The authorization endpoint and the key set are taken from the platform's
        OIDC discovery document when it serves one, and otherwise from the one
        route whose path names them.

    Two paths are all this leaves to a fragment match, and each fails with a
    message saying so. **What this does not do is decide anything**: where E0-14
    leaves a name open, a test fails naming the gap rather than passing against
    an interface the ticket never asked for.
    """

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        from fastapi.testclient import TestClient

        self.values = dict(values or {})
        self.application = import_mock_lms_application(self.values)
        self.client = TestClient(self.application, follow_redirects=False)
        # Entered so the application's lifespan runs: a platform that generates
        # its issuer key on startup has not generated one until it does.
        self.client.__enter__()

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    # -- what the application serves ----------------------------------------

    def paths(self, method: str = "GET") -> list[str]:
        """Every declared path that answers `method` and takes no path parameter."""
        return declared_paths(self.application, method)

    def path_named_after(self, fragments: tuple[str, ...], purpose: str) -> str:
        """The one route whose path carries one of `fragments`.

        Ambiguity stops rather than picks, the way `callable_named_after` does
        above: two candidates mean this cannot tell which one the ticket is
        about, and choosing would be the test deciding.
        """
        declared = sorted(set(self.paths("GET")) | set(self.paths("POST")))
        for fragment in fragments:
            matches = [path for path in declared if fragment in path.lower()]
            if len(matches) > 1:
                pytest.fail(
                    f"The mock platform declares more than one route whose path carries "
                    f"{fragment!r} ({matches}), so this cannot tell which one {purpose}. E0-14 "
                    "spells no URL, so naming one here would pin an interface the ticket leaves "
                    "open — say in the pull request which it is, and `MockPlatform` in "
                    "tests/conftest.py is the one place that changes."
                )
            if matches:
                return matches[0]
        pytest.fail(
            f"The mock platform declares no route whose path carries any of {list(fragments)} — "
            f"it declares {declared}. This is the endpoint that {purpose}, which E0-14's scope "
            "requires; if it is there under a path none of these fragments reaches, that is a "
            "defect in `MockPlatform` in tests/conftest.py rather than in the mock."
        )

    def discovery(self) -> dict[str, Any] | None:
        """The platform's OIDC discovery document, if it serves one."""
        for path in self.paths("GET"):
            if "openid-configuration" not in path:
                continue
            response = self.client.get(path)
            if response.status_code == 200:
                document = response.json()
                if isinstance(document, dict):
                    return document
        return None

    def endpoint(self, discovered: str, fragments: tuple[str, ...], purpose: str) -> str:
        """An endpoint path, from the discovery document if there is one."""
        document = self.discovery()
        if document:
            advertised = document.get(discovered)
            if isinstance(advertised, str) and advertised:
                return urlsplit(advertised).path or advertised
        return self.path_named_after(fragments, purpose)

    def jwks(self) -> dict[str, Any]:
        """The published key set, as JSON."""
        path = self.endpoint("jwks_uri", ("jwks", "keys"), "serves the platform's public keys")
        response = self.client.get(path)
        assert response.status_code == 200, (
            f"The JWKS endpoint `{path}` answered {response.status_code} rather than 200. E0-14's "
            "second acceptance criterion is that it serves a key that verifies an issued "
            "`id_token`, and a key set nobody can fetch verifies nothing."
        )
        document = response.json()
        assert isinstance(document, dict), (
            f"The JWKS endpoint `{path}` served {document!r}, which is not a JWK Set. RFC 7517 "
            "makes a key set a JSON object with a `keys` member."
        )
        return document

    def published_keys(self) -> list[dict[str, Any]]:
        keys = self.jwks().get("keys")
        return [key for key in keys if isinstance(key, dict)] if isinstance(keys, list) else []

    def verifies(self, token: Any) -> dict[str, Any] | None:
        """The published key that verifies `token`, or `None` if none does.

        Takes a compact JWS string or an already-split one, so a test that has
        tampered with a token can hand over the string it produced rather than
        rebuilding the split. Verification is the arithmetic in `verify_rs256`
        above; this only supplies the key set.
        """
        signature = token if isinstance(token, JsonWebSignature) else split_jws(str(token))
        return verifying_key(signature, self.jwks())

    # -- launches ------------------------------------------------------------

    def offers(self) -> list[LaunchOffer]:
        """Every launch the platform's launch page offers.

        Found by serving rather than by path: a launch page is the page carrying
        a form whose fields are an OIDC third-party-initiated login request, and
        `target_link_uri` plus `login_hint` are the two that request must carry.
        Only `GET` routes with no path parameter are fetched, so nothing here can
        have a side effect.
        """
        offers: list[LaunchOffer] = []
        for path in self.paths("GET"):
            response = self.client.get(path)
            if response.status_code != 200:
                continue
            if "html" not in response.headers.get("content-type", "").lower():
                continue
            for form in forms_in(response.text):
                names = set(form["fields"]) | set(form["choices"])
                if not {"target_link_uri", "login_hint"} <= names:
                    continue
                for parameters in form_submissions(form):
                    offers.append(
                        LaunchOffer(
                            page=path,
                            posts_to=urljoin(f"http://testserver{path}", form["action"]),
                            method=form["method"],
                            parameters=parameters,
                        )
                    )
        return offers

    def require_offers(self) -> list[LaunchOffer]:
        offers = self.offers()
        assert offers, (
            "The mock platform serves no page carrying a form with `target_link_uri` and "
            f"`login_hint` fields. Pages fetched: {self.paths('GET')}. E0-14's scope asks for "
            "'a launch page that posts the form to the tool, so a browser-driven test can click "
            "through a realistic launch', and those two fields are what make that form an OIDC "
            "third-party-initiated login request rather than an arbitrary form."
        )
        return offers

    def mint(
        self,
        offer: LaunchOffer | None = None,
        *,
        state: str | None = None,
        nonce: str | None = None,
    ) -> SignedLaunch:
        """Drive one launch to the point a tool would receive the `id_token`.

        This is E0-14's seventh criterion — "a test can obtain a signed launch
        for an arbitrary seeded user and role without a browser" — and it is done
        by *being* the tool: taking the platform's initiation request, answering
        it with an authorization request the way a tool would, and reading the
        `id_token` out of what comes back. Nothing is called that a real tool
        would not call, so a launch minted here and a launch a browser produces
        are the same launch.
        """
        chosen = offer or self.require_offers()[0]
        request = dict(AUTHORIZATION_REQUEST_CONSTANTS)
        request["state"] = state if state is not None else secrets.token_urlsafe(24)
        request["nonce"] = nonce if nonce is not None else secrets.token_urlsafe(24)
        request["redirect_uri"] = chosen.parameters.get("target_link_uri", "")
        for name in ("login_hint", "lti_message_hint", "client_id", "lti_deployment_id"):
            value = chosen.parameters.get(name)
            if value:
                request[name] = value

        path = self.endpoint(
            "authorization_endpoint",
            ("auth",),
            "receives the tool's authorization request and answers with a signed `id_token`",
        )
        # POST where the route accepts it, GET otherwise. Which of the two a
        # tool uses is the tool's choice under OIDC, so the endpoint's own
        # declaration decides rather than this file.
        if path in self.paths("POST"):
            response = self.client.post(path, data=request)
        else:
            response = self.client.get(path, params=request)

        id_token, returned_state, posted_to = self.read_authorization_response(response, path)
        return SignedLaunch(
            offer=chosen,
            authorization_request=request,
            id_token=id_token,
            state=returned_state,
            posted_to=posted_to,
            signature=split_jws(id_token),
        )

    def read_authorization_response(
        self, response: Any, path: str
    ) -> tuple[str, str | None, str | None]:
        """Pull the `id_token` and the returned `state` out of what the platform sent.

        Both shapes are accepted — the `form_post` auto-submitting form the LTI
        security framework specifies, and a redirect carrying the values in its
        query or fragment — because which one the mock uses is not something
        E0-14 decides, and refusing the second would fail a platform that is
        merely making a different legal choice.
        """
        if response.status_code == 200:
            for form in forms_in(response.text):
                fields = form["fields"]
                if "id_token" in fields:
                    return fields["id_token"], fields.get("state"), form["action"]
        location = response.headers.get("location")
        if location:
            split = urlsplit(location)
            for blob in (split.query, split.fragment):
                pairs = parse_qs(blob)
                if "id_token" in pairs:
                    returned = pairs.get("state") or [None]
                    return pairs["id_token"][0], returned[0], location
        pytest.fail(
            f"The authorization endpoint `{path}` answered {response.status_code} with no "
            "`id_token` in a form and none in a redirect, so no launch was produced. Body begins "
            f"{response.text[:300]!r}. E0-14 issues 'a signed `id_token` carrying the LTI 1.3 "
            "core claims'; the LTI 1.3 security framework returns it by `form_post` to the "
            "tool's redirect URI."
        )

    # -- the LTI Advantage services (E0-15) ----------------------------------

    def local(self, url: str) -> str:
        """`url` as this in-process client can request it: its path and query.

        The services advertise themselves with absolute URLs built from whatever
        public base the mock is configured with, and that host is one this
        client neither can nor should resolve — what is under test is the
        platform's own routing. That the advertised URL *is* absolute is
        asserted by a test rather than assumed here, because a relative one is a
        URL no real tool could follow.
        """
        return local_target(url)

    @staticmethod
    def refuse_an_unspecified_token_flow(response: Any, url: str) -> None:
        """Turn a 401 or a 403 into a named gap rather than a puzzling red.

        Real LTI Advantage services sit behind an OAuth 2.0 client-credentials
        grant against the platform's token endpoint. E0-15 does not mention one,
        E0-14 built none, and no ticket says what a tool would sign its
        assertion with — so this suite drives the services unauthenticated,
        which is the only reading of the ticket that does not invent an
        interface. If the mock requires a token, the answer is a sentence in the
        ticket, not a guess here.
        """
        if response.status_code in (401, 403):
            pytest.fail(
                f"The platform answered {response.status_code} for `{url}`, so it requires an "
                "access token for its Advantage services. E0-15 specifies no token endpoint and "
                "no grant, and E0-14 built neither, so this suite calls NRPS and AGS "
                "unauthenticated. What a tool should present is an interface question for the "
                "ticket rather than something to guess at in tests/conftest.py."
            )

    def service_get(self, url: str, accept: str | None = None) -> Any:
        """GET one Advantage URL the platform advertised."""
        response = self.client.get(self.local(url), headers={"accept": accept} if accept else None)
        self.refuse_an_unspecified_token_flow(response, url)
        return response

    def service_post(
        self,
        url: str,
        payload: Mapping[str, Any],
        content_type: str,
        accept: str | None = None,
    ) -> Any:
        """POST one JSON document to an Advantage URL, under the media type AGS fixes.

        The body is serialised here rather than handed to httpx's `json=`
        keyword, because that keyword would set `application/json` and overwrite
        the media type the specification requires the request to carry.
        """
        headers = {"content-type": content_type}
        if accept:
            headers["accept"] = accept
        response = self.client.post(self.local(url), content=json.dumps(payload), headers=headers)
        self.refuse_an_unspecified_token_flow(response, url)
        return response

    def service_claim(self, launch: SignedLaunch, claim: str, member: str, purpose: str) -> str:
        """One member of one service claim, or a failure naming what is missing.

        The failure is worth more than the value: a launch that carries no
        service claim is a platform whose services a conformant tool cannot
        discover at all, whatever it serves and wherever.
        """
        advertised = launch.claims.get(claim)
        if not isinstance(advertised, dict):
            pytest.fail(
                f"The `id_token` carries no `{claim}` claim (it carries "
                f"{sorted(launch.claims)}). That claim is how a platform tells a tool where "
                f"{purpose}; without it a tool has nothing to call, whatever the mock serves and "
                "at whatever path."
            )
        value = advertised.get(member)
        if not isinstance(value, str) or not value:
            pytest.fail(
                f"The `{claim}` claim carries no `{member}` (it carries {sorted(advertised)}). "
                f"That member is the URL {purpose}."
            )
        return value

    def memberships_url(self, launch: SignedLaunch) -> str:
        """Where this launch's context roster lives, per the NRPS claim."""
        return self.service_claim(
            launch,
            NRPS_CLAIM,
            "context_memberships_url",
            "the roster for the launched context is served",
        )

    def line_items_url(self, launch: SignedLaunch) -> str:
        """Where this launch's line items live, per the AGS endpoint claim."""
        return self.service_claim(
            launch,
            AGS_CLAIM,
            "lineitems",
            "the context's line items are listed and created",
        )

    def ags_scopes(self, launch: SignedLaunch) -> list[str]:
        """The scopes the AGS endpoint claim says a token may be requested for."""
        advertised = launch.claims.get(AGS_CLAIM)
        if not isinstance(advertised, dict):
            return []
        scopes = advertised.get("scope")
        if not isinstance(scopes, list):
            return []
        return [scope for scope in scopes if isinstance(scope, str)]

    def membership_page(self, url: str) -> MembershipPage:
        """Fetch one page of a membership container and read its paging header."""
        response = self.service_get(url, accept=NRPS_MEDIA_TYPE)
        assert response.status_code == 200, (
            f"The membership service answered {response.status_code} for `{url}` rather than 200. "
            "E0-15's first criterion is a roster whose members carry role and enrollment status, "
            f"and a roster nobody can fetch carries nothing. Body begins {response.text[:200]!r}."
        )
        return self.membership_page_of(url, response)

    def membership_page_of(self, url: str, response: Any) -> MembershipPage:
        """Read one already-fetched membership page, header and all.

        Split from the fetch so that the walk in `link_walk` above and a caller
        asking for a single page build a page the same way, from one place.
        """
        document = response.json()
        assert isinstance(document, dict), (
            f"The membership service served {document!r} for `{url}`, which is not an NRPS "
            "membership container. NRPS 2.0 makes the container a JSON object with `id`, "
            "`context` and `members` members; a bare array is the shape `pylti1p3` cannot read."
        )
        members = document.get("members")
        header = response.headers.get("link")
        relations = link_relations(header)
        following = relations.get("next")
        return MembershipPage(
            url=url,
            status_code=response.status_code,
            document=document,
            link_header=header,
            relations=relations,
            members=[member for member in members if isinstance(member, dict)]
            if isinstance(members, list)
            else [],
            next_url=urljoin(url, following) if following else None,
        )

    def link_walk(self, url: str, accept: str, subject: str) -> list[tuple[str, Any]]:
        """Fetch `url` and every page its `Link` header advertises, in order.

        One walk for both paged containers E0-15 serves — the roster and the
        line-item container, which the ticket pages "the same way NRPS does" —
        so that the guards below exist once rather than twice
        (`docs/MISTAKES.md` entry 13). What differs between the two callers is
        what a page *carries*, and that stays with the caller.

        Two ways of not terminating are failures rather than hangs, and neither
        is hypothetical: a `next` URL that points at the page that served it, and
        a header that advertises a next page forever. Both leave a real tool
        looping, so both are named where they happen rather than left to a
        pytest timeout that says only that something hung.
        """
        walked: list[tuple[str, Any]] = []
        visited: set[str] = set()
        following: str | None = url
        while following is not None:
            if following in visited:
                pytest.fail(
                    f"The {subject} walk arrived back at `{following}` after {len(walked)} pages, "
                    "so the `Link` header advertises a next page that is the page that served "
                    "it. A client following this header never finishes."
                )
            visited.add(following)
            response = self.service_get(following, accept=accept)
            assert response.status_code == 200, (
                f"Page {len(walked) + 1} of the {subject} at `{following}` answered "
                f"{response.status_code} rather than 200, so the `Link` header that pointed here "
                f"points at nothing. Body begins {response.text[:200]!r}."
            )
            walked.append((following, response))
            if len(walked) > MAX_PAGES_WALKED:
                pytest.fail(
                    f"The {subject} at `{url}` ran past {MAX_PAGES_WALKED} pages without reaching "
                    "one that advertises no next relation. E0-15 keeps the seed small, so this is "
                    "a header that never says stop rather than a large collection — and a tool "
                    "paging on it does not stop either."
                )
            relations = link_relations(response.headers.get("link"))
            advertised = relations.get("next")
            following = urljoin(following, advertised) if advertised else None
        return walked

    def membership_pages(self, url: str) -> list[MembershipPage]:
        """Walk a roster from its first page to its last. Exactly what a sync does."""
        return [
            self.membership_page_of(page_url, response)
            for page_url, response in self.link_walk(url, NRPS_MEDIA_TYPE, "roster")
        ]

    def seeded_contexts(self) -> list[SeededContext]:
        """Every context the launch page offers a launch into, with those launches.

        Grouped by the context claim's `id`, so that a page offering four users
        in two sections answers two contexts rather than four. The memberships
        URL is taken from the first launch into each context, which is the URL
        that context's own roster lives at.
        """
        grouped: dict[str, list[SignedLaunch]] = {}
        for offer in self.require_offers():
            launch = self.mint(offer)
            context = launch.claims.get(CONTEXT_CLAIM)
            identifier = context.get("id") if isinstance(context, dict) else None
            if not isinstance(identifier, str) or not identifier:
                pytest.fail(
                    f"A launch from `{offer.page}` carries no context `id` (its context claim is "
                    f"{context!r}). E0-14's own suite asserts that claim, so this is that failure "
                    "arriving here first; without it a roster cannot be attributed to a section."
                )
            grouped.setdefault(identifier, []).append(launch)
        return [
            SeededContext(
                context_id=identifier,
                memberships_url=self.memberships_url(launches[0]),
                launches=launches,
            )
            for identifier, launches in sorted(grouped.items())
        ]

    def create_line_item(
        self,
        launch: SignedLaunch,
        *,
        omitting: Sequence[str] = (),
        **overrides: Any,
    ) -> dict[str, Any]:
        """Create one line item and hand back what the platform stored.

        The default body is SPEC §3.4's: one line item per section labelled
        "Pulse Participation", scored out of 100. `resourceId` is drawn fresh per
        call so that a test asking whether *its* line item appears in a listing
        is not answered by a seeded one.

        `omitting` sends a body with those keys **absent**, which `overrides`
        cannot express: `tag=None` posts `{"tag": null}`, and a null member and a
        missing member are two different bodies that a filter is entitled to
        treat differently — the missing one is the case a fail-open filter
        matches. It is a keyword rather than a sentinel value so that the call
        site reads as what it does, and a name that was not there to omit is a
        failure rather than a silent no-op, because a misspelling would
        otherwise leave a test quietly asserting nothing about the body it meant
        to send.
        """
        payload: dict[str, Any] = {
            "scoreMaximum": 100,
            "label": "Pulse Participation",
            "resourceId": f"e0-15-{uuid4().hex[:12]}",
            "tag": "participation",
        }
        payload.update(overrides)
        return self.created_line_item(launch, payload, omitting)

    def post_line_item(
        self,
        launch: SignedLaunch,
        payload: Mapping[str, Any],
    ) -> Any:
        """POST one line-item body and hand back the response, asserting nothing.

        `create_line_item` requires success, which is right for the callers that
        need a line item to work with and wrong for the ones asking what the
        container *refuses*. Those need the raw answer, and they need it without
        knowing the media type AGS fixes for the request.
        """
        return self.service_post(
            self.line_items_url(launch),
            payload,
            LINE_ITEM_MEDIA_TYPE,
            accept=LINE_ITEM_MEDIA_TYPE,
        )

    def created_line_item(
        self,
        launch: SignedLaunch,
        payload: dict[str, Any],
        omitting: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Post `payload`, require it created, and hand back what was stored."""
        for name in omitting:
            if name not in payload:
                pytest.fail(
                    f"`create_line_item(omitting={list(omitting)})` was asked to leave out "
                    f"`{name}`, which this body does not carry — it carries {sorted(payload)}. "
                    "A key that is already absent cannot be omitted, and a misspelling here "
                    "would post the very member the caller meant to leave out."
                )
            payload.pop(name)
        response = self.post_line_item(launch, payload)
        assert response.status_code in (200, 201), (
            f"Creating a line item answered {response.status_code} rather than 200 or 201. E0-15 "
            "criterion 3: line-item creation returns an identifier that score posting accepts. "
            f"Body begins {response.text[:200]!r}."
        )
        created = response.json()
        assert isinstance(created, dict), (
            f"Creating a line item answered {created!r}, which is not an AGS line item. AGS 2.0 "
            "makes it a JSON object whose `id` is the line item's own URL."
        )
        return created

    def with_query(self, url: str, query: Mapping[str, Any]) -> str:
        """`url` with `query` appended to whatever it already carries."""
        return url_with_query(url, query)

    def line_item_container(self, url: str) -> list[dict[str, Any]]:
        """One page of an AGS line-item container, as a list.

        AGS 2.0 serves an array; a mock that wraps it in an object is read here
        rather than failed, because which of the two E0-15 meant is not
        something this file decides — what every caller needs is the line items.
        """
        response = self.service_get(url, accept=LINE_ITEM_CONTAINER_MEDIA_TYPE)
        assert response.status_code == 200, (
            f"Listing line items at `{url}` answered {response.status_code} rather than 200. "
            "E0-15's scope: 'Assignment and Grade Services 2.0 stubs: line-item creation and "
            f"listing'. Body begins {response.text[:200]!r}."
        )
        return self.line_items_of(response)

    def line_items_of(self, response: Any) -> list[dict[str, Any]]:
        """Read the line items out of an already-fetched container page."""
        listed = response.json()
        if isinstance(listed, dict):
            listed = listed.get("lineItems") or listed.get("line_items") or listed.get("items")
        assert isinstance(listed, list), (
            f"Listing line items answered {response.json()!r}, which is not a line item "
            "container. AGS 2.0 serves an array of line items."
        )
        return [item for item in listed if isinstance(item, dict)]

    def line_items(self, launch: SignedLaunch, **query: Any) -> list[dict[str, Any]]:
        """The line items the platform lists for this launch's context, one page.

        `query` is passed to the container as it stands, so a test asking for
        `resource_id=…` is asking the platform the question AGS 2.0 defines
        rather than filtering the answer itself — which is the only way to tell a
        platform that honours the filter from one that accepts it and ignores it.
        """
        return self.line_item_container(self.with_query(self.line_items_url(launch), query))

    def line_item_pages(self, launch: SignedLaunch, **query: Any) -> list[list[dict[str, Any]]]:
        """Every page of the line-item container, walked by `Link` as the roster is."""
        return [
            self.line_items_of(response)
            for _, response in self.link_walk(
                self.with_query(self.line_items_url(launch), query),
                LINE_ITEM_CONTAINER_MEDIA_TYPE,
                "line item container",
            )
        ]

    def post_score(self, line_item: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
        """POST one score against a line item, to the URL AGS derives from its `id`.

        `{lineitem}/scores` is the specification's own construction rather than
        this file's guess: AGS 2.0 defines the Score service as the line item URL
        with `/scores` appended, which is why criterion 3 can speak of an
        identifier "that score posting accepts" without naming a second URL.
        """
        identifier = self.line_item_id(line_item)
        return self.service_post(f"{identifier.rstrip('/')}/scores", payload, SCORE_MEDIA_TYPE)

    def line_item_id(self, line_item: Mapping[str, Any]) -> str:
        """A line item's own URL, or a failure saying it has none."""
        identifier = line_item.get("id")
        if not isinstance(identifier, str) or not identifier:
            pytest.fail(
                f"The line item {line_item!r} carries no `id`, so there is no URL to address it "
                "by. E0-15 criterion 3: 'AGS line-item creation returns an identifier that score "
                "posting accepts.'"
            )
        return identifier

    def posted_scores(self) -> list[dict[str, Any]]:
        """Every score the platform has been sent, in the order it received them.

        E0-15 settles this surface rather than leaving it to be discovered:
        `GET /mock/posted-scores`, outside the AGS namespace, answering
        `{"scores": [{"lineItem": …, "score": {…}}]}` in arrival order (ADR
        0047). So the shape is asserted here rather than normalised — an earlier
        version of this helper accepted four shapes because the ticket named
        none, and every one of the three it no longer accepts is now a mock that
        does not do what the ticket says.
        """
        response = self.service_get(MOCK_POSTED_SCORES_PATH)
        assert response.status_code == 200, (
            f"`GET {MOCK_POSTED_SCORES_PATH}` answered {response.status_code} rather than 200. "
            "E0-15 criterion 4 reads a posted score back from exactly this route, outside the AGS "
            f"namespace. Body begins {response.text[:200]!r}."
        )
        document = response.json()
        assert isinstance(document, dict), (
            f"`{MOCK_POSTED_SCORES_PATH}` served {document!r}. E0-15 spells the body "
            '`{"scores": [{"lineItem": …, "score": {…}}]}`.'
        )
        entries = document.get("scores")
        assert isinstance(entries, list), (
            f"`{MOCK_POSTED_SCORES_PATH}` served an object carrying {sorted(document)} rather "
            "than a `scores` array. A bare array, or the scores under another key, is a shape "
            "E0-15 does not describe and a test cannot read as arrival order."
        )
        return [entry for entry in entries if isinstance(entry, dict)]

    def posted_scores_for(self, line_item: Mapping[str, Any]) -> list[dict[str, Any]]:
        """The scores posted to one line item, in the order they arrived."""
        identifier = self.line_item_id(line_item)
        return [entry for entry in self.posted_scores() if entry.get("lineItem") == identifier]

    def results(self, line_item: Mapping[str, Any], **query: Any) -> list[dict[str, Any]]:
        """The conformant AGS Result container for one line item.

        The other half of E0-15's readback, and the one E3 is built against. AGS
        2.0 puts the Result service at the line item URL with `/results`
        appended, and a `Result` carries `userId`, `resultScore`,
        `resultMaximum` and `scoreOf` — no timestamp, no progress. That absence
        is a criterion of its own, which is why this is reached separately from
        `posted_scores` rather than folded into it.
        """
        identifier = self.line_item_id(line_item)
        response = self.service_get(
            self.with_query(f"{identifier.rstrip('/')}/results", query),
            accept=RESULT_CONTAINER_MEDIA_TYPE,
        )
        assert response.status_code == 200, (
            f"The AGS Result service answered {response.status_code} for line item "
            f"`{identifier}`. E0-15: 'The conformant AGS Results endpoint answers for the same "
            f"line item.' Body begins {response.text[:200]!r}."
        )
        listed = response.json()
        if isinstance(listed, dict):
            listed = listed.get("results")
        assert isinstance(listed, list), (
            f"The AGS Result service served {response.json()!r}, which is not a result container. "
            "AGS 2.0 serves an array of results."
        )
        return [result for result in listed if isinstance(result, dict)]


@pytest.fixture
def repo_root() -> Path:
    """The repository root, for the tests that sweep the whole tree."""
    return REPO_ROOT


@pytest.fixture
def mock_lms_dir() -> Path:
    """Where the mock platform must live (SPEC §13). Asserted by the test, not here."""
    return MOCK_LMS_DIR


@pytest.fixture
def mock_lms_service() -> str:
    """The Compose service name SPEC §7.2 gives the mock platform."""
    return MOCK_LMS_SERVICE


@pytest.fixture
def mock_platforms() -> Iterator[Callable[..., MockPlatform]]:
    """Start one or more independent mock platforms, and shut them all down after.

    A factory rather than a single instance because two of E0-14's criteria are
    about *two* platforms: issuer keys generated per run means a second start
    generates a second key, and a key set that verifies its own launches has to
    refuse someone else's. Neither is observable from one instance.
    """
    started: list[MockPlatform] = []

    def start(values: Mapping[str, str] | None = None) -> MockPlatform:
        platform = MockPlatform(values)
        started.append(platform)
        return platform

    try:
        yield start
    finally:
        for platform in reversed(started):
            platform.close()


@pytest.fixture
def mock_platform(mock_platforms: Callable[..., MockPlatform]) -> MockPlatform:
    """One mock platform, started fresh for this test. See `MockPlatform` above."""
    return mock_platforms()


@pytest.fixture
def signed_launch(mock_platform: MockPlatform) -> SignedLaunch:
    """One signed launch off the first seeded offer.

    E0-14's definition of done names this: "a reusable fixture that mints a
    signed launch — E1's launch-validation tests depend on it, so its interface
    matters". `mock_platform.mint(...)` is the interface; this fixture is the
    common case of it.
    """
    return mock_platform.mint()


@pytest.fixture
def link_relations_in() -> Callable[[str | None], dict[str, str]]:
    """Hand `link_relations` to a test that checks the parser itself.

    The walk in `MockPlatform.membership_pages` reads paging headers with this
    same function, so the control test and the thing it controls cannot end up
    disagreeing about what a `Link` header says — which is the whole value of
    the control (`docs/MISTAKES.md` entry 3: run the pattern against the text
    you claim it catches *and* the text you claim it allows).
    """
    return link_relations


@pytest.fixture
def instant_of() -> Callable[[Any], datetime | None]:
    """Hand `instant` to a test that has to compare two spellings of one moment.

    The seeded rosters ask it: an enrollment window's `start` and `end` are
    moments, and whether one member enrolled after another is a question about
    instants rather than about strings.

    **The AGS round trip deliberately does not**, and the asymmetry is worth
    knowing before someone tidies it away. E0-15 records a posted score "the
    posted body, verbatim" (ADR 0047), so there the spelling *is* the fact: a
    recorder that re-renders `+00:00` as `Z` has stopped carrying what the tool
    sent, and comparing instants would call that agreement.
    """
    return instant


# E0-09 — role assignments and the supervision graph.
# ---------------------------------------------------------------------------

# Spelled by the ticket and by SPEC §8's table list, so not this file's choice.
ROLE_ASSIGNMENT_TABLE = "role_assignment"
LEAD_FACULTY_MAPPING_TABLE = "lead_faculty_mapping"
E0_09_TABLES = (ROLE_ASSIGNMENT_TABLE, LEAD_FACULTY_MAPPING_TABLE)

# SPEC §2.1's containment hierarchy, outermost first. Used to build a sibling
# node at a given level: everything strictly above it is kept, everything at or
# below it is built fresh.
CONTAINMENT_ORDER = ("institution", "college", "department", "prefix", "course", "section")

# The three columns E0-09 and SPEC §8 both spell — `person_id`, `role`,
# `scope_node_id` — plus `reports_to`. Each is a candidate list rather than a
# literal, because the ticket's prose spelling and a model's column name are
# allowed to differ and a rename should be a one-line change here rather than a
# rewrite of two test modules. The spelled name is always first.
ROLE_COLUMN_CANDIDATES = ("role", "role_name", "role_code")
REPORTS_TO_CANDIDATES = (
    "reports_to",
    "reports_to_id",
    "reports_to_assignment_id",
    "parent_assignment_id",
    "supervisor_assignment_id",
)
SCOPE_ID_CANDIDATES = ("scope_node_id", "scope_id", "org_node_id", "node_id")
SCOPE_KIND_CANDIDATES = (
    "scope_node_kind",
    "scope_kind",
    "scope_node_type",
    "scope_type",
    "node_kind",
    "node_type",
    "scope_level",
)

# How each role is spelled, as exact alternatives matched case-insensitively
# against whatever the `role` column enumerates. Five of the nine come straight
# out of SPEC §2.1's canonical chain — `INSTRUCTOR(section) → LEAD_FACULTY(course)
# → CHAIR(department) → DEAN(college) → VP_ACADEMICS` — and `CARE` out of E0-09's
# own scope; the rest are **this file's choice** of the obvious spelling, with one
# or two alternatives each. Matching is exact rather than by substring on purpose:
# `DEAN` is a substring of `ASSISTANT_DEAN`, and a fuzzy match that resolved the
# two to one enum value would silently make every assistant-dean test a second
# dean test.
ROLE_ALIASES = {
    "INSTRUCTOR": ("INSTRUCTOR",),
    "LEAD_FACULTY": ("LEAD_FACULTY", "LEAD"),
    "CHAIR": ("CHAIR", "DEPARTMENT_CHAIR", "DEPT_CHAIR"),
    "ASSISTANT_DEAN": ("ASSISTANT_DEAN", "ASST_DEAN"),
    "DEAN": ("DEAN",),
    "VP_ACADEMICS": ("VP_ACADEMICS", "VPAA", "VP_OF_ACADEMICS"),
    "CARE": ("CARE",),
    "ADMIN": ("ADMIN",),
    "STUDENT": ("STUDENT",),
}

# The kind of containment node each role is scoped to. E0-09's scope: "a chair
# scoped to a department, a dean to a college, a lead to a course, **Care and
# Admin to the institution**"; SPEC §2.1's table gives the instructor a section
# and the VP the institution, and puts the assistant dean on "the same node as
# the dean". `STUDENT` is deliberately absent: §2.1 attaches a student to "own
# responses" rather than to a node, and no ticket says a student holds a
# `role_assignment` row at all.
ROLE_SCOPE_GRAIN = {
    "INSTRUCTOR": "section",
    "LEAD_FACULTY": "course",
    "CHAIR": "department",
    "ASSISTANT_DEAN": "college",
    "DEAN": "college",
    "VP_ACADEMICS": "institution",
    "CARE": "institution",
    "ADMIN": "institution",
}

# Distinguishes "no parent was asked for" from "the parent is explicitly NULL",
# which a nullable column needs: `seed_row` honours an override that is `None`.
UNSET = object()

# ---------------------------------------------------------------------------
# Values the seeding helper invents. Guesses about *values* only — nothing here
# decides that a column exists or what it is called, and nothing here is read by
# an assertion. Chosen to be mutually consistent with the calendar E0-06
# enforces, so that a cross-column check constraint cannot reject the helper's
# own rows and leave a test failing inside its fixture: an 18-week fall term
# running 8/17 to 12/20. A copy of `test_identity_schema.py`'s set.
# ---------------------------------------------------------------------------

GRAPH_TERM_START = date(2026, 8, 17)
GRAPH_TERM_END = date(2026, 12, 20)
GRAPH_LENGTH_WEEKS = 18
GRAPH_WEEK_CEILING = 18
GRAPH_WINDOW_OPENS_AT = datetime(2026, 8, 21, 22, 0, tzinfo=UTC)
GRAPH_WINDOW_CLOSES_AT = datetime(2026, 8, 24, 3, 59, 59, tzinfo=UTC)

GRAPH_DATE_HINTS = (
    ("start", GRAPH_TERM_START),
    ("begin", GRAPH_TERM_START),
    ("end", GRAPH_TERM_END),
)
GRAPH_DATETIME_HINTS = (
    ("open", GRAPH_WINDOW_OPENS_AT),
    ("close", GRAPH_WINDOW_CLOSES_AT),
    ("end", GRAPH_WINDOW_CLOSES_AT),
)
GRAPH_LENGTH_FRAGMENTS = ("length", "weeks", "duration")

# Two columns whose value this file has to choose deliberately, because each is
# governed by **two** rules from an earlier ticket and satisfying one of them is
# what breaks the other. A course number has to sit inside SPEC §8's bands *and*
# be unique within its prefix (E0-05's `uq_course_prefix_id_lms_number`); a
# section code has to match §2.2's shape *and* be unique within its course and
# term (E0-06's `UniqueConstraint("course_id", "term_id", "lms_section_code")`).
#
# An earlier version of this file pinned the course number to the constant
# `"150"`, which met the band rule and violated the uniqueness one the moment a
# test asked for a second course under one prefix — `fresh_scope("course")` keeps
# the shared `prefix` row on purpose, because two courses under one prefix is
# what a sibling lead *is*. Three tests were blocked before any assertion ran and
# it took a dispute to settle ([E0-09-01](../docs/disputes/E0-09-01.md)). Both
# values are now drawn fresh per call.
GRAPH_SECTION_CODE_COLUMN = "lms_section_code"
GRAPH_COURSE_NUMBER_COLUMN = "lms_number"

# The band a generated course number is drawn from: three digits, `100`-`799`,
# which SPEC §8 splits into UG, UGGR and GR. Staying inside a band matters more
# than which band, because the bands are not enforced by a `CHECK`: `course.level`
# is a stored generated column ([ADR 0015](../docs/adr/0015-course-level-is-a-stored-generated-column.md))
# and an out-of-band number derives `NULL::course_level`, so the row is refused by
# that column's `NOT NULL` and the error names the level rather than the number.
# `000`-`099` is left out only because it needs zero padding to stay three digits,
# and a padded number is a case E0-05's own tests own rather than this fixture's.
GRAPH_COURSE_NUMBER_FIRST = 100
GRAPH_COURSE_NUMBER_LAST = 799

_GRAPH_UNIQUE = count(1)
_GRAPH_INTEGER_COUNTERS: dict[tuple[str, str], Any] = {}


def graph_letters(limit: int | None) -> str:
    """A short, unique, upper-case string that fits a column of length `limit`.

    Upper-case letters and nothing else, because a code column plausibly carries
    a format check and a hex string would trip it — failing a test inside its own
    seeding for a reason it is not about.
    """
    width = max(min(6, limit or 6), 1)
    value = next(_GRAPH_UNIQUE)
    out = []
    for _ in range(width):
        value, remainder = divmod(value, 26)
        out.append(string.ascii_uppercase[remainder])
    return "".join(reversed(out))


def graph_unique_url() -> str:
    """A URL no other seeded row will carry, since an issuer is plausibly unique."""
    return f"https://{graph_letters(6).lower()}.example.invalid"


def graph_unique_email() -> str:
    """An address no other seeded row will carry, for the same reason."""
    return f"{graph_letters(6).lower()}@example.invalid"


GRAPH_STRING_HINTS = (
    ("timezone", lambda: "America/New_York"),
    ("email", graph_unique_email),
    ("issuer", graph_unique_url),
    ("iss", graph_unique_url),
    ("url", graph_unique_url),
    ("uri", graph_unique_url),
    ("jwks", graph_unique_url),
)


def graph_course_number() -> str:
    """A course number no other course in this test carries, inside SPEC §8's bands.

    Counts up from `GRAPH_COURSE_NUMBER_FIRST` rather than wrapping around it, and
    the difference is the whole repair: a generator that wrapped would hand out a
    duplicate again once a test asked for enough courses, and the failure would
    look exactly like the one this replaces — a unique violation on an E0-05
    constraint, raised inside a fixture, from a statement naming no column E0-09
    owns.

    **Per test rather than per session**, which is enough here and is the reason
    it borrows `_GRAPH_INTEGER_COUNTERS`: that dict is cleared by the
    `supervision_graph` fixture for every test, and `db_session` rolls every write
    back at the end of one, so two tests cannot see each other's courses. One
    reset mechanism serves both counters, rather than a second one beside it that
    could drift out of step (`docs/MISTAKES.md` entry 13).

    **Not `graph_letters`, which is what the section code beside it uses.** That
    draws from a session-wide counter one letter wide, so it repeats every 26
    calls; a course number built the same way would reintroduce a rarer and
    order-dependent version of this same defect, and rarer is worse — it would
    surface as a flake in somebody else's ticket.
    """
    counter = _GRAPH_INTEGER_COUNTERS.setdefault(
        ("course", GRAPH_COURSE_NUMBER_COLUMN), count(GRAPH_COURSE_NUMBER_FIRST)
    )
    number = next(counter)
    if number > GRAPH_COURSE_NUMBER_LAST:
        available = GRAPH_COURSE_NUMBER_LAST - GRAPH_COURSE_NUMBER_FIRST + 1
        pytest.fail(
            f"This test asked for more than {available} courses, so the seeding helper has run "
            f"out of three-digit numbers inside SPEC §8's bands. It stops here rather than "
            f"starting again at {GRAPH_COURSE_NUMBER_FIRST}: reusing a number would write a "
            "second course with the same number under the same prefix, which E0-05's "
            "`uq_course_prefix_id_lms_number` refuses — and that failure would be a unique "
            "violation raised inside a fixture rather than a message naming its cause, which is "
            "the shape this generator exists to leave behind. If a test genuinely needs this many "
            "courses, widen the band in tests/conftest.py: `000`-`099` is available with zero "
            "padding."
        )
    return str(number)


GRAPH_COLUMN_VALUES = {
    ("course", GRAPH_COURSE_NUMBER_COLUMN): graph_course_number,
    ("section", GRAPH_SECTION_CODE_COLUMN): lambda: f"{graph_letters(1)}3WW",
}


def stored_type(column: Any) -> Any:
    """The type a column actually stores, with any `TypeDecorator` resolved away.

    A `TypeDecorator` is not an instance of the type it decorates, and dispatching
    on the declared type instead of this one is what cost E0-06 a dispute
    (`docs/MISTAKES.md` entry 13). ADR 0019 puts the naive-datetime guard on a
    column type, so decorated timestamps are expected here rather than exotic.
    """
    from sqlalchemy.types import TypeDecorator

    kind = column.type
    while isinstance(kind, TypeDecorator):
        kind = kind.impl_instance
    return kind


def invented_value(table: Any, column: Any) -> Any:
    """Something a NOT NULL column of unknown purpose will accept.

    Deliberately dumb about meaning and careful about type. A column this cannot
    answer for stops the test with a message naming it, rather than inserting
    `None` and failing later somewhere that reads like a schema defect.
    """
    from sqlalchemy import (
        Boolean,
        Date,
        DateTime,
        Enum,
        Integer,
        LargeBinary,
        Numeric,
        String,
        Uuid,
    )

    maker = GRAPH_COLUMN_VALUES.get((table.name, column.name))
    if maker is not None:
        return maker()

    kind = stored_type(column)
    lowered = column.name.lower()
    if isinstance(kind, Enum):
        values = list(getattr(kind, "enums", ()) or ())
        if values:
            return values[0]
    elif isinstance(kind, Uuid):
        return uuid4()
    elif isinstance(kind, Boolean):
        return False
    elif isinstance(kind, DateTime):
        for fragment, value in GRAPH_DATETIME_HINTS:
            if fragment in lowered:
                return value
        return GRAPH_WINDOW_OPENS_AT
    elif isinstance(kind, Date):
        for fragment, value in GRAPH_DATE_HINTS:
            if fragment in lowered:
                return value
        return GRAPH_TERM_START
    elif isinstance(kind, Integer):
        if any(fragment in lowered for fragment in GRAPH_LENGTH_FRAGMENTS):
            return GRAPH_LENGTH_WEEKS
        counter = _GRAPH_INTEGER_COUNTERS.setdefault((table.name, column.name), count(1))
        return 1 + (next(counter) - 1) % GRAPH_WEEK_CEILING
    elif isinstance(kind, Numeric):
        return Decimal("1")
    elif isinstance(kind, LargeBinary):
        return graph_letters(None).encode()
    elif isinstance(kind, String):
        limit = getattr(kind, "length", None)
        for fragment, maker in GRAPH_STRING_HINTS:
            if fragment in lowered:
                hint = maker()
                if limit is None or len(hint) <= limit:
                    return hint
        return graph_letters(limit)

    pytest.fail(
        f"The seeding helper in tests/conftest.py cannot invent a value for `{table.name}."
        f"{column.name}`, which is NOT NULL, has no default, and is of type {column.type!r}. That "
        "is this fixture needing a case added, not a defect in the schema — add the type to "
        "`invented_value`."
    )


def require_table(tables: dict[str, Any], name: str) -> Any:
    """The table called `name`, or a failure saying it is not there."""
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E0-09 creates "
            f"{list(E0_09_TABLES)} and E0-05 creates {list(CONTAINMENT_ORDER)}; the existence "
            "tests are the assertion for that, and everything else needs the table first."
        )
    return table


def require_column(table: Any, candidates: tuple[str, ...]) -> str:
    """The first of `candidates` that `table` has, or a failure listing both sides."""
    for candidate in candidates:
        if candidate in table.c:
            return candidate
    present = [column.name for column in table.columns]
    pytest.fail(
        f"`{table.name}` has none of the columns {list(candidates)} — it has {present}. The "
        "candidate list is a constant in tests/conftest.py, so a deliberate rename is a one-line "
        "change there."
    )


def single_primary_key(table: Any) -> str:
    """The name of `table`'s one primary key column.

    One, because [ADR 0016](../docs/adr/0016-primary-keys-are-database-generated-uuids.md)
    makes every primary key here a single server-generated uuid.
    """
    columns = list(table.primary_key.columns)
    if len(columns) != 1:
        pytest.fail(
            f"`{table.name}` has {len(columns)} primary key columns "
            f"({[column.name for column in columns]}). ADR 0016 makes every primary key one uuid "
            "with a server default, and these fixtures address rows by it."
        )
    return columns[0].name


def foreign_key_columns(table: Any, target: str) -> list[str]:
    """Every column on `table` whose foreign key points at `target`, sorted.

    Found by following the key rather than by guessing a name, so a reference
    spelled any way at all is picked up — which is the whole mechanism behind
    E0-09's first criterion.
    """
    return sorted(
        {key.parent.name for key in table.foreign_keys if key.column.table.name == target}
    )


def seed_row(
    session: Any,
    tables: dict[str, Any],
    name: str,
    chain: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    """Insert one row into `name`, building whatever ancestors it requires.

    `chain` is the set of ancestor rows built so far, keyed by table name, so a
    caller can put two rows under one parent by passing the same chain and two
    rows under different parents by passing different ones.

    Columns are filled only where the schema requires it: anything generated,
    defaulted or nullable is left to the database, which matters because every
    primary key is a server-defaulted `gen_random_uuid()` (ADR 0016) and has to
    be read back with RETURNING rather than predicted. An override is honoured
    even when it is `None`, so a test can write a null and let the database
    accept or refuse it.
    """
    chain = {} if chain is None else chain
    table = require_table(tables, name)
    values: dict[str, Any] = dict(overrides)

    for column in table.columns:
        if column.name in values:
            continue
        if column.computed is not None or column.identity is not None:
            continue
        if column.server_default is not None or column.default is not None:
            continue
        if column.foreign_keys and not column.nullable:
            ordered = sorted(column.foreign_keys, key=lambda fk: str(fk.target_fullname))
            target = ordered[0].column
            if target.table.name not in chain:
                chain[target.table.name] = seed_row(session, tables, target.table.name, chain)
            values[column.name] = chain[target.table.name][target.name]
            continue
        if column.nullable:
            continue
        values[column.name] = invented_value(table, column)

    statement = table.insert().values(**values).returning(*table.columns)
    inserted = session.execute(statement).mappings().one()
    chain.setdefault(name, inserted)
    return inserted


class SupervisionGraph:
    """E0-09's assignment graph, built without naming what a scope is made of.

    **What it decides and what it refuses to.** The ticket spells four columns on
    `role_assignment` — `person_id`, `role`, `scope_node_id`, `reports_to` — and
    two table names, and that is all it spells. (SPEC §8 has since been corrected
    to describe the five per-level columns that were actually built; the ticket
    text this fixture was written against is quoted as written.) So the role column, the person
    link and the parent edge are each found here by following a foreign key or by
    a candidate list at the top of this file, and a role's spelling is matched
    against whatever the column enumerates rather than asserted to be a
    particular string.

    **The one thing it cannot find on its own is what a scope node is.** SPEC
    §2.1's containment hierarchy is six separate tables — E0-05 built them that
    way — and there is no single `org_node` table for a `scope_node_id` to
    reference, so "an assignment is scoped to a department" has several
    reasonable schema shapes. Three are supported here:

      - **per-kind foreign keys** — one nullable reference per containment level,
        with the role grain rule expressed as a `CHECK` over which one is
        populated;
      - **a kind column beside the id** — `scope_node_kind` plus an untyped
        `scope_node_id`, which is what the singular name in the ticket suggests;
      - **the id alone**, with the kind implied by the role. Supported because it
        is the reading the singular name suggests most directly, and because
        failing here would stop every test in the suite inside its fixture — but
        it is a shape with nothing for the role grain rule to be enforced by, so
        the role grain tests go red against it. That is criterion 6 reporting
        itself, not this fixture objecting to a design.

    A schema that introduces a unified node table is a fourth shape and a good
    answer, and this fixture cannot seed a node in it without knowing how a node
    of a given kind is spelled there. That failure names itself.

    **Nothing here asserts anything.** Every method either returns a row or fails
    with a message saying which part of the ticket it could not express; the
    assertions live in the test modules, so that a red test and a broken fixture
    are never reported as the same thing.
    """

    def __init__(self, session: Any, tables: dict[str, Any]) -> None:
        self.session = session
        self.tables = tables
        self._chain: dict[str, Any] = {}

    # -- reaching the tables and the columns the ticket names ---------------

    @property
    def assignments(self) -> Any:
        return require_table(self.tables, ROLE_ASSIGNMENT_TABLE)

    @property
    def mappings(self) -> Any:
        return require_table(self.tables, LEAD_FACULTY_MAPPING_TABLE)

    @property
    def assignment_key(self) -> str:
        return single_primary_key(self.assignments)

    @property
    def role_column(self) -> str:
        return require_column(self.assignments, ROLE_COLUMN_CANDIDATES)

    @property
    def person_column(self) -> str:
        """The column carrying `person_id`, found by following the key.

        Found rather than named because the criterion this serves is about where
        the key *points*: SPEC §2.1 computes purview from the Pulse-owned people
        graph, and an assignment keyed to `user` cannot describe a dean who has
        never launched the tool (ADR 0024).
        """
        found = foreign_key_columns(self.assignments, "person")
        if len(found) == 1:
            return found[0]
        referenced = sorted({key.column.table.name for key in self.assignments.foreign_keys})
        pytest.fail(
            f"`{ROLE_ASSIGNMENT_TABLE}` has {len(found)} foreign keys to `person` ({found}); it "
            f"references {referenced}. E0-09 and SPEC §8 both give an assignment a `person_id`, "
            "and every fixture here needs to know which person holds an assignment."
        )

    @property
    def reports_to_column(self) -> str:
        """The parent edge, preferring the column whose key is self-referential.

        The preference is the point. A `reports_to` that references `person` or an
        org table is the defect criterion 1 exists to stop, and looking for the
        self-reference first means the fixture keeps working while the criterion
        test reports it — rather than every test in the module failing at once
        with a message about a column name.
        """
        self_referential = foreign_key_columns(self.assignments, ROLE_ASSIGNMENT_TABLE)
        if len(self_referential) == 1:
            return self_referential[0]
        if len(self_referential) > 1:
            pytest.fail(
                f"`{ROLE_ASSIGNMENT_TABLE}` references itself from more than one column "
                f"({self_referential}), so there is no single answer to which one is the "
                "supervision edge."
            )
        return require_column(self.assignments, REPORTS_TO_CANDIDATES)

    # -- roles --------------------------------------------------------------

    def role_value(self, token: str) -> Any:
        """The value the `role` column uses for `token`.

        Read off the column's own enumeration where there is one, so the enum's
        spelling stays the implementer's decision. A plain string column gets the
        first alias, which is the spelling SPEC §2.1 uses.
        """
        aliases = ROLE_ALIASES[token]
        values = list(getattr(stored_type(self.assignments.c[self.role_column]), "enums", ()) or ())
        if not values:
            return aliases[0]
        for alias in aliases:
            for value in values:
                if value.upper() == alias:
                    return value
        pytest.fail(
            f"The `{self.role_column}` column enumerates {values}, none of which is any of "
            f"{list(aliases)}. SPEC §2.1's canonical chain spells INSTRUCTOR, LEAD_FACULTY, "
            "CHAIR, DEAN and VP_ACADEMICS, and E0-09 spells CARE; if this role is genuinely "
            "spelled some other way, add it to `ROLE_ALIASES` in tests/conftest.py."
        )

    # -- scope nodes --------------------------------------------------------

    def scope_shape(self) -> tuple[str, Any]:
        """How this schema says which node an assignment is scoped to."""
        per_kind = {}
        for kind in CONTAINMENT_ORDER:
            columns = foreign_key_columns(self.assignments, kind)
            if len(columns) == 1:
                per_kind[kind] = columns[0]
        if len(per_kind) >= 2:
            return "per_kind", per_kind

        columns = self.assignments.c
        kind_column = next((name for name in SCOPE_KIND_CANDIDATES if name in columns), None)
        id_column = next((name for name in SCOPE_ID_CANDIDATES if name in columns), None)
        if kind_column is not None and id_column is not None:
            elsewhere = sorted(
                {
                    key.column.table.name
                    for key in columns[id_column].foreign_keys
                    if key.column.table.name not in CONTAINMENT_ORDER
                }
            )
            if elsewhere:
                pytest.fail(
                    f"`{ROLE_ASSIGNMENT_TABLE}.{id_column}` references {elsewhere}, which is not "
                    "one of SPEC §2.1's containment tables. That reads as a unified node table, "
                    "which is a good answer to what a singular `scope_node_id` points at and is "
                    "the one shape this fixture cannot build a node in: it would have to know how "
                    f"a node of a given kind is spelled in {elsewhere}. Say so in the pull "
                    "request and teach `scope_overrides` in tests/conftest.py how to seed one."
                )
            return "kind_and_id", (kind_column, id_column)

        if id_column is not None:
            # An id and nothing else: the kind is implied by the role. Handled
            # rather than refused, because it is the shape the singular
            # `scope_node_id` most naturally suggests, and because refusing it
            # here would stop every test in the suite inside its fixture. What it
            # cannot do is *enforce* the role grain — there is nothing for a
            # foreign key or a check to compare against — so the role grain tests
            # go red against it, which is criterion 6 reporting itself rather than
            # this fixture reporting a shape it dislikes.
            return "id_only", id_column

        pytest.fail(
            f"This fixture cannot tell how `{ROLE_ASSIGNMENT_TABLE}` records the node an "
            f"assignment is scoped to. Its columns are "
            f"{[column.name for column in self.assignments.columns]}, and it references "
            f"{sorted({key.column.table.name for key in self.assignments.foreign_keys})}. E0-09 "
            "wrote `scope_node_id` in the singular — SPEC §8 did too until it was corrected on "
            "2026-08-18 to describe the five per-level columns — but E0-05 built the "
            "containment hierarchy as six separate tables and no ticket says what a single "
            "`scope_node_id` points at. Three shapes are supported — one nullable foreign key per "
            "containment level, a kind column beside an untyped id, or the id alone with the kind "
            "implied by the role — and a fourth (a unified node table) needs this fixture to be "
            "told how a node of a given kind is spelled there. That is a question for the ticket, "
            "not something to guess at here."
        )

    def scope_kind_value(self, kind: str) -> Any:
        """How the kind column spells `kind`, read off its enumeration where there is one."""
        shape, detail = self.scope_shape()
        if shape != "kind_and_id":
            return kind
        kind_column = detail[0]
        values = list(getattr(stored_type(self.assignments.c[kind_column]), "enums", ()) or ())
        if not values:
            return kind
        for value in values:
            if value.upper() == kind.upper():
                return value
        pytest.fail(
            f"`{kind_column}` enumerates {values}, none of which is {kind!r}. The six containment "
            f"levels are {list(CONTAINMENT_ORDER)} (SPEC §2.1), and a scope kind that cannot name "
            "one of them cannot express the role grain rule."
        )

    def can_express(self, kind: str) -> bool:
        """Can this schema even say "scoped to a node of this kind"?

        It answers no only under the per-kind shape, when there is no column for
        that level — a schema with `department_id` and no `prefix_id` cannot
        record a chair scoped to a prefix at all. That is the *strongest* form of
        the role grain rule rather than a gap in it, so the tests that expect a
        wrong pairing to be refused ask this first and count unrepresentable as
        refused. They say so in their message; nothing here decides it silently.
        """
        shape, detail = self.scope_shape()
        return kind in detail if shape == "per_kind" else True

    def scope_overrides(self, kind: str, key: Any) -> dict[str, Any]:
        """The column values that say "scoped to this node of this kind"."""
        shape, detail = self.scope_shape()
        if shape == "per_kind":
            if kind not in detail:
                pytest.fail(
                    f"`{ROLE_ASSIGNMENT_TABLE}` carries a scope reference for {sorted(detail)} and "
                    f"none for `{kind}`, so an assignment scoped to a {kind} is unwritable. E0-09's "
                    "role grain rule is about refusing the wrong kind, not about being unable to "
                    "spell it — a schema where the wrong scope cannot be expressed at all makes "
                    "the criterion untestable rather than satisfied."
                )
            return {detail[kind]: key}
        if shape == "id_only":
            return {detail: key}
        kind_column, id_column = detail
        return {kind_column: self.scope_kind_value(kind), id_column: key}

    def scope(self, kind: str) -> Any:
        """The key of the shared node of `kind`, seeding the containment chain once.

        Shared on purpose: `scope("section")` and `scope("course")` answer for a
        section and the course that holds it, so a fixture built out of these
        calls is one coherent hierarchy rather than six unrelated rows.
        """
        table = require_table(self.tables, kind)
        if kind not in self._chain:
            seed_row(self.session, self.tables, kind, self._chain)
        return self._chain[kind][single_primary_key(table)]

    def new_branch(self, *keep: str) -> dict[str, Any]:
        """A fresh chain sharing only the named ancestors with the shared one."""
        return {name: row for name, row in self._chain.items() if name in keep}

    def fresh_scope(self, kind: str) -> Any:
        """A second node of `kind` under the same ancestors as the shared one.

        This is what makes a sibling: two departments in one college, two courses
        under one prefix. Everything strictly above `kind` in SPEC §2.1's
        containment order is kept, everything at or below it is built again.
        `term` is always kept, since a second section in a second term would be
        a different comparison entirely.

        **An institution is never duplicated**, and that is a deliberate refusal
        rather than an omission: whether a deployment holds one institution or
        many is an open spec question ([E0-22](../docs/tickets/e0/E0-22-spec-questions-from-e0-05.md)),
        so a fixture that wrote a second one would answer it, and every test
        built on this would fail inside its own seeding the day the answer is
        "one". Institution-scoped roles therefore share the one node.
        """
        if kind not in CONTAINMENT_ORDER:
            pytest.fail(f"{kind!r} is not one of SPEC §2.1's containment levels.")
        if kind == "institution":
            return self.scope(kind)
        keep = (*CONTAINMENT_ORDER[: CONTAINMENT_ORDER.index(kind)], "term")
        branch = self.new_branch(*keep)
        row = seed_row(self.session, self.tables, kind, branch)
        return row[single_primary_key(require_table(self.tables, kind))]

    def key_of(self, table_name: str, row: Any) -> Any:
        """The primary key value of a row from `table_name`."""
        return row[single_primary_key(require_table(self.tables, table_name))]

    # -- people and assignments ---------------------------------------------

    def person(self) -> Any:
        """One new `person` row, with no user linked (ADR 0024: the link is nullable)."""
        row = seed_row(self.session, self.tables, "person", {})
        return self.key_of("person", row)

    def assign(
        self,
        role: str,
        *,
        scope_kind: str | None = None,
        scope: Any = None,
        person: Any = None,
        reports_to: Any = UNSET,
        **overrides: Any,
    ) -> Any:
        """One `role_assignment` row, returned as the inserted mapping.

        `scope_kind` defaults to the kind SPEC §2.1 gives the role, so a test that
        wants a *wrong* kind has to say so — which keeps the role grain criterion
        an assertion rather than a default. `reports_to` is left out of the insert
        entirely unless it is passed, so a schema that defaults it is not
        overridden, and passing `None` writes an explicit null.
        """
        kind = scope_kind or ROLE_SCOPE_GRAIN[role]
        key = self.scope(kind) if scope is None else scope
        values: dict[str, Any] = {
            self.role_column: self.role_value(role),
            self.person_column: self.person() if person is None else person,
            **self.scope_overrides(kind, key),
        }
        if reports_to is not UNSET:
            values[self.reports_to_column] = reports_to
        values.update(overrides)
        return seed_row(
            self.session, self.tables, ROLE_ASSIGNMENT_TABLE, dict(self._chain), **values
        )

    def node(self, role: str, *, reports_to: Any = UNSET) -> Any:
        """An assignment sharing nothing with any other: its own person, its own scope node.

        Used where a test is about the *graph* and not about the rows — the
        generated-graph properties, and the long legal chains. Sharing nothing
        means no uniqueness rule this ticket does not mention (one chair per
        department, one instructor per section) can refuse a row and be read as
        the cycle guard firing.
        """
        return self.assign(
            role,
            scope=self.fresh_scope(ROLE_SCOPE_GRAIN[role]),
            person=self.person(),
            reports_to=reports_to,
        )

    def repoint(self, row: Any, parent: Any) -> None:
        """Point an existing assignment's `reports_to` at `parent` (or at `None`)."""
        table = self.assignments
        key = self.assignment_key
        self.session.execute(
            table.update()
            .where(table.c[key] == row[key])
            .values(**{self.reports_to_column: parent})
        )

    def parent_of(self, assignment_id: Any) -> Any:
        """The stored `reports_to` of one assignment, read back out of the database."""
        from sqlalchemy import select

        table = self.assignments
        return self.session.execute(
            select(table.c[self.reports_to_column]).where(
                table.c[self.assignment_key] == assignment_id
            )
        ).scalar_one()

    def assignments_of(self, person_id: Any) -> list[Any]:
        """Every assignment id one person holds, read back out of the database.

        Read back rather than collected as the rows are written, because the
        question a two-hat test asks is whether the schema kept two rows — and a
        list built in Python holds two either way.
        """
        from sqlalchemy import select

        table = self.assignments
        return list(
            self.session.execute(
                select(table.c[self.assignment_key]).where(table.c[self.person_column] == person_id)
            ).scalars()
        )

    def ancestors(self, assignment_id: Any, limit: int = 64) -> list[Any]:
        """Every assignment reachable by walking `reports_to` upwards, nearest first.

        Bounded, so that a schema which accepted a cycle produces a failed
        assertion in the test that asked rather than a hang in the fixture.
        """
        found: list[Any] = []
        current = self.parent_of(assignment_id)
        while current is not None and len(found) < limit:
            found.append(current)
            current = self.parent_of(current)
        return found

    def lead_mapping(self, *, person: Any = None, course: Any = None) -> Any:
        """One `lead_faculty_mapping` row, both links found by following keys."""
        table = self.mappings
        person_columns = foreign_key_columns(table, "person")
        course_columns = foreign_key_columns(table, "course")
        if len(person_columns) != 1 or len(course_columns) != 1:
            pytest.fail(
                f"`{LEAD_FACULTY_MAPPING_TABLE}` has {person_columns} referencing `person` and "
                f"{course_columns} referencing `course`. E0-09: it 'maps a person to courses they "
                "lead, one lead per course'; SPEC §2.1 calls it 'a mapping of individuals to the "
                "courses they lead'. One of each is what that sentence describes."
            )
        values = {
            person_columns[0]: self.person() if person is None else person,
            course_columns[0]: self.scope("course") if course is None else course,
        }
        return seed_row(
            self.session, self.tables, LEAD_FACULTY_MAPPING_TABLE, dict(self._chain), **values
        )

    # -- attempting a write, and finding out whether it was refused ---------

    def refusal(self, action: Any) -> Any:
        """Run `action`; answer the database error it provoked, or `None`.

        Two things this does that a bare `pytest.raises` does not.

        **It forces any deferred check.** A cycle guard written as a deferrable
        constraint trigger — which is the shape that survives a transaction
        reorganising a subtree — does not fire until commit, and nothing in this
        suite commits. `SET CONSTRAINTS ALL IMMEDIATE` makes the deferred and the
        immediate designs answer at the same moment, so this fixture does not
        quietly decide which one the implementer must pick.

        **It keeps the rows when the write succeeds.** Every control row a test
        writes before the row that must be refused goes in through the same path,
        so a refusal is known to be about the row under test rather than about the
        insert path not working (`docs/MISTAKES.md` entry 3).
        """
        from sqlalchemy import text
        from sqlalchemy.exc import DatabaseError

        savepoint = self.session.begin_nested()
        try:
            action()
            self.session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        except DatabaseError as refused:
            savepoint.rollback()
            return refused
        savepoint.commit()
        return None

    # -- the two shapes the ticket asks to be constructible ------------------

    def assistant_dean_shape(self) -> dict[str, Any]:
        """SPEC §2.1's worked example, as rows.

        "Own led courses  union  every supervised chair's department — a set no single
        containment node holds." So the assistant dean's own led course sits in a
        *third* department, whose chair reports straight to the dean: without
        that, the college node would hold the whole purview and the example would
        not be the example.

        The assistant dean is scoped to the college, the same node as the dean
        (§2.1: "authority comes from the supervision graph, not the scope").
        Computing the purview over this shape is E9's; constructing it is E0-09's
        last criterion.
        """
        college = self.scope("college")
        supervised_department = self.scope("department")

        second = self.new_branch("institution", "college", "term")
        seed_row(self.session, self.tables, "course", second)
        third = self.new_branch("institution", "college", "term")
        led_course_row = seed_row(self.session, self.tables, "course", third)

        assistant_dean_person = self.person()
        dean = self.assign("DEAN", scope=college)
        assistant_dean = self.assign(
            "ASSISTANT_DEAN",
            scope=college,
            person=assistant_dean_person,
            reports_to=dean[self.assignment_key],
        )
        supervised_chairs = [
            self.assign(
                "CHAIR",
                scope=supervised_department,
                reports_to=assistant_dean[self.assignment_key],
            ),
            self.assign(
                "CHAIR",
                scope=self.key_of("department", second["department"]),
                reports_to=assistant_dean[self.assignment_key],
            ),
        ]
        unsupervised_chair = self.assign(
            "CHAIR",
            scope=self.key_of("department", third["department"]),
            reports_to=dean[self.assignment_key],
        )
        led_course = self.key_of("course", led_course_row)
        lead = self.assign(
            "LEAD_FACULTY",
            scope=led_course,
            person=assistant_dean_person,
            reports_to=unsupervised_chair[self.assignment_key],
        )
        self.lead_mapping(person=assistant_dean_person, course=led_course)

        return {
            "college": college,
            "dean": dean,
            "assistant_dean": assistant_dean,
            "assistant_dean_person": assistant_dean_person,
            "supervised_chairs": supervised_chairs,
            "supervised_departments": [
                supervised_department,
                self.key_of("department", second["department"]),
            ],
            "unsupervised_chair": unsupervised_chair,
            "unsupervised_department": self.key_of("department", third["department"]),
            "lead": lead,
            "led_course": led_course,
        }

    def care_and_instructor_person(self) -> dict[str, Any]:
        """E0-09 criterion 9's fixture: one person, a Care hat and a teaching hat.

        Named by the ticket as reused by E0-10 and E0-18, which is why it is here
        rather than in a test module. The instructor assignment carries a
        `reports_to` and the Care assignment does not — §2.1 puts Care outside the
        supervision graph entirely — so the row shape says the thing the ticket
        says: it is capabilities that do not compose, not people.
        """
        person = self.person()
        lead = self.assign("LEAD_FACULTY", scope=self.scope("course"))
        instructor = self.assign(
            "INSTRUCTOR",
            scope=self.scope("section"),
            person=person,
            reports_to=lead[self.assignment_key],
        )
        care = self.assign("CARE", scope=self.scope("institution"), person=person, reports_to=None)
        return {"person": person, "care": care, "instructor": instructor, "lead": lead}


@pytest.fixture(scope="session")
def metadata_tables(migrated_database: DatabaseUnderTest) -> dict[str, Any]:
    """`Base.metadata`, with every model module registered on it.

    Reached through `app.models` and not through the module a ticket names, for
    the reason `tests/unit/test_identity_models_registered.py` gives at length:
    `migrations/env.py` imports the package, and a module nobody imported is on
    no metadata. `Base` comes from `app.models.base` rather than from `app.db`,
    which builds an engine out of `Settings()` at import.

    Declared rather than reflected, because writes go through it: a column
    protected by a `TypeDecorator` is bypassed by a write through a reflected
    table. `migrated_database` is depended on and not used — it is what
    guarantees the migration has run before anything inserts.
    """
    try:
        importlib.import_module("app.models")
        base_module = importlib.import_module("app.models.base")
    except ImportError as failure:
        pytest.fail(
            f"Importing the model package raised {failure!r}. E0-04 ships `app/models/base.py` "
            "with the declarative base, and every model module imports `Base` from it."
        )
    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    if metadata is None:
        pytest.fail(
            "`app.models.base` exposes no `Base` with `metadata`, so there is nothing to insert "
            "through — and nothing for `migrations/env.py` to autogenerate against either."
        )
    return dict(metadata.tables)


@pytest.fixture
def seed_rows(db_session: Any, metadata_tables: dict[str, Any]) -> Callable[..., Any]:
    """`seed_row` bound to the session whose writes are rolled back after the test.

    E0-10 is what needs it. Every assertion about its Care reveal is about a
    **particular** identity — that the function returned the name that was seeded,
    not that it returned something — and over an unseeded database each of them is
    satisfied by a function that reveals nobody (`docs/MISTAKES.md` entry 3).
    `SupervisionGraph` seeds the containment chain and assignments and nothing
    else, so the choice was a fifth private copy of the seeding helper or this;
    entry 13 says one helper, reached from both places.

    The integer counters are restarted for the same reason `supervision_graph`
    restarts them: a course number is drawn from a 700-wide band, and a counter
    that climbed across the session would eventually fail somebody else's test
    inside its own seeding.
    """
    _GRAPH_INTEGER_COUNTERS.clear()

    def seed(name: str, chain: dict[str, Any] | None = None, **overrides: Any) -> Any:
        return seed_row(db_session, metadata_tables, name, chain, **overrides)

    return seed


@pytest.fixture
def supervision_graph(db_session: Any, metadata_tables: dict[str, Any]) -> SupervisionGraph:
    """E0-09's graph builder, on a session whose writes are rolled back after the test.

    The integer counters are restarted per test, and two things now depend on it.
    An ordinal the seeding helper invents has to land inside an 18-week term
    rather than at 47; and `graph_course_number` draws from the same dict, so the
    restart is what keeps its 700 numbers a per-test budget rather than a
    session-wide one. Without the restart both climb across the session and
    eventually fail a later test inside its own seeding, for a reason that test is
    not about.
    """
    _GRAPH_INTEGER_COUNTERS.clear()
    return SupervisionGraph(db_session, metadata_tables)


@pytest.fixture
def supervision_graph_on(
    metadata_tables: dict[str, Any],
) -> Callable[[Any], SupervisionGraph]:
    """The same builder, on a session the caller opened, for a database that is not at head.

    `supervision_graph` above and `committed_rows` below both bind the builder to
    the session database, which `migrated_database` has already taken to head.
    E0-11 needs the same rows in a database standing at an **earlier** revision —
    the state a deployment is in at the moment a new rule arrives — and that is
    `empty_database`'s, on a connection the test opens and closes around each
    migration step. The choice was a fifth private copy of the builder or this
    (`docs/MISTAKES.md` entry 13), and the copy is the one nobody updates.

    The counters are cleared once per test rather than once per call, because a
    test that opens three sessions against one database is still one test's budget
    of course numbers — clearing per call would hand out `100` twice under the
    same prefix and fail E0-05's uniqueness rule inside the fixture.
    """
    _GRAPH_INTEGER_COUNTERS.clear()

    def build(session: Any) -> SupervisionGraph:
        return SupervisionGraph(session, metadata_tables)

    return build


# ---------------------------------------------------------------------------
# E0-10 — rows a *second connection* can see, and the environment that points
# `app.services.safety` at this container.
# ---------------------------------------------------------------------------


class CommittedRows:
    """Seeding for a service that opens its own connection, undone when the test ends.

    Every other database fixture here writes inside `db_session`'s transaction and
    rolls it back, which is the right default and is useless for one case: a
    service that connects for itself sees none of it. `app.services.safety` is
    that case — `CARE_DATABASE_URL` is a second connection by design (ADR 0001:
    "the connection pool is bound to the service module"), so a test that calls
    `reveal_identity` has to hand it committed rows or it is testing a reveal of
    nothing.

    So this commits, and the fixture below removes afterwards **whatever appeared**
    rather than whatever it wrote. That difference is not tidiness: the service's
    own audit row is written on its connection, inside its transaction, and no
    amount of bookkeeping on this side would know its key. A snapshot of every
    single-key table before and after does.
    """

    def __init__(self, session: Any, tables: dict[str, Any]) -> None:
        self.session = session
        self.tables = tables
        self.graph = SupervisionGraph(session, tables)

    def seed(self, name: str, chain: dict[str, Any] | None = None, **overrides: Any) -> Any:
        """One row of `name`, with its ancestors. Not visible elsewhere until `commit`."""
        return seed_row(self.session, self.tables, name, chain, **overrides)

    def commit(self) -> None:
        """Make everything seeded so far visible to every other connection."""
        self.session.commit()


def keyed_tables(tables: dict[str, Any]) -> list[Any]:
    """Every declared table with exactly one primary key column, parents first.

    Sorted by dependency so the caller can delete in reverse and never orphan a
    row. `MetaData.sorted_tables` is what does the sorting — the metadata is
    reached through any one table rather than passed in, because every table here
    comes from the same `Base.metadata`. A self-referential table —
    `role_assignment` — is safe inside one statement: Postgres queues
    referential-integrity checks as after-row triggers and fires them at the end
    of the statement, so a parent and its child leave together.
    """
    if not tables:
        return []
    ordered = next(iter(tables.values())).metadata.sorted_tables
    return [table for table in ordered if len(list(table.primary_key.columns)) == 1]


def row_keys(connection: Any, tables: list[Any]) -> dict[str, set[Any]]:
    """The primary key of every row in each of `tables`, right now."""
    from sqlalchemy import select

    found: dict[str, set[Any]] = {}
    for table in tables:
        key = next(iter(table.primary_key.columns))
        found[table.name] = {row[0] for row in connection.execute(select(key))}
    return found


def delete_rows_added_since(engine: Any, tables: list[Any], before: dict[str, set[Any]]) -> None:
    """Remove every row that appeared since `before` was taken, children first."""
    from sqlalchemy import delete, select

    with engine.begin() as connection:
        for table in reversed(tables):
            key = next(iter(table.primary_key.columns))
            present = {row[0] for row in connection.execute(select(key))}
            added = present - before.get(table.name, set())
            if added:
                connection.execute(delete(table).where(key.in_(list(added))))


@pytest.fixture
def committed_rows(
    migrated_engine: Any, metadata_tables: dict[str, Any]
) -> Iterator[CommittedRows]:
    """`CommittedRows` on the migrated database, with the database left as it was found.

    The teardown is a diff rather than a rollback, so it also removes what the
    *service under test* wrote — which for E0-10 is the audit row every reveal
    leaves, on a connection this fixture never sees. A test that leaks a row here
    would fail somebody else's non-vacuity guard three tickets from now, which is
    the expensive kind of flake.
    """
    from sqlalchemy.orm import Session

    _GRAPH_INTEGER_COUNTERS.clear()
    tables = keyed_tables(metadata_tables)
    with migrated_engine.connect() as probe:
        before = row_keys(probe, tables)

    connection = migrated_engine.connect()
    session = Session(bind=connection)
    try:
        yield CommittedRows(session, metadata_tables)
    finally:
        session.close()
        connection.close()
        delete_rows_added_since(migrated_engine, tables, before)


@pytest.fixture
def care_service_environment(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
    migrated_database: DatabaseUnderTest,
) -> dict[str, str]:
    """Point an `app.*` import at this container, as the application and as Care.

    `configured_env` first, so every documented variable has a value and
    `Settings()` constructs; then the database variables are overwritten with the
    container's, because `.env.example`'s placeholders name the Compose service
    `db` and resolve to nothing here.

    `migrated_database` rather than `provisioned_database`: the Care role can log
    in from the moment the fixture creates it, and it can *do* nothing until the
    E0-10 migration grants it, so a service test against an unmigrated database
    would be measuring the wrong refusal.
    """
    values = application_environment(migrated_database)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


# ---------------------------------------------------------------------------
# E0-11 — the authorization chokepoint, and the connection it has to work over.
# ---------------------------------------------------------------------------

# SPEC §13 puts the chokepoint here and E0-11's scope repeats the path:
# "`backend/app/services/authz.py` with the interface every caller uses".
AUTHZ_MODULE = "app.services.authz"


class AuthzModule:
    """E0-11's chokepoint, reached by name, with a clear failure when it is absent.

    **Nothing here is discovered, which is what makes it unlike
    `SectionCodeService` above.** E0-07 named a file and none of its callables, so
    that fixture hunts for them by name fragment. E0-11's surface was settled in
    the ticket before any code was written — `AuthzError`,
    `CareIsNotComposableError`, `OutOfPurviewError`, `LmsOwnedWriteRefused`,
    `Purview`, `ActorScope`, `LMS_OWNED_TABLES`, `own_grant`, `resolve_scope`,
    `holds_care`, `transitive_purview`, `guard_write`, `raw_comments_permitted`
    and `scoped_reader` — so a lookup here transcribes that contract rather than
    guessing at one, and a name this cannot find is a deliverable that is not
    there yet.

    **Its whole job is to keep that a failed assertion rather than a collection
    error.** `from app.services.authz import own_grant` at the top of a test
    module makes every test in the file uncollectable while the module is absent,
    and an uncollected test is not a red test: it reports as a broken suite rather
    than as a criterion nobody has met, and the two are fixed by different people.
    `import_app_module` above draws the same distinction for the same reason, and
    like it, a `ModuleNotFoundError` for some *other* module is re-raised
    untouched — a chokepoint that exists and imports something absent and one that
    was never written need different fixes.
    """

    def __init__(self) -> None:
        self._module: ModuleType | None = None

    @property
    def module(self) -> ModuleType:
        """`app.services.authz`, or a failure naming the missing file."""
        if self._module is None:
            try:
                self._module = importlib.import_module(AUTHZ_MODULE)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is None or not (
                    absent == AUTHZ_MODULE or AUTHZ_MODULE.startswith(f"{absent}.")
                ):
                    raise
                pytest.fail(
                    f"There is no `{AUTHZ_MODULE}` module. E0-11's scope puts the authorization "
                    "chokepoint in `backend/app/services/authz.py`: 'the single chokepoint every "
                    "entry point passes through — HTTP, Celery jobs, and the future MCP server' "
                    "(SPEC §13, and `CLAUDE.md`)."
                )
        return self._module

    def symbol(self, name: str) -> Any:
        """One name off the module's agreed surface, or a failure saying it is missing."""
        found = getattr(self.module, name, None)
        if found is None:
            defined = sorted(
                attribute for attribute in vars(self.module) if not attribute.startswith("_")
            )
            pytest.fail(
                f"`{AUTHZ_MODULE}` defines no `{name}` — it defines {defined}. That name is part "
                "of the interface E0-11 settled before any of it was written, so this is a "
                "missing deliverable rather than a rename to accommodate here. If it genuinely "
                "moved, say so in the pull request; `AuthzModule` in tests/conftest.py is the one "
                "place that changes."
            )
        return found

    def __getattr__(self, name: str) -> Any:
        """`authz.own_grant` and `authz.symbol("own_grant")` are the same lookup.

        Only reached for attributes this class does not define itself, so `module`
        and `symbol` above keep their meanings and everything else falls through
        to the contract.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return self.symbol(name)


@pytest.fixture
def authz(configured_env: dict[str, str]) -> AuthzModule:
    """E0-11's chokepoint. See `AuthzModule` above for what it will and will not do.

    `configured_env` runs first so that every documented variable has a value
    before the import: `resolve_scope` reads the n-threshold from `Settings`
    (§4), and a module that builds one at import time would otherwise fail on
    whichever variable the machine running the suite happens not to have.
    """
    return AuthzModule()


@pytest.fixture
def application_session(
    migrated_database: DatabaseUnderTest, application_engine: Any
) -> Iterator[Any]:
    """A session on the connection the application actually serves requests over.

    `db_session` above connects as the bootstrap superuser, which is right for a
    fixture that has to seed rows and wrong for anything that asks what a read
    path can reach: a superuser passes every grant. From E0-10 on, `pulse_app`
    holds `SELECT` on the read views and on nothing else, so "the resolver read
    the assignment" is a claim about a grant, and it is only true over this
    session.

    Nothing seeded inside `db_session` is visible here — this is a second
    connection, and that transaction has not committed. Pair it with
    `committed_rows`, which is the fixture for exactly that.

    `migrated_database` is depended on and not used: `application_engine` is built
    from `provisioned_database`, which is the state *before* any migration, so
    without this a test could open this session against a database holding no
    views and no grants and read the absence as a refusal.
    """
    from sqlalchemy.orm import Session

    connection = application_engine.connect()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        connection.close()


# ---------------------------------------------------------------------------
# E0-16 — the mock OIDC identity provider, driven the way a client drives one.
# ---------------------------------------------------------------------------

# SPEC §13's layout again, and §7.2's service list: `mock-idp/` holding a
# `Dockerfile` and an `app/`, run as the Compose service `mock-idp`.
MOCK_IDP_DIR = REPO_ROOT / "mock-idp"
MOCK_IDP_SERVICE = "mock-idp"

# Where the ASGI application might sit inside that package, most likely first —
# the same list as the platform's with the platform-shaped names swapped for
# provider-shaped ones. Nothing in E0-16 spells a module, so it is discovered.
MOCK_IDP_MODULES = ("app.main", "app", "app.provider", "app.idp", "app.server", "app.api")

# Where the provider's settings object might sit, and what it might be called.
# `mock-lms/app/config.py` holds `PlatformSettings`, so a provider written beside
# it probably mirrors that; the rest are here so a different arrangement is found
# rather than reported as a missing deliverable. The *factory* name is the review's
# — `ProviderSettings.from_environment` is the callable whose redirect-URI
# validation has no HTTP surface to be reached through, which is why it is
# imported at all.
MOCK_IDP_SETTINGS_MODULES = ("app.config", "app.settings", "app.main", "app")
PROVIDER_SETTINGS_NAMES = ("ProviderSettings", "IdpSettings", "OidcSettings", "Settings")
SETTINGS_FACTORY_NAME = "from_environment"

# **Not this suite's choice.** OpenID Connect Discovery 1.0 §4 fixes this path,
# and E0-16's scope spells it out: "Discovery document at
# `/.well-known/openid-configuration`". A provider serving its metadata anywhere
# else is one no conformant client can configure itself from.
DISCOVERY_PATH = "/.well-known/openid-configuration"

# How many of the identities a login form offers are walked. **This suite's
# choice**, and a bound rather than a rule: E0-16 seeds six roles plus the
# two-hat person, so a form offering more than this is a seed that has grown
# rather than a form this cannot read. Raise it if that happens.
MAX_LOGIN_VARIANTS = 24

# How many internal redirects are followed between the authorization request and
# the page that asks who is signing in. **This suite's choice.** A provider may
# reasonably send `/authorize` to `/login?...` and back; a provider that sends a
# client round more hops than this is looping.
MAX_LOGIN_HOPS = 4

# Input types that are a person typing something this test cannot know. A login
# form built out of these is drivable by a browser and not by a fixture, and the
# right answer is a named failure rather than a guess at a seeded password.
TYPED_INPUT_TYPES = frozenset({"text", "password", "email", "tel", "url", "number", "search"})

# Words that name the field a login form picks a person with, consulted only when
# the form offers more than one set of choices and the ambiguity has to be
# resolved. Read by `MockIdentityProvider.identity_field` below.
IDENTITY_FIELD_HINTS = ("user", "login", "identity", "account", "sub", "person", "email", "name")

# The claims that carry a *person* rather than a *role*, from OIDC Core 1.0 §2
# and §5.1, plus the registered JWT claims. Values under these keys are skipped
# when scanning a session for roles, because a dean called "Dean" is a name and
# not a grant — and a scanner that could not tell the two apart would report a
# reporting role on the Care session that §2 exists to keep clear of one.
PERSONAL_CLAIM_NAMES = frozenset(
    {
        "address",
        "at_hash",
        "aud",
        "azp",
        "birthdate",
        "c_hash",
        "email",
        "email_verified",
        "family_name",
        "gender",
        "given_name",
        "iss",
        "jti",
        "locale",
        "middle_name",
        "name",
        "nickname",
        "nonce",
        "phone_number",
        "phone_number_verified",
        "picture",
        "preferred_username",
        "profile",
        "sub",
        "updated_at",
        "website",
        "zoneinfo",
    }
)

# How a role may be spelled in a session, built from E0-09's `ROLE_ALIASES`
# rather than beside it, so that "how this project spells LEAD_FACULTY" stays one
# fact (`docs/MISTAKES.md` entry 13). Two additions, both for this door only: a
# provider standing in for an institutional IdP may spell the two launch-only
# roles in the LIS vocabulary a platform uses, where a student is a `Learner`.
# They are added rather than pushed back into `ROLE_ALIASES` because that mapping
# is matched against database enum labels, which have no `Learner`.
ROLE_CLAIM_ALIASES = {
    **ROLE_ALIASES,
    "INSTRUCTOR": ("INSTRUCTOR", "TEACHER"),
    "STUDENT": ("STUDENT", "LEARNER"),
}

# Which roles a door may hand out is a ticket's expectation rather than a
# property of the driver, so the three lists E0-16's criteria are written in —
# the six web-login roles, the two launch-only ones, and §2.1's reporting chain —
# live in `tests/integration/test_mock_idp_web_login.py` beside the assertions
# that read them, and are transcribed there from the ticket.

# Fragments that would make a claim name a *purview* — a set of org nodes, or a
# supervision edge — rather than an identity. §2.1's containment levels, plus the
# two words the graph is described in. `scope` on its own is deliberately absent:
# it is an OAuth 2.0 term with a legitimate meaning in a token response, and
# matching it would fail a conformant provider for saying `openid`.
PURVIEW_CLAIM_FRAGMENTS = (
    "purview",
    "college",
    "department",
    "prefix",
    "course",
    "section",
    "scope_node",
    "reports_to",
    "supervis",
)


def pkce_pair() -> tuple[str, str]:
    """One PKCE verifier and its S256 challenge, per RFC 7636 §4.1 and §4.2.

    `secrets.token_urlsafe(48)` produces 64 characters from the unreserved set,
    inside the 43-to-128 the specification allows. The challenge is the
    base64url of the SHA-256 of the *ASCII* verifier with the padding stripped,
    which is the whole of what a provider recomputes.
    """
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def role_token(value: str) -> str:
    """One string from a session, normalised to the shape a role name has.

    A role arrives as a bare word (`chair`), as a phrase (`VP Academics`), or as
    a vocabulary URI (`http://purl.imsglobal.org/vocab/lis/v2/membership#Learner`
    is how a platform spells one). All three are the same claim about a person,
    so the last path, fragment or scheme segment is taken and everything that is
    not a letter or a digit becomes an underscore.
    """
    tail = re.split(r"[/#:]", value.strip())[-1]
    return re.sub(r"[^A-Za-z0-9]+", "_", tail).strip("_").upper()


def role_strings(node: Any) -> Iterator[str]:
    """Every string in a session that could be stating a role.

    Walks the whole claim tree rather than one agreed claim name, because E0-16
    spells no claim: a provider may put roles under `roles`, under a namespaced
    URI, or inside a nested object, and a scan that knew the name would report
    "no instructor role here" about a claim it never looked at.

    Values under the personal claims above are skipped — a name, an email address
    and a preferred username describe the person, not what they may do.
    """
    if isinstance(node, Mapping):
        for name, value in node.items():
            if str(name).lower() in PERSONAL_CLAIM_NAMES:
                continue
            yield from role_strings(value)
    elif isinstance(node, list | tuple):
        for item in node:
            yield from role_strings(item)
    elif isinstance(node, str):
        yield node


def roles_in(claims: Any) -> set[str]:
    """Every role this project recognises, stated anywhere in `claims`.

    Matching is exact against the normalised token rather than by substring, for
    the reason `ROLE_ALIASES` gives: `DEAN` is a substring of `ASSISTANT_DEAN`,
    and a fuzzy match would make every assistant dean a dean. Its own control is
    `tests/integration/test_mock_idp_web_login.py`, which runs it against the
    values it is claimed to catch *and* the values it is claimed to let past —
    `docs/MISTAKES.md` entry 3, since every assertion about a role that is
    *absent* is satisfied by a scanner that finds nothing at all.
    """
    tokens = {role_token(value) for value in role_strings(claims)}
    return {
        role
        for role, aliases in ROLE_CLAIM_ALIASES.items()
        if tokens & {role_token(alias) for alias in aliases}
    }


def purview_claim_names(node: Any) -> set[str]:
    """Every claim name in a session that names a purview rather than a person."""
    found: set[str] = set()
    if isinstance(node, Mapping):
        for name, value in node.items():
            lowered = str(name).lower()
            if any(fragment in lowered for fragment in PURVIEW_CLAIM_FRAGMENTS):
                found.add(str(name))
            found |= purview_claim_names(value)
    elif isinstance(node, list | tuple):
        for item in node:
            found |= purview_claim_names(item)
    return found


class LoginAttempt(NamedTuple):
    """One trip through the provider's login form, refused or not.

    `code` is `None` when the provider did not issue one, whatever it did
    instead — that is the shape criterion 7 needs, because "an instructor cannot
    obtain a session here" is a claim about what did *not* come back and the
    status alone does not say it.
    """

    submission: dict[str, str]
    request: dict[str, str]
    verifier: str
    response: Any
    location: str | None
    code: str | None
    state: str | None

    @property
    def refused(self) -> bool:
        return self.code is None


class WebLogin(NamedTuple):
    """One completed authorization code flow: the session a web login produces."""

    submission: dict[str, str]
    request: dict[str, str]
    verifier: str
    code: str
    state: str | None
    tokens: dict[str, Any]
    id_token: str
    signature: JsonWebSignature

    @property
    def claims(self) -> dict[str, Any]:
        return self.signature.claims

    @property
    def header(self) -> dict[str, Any]:
        return self.signature.header


class AuthorizationAttempt(NamedTuple):
    """An authorization request, taken as far as the page that asks who you are."""

    request: dict[str, str]
    verifier: str
    page_url: str | None
    form: dict[str, Any] | None
    response: Any


def import_mock_idp_application(values: Mapping[str, str]) -> Any:
    """The mock provider's ASGI application. See `import_mock_application` above."""
    return import_mock_application(
        MOCK_IDP_DIR,
        MOCK_IDP_MODULES,
        values,
        absent_directory=(
            f"{MOCK_IDP_DIR} does not exist. E0-16's scope is a `mock-idp/` FastAPI application "
            "with a Dockerfile, added to Compose as `mock-idp` (SPEC §7.2 lists the service and "
            "§9.2 says what it is for: an in-repo OIDC provider so that the second entry door is "
            "exercised in every run)."
        ),
        nothing_found=(
            "Nothing under `mock-idp/app/` exposes a FastAPI application. Looked for a "
            f"module-level instance, then a factory named one of {list(APPLICATION_FACTORY_NAMES)}"
            f", in {list(MOCK_IDP_MODULES)}; imported {{imported}}. If it is reachable under a "
            "spelling none of those covers, that is a defect in `MockIdentityProvider` in "
            "tests/conftest.py rather than in the mock, and MOCK_IDP_MODULES there is the one "
            "line that changes."
        ),
    )


class MockIdentityProvider:
    """E0-16's provider, driven the way a client drives one rather than by name.

    **Nothing about the provider's URLs is written down except the one the
    standard fixes**, so nothing here is hardcoded that the protocol can supply
    instead:

      - The discovery document is fetched from `/.well-known/openid-configuration`,
        which OIDC Discovery 1.0 §4 fixes and E0-16's scope repeats.
      - Every endpoint — authorization, token, JWKS — is read out of that
        document, because that is how a client finds them. A provider that serves
        them at sensible paths and advertises none has built something no
        conformant client can configure itself from, and the right outcome is a
        red rather than a fixture that goes looking.
      - The identities come out of the login form, the way a browser meets them.

    **The one thing E0-16 does not say is how a client learns the seeded
    `client_id` and redirect URI.** A registered client is what an authorization
    request names, so a test cannot start a flow without one. `registration()`
    looks in the three places a reasonable implementation would put it and then
    fails by name; it does not invent one.

    **What this does not do is decide anything.** Where the ticket leaves a name
    open, a test fails saying so rather than passing against an interface nobody
    asked for.
    """

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        from fastapi.testclient import TestClient

        self.values = dict(values or {})
        self.application = import_mock_idp_application(self.values)
        self.client = TestClient(self.application, follow_redirects=False)
        # Entered so the application's lifespan runs: a provider that generates
        # its signing key on startup has not generated one until it does.
        self.client.__enter__()
        self._discovery: dict[str, Any] | None = None
        self._registration: dict[str, str] | None = None
        self._registration_document: dict[str, Any] | None = None
        self._registration_source: str | None = None

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    # -- what the application serves ----------------------------------------

    def paths(self, method: str = "GET") -> list[str]:
        """Every declared path that answers `method` and takes no path parameter."""
        return declared_paths(self.application, method)

    def discovery(self) -> dict[str, Any]:
        """The provider's metadata document, fetched from the standard path."""
        if self._discovery is None:
            response = self.client.get(DISCOVERY_PATH)
            assert response.status_code == 200, (
                f"`GET {DISCOVERY_PATH}` answered {response.status_code} rather than 200. E0-16's "
                "scope puts the discovery document there and OIDC Discovery 1.0 §4 fixes the "
                "path; a client that cannot fetch it cannot find any other endpoint. Body begins "
                f"{response.text[:200]!r}."
            )
            try:
                document = response.json()
            except ValueError as failure:
                pytest.fail(
                    f"`GET {DISCOVERY_PATH}` served something that is not JSON ({failure}). "
                    "Provider metadata is a JSON object."
                )
            assert isinstance(document, dict) and document, (
                f"`GET {DISCOVERY_PATH}` served {document!r}, which is not a provider metadata "
                "document. OIDC Discovery 1.0 §3 makes it a non-empty JSON object."
            )
            self._discovery = document
        return self._discovery

    def metadata(self, name: str, purpose: str) -> str:
        """One string member of the discovery document, or a failure naming it."""
        document = self.discovery()
        value = document.get(name)
        if not isinstance(value, str) or not value:
            pytest.fail(
                f"The discovery document advertises no `{name}` (it carries {sorted(document)}). "
                f"That member is how a client learns {purpose}, so without it there is nothing to "
                "call — whatever the provider serves and at whatever path."
            )
        return value

    def endpoint_path(self, name: str, purpose: str) -> str:
        """One advertised endpoint, as this in-process client can request it."""
        return local_target(self.metadata(name, purpose))

    def jwks(self) -> dict[str, Any]:
        """The published key set, fetched from the advertised `jwks_uri`."""
        path = self.endpoint_path("jwks_uri", "where the provider publishes its signing keys")
        response = self.client.get(path)
        assert response.status_code == 200, (
            f"The JWKS endpoint `{path}` answered {response.status_code} rather than 200. E0-16's "
            "third criterion is an `id_token` that verifies against the served JWKS, and a key "
            "set nobody can fetch verifies nothing."
        )
        document = response.json()
        assert isinstance(document, dict), (
            f"The JWKS endpoint `{path}` served {document!r}, which is not a JWK Set. RFC 7517 "
            "makes a key set a JSON object with a `keys` member."
        )
        return document

    def published_keys(self) -> list[dict[str, Any]]:
        keys = self.jwks().get("keys")
        return [key for key in keys if isinstance(key, dict)] if isinstance(keys, list) else []

    def verifies(self, token: Any) -> dict[str, Any] | None:
        """The published key that verifies `token`, or `None` if none does.

        The arithmetic is `verify_rs256` above — written out of `pow` and
        `hashlib` because nothing in the locked dependency set verifies a JWS, and
        controlled by its own tests rather than trusted.
        """
        signature = token if isinstance(token, JsonWebSignature) else split_jws(str(token))
        return verifying_key(signature, self.jwks())

    # -- the seeded client --------------------------------------------------

    def registration(self) -> dict[str, str]:
        """The client an authorization request may name, and where it may come back to.

        Looked for in three places, most published first, because E0-16 names
        none and a fixture that pinned one would decide it:

          1. A JSON document the provider serves carrying a `client_id`. The mock
             platform publishes its registration exactly this way
             ([ADR 0036](../docs/adr/0036-the-mock-platform-publishes-its-registration-as-a-document.md)),
             so a provider written beside it may too.
          2. A form on one of its own pages carrying `client_id` as a field — a
             demo page that starts a flow announces the client the same way the
             launch page announces the platform.
          3. The `mock-idp` service's Compose environment, which is where the mock
             platform's five addresses are written as literals
             ([ADR 0037](../docs/adr/0037-the-mock-platform-is-configured-by-compose-literals.md)).

        A failure here is a real gap rather than a fixture problem: E1's login
        work and E0-18's Playwright path both have to learn the same two values,
        and if nothing publishes them then every client learns them by reading the
        source.
        """
        if self._registration is None:
            found = (
                self.registration_in_a_document()
                or self.registration_in_a_form()
                or self.registration_in_compose()
            )
            if found is None:
                pytest.fail(
                    "Nothing tells a client which `client_id` this provider will accept or which "
                    "redirect URI it will return to, so no authorization request can be built. "
                    f"Looked for a JSON document carrying `client_id` among {self.paths('GET')}, "
                    "for a form field of that name on those pages, and for a `CLIENT_ID` entry in "
                    f"the `{MOCK_IDP_SERVICE}` service's Compose environment. E0-16 spells none "
                    "of the three, and a fixture that guessed would be deciding it — publish the "
                    "registration the way the mock platform does (ADR 0036), or say in the "
                    "ticket where a client reads it."
                )
            self._registration = found
        return self._registration

    @staticmethod
    def client_registration_in(node: Any) -> dict[str, str] | None:
        """The first mapping anywhere in `node` that names a client and a redirect URI."""
        if isinstance(node, Mapping):
            client = node.get("client_id")
            redirect = node.get("redirect_uri")
            if not isinstance(redirect, str):
                listed = node.get("redirect_uris")
                redirect = listed[0] if isinstance(listed, list) and listed else None
            if isinstance(client, str) and client and isinstance(redirect, str) and redirect:
                return {"client_id": client, "redirect_uri": redirect}
            for value in node.values():
                found = MockIdentityProvider.client_registration_in(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = MockIdentityProvider.client_registration_in(item)
                if found is not None:
                    return found
        return None

    def registration_in_a_document(self) -> dict[str, str] | None:
        """A JSON document the provider serves that names its seeded client.

        The document itself is kept, not only the two values pulled out of it:
        [ADR 0058](../docs/adr/0058-the-registration-document-is-the-contract-between-the-mocks.md)
        makes `launch_only_roles`, `lms_user_id` and `roles_claim` contract
        members of it, which is how a test names one seeded person rather than
        asserting over whichever set of people happens to be there.
        """
        for path in self.paths("GET"):
            if path == DISCOVERY_PATH:
                continue
            response = self.client.get(path)
            if response.status_code != 200:
                continue
            if "json" not in response.headers.get("content-type", "").lower():
                continue
            try:
                document = response.json()
            except ValueError:
                continue
            found = self.client_registration_in(document)
            if found is not None:
                self._registration_document = document if isinstance(document, dict) else None
                self._registration_source = f"the JSON document at `{path}`"
                return found
        return None

    def registration_in_a_form(self) -> dict[str, str] | None:
        """A form on one of the provider's own pages that names its seeded client."""
        for path in self.paths("GET"):
            response = self.client.get(path)
            if response.status_code != 200:
                continue
            if "html" not in response.headers.get("content-type", "").lower():
                continue
            for form in forms_in(response.text):
                found = self.client_registration_in(form["fields"])
                if found is not None:
                    self._registration_source = f"a form on the page at `{path}`"
                    return found
        return None

    @staticmethod
    def registration_in_compose() -> dict[str, str] | None:
        """The client and redirect URI written as Compose literals on the service."""
        services = load_compose(BASE_COMPOSE_PATH).get("services") or {}
        service = services.get(MOCK_IDP_SERVICE)
        block = service.get("environment") if isinstance(service, dict) else None
        if not isinstance(block, dict):
            return None
        values = {str(name).upper(): str(value) for name, value in block.items() if value}
        literal = {name: value for name, value in values.items() if "$" not in value}
        client = next((v for k, v in literal.items() if k.endswith("CLIENT_ID")), None)
        redirect = next((v for k, v in literal.items() if "REDIRECT" in k), None)
        if client and redirect:
            return {"client_id": client, "redirect_uri": redirect}
        return None

    # -- the seeded people, out of the published document (ADR 0058) ---------

    def registration_document(self) -> dict[str, Any]:
        """The whole published registration document, or a failure saying there is none."""
        self.registration()
        if self._registration_document is None:
            pytest.fail(
                "This provider publishes no registration *document*, so the seeded people cannot "
                f"be read off it — the client registration was found in {self._registration_source}"
                ". ADR 0058 makes that document the contract between the two mocks: `roles`, "
                "`launch_only_roles`, `lms_user_id` and `roles_claim` are how E0-18 finds the same "
                "person on both doors, and how a test names one seeded person instead of asserting "
                "over whoever happens to be seeded."
            )
        return self._registration_document

    @staticmethod
    def mappings_carrying(node: Any, member: str) -> list[dict[str, Any]]:
        """Every mapping anywhere in `node` that carries `member` as a key.

        The document's shape below the contract members is not written down, so
        the people are found by what a person *has* — a `roles` list — rather than
        by the name of the array holding them. That keeps this from pinning a key
        ADR 0058 does not fix.
        """
        found: list[dict[str, Any]] = []
        if isinstance(node, Mapping):
            if member in node:
                found.append(dict(node))
            for value in node.values():
                found.extend(MockIdentityProvider.mappings_carrying(value, member))
        elif isinstance(node, list):
            for item in node:
                found.extend(MockIdentityProvider.mappings_carrying(item, member))
        return found

    @staticmethod
    def first_member(node: Any, member: str) -> Any:
        """The first value of `member` found anywhere in `node`, or `None`."""
        if isinstance(node, Mapping):
            if member in node:
                return node[member]
            for value in node.values():
                found = MockIdentityProvider.first_member(value, member)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = MockIdentityProvider.first_member(item, member)
                if found is not None:
                    return found
        return None

    def published_users(self) -> list[dict[str, Any]]:
        """Every seeded person the registration document publishes."""
        found = self.mappings_carrying(self.registration_document(), "roles")
        assert found, (
            "The registration document publishes nobody — no mapping in it carries a `roles` "
            f"member (it carries {sorted(self.registration_document())}). ADR 0058 makes the "
            "seeded people part of that document, and every assertion about who is seeded reads "
            "them from there."
        )
        return found

    def roles_claim_name(self) -> str:
        """The claim a session states its roles in, as the document declares it."""
        declared = self.first_member(self.registration_document(), "roles_claim")
        if not isinstance(declared, str) or not declared:
            pytest.fail(
                "The registration document declares no `roles_claim` (it carries "
                f"{sorted(self.registration_document())}). ADR 0058 makes it a contract member "
                "because it is how a client knows which claim to read a session's roles out of — "
                "without it, every reader guesses, and this suite's own scan is a guess that "
                "happens to work."
            )
        return declared

    def identity_of(self, user: Mapping[str, Any], attempt: AuthorizationAttempt) -> dict[str, str]:
        """The login-form submission that signs in as `user`.

        Matched on the form's *choice* values only, never on its hidden fields:
        the hidden fields carry the client id, the redirect URI and the request's
        own state, and a published person who happened to share one of those
        strings would otherwise match the first submission in the list — which is
        the submission this would have returned anyway, so the test would pass
        having signed in as somebody else.
        """
        form = self.require_login_form(attempt)
        wanted = {value for value in user.values() if isinstance(value, str) and value}
        offered: list[dict[str, str]] = []
        for submission in self.offered_identities(attempt):
            chosen = {name: str(submission[name]) for name in form["choices"] if name in submission}
            offered.append(chosen)
            if wanted & set(chosen.values()):
                return submission
        pytest.fail(
            f"The login form offers no identity matching the published user {user!r} — it offers "
            f"{offered}. A person the registration document publishes and the login form cannot "
            "sign in is a person E0-18 would find on one door and not on the other."
        )

    # -- the authorization code flow ----------------------------------------

    def authorization_request(
        self, *, omitting: Sequence[str] = (), **overrides: str
    ) -> tuple[dict[str, str], str]:
        """A conformant authorization request with PKCE, and the verifier behind it.

        Every value is one OIDC Core 1.0 §3.1.2.1 and RFC 7636 require of a code
        flow with PKCE, so nothing here is a preference. `omitting` sends a
        request with those parameters absent, which an override cannot express —
        and "absent" is the case that matters for a downgrade.
        """
        registration = self.registration()
        verifier, challenge = pkce_pair()
        request = {
            "response_type": "code",
            "scope": "openid",
            "client_id": registration["client_id"],
            "redirect_uri": registration["redirect_uri"],
            "state": secrets.token_urlsafe(24),
            "nonce": secrets.token_urlsafe(24),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        request.update(overrides)
        for name in omitting:
            request.pop(name, None)
        return request, verifier

    def begin(self, *, omitting: Sequence[str] = (), **overrides: str) -> AuthorizationAttempt:
        """Send an authorization request and follow it to the page that asks who you are."""
        request, verifier = self.authorization_request(omitting=omitting, **overrides)
        return self.begin_from(list(request.items()), verifier)

    def begin_from(
        self, parameters: Sequence[tuple[str, str]], verifier: str
    ) -> AuthorizationAttempt:
        """The same, from a parameter *list* rather than a mapping.

        A mapping cannot express a query string that carries one name twice, and
        `client_id=evil&client_id=real` is a request a real client never sends and
        an attacker does. Which of the two a server reads is undefined by RFC 6749
        and decided by the framework underneath it, so a provider that takes the
        last wins for one ordering and loses for the other — which means a test
        written with a mapping cannot ask the question at all.
        """
        path = self.endpoint_path(
            "authorization_endpoint", "where an authorization request is sent"
        )
        response = self.client.get(path, params=list(parameters))
        request = dict(parameters)
        page_url, form, final = self.follow_to_a_login_form(path, response, request)
        return AuthorizationAttempt(
            request=request, verifier=verifier, page_url=page_url, form=form, response=final
        )

    def follow_to_a_login_form(
        self, url: str, response: Any, request: Mapping[str, str]
    ) -> tuple[str | None, dict[str, Any] | None, Any]:
        """Follow the provider's own redirects until a page carrying a form arrives.

        A redirect to the *client's* redirect URI is not followed and ends the
        walk: that is the authorization response, and reaching it without being
        asked anything is a provider that issued a session to whoever asked.
        """
        current, hops = url, 0
        while hops < MAX_LOGIN_HOPS:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location") or ""
                if not location or location.startswith(str(request.get("redirect_uri", "\0"))):
                    return None, None, response
                current = local_target(urljoin(f"http://testserver{current}", location))
                response = self.client.get(current)
                hops += 1
                continue
            if (
                response.status_code == 200
                and "html" in response.headers.get("content-type", "").lower()
            ):
                forms = forms_in(response.text)
                posting = [form for form in forms if form["method"] == "post"]
                chosen = (posting or forms or [None])[0]
                return current, chosen, response
            return current, None, response
        return current, None, response

    def require_login_form(self, attempt: AuthorizationAttempt) -> dict[str, Any]:
        """The login form, or a failure saying what arrived instead."""
        if attempt.form is None:
            pytest.fail(
                "The authorization request did not reach a page carrying a form, so there is no "
                f"login to drive. The last response was {attempt.response.status_code} for "
                f"`{attempt.page_url}`; the provider serves {self.paths('GET')}. E0-16's scope "
                "asks for 'a login form simple enough for a Playwright test to drive without "
                "brittle selectors', and a provider that answers an authorization request without "
                "asking who is signing in has issued a session to whoever asked."
            )
        typed = [
            control
            for control in attempt.form["controls"]
            if control.get("tag") == "input"
            and control.get("type", "text").lower() in TYPED_INPUT_TYPES
            and not control.get("value")
        ]
        if typed and not attempt.form["choices"]:
            pytest.fail(
                "The login form asks for values this test cannot know — it carries "
                f"{[control.get('name') for control in typed]} and offers no choice of seeded "
                "identity. E0-16 seeds the identities and spells no credential for any of them, "
                "so either the form offers them (a `<select>`, radio buttons or named submit "
                "buttons are all read here) or the ticket has to say what a test signs in with."
            )
        return attempt.form

    def identify(
        self, attempt: AuthorizationAttempt, identity: Mapping[str, str] | None
    ) -> dict[str, str]:
        """One submission for `attempt`'s form, signing in as `identity`.

        The chosen values are the ones the form offers a *choice* of — a
        `<select>`, radio buttons or named submit buttons — and everything else
        comes from this attempt's own form. That is what keeps a caller able to
        say "sign in as this one" without carrying another flow's hidden state
        along with it.
        """
        offered = self.offered_identities(attempt)
        if identity is None:
            return offered[0]
        form = self.require_login_form(attempt)
        wanted = {name: value for name, value in identity.items() if name in form["choices"]}
        for submission in offered:
            if all(submission.get(name) == value for name, value in wanted.items()):
                return submission
        return {**offered[0], **wanted}

    def offered_identities(self, attempt: AuthorizationAttempt) -> list[dict[str, str]]:
        """Every submission the login form could send, one per seeded identity."""
        form = self.require_login_form(attempt)
        submissions = form_submissions(form)[:MAX_LOGIN_VARIANTS]
        assert submissions, (
            "The login form offers nothing to submit, so no identity can sign in. E0-16 seeds six "
            "web-login roles plus the person holding Care and an instructor assignment."
        )
        return submissions

    @staticmethod
    def identity_field(form: Mapping[str, Any]) -> str:
        """The name of the field a login form picks a person with.

        A login form offering seeded identities offers them under one name — the
        `<select>`, the radio group, the named submit buttons. Where a form offers
        more than one set of choices, the one whose name reads as a person is
        taken, and an ambiguity this cannot resolve stops rather than guesses:
        choosing would let a test submit the wrong field and pass for a reason
        unrelated to what it asserts.

        On the driver rather than in a test module because two modules ask it —
        the refusal tests over launch-only identities, and the duplicate-parameter
        tests that send the same name in the query and the body — and two copies
        of "which field names the person" would drift (`docs/MISTAKES.md` entry
        13).
        """
        choices = sorted(name for name, options in form["choices"].items() if options)
        if len(choices) == 1:
            return choices[0]
        hinted = [
            name for name in choices if any(hint in name.lower() for hint in IDENTITY_FIELD_HINTS)
        ]
        if len(hinted) == 1:
            return hinted[0]
        pytest.fail(
            f"The login form offers choices under {choices}, and this cannot tell which one names "
            "the person signing in. Submitting the wrong field would make a refusal a fact about "
            "something else. `IDENTITY_FIELD_HINTS` in tests/conftest.py is the one line that "
            "changes."
        )

    def submit_login(
        self,
        attempt: AuthorizationAttempt,
        submission: Mapping[str, str],
        *,
        query: Mapping[str, str] | None = None,
    ) -> LoginAttempt:
        """Post one identity to the login form and read what came back.

        Asserts nothing about the outcome. Criterion 7 needs a refusal to be
        readable as a refusal rather than as a fixture failure, so the caller
        decides whether a missing code is the answer it wanted.

        `query` puts parameters on the form's action URL *as well as* in the body,
        which is the only way to ask whether a name arriving from two sources is
        seen as one duplicate. A browser never sends that request; something
        pretending to be a browser does.
        """
        form = self.require_login_form(attempt)
        action = urljoin(f"http://testserver{attempt.page_url}", form["action"] or "")
        target = url_with_query(local_target(action), query or {})
        values = dict(submission)
        if form["method"] == "post":
            response = self.client.post(target, data=values)
        else:
            response = self.client.get(target, params=values)
        location, code, state = self.read_authorization_response(response)
        return LoginAttempt(
            submission=values,
            request=dict(attempt.request),
            verifier=attempt.verifier,
            response=response,
            location=location,
            code=code,
            state=state,
        )

    @staticmethod
    def read_authorization_response(response: Any) -> tuple[str | None, str | None, str | None]:
        """The `code` and `state` the provider sent back, wherever it put them.

        A redirect carrying them in the query is the code flow's default response
        mode; a self-submitting form is `form_post`, which is legal and which the
        LTI side of this repository already uses. Which one E0-16 chose is not
        something this file decides, so both are read.
        """
        location = response.headers.get("location")
        if location:
            split = urlsplit(location)
            for blob in (split.query, split.fragment):
                pairs = parse_qs(blob)
                if "code" in pairs:
                    return location, pairs["code"][0], (pairs.get("state") or [None])[0]
            return location, None, None
        if response.status_code == 200:
            for form in forms_in(response.text):
                if "code" in form["fields"]:
                    return (
                        form["action"] or None,
                        form["fields"]["code"],
                        form["fields"].get("state"),
                    )
        return None, None, None

    def redeem(
        self,
        code: str,
        verifier: str | None,
        *,
        omitting: Sequence[str] = (),
        **overrides: str,
    ) -> Any:
        """Exchange an authorization code at the token endpoint. Asserts nothing.

        The body is RFC 6749 §4.1.3's plus RFC 7636's `code_verifier`, form-encoded
        as those specifications require. `verifier` of `None` sends no verifier at
        all, which is the downgrade case and is not the same request as sending a
        wrong one.
        """
        return self.redeem_from(
            list(self.token_body(code, verifier, omitting=omitting, **overrides).items())
        )

    def token_body(
        self,
        code: str,
        verifier: str | None,
        *,
        omitting: Sequence[str] = (),
        **overrides: str,
    ) -> dict[str, str]:
        """What a conformant client posts to redeem `code`.

        Built here rather than inside `redeem` so that a test asking what the
        endpoint does with a *repeated* field can start from the same body a
        correct client sends and add one entry to it — one definition of the
        request, two ways of encoding it (`docs/MISTAKES.md` entry 13).
        """
        registration = self.registration()
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": registration["redirect_uri"],
            "client_id": registration["client_id"],
        }
        if verifier is not None:
            body["code_verifier"] = verifier
        body.update(overrides)
        for name in omitting:
            body.pop(name, None)
        return body

    def redeem_from(
        self,
        parameters: Sequence[tuple[str, str]],
        *,
        query: Mapping[str, str] | None = None,
    ) -> Any:
        """Post one token request as a list of fields, so a name may appear twice.

        Gathered into a mapping of name to values because that is the shape httpx
        form-encodes with `doseq`; the order of the values under one name is what
        decides the question being asked, and it survives the gathering.

        `query` puts parameters on the token endpoint's URL as well as in the
        body. RFC 6749 §3.1's rule is about the *request* rather than about one
        encoding of it, and a name arriving once from each source is the shape
        that looks like two singletons to anything checking one collection at a
        time.
        """
        fields: dict[str, list[str]] = {}
        for name, value in parameters:
            fields.setdefault(name, []).append(value)
        path = self.endpoint_path("token_endpoint", "where an authorization code is redeemed")
        return self.client.post(url_with_query(path, query or {}), data=fields)

    @staticmethod
    def body_of(response: Any) -> dict[str, Any]:
        """A token endpoint response as a mapping, or an empty one if it is not JSON."""
        try:
            document = response.json()
        except ValueError:
            return {}
        return document if isinstance(document, dict) else {}

    def refuse_an_unspecified_client_credential(self, response: Any) -> None:
        """Turn `invalid_client` into a named gap rather than a passing refusal.

        E0-16 describes no client secret, and PKCE is what a public client
        authenticates a code exchange with, so this suite redeems without one. If
        the provider requires a secret, every exchange here fails — and the two
        refusal criteria would then pass for a reason unrelated to what they
        assert, which is `docs/MISTAKES.md` entry 3 exactly. So it is named
        wherever it appears, on the successes and on the refusals alike.
        """
        if self.body_of(response).get("error") == "invalid_client":
            pytest.fail(
                f"The token endpoint answered {response.status_code} `invalid_client`, so it "
                "requires a client credential this suite does not send. E0-16 names no client "
                "secret and PKCE is what a public client proves possession with — if the seeded "
                "client is confidential, the ticket has to say so, because a refusal for this "
                "reason is indistinguishable from the code-replay and verifier-mismatch refusals "
                "two of its criteria are about."
            )

    def tokens(self, response: Any) -> dict[str, Any]:
        """The token endpoint's successful response, or a failure saying what came back."""
        self.refuse_an_unspecified_client_credential(response)
        assert response.status_code == 200, (
            f"The token endpoint answered {response.status_code} rather than 200 for a code "
            "exchange with a matching PKCE verifier. E0-16 criterion 3 is that this flow "
            f"completes end to end. Body begins {response.text[:300]!r}."
        )
        body = self.body_of(response)
        assert body, (
            f"The token endpoint answered 200 with {response.text[:200]!r}, which is not a JSON "
            "object. RFC 6749 §5.1 makes a successful token response one."
        )
        return body

    def login(
        self,
        identity: Mapping[str, str] | None = None,
        *,
        omitting: Sequence[str] = (),
        **overrides: str,
    ) -> WebLogin:
        """Drive one whole authorization code flow, from the form to the `id_token`.

        This is E0-16's third criterion done by *being* a client: an authorization
        request, a login, a code, and an exchange carrying the verifier. Nothing
        is called that a real client would not call, so a session obtained here
        and a session a browser produces are the same session.

        `identity` selects **which** seeded identity signs in, and only that: the
        hidden fields come from this call's own fresh authorization request. A
        submission carried whole from an earlier attempt would post that attempt's
        state, nonce and challenge into this one, and the session would then be
        checked against a request it did not answer — which reads as the provider
        returning the wrong nonce.
        """
        attempt = self.begin(omitting=omitting, **overrides)
        chosen = self.identify(attempt, identity)
        submitted = self.submit_login(attempt, chosen)
        assert submitted.code, (
            f"Signing in as {chosen} produced no authorization code — the provider answered "
            f"{submitted.response.status_code} and sent {submitted.location!r}. Body begins "
            f"{submitted.response.text[:200]!r}."
        )
        response = self.redeem(submitted.code, submitted.verifier)
        body = self.tokens(response)
        id_token = body.get("id_token")
        assert isinstance(id_token, str) and id_token, (
            f"The token response carries no `id_token` (it carries {sorted(body)}). OIDC Core "
            "1.0 §3.1.3.3 makes it the member that distinguishes an OpenID Connect response from "
            "a plain OAuth 2.0 one, and it is the whole of what E0-16 criterion 3 produces."
        )
        return WebLogin(
            submission=submitted.submission,
            request=submitted.request,
            verifier=submitted.verifier,
            code=submitted.code,
            state=submitted.state,
            tokens=body,
            id_token=id_token,
            signature=split_jws(id_token),
        )

    def logins(self) -> list[WebLogin]:
        """One completed session per identity the login form offers."""
        attempt = self.begin()
        return [self.login(identity) for identity in self.offered_identities(attempt)]

    @staticmethod
    def roles(login: WebLogin) -> set[str]:
        """The roles one session states, by the scan `roles_in` above performs."""
        return roles_in(login.claims)


def find_mock_idp_settings_class() -> Any:
    """The provider's settings class, found rather than imported by path.

    Called inside `mock_package_resolved`, and only from the fixture below, which
    keeps that resolution open for the whole test: a settings class is used after
    it is imported, and its `from_environment` reads the environment at call time.

    Looked for by name first and by *capability* second — any class the mock
    defines that carries a `from_environment` — because E0-16 spells no module and
    no class, and a fixture that insisted on one spelling would report a rename as
    a missing deliverable.
    """
    imported: list[str] = []
    candidates: list[Any] = []
    for name in MOCK_IDP_SETTINGS_MODULES:
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError as failure:
            absent = failure.name
            if absent is not None and (name == absent or name.startswith(f"{absent}.")):
                continue
            raise
        imported.append(name)
        for attribute, value in vars(module).items():
            if attribute.startswith("_") or not inspect.isclass(value):
                continue
            if getattr(value, "__module__", "").split(".")[0] != MOCK_PACKAGE:
                continue
            if not hasattr(value, SETTINGS_FACTORY_NAME):
                continue
            if attribute in PROVIDER_SETTINGS_NAMES:
                return value
            candidates.append(value)
    if candidates:
        return candidates[0]
    pytest.fail(
        f"Nothing under `mock-idp/app/` defines a class with a `{SETTINGS_FACTORY_NAME}` — looked "
        f"in {list(MOCK_IDP_SETTINGS_MODULES)}, imported {imported or 'nothing'}. That callable is "
        "where the redirect URI is validated, and validation with no HTTP surface can only be "
        "reached by importing it. If it is there under a spelling none of "
        "`PROVIDER_SETTINGS_NAMES` reaches, that constant in tests/conftest.py is the one line "
        "that changes."
    )


@pytest.fixture
def mock_idp_settings() -> Iterator[Any]:
    """The provider's settings class, with `mock-idp/`'s `app` resolving for the test.

    The resolution is held open for the body rather than just for the import, so
    that anything `from_environment` imports when it runs still comes out of the
    mock. See `mock_package_resolved` above.
    """
    if not MOCK_IDP_DIR.is_dir():
        pytest.fail(
            f"{MOCK_IDP_DIR} does not exist, so there is no settings object to import. E0-16's "
            "scope is a `mock-idp/` FastAPI application with a Dockerfile."
        )
    with mock_package_resolved(MOCK_IDP_DIR):
        yield find_mock_idp_settings_class()


@pytest.fixture
def mock_idp_compose_environment() -> dict[str, str]:
    """The literal environment `docker-compose.yml` gives the `mock-idp` service.

    Literal values only — anything carrying a `${...}` is dropped, because this is
    handed to a settings object as if it were the container's environment and an
    uninterpolated string is not a value any container ever sees.

    Deliberately asserts nothing: an absent service yields an empty mapping and
    the test that needs it says so, which is the choice every other Compose
    reader in this file makes.
    """
    services = load_compose(BASE_COMPOSE_PATH).get("services") or {}
    service = services.get(MOCK_IDP_SERVICE)
    block = service.get("environment") if isinstance(service, dict) else None
    if not isinstance(block, dict):
        return {}
    return {
        str(name): str(value)
        for name, value in block.items()
        if value is not None and "$" not in str(value)
    }


@pytest.fixture
def mock_idp_dir() -> Path:
    """Where the mock provider must live (SPEC §13). Asserted by the test, not here."""
    return MOCK_IDP_DIR


@pytest.fixture
def mock_idp_service() -> str:
    """The Compose service name SPEC §7.2 gives the mock provider."""
    return MOCK_IDP_SERVICE


@pytest.fixture
def discovery_path() -> str:
    """The path OIDC Discovery 1.0 §4 fixes, for the test that reasons about it.

    Handed over rather than transcribed a second time, so that the path the
    driver fetches and the path a test says a client would build cannot end up
    being two different strings.
    """
    return DISCOVERY_PATH


@pytest.fixture
def claims_in_token() -> Callable[[str], dict[str, Any]]:
    """Read the claims out of a bare `id_token`, for a test holding one raw.

    `WebLogin.claims` covers every flow that completed; this is for the tests that
    have a token endpoint's *response* in hand and need to say what a session the
    provider should never have issued was carrying. Same splitter either way.
    """
    return lambda token: split_jws(str(token)).claims


@pytest.fixture
def padded() -> Callable[[str], str]:
    """Wrap a value in whitespace that a `.strip()` would remove.

    One helper rather than a literal at each call site, because the review round
    that added it found one defect reaching four parameters — a value trimmed
    before the check that judges it — and a second spelling of "padded" would be
    a second definition of the thing under test (`docs/MISTAKES.md` entry 13).

    A leading space and a trailing newline. Neither is exotic: `base64.encodebytes`
    ends every line with the second, which is how the defect arrived.
    """
    return lambda value: f" {value}\n"


@pytest.fixture
def mock_idps() -> Iterator[Callable[..., MockIdentityProvider]]:
    """Start one or more independent mock providers, and shut them all down after.

    A factory rather than a single instance, for the reason `mock_platforms` is
    one: E0-16's last criterion is that keys are generated at startup, and a
    second start generating a second key is not observable from one instance.
    """
    started: list[MockIdentityProvider] = []

    def start(values: Mapping[str, str] | None = None) -> MockIdentityProvider:
        provider = MockIdentityProvider(values)
        started.append(provider)
        return provider

    try:
        yield start
    finally:
        for provider in reversed(started):
            provider.close()


@pytest.fixture
def mock_idp(mock_idps: Callable[..., MockIdentityProvider]) -> MockIdentityProvider:
    """One mock provider, started fresh for this test. See `MockIdentityProvider`."""
    return mock_idps()


@pytest.fixture
def web_login(mock_idp: MockIdentityProvider) -> WebLogin:
    """One completed web login off the first seeded identity.

    E1's login work and E0-18's Playwright path both build on this door, so the
    interface matters the way `signed_launch`'s does: `mock_idp.login(...)` is the
    interface and this fixture is its common case.
    """
    return mock_idp.login()


@pytest.fixture
def roles_in_claims() -> Callable[[Any], set[str]]:
    """Hand `roles_in` to the test that checks the scanner itself.

    The provider reads a session's roles with this same function, so the control
    and the thing it controls cannot end up disagreeing about what counts as a
    role — which is the whole value of the control (`docs/MISTAKES.md` entry 3:
    run the matcher against the text you claim it catches *and* the text you
    claim it allows).
    """
    return roles_in


@pytest.fixture
def purview_claims_in() -> Callable[[Any], set[str]]:
    """Hand `purview_claim_names` to the test that checks that scanner too."""
    return purview_claim_names


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

    Three layers, and the over-supply is the same choice `migration_environment`
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
        (ADR 0012, and `backend/migrations/env.py` reads exactly those three),
        with a whole superuser URL beside them in case the script prefers one.
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
        with environment(migration_environment(database)):
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
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    def plant(
        demo: DemoSeed, name: str, chain: dict[str, Any] | None = None, **overrides: Any
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
