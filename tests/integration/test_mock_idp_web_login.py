"""Who may come through the second door, and what they get — ticket E0-16.

SPEC §2 gives Pulse two entry doors and gives each role exactly one of them:
"LTI launch requires being an enrolled LMS user in *some* course, so **web login
via OIDC is retained** for all leadership and staff roles." E0-16 seeds that
door — VPAA, dean, chair, lead faculty, Care and admin — and says of the other
two roles: "do not seed either here."

Three of its criteria are about the identities rather than the protocol, and this
module holds those. The protocol is next door in
`test_mock_idp_authorization_code_flow.py`.

**Roles are read by scanning the session, not by reading one agreed claim.**
E0-16 spells no claim name, and pinning one here would decide it — so
`roles_in` in `tests/conftest.py` walks the whole claim tree and matches the
normalised leaves against how this project spells its roles (E0-09's
`ROLE_ALIASES`, plus the vocabulary spelling of the two launch-only roles). Two
of the assertions below are about a role being *absent*, which is exactly the
shape `docs/MISTAKES.md` entry 3 is about, so the scanner has its own control
here — run against the values it is claimed to catch and the values it is claimed
to let past — and each absence assertion carries a live control beside it: a
session in the same provider that *does* state the thing being looked for.

**The two-hat person is asserted twice, and the second way is there because the
first was not enough.** E0-16 seeds "one person who holds **both** a Care
assignment and an instructor assignment", and the point of her is that the
instructor half is invisible from this door. When this module was written nothing
in the ticket said how a test would identify her, so criterion 8 was asserted over
*every* session holding Care — each one states no reporting role and carries no
purview. That property is worth keeping and it is what makes a session built from
`assignments` rather than from web-login roles fail here. What it cannot do is
prove she was seeded: **deleting her left all of these tests green**, and
quantifying over "every session that holds Care" is precisely what let the
deletion pass, because a set with nobody in it satisfies every statement about
its members. The non-emptiness guard this module already carried did not close it
either — it required *a* Care session to exist, and a Care-only person satisfies
that.

She is nameable now. [ADR 0058](../../docs/adr/0058-the-registration-document-is-the-contract-between-the-mocks.md)
makes `roles`, `launch_only_roles`, `lms_user_id` and `roles_claim` contract
members of the published registration document, so the tests below select her by
identity rather than by scanning: exactly one published person carries a
launch-only assignment, she holds Care and nothing else, and signing in **as her**
yields Care without it. Selecting her is what makes her deletion a failure.
"""

from html.parser import HTMLParser
from typing import Any, NamedTuple

import pytest

# The roles seeded for web login, spelled as this project spells roles. Six are
# the ticket's own list — "VPAA, dean, chair, lead faculty, Care, and admin" —
# transcribed rather than derived, so a seed that quietly loses one fails here by
# name instead of passing unnoticed. That enumeration *is* criterion 6.
#
# **`ASSISTANT_DEAN` is a seventh, seeded beyond the ticket's six.** That is
# defensible on SPEC §2's own terms — the web door belongs to every leadership and
# staff role, and §2.1 makes the assistant dean the worked example of a reporting
# line containment cannot express — but a person seeded without being enumerated
# here is exactly the failure this list exists to prevent, and it was live: while
# the role was missing, deleting the `assistant-dean` block from the seed left
# every test in this module green, where deleting `admin` correctly failed.
# Enumerating the role rather than removing the person is the right direction, and
# the rule to carry forward is that a seeded role and this list move together.
WEB_LOGIN_ROLES = (
    "VP_ACADEMICS",
    "DEAN",
    "ASSISTANT_DEAN",
    "CHAIR",
    "LEAD_FACULTY",
    "CARE",
    "ADMIN",
)

# The two roles that enter by launch only, from the same sentence: "Web login is
# available to every role **except instructor and student**, who enter by launch
# only — do not seed either here."
LAUNCH_ONLY_ROLES = ("INSTRUCTOR", "STUDENT")

# SPEC §2.1's supervision chain: `INSTRUCTOR(section) → LEAD_FACULTY(course) →
# CHAIR(department) → DEAN(college) → VP_ACADEMICS`, with the assistant dean
# inserted. Care and Admin are deliberately not in it — §2.1: "Care and Admin sit
# outside the graph and hold no edges in either direction" — which is why a Care
# session holding one of these is the composition §2 forbids.
REPORTING_ROLES = ("VP_ACADEMICS", "DEAN", "ASSISTANT_DEAN", "CHAIR", "LEAD_FACULTY", "INSTRUCTOR")

