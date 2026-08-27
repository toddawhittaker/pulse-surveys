"""Two doors, one stored identity — ticket E1-12, acceptance criteria 1, 2 and 4.

The first entry of `docs/tickets/e1/carried-from-e0.md` is this module's brief, and
its "done when" is the criterion verbatim: "one test drives the two-hat person
through both doors and asserts that both resolve to the *same stored identity* —
one row, by its primary key, not two rows that happen to agree on an email
address". The identity is the `person` row (D1, ADR 0097): a launch resolves `sub`
→ `user` → `person`, a web login resolves `(issuer, subject)` → `person` through
the linkage `web_login_subject`, and the session carries `person_id` from here on.

**Read through the session, because that is where the identity now lives.** Both
doors answer a landing with `302` to `/app/<segment>#session=<token>` (E1-08's
ruling, adopted by E1-09), and E1-12 puts `person_id` in that token's claims. So
every assertion below reads the claim off the fragment — decoded, not verified,
because no test module here is handed `SESSION_SECRET` and both door suites already
read a session this way. `tests/unit/test_session_module.py` is where the signature
is the subject.

**Which view a person lands on is deliberately not asserted anywhere in this
module.** E1-12 leaves `landing_role_for` reading the claim and E1-13 replaces it;
a test here that pinned the route would go red on somebody else's ticket for a
reason that has nothing to do with identity.

**The rows are seeded, not provisioned by a door.** `tests/fixtures/web_identity.py`
writes the `person`, `user` and linkage rows each test means, committed, because the
tool reads on its own connection. Nothing composes them for the test: "these two
doors reach one row" is the property under test, so a fixture that built the
two-hat person in one call would be handing back its own answer
(`docs/MISTAKES.md` entry 30). `scripts/seed.py` writes the same shape for the
running stack and for E1-15's browser proof (D7); an integration test that leaned
on the seed would be asserting about a program it did not run.

**The environment** (`docs/MISTAKES.md` entry 40): both doors are built by
`tool_doors` over `configured_env`, so `ENVIRONMENT` is the development name and
the container's `DATABASE_URL` is laid down before `app.main` is imported. The
database is the session-wide testcontainers Postgres at head; every row written
here — and everything the application writes on its own connection while a test
runs — is removed by `committed_rows`'s diff-delete at teardown.

**Two must-be-green controls open the module.** A red in either means these tests
are broken rather than that the doors are: the first says the claim reader can read
a token at all, the second says a launch driven here lands with a session carrying
the claims E1-08 already issues. Every assertion below is silent unless both hold.
"""

import base64
import json
from typing import Any, ClassVar

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `web_identity`, `web_door`, `identity_provider`, `provider_issuer` and
# `published_person` come from `tests/fixtures/web_identity.py`; `launch_driver`,
# `launch_ground`, `provisioning_contract` and `provisioned_rows` from
# `tests/fixtures/provisioning.py`. All are reached as fixtures rather than
# imported: an import of a fixtures module by name depends on where pytest put
# `tests/` on `sys.path`, and an import error is not a red.

# The two claims E1-12 adds to `SessionClaims` (D4). Spelled here as well as in the
# fixtures module on purpose: a test module importing a fixtures module is the
# import this suite avoids, and these two names are the ticket's contract rather
# than a discovery — if they are wrong they are wrong in one obvious place.
PERSON_ID_CLAIM = "person_id"
USER_ID_CLAIM = "user_id"

# E1-08's own session claims, used only by the control below.
DOOR_CLAIM = "door"
SUBJECT_CLAIM = "sub"

# The role whose seeded person holds both hats: Care through the web door, and an
# instructor assignment that enters by launch. §2: "Entry doors are a property of
# the assignment, not the person."
CARE_ROLE = "CARE"

# The table a linkage row lives in, for the counts below. Spelled rather than
# discovered for the same reason as the claims above.
LINKAGE_TABLE = "web_login_subject"
PERSON_TABLE = "person"
USER_TABLE = "user"
PLATFORM_TABLE = "lti_platform"


