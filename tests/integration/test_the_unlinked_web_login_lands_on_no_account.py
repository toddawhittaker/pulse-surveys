"""A verified token is not a membership — ticket E1-12, acceptance criterion 3.

"An unlinked web subject gets the defined state and no identity row is created; the
forbidden state (auto-created identity) is asserted." The identity provider asserts
that somebody authenticated; it does not assert that Pulse has a record of them.
§2 puts every role in Pulse's own records, and E1-12's bounding constraint is that
a merge is never inferred from a mutable claim — so a subject with no
`web_login_subject` row is a person this system does not know, and the honest
answer is a calm page rather than an error and rather than an account.

**Both directions, always in pairs.** A door that answered the no-account page to
everybody would satisfy every "no row was written" assertion in this module
perfectly, so each refusal here sits beside the login that must land: same
provider, same flow, same environment, one difference — whether a linkage row
exists (`docs/MISTAKES.md` entry 3).

**The named anti-pattern is asserted directly.** The carried entry's "done when"
rules out "two rows that happen to agree on an email address", and the last test
here is that sentence made executable: a stored identity carrying exactly the
address the IdP asserts, and a login that must **not** become it. Email equality is
the merge nobody writes on purpose and everybody reaches for when a linkage is
missing; the failure it produces is a plausible answer for the wrong human, which
is the kind nothing downstream can detect.

**The environment** (`docs/MISTAKES.md` entry 40): the door is built by
`tool_doors` over `configured_env`, so `ENVIRONMENT` is the development name and
`DATABASE_URL` names the session-wide testcontainers Postgres before `app.main` is
imported. Rows are seeded committed through `tests/fixtures/web_identity.py` and
removed by `committed_rows`'s diff-delete at teardown, which also removes anything
the application wrote on its own connection — so a door that does provision leaves
a failure here rather than a row somebody else's non-vacuity guard trips over three
tickets from now.
"""

import base64
import json
from typing import Any

import pytest

pytestmark = pytest.mark.integration

# `web_door`, `identity_provider`, `provider_issuer`, `published_person` and
# `web_identity` come from `tests/fixtures/web_identity.py`, reached as fixtures
# rather than imported: an import of a fixtures module by name depends on where
# pytest put `tests/` on `sys.path`, and an import error is not a red.

# E1-12's calm page, by the testid E1-15's browser proof addresses it by (D5). It
# is neither one of the five landing testids nor the cancel page: three
# distinguishable answers, because "the IdP signed in somebody Pulse has no record
# of", "the person cancelled" and "this tool refuses your token" are three events
# and the person in front of the screen is owed different words for each.
NO_ACCOUNT_TESTID = "no-account"

# The session claim the identity rides in (D4).
PERSON_ID_CLAIM = "person_id"

# The tables an auto-created identity would appear in. `role_assignment` is here
# because it is the table E0-09's criterion 10 is about — "no OIDC claim may ever
# produce a `CARE` assignment" — and a door that provisioned an identity from a
# token is one step from provisioning what the token says that identity is.
IDENTITY_TABLES = ("person", "user", "web_login_subject", "role_assignment")

# A table the migration itself fills, so that "nothing was written" and "this
# reader is looking at an empty or unmigrated database" are different observations.
STAMPED_TABLE = "alembic_version"

# Where a stored identity's address lives (ADR 0001: `user_identity` holds name and
# email), and the column that holds it. Spelled here because the anti-pattern test
# has to stand up that exact collision — an address stored in Pulse that equals the
# one the provider asserts — and a discovered column would let the collision
# quietly not happen.
IDENTITY_TABLE = "user_identity"
IDENTITY_EMAIL_COLUMN = "identity_email"

# The two roles this module signs in as. Both hold the web door by §2's table; the
# Care office is the person with no launch assignment, the two-hat person has one.
CARE_ROLE = "CARE"
ADMIN_ROLE = "ADMIN"


def claims_of_session(response: Any, what: str) -> dict[str, Any]:
    """The session claims a landing hands the browser, decoded off its fragment.

    A copy of the reader in `test_dual_door_identity_merge.py` and in the fixtures
    module, for the reason this suite copies rather than imports across test
    modules. `test_the_reader_and_the_calm_page_check_both_fire` below is this
    module's control on it.
    """
    assert response.status_code in (302, 303, 307), (
        f"{what} answered {response.status_code} rather than a landing redirect. Body begins "
        f"{response.text[:400]!r}."
    )
    location = response.headers.get("location") or ""
    marker = "#session="
    assert marker in location, f"{what} redirected to `{location}`, which carries no `{marker}`."
    payload = location.split(marker, 1)[1].split(".")[1]
    decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode(
        "utf-8", "replace"
    )
    claims = json.loads(decoded)
    assert isinstance(claims, dict), f"{what}'s session payload is not a JSON object: {decoded!r}"
    return claims


