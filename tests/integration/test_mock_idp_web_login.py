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

**What this module cannot see, stated rather than implied.** E0-16 seeds "one
person who holds **both** a Care assignment and an instructor assignment", and
the whole point of that person is that the instructor half is invisible from this
door. Nothing here can identify her by name, because nothing in the ticket says
how a test would — so criterion 8 is asserted over *every* session that holds
Care: each one holds no reporting role and carries no purview. That is a stronger
statement than one about a named person and a weaker one in a single respect,
which is that it cannot prove the two-hat person was seeded at all. If E0-10 and
E0-18 are to reuse this fixture, the ticket needs to say where a test reads the
seed from — the mock platform publishes its own registration as a document
(ADR 0036), which is the shape that would answer it.
"""

from typing import Any

import pytest

# The six roles E0-16 seeds for web login, spelled as this project spells roles.
# The ticket's own list — "VPAA, dean, chair, lead faculty, Care, and admin" —
# transcribed rather than derived, so a seed that quietly loses one fails here by
# name instead of passing unnoticed. That enumeration *is* criterion 6.
WEB_LOGIN_ROLES = ("VP_ACADEMICS", "DEAN", "CHAIR", "LEAD_FACULTY", "CARE", "ADMIN")

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

# Words that name the field a login form picks a person with, if the form offers
# more than one choice. Only consulted when there is an ambiguity to resolve.
IDENTITY_FIELD_HINTS = ("user", "login", "identity", "account", "sub", "person", "email", "name")

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


def identity_field(form: dict[str, Any]) -> str:
    """The name of the field a login form picks a person with.

    A login form offering seeded identities offers them under one name — the
    `<select>`, the radio group, the named submit buttons. Where a form offers
    more than one set of choices, the one whose name reads as a person is taken,
    and an ambiguity this cannot resolve stops rather than guesses: choosing
    would make the refusal test below submit the wrong field and pass for a
    reason unrelated to what it asserts.
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
        f"The login form offers choices under {choices}, and this cannot tell which one names the "
        "person signing in. Criterion 7 needs to submit an identity this provider does not offer, "
        "and submitting the wrong field would make the refusal a fact about something else. "
        "`IDENTITY_FIELD_HINTS` in this module is the one line that changes."
    )


def sessions_with(provider: Any, logins: list[Any], roles: tuple[str, ...]) -> list[Any]:
    """Every session in `logins` stating any of `roles`."""
    return [login for login in logins if provider.roles(login) & set(roles)]


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
    submission[identity_field(form)] = LAUNCH_ONLY_SUBJECTS[case]

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
