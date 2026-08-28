"""The rows that say who a subject is, and the session claim that carries it — E1-12.

E1-12 makes a verified subject resolve to a stored identity: the launch door
through `user.lms_user_id`, the web door through a pre-provisioned linkage from
an IdP `(issuer, subject)` pair. Both are rows, both have to be **committed**
before a door can see them — every door in this suite is driven over HTTP against
an application that opens its own connection out of `DATABASE_URL` — and both are
seeded here rather than in each module that needs them, because four modules need
the same three rows (`docs/MISTAKES.md` entry 13).

**What this seeds and what it deliberately refuses to decide.** `WebIdentityRows`
writes `person` rows, `user` rows and `web_login_subject` linkage rows, and nothing
else — no `role_assignment`. Tests that need an assignment build it through
`committed_rows.graph`, in the open, where the assertion can see it, and that is
unchanged: which assignment a person holds is what decides their view, so a
fixture that chose one would be answering the question under test
(`docs/MISTAKES.md` entry 30).

**E1-13 decided the question this paragraph used to say was open, and one fixture
below moved with it.** Until that ticket the landing came from the roles claim and
an assignment changed nothing; from E1-13 on it comes from the assignment model,
so a person with a linkage and no assignment lands on the calm no-access page.
`link_published_people` therefore writes the assignments the provider's own
registration document says each published person holds, because its whole job is
to stand up "a deployment whose people all have accounts" for suites whose subject
is not the landing. Its docstring says what that costs and where the rule it
mirrors is asserted in the open instead.

**The names below are the settled contract, not a guess.** The linkage table is
`web_login_subject` with `idp_issuer`, `idp_subject` and `person_id`; the session
gains `person_id` and `user_id`; the unlinked web login lands on a page carrying
`data-testid="no-account"`. Each was settled before any test was written, so a
disagreement with the implementation is a dispute rather than a rename to
accommodate here — and a name that turns out to be wrong is one line in this file.

**The environment these run under** (`docs/MISTAKES.md` entry 40): everything here
rides `committed_rows`, which rides `migrated_engine` and therefore
`migrated_database` — the testcontainers Postgres, migrated in process with the
whole process environment snapshotted and restored around the upgrade. Nothing
here reads `os.environ` and nothing here sets it; the doors these rows are read
through state their own environment through `tool_doors`.

**Teardown is `committed_rows`'s diff-delete**, so a row written here — or written
by the application on its own connection while a test runs — is removed when the
test ends, whichever connection wrote it.
"""

import base64
import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

from fixtures.supervision import (
    ROLE_SCOPE_GRAIN,
    foreign_key_columns,
    require_table,
    seed_row,
    single_primary_key,
)

# ---------------------------------------------------------------------------
# The linkage table, as E1-12 settles it.
# ---------------------------------------------------------------------------

# The table the web door resolves through, and its three columns. ADR 0024 puts
# the person→user link on `person`; nothing in this schema carries an IdP subject
# at all before this ticket, so the table and its columns are new and are named
# here once. `idp_issuer` and `idp_subject` together are one subject at one
# provider — the only pair an `id_token` identifies anybody by — and `person_id`
# is the identity it resolves to.
LINKAGE_TABLE = "web_login_subject"
LINKAGE_ISSUER_COLUMN = "idp_issuer"
LINKAGE_SUBJECT_COLUMN = "idp_subject"
LINKAGE_PERSON_COLUMN = "person_id"

# The two columns a launch resolves a subject through. `user.lms_user_id` is the
# `sub` claim verbatim (ADR 0045, ADR 0014's `lms_` ownership marker), and
# `lti_platform_id` is the registration it was issued under — a subject means
# nothing outside the platform that issued it, which is why both are written.
USER_TABLE = "user"
USER_SUBJECT_COLUMN = "lms_user_id"

# The Pulse-owned side. ADR 0024: "`person.user_id` — nullable, unique, foreign
# key to `user.id`". The link is what makes a launch subject reach a person.
PERSON_TABLE = "person"
PERSON_USER_COLUMN = "user_id"

