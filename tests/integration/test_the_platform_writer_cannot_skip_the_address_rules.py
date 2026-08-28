"""Writing an `lti_platform` row through SQLAlchemy judges its addresses — deferred E1-05 item 3.

E1-05's security review, LOW, carried to the end of the epic: **the write-time
chokepoint is a call convention.** `app.models.lti.refuse_invalid_registration_addresses`
is called by `scripts/seed.py` because `scripts/seed.py` calls it. Nothing — no
mapper event, no sweep, no grant — makes the next writer do the same, and E11's
registration console is that writer. A console that inserted an `LtiPlatform`
through the ORM without the call would be exactly as unjudged as the raw-SQL
writer ADR 0081 records in its consequences, with the difference that nobody would
know: every test of the rules would still be green, because the rules would still
be right.

The item's own "done when" names the fix: *the call is structural — a
`before_insert`/`before_update` event on `LtiPlatform`.* So this module writes
rows the way a future writer would and asserts that the rules fire anyway.

**Where the environment comes from, and why an absent one is a deployment.** The
rules read `ENVIRONMENT` and a mapper event has no `Settings` in hand, so the
environment is carried on the session: `Session.info["environment"]`, stamped by
`app.db`'s `SessionLocal` from the settings it already builds its engine from, by
`scripts/seed.py`, and by this suite's own session fixtures. A session that states
nothing is judged **as a deployment**, which is the fail-closed direction: the
cost of getting it wrong that way is a refused write somebody notices immediately,
and the cost of the other way is a writer nobody thought about registering the
mock platform in production.

**What this module deliberately does not assert.** A Core `insert()` and a raw SQL
statement still write whatever they are given — mapper events do not fire for
either. That is recorded residue, extending the residue ADR 0081 already carries,
and a test pinning it would turn a known limitation into a promised behaviour.

**Every vector here needs no name lookup.** The mock platform's Compose host is
refused by rule 2 before anything is resolved, and the private address is a
literal, which `getaddrinfo` answers without a query. The event takes the default
resolver — it has no injection seam and wants none — so a hostname in this module
would make its result depend on the machine's name server.

**Which failure a red here is.** The two write-and-succeed rows and the session
control are green on today's tree: no event exists, so an ORM insert simply
happens, and they must stay green afterwards for a validator that refuses
everything outside development. Everything else is expected red on the absence of
the event.
"""

from typing import Any
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

PLATFORM_TABLE = "lti_platform"

# The three columns the chokepoint judges, spelled as ADR 0081 and E1-05 spell
# them and as `tests/unit/test_registration_address_constraints.py` spells them.
AUTHORIZATION_ENDPOINT = "authorization_endpoint"
JWKS_URL = "jwks_url"
AUTH_TOKEN_URL = "auth_token_url"  # noqa: S105 - a column name, not a credential
ADDRESS_COLUMNS = (AUTHORIZATION_ENDPOINT, JWKS_URL, AUTH_TOKEN_URL)

# A deployment's `ENVIRONMENT`, and a registration a deployment would legitimately
# hold. A globally routable IP literal on all three columns: `https` satisfies rule
# 1, it is not the mock, it is neither loopback nor link-local, and rule 5 resolves
# a literal without asking anybody. Documentation ranges (`203.0.113.0/24`,
# `192.0.2.0/24`) would be refused by rule 5 — they report `is_global` false — so
# the obvious placeholder is the one thing that cannot be used here.
PRODUCTION = "production"
A_GLOBAL_ADDRESS = "93.184.216.34"
A_VALID_REGISTRATION = {
    AUTHORIZATION_ENDPOINT: f"https://{A_GLOBAL_ADDRESS}/lti/authorize",
    JWKS_URL: f"https://{A_GLOBAL_ADDRESS}/.well-known/jwks.json",
    AUTH_TOKEN_URL: f"https://{A_GLOBAL_ADDRESS}/lti/token",
}

