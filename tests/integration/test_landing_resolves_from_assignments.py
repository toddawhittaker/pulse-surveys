"""Which view a door lands a person on, decided by rows — ticket E1-13.

The second entry of `docs/tickets/e1/carried-from-e0.md` is this module's brief.
`backend/app/services/landing.py` mapped a verified token's roles claim to one of
five empty views; that was honest for E0's empty pages and "is not how the system
decides anything afterwards". From this ticket on the landing comes from the
**assignment model**: the session's own person, their live assignments filtered by
the entered door's permission column (ADR 0026), and — at the launch door only —
enrollment as the student fallback (ADR 0028, SPEC §2.1).

**Everything here is driven through a real door.** The rule under test is what a
door answers, and a test that called the resolver directly would say nothing about
whether either router calls it: the pure half is
`tests/unit/test_chosen_landing.py`, and this is the half that needs a launch, a
login and rows a second connection can see.

**Every row is written in the open.** `tests/fixtures/landing.py` will seed a
launch-driving suite's ground in one call, and this module deliberately does not
use it: which assignment a person holds *is* the question here, so a fixture that
composed the person would be handing back its own answer (`docs/MISTAKES.md`
entry 30). Each test writes the `person`, `user`, linkage, assignment and
enrollment rows it means, through `web_identity`, `committed_rows.graph` and
`enrol`, and says what it expects to fall out.

**Boundary pairs, both directions, everywhere.** A door that answered the
no-access page to everybody would satisfy every refusal below, and a door that
landed everybody would satisfy every landing. So each rule is posed twice, one row
apart: Care at the web door beside Care at a launch, an enrollment ending today
beside one that ended yesterday, an instructor assignment beside the same person's
live enrollment. The round-3 lesson this suite keeps learning is that predictions
about which side holds the hole are wrong about half the time.

**What the claims still lawfully decide** (work order D11). "The token's roles
claim stops deciding anything beyond authentication context" means the *landing*.
§7.3's provisioning and E1-11's roster sync go on reading the roles claim, which
is E1-10 and E1-11's settled design and outside this ticket. So nothing here
asserts that claims decide nothing anywhere; what the two criterion-2 tests below
assert is narrower and is the whole of what the criterion asks — that the landing
comes from the rows.

**Criterion 2 is posed with genuinely signed launches rather than with a re-signed
one**, and that is a deliberate strengthening rather than a shortcut. The mock
platform signs a Learner launch and an Instructor launch for two different
subjects; giving the Learner's subject an instructor assignment, and the
Instructor's subject nothing but a live enrollment, makes each launch's claims
disagree with its rows in the direction the criterion names — with no harness in
the signing path at all. The launch-door suite's `re_signed_launch` seam exists
for claims *no seeded person produces*; these two are produced by the platform
itself.

**The environment** (`docs/MISTAKES.md` entry 40): both doors are built by
`tool_doors` over `configured_env`, so `ENVIRONMENT` is the development name and
the container's `DATABASE_URL` is laid down before `app.main` is imported. The
five tests whose subject is *which day it is* set `INSTITUTION_TIMEZONE`
themselves, before the door is built, because the application reads it into
`Settings` at import and a value set afterwards would reach nothing.
"""

import ast
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `launch_driver`, `launch_driver_in`, `launch_ground` and `provisioning_contract`
# come from `tests/fixtures/provisioning.py`; `web_door`, `web_identity`,
# `provider_issuer`, `published_person` and `published_subject` from
# `tests/fixtures/web_identity.py`; `enrol` and `landing_contract` from
# `tests/fixtures/landing.py`; `committed_rows` and `application_session` from
# `tests/fixtures/authz_data.py`. All are reached as fixtures rather than
# imported: an import of a fixtures module by name depends on where pytest put
# `tests/` on `sys.path`, and an import error is not a red.

SUBJECT_CLAIM = "sub"

# The two roles §2.1 gives the web door and no other, the two it gives a launch,
# and the leadership role both doors admit. Spelled as SPEC §2.1's table spells
# them, which is also how `tests/fixtures/supervision.py::ROLE_ALIASES` keys them.
INSTRUCTOR_ROLE = "INSTRUCTOR"
DEAN_ROLE = "DEAN"
CARE_ROLE = "CARE"
ADMIN_ROLE = "ADMIN"

# E1-04's five route group names, which E1-08's `fragment_redirect` builds
# `/app/<segment>` from. Spelled here as `tests/integration/test_web_login_door.py`
# and `test_the_launch_views_name_nobody.py` spell them — one copy per module is
# this suite's established convention for a name that belongs to a *route table*
# rather than to any one ticket, and `tests/fixtures/landing.py::landing_contract`
# carries the same five for a module that would otherwise need them twice.
STUDENT_ROUTE = "student"
INSTRUCTOR_ROUTE = "instructor"
LEADERSHIP_ROUTE = "leadership"
CARE_ROUTE = "care"
ADMIN_ROUTE = "admin"

# How far back a window that is certainly live starts, and how far ahead a term
# that certainly contains today runs. Wide enough that no timezone offset can move
# a test whose subject is not the day; the five tests whose subject *is* the day
# use exact edges instead.
COMFORTABLY_LIVE_DAYS = 30

# The zone the two criterion-5 edge tests **set**, through
# `drive_a_student_launch_over`, before the door is built. `.env.example`
# configures `America/New_York` and naming it here rather than inheriting it is
# `docs/MISTAKES.md` entry 40's rule: a test whose subject reads the process
# environment states the value it runs under.
#
# Every other test here uses it only to compute a date comfortably in the past for
# a window `COMFORTABLY_LIVE_DAYS` wide, and sets nothing — which is honest rather
# than sloppy, because a window that wide contains the institution's today under
# any zone at all, so no assertion outside those two depends on which zone is
# configured.
INSTITUTION_TIMEZONE_VARIABLE = "INSTITUTION_TIMEZONE"
A_STATED_TIMEZONE = "America/New_York"

# Two zones at the far ends of the offset range, so that at **every** instant at
# least one of them is on a different calendar date from UTC. Kiritimati is UTC+14
# and Niue is UTC-11; between them they cover the clock, which is what makes the
# institution's-day test runnable at any hour rather than only overnight. Copied
# from `tests/integration/test_provisioning_reads_its_environment_and_its_day_from_settings.py`,
# which needs the same arithmetic for the same reason (E1-11 closed deferred E1-10
# item 2 with it); if one of these is ever renamed in tzdata it is wrong in both.
CANDIDATE_ZONES = ("Pacific/Kiritimati", "Pacific/Niue")

# The view D4 re-versions, read over the connection the application serves
# requests on. Schema-qualified, and the column names are ADR 0026's own.
VIEW_SCHEMA = "public"
ASSIGNMENT_SCOPE_RELATION = "public.assignment_scope"

# How much of a page is printed around a suspected leak, so a failure can be acted
# on in one read.
CONTEXT_CHARACTERS = 80


def a_zone_whose_date_differs_from_utc() -> tuple[Any, date, date]:
    """A zone where today is not UTC's today, with both dates.

    A failure here is a failure of arithmetic rather than of the code under test,
    so it says so: one of the two is UTC+14 and the other UTC-11, and between them
    they differ from UTC at every instant.
    """
    today = datetime.now(UTC).date()
    for name in CANDIDATE_ZONES:
        zone = ZoneInfo(name)
        local = datetime.now(zone).date()
        if local != today:
            return zone, local, today
    pytest.fail(
        f"Neither {list(CANDIDATE_ZONES)} is on a different calendar date from UTC right now "
        f"({today}), which cannot happen. Either a zone has been renamed in the tzdata this "
        "container carries, or this arithmetic is wrong — and until it is fixed the test below "
        "cannot pose its question at all."
    )


def today_in(zone_name: str) -> date:
    """The institution's current day, computed the way E1-11 ruled provisioning computes it.

    `datetime.now(ZoneInfo(settings.institution_timezone)).date()` — never UTC's
    day and never `CURRENT_DATE`. Every window seeded below is built from this, so
    a test and the code under test are asking the same question about the same
    calendar.
    """
    return datetime.now(ZoneInfo(zone_name)).date()