# Values submitted as an identity this provider does not offer web login to.
# **This suite's choice** of spelling; what they stand for is the ticket's. Both
# say what they are in the value itself, so one appearing in a session, a log or
# a seed is traceable to this file.
LAUNCH_ONLY_SUBJECTS = {
    "an instructor-only identity": "instructor-only-e0-16",
    "a student-only identity": "student-only-e0-16",
}

# Control values for the role scanner: what it must recognise, and what it must
# not. The last two are the ones that matter — a person *called* Dean is not a
# dean, and an assistant dean is not a dean either, which is the failure a
# substring match would produce silently.
STATED_ROLES = {
    "a bare word": ({"roles": ["care"]}, {"CARE"}),
    "a phrase": ({"https://pulse.example/claims": {"role": "VP Academics"}}, {"VP_ACADEMICS"}),
    "a vocabulary URI": (
        {"roles": ["http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"]},
        {"STUDENT"},
    ),
    "a compound role name": ({"roles": ["ASSISTANT_DEAN"]}, {"ASSISTANT_DEAN"}),
    "a person named after a role": (
        {"name": "Dean Ashford", "preferred_username": "chair", "email": "care@example.edu"},
        set(),
    ),
    "a session stating nothing": ({"sub": "u-1"}, set()),
}

# The same, for the purview scanner. An OAuth scope of `openid` is the near miss:
# it is a claim about the request rather than a set of org nodes, and a scanner
# that flagged it would fail every conformant provider.
PURVIEW_SHAPES = {
    "a purview object": ({"purview": {"college_ids": []}}, {"purview", "college_ids"}),
    "a namespaced level": ({"pulse_department_ids": ["d-1"]}, {"pulse_department_ids"}),
    "an oauth scope": ({"scope": "openid"}, set()),
    "a plain session": ({"sub": "u-1", "roles": ["CARE"]}, set()),
}


def sessions_with(provider: Any, logins: list[Any], roles: tuple[str, ...]) -> list[Any]:
    """Every session in `logins` stating any of `roles`."""
    return [login for login in logins if provider.roles(login) & set(roles)]


def launch_only_users(provider: Any) -> list[dict[str, Any]]:
    """Every published person carrying an assignment that enters by launch (ADR 0058)."""
    return [user for user in provider.published_users() if user.get("launch_only_roles")]


def two_hat_user(provider: Any) -> dict[str, Any]:
    """The one person who holds a Care assignment here and a teaching one on the platform.

    Fails rather than picking when there is not exactly one, because every test
    that calls this is about *her* — a second such person would mean the tests
    below are about whichever one the document lists first, which is the shape
    that reads as a pass.
    """
    found = launch_only_users(provider)
    if len(found) != 1:
        pytest.fail(
            f"The registration document publishes {len(found)} people carrying a "
            f"`launch_only_roles` assignment rather than one: {found!r}. E0-16 seeds exactly one "
            "person who logs in here for Care work and launches from the mock LMS for teaching, "
            "and `test_exactly_one_published_user_holds_a_launch_only_assignment` is the test "
            "that says so."
        )
    return found[0]


# ---------------------------------------------------------------------------
# The scanners the assertions below are made with, run before they are believed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(STATED_ROLES))
def test_the_role_scanner_reads_a_stated_role_and_not_a_person_named_after_one(
    roles_in_claims: Any, case: str
) -> None:
    """The control on every role assertion in this module.

    `docs/MISTAKES.md` entry 3: a matcher run against a document is a case of "a
    test passed for a reason unrelated to what it asserted" and looks like none,
    so it is run against the values it is claimed to catch *and* the values it is
    claimed to let past. Both halves are here, and the second is the one that
    would otherwise be discovered late: without it, a scanner that recognised
    nothing at all would make "no session states an instructor role" and "the
    Care session states no reporting role" both pass, and both would read as the
    provider being correct.
    """
    claims, expected = STATED_ROLES[case]

    assert roles_in_claims(claims) == expected, (
        f"Scanning {case} — {claims!r} — found {sorted(roles_in_claims(claims))} rather than "
        f"{sorted(expected)}. `roles_in` in tests/conftest.py is what every role assertion in "
        "this module is made with, so it is wrong here before it is wrong about the provider."
    )