# Where a stored identity's address lives. ADR 0001: "`user` holds the key and
# platform reference; `user_identity` holds name and email." Only the anti-pattern
# test writes here — an address stored in Pulse that equals the one a provider
# asserts is the collision E1-12's design has to refuse to merge on.
IDENTITY_TABLE = "user_identity"
IDENTITY_EMAIL_COLUMN = "identity_email"

# ---------------------------------------------------------------------------
# What a session says about who is signed in.
# ---------------------------------------------------------------------------

# The two claims E1-12 adds to `SessionClaims`. `person_id` is the stored identity
# — the `person` row's primary key, or absent where there is none (a student: ADR
# 0028 gives a student a `user` row and no assignment, and D1 makes "no person" a
# defined session-carried state rather than an error). `user_id` is the launch-side
# row, which the web door leaves unset.
PERSON_ID_CLAIM = "person_id"
USER_ID_CLAIM = "user_id"

# E1-08's own claims, used here only as the control on the reader below: a token
# these are missing from is one this decoder has misread, whatever it says about
# `person_id`.
E1_08_SESSION_CLAIMS = ("door", "role", "sub", "jti", "iat", "exp")

# Where a landing hands the browser its session (E1-08's interface ruling, adopted
# unchanged by E1-09): `302` to `/app/<segment>#session=<token>`.
SESSION_FRAGMENT = "#session="

# The calm page an unlinked web login lands on. Not one of the five landing
# testids and not the cancel page: three distinguishable answers, because "the IdP
# signed somebody in that Pulse has no record of" is a different event from "the
# person cancelled" and from "this tool refuses your token".
NO_ACCOUNT_TESTID = "no-account"


# How the mock provider's registration document names a published person's
# subject. **Measured, not guessed**, and it is deliberately not what the seed's
# own dataclass calls it: `mock-idp/app/seed.py` holds the value on
# `MockPerson.subject`, and what the document — and the login form, and the
# `id_token` — carries is `sub` (`mock-idp/app/pages.py::IDENTITY_FIELD`,
# `mock-idp/app/flow.py`). Reading it as `subject` is a `KeyError` and reading it
# with `.get("subject")` is a silent `None`; both happened in this ticket's first
# test round, and the second is the one that would have seeded a linkage for
# nobody and left five tests green about it.
#
# Two spellings, because both name the same person and the seed's own word is the
# one a reader of that file would reach for first. Neither present is a named
# failure rather than a fallback: `published_subject_of` fails, it does not guess.
PUBLISHED_SUBJECT_MEMBERS = ("sub", "subject")


def published_subject_of(person: Mapping[str, Any]) -> str:
    """The `sub` of one person the registration document publishes, or a loud failure.

    One reader for a name this suite does not own (`docs/MISTAKES.md` entry 13):
    six call sites across two test modules and this file's own linkage seeder asked
    the same question, and each copy of the answer was a place to get it wrong.
    """
    for member in PUBLISHED_SUBJECT_MEMBERS:
        value = person.get(member)
        if isinstance(value, str) and value:
            return value
    pytest.fail(
        f"The registration document publishes {person!r} under none of "
        f"{list(PUBLISHED_SUBJECT_MEMBERS)}. That value is half of the pair E1-12 resolves a web "
        "login by — the other half is the issuer — so without it there is no linkage to write and "
        "no subject to sign in as. ADR 0058 makes the seeded people part of that document; if the "
        "member has been renamed again, this tuple in tests/fixtures/web_identity.py is the "
        "one-line change."
    )


def claims_in_session(token: str) -> dict[str, Any]:
    """The claim set of a session token, decoded and not verified.

    Decoded rather than verified because no test module in this suite is handed
    `SESSION_SECRET`, and both door suites already read a session this way — a
    confidentiality scan does not need a signature checked to read what anybody
    intercepting the redirect could read. `tests/unit/test_session_module.py` is
    where the signature is the subject.

    Fails loudly on anything that is not a three-segment JWS whose payload is a
    JSON object: a decoder that quietly answered `{}` would make every assertion
    below it — "the two doors carry the same `person_id`" among them — true of a
    token carrying nothing at all (`docs/MISTAKES.md` entry 3).
    """
    parts = token.split(".")
    assert len(parts) == 3, (
        f"{token[:80]!r} is not a compact JWS (three dot-separated segments), so it carries no "
        "claim set and every assertion about what the session says would be about an empty dict."
    )
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
    try:
        claims = json.loads(decoded)
    except ValueError as broken:
        pytest.fail(
            f"A session token's payload does not decode to JSON ({broken}); it decodes to "
            f"{decoded[:200]!r}. Nothing read out of it afterwards would mean anything."
        )
    assert isinstance(claims, dict), (
        f"A session token's payload decoded to {type(claims).__name__}, not to a JSON object: "
        f"{decoded[:200]!r}."
    )
    return claims