# The two refused vectors, one per rule, so that a green refusal cannot be
# attributed to the wrong one and so that neither needs DNS. The mock's host is
# rule 2 — ADR 0038's fourth property is that a production Pulse holds no row
# naming that issuer, and this event is the layer that holds when a guard is
# bypassed. The private literal is rule 5, the address class the cleanup batch
# adds.
MOCK_SERVICE = "mock-lms"
A_MOCK_ADDRESS = f"https://{MOCK_SERVICE}:8443/.well-known/jwks.json"
A_PRIVATE_ADDRESS = "10.0.0.7"
A_PRIVATE_ADDRESS_URL = f"https://{A_PRIVATE_ADDRESS}/.well-known/jwks.json"

REFUSED_JWKS_URLS = {
    "the mock platform's own host": A_MOCK_ADDRESS,
    "an address that resolves privately": A_PRIVATE_ADDRESS_URL,
}


def registration_error() -> type[BaseException]:
    """The error the chokepoint raises, named rather than caught as `Exception`.

    Named for the reason the unit module gives on the same import: a bare
    `Exception` is satisfied by a `TypeError` or an `IntegrityError` out of a row
    this module built wrongly, which is a broken test reading as a refused
    registration.
    """
    try:
        from app.models.lti import RegistrationAddressError
    except ImportError as absent:
        pytest.fail(
            f"`app.models.lti` exposes no `RegistrationAddressError` ({absent}). E1-05 raises it "
            "from the registration-address chokepoint and the mapper event this module is about "
            "raises the same thing."
        )
    return RegistrationAddressError


def development_environment() -> str:
    """The `ENVIRONMENT` value that means development, read from its one definition."""
    from app.config import DEVELOPMENT_ENVIRONMENT

    assert isinstance(DEVELOPMENT_ENVIRONMENT, str) and DEVELOPMENT_ENVIRONMENT, (
        "`app.config.DEVELOPMENT_ENVIRONMENT` is not a non-empty string, so this module cannot "
        "tell which environment admits the mock platform's own addresses."
    )
    return DEVELOPMENT_ENVIRONMENT


def platform_model() -> Any:
    """The mapped class for `lti_platform`, found by its table rather than by its name.

    Found rather than imported by name for the reason every discovery in this
    suite gives: the deferred item names the event and the table, and pinning a
    class name here would settle something the item leaves to the implementer. The
    failure below names what could not be found, so an absence is a failed
    assertion rather than an `AttributeError` in a helper.
    """
    import importlib

    module = importlib.import_module("app.models.lti")
    found = [
        value
        for value in vars(module).values()
        if isinstance(value, type) and getattr(value, "__tablename__", None) == PLATFORM_TABLE
    ]
    if len(found) != 1:
        pytest.fail(
            f"`app.models.lti` defines {len(found)} mapped classes whose `__tablename__` is "
            f"`{PLATFORM_TABLE}` ({[value.__name__ for value in found]}), and this module needs "
            "exactly one: the class a future writer of a registration row would construct, and "
            "the class deferred E1-05 item 3 puts the `before_insert`/`before_update` event on."
        )
    return found[0]


def attribute_names(model: Any) -> dict[str, str]:
    """Each mapped column's name, mapped to the attribute it is reached through.

    Followed rather than assumed: an attribute and its column need not share a
    spelling, and a module that guessed would build a row with the address columns
    left at whatever the template carried — which is a test that writes a valid
    registration while claiming to write a refused one.
    """
    from sqlalchemy import inspect as mapper_of

    return {column.name: str(key) for key, column in mapper_of(model).columns.items()}


def unique_column_names(table: Any) -> set[str]:
    """Every column covered by a unique constraint or a unique index on `table`.

    A second registration row seeded beside the first has to differ wherever the
    schema says rows differ, or the insert fails on a constraint and the failure
    reads as a refusal.
    """
    from sqlalchemy import UniqueConstraint

    names: set[str] = set()
    for constraint in table.constraints:
        if isinstance(constraint, UniqueConstraint):
            names.update(column.name for column in constraint.columns)
    for index in table.indexes:
        if index.unique:
            names.update(column.name for column in index.columns)
    return names