@pytest.mark.parametrize("case", sorted(PURVIEW_SHAPES))
def test_the_purview_scanner_finds_a_purview_and_ignores_an_oauth_scope(
    purview_claims_in: Any, case: str
) -> None:
    """The control on criterion 8's second half, for the same reason as above.

    The near miss is the OAuth `scope` member: it is in every conformant token
    exchange, it is not a set of org nodes, and a scanner that read it as one
    would report a purview on every session ever issued.
    """
    claims, expected = PURVIEW_SHAPES[case]

    assert purview_claims_in(claims) == expected, (
        f"Scanning {case} — {claims!r} — found {sorted(purview_claims_in(claims))} rather than "
        f"{sorted(expected)}."
    )


# ---------------------------------------------------------------------------
# Who may sign in. Criteria 6 and 7.
# ---------------------------------------------------------------------------


def test_every_seeded_web_login_role_can_obtain_a_session(mock_idp: Any) -> None:
    """Criterion 6, and the enumeration is the criterion.

    "Every seeded role can log in, and a test enumerates them so a missing role
    fails rather than going unnoticed." A test that asserted "some identity signs
    in" would pass against a provider seeded with one person, which is why the
    six are written out at the top of this file and compared as a set.

    Each identity is driven through a whole flow, so "can log in" means a session
    was issued rather than that a name appears in a form.
    """
    logins = mock_idp.logins()
    assert logins, (
        "The provider's login form offered no identity to sign in as. E0-16 seeds six web-login "
        "roles, and every assertion below is about the set of sessions they produce."
    )

    stated: set[str] = set()
    for login in logins:
        stated |= mock_idp.roles(login)

    missing = [role for role in WEB_LOGIN_ROLES if role not in stated]
    assert not missing, "\n".join(
        [
            f"No seeded identity signs in with {missing}.",
            f"  identities offered: {[login.submission for login in logins]}",
            f"  roles their sessions state: {sorted(stated)}",
            "",
            "E0-16's scope: 'Seeded users covering every web-login role: VPAA, dean, chair, lead "
            "faculty, Care, and admin.' SPEC §2 keeps web login for exactly these roles because "
            "an LTI launch needs an enrollment they do not have — a role missing here is a role "
            "that cannot enter the product at all.",
        ]
    )


def test_no_identity_the_login_form_offers_holds_a_launch_only_role(mock_idp: Any) -> None:
    """Criterion 7, over the identities the door actually offers.

    The enumeration half: whatever else is true, none of the people this form
    will sign in may arrive holding an instructor or a student role. E0-16: "do
    not seed either here", and SPEC §2 gives both of them the other door.

    This is an assertion that something is absent, so it carries a control in the
    same run: the same scan over the same sessions has to find the reporting
    roles that *are* seeded. Without it, a provider that issued sessions with no
    roles in them at all would pass — and would pass while being the same defect
    from the opposite side.
    """
    logins = mock_idp.logins()
    assert logins, "The provider's login form offered no identity to sign in as."

    assert sessions_with(mock_idp, logins, REPORTING_ROLES), (
        "No session this provider issued states any reporting role, so the absence asserted "
        f"below is a fact about the scan rather than about the seed. Sessions found: "
        f"{[sorted(mock_idp.roles(login)) for login in logins]}."
    )

    offenders = [
        (login.submission, sorted(mock_idp.roles(login) & set(LAUNCH_ONLY_ROLES)))
        for login in sessions_with(mock_idp, logins, LAUNCH_ONLY_ROLES)
    ]
    assert not offenders, "\n".join(
        [
            "The web login door offers identities holding a launch-only role:",
            *(f"  {submission} states {roles}" for submission, roles in offenders),
            "",
            "E0-16: web login is available to every role 'except instructor and student, who "
            "enter by launch only — do not seed either here'. SPEC §2 puts them behind the LTI "
            "launch because that is where their enrollment is; a session issued here carries no "
            "launch context at all.",
        ]
    )