def session_token_in(response: Any, what: str) -> str:
    """The session token a landing redirect hands the browser, or a failure saying why not.

    Deliberately says nothing about *which* route the redirect names. Which view a
    person lands on is E1-13's subject and E1-12 changes none of it, so a helper
    that pinned the segment here would make every identity assertion in this ticket
    fail on somebody else's rule.
    """
    assert response.status_code in (302, 303, 307), (
        f"{what} answered {response.status_code} rather than the redirect a door issues for a "
        f"session it minted. Body begins {response.text[:400]!r}."
    )
    location = response.headers.get("location") or ""
    assert SESSION_FRAGMENT in location, (
        f"{what} redirected to `{location}`, which carries no `{SESSION_FRAGMENT}` fragment. "
        "E1-08's interface ruling: a landing is a 302 whose `Location` is "
        "`/app/<segment>#session=<token>`, and the token is what carries the identity this "
        "ticket resolves."
    )
    token = location.split(SESSION_FRAGMENT, 1)[1]
    assert token, f"{what} redirected to `{location}`, whose `session=` fragment is empty."
    return token


def session_claims_of(response: Any, what: str) -> dict[str, Any]:
    """One landing's session claims, off the fragment its redirect carries."""
    return claims_in_session(session_token_in(response, what))


class WebIdentityRows:
    """The three rows an identity is made of, seeded committed, one call each.

    **Nothing here composes them for the caller**, and that is the point rather
    than an omission. "The two doors resolve to one person" is the property under
    test, so a fixture that built a two-hat person in one call would be supplying
    the answer and the test would be reading it back (`docs/MISTAKES.md` entry 30).
    Each test writes the rows it means, in the order it means, and says what it
    expects to fall out.

    Every method commits, because the tool reads on its own connection.
    """

    def __init__(self, rows: Any, tables: dict[str, Any]) -> None:
        self.rows = rows
        self.tables = tables

    # -- reaching the columns -------------------------------------------------

    def key_of(self, table_name: str) -> str:
        """One table's single primary key column (ADR 0016 makes every key one uuid)."""
        return single_primary_key(require_table(self.tables, table_name))

    def platform_column(self) -> str:
        """The column on `user` whose foreign key points at a registration.

        Followed rather than named: a `row.get("lti_platform_id")` that answers
        `None` for every row makes a seeded user belong to no platform, and a
        launch would then resolve nobody while this fixture reported success.
        """
        found = foreign_key_columns(require_table(self.tables, USER_TABLE), "lti_platform")
        if len(found) != 1:
            pytest.fail(
                f"`{USER_TABLE}` has {len(found)} foreign keys to `lti_platform` ({found}). ADR "
                "0001 puts the platform reference on `user` beside the key, and a subject means "
                "nothing outside the registration that issued it."
            )
        return found[0]

    # -- the rows themselves --------------------------------------------------

    def person(self, **overrides: Any) -> Any:
        """One `person` row's primary key. ADR 0024 leaves `user_id` nullable and unset."""
        row = seed_row(self.rows.session, self.tables, PERSON_TABLE, {}, **overrides)
        self.rows.commit()
        return row[self.key_of(PERSON_TABLE)]

    def user(self, *, platform_id: Any, subject: str) -> Any:
        """One `user` row for one subject at one registration, and its primary key.

        This is the row E1-10's launch door writes for itself on every verified
        launch; seeding it ahead of a launch is what D7's seed does for the mock
        world, and ADR 0091 says the launch-time insert tolerates a row that is
        already there.
        """
        row = seed_row(
            self.rows.session,
            self.tables,
            USER_TABLE,
            {},
            **{self.platform_column(): platform_id, USER_SUBJECT_COLUMN: subject},
        )
        self.rows.commit()
        return row[self.key_of(USER_TABLE)]

    def stored_identity(self, *, user_id: Any, email: str, **overrides: Any) -> Any:
        """One `user_identity` row carrying a chosen address (ADR 0001 puts it there).

        For the one question this ticket has to answer out loud: an address stored
        in Pulse that equals the address a provider asserts must not merge the two.
        The seeding runs as the bootstrap identity, which is the only role that may
        write this table at all — `pulse_app` holds no privilege on it of any kind,
        which is ADR 0001's whole scheme and is asserted at length in
        `tests/integration/test_identity_grants.py`.
        """
        row = seed_row(
            self.rows.session,
            self.tables,
            IDENTITY_TABLE,
            {},
            **{
                foreign_key_columns(require_table(self.tables, IDENTITY_TABLE), USER_TABLE)[0]: (
                    user_id
                ),
                IDENTITY_EMAIL_COLUMN: email,
                **overrides,
            },
        )
        self.rows.commit()
        return row

    def link_person_to_user(self, *, person_id: Any, user_id: Any) -> None:
        """Point `person.user_id` at a `user` row (ADR 0024's direction, and the only one)."""
        table = require_table(self.tables, PERSON_TABLE)
        key = self.key_of(PERSON_TABLE)
        self.rows.session.execute(
            table.update().where(table.c[key] == person_id).values(**{PERSON_USER_COLUMN: user_id})
        )
        self.rows.commit()

    def link_web_subject(self, *, issuer: str, subject: str, person_id: Any) -> Any:
        """One `web_login_subject` row: this IdP subject *is* this person.

        The row an administrator or the seed provisions ahead of a first web login.
        Nothing infers it — E1-12's bounding constraint is that a merge is never
        inferred from a mutable claim — so a subject with no row here is a subject
        this system has no record of, which is D5's defined state and not an error.
        """
        row = seed_row(
            self.rows.session,
            self.tables,
            LINKAGE_TABLE,
            {},
            **{
                LINKAGE_ISSUER_COLUMN: issuer,
                LINKAGE_SUBJECT_COLUMN: subject,
                LINKAGE_PERSON_COLUMN: person_id,
            },
        )
        self.rows.commit()
        return row

    # -- reading back ---------------------------------------------------------

    def rows_of(self, table_name: str) -> list[Any]:
        """Every row of one table, read after ending this session's transaction.

        The transaction is ended first for the reason `ProvisionedRows` gives: this
        connection has been open since it seeded, and what a door wrote was
        committed on another one, so a read inside the old snapshot reports
        "unchanged" whatever happened.
        """
        table = require_table(self.tables, table_name)
        self.rows.session.rollback()
        return list(self.rows.session.execute(table.select()).mappings())

    def linkages(self) -> list[Any]:
        """Every `web_login_subject` row there is."""
        return self.rows_of(LINKAGE_TABLE)

    def keys_of(self, table_name: str) -> set[Any]:
        """The primary key of every row in one table, right now.

        Sets of keys rather than counts, so "no identity row was created" is a
        statement about *which* rows exist. A count is equally satisfied by a door
        that created one row and deleted another.
        """
        key = self.key_of(table_name)
        return {row[key] for row in self.rows_of(table_name)}