def a_platform_row(model: Any, table: Any, template: Any, **addresses: str | None) -> Any:
    """An unsaved `LtiPlatform`, built from a row the schema already accepted.

    Every column is copied from `template` — a row this suite seeded through Core
    — except the primary key, which the database generates (ADR 0016), the columns
    a unique constraint covers, which get a marker so two rows can coexist, and the
    three addresses, which are this module's whole subject.

    Copying rather than inventing, because the point of the test is the *addresses*
    and a row that failed on some unrelated NOT NULL column would report the
    absence of a mapper event as a schema error.
    """
    marker = uuid4().hex[:12]
    by_column = attribute_names(model)
    missing = [name for name in ADDRESS_COLUMNS if name not in by_column]
    if missing:
        pytest.fail(
            f"`{model.__name__}` maps no {missing} column — it maps {sorted(by_column)}. Those "
            "three are the columns ADR 0081's chokepoint judges, and E1-05 added the two beside "
            "`jwks_url`."
        )
    primary_key = {column.name for column in table.primary_key.columns}
    unique = unique_column_names(table)

    values: dict[str, Any] = {}
    for name, attribute in by_column.items():
        if name in primary_key:
            continue
        if name in ADDRESS_COLUMNS:
            values[attribute] = addresses.get(name, A_VALID_REGISTRATION[name])
            continue
        carried = template[name]
        if name in unique and isinstance(carried, str):
            carried = f"{carried}-{marker}"
        values[attribute] = carried
    return model(**values)


def written(session: Any, instance: Any) -> BaseException | None:
    """Flush one ORM write, answering the exception it raised or `None`.

    Inside a savepoint, so a refused flush leaves the rest of the test's rows where
    they were: the template row this instance was built from is one of them, and a
    test whose fixture data vanished with the refusal would report the next
    assertion's failure instead of this one.
    """
    try:
        with session.begin_nested():
            session.add(instance)
            session.flush()
    except Exception as refused:
        return refused
    return None


def refusal(session: Any, instance: Any, what: str) -> BaseException:
    """Require the write to be refused, and answer the refusal for further reading."""
    escaped = written(session, instance)
    assert escaped is not None, (
        f"{what} was written with no complaint. Deferred E1-05 item 3: nothing today makes a "
        "writer of `lti_platform` call `refuse_invalid_registration_addresses`, so a console, a "
        "script, or a future service that constructs the model and flushes it stores whatever it "
        "was given. The done-when is a `before_insert`/`before_update` event on the model."
    )
    assert isinstance(escaped, registration_error()), (
        f"{what} was refused with {escaped!r}, which is not `RegistrationAddressError`. A refusal "
        "that arrives as an `IntegrityError` or a `TypeError` is this test building a bad row, not "
        "the address rules firing — and a test that accepted any exception could never tell the "
        "two apart."
    )
    return escaped


@pytest.fixture
def platform_template(seed_rows: Any) -> Any:
    """One `lti_platform` row, seeded through Core, to build ORM rows from.

    Core, deliberately: mapper events do not fire for it, so this row exists
    whatever the event does, and the test's own subject is the ORM write that
    follows.
    """
    return seed_rows(PLATFORM_TABLE)


@pytest.fixture
def platform_table(metadata_tables: dict[str, Any]) -> Any:
    table = metadata_tables.get(PLATFORM_TABLE)
    if table is None:
        pytest.fail(
            f"There is no `{PLATFORM_TABLE}` table (there are {sorted(metadata_tables)}). E0-08 "
            "creates it and E1-05 adds two of the three columns this module is about."
        )
    return table


# ---------------------------------------------------------------------------
# Controls. **A red in this section means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_session_this_suite_writes_through_states_its_environment(db_session: Any) -> None:
    """A control: the fixture every ORM write in this suite goes through is stamped.

    The event judges an unstamped session as a deployment, which is the right
    default and is also a live hazard for this repository's own tests: every
    fixture that seeds a registration is seeding the mock platform's cleartext
    addresses on a Compose service name, and under a deployment's rules those are
    refused. A ticket whose new rule makes an earlier ticket's tests unrunnable is
    `docs/MISTAKES.md` entry 22, and the stamp on `db_session` is what stops it.

    Read here rather than assumed, because a fixture that quietly lost the stamp
    would make every refusal below pass for the wrong reason: the write would be
    refused because nobody said what environment it was in.
    """
    assert db_session.info.get("environment") == development_environment(), (
        f"`db_session.info` carries {db_session.info.get('environment')!r} and this suite writes "
        f"development rows ({development_environment()!r}). The stamp is in "
        "tests/fixtures/database.py; without it every ORM write in the suite is judged by a "
        "deployment's rules."
    )