def no_session_was_issued(response: Any, what: str) -> None:
    """Nothing in this response hands the caller a session. The forbidden state.

    Three ways a session could leave a door and all three are checked, because a
    door that stopped setting the cookies and went on redirecting with the fragment
    would satisfy a cookie-only check while handing the token over
    (`docs/MISTAKES.md` entry 2 — assert the forbidden state, and assert all of it).
    The cookie names are read out of the shared session module rather than
    transcribed, so this module and the door cannot end up meaning two different
    cookies.
    """
    try:
        from app.services.session import CSRF_COOKIE, SESSION_COOKIE
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`app.services.session` does not import ({missing}). E1-08's module layout names "
            "`SESSION_COOKIE`/`CSRF_COOKIE` there and E1-09 issues the web door's session through "
            "the same module."
        )
    names = {header.split("=", 1)[0].strip() for header in response.headers.get_list("set-cookie")}
    handed = sorted(names & {SESSION_COOKIE, CSRF_COOKIE})
    assert not handed, (
        f"The tool set {handed} while answering {what}. That is a session issued to a subject this "
        "system has no record of."
    )
    location = response.headers.get("location") or ""
    assert "session=" not in location, (
        f"The tool answered {what} with `Location: {location}`, which carries a session token in "
        "the URL."
    )
    assert "session=" not in response.text, (
        f"The body the tool answered {what} with carries `session=`. Body begins "
        f"{response.text[:400]!r}."
    )


def the_no_account_page(response: Any, contract: Any, what: str) -> None:
    """D5's defined state: a calm page, no session, and nobody's landing view.

    Distinct from a refusal in every respect a test can see — the status, the
    testid, and the fact that this is a page somebody is meant to read. Both halves
    are checked, because a door answering 4xx would be right about the words and
    wrong about the event, and a door answering 200 with a landing would be the
    reverse.
    """
    assert response.status_code == 200, (
        f"The tool answered {response.status_code} to {what}. D5 makes this the same mechanism, "
        "status and register as the cancelled login E1-09 built: HTTP 200, server-rendered, plain "
        f"words. Body begins {response.text[:400]!r}."
    )
    assert NO_ACCOUNT_TESTID in response.text, (
        f"The tool answered {what} with a 200 carrying no `{NO_ACCOUNT_TESTID}` testid (body "
        f"begins {response.text[:400]!r}). That testid is E1-12's contract for this page and it is "
        "what tells this suite — and E1-15's browser proof — that the person was met with the "
        "no-account copy rather than with somebody else's screen."
    )
    landings = [testid for testid in contract.landing_testids if testid in response.text]
    assert not landings, (
        f"The tool answered {what} with a page carrying {landings}. A subject with no stored "
        "identity lands on nobody's view."
    )
    no_session_was_issued(response, what)


def committed_row_count(engine: Any, table: str) -> int:
    """How many rows `table` holds right now, on a connection of its own.

    A connection per call on purpose: a reader holding one transaction open across
    the flow answers out of the snapshot it started in and reports "unchanged"
    whatever the door did.
    """
    from sqlalchemy import text

    query = text(f'SELECT count(*) FROM public."{table}"')  # noqa: S608
    with engine.connect() as connection:
        return int(connection.execute(query).scalar_one())


# ---------------------------------------------------------------------------
# The machinery, before anything is asserted with it. A must-be-green control:
# a red here means this module is broken, not that the door is.
# ---------------------------------------------------------------------------


def test_the_reader_and_the_calm_page_check_both_fire(
    door_contract: Any, configured_env: dict[str, str]
) -> None:
    """The control on both instruments: each finds what it looks for, and only that.

    **Dies if `the_no_account_page` passes a page that does not carry the testid**,
    which would make every refusal below true of a door that answers anything with a
    200 — and **dies if it accepts a landing testid beside it**, which is how a door
    that renders the wrong screen would slip past. Needs no implementation and is
    green today.

    `configured_env` is depended on and not used: `no_session_was_issued` imports
    `app.services.session` for the cookie names, and a module that builds anything
    out of `Settings` at import needs every documented variable to have a value
    (`docs/MISTAKES.md` entry 40 — a test states the environment it runs under).
    """

    class Page:
        status_code = 200
        text = f'<main data-testid="{NO_ACCOUNT_TESTID}">no account</main>'
        headers: Any = None

    class Headers:
        @staticmethod
        def get_list(_name: str) -> list[str]:
            return []

        @staticmethod
        def get(_name: str, default: Any = None) -> Any:
            return default

    page = Page()
    page.headers = Headers()
    the_no_account_page(page, door_contract, "a page this test built")

    landing = Page()
    landing.headers = Headers()
    landing.text = f'{page.text}<div data-testid="{door_contract.landing_testids[0]}"></div>'
    with pytest.raises(AssertionError):
        the_no_account_page(landing, door_contract, "a page carrying a landing view as well")