@pytest.fixture
def web_identity(committed_rows: Any, metadata_tables: dict[str, Any]) -> WebIdentityRows:
    """The rows an identity is made of, seeded committed and removed at teardown."""
    return WebIdentityRows(committed_rows, metadata_tables)


@pytest.fixture
def link_published_people(
    web_identity: WebIdentityRows, committed_rows: Any
) -> Callable[[Any], dict[str, Any]]:
    """Give every person a mock provider publishes a Pulse identity, and the roles it publishes.

    **This exists because E1-12 changes what a successful web login requires**, and
    the modules that meet the change are ones this ticket does not otherwise edit
    (`docs/MISTAKES.md` entry 22). Before E1-12 a verified `id_token` was enough to
    land; from E1-12 on a subject with no linkage row lands on the no-account page,
    so every web login in `tests/integration/test_web_login_door.py` — the dean, the
    Care office, the administrator, the cookie attributes, the login hints, the
    re-signed sessions — would answer 200 with a calm page instead of a session, in
    tests whose subject is none of that.

    So the linkage is provisioned for **everybody the provider publishes**, which is
    what a deployment whose people all have accounts looks like. It is applied where
    that suite builds its provider, so no test there has to know this exists.

    A person per subject, and no two subjects sharing one — the near miss this
    fixture must not stand up is exactly the one AC2 is about, so a suite using it
    cannot accidentally prove "everybody resolves to one row". Returns the mapping
    from subject to `person.id`, so a caller can say which person it expects.

    **Before the linkage table exists it seeds nothing and says so by returning an
    empty mapping**, which is deliberate and is the one piece of tolerance in this
    file. These tests are written before the implementation, and a fixture that
    failed on the absent table would turn E1-09's whole module into errors in
    setup — fifty-odd tests reported as broken rather than one ticket reported as
    unbuilt, which is noise a reviewer has to see past on every run of the red
    phase. E1-09's door lands everybody while the table is absent, so seeding
    nothing is exactly right for that state.

    It is not a hole once the table lands: `web_login_subject` is asserted to exist,
    by name and by the sweep it has to join, in
    `tests/integration/test_identity_column_marker.py`. So a table under a different
    name is a named failure there rather than a silent no-op here.

    **E1-13 makes it write the assignments too, and for exactly the same reason.**
    That ticket resolves the landing from the assignment model, so a person with a
    linkage and no assignment lands on the calm no-access page — and every web
    login in `test_web_login_door.py` would answer 200 with that page instead of a
    session, in tests about PKCE, nonces, cookies and login hints. So each
    published person is given the assignments the registration document says they
    hold: their `roles`, which are what a session for them states, plus their
    `launch_only_roles`, which is what the two-hat person holds on the other door
    (ADR 0058 makes both members part of the published contract). That is what a
    seeded deployment looks like — `scripts/seed.py` writes the same shape for the
    running stack — and the roles come from the document rather than from a list
    here, so a reseeding moves the assignments with it.

    **What that costs, stated rather than implied.** A suite using this fixture
    cannot prove *that* the landing comes from the assignment, because the fixture
    is what put the assignment there. It is not asked to: the rule is asserted in
    the open, over rows each test writes itself, in
    `tests/integration/test_landing_resolves_from_assignments.py`. What a suite
    using this fixture proves is everything else about a door, over a deployment
    where the people have accounts and roles — which is the only state in which
    those questions can be asked at all.

    Assignments are written only where the graph can express the role's scope
    grain, and a role it cannot place is skipped rather than guessed at: the scope
    a role attaches to is SPEC §2.1's decision, and inventing one here would seed a
    row the schema's grain rule may refuse and fail a test inside its own fixture
    (`docs/MISTAKES.md` entry 13).
    """

    def assignments_for(person_id: Any, user: Mapping[str, Any]) -> None:
        """Every role the document publishes for this person, as a live assignment.

        Each row gets a scope node of its own through `fresh_scope`, which shares
        every ancestor above the role's grain and builds the node itself again.
        Two people holding the same role at the same node is a shape the schema may
        refuse — `SupervisionGraph.node` names "one chair per department, one
        instructor per section" as rules E0-09's ticket does not mention and the
        schema may still carry — and a fixture that tripped one would fail a suite
        inside its own setup for a reason no test there is about. The institution
        is the exception and cannot be duplicated (`uq_institution_one_row`, ADR
        0072); `fresh_scope` hands back the one that is already there.

        `reports_to` is explicitly null. Supervision edges are §2.1's own subject
        and are asserted in `tests/integration/test_role_assignment_graph.py`; what
        a door needs is a live assignment, and a graph invented here would be this
        fixture deciding who answers to whom.
        """
        published = [
            *(user.get("roles") or []),
            *(user.get("launch_only_roles") or []),
        ]
        for role in published:
            token = str(role).upper()
            if token not in ROLE_SCOPE_GRAIN:
                continue
            committed_rows.graph.assign(
                token,
                scope=committed_rows.graph.fresh_scope(ROLE_SCOPE_GRAIN[token]),
                person=person_id,
                reports_to=None,
            )
        committed_rows.commit()

    def link(provider: Any) -> dict[str, Any]:
        if LINKAGE_TABLE not in web_identity.tables:
            return {}
        issuer = provider.discovery().get("issuer")
        assert isinstance(issuer, str) and issuer, (
            "The provider's discovery document advertises no `issuer` (it carries "
            f"{sorted(provider.discovery())}), so there is no issuer half of a linkage to write "
            "and every web login through it would land on the no-account page."
        )
        linked: dict[str, Any] = {}
        for user in provider.published_users():
            subject = published_subject_of(user)
            person_id = web_identity.person()
            web_identity.link_web_subject(issuer=issuer, subject=subject, person_id=person_id)
            assignments_for(person_id, user)
            linked[subject] = person_id
        assert len(set(linked.values())) == len(linked), (
            f"Two of the {len(linked)} published subjects were linked to one person: {linked}. "
            "That is the state AC2's near miss is written against, and a suite built on it would "
            "prove nothing about a merge."
        )
        return linked

    return link