def test_a_registration_written_through_the_orm_in_development_is_written(
    db_session: Any, platform_template: Any, platform_table: Any
) -> None:
    """A control, and the acceptance half of the whole module: ordinary writes still work.

    The demo seed writes the mock platform's own addresses, which rules 1, 2 and 5
    all refuse anywhere else, and it writes them through this same model. An event
    that refused unconditionally would pass every refusal below and stop `make
    seed` — which takes SPEC §14.3's exit criterion with it.

    The addresses here are the mock's own, so this is the seed's row rather than an
    innocuous one: a green here says the development gate survived the event.
    """
    instance = a_platform_row(
        platform_model(),
        platform_table,
        platform_template,
        **{
            AUTHORIZATION_ENDPOINT: "http://localhost:8080/oidc/authorize",
            JWKS_URL: f"http://{MOCK_SERVICE}:8000/.well-known/jwks.json",
            AUTH_TOKEN_URL: f"http://{MOCK_SERVICE}:8000/token",
        },
    )
    db_session.info["environment"] = development_environment()

    escaped = written(db_session, instance)

    assert escaped is None, (
        f"Writing the development registration through the ORM raised {escaped!r}. Every rule is "
        "switched off under the development name — ADR 0081 — and this is the row the demo seed "
        "writes."
    )


def test_a_valid_registration_is_written_through_the_orm_under_a_deployment(
    db_session: Any, platform_template: Any, platform_table: Any
) -> None:
    """The second control, and the one that stops the cheapest wrong event.

    An event that raised whenever the session was not a development one passes
    every refusal in this module and makes Pulse registrable nowhere. This is a
    real institution's registration — `https`, not the mock, globally routable —
    under a deployment's name, and it has to be written.
    """
    instance = a_platform_row(platform_model(), platform_table, platform_template)
    db_session.info["environment"] = PRODUCTION

    escaped = written(db_session, instance)

    assert escaped is None, (
        f"Writing a valid deployment registration through the ORM raised {escaped!r}. The three "
        f"addresses were {A_VALID_REGISTRATION}, which every rule accepts."
    )


# ---------------------------------------------------------------------------
# The event itself. Expected red until it exists.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spelling", sorted(REFUSED_JWKS_URLS))
def test_a_refused_registration_is_refused_at_the_flush_under_a_deployment(
    db_session: Any, platform_template: Any, platform_table: Any, spelling: str
) -> None:
    """The item: the rules fire on a writer that never called them.

    This is what E11's console will be if the chokepoint stays a call convention —
    a piece of code that builds the model and flushes the session, with no import
    of `refuse_invalid_registration_addresses` anywhere in it. Nothing about that
    writer is wrong; the guarantee is simply not one the system makes.

    **Two vectors, one per rule, so a green cannot be misattributed.** The mock's
    Compose host is rule 2 and reaches the address before anything is resolved:
    ADR 0038's fourth property is that a production Pulse holds no row naming that
    issuer, and ADR 0068 moved the boundary from "no such row exists in this
    repository" to "no run permitted to write it can start" — this event is the
    layer that holds when both are bypassed. The private literal is rule 5, the
    class the cleanup batch adds, and it is the one a writer reaches through a form
    rather than through a copied development value.

    The other two columns carry a valid deployment registration, so exactly one
    thing in the row is refusable (`docs/MISTAKES.md` entry 3).

    **The mutation this kills**: the event registered for `before_insert` and not
    for the mapper at all — that is, the rules left as a call convention, which is
    HEAD.
    """
    instance = a_platform_row(
        platform_model(),
        platform_table,
        platform_template,
        **{JWKS_URL: REFUSED_JWKS_URLS[spelling]},
    )
    db_session.info["environment"] = PRODUCTION

    refused = refusal(
        db_session,
        instance,
        f"An `lti_platform` row whose `jwks_url` names {spelling}",
    )

    assert JWKS_URL in str(refused).lower(), (
        f"The refusal does not name `{JWKS_URL}`: {str(refused)!r}. Whoever reads this — a seed's "
        "stderr, a container log, later a rendered console page — has to learn which of three "
        "columns carried the refused address."
    )
    assert REFUSED_JWKS_URLS[spelling] not in str(refused), (
        f"The refusal quotes the address back: {str(refused)!r}. ADR 0056's house rule, and it "
        "applies with more force through an event, whose message reaches a log stream nobody "
        "chose."
    )