def claims_of_session(response: Any, what: str) -> dict[str, Any]:
    """The session claims a landing hands the browser, decoded off the fragment.

    This module's own copy of the reader in `tests/fixtures/web_identity.py`, and
    it is a copy for the reason every constant above is: nothing here imports a
    fixtures module. The control below is what says the copy works.
    """
    assert response.status_code in (302, 303, 307), (
        f"{what} answered {response.status_code} rather than the redirect a door issues for a "
        f"session it minted. Body begins {response.text[:400]!r}."
    )
    location = response.headers.get("location") or ""
    marker = "#session="
    assert marker in location, (
        f"{what} redirected to `{location}`, which carries no `{marker}` fragment. E1-08's "
        "interface ruling makes a landing a 302 to `/app/<segment>#session=<token>`, and the "
        "token is what carries the identity this ticket resolves."
    )
    token = location.split(marker, 1)[1]
    assert token, f"{what} redirected to `{location}`, whose `session=` fragment is empty."
    parts = token.split(".")
    assert len(parts) == 3, (
        f"{what} handed back {token[:80]!r}, which is not a compact JWS, so it carries no claim "
        "set and everything read out of it below would be read out of an empty dict."
    )
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
    try:
        claims = json.loads(decoded)
    except ValueError as broken:
        pytest.fail(
            f"{what}'s session payload does not decode to JSON ({broken}): {decoded[:200]!r}"
        )
    assert isinstance(
        claims, dict
    ), f"{what}'s session payload is not a JSON object: {decoded[:200]!r}"
    return claims


def resolved_person(claims: dict[str, Any], what: str) -> str:
    """The `person_id` a session carries, or a failure saying it carries none.

    Required non-empty at every call site, because "both doors carry the same
    `person_id`" is satisfied by two sessions that carry none at all — which is
    exactly the state of this repository before E1-12 (`docs/MISTAKES.md` entry 3).
    """
    found = claims.get(PERSON_ID_CLAIM)
    assert isinstance(found, str) and found, (
        f"{what} carries `{PERSON_ID_CLAIM}` = {found!r}. E1-12 binds a verified subject to the "
        f"stored identity it resolves to and carries it in the session; the claims are "
        f"{sorted(claims)}. A session with no identity is what the two doors handed back before "
        "this ticket, and it is what E1-13 reads assignments through."
    )
    return found


def platform_id_of(registration: Any, rows: Any) -> Any:
    """The `lti_platform` row a launch driven by this suite resolves to."""
    return registration.platform_row[rows.key_of(PLATFORM_TABLE)]


def one_person_row(rows: Any, person_id: str, what: str) -> Any:
    """The single `person` row with this primary key, or a failure counting what there is.

    "One row, by its primary key" is the criterion's own wording, so the id a
    session carries is looked up in the table rather than merely compared with
    another id: two sessions could agree perfectly on a value that names nothing.
    """
    key = rows.key_of(PERSON_TABLE)
    matching = [row for row in rows.rows_of(PERSON_TABLE) if str(row[key]) == str(person_id)]
    assert len(matching) == 1, (
        f"{what} names `{PERSON_TABLE}` {person_id!r}, and the table holds {len(matching)} rows "
        f"with that key. Zero means the session carries an identity nothing stores — a subject "
        "resolved to a value rather than to a row."
    )
    return matching[0]


# ---------------------------------------------------------------------------
# The machinery, before anything is asserted with it. Two must-be-green
# controls: a red here means these tests are broken, not that the doors are.
# ---------------------------------------------------------------------------


def test_the_session_claim_reader_reads_a_token_it_is_handed() -> None:
    """The control on the decoder: it finds a claim that is there, and none that is not.

    **Dies if `claims_of_session` is satisfied by emptiness** — a padding bug, a
    segment counted wrong, a payload read as the header. Every assertion in this
    module is either "the two doors agree on `person_id`" or "this session carries
    no `person_id`", and a decoder that always answered `{}` would make the second
    kind pass against a door that leaks and the first kind fail for no reason
    anybody could act on (`docs/MISTAKES.md` entry 9: a guard nobody has watched
    catch its own case is a comment).

    Needs no implementation and is green today. Both directions are checked,
    because a decoder that answered the *whole payload* for every key would find
    `person_id` in a token that has none.
    """
    payload = {PERSON_ID_CLAIM: "a-person-id", DOOR_CLAIM: "web"}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=")
    compact_jws = ".".join(["header", encoded.decode("ascii"), "signature"])

    class Landing:
        status_code = 302
        headers: ClassVar[dict[str, str]] = {"location": f"/app/care#session={compact_jws}"}
        text = ""

    read = claims_of_session(Landing(), "a token this test built")

    assert read.get(PERSON_ID_CLAIM) == "a-person-id", (
        f"The reader answered {read!r} for a token whose payload is {payload!r}. Nothing below "
        "that reads a session claim means anything until this passes."
    )
    assert USER_ID_CLAIM not in read, (
        f"The reader reports `{USER_ID_CLAIM}` in {read!r}, and the token carries no such claim. "
        "Then 'the web door leaves `user_id` unset' is a statement this instrument cannot make."
    )