@pytest.fixture
def published_person() -> Callable[..., Mapping[str, Any]]:
    """One seeded provider person, chosen by the role the registration document gives them.

    Read off `/mock/registration` (ADR 0058) rather than transcribed, so nothing
    here is a copy of `mock-idp/app/seed.py` and a reseeding cannot leave a test
    quietly asserting over somebody who is no longer there.

    `and_a_launch_assignment` distinguishes the two people who hold Care — the
    office, and the person who also teaches, who is the two-hat person this
    ticket's first criterion is about.
    """

    def find(provider: Any, role: str, *, and_a_launch_assignment: bool = False) -> Any:
        found = [
            user
            for user in provider.published_users()
            if role in (user.get("roles") or [])
            and bool(user.get("launch_only_roles")) == and_a_launch_assignment
        ]
        assert len(found) == 1, (
            f"The registration document publishes {len(found)} people holding {role!r} with "
            f"launch_only_roles {'set' if and_a_launch_assignment else 'empty'}; this asks for "
            "one. It publishes "
            f"{[published_subject_of(user) for user in provider.published_users()]}."
        )
        return found[0]

    return find


@pytest.fixture
def published_subject() -> Callable[[Mapping[str, Any]], str]:
    """`published_subject_of`, for a test module that may not import this one.

    A fixture rather than a constant a test module copies, because the member name
    belongs to the mock's registration document and not to this ticket: the
    document is where it is discovered, one reader answers for every caller, and a
    rename is one line here rather than six across two modules.
    """
    return published_subject_of