@pytest.mark.parametrize("case", sorted(LAUNCH_ONLY_SUBJECTS))
def test_a_launch_only_identity_cannot_obtain_a_session_here(mock_idp: Any, case: str) -> None:
    """Criterion 7's refusal half: the door says no rather than defaults to yes.

    Asserted as a refusal rather than as an absence, which is the difference
    between "no instructor appears in the form" — already covered above — and
    "this provider will not sign one in". The failure it exists for is a login
    handler that trusts what the form submitted: a `<select>` is a suggestion, and
    a provider that mints a session for whatever subject arrives has opened the
    web door to every identity in the institution, instructors and students
    included, while its own form offers only the six.

    **What it cannot distinguish, stated plainly.** E0-16 forbids seeding an
    instructor or a student here, so from this door a launch-only identity is
    necessarily one the provider was not seeded with, and a refusal for "unknown
    subject" and a refusal for "this role uses the other door" look identical
    from outside. Both are the required outcome — no code, no session — and the
    ticket does not say the provider should know launch-only identities by name.
    If it should, that is a sentence for the ticket rather than a guess here.

    The control is a seeded identity signing in successfully through the same
    form, in the same test: without it, a provider whose login form is broken for
    everybody would pass.
    """
    control_attempt = mock_idp.begin()
    control = mock_idp.submit_login(
        control_attempt, mock_idp.offered_identities(control_attempt)[0]
    )
    assert control.code, (
        f"A seeded identity ({control.submission}) could not sign in either — the provider "
        f"answered {control.response.status_code}. The refusal below would then be a fact about "
        "a broken login form rather than about who may use this door."
    )

    attempt = mock_idp.begin()
    form = mock_idp.require_login_form(attempt)
    submission = dict(mock_idp.offered_identities(attempt)[0])
    submission[mock_idp.identity_field(form)] = LAUNCH_ONLY_SUBJECTS[case]

    refused = mock_idp.submit_login(attempt, submission)

    assert refused.refused, "\n".join(
        [
            f"Submitting {case} — {submission} — obtained an authorization code "
            f"({refused.code!r}, sent to {refused.location!r}).",
            "",
            "E0-16 criterion 7: an instructor-only or student-only identity cannot obtain a "
            "session here; web login is not their door (SPEC §2). A provider that signs in "
            "whatever the form posts has no door at all — the six seeded identities are then a "
            "convenience rather than the boundary.",
        ]
    )


# ---------------------------------------------------------------------------
# Care, and what does not ride along with it. Criterion 8.
# ---------------------------------------------------------------------------


def test_a_seeded_identity_signs_in_and_holds_the_care_capability(mock_idp: Any) -> None:
    """Criterion 8's first half, and the precondition the two below rest on.

    "The Care-and-instructor person authenticates successfully." Asserted on its
    own because the two assertions that follow are about *every* session holding
    Care, and a provider that seeds no Care identity satisfies both by having
    nothing to check — the emptiness `docs/MISTAKES.md` entry 3 is about.
    """
    logins = mock_idp.logins()
    assert logins, "The provider's login form offered no identity to sign in as."

    care = sessions_with(mock_idp, logins, ("CARE",))
    assert care, "\n".join(
        [
            "No identity this provider offers signs in holding Care.",
            f"  identities offered: {[login.submission for login in logins]}",
            f"  roles their sessions state: {[sorted(mock_idp.roles(login)) for login in logins]}",
            "",
            "E0-16 seeds Care among the six web-login roles, and separately 'one person who holds "
            "both a Care assignment and an instructor assignment ... this person logs in here for "
            "Care work and launches from the mock LMS for teaching'. E0-10 and E0-18 both reuse "
            "that fixture.",
        ]
    )


def test_a_session_holding_care_states_no_reporting_role(mock_idp: Any) -> None:
    """Criterion 8: Care arrives on its own, or it is not Care.

    SPEC §2: "**Care is deliberately not composable** with reporting roles — its
    sole power is the threat queue, kept isolated so safety re-identification
    never rides alongside routine oversight access." §2.1 puts Care outside the
    supervision graph entirely, so there is no reporting role for a Care session
    to legitimately carry, and the person this criterion is written about is
    precisely the one who could make it look reasonable: she really does hold an
    instructor assignment, and it really does belong to the other door.

    The control is in the same run and is not ceremony: another session from this
    provider must state a reporting role under the same scan. Without it, a
    provider that put no roles anywhere would pass — and the assertion would read
    as evidence of an isolation that had never been implemented.
    """
    logins = mock_idp.logins()
    care = sessions_with(mock_idp, logins, ("CARE",))
    assert care, "No session holds Care, so this test would assert nothing about an empty set."

    assert sessions_with(mock_idp, logins, REPORTING_ROLES), (
        "No session this provider issued states any reporting role at all, so 'the Care session "
        "states none' is a fact about the scan rather than about the provider. Sessions found: "
        f"{[sorted(mock_idp.roles(login)) for login in logins]}."
    )

    composed = [
        (login.submission, sorted(mock_idp.roles(login) & set(REPORTING_ROLES))) for login in care
    ]
    composed = [entry for entry in composed if entry[1]]
    assert not composed, "\n".join(
        [
            "A session holding Care also states a reporting role:",
            *(f"  {submission} also states {roles}" for submission, roles in composed),
            "",
            "SPEC §2: Care is deliberately not composable with reporting roles, so that safety "
            "re-identification never rides alongside routine oversight access. The two-hat person "
            "holds both assignments and enters by two doors; this one carries only the Care half.",
        ]
    )