def test_a_launch_lands_with_a_session_this_module_can_read(
    launch_driver: Any, provisioning_contract: Any, launch_ground: Any
) -> None:
    """The second control: the launch driver reaches a landing, and its session decodes.

    **Dies if the launch never lands** — a refused handshake, a platform nothing
    registered, a door answering 4xx — in which case every identity assertion below
    would be a statement about a flow that did not happen. E1-08's own claims are
    what is checked, not E1-12's: those are already shipped, so this control is
    green before the implementer starts and stays green after, which is what makes
    a red here a fault in this module rather than in the ticket.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    launch_ground(provisioning_contract.label_of(launch_driver.claims_of(offer)))

    response, signed = launch_driver.launch(offer)

    claims = claims_of_session(response, "an instructor's launch")
    assert claims.get(DOOR_CLAIM), (
        f"The session a launch landed with carries no `{DOOR_CLAIM}` claim; it carries "
        f"{sorted(claims)}. E1-08's `SessionClaims` names one for every session, so this reader is "
        "looking at something other than the session the door issued."
    )
    assert claims.get(SUBJECT_CLAIM) == signed.claims.get(SUBJECT_CLAIM), (
        f"The session says `{SUBJECT_CLAIM}` is {claims.get(SUBJECT_CLAIM)!r} and the launch it "
        f"was issued for said {signed.claims.get(SUBJECT_CLAIM)!r}. The two disagreeing means this "
        "module is reading a session belonging to some other flow."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — the two-hat person, both doors, one row.
# ---------------------------------------------------------------------------


def test_the_two_hat_person_resolves_to_one_person_row_through_both_doors(
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
) -> None:
    """The done-when, verbatim: same stored identity, one row, by its primary key.

    She holds a Care assignment, which enters by web login, and an instructor
    assignment, which enters by launch (§2: "Entry doors are a property of the
    assignment, not the person"). Before this ticket the two were two unrelated
    verified tokens and E0 said so on purpose. One `person` row is seeded, her
    launch-side `user` row is linked to it through `person.user_id` (ADR 0024), and
    her IdP subject is linked to it through `web_login_subject` — and then both
    doors are driven for real and asked who they think she is.

    **Both doors in one test on purpose.** Split in two, each half is satisfied by a
    seed the other person is missing from, and the fact worth asserting — that one
    human's two subjects reach one row — is stated nowhere.

    **Dies if a door resolves nothing** (`resolved_person` requires the claim),
    **dies if the two doors resolve to two rows**, which is the state E0 shipped,
    and **dies if the id names no row at all** — `one_person_row` looks it up, so a
    session carrying a plausible uuid that stores nothing fails here rather than
    passing an equality between two identical strings.

    **This is also where the constant-pinning unit test's fact is asserted
    directly**, which is what lets that module be deleted in this same change (D8).
    `tests/unit/test_the_mock_seeds_name_one_person.py` compared
    `mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID` with the platform's own
    instructor because nothing else tied the two mocks to one human. The assertion
    below is that tie, made against what the two mocks *serve*: the subject the
    platform signs into her launch is the `lms_user_id` the provider publishes for
    her. If the platform reseeds its instructor under another name, this fails here,
    in the test whose subject it is.
    """
    hers = published_person(web_door.provider, CARE_ROLE, and_a_launch_assignment=True)
    her_lms_subject = hers.get("lms_user_id")
    assert her_lms_subject, (
        f"The two-hat person is published without an `lms_user_id` ({hers!r}). ADR 0058 makes it "
        "the member that says which LMS user she is, and without it these are two fixtures rather "
        "than one human."
    )

    offers = [
        offer
        for offer in launch_driver.offers()
        if offer.parameters.get("login_hint") == her_lms_subject
    ]
    assert offers, (
        f"The mock platform offers no launch for {her_lms_subject!r}, the LMS user the provider "
        "says she is. The two mocks then name two different people and this test cannot ask its "
        "question."
    )
    launch_claims = launch_driver.claims_of(offers[0])
    assert launch_claims.get(SUBJECT_CLAIM) == her_lms_subject, (
        f"The platform signs that launch as {launch_claims.get(SUBJECT_CLAIM)!r} and the provider "
        f"publishes her LMS identity as {her_lms_subject!r}. That reference is the only thing in "
        "either mock tying the two entry doors to one human, and with the two disagreeing this "
        "test seeds a `user` row for a subject no launch carries — after which the launch door "
        "resolves a different person and the merge below is untested. If a rename was deliberate, "
        "both mocks change together."
    )
    launch_ground(provisioning_contract.label_of(launch_claims))

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver.registration, web_identity),
        subject=her_lms_subject,
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(hers), person_id=person_id
    )

    web_landing = web_door.login_as(hers)
    launch_landing, _ = launch_driver.launch(offers[0])

    by_web = resolved_person(claims_of_session(web_landing, "her web login"), "Her web session")
    by_launch = resolved_person(
        claims_of_session(launch_landing, "her launch"), "Her launch session"
    )

    assert by_web == by_launch, (
        f"Her web login resolved to `{PERSON_TABLE}` {by_web!r} and her launch to {by_launch!r}. "
        "One human, two subjects, two rows — which is what E0 shipped deliberately and what this "
        "ticket exists to close. SPEC §2.1 computes purview from the people graph, so two rows "
        "means two purviews for one person, and the Care hat and the teaching hat stop being one "
        "person's."
    )
    assert by_web == str(person_id), (
        f"Both doors agree on `{PERSON_TABLE}` {by_web!r}, and the row seeded for her is "
        f"{str(person_id)!r}. Agreeing on the wrong row is the failure a merge makes silently: the "
        "doors resolve to *a* person consistently, and it is not her."
    )
    one_person_row(web_identity, by_web, "The identity both her doors resolved to")


# ---------------------------------------------------------------------------
# Criterion 2 — the near miss the criterion names: everybody resolving to one
# row would satisfy the test above.
# ---------------------------------------------------------------------------


def test_a_second_person_entering_by_launch_resolves_to_their_own_person_row(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
) -> None:
    """Criterion 2: the merge is a merge and not a constant (`docs/MISTAKES.md` entry 3).

    "A second person entering by launch only resolves to their own identity — the
    two-hat test cannot pass by everyone resolving to one row." Two subjects the
    platform signs different launches for, two seeded `person` rows, two sessions —
    and each has to name **its own** row, not merely a different one.

    **Dies against a resolver that answers a constant**: the first person's row, the
    first row in the table, the only row it can see. Every one of those passes the
    two-hat test above, which asks one person twice.

    **Dies against a resolver that answers by position rather than by subject** —
    the assertion is against the row seeded for each subject, so a door that swapped
    the two fails here while a door that merely returned two different values would
    pass a distinctness check.

    Both launches are ordinary and neither person's row is special: what
    distinguishes them is the `user` row their `sub` reaches and the `person` row
    that links to it (ADR 0024).
    """
    first_offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    second_offer = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    first_claims = launch_driver.claims_of(first_offer)
    second_claims = launch_driver.claims_of(second_offer)
    first_subject = first_claims.get(SUBJECT_CLAIM)
    second_subject = second_claims.get(SUBJECT_CLAIM)
    assert first_subject and second_subject and first_subject != second_subject, (
        f"The two launches this test drives carry subjects {first_subject!r} and "
        f"{second_subject!r}. Two launches by one subject cannot pose the question — one person "
        "resolving to one row twice is the state the near miss is written against."
    )
    launch_ground(provisioning_contract.label_of(first_claims))

    platform_id = platform_id_of(launch_driver.registration, web_identity)
    people = {}
    for subject in (first_subject, second_subject):
        person_id = web_identity.person()
        user_id = web_identity.user(platform_id=platform_id, subject=subject)
        web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
        people[subject] = str(person_id)

    first_landing, _ = launch_driver.launch(first_offer)
    second_landing, _ = launch_driver.launch(second_offer)

    first_resolved = resolved_person(
        claims_of_session(first_landing, "the first person's launch"), "The first launch session"
    )
    second_resolved = resolved_person(
        claims_of_session(second_landing, "the second person's launch"), "The second launch session"
    )

    assert first_resolved != second_resolved, (
        f"Two different subjects both resolved to `{PERSON_TABLE}` {first_resolved!r}. Every "
        "person entering by launch is one person, which satisfies the two-hat criterion perfectly "
        "and is a confidentiality failure in every later epic: one purview, one Care hat, everyone."
    )
    assert (first_resolved, second_resolved) == (people[first_subject], people[second_subject]), (
        f"The launches by {first_subject!r} and {second_subject!r} resolved to "
        f"{(first_resolved, second_resolved)}; the rows seeded for them are "
        f"{(people[first_subject], people[second_subject])}. Distinct and wrong is the shape a "
        "resolver keyed on anything but the subject produces — a row per launch, a row per "
        "position in the table — and a test that only required two different answers would pass "
        "against it."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — re-entry, asserted on row identity.
# ---------------------------------------------------------------------------


def test_a_second_launch_by_one_subject_leaves_one_user_row_and_one_identity(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
) -> None:
    """Criterion 4, the launch side: "no duplicate identities after repeated logins".

    Asserted on **row identity** rather than on a count, which the criterion asks
    for by name: an upsert that rewrites the row on every launch keeps the count at
    one while editing a `sub` this project is never supposed to edit (ADR 0014's
    ownership marker), and a delete-and-reinsert gives the person a new primary key
    and orphans everything a later epic hangs off it. The whole mapping is compared.

    **The identity half is what E1-12 adds**: the second launch has to resolve to
    the *same* `person`, not to a second one. A resolver that inserted a person when
    it could not find one would pass every row-identity check on `user` and hand the
    same human two identities on their second visit.

    Its own control is the first launch: the `user` row and the `person_id` are both
    required before the second launch runs, so "unchanged" is a statement about a
    row that existed rather than about an empty table.

    **The rows are counted per registration, not per subject, and the mutation
    battery is why.** The first version filtered them to `lms_user_id == sub`, which
    made a whole class of duplicate invisible: a door inserting a second row for the
    same human under a near-miss key — `sub` with anything appended, a normalised
    or re-cased `sub` — leaves the filtered list holding exactly the seeded row
    before and after, and resolution still finds that row, so the same-person
    assertion holds too. The mutation "reinsert a fresh `user` row on every launch"
    survived the test whole. Every `user` row on the platform that signed these
    launches is now the measurement, which is what the message below always claimed
    to be saying: this registration has one human launching into it, so one row is
    the whole of what may be there.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = launch_driver.claims_of(offer)
    subject = claims.get(SUBJECT_CLAIM)
    launch_ground(provisioning_contract.label_of(claims))

    platform_id = platform_id_of(launch_driver.registration, web_identity)
    person_id = web_identity.person()
    user_id = web_identity.user(platform_id=platform_id, subject=subject)
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)

    def users_on_the_platform() -> list[Any]:
        """Every `user` row belonging to the registration these launches are signed by.

        A subject means nothing outside the registration that issued it, so the
        registration is the right grain to count a duplicate at — and it is the only
        grain that can see one keyed to something *near* this launch's `sub` rather
        than to it. Exactly one human launches into this registration in this test,
        and the seeding above is the only thing that put a row there.
        """
        column = web_identity.platform_column()
        return [row for row in web_identity.rows_of(USER_TABLE) if row.get(column) == platform_id]

    first, _ = launch_driver.launch(offer)
    first_person = resolved_person(
        claims_of_session(first, "the first launch"), "The first launch's session"
    )
    after_one = users_on_the_platform()
    assert len(after_one) == 1, (
        f"There are {len(after_one)} `{USER_TABLE}` rows on the registration this launch was "
        f"signed by after one launch, and one human has launched into it: {after_one}. One row was "
        f"seeded, for {subject!r}, and ADR 0091 has the launch tolerate the row it finds — so zero "
        "means the seeded row is not where the door looks, and two means the door inserted beside "
        "it. **Read the second row's `lms_user_id` before anything else**: equal to the seeded "
        "one, the unique constraint is missing; *near* it — the `sub` with something appended, "
        "trimmed or re-cased — the door is deriving its key rather than storing the claim "
        "verbatim, which is a second identity for one human that a lookup by the exact `sub` "
        "would never have found."
    )

    second, _ = launch_driver.launch(offer)
    second_person = resolved_person(
        claims_of_session(second, "the second launch"), "The second launch's session"
    )
    after_two = users_on_the_platform()

    assert [dict(row) for row in after_two] == [dict(row) for row in after_one], (
        f"The second launch changed the `{USER_TABLE}` rows on this registration.\n"
        f"  after the first: {[dict(row) for row in after_one]}\n"
        f"  after the second: {[dict(row) for row in after_two]}\n"
        "Criterion 4 asks for idempotence on row identity: same key, same values. A changed key "
        "is a delete-and-reinsert, which orphans everything a later epic hangs off this row; a "
        "second row is a second identity for one human, whatever key it carries."
    )
    assert second_person == first_person, (
        f"The same subject's two launches resolved to `{PERSON_TABLE}` {first_person!r} and then "
        f"{second_person!r}. Re-entry has produced a second identity, which is precisely what "
        "'no duplicate identities after repeated logins' forbids — and the person's earlier "
        "responses, assignments and purview stay attached to the first one."
    )