# ---------------------------------------------------------------------------
# Reading what a door answered.
# ---------------------------------------------------------------------------


def session_cookie_names() -> tuple[str, str]:
    """`SESSION_COOKIE` and `CSRF_COOKIE`, read out of the shared session module.

    Read rather than transcribed so this module and the doors cannot end up
    meaning two different cookies (`docs/MISTAKES.md` entry 13).
    """
    try:
        from app.services.session import CSRF_COOKIE, SESSION_COOKIE
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`app.services.session` does not import ({missing}). E1-08's module layout names "
            "`SESSION_COOKIE`/`CSRF_COOKIE` there and both doors issue through it."
        )
    return SESSION_COOKIE, CSRF_COOKIE


def cookie_names_set_by(response: Any) -> set[str]:
    """The names of every cookie a response sets, without asserting there are any."""
    return {header.split("=", 1)[0].strip() for header in response.headers.get_list("set-cookie")}


def landed_on(response: Any, route: str, what: str) -> str:
    """A door landed this person on `/app/<route>#session=<token>`, and the token itself.

    E1-08's interface ruling, adopted unchanged by E1-09: a landing is a `302`
    whose `Location` is `/app/<segment>#session=<token>`, with the session cookie
    beside it. The exact-prefix check is what makes "she landed on leadership"
    different from "she landed somewhere that mentions leadership".

    **Every assertion in this module about *which* view is this check**, so a
    refusal, a calm page or a redirect to another role all fail here rather than
    slipping past a substring search.
    """
    session_cookie, _ = session_cookie_names()

    assert response.status_code in (302, 303, 307), (
        f"{what} answered {response.status_code} rather than the redirect a door issues for a "
        f"session it minted. Body begins {response.text[:400]!r}."
    )
    location = response.headers.get("location") or ""
    prefix = f"/app/{route}#session="
    assert location.startswith(prefix), (
        f"{what} redirected to `{location}`, which does not start with `{prefix}`. E1-13 resolves "
        "the landing from the assignment model, so the route named here is the view this person's "
        "rows entitle them to."
    )
    token = location[len(prefix) :]
    assert token, f"{what} redirected to `{location}`, whose `session=` fragment is empty."
    assert session_cookie in cookie_names_set_by(response), (
        f"{what} redirected to `/app/{route}` and set no `{session_cookie}` cookie (it set "
        f"{sorted(cookie_names_set_by(response))}). A person sent to a route with no session is on "
        "a page they cannot use."
    )
    return token


def no_session_was_issued(response: Any, what: str) -> None:
    """Nothing in this response hands the caller a session. The forbidden state.

    Three ways a session could leave a door, and all three are checked: a door
    that stopped setting the cookies and went on redirecting with the fragment
    would satisfy a cookie-only check while handing the token over
    (`docs/MISTAKES.md` entry 2 — assert the forbidden state, and assert all of
    it).
    """
    session_cookie, csrf_cookie = session_cookie_names()
    handed = sorted(cookie_names_set_by(response) & {session_cookie, csrf_cookie})
    assert not handed, (
        f"The tool set {handed} while answering {what}. That is a session issued on a path where "
        "nothing entitled this person to a view."
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


def the_no_access_page(response: Any, contract: Any, doors: Any, what: str) -> None:
    """The calm answer when identity resolved and nothing here gives this person a view.

    Work order D5: status **200** — nothing went wrong — testid `no-access`, a
    message built from constants that "names nobody, repeats nothing from any
    token". Four things are checked and each is a different failure: a 4xx is
    fail-closed and is not what the person is owed; a missing testid means they
    were met with somebody else's words; a landing testid means they were met with
    somebody else's *screen*; and a session means the door decided they had a view
    after all and merely declined to say which.
    """
    assert response.status_code == 200, (
        f"The tool answered {response.status_code} to {what}. E1-13 replaces both doors' 'no role "
        "this tool has a view for' refusals with a calm page: nothing went wrong, so the answer is "
        f"a 200 somebody is meant to read. Body begins {response.text[:400]!r}."
    )
    assert contract.no_access_testid in response.text, (
        f"The tool answered {what} with a 200 carrying no `{contract.no_access_testid}` testid "
        f"(body begins {response.text[:400]!r}). That testid is E1-13's contract for this page and "
        "it is what tells this suite — and E1-15's browser proof — which of the four non-landing "
        "answers the person actually got."
    )
    landings = [testid for testid in doors.landing_testids if testid in response.text]
    assert not landings, (
        f"The tool answered {what} with a page carrying {landings}. A person whose rows entitle "
        "them to no view lands on nobody's."
    )
    no_session_was_issued(response, what)


def around(body: str, needle: str) -> str:
    """The text a suspected leak sits in, so a failure can be acted on in one read."""
    at = body.find(needle)
    if at < 0:  # pragma: no cover - only reached if the caller found it another way
        return ""
    return body[max(0, at - CONTEXT_CHARACTERS) : at + len(needle) + CONTEXT_CHARACTERS]


def assert_the_page_names_none_of(response: Any, values: list[str], what: str) -> None:
    """The page repeats none of these strings, and the scan is shown able to find them.

    D5 makes the calm page take no argument at all, so there is nothing a caller
    can put into it — this is that property asserted from the outside, over the
    values a caller actually supplied. The canary is what stops a scan that has
    gone blind from reading exactly like a clean page (`docs/MISTAKES.md` entry
    3).
    """
    assert values, (
        f"This test has no identifier to look for on the page answering {what}, so its silence "
        "would be about a search with nothing to find."
    )
    canary = " ".join(values)
    assert all(value in canary for value in values), (
        "The scan below cannot find these strings in a sample built out of them, so its silence "
        "about the page means nothing."
    )
    leaked = sorted({value for value in values if value in response.text})
    assert not leaked, (
        f"The page answering {what} carries {leaked}. First occurrence: "
        f"{around(response.text, leaked[0])!r}. The calm page is built from constants and takes no "
        "argument, precisely so that nothing a caller chose — a subject, an address, a role name — "
        "can be echoed back out of it."
    )


# ---------------------------------------------------------------------------
# Seeding, written out rather than wrapped, so each test's rows are visible.
# ---------------------------------------------------------------------------


def platform_id_of(launch_driver: Any, web_identity: Any) -> Any:
    """The `lti_platform` row this suite's launches are signed by."""
    return launch_driver.registration.platform_row[web_identity.key_of("lti_platform")]


def a_launch_subject(launch_driver: Any, role_urn: str) -> tuple[Any, str]:
    """One offer the platform makes, and the subject its signed token carries.

    The subject is read off the *signed* claims rather than off the offer's form
    parameters, for the reason the launch-door suite gives: the form carries no
    roles at all, so the token is the only place the question can be answered, and
    reading it here means nothing in this module is a copy of
    `mock-lms/app/seed.py`.
    """
    offer = launch_driver.offer_for_role(role_urn)
    claims = launch_driver.claims_of(offer)
    subject = claims.get(SUBJECT_CLAIM)
    assert isinstance(subject, str) and subject, (
        f"The launch this platform signs for {role_urn!r} carries `{SUBJECT_CLAIM}` {subject!r}, so "
        "there is no subject to seed a `user` row for and the launch would resolve nobody."
    )
    return offer, subject


# ---------------------------------------------------------------------------
# The machinery, before anything is asserted with it. A must-be-green control:
# a red here means these tests are broken, not that the doors are.
# ---------------------------------------------------------------------------


def test_the_page_reader_finds_the_calm_page_and_refuses_a_landing_beside_it(
    landing_contract: Any, door_contract: Any, configured_env: dict[str, str]
) -> None:
    """The control on `the_no_access_page`: it finds what it looks for, and only that.

    **Dies if the reader passes a page that does not carry the testid**, which
    would make every refusal in this module true of a door that answers anything
    at all with a 200 — and **dies if it accepts a landing testid beside it**,
    which is how a door that rendered the wrong screen would slip past.

    Needs no implementation and is green now. If it is red, nothing else in this
    module means what it says (`docs/MISTAKES.md` entry 9: a guard nobody has
    watched catch its own case is a comment).

    `configured_env` is depended on and not used: `no_session_was_issued` imports
    `app.services.session` for the cookie names, and an application module may
    build a `Settings` at import.
    """

    class Headers:
        @staticmethod
        def get_list(_name: str) -> list[str]:
            return []

        @staticmethod
        def get(_name: str, default: Any = None) -> Any:
            return default

    class Page:
        status_code = 200
        text = f'<main data-testid="{landing_contract.no_access_testid}">nothing yet</main>'
        headers: Any = Headers()

    the_no_access_page(Page(), landing_contract, door_contract, "a page this test built")

    class WithALanding(Page):
        text = (
            f'<main data-testid="{landing_contract.no_access_testid}"></main>'
            f'<div data-testid="{door_contract.landing_testids[0]}"></div>'
        )

    with pytest.raises(AssertionError):
        the_no_access_page(
            WithALanding(), landing_contract, door_contract, "a page carrying a landing view too"
        )

    class WithoutTheTestid(Page):
        text = "<main>nothing yet</main>"

    with pytest.raises(AssertionError):
        the_no_access_page(
            WithoutTheTestid(), landing_contract, door_contract, "a 200 carrying no testid"
        )


# ---------------------------------------------------------------------------
# Criterion 1 — each seeded person lands correctly, by door.
# ---------------------------------------------------------------------------


def test_a_launch_by_an_enrolled_person_holding_no_assignment_lands_on_the_student_route(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
) -> None:
    """Criterion 1, the student third: enrollment is the whole of a student's access.

    ADR 0028: "A student holds no `role_assignment` row, and one cannot be
    written… A student's access is resolved from `enrollment` — the row that says
    this user was in this section during this window." So the rows here are a
    `user` row for the launching subject and one live enrollment, and **no
    `person` row at all** — which is also the state E1-12 defines for a student
    session.

    **Dies while the landing comes from the roles claim**, which is HEAD: today
    this launch lands student because the token says Learner, and it would land
    student with no enrollment row anywhere. The pair that makes this mean
    "enrollment decided" is
    `test_a_launch_by_a_person_with_no_assignment_and_no_enrollment_lands_on_the_calm_page`
    below, which drives the identical launch with the enrollment left out.

    **Dies if the assignment read is the only read** — a resolver that asks one
    question rather than ADR 0028's two lands this person nowhere.
    """
    offer, subject = a_launch_subject(launch_driver, provisioning_contract.learner_role_urn)
    launch_ground(provisioning_contract.label_of(launch_driver.claims_of(offer)))

    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=subject
    )
    section_id = committed_rows.graph.scope("section")
    committed_rows.commit()
    enrol.enrol(
        user_id=user_id,
        section_id=section_id,
        started_on=today_in(A_STATED_TIMEZONE) - timedelta(days=COMFORTABLY_LIVE_DAYS),
        ended_on=None,
    )

    response, _ = launch_driver.launch(offer)

    landed_on(response, STUDENT_ROUTE, "an enrolled person's launch")