def test_a_session_holding_care_carries_no_purview(mock_idp: Any, purview_claims_in: Any) -> None:
    """Criterion 8, in its own words: "without any reporting purview attached".

    A purview is §2.1's six sets of org nodes, and E0-11 keeps Care beside one
    rather than inside it "so that no union operation can ever pick it up". This
    is the same rule one layer earlier: a session that arrives carrying a purview
    has already composed them, before any resolver is involved, and E1's session
    model would then have a purview to trust that no supervision graph produced.

    Purview resolution from claims is explicitly E1's and E9's work, so the
    correct number of purview claims on any session this provider issues is zero;
    that is why this is asserted over the Care sessions and not compared against
    a reporting one. **There is no live control for it**, because no door in E0
    emits a purview to compare against — what stands in for one is the scanner's
    own test at the top of this file, which shows it finding a purview when one
    is there.
    """
    logins = mock_idp.logins()
    care = sessions_with(mock_idp, logins, ("CARE",))
    assert care, "No session holds Care, so this test would assert nothing about an empty set."

    attached = [
        (login.submission, sorted(purview_claims_in(login.claims)))
        for login in care
        if purview_claims_in(login.claims)
    ]
    assert not attached, "\n".join(
        [
            "A session holding Care carries purview claims:",
            *(f"  {submission} carries {claims}" for submission, claims in attached),
            "",
            "E0-16 criterion 8: the session exposes the Care capability 'without any reporting "
            "purview attached'. Purview comes from the supervision graph (SPEC §2.1) and is "
            "computed by the tool in E1 and E9 — a provider that ships one has invented a scope "
            "nothing granted.",
        ]
    )


# ---------------------------------------------------------------------------
# The person the criterion is actually about, selected rather than scanned for.
# ---------------------------------------------------------------------------


def test_exactly_one_published_user_holds_a_launch_only_assignment(
    mock_idp: Any, roles_in_claims: Any
) -> None:
    """Criterion 8's subject exists, and there is one of her.

    "Seed one person who holds **both** a Care assignment and an instructor
    assignment. Unlikely in practice but legitimate, and it is the case that
    proves the doors are a property of the assignment rather than the person."

    Everything else this module says about Care is quantified over the sessions
    the provider issues, and **deleting her satisfied all of it** — an empty set
    agrees with every statement about its members. This is the assertion that
    cannot be satisfied by her absence, and it is why the others are worth having:
    they say what a Care session may not carry, and this one says whose.

    `roles == ["CARE"]` exactly, not "contains Care". Her second assignment is
    real and it is not a web-login role; a document that listed it under `roles`
    would be publishing the composition §2 forbids, one layer before any session
    is issued.
    """
    users = mock_idp.published_users()
    assert users, "The registration document publishes nobody, so there is nobody to find."

    carried = launch_only_users(mock_idp)
    assert len(carried) == 1, "\n".join(
        [
            f"{len(carried)} of the {len(users)} published people carry a `launch_only_roles` "
            "assignment; E0-16 seeds exactly one.",
            *(f"  {user}" for user in users),
            "",
            "She is the case that proves the doors belong to the assignment rather than to the "
            "person: she signs in here for Care work and launches from the mock LMS for teaching. "
            "E0-10 and E0-18 both reuse her, and with nobody carrying the marker, every other "
            "assertion in this module about Care is satisfied by a seed she is missing from.",
        ]
    )

    user = carried[0]
    stated = roles_in_claims({"roles": user.get("roles") or []})
    assert stated == {"CARE"} and len(user.get("roles") or []) == 1, (
        f"The two-hat person is published with `roles` {user.get('roles')!r}. It has to be Care "
        "and nothing else: her teaching assignment belongs to the other door, and SPEC §2 makes "
        "Care non-composable with reporting roles — a document that lists both under `roles` has "
        "published the composition before any session exists to carry it."
    )
    assert user.get("launch_only_roles"), (
        f"The two-hat person's `launch_only_roles` is {user.get('launch_only_roles')!r}. That "
        "member is what records the assignment this door may not honour."
    )
    assert user.get("lms_user_id"), (
        f"The two-hat person carries `lms_user_id` {user.get('lms_user_id')!r}. ADR 0058 makes it "
        "the member that says which LMS user she is, and it is how E0-18 finds the same person "
        "on the launch door — without it the two doors resolve to two people."
    )