# ---------------------------------------------------------------------------
# Criterion 3, in both directions.
# ---------------------------------------------------------------------------


def test_a_web_login_by_a_linked_subject_lands_with_a_session_naming_its_person(
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The accepting half of the pair: a provisioned linkage is what opens this door.

    Without it, every no-account assertion in this module is equally true of a door
    that has stopped signing anybody in — and a door refused at the token endpoint,
    at the signature check or at the issuer comparison answers something the tests
    below would happily read as "no account" (`docs/MISTAKES.md` entry 3).

    **Dies if the linkage is not what decides.** The session has to name the very
    row the linkage points at, so a door that resolved by anything else — the first
    person in the table, a person it created — fails here rather than passing an
    "it landed somewhere" check.

    **The `ADMIN` assignment is E1-13's arrival in this module**
    (`docs/MISTAKES.md` entry 22). From that ticket the landing comes from the
    assignment model, so a person with a linkage and no assignment lands on the
    calm *no-access* page — which carries no session, and would make this half of
    the pair unstatable while looking like the door was broken. One row, written in
    the open, restores the difference the pair turns on: linkage and assignment
    against no linkage at all. Which view the assignment chooses is not this
    module's subject and is asserted in
    `tests/integration/test_landing_resolves_from_assignments.py`.
    """
    person = published_person(web_door.provider, ADMIN_ROLE)
    person_id = web_identity.person()
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(person), person_id=person_id
    )
    committed_rows.graph.assign(
        ADMIN_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.commit()

    response = web_door.login_as(person)

    claims = claims_of_session(response, "a linked subject's web login")
    assert claims.get(PERSON_ID_CLAIM) == str(person_id), (
        f"A linked subject's session carries `{PERSON_ID_CLAIM}` {claims.get(PERSON_ID_CLAIM)!r} "
        f"and the linkage row for {published_subject(person)!r} names {str(person_id)!r}. The "
        "claims are "
        f"{sorted(claims)}. E1-12 binds the session to the identity the linkage resolves to; "
        "anything else means the pre-provisioned linkage is not what decides who this is."
    )


def test_a_web_login_by_an_unlinked_subject_lands_on_the_no_account_page(
    web_door: Any, published_person: Any, published_subject: Any, door_contract: Any
) -> None:
    """The refusing half: a verified token whose subject nobody has provisioned.

    The token is good — this flow completes the whole authorization code exchange
    against the mock provider, and the door verified the `id_token` before it could
    know there was no linkage. What is missing is a record in Pulse, and §2 puts
    every role in Pulse's own records: "the IdP asserts authentication, not
    membership".

    **Dies if the door refuses with a 4xx**, which is fail-closed and is not what
    the person is owed — they have signed in correctly and are owed plain words.
    **Dies if the door signs them in anyway**, which is the auto-provisioning
    criterion 3 forbids, and `no_session_was_issued` checks all three routes a
    session could take out of this response.

    Nothing is linked for this subject in this test, which is the whole of the
    difference from the test above.
    """
    person = published_person(web_door.provider, ADMIN_ROLE)

    response = web_door.login_as(person)

    the_no_account_page(
        response,
        door_contract,
        f"a verified login by the unlinked subject {published_subject(person)!r}",
    )


@pytest.mark.invariant
def test_an_unlinked_web_login_creates_no_identity_row_of_any_kind(
    web_door: Any,
    published_person: Any,
    published_subject: Any,
    door_contract: Any,
    web_identity: Any,
    migrated_engine: Any,
) -> None:
    """The forbidden state, asserted as a state rather than inferred from the page.

    Criterion 3 names it: "no identity row is created; the forbidden state
    (auto-created identity) is asserted". A door that rendered the no-account page
    *and* provisioned the person behind it would pass every other test in this
    module — the page is right, the session is absent — while a subject the IdP
    signed in has become a `person` row in Pulse, which is a role-bearing record
    (§2.1) created by whoever administers the identity provider.

    **Asserted on the set of primary keys, not on a count.** A count is equally
    satisfied by a door that wrote one row and removed another, and the key set says
    *which* rows are new.

    **Its control is the page itself.** Reaching the no-account page proves the
    token verified and the door ran — a flow that failed earlier would write nothing
    for reasons this test is not about — and the stamped table proves the reader is
    looking at the migrated database rather than at an empty one.

    `role_assignment` is counted with the three identity tables because E0-09's
    criterion 10 is the rule underneath this one: "no OIDC claim may ever produce a
    `CARE` assignment", and a door willing to invent a person from a token is one
    step from inventing what the token says that person is.
    """
    stamped = committed_row_count(migrated_engine, STAMPED_TABLE)
    assert stamped >= 1, (
        f"`public.{STAMPED_TABLE}` holds {stamped} rows, so this reader is looking at a database "
        "nothing has migrated and would report every table below as empty and unchanged whatever "
        "the door wrote."
    )
    person = published_person(web_door.provider, CARE_ROLE)
    before = {name: web_identity.keys_of(name) for name in IDENTITY_TABLES}

    response = web_door.login_as(person)

    the_no_account_page(
        response,
        door_contract,
        f"a verified login by the unlinked subject {published_subject(person)!r}",
    )
    after = {name: web_identity.keys_of(name) for name in IDENTITY_TABLES}
    created = {
        name: sorted(str(key) for key in after[name] - before[name])
        for name in IDENTITY_TABLES
        if after[name] - before[name]
    }
    assert not created, (
        f"A web login by a subject with no linkage created {created}. E1-12's design: the linkage "
        "is pre-provisioned in the seed or in admin data and never inferred, so a row appearing "
        "here means the door decided this token identifies a new human — on the word of a provider "
        "that asserts authentication and nothing else. §2 puts every role in Pulse's own records, "
        "and a `person` row is the record purview is computed from (§2.1)."
    )


# ---------------------------------------------------------------------------
# The anti-pattern the done-when names, asserted directly.
# ---------------------------------------------------------------------------


def test_a_stored_identity_agreeing_on_an_email_does_not_become_the_signed_in_subject(
    web_door: Any,
    published_person: Any,
    published_subject: Any,
    door_contract: Any,
    web_identity: Any,
    launch_driver: Any,
) -> None:
    """ "Not two rows that happen to agree on an email address" — the done-when's own words.

    The collision is stood up exactly: a `person` with a `user` row and a
    `user_identity` carrying **the very address** the provider asserts for the
    subject signing in, and no linkage between them. A door that matched on the
    claim would hand that session this person's identity, and every other test in
    this repository would stay green — the page is a landing, the session verifies,
    the person is real. What it costs is who the system believes somebody is: two
    people share an address after a rename, a departmental mailbox is on two
    records, an address is reassigned to a new hire, and the answer is plausible and
    wrong. ADR 0024 rejected the same shape for the person-to-user link — "two
    people with the same name is not an exotic case, and the failure is a purview
    computed for the wrong person — invisible, because it produces a plausible
    answer".

    **Dies if resolution consults any claim but `(issuer, subject)`.** The subject
    has no linkage, so the correct answer is the no-account page; the assertion
    below is both that, and — separately — that no session names the person whose
    address matched, so a door that landed *somebody* is caught by the first and a
    door that landed *her* by the second.

    The address is read off the provider's own registration document rather than
    transcribed, so a reseeding moves the collision with it instead of leaving this
    test asserting over an address nobody asserts (`docs/MISTAKES.md` entry 19).

    `launch_driver` is taken for its registration alone: a `user` row belongs to a
    platform, and this one has to belong to a registration that exists.
    """
    person = published_person(web_door.provider, ADMIN_ROLE)
    her_subject = published_subject(person)
    asserted_email = person.get("email")
    assert isinstance(asserted_email, str) and asserted_email, (
        f"The provider publishes {person!r} with no `email`, so there is no address for a stored "
        "identity to agree with and this test would prove nothing about email equality."
    )

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=launch_driver.registration.platform_row[web_identity.key_of("lti_platform")],
        subject=f"an-lms-subject-that-is-not-{her_subject}",
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    web_identity.stored_identity(user_id=user_id, email=asserted_email)

    response = web_door.login_as(person)

    if "#session=" in (response.headers.get("location") or ""):
        merged = claims_of_session(response, "a login whose address matches a stored identity")
        assert merged.get(PERSON_ID_CLAIM) != str(person_id), (
            f"A login by {her_subject!r} was signed in as `person` {str(person_id)!r} — the "
            f"row whose stored identity carries the same address the provider asserts "
            f"({asserted_email!r}), and which nothing links to this subject. That is the merge "
            "this ticket's design forbids by name: an address is a claim the provider's "
            "administrator controls and a person can change, and a merge inferred from one hands "
            "somebody else's purview, responses and Care hat to whoever holds it next."
        )
    the_no_account_page(
        response,
        door_contract,
        f"a verified login by {her_subject!r}, whose asserted address {asserted_email!r} "
        "matches a stored identity nothing links them to",
    )