# ---------------------------------------------------------------------------
# Driving the web door, for the modules whose subject is who a login resolves to.
# ---------------------------------------------------------------------------

# The mock provider's configuration surface, from `mock-idp/app/config.py`. The
# redirect URI is compared exactly, on the way in and again at the token endpoint,
# so this and the tool's `PUBLIC_BASE_URL` have to be one address or no flow
# completes at all.
MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE = "MOCK_IDP_TOOL_REDIRECT_URI"

# Where the tool sends a browser to begin a web login. Chosen so that no
# implementation could arrive at it by accident — a redirect derived from the
# issuer would agree with the real provider and disagree with this. `.invalid` is
# reserved by RFC 2606. Nothing in these modules asserts about it; it is here
# because the setting is required and this suite's flows never follow it.
CONFIGURED_AUTHORIZATION_ENDPOINT = "http://identity-provider.invalid/e1-12-configured-authorize"


class WebDoor:
    """One tool, one mock provider, and whole web logins through both.

    A second copy of "how a login reaches this door" would be a second thing to fix
    when the door changes, and the door has changed under E1-09 already
    (`docs/MISTAKES.md` entry 13). `tests/integration/test_web_login_door.py` keeps
    its own copy deliberately — that module's subject *is* the flow, and it drives
    parts of it this class does not expose.

    Nothing here seeds a linkage. Which subjects have identities is the subject of
    every test using this, so the driver must not decide it.
    """

    def __init__(self, tool: Any, contract: Any, provider: Any) -> None:
        self.tool = tool
        self.contract = contract
        self.provider = provider

    def begin(self) -> dict[str, str]:
        """Start a login and read the authorization request the tool built."""
        response = self.tool.get(self.contract.oidc_login)
        assert response.status_code in (302, 303, 307), (
            f"`GET {self.contract.oidc_login}` answered {response.status_code} rather than a "
            f"redirect to the provider. Body begins {response.text[:300]!r}."
        )
        location = response.headers.get("location") or ""
        assert location, f"`GET {self.contract.oidc_login}` answered with no `Location`."
        return dict(parse_qsl(urlsplit(location).query))

    def sign_in(self, person: Mapping[str, Any]) -> Any:
        """Carry the tool's authorization request to the provider and sign in as `person`."""
        parameters = self.begin()
        attempt = self.provider.begin_from(list(parameters.items()), "")
        submitted = self.provider.submit_login(attempt, self.provider.identity_of(person, attempt))
        # The subject is looked up leniently *here only*, because this is a failure
        # message: `published_subject_of` fails when it finds nothing, and a message
        # that raises replaces the diagnosis with its own.
        whoever = next(
            (person.get(member) for member in PUBLISHED_SUBJECT_MEMBERS if person.get(member)),
            person,
        )
        assert submitted.code, (
            f"The provider issued no authorization code for {whoever!r}: it answered "
            f"{submitted.response.status_code} and sent {submitted.location!r}. E0-16's own suite "
            "asserts this flow completes, so a failure here is this driver misusing the provider "
            "rather than a defect in the tool."
        )
        return submitted

    def login_as(self, person: Mapping[str, Any]) -> Any:
        """One whole web login, from `/auth/oidc/login` to whatever the callback answers."""
        submitted = self.sign_in(person)
        return self.tool.get(
            self.contract.oidc_callback,
            params={"code": submitted.code, "state": submitted.state},
        )