def test_a_second_web_login_writes_no_linkage_row_and_carries_one_identity(
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
) -> None:
    """Criterion 4, the web side: a login reads the linkage and never writes one.

    D2 gives `pulse_app` no grant of any kind on `web_login_subject` — the rows are
    written by the seed and by an administrator, and the door reads through a
    definer function — so "idempotent across re-entry" on this side is the stronger
    statement that a web login writes **nothing**. Asserted on row identity, not on
    a count: a door that rewrote the row it found would keep the count at one while
    editing the mapping that decides who a subject is.

    **Dies if a second login provisions a second linkage or a second person**, which
    is the shape a door takes when it treats "resolve" as "get or create" — and the
    same door lands the person correctly both times, so nothing else here would
    notice.

    Its control is the first login: it has to reach a session carrying this person's
    id before "the second changed nothing" says anything about a door that ran.
    """
    hers = published_person(web_door.provider, CARE_ROLE, and_a_launch_assignment=True)
    person_id = web_identity.person()
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(hers), person_id=person_id
    )

    before_linkages = [dict(row) for row in web_identity.linkages()]
    before_people = web_identity.keys_of(PERSON_TABLE)

    first = web_door.login_as(hers)
    first_person = resolved_person(
        claims_of_session(first, "her first web login"), "Her first web session"
    )
    assert first_person == str(person_id), (
        f"Her first web login resolved to {first_person!r} and her linkage names {str(person_id)!r}"
        ". The rest of this test compares a second login against a first one that already resolved "
        "the wrong person."
    )

    second = web_door.login_as(hers)
    second_person = resolved_person(
        claims_of_session(second, "her second web login"), "Her second web session"
    )

    assert [dict(row) for row in web_identity.linkages()] == before_linkages, (
        f"A web login changed `{LINKAGE_TABLE}`.\n  before: {before_linkages}\n"
        f"  after two logins: {[dict(row) for row in web_identity.linkages()]}\n"
        "D2 gives the application connection no grant on this table at all: the linkage is "
        "provisioned ahead of a login and read through a definer function, so a login that wrote "
        "one has either been granted something no ticket granted or is inferring a merge from a "
        "token — which is the one thing this ticket's design forbids outright."
    )
    assert web_identity.keys_of(PERSON_TABLE) == before_people, (
        f"A web login created a `{PERSON_TABLE}` row. Before: {sorted(str(k) for k in before_people)}"
        f". After: {sorted(str(k) for k in web_identity.keys_of(PERSON_TABLE))}. The IdP asserts "
        "authentication, not membership (§2: Pulse's roles come from Pulse's own records), so a "
        "person invented at the door is an identity nobody provisioned."
    )
    assert second_person == first_person, (
        f"Two logins by one subject resolved to {first_person!r} and then {second_person!r}. A "
        "second identity for one human on re-entry is what criterion 4 forbids."
    )