def test_a_session_that_states_no_environment_is_judged_as_a_deployment(
    db_session: Any, platform_template: Any, platform_table: Any
) -> None:
    """Fail closed: a writer that says nothing about where it is gets the strict rules.

    The direction is the whole decision. A session with no stated environment is
    every writer nobody has thought about yet — a script somebody runs once, a
    migration helper, a console built in another epic — and the two ways to read it
    are not symmetrical. Read as development, an unstamped writer may register the
    mock platform in production and nothing anywhere notices. Read as a deployment,
    a legitimate development writer is refused loudly, on its first run, with a
    message naming the column, and the repair is one line where the session is
    built.

    **The mutation this kills**: `session.info.get("environment", DEVELOPMENT)`, or
    an event that skips its work when it cannot find an environment — both of
    which pass every other test in this module, because every other test states
    one.

    **Its pair** is the development control above, where a session that *does*
    state development writes the mock's own addresses.
    """
    instance = a_platform_row(
        platform_model(),
        platform_table,
        platform_template,
        **{JWKS_URL: A_MOCK_ADDRESS},
    )
    db_session.info.pop("environment", None)

    refusal(
        db_session,
        instance,
        "An `lti_platform` row written through a session that states no environment",
    )


def test_an_address_flipped_to_a_refused_value_is_refused_at_the_update(
    db_session: Any, platform_template: Any, platform_table: Any
) -> None:
    """`before_update` too, because a registration is edited more often than it is created.

    An insert-only event guards the first write and nothing after it. The console
    E11 builds is an *edit* surface — an administrator fixes a typo in a key set
    address, or repoints a platform after a migration — so the update path is
    where a bad address most plausibly arrives, and it is the path an event
    registered for `before_insert` alone leaves wide open.

    Written valid first, under a deployment, and then flipped: so the row exists
    and is persistent when the update fires, which is the state a real edit is made
    in and the only state `before_update` runs for.

    **The mutation this kills**: `@event.listens_for(LtiPlatform, "before_insert")`
    with no `before_update` beside it — which passes every other refusal in this
    module. **Its pair** is the next test, where an update that leaves the
    addresses valid is written.
    """
    model = platform_model()
    instance = a_platform_row(model, platform_table, platform_template)
    db_session.info["environment"] = PRODUCTION
    assert written(db_session, instance) is None, (
        "The valid registration could not be inserted, so there is no persistent row to update "
        "and this test would be asserting `before_insert` a second time."
    )

    setattr(instance, attribute_names(model)[JWKS_URL], A_PRIVATE_ADDRESS_URL)

    refusal(
        db_session,
        instance,
        "An `lti_platform` row whose `jwks_url` was edited to an address that resolves privately",
    )


def test_an_update_that_leaves_every_address_valid_is_written(
    db_session: Any, platform_template: Any, platform_table: Any
) -> None:
    """The pair: editing a registration is an ordinary thing to do.

    Without this row, the update refusal above is satisfied by an event that
    refuses every update — which would make a registration unmaintainable and
    which no refusal test would notice. The address moves to a second valid one
    rather than staying put, so the event has something to judge rather than a
    no-op flush.
    """
    model = platform_model()
    instance = a_platform_row(model, platform_table, platform_template)
    db_session.info["environment"] = PRODUCTION
    assert (
        written(db_session, instance) is None
    ), "The valid registration could not be inserted, so there is nothing here to update."

    setattr(
        instance,
        attribute_names(model)[JWKS_URL],
        f"https://{A_GLOBAL_ADDRESS}/.well-known/jwks-2.json",
    )

    escaped = written(db_session, instance)

    assert escaped is None, (
        f"Editing a registration's key set address to another valid one raised {escaped!r}. The "
        "console this event exists for is an edit surface before it is anything else."
    )