def test_a_launch_by_a_person_holding_an_instructor_assignment_lands_on_the_instructor_route(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """Criterion 1, the instructor third: a live assignment, reached through the linkage.

    §2.1 gives the instructor an assignment scoped to a section and the LTI launch
    as its door, and E1-12 is what makes the launching subject reachable from one:
    `sub` → `user` → `person` → `role_assignment`.

    **Dies if the linkage is not consulted** — a door that resolved the landing
    from anything but the person behind the subject lands this person on whatever
    her token happens to say.
    """
    offer, subject = a_launch_subject(launch_driver, provisioning_contract.instructor_role_urn)
    launch_ground(provisioning_contract.label_of(launch_driver.claims_of(offer)))

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=subject
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    committed_rows.graph.assign(INSTRUCTOR_ROLE, person=person_id)
    committed_rows.commit()

    response, _ = launch_driver.launch(offer)

    landed_on(response, INSTRUCTOR_ROUTE, "an instructor's launch")


def test_the_dean_reaches_the_same_leadership_view_through_both_doors(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """Criterion 1's hardest third: "with the Dean's two doors asserted as the *same* view".

    §2.1's table gives every reporting role — leadership included — the LTI launch
    *and* the web login, and §2 says why the two agree: "Both doors resolve to the
    same identity and the same views." One `person` row holds one `DEAN`
    assignment; her IdP subject reaches it through `web_login_subject` and her LMS
    subject through `user.lms_user_id` and ADR 0024's link.

    **Both doors in one test on purpose.** Split in two, each half is satisfied by
    a seed the other is missing from, and the fact worth asserting — that one
    person's two doors agree — is stated nowhere.

    **The two routes are compared to each other as well as to `leadership`**,
    which is the criterion's own wording. A door that landed her on two different
    role routes would pass two separate single-door tests that each happened to
    name the route that door chose.

    **Dies if either door keeps a role rule of its own**, which is the shape the
    carried entry describes E0-18 shipping: "The seam is one function,
    `landing_role_for`, taking which door it is answering for; both routers call it
    and neither has a role rule of its own." E1-13 keeps that property while
    changing what the seam reads.
    """
    hers = published_person(web_door.provider, DEAN_ROLE)
    offer, lms_subject = a_launch_subject(launch_driver, provisioning_contract.learner_role_urn)
    launch_ground(provisioning_contract.label_of(launch_driver.claims_of(offer)))

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=lms_subject
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(hers), person_id=person_id
    )
    committed_rows.graph.assign(DEAN_ROLE, person=person_id)
    committed_rows.commit()

    by_web = web_door.login_as(hers)
    by_launch, _ = launch_driver.launch(offer)

    landed_on(by_web, LEADERSHIP_ROUTE, "the dean's web login")
    landed_on(by_launch, LEADERSHIP_ROUTE, "the dean's launch")

    web_location = by_web.headers.get("location") or ""
    launch_location = by_launch.headers.get("location") or ""
    assert web_location.split("#", 1)[0] == launch_location.split("#", 1)[0], (
        f"Her web login landed on `{web_location.split('#', 1)[0]}` and her launch on "
        f"`{launch_location.split('#', 1)[0]}`. §2: 'Both doors resolve to the same identity and "
        "the same views' — one person, one `DEAN` assignment, and two doors that both admit it "
        "(§2.1's table), so a difference here is a door with a role rule of its own."
    )


def test_the_care_officer_lands_on_care_at_the_web_door(
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """Criterion 1, the Care third — and the accepting half of the door pair below.

    §2.1's table gives Care the web login and nothing else: "Care and Admin are web
    login only (their work has no launch context)". §6.2 makes this the one surface
    that can re-identify a student, which is why the pair below matters as much as
    this does.

    **Dies if a `CARE` assignment stops reaching this door at all**, which is what
    a `permits_web_login` list written as an exclusion, or a door filter applied
    twice, would produce — and which every "Care is unreachable from a launch"
    assertion in this repository would report as a success.
    """
    hers = published_person(web_door.provider, CARE_ROLE)
    person_id = web_identity.person()
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(hers), person_id=person_id
    )
    committed_rows.graph.assign(
        CARE_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.commit()

    response = web_door.login_as(hers)

    landed_on(response, CARE_ROUTE, "the Care officer's web login")


def test_the_administrator_lands_on_admin_at_the_web_door(
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """Criterion 1, the admin third, and the last of §2.1's five landings.

    **Dies if the resolution falls through to a default.** Admin is last in the
    recorded precedence, so a resolver that landed everything it did not recognise
    on one route passes the leadership and Care tests above and fails here — which
    is the same reason E0-18's own suite put the admin case last.
    """
    theirs = published_person(web_door.provider, ADMIN_ROLE)
    person_id = web_identity.person()
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(theirs), person_id=person_id
    )
    committed_rows.graph.assign(
        ADMIN_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.commit()

    response = web_door.login_as(theirs)

    landed_on(response, ADMIN_ROUTE, "the administrator's web login")


# ---------------------------------------------------------------------------
# Criterion 2 — the claims say one thing and the rows say another.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_a_launch_whose_claims_say_instructor_lands_by_the_rows_and_never_on_instructor(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
) -> None:
    """Criterion 2, the direction that costs something: a claim cannot grant a view.

    The launch is the platform's own Instructor launch, signed, verified and
    correct in every claim — and the subject behind it holds no instructor
    assignment at all. Pulse's own records say she is enrolled in a section, so
    that is the view she gets. E0-09's criterion 10 is the rule underneath:
    "The launch or login establishes who someone is; this table establishes what
    they may do", and the person who administers the LMS controls what the roles
    claim says.

    **Dies against HEAD**, where the roles claim is the whole of the decision and
    this launch lands on the instructor view.

    **Dies against a resolver that keeps the claim as a fallback** — "no
    assignment? then believe the token" — which is the shape that survives a
    rewrite because it makes every existing door test go on passing.

    **What this does not say**, and deliberately (work order D11): that the roles
    claim decides nothing anywhere. §7.3's provisioning still reads it to tell a
    staff launch from a student one, which is E1-10's settled design; what stops
    here is its authority over the *landing*.
    """
    offer, subject = a_launch_subject(launch_driver, provisioning_contract.instructor_role_urn)
    claims = launch_driver.claims_of(offer)
    launch_ground(provisioning_contract.label_of(claims))
    assert provisioning_contract.instructor_role_urn in (
        claims.get(provisioning_contract.roles_claim) or []
    ), (
        "The launch this test drives does not state the Instructor role after all (it states "
        f"{claims.get(provisioning_contract.roles_claim)!r}), so its claims and its rows do not "
        "disagree and it poses no question."
    )

    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=subject
    )
    section_id = committed_rows.graph.scope("section")
    committed_rows.commit()
    enrol.enrol(
        user_id=user_id,
        section_id=section_id,
        started_on=today_in(A_STATED_TIMEZONE) - timedelta(days=COMFORTABLY_LIVE_DAYS),
        ended_on=None,
    )

    response, _ = launch_driver.launch(offer)

    landed_on(
        response,
        STUDENT_ROUTE,
        "a launch stating the Instructor role, by a subject holding no instructor assignment",
    )


def test_a_launch_whose_claims_say_learner_lands_on_instructor_when_the_rows_say_so(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """Criterion 2, the other direction, and the pair that makes the first one mean something.

    Without this, "a launch stating Instructor lands on student" is equally
    satisfied by a door that has stopped serving the instructor view at all. Here
    the platform signs a Learner launch and the subject behind it holds a live
    `INSTRUCTOR` assignment, so the answer has to be the instructor view — the
    claims are wrong in the other direction and the rows win again.

    **Dies against HEAD** for the same reason as its pair, and in the opposite
    direction: today this lands student.

    **Dies against a resolver that intersects the claim with the assignment** —
    "believe the rows, but only where the token agrees" — which passes the first
    test perfectly and is the natural way to write a cautious migration.
    """
    offer, subject = a_launch_subject(launch_driver, provisioning_contract.learner_role_urn)
    claims = launch_driver.claims_of(offer)
    launch_ground(provisioning_contract.label_of(claims))
    roles = claims.get(provisioning_contract.roles_claim) or []
    assert provisioning_contract.instructor_role_urn not in roles, (
        f"The launch this test drives states {roles!r}, which includes the Instructor role — so its "
        "claims and its rows agree and a landing on the instructor view would say nothing."
    )

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=subject
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    committed_rows.graph.assign(INSTRUCTOR_ROLE, person=person_id)
    committed_rows.commit()

    response, _ = launch_driver.launch(offer)

    landed_on(
        response,
        INSTRUCTOR_ROUTE,
        "a launch stating the Learner role, by a subject holding a live instructor assignment",
    )


# ---------------------------------------------------------------------------
# Criterion 4 — the precedence, pinned on people who hold two hats.
# ---------------------------------------------------------------------------


def test_a_person_holding_dean_and_care_lands_on_the_leadership_view_at_the_web_door(
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """Criterion 4's done-when, over the pair the carried entry names first.

    "**Leadership beats `CARE` beats `ADMIN`** on a web login. No seeded person
    holds two of those three; the two-hat person's second hat is on the other door,
    so she does not exercise this either." This is the fixture person that entry
    asks for: one `person`, a `DEAN` assignment on a college and a `CARE`
    assignment on the institution, both live, both admitting the web door.

    **The mutation this must kill, and it is the entry's own**: reverse
    `LANDING_PRECEDENCE`. Under it she lands on `/app/care`, and the carried entry
    measured that reversing both of `landing.py`'s orderings left 424 tests green.

    **Its near miss is the next test**, which pins the other end of the ordering:
    a transposition of only `CARE` and `ADMIN` leaves leadership above care and
    passes this one.

    **Its boundary pair is `test_the_care_officer_lands_on_care_at_the_web_door`**
    above — the same Care assignment, alone, landing on Care — so "she landed on
    leadership" cannot be a door that has stopped serving the Care view.

    §2's "Care is deliberately not composable with reporting roles" is about the
    *capability*, not the door: she may hold both assignments (§2.1's two-hat
    people), and what E1 decides here is only which empty screen she opens on.
    E9's switcher is what eventually supersedes this ordering.
    """
    hers = published_person(web_door.provider, DEAN_ROLE)
    person_id = web_identity.person()
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(hers), person_id=person_id
    )
    committed_rows.graph.assign(DEAN_ROLE, person=person_id)
    committed_rows.graph.assign(
        CARE_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.commit()

    response = web_door.login_as(hers)

    landed_on(
        response,
        LEADERSHIP_ROUTE,
        "a web login by a person holding both a dean's assignment and a Care assignment",
    )


def test_a_person_holding_care_and_admin_lands_on_the_care_view_at_the_web_door(
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The other end of the same ordering — the near miss the pair above cannot see.

    "Leadership beats `CARE` beats `ADMIN`" has two adjacent steps and a test at
    one end says nothing about the other. Swapping only `CARE` and `ADMIN` in
    `LANDING_PRECEDENCE` leaves the dean-and-Care person landing on leadership,
    and this person landing on admin.

    **The mutation this must kill**: transpose `CARE` and `ADMIN`.

    **Its boundary pair is
    `test_the_administrator_lands_on_admin_at_the_web_door`** above — the same
    `ADMIN` assignment, alone, landing on admin — so a green here is not a door
    that has stopped serving the admin view.
    """
    theirs = published_person(web_door.provider, ADMIN_ROLE)
    person_id = web_identity.person()
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(theirs), person_id=person_id
    )
    committed_rows.graph.assign(
        CARE_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.graph.assign(
        ADMIN_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.commit()

    response = web_door.login_as(theirs)

    landed_on(
        response,
        CARE_ROUTE,
        "a web login by a person holding both a Care assignment and an administrator's",
    )


def test_the_teaching_assistant_lands_on_instructor_rather_than_on_her_own_student_view(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
) -> None:
    """Criterion 4's launch-side pin — the carried entry's other unheld ordering.

    "**Instructor beats Learner** on a launch, for the teaching assistant enrolled
    as a learner in the course she grades. No seeded launch carries both roles."
    E1-13 restates it as assignments before enrollment (work order D2), and this is
    the person that makes it observable: one live `INSTRUCTOR` assignment and one
    live enrollment, on the same human, at the same moment.

    **The mutation this must kill**: consult the enrollment predicate first. Under
    it she lands on `/app/student`, and both of her rows are still perfectly
    legitimate — nothing else in this repository would notice.

    **Its two boundary pairs already exist**: the enrolled person with no
    assignment lands student, and the assigned person with no enrollment lands
    instructor. So a green here is neither a door that ignores enrollment nor one
    that ignores assignments.
    """
    offer, subject = a_launch_subject(launch_driver, provisioning_contract.learner_role_urn)
    launch_ground(provisioning_contract.label_of(launch_driver.claims_of(offer)))

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=subject
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    committed_rows.graph.assign(INSTRUCTOR_ROLE, person=person_id)
    section_id = committed_rows.graph.scope("section")
    committed_rows.commit()
    enrol.enrol(
        user_id=user_id,
        section_id=section_id,
        started_on=today_in(A_STATED_TIMEZONE) - timedelta(days=COMFORTABLY_LIVE_DAYS),
        ended_on=None,
    )

    response, _ = launch_driver.launch(offer)

    landed_on(response, INSTRUCTOR_ROUTE, "the teaching assistant's launch")


# ---------------------------------------------------------------------------
# Criterion 5 — the enrollment window's edges, and whose day they are measured in.
# ---------------------------------------------------------------------------


def drive_a_student_launch_over(
    monkeypatch: Any,
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
    *,
    zone: str,
    started_on: date,
    ended_on: date | None,
) -> tuple[Any, str]:
    """One launch by a subject whose only claim on a view is one enrollment window.

    The window is always the caller's, because which side of the boundary a date
    falls on is the whole of what criterion 5 asks. The zone is the caller's too,
    and it is **set before the door is built**: the application reads
    `INSTITUTION_TIMEZONE` into `Settings`, `tool_doors` imports `app.main` fresh
    per call, and a value set afterwards would reach nothing.
    """
    monkeypatch.setenv(INSTITUTION_TIMEZONE_VARIABLE, zone)
    driver = launch_driver_in()
    offer, subject = a_launch_subject(driver, provisioning_contract.learner_role_urn)
    launch_ground(provisioning_contract.label_of(driver.claims_of(offer)))

    user_id = web_identity.user(platform_id=platform_id_of(driver, web_identity), subject=subject)
    section_id = committed_rows.graph.scope("section")
    committed_rows.commit()
    enrol.enrol(user_id=user_id, section_id=section_id, started_on=started_on, ended_on=ended_on)

    response, _ = driver.launch(offer)
    return response, subject


def test_an_enrollment_whose_last_day_is_today_still_lands_a_student(
    monkeypatch: pytest.MonkeyPatch,
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
) -> None:
    """Criterion 5's inclusive edge: "the day they dropped is an enrolled day".

    ADR 0020 makes a section's end date its last day, and the work order (D3)
    carries the same convention onto an enrollment window: `started_on <= today AND
    (ended_on IS NULL OR ended_on >= today)`. So a person whose enrollment ends
    today is still enrolled today.

    **The mutation this kills**: `ended_on > :today`, the half-open reading — one
    character, and it takes today's survey away from everybody who dropped this
    morning.

    **Its pair is the next test**, one day earlier, which must not land. Neither is
    worth much alone: this one alone is satisfied by a resolver that ignores
    `ended_on` entirely.
    """
    zone = A_STATED_TIMEZONE
    today = today_in(zone)

    response, _ = drive_a_student_launch_over(
        monkeypatch,
        launch_driver_in,
        provisioning_contract,
        launch_ground,
        web_identity,
        enrol,
        committed_rows,
        zone=zone,
        started_on=today - timedelta(days=COMFORTABLY_LIVE_DAYS),
        ended_on=today,
    )

    landed_on(
        response, STUDENT_ROUTE, f"a launch by somebody whose enrollment ends today ({today})"
    )


def test_an_enrollment_that_ended_yesterday_does_not_land_a_student(
    monkeypatch: pytest.MonkeyPatch,
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
    landing_contract: Any,
    door_contract: Any,
) -> None:
    """Criterion 5, verbatim: "an assignment end-dated yesterday does not land today".

    The work order reads that sentence for what it can mean: `role_assignment`
    carries no validity dates at all — live means the row exists — so the dated
    boundary this criterion is about is enrollment's, and this is it. One day
    earlier than the test above, everything else identical, and the answer is the
    calm page rather than a student's view.

    **The mutation this kills**: `ended_on >= :today - 1`, or a window comparison
    that reads a `date` as a timestamp at midnight and then compares it against
    `now()` — both of which land a person who left the section yesterday on today's
    survey.

    **Dies too if the resolver stops reading `ended_on`**, which is the simplest
    version of the same defect and passes its pair above perfectly.
    """
    zone = A_STATED_TIMEZONE
    today = today_in(zone)

    response, _ = drive_a_student_launch_over(
        monkeypatch,
        launch_driver_in,
        provisioning_contract,
        launch_ground,
        web_identity,
        enrol,
        committed_rows,
        zone=zone,
        started_on=today - timedelta(days=COMFORTABLY_LIVE_DAYS),
        ended_on=today - timedelta(days=1),
    )

    the_no_access_page(
        response,
        landing_contract,
        door_contract,
        f"a launch by somebody whose enrollment ended yesterday ({today - timedelta(days=1)})",
    )


def test_an_enrollment_whose_first_day_is_today_lands_a_student(
    monkeypatch: pytest.MonkeyPatch,
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
) -> None:
    """The start edge's inclusive side: the day they added is an enrolled day.

    The mirror of `test_an_enrollment_whose_last_day_is_today_still_lands_a_student`
    at the other end of the window. Work order D3 makes the predicate
    `started_on <= :today AND (ended_on IS NULL OR ended_on >= :today)` — inclusive
    at both ends, ADR 0020's `'[]'` convention — so a person whose enrollment begins
    today is enrolled today, and §3.1 shows them this week's survey rather than
    making them wait until tomorrow.

    **The mutation this kills**: `started_on < :today`. One character, and it takes
    the first day of every section away from everybody who was added on it — which
    on a Monday-start section is the whole first week's cohort, and which no other
    test in this module sees. Its pair,
    `test_an_enrollment_that_starts_tomorrow_does_not_land_a_student` below, seeds
    one day later and must **not** land; between them the edge is pinned from both
    sides.

    **Added after the mutation battery found the gap.** The three boundary tests
    that were here seeded start-side windows thirty days wide, so `<=` → `<` was
    reachable only incidentally, through the timezone test's one-day window — a
    test whose subject is which *calendar* the day is read in, not which side of
    the edge is inclusive. Two rules were resting on one assertion, and the one
    that would have reported this failure was about something else
    (`docs/MISTAKES.md` entry 3, frozen).
    """
    zone = A_STATED_TIMEZONE
    today = today_in(zone)

    response, _ = drive_a_student_launch_over(
        monkeypatch,
        launch_driver_in,
        provisioning_contract,
        launch_ground,
        web_identity,
        enrol,
        committed_rows,
        zone=zone,
        started_on=today,
        ended_on=None,
    )

    landed_on(
        response, STUDENT_ROUTE, f"a launch by somebody whose enrollment begins today ({today})"
    )


def test_an_enrollment_that_starts_tomorrow_does_not_land_a_student(
    monkeypatch: pytest.MonkeyPatch,
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
    landing_contract: Any,
    door_contract: Any,
) -> None:
    """The other edge of the same window, which the two ended-on tests cannot see.

    A window has two ends and a resolver that checked only one is right about half
    the boundary. `started_on > today` is a person enrolled in a section that has
    not begun — the add that takes effect on Monday — and §3.1 shows a student one
    open survey per section they are *in*.

    **The mutation this kills**: dropping the `started_on <= :today` clause, which
    leaves every future enrollment live and passes both ended-on tests above.

    **Its pair is the test immediately above**, seeded one day earlier, which must
    land. Neither is worth much alone: this one is equally satisfied by a resolver
    that has stopped landing students at all, and that one by a resolver that
    ignores `started_on` entirely.
    """
    zone = A_STATED_TIMEZONE
    today = today_in(zone)

    response, _ = drive_a_student_launch_over(
        monkeypatch,
        launch_driver_in,
        provisioning_contract,
        launch_ground,
        web_identity,
        enrol,
        committed_rows,
        zone=zone,
        started_on=today + timedelta(days=1),
        ended_on=None,
    )

    the_no_access_page(
        response,
        landing_contract,
        door_contract,
        f"a launch by somebody whose enrollment starts tomorrow ({today + timedelta(days=1)})",
    )


def test_the_enrollment_boundary_is_measured_in_the_institutions_day_and_not_in_utcs(
    monkeypatch: pytest.MonkeyPatch,
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
) -> None:
    """Whose calendar the edge is on — Todd's ruling on E1-11, applied to this read.

    The window is exactly one day wide and that day is the **institution's** today,
    which right now is not UTC's. Read in the institution's zone the person is
    enrolled and lands on the student view; read in UTC the window is entirely in
    the past or entirely in the future and there is nothing to land on. SPEC §8
    makes the institution timezone a deployment-level setting for precisely this
    reason.

    **The mutation this kills**: `datetime.now(UTC).date()`, `date.today()`, or
    `CURRENT_DATE` in the enrollment predicate — three spellings of the same
    defect, none of which any of the four boundary tests above can see, because
    each of those seeds a window thirty days wide on one side.

    **What it must not be relied on for.** Its window is one day wide, so it also
    happens to sit on both edges at once and would incidentally catch `<=` → `<`
    or `>=` → `>`. The mutation battery found the suite resting on that: the start
    edge had no inclusive-side test of its own and this one was covering for it.
    Each edge is now pinned by a test whose subject *is* that edge, and this one is
    left to say the one thing only it can — whose calendar the day is read in.

    **The zone is chosen at run time from two that bracket the clock**, so this
    poses its question at every hour rather than only in the few where a
    conveniently picked zone happens to differ. The two dates are required to
    differ before anything is seeded: a test whose two candidate days were the same
    day is satisfied by either reading (`docs/MISTAKES.md` entry 3).
    """
    zone, institution_day, utc_day = a_zone_whose_date_differs_from_utc()
    assert institution_day != utc_day, (
        f"The institution's date and UTC's are both {utc_day}, so both readings of 'today' give the "
        "same answer and this test cannot tell them apart."
    )

    response, _ = drive_a_student_launch_over(
        monkeypatch,
        launch_driver_in,
        provisioning_contract,
        launch_ground,
        web_identity,
        enrol,
        committed_rows,
        zone=str(zone),
        started_on=institution_day,
        ended_on=institution_day,
    )

    landed_on(
        response,
        STUDENT_ROUTE,
        f"a launch by somebody enrolled for exactly {institution_day}, the institution's own day, "
        f"while UTC's day is {utc_day}",
    )


# ---------------------------------------------------------------------------
# The door property, live. ADR 0026's columns doing the work an exception list
# used to do.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_a_care_only_persons_launch_is_answered_with_the_calm_page_and_never_the_care_view(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    committed_rows: Any,
    landing_contract: Any,
    door_contract: Any,
) -> None:
    """Care is unreachable from a launch **by data**, and this is the behavioural proof.

    E1-13's scope: "Care remains unreachable from a launch — now proven by data
    (ADR 0026's column) rather than by an exception list, and the existing
    invariant test gets strictly stronger, never weaker." ADR 0026 makes
    `permits_launch` a stored generated column derived from the role, so "a Care
    assignment is unreachable from a launch" is a property of the row rather than
    of a Python branch, and "there is no write path to either column for anyone —
    application role, seed script, superuser session or future admin console
    alike".

    **The refusal is asserted, not the absence of a name.** SPEC §4.1's rule for a
    confidentiality test is that a query has to be *refused*: a check that
    `pulse-landing-care` is missing from the response would pass equally well
    against a launch that failed for some reason nobody looked at, so what is
    required here is the whole positive shape of the calm page — 200, the
    `no-access` testid, no landing of any kind, and no session issued.

    §6.2 is why this is the one that must never move: Care is the only role that
    can re-identify a student, and the person who administers the LMS controls what
    a launch says. E0-09 criterion 10: "a claim-to-Care mapping would let an LMS
    administrator grant themselves identity access, walking past every guarantee in
    §4."

    **Dies if `permits_launch` is dropped from the assignment read**, which is the
    whole of ADR 0026's contribution to this door and which nothing else would
    notice: every other landing in this module is answered identically with or
    without the clause.

    **Its boundary pair is `test_the_care_officer_lands_on_care_at_the_web_door`**
    — the same person, the same assignment, the other door, and a Care view. So
    this green is not a Care assignment that has stopped working.

    **The denial is asserted in this body and not only in the helpers it calls.**
    `scripts/ci/check_invariant_assertions.py` refuses an `invariant`-marked test
    whose own body contains no `assert`, no `with pytest.raises(...)` and no
    `pytest.fail(...)`, and E0-36 §3 settles that helpers are not chased: "chasing
    calls means choosing a depth, and every choice is arbitrary". That is a rule
    about where a reader of *this* function can see the guarantee, so the two
    sentences that matter most — she was not sent to the Care route, and she was
    met with the calm page — are written here, and `the_no_access_page` below adds
    the rest of the shape.
    """
    offer, subject = a_launch_subject(launch_driver, provisioning_contract.learner_role_urn)
    launch_ground(provisioning_contract.label_of(launch_driver.claims_of(offer)))

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=subject
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    committed_rows.graph.assign(
        CARE_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.commit()

    response, _ = launch_driver.launch(offer)

    reached = response.headers.get("location") or ""
    assert not reached.startswith(f"/app/{CARE_ROUTE}"), (
        f"A launch by a person whose only live assignment is a Care assignment was sent to "
        f"`{reached}`. ADR 0026 derives `permits_launch` from the role so that no write path can "
        "contradict it, and §2.1's table gives Care the web login and no launch: the Care queue is "
        "the one surface in this product that can re-identify a student (§6.2), and the person who "
        "administers the LMS decides what a launch says."
    )
    assert landing_contract.no_access_testid in response.text, (
        f"That launch was answered {response.status_code} with a body beginning "
        f"{response.text[:400]!r}, which carries no `{landing_contract.no_access_testid}` testid. "
        "The refusal has to be the calm page rather than any other answer, or 'she did not reach "
        "the Care view' is equally true of a launch that failed for a reason nobody looked at "
        "(`docs/MISTAKES.md` entry 3)."
    )

    the_no_access_page(
        response,
        landing_contract,
        door_contract,
        "a launch by a person whose only live assignment is a Care assignment",
    )
    assert_the_page_names_none_of(
        response, [subject], "a launch by a person holding only a Care assignment"
    )


@pytest.mark.invariant
def test_the_care_who_teaches_reaches_instructor_by_launch_and_care_by_web_login(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """One person, two hats, two doors, two views — decided by the permission columns.

    §2: "Entry doors are a property of the assignment, not the person. A person
    holding two assignments uses whichever door fits the one they are acting
    under." She is the shape E0-09's criterion 9 seeds and E0-10 and E0-18 reuse:
    a Care officer who also teaches. Her instructor assignment permits a launch and
    not a web login; her Care assignment permits a web login and not a launch; and
    the two columns are the whole of what decides which she gets where.

    **This is what "strictly stronger than the exception list" means.** Until this
    ticket, "Care is unreachable from a launch" rested on
    `tests/unit/test_care_is_not_reachable_from_a_claim.py::EXCEPTIONS` and on a
    launch-door refusal of a smuggled claim. Here the Care assignment is real, live
    and held by the very person who is launching — and the launch still cannot
    reach it, because the door reads `permits_launch` and the column says no.

    **The mutation this kills**: filter the assignment read by the wrong column, or
    by neither. Under it her launch lands on `/app/care`, and every other test in
    this module still passes — which is exactly the state E0-18 shipped and E0-09's
    criterion 10 exists to stop.

    **Both doors in one test on purpose.** Split in two, each half is satisfied by
    a seed the other is missing from, and the fact worth asserting — that the same
    two rows answer differently at the two doors — is stated nowhere.

    **The two sentences that carry the guarantee are asserted in this body**, not
    only in the `landed_on` calls that follow: `scripts/ci/check_invariant_assertions.py`
    refuses an `invariant`-marked test whose own body asserts nothing, and E0-36 §3
    settles that helpers are not chased. So the denial — her launch did not reach
    the Care route — and the property the pair exists for — her two doors did not
    answer the same view — are written here, where a reader of this function can
    see them.
    """
    hers = published_person(web_door.provider, CARE_ROLE, and_a_launch_assignment=True)
    offer, lms_subject = a_launch_subject(launch_driver, provisioning_contract.learner_role_urn)
    launch_ground(provisioning_contract.label_of(launch_driver.claims_of(offer)))

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=lms_subject
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    web_identity.link_web_subject(
        issuer=provider_issuer, subject=published_subject(hers), person_id=person_id
    )
    committed_rows.graph.assign(INSTRUCTOR_ROLE, person=person_id)
    committed_rows.graph.assign(
        CARE_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.commit()

    by_launch, _ = launch_driver.launch(offer)
    by_web = web_door.login_as(hers)

    through_the_launch = (by_launch.headers.get("location") or "").split("#", 1)[0]
    through_the_web = (by_web.headers.get("location") or "").split("#", 1)[0]
    assert through_the_launch != f"/app/{CARE_ROUTE}", (
        f"Her launch reached `{through_the_launch}`. She holds a live `CARE` assignment and a live "
        "`INSTRUCTOR` one, and ADR 0026's `permits_launch` is what keeps the first of them out of "
        "this door: §2.1 gives Care the web login and no launch, because §6.2's queue is the one "
        "surface that can re-identify a student and an LMS launch is a context it has no meaning "
        "in. Reaching it here is the assignment read filtered by the wrong column, or by neither."
    )
    assert through_the_launch != through_the_web, (
        f"Both of her doors answered `{through_the_launch}`. §2: 'Entry doors are a property of "
        "the assignment, not the person' — she holds two, each opening one door, so two doors "
        "answering one view means the permission columns decided nothing and one of her two "
        "assignments is being served where it does not belong."
    )

    landed_on(by_launch, INSTRUCTOR_ROUTE, "the Care officer's launch")
    landed_on(by_web, CARE_ROUTE, "the Care officer's web login")


@pytest.mark.invariant
def test_the_assignment_scope_view_publishes_a_door_permission_per_role(
    committed_rows: Any, application_session: Any, landing_contract: Any
) -> None:
    """ADR 0026's columns, readable from the view the resolution reads (work order D4).

    `assignment_scope` withheld both generated columns deliberately — its own
    header says a later ticket writes a `_v002` — and this is that ticket. The
    columns are what make the door rule a fact about the row rather than a Python
    branch: ADR 0026 rejected "derived in Python, with no column at all" because
    "a property of an assignment that cannot be read off the assignment is not a
    property of the assignment", and E0-10's identity-separated views are SQL.

    **Read over `application_session`**, the connection production serves requests
    on. From E0-10 on `pulse_app` holds `SELECT` on the read views and on nothing
    else, so "the resolver can read this" is a claim about a grant and is only true
    over this session — a superuser would pass whatever the migration granted.

    **Two rows, opposite answers, and both are needed.** A Care assignment must
    permit the web login and not a launch, and an instructor assignment the
    reverse. ADR 0026's own consequences record the same pair as the mutation it
    was verified by: "adding `CARE` to the launch list, or `INSTRUCTOR` to the
    web-login list, turns the door test red." A test that asserted only the
    negative would be satisfied by two columns that are false for everybody.

    **The column list is read before it is selected from, and that is deliberate.**
    Naming a column the view does not carry makes Postgres raise `UndefinedColumn`
    out of `execute()`, and a test whose red is an exception from the driver is a
    test that reports the deliverable being absent and an unrelated database
    failure in exactly the same way. So the columns are read out of
    `information_schema` first and their presence is an assertion about the
    deliverable; the rows are only selected once that holds. The read doubles as
    the grant check: `information_schema.columns` shows a caller only the objects
    it has privileges on, so an empty answer here is `pulse_app` holding no
    `SELECT` on the re-versioned view, which the failure says in as many words.
    """
    care = committed_rows.graph.assign(
        CARE_ROLE, scope=committed_rows.graph.scope("institution"), reports_to=None
    )
    instructor = committed_rows.graph.assign(INSTRUCTOR_ROLE)
    committed_rows.commit()
    key = committed_rows.graph.assignment_key

    published = {
        row[0]
        for row in application_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :view"
            ),
            {"schema": VIEW_SCHEMA, "view": landing_contract.assignment_scope_view},
        )
    }
    assert published, (
        f"The application connection can see no columns at all on "
        f"`{ASSIGNMENT_SCOPE_RELATION}`. `information_schema.columns` shows a caller only what it "
        "has privileges on, so this is `pulse_app` holding no `SELECT` on the view — which the "
        "`_v002` re-version has to re-grant, following the `reveal_student_identity_v002` "
        "precedent — or the view not existing under that name at all."
    )
    absent = [
        column
        for column in (
            landing_contract.permits_launch_column,
            landing_contract.permits_web_login_column,
        )
        if column not in published
    ]
    assert not absent, (
        f"`{ASSIGNMENT_SCOPE_RELATION}` publishes no {absent}; it publishes {sorted(published)}. "
        "ADR 0026 puts both on `role_assignment` as stored generated columns derived from the "
        "role, and the view withheld them deliberately — its own header says a later ticket writes "
        "a `_v002`. E1-13 is that ticket: the landing resolution filters a person's assignments by "
        "the entered door's permission column, so without these the rule has nowhere to be read "
        "from but a Python branch, which is the option ADR 0026 rejected."
    )

    # Every name interpolated here is a module constant, never a value a test or a
    # request supplied, which is what S608 is about; the two ids are bound. The
    # assertion above is what guarantees the columns exist before they are named.
    columns = ", ".join(
        (
            "assignment_id",
            "role",
            landing_contract.permits_launch_column,
            landing_contract.permits_web_login_column,
        )
    )
    statement = f"SELECT {columns} FROM {ASSIGNMENT_SCOPE_RELATION} WHERE assignment_id IN (:care, :instructor)"  # noqa: S608
    query = text(statement)
    rows = {
        str(row.assignment_id): row
        for row in application_session.execute(
            query, {"care": care[key], "instructor": instructor[key]}
        )
    }

    assert len(rows) == 2, (
        f"`{ASSIGNMENT_SCOPE_RELATION}` returned {len(rows)} of the two assignments seeded here. "
        "Zero means the application connection cannot read the view at all — the `_v002` "
        "re-version has to re-grant `SELECT` to `pulse_app`, following the "
        "`reveal_student_identity_v002` precedent — and one means the view is filtering rows the "
        "resolution needs."
    )
    care_row = rows[str(care[key])]
    instructor_row = rows[str(instructor[key])]

    assert getattr(care_row, landing_contract.permits_web_login_column) is True, (
        f"The Care assignment's `{landing_contract.permits_web_login_column}` is "
        f"{getattr(care_row, landing_contract.permits_web_login_column)!r}. SPEC §2.1's table gives "
        "Care the web login, and a column that is false for everybody would satisfy the negative "
        "half of this test while shutting the door on the one role §6.2 depends on."
    )
    assert getattr(care_row, landing_contract.permits_launch_column) is False, (
        f"The Care assignment's `{landing_contract.permits_launch_column}` is "
        f"{getattr(care_row, landing_contract.permits_launch_column)!r}. §2.1: 'Care and Admin are "
        "web login only (their work has no launch context)', and ADR 0026 derives the column from "
        "the role so that no write path can contradict it."
    )
    assert getattr(instructor_row, landing_contract.permits_launch_column) is True, (
        f"The instructor assignment's `{landing_contract.permits_launch_column}` is "
        f"{getattr(instructor_row, landing_contract.permits_launch_column)!r}. §2.1's table gives "
        "the instructor the LTI launch, and with this false no instructor could land at all."
    )
    assert getattr(instructor_row, landing_contract.permits_web_login_column) is False, (
        f"The instructor assignment's `{landing_contract.permits_web_login_column}` is "
        f"{getattr(instructor_row, landing_contract.permits_web_login_column)!r}. §2.1: 'Every role "
        "except instructor and student can *also* enter by web login' — the instructor is one of "
        "the two exclusions, and ADR 0026 writes each door as a positive list of roles so that a "
        "role added later gets no door rather than every door."
    )


# ---------------------------------------------------------------------------
# The two calm pages, and which of them answers which event.
# ---------------------------------------------------------------------------


def test_a_launch_by_a_person_with_no_assignment_and_no_enrollment_lands_on_the_calm_page(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    landing_contract: Any,
    door_contract: Any,
) -> None:
    """E1-13's scope, verbatim: "no assignment and no enrollment gets the calm no-access state".

    The launch is correct in every respect — signed, verified, from a registered
    platform and a registered deployment — and the person behind it is somebody
    Pulse holds a record of and nothing else. That is a real state rather than a
    fault: a member of staff whose assignment has not been entered yet, or a
    student between terms.

    **Dies against HEAD**, where the roles claim lands this person on the student
    view with nothing in the database saying they may see one.

    **Dies if the answer is a 4xx**, which is fail-closed and is not what the
    person is owed: they authenticated correctly and are owed plain words and the
    LMS-launch hint, not a refusal.

    **It is the boundary pair for every landing above** — the same launch, the
    same subject, with the one row that entitles them removed.
    """
    offer, subject = a_launch_subject(launch_driver, provisioning_contract.learner_role_urn)
    launch_ground(provisioning_contract.label_of(launch_driver.claims_of(offer)))

    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=platform_id_of(launch_driver, web_identity), subject=subject
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)

    response, _ = launch_driver.launch(offer)

    the_no_access_page(
        response,
        landing_contract,
        door_contract,
        "a launch by a person holding no assignment and no live enrollment",
    )
    assert_the_page_names_none_of(
        response, [subject], "a launch by a person with nothing to land on"
    )


def test_a_web_login_by_a_linked_person_holding_no_assignment_lands_on_the_calm_page(
    web_door: Any,
    provider_issuer: str,
    published_person: Any,
    published_subject: Any,
    web_identity: Any,
    landing_contract: Any,
    door_contract: Any,
) -> None:
    """The same state at the other door, and the pair that says the enrollment fallback stops here.

    A person Pulse has a record of, signed in correctly, holding no assignment at
    all. §2.1's table gives students one door and it is not this one, so there is
    no fallback to reach for — the honest answer is the same calm page.

    **Dies if the web door consults enrollment**, which is the mutation
    `chosen_landing`'s own unit test poses over a boolean and this poses over rows:
    a person with an old student enrollment would otherwise land on a student view
    through a door §2.1 gives them no student access at.

    **Dies against HEAD**, where her roles claim decides and she lands wherever the
    provider says.
    """
    theirs = published_person(web_door.provider, ADMIN_ROLE)
    subject = published_subject(theirs)
    person_id = web_identity.person()
    web_identity.link_web_subject(issuer=provider_issuer, subject=subject, person_id=person_id)

    response = web_door.login_as(theirs)

    the_no_access_page(
        response,
        landing_contract,
        door_contract,
        f"a web login by {subject!r}, whose person row holds no assignment",
    )
    assert_the_page_names_none_of(response, [subject], "a web login by a person with no assignment")


def test_an_unlinked_web_subject_still_gets_the_no_account_page_rather_than_the_no_access_one(
    web_door: Any,
    published_person: Any,
    published_subject: Any,
    landing_contract: Any,
    door_contract: Any,
) -> None:
    """The order the two calm pages are decided in: E1-12's check comes first, unchanged.

    Two events that both end in a 200 and plain words, and they are different
    things to have happened. "Pulse has no record of you at all" is E1-12's
    no-account page and is a matter for whoever administers Pulse; "we have your
    record and nothing in it gives you a view here" is E1-13's no-access page and
    is a matter for whoever enters assignments. A person told the second when the
    first is true is sent to the wrong person for help.

    **The mutation this kills**: resolving the landing *before* the identity, or
    folding the two pages into one. Either leaves an unlinked subject on the
    no-access page, and every assertion in
    `tests/integration/test_the_unlinked_web_login_lands_on_no_account.py` that
    checks the absence of rows would still pass.

    **This is also a control on the reworked door**: it is E1-12's own behaviour,
    green before this ticket and required to stay green after it, so a red here is
    E1-13 having broken something rather than E1-13 being unbuilt.
    """
    theirs = published_person(web_door.provider, ADMIN_ROLE)

    response = web_door.login_as(theirs)

    assert response.status_code == 200, (
        f"A verified login by the unlinked subject {published_subject(theirs)!r} answered "
        f"{response.status_code}. E1-12's D5 makes this a calm page: the IdP asserts "
        f"authentication, not membership. Body begins {response.text[:400]!r}."
    )
    assert landing_contract.no_account_testid in response.text, (
        f"The page carries no `{landing_contract.no_account_testid}` testid (body begins "
        f"{response.text[:400]!r}). E1-12 checks the linkage before anything else, and a subject "
        "with no `person` row has no assignments to read in the first place."
    )
    assert landing_contract.no_access_testid not in response.text, (
        f"The page carries `{landing_contract.no_access_testid}`, which is E1-13's answer for a "
        "person Pulse *does* hold a record of. Told this, somebody whose account was never "
        "provisioned goes looking for the administrator who enters assignments instead of the one "
        "who creates accounts."
    )
    landings = [testid for testid in door_contract.landing_testids if testid in response.text]
    assert not landings, f"The no-account page carries {landings}."


# ---------------------------------------------------------------------------
# The retired module, from the outside.
# ---------------------------------------------------------------------------


def test_no_module_under_app_still_imports_or_calls_the_retired_landing_seam(
    landing_contract: Any,
) -> None:
    """Criterion 3, swept: nothing imports the module this ticket deletes, or calls its seam.

    A deleted file and a caller that still names it are two different states, and
    the second is an `ImportError` the first time that path runs in a deployment
    while a suite that never exercises it stays green.

    **Read out of the syntax tree rather than out of the file text**, for the
    reason `tests/unit/test_care_is_not_reachable_from_a_claim.py` gives about the
    same sweep: a correct implementation is very likely to *say* `landing.py` in a
    comment or a docstring — E1-13's own record corrections (work order D12) do
    exactly that — and searching the text would turn those sentences into a
    failure and teach the next person to delete them. Comments are not in a syntax
    tree at all, and a docstring is a string constant rather than an import.

    **Dies if either router, `deps.py`, or anything else is left importing
    `app.services.landing` or calling `landing_role_for`.**

    The sibling assertion — that the module itself no longer imports — is in
    `tests/unit/test_chosen_landing.py`; this is the half about everybody who used
    to call it.
    """
    from pathlib import Path

    app_root = Path(__file__).resolve().parents[2] / "backend" / "app"
    assert (
        app_root.is_dir()
    ), f"{app_root} does not exist, so this sweep looked at nothing and would report success."

    sources = sorted(app_root.rglob("*.py"))
    assert sources, f"There are no Python modules under {app_root}, so this sweep read nothing."

    retired = landing_contract.retired_module
    seam = landing_contract.retired_seam
    naming: list[str] = []
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imports = (
                any(alias.name == retired for alias in node.names)
                if isinstance(node, ast.Import)
                else (node.module == retired if isinstance(node, ast.ImportFrom) else False)
            )
            calls_seam = (isinstance(node, ast.Name) and node.id == seam) or (
                isinstance(node, ast.Attribute) and node.attr == seam
            )
            if imports or calls_seam:
                naming.append(str(path.relative_to(app_root.parent.parent)))
                break

    assert not naming, (
        f"{sorted(set(naming))} still import `{retired}` or name `{seam}` in code. The carried "
        "entry's done-when is that the claims-derived mapping is gone — not shadowed, not unused — "
        "and a caller left pointing at a deleted module is an `ImportError` the first time that "
        "path runs in a deployment."
    )