def test_the_two_hat_person_signs_in_holding_care_and_no_launch_only_role(mock_idp: Any) -> None:
    """Criterion 8, over the person it names rather than over whoever holds Care.

    She is selected by identity — the login form's own choice for the person the
    registration document publishes — so a seed she has been removed from fails
    here instead of quietly having nothing to check. That selection is the whole
    difference between this test and `test_a_session_holding_care_states_no_
    reporting_role` above, which stays because the two fail for different reasons:
    that one catches a session built from every assignment a person holds, and
    this one catches the person disappearing.

    Both halves are asserted on the one session: Care is there, and the assignment
    that belongs to the other door is not. §2: "Care is deliberately not
    composable with reporting roles — its sole power is the threat queue, kept
    isolated so safety re-identification never rides alongside routine oversight
    access."
    """
    user = two_hat_user(mock_idp)
    attempt = mock_idp.begin()
    identity = mock_idp.identity_of(user, attempt)

    login = mock_idp.login(identity)
    stated = mock_idp.roles(login)

    assert "CARE" in stated, (
        f"Signing in as the two-hat person ({identity}) produced a session stating "
        f"{sorted(stated)}. She holds a Care assignment and web login is the door she uses for "
        "it, so a session without Care in it is the queue she cannot reach."
    )
    assert not stated & set(LAUNCH_ONLY_ROLES), (
        f"Her session states {sorted(stated & set(LAUNCH_ONLY_ROLES))} beside Care. That "
        "assignment is real and it enters by LTI launch: the launch context is where her teaching "
        "lives, and a web session carrying it hands the one role that can re-identify a student "
        "to a person acting in their teaching capacity — which is the composition §2 exists to "
        "prevent, arriving through the door rather than through a union."
    )


def test_the_lms_user_id_the_provider_publishes_names_a_user_the_platform_will_launch(
    mock_idp: Any, mock_platform: Any
) -> None:
    """The two mocks agree about who she is, which nothing else checks.

    `lms_user_id` is a claim this provider makes about the *other* mock's seed,
    and the two are edited by different tickets. Rename the instructor in
    `mock-lms/app/seed.py` and both suites stay green while `/mock/registration`
    publishes an id matching no LMS user — E0-18 then discovers it as a browser
    test that finds her on one door and not on the other, which is an expensive
    place to find a two-character difference.

    Both mocks are fetchable in process, so the comparison costs one launch. It is
    made against a launch the platform actually signs rather than against the
    option value on its page: the `sub` in an `id_token` is what a tool resolves a
    person by, and a page that offers a login hint the launch does not honour
    would satisfy the weaker check.
    """
    user = two_hat_user(mock_idp)
    published = str(user.get("lms_user_id") or "")
    assert published, "The two-hat person carries no `lms_user_id`, so there is nothing to match."

    offers = mock_platform.require_offers()
    hints = {offer.parameters.get("login_hint") for offer in offers}
    assert published in hints, "\n".join(
        [
            f"The provider publishes `lms_user_id` {published!r}, and the mock platform offers no "
            "launch for that user.",
            f"  the platform's launch page offers: {sorted(hint for hint in hints if hint)}",
            "",
            "The two mocks are the two doors of SPEC §2 and this member is the only thing tying "
            "them to one person. Nothing else compares them: rename the user on either side and "
            "both suites stay green while the doors resolve to two different people.",
        ]
    )

    hers = next(offer for offer in offers if offer.parameters.get("login_hint") == published)
    launch = mock_platform.mint(hers)
    assert str(launch.claims.get("sub")) == published, (
        f"The platform signed a launch for login hint {published!r} whose `sub` is "
        f"{launch.claims.get('sub')!r}. A tool resolves a person by the `sub` in the `id_token`, "
        "not by the hint the page offered, so those two disagreeing is the same failure one step "
        "further in."
    )


# ---------------------------------------------------------------------------
# The form itself, as far as it can be judged without a browser.
# ---------------------------------------------------------------------------