@pytest.fixture
def identity_provider(mock_idps: Any, door_contract: Any) -> Any:
    """The mock provider, registered to return to this tool's own callback."""
    return mock_idps(
        {
            MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.oidc_callback}"
            )
        }
    )


@pytest.fixture
def provider_issuer(identity_provider: Any) -> str:
    """The issuer half of every linkage these modules write, out of the discovery document.

    Read from the document rather than written down, so the string a linkage row
    carries and the string an `id_token` states cannot become two values — which
    would leave every web login landing on the no-account page for a reason no
    assertion here is about.
    """
    issuer = identity_provider.discovery().get("issuer")
    assert isinstance(issuer, str) and issuer, (
        "The provider's discovery document advertises no `issuer` (it carries "
        f"{sorted(identity_provider.discovery())}). That is half of the pair E1-12 resolves a web "
        "subject by, and without it no linkage can be written."
    )
    return issuer


@pytest.fixture
def web_door(
    tool_doors: Any,
    door_contract: Any,
    identity_provider: Any,
    deployed_identity_provider: dict[str, str],
) -> WebDoor:
    """This project's web door, configured for the running mock provider.

    Every OIDC endpoint comes out of the provider's discovery document, which is how
    a client learns them; the host in those addresses is also what routes the tool's
    server-side calls back into the in-process provider, so a door that fetched from
    anywhere else reaches no mock and says so.

    **The environment is `configured_env`'s** — the development name, laid down by
    `tool_doors` before the application is imported (`docs/MISTAKES.md` entry 40).
    Every flow here redeems a code at the mock, and E0-39 refuses the mock's own
    addresses outside development; `deployed_identity_provider` is depended on only
    so `tool_doors` behaves the same way it does for the door suites, and its
    placeholder values are overwritten below.
    """
    document = identity_provider.discovery()
    names = door_contract.settings

    def endpoint(member: str) -> str:
        value = document.get(member)
        assert isinstance(value, str) and value, (
            f"The provider's discovery document advertises no `{member}` (it carries "
            f"{sorted(document)}). That member is how a client configures itself."
        )
        return value

    values = {
        names["public_base_url"]: door_contract.public_base_url,
        names["oidc_issuer"]: endpoint("issuer"),
        names["oidc_authorization_endpoint"]: CONFIGURED_AUTHORIZATION_ENDPOINT,
        names["oidc_token_endpoint"]: endpoint("token_endpoint"),
        names["oidc_jwks_url"]: endpoint("jwks_uri"),
        names["oidc_client_id"]: identity_provider.registration()["client_id"],
    }
    host = urlsplit(endpoint("token_endpoint")).hostname
    tool = tool_doors(values, {host: identity_provider})
    return WebDoor(tool, door_contract, identity_provider)