def test_the_login_form_can_be_addressed_without_a_brittle_selector(mock_idp: Any) -> None:
    """E0-16's scope: "a login form simple enough for a Playwright test to drive".

    The Playwright test is E0-18's and cannot be written here, but the property
    it needs can be checked without a browser: every control a person operates is
    addressable by something stable — a `<label for>` pointing at its `id`, a
    `data-testid`, or an `aria-label` — rather than by its position in the
    markup. Those are what `get_by_label` and `get_by_test_id` resolve, and the
    alternative is the nth-child selector that breaks the first time a paragraph
    moves.

    Three hooks are accepted rather than one, because which of them to use is the
    implementer's choice and E0-18's, not this file's. Hidden fields are exempt:
    nobody clicks them. A submit control is required separately — a form with no
    way to submit it is one only a script can send.
    """
    attempt = mock_idp.begin()
    form = mock_idp.require_login_form(attempt)

    operable = [
        control
        for control in form["controls"]
        if control.get("type", "text").lower() != "hidden"
        and not (control.get("tag") == "button" or control.get("type", "").lower() == "submit")
    ]
    assert operable, (
        f"The login form declares no control a person could operate — it declares "
        f"{form['controls']}. E0-16 asks for a form a browser-driven test can drive, and a form "
        "with nothing in it drives nothing."
    )

    labelled = {value for value in form["labels"] if value}
    unaddressable = [
        control
        for control in operable
        if not (
            (control.get("id") and control["id"] in labelled)
            or control.get("data-testid")
            or control.get("aria-label")
        )
    ]
    assert not unaddressable, "\n".join(
        [
            "Controls on the login form carry no stable hook for a browser-driven test:",
            *(f"  {control}" for control in unaddressable),
            "",
            f"The form declares labels for {sorted(labelled)}. E0-16's scope asks for 'a login "
            "form simple enough for a Playwright test to drive without brittle selectors', and "
            "E0-18 is the ticket that has to drive it. A `<label for>` matching the control's "
            "`id`, a `data-testid` or an `aria-label` all satisfy this; position in the markup "
            "does not.",
        ]
    )

    submits = [
        control
        for control in form["controls"]
        if control.get("tag") == "button" or control.get("type", "").lower() == "submit"
    ]
    assert submits, (
        f"The login form declares no submit control (it declares {form['controls']}). A form a "
        "person cannot submit is one only a script can send, which is the opposite of what "
        "E0-18 needs to click through."
    )


# ---------------------------------------------------------------------------
# `login_hint` pre-selects a person on the login form. The developer test console
# links to the tool's web door with a `login_hint`, the tool forwards it to this
# provider's authorization request (OIDC Core 1.0 §3.1.2.1), and the form marks
# the matching option `selected` so a developer lands on the person they clicked.
# It is presentational only: the `data-testid`s do not move, every option is still
# present, and an unknown or absent hint selects nothing — the form as it renders
# today.
# ---------------------------------------------------------------------------

# The subject nobody is seeded under, used for the "unknown hint selects nothing"
# half. It says what it is in the value, so one appearing in a form or a log is
# traceable to this file.
UNSEEDED_SUBJECT = "mock-idp-user-nobody-e0-dev-console"


class Option(NamedTuple):
    """One `<option>`: the value it would submit and whether it is pre-selected."""

    value: str
    selected: bool


class OptionReader(HTMLParser):
    """Every `<option>` on a page, as a value/selected pair.

    A parser rather than a regular expression because the property under test is
    exactly which `<option>` carries the `selected` attribute, and a pattern over
    markup answers a question that only looks the same (`docs/MISTAKES.md` entry 3).
    `selected` is a boolean attribute, so it is read as present-or-absent —
    catching `selected`, `selected=""` and `selected="selected"` alike — because a
    check for one spelling would pass a form using another. Its own control test is
    below.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.options: list[Option] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "option":
            return
        names = {name.lower() for name, _ in attrs}
        value = next((value or "" for name, value in attrs if name.lower() == "value"), "")
        self.options.append(Option(value=value, selected="selected" in names))


def options_in(markup: str) -> list[Option]:
    """Parse `markup` and hand back every option it declares."""
    reader = OptionReader()
    reader.feed(markup)
    reader.close()
    return reader.options


def selected_values(markup: str) -> list[str]:
    """The values of the pre-selected options on a page, in document order."""
    return [option.value for option in options_in(markup) if option.selected]


def web_subject(mock_idp: Any, role: str) -> str:
    """The subject the provider publishes for the one web-login person holding `role`."""
    holders = [
        str(user["sub"])
        for user in mock_idp.published_users()
        if role in (user.get("roles") or []) and user.get("web_login") and user.get("sub")
    ]
    assert len(holders) == 1, (
        f"The registration document publishes {len(holders)} web-login people holding {role!r}; "
        "this test names one so the pre-selection is asserted about a known subject."
    )
    return holders[0]


def offered_subjects(mock_idp: Any) -> list[str]:
    """Every subject the provider publishes as a web-login identity (ADR 0058)."""
    return [
        str(user["sub"])
        for user in mock_idp.published_users()
        if user.get("web_login") and user.get("sub")
    ]


def test_the_option_reader_reads_the_selected_attribute_in_every_spelling() -> None:
    """The control on the pre-selection assertions (`docs/MISTAKES.md` entry 3).

    Those assertions turn on one `<option>` carrying `selected` and the rest not; a
    reader that saw the attribute on nothing would make "the right one is selected"
    and "nothing is selected" both pass, and both would read as the provider being
    correct. So it is shown reading a bare `selected`, both quoted spellings, and an
    option with none — before it is trusted about the form.
    """
    markup = (
        "<select>"
        '<option value="a">A</option>'
        '<option value="b" selected>B</option>'
        '<option value="c" selected="">C</option>'
        '<option value="d" selected="selected">D</option>'
        "</select>"
    )

    parsed = options_in(markup)

    assert parsed == [
        Option("a", False),
        Option("b", True),
        Option("c", True),
        Option("d", True),
    ], (
        f"The option reader parsed {parsed}. Every pre-selection assertion below is made with it, "
        "and it has to recognise a bare boolean attribute and both quoted spellings — a form is "
        "free to use any of them — while leaving an option with none unselected."
    )


def test_a_login_hint_pre_selects_that_persons_option_and_no_other(mock_idp: Any) -> None:
    """**Dies if the hint pre-selects nothing**, and dies if it selects more than one.

    A `login_hint` naming a seeded web subject renders a form whose selected option
    is that subject and whose every other option is present and unselected. That is
    the whole of the console's convenience: a developer clicks a person, the form
    opens with that person chosen, and one submit signs them in.

    Two near-misses are ruled out. A form that pre-selected the hinted person and
    dropped the others would make the wrong developer unable to switch — so the full
    offered set is required present. A form that marked several options — the hinted
    one and whatever a browser defaults to — would submit ambiguously, so exactly
    one selection is required. The `data-testid`s are asserted intact, because the
    console and the Playwright specs address the form by them and a pre-selection
    that renamed a control would break the click it exists to serve.
    """
    hint = web_subject(mock_idp, "DEAN")
    attempt = mock_idp.begin(login_hint=hint)
    mock_idp.require_login_form(attempt)
    body = attempt.response.text

    selected = selected_values(body)
    assert selected == [hint], (
        f"A login form rendered for `login_hint={hint!r}` marks {selected} selected; it must mark "
        f"exactly {[hint]}. A hint that selects nothing is the feature missing, and one that selects "
        "several submits an ambiguous choice."
    )

    present = {option.value for option in options_in(body)}
    missing = [subject for subject in offered_subjects(mock_idp) if subject not in present]
    assert not missing, (
        f"The form rendered for `login_hint={hint!r}` no longer offers {missing}. Pre-selecting one "
        "person must not remove the others — a developer has to be able to pick somebody else."
    )

    for testid in ("mock-idp-identity", "mock-idp-submit"):
        assert testid in body, (
            f"The form rendered for a `login_hint` no longer carries `data-testid={testid!r}`. The "
            "console and E0-18's Playwright specs address the form by these, and pre-selection is "
            "presentational — it does not move the hooks."
        )


@pytest.mark.parametrize(
    "case,login_hint",
    [
        ("an unknown subject", UNSEEDED_SUBJECT),
        ("no login_hint at all", None),
    ],
)
def test_an_unknown_or_absent_login_hint_selects_nothing(
    mock_idp: Any, case: str, login_hint: str | None
) -> None:
    """The pair for the pre-selection test: the form renders as today when it cannot pre-select.

    **Dies if the provider marks an option `selected` for a hint it cannot place**,
    or if it defaults a selection when none was hinted. A `login_hint` naming nobody
    seeded, and no hint at all, both leave the form exactly as it renders now — no
    option pre-selected — so a developer sees the plain list. Without this, a
    provider that always selected its first option would satisfy the test above for
    the wrong reason and pre-select the wrong person on every unhinted login.

    The premise is guarded: the form still has to offer options, so a form that
    selected nothing because it rendered nothing would fail here rather than pass.
    """
    attempt = mock_idp.begin() if login_hint is None else mock_idp.begin(login_hint=login_hint)
    mock_idp.require_login_form(attempt)
    body = attempt.response.text

    assert options_in(body), (
        f"The login form for {case} offers no options at all, so 'nothing is selected' is a fact "
        "about an empty form rather than about pre-selection."
    )
    selected = selected_values(body)
    assert selected == [], (
        f"The login form for {case} pre-selects {selected}. A hint the provider cannot place — and "
        "the absence of one — leaves the form as it renders today, with nothing chosen; a default "
        "selection would sign in whoever happened to be first."
    )
