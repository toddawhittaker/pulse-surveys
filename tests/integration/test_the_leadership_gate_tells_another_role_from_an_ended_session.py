"""The leadership gate answers 403 to a reader in another role and 401 to everything else — E7-08.

Ruling 11 (`docs/tickets/e7/README.md`), as the ticket states it: "A real,
verified session in another role gets **403**. The first four cases stay 401,
collapsed together as now, so a caller trying tokens still cannot tell a real one
from a forgery." The criteria this module asserts:

> 1. A real student session and a real instructor session each get 403 from
>    every leadership route, read and write, over HTTP against the built
>    application, and the body names no route, section or person.
> 2. Absent, malformed, expired and wrongly signed tokens each get the same 401
>    with the same body and headers, so none can be told from another. An
>    expired but correctly signed student token [...] gets 401, not 403.
> 3. A leader is still admitted, beside each refusal above, in one world.
> 4. A person with an instructor and a leadership assignment gets 403 under the
>    instructor session and is admitted under the leadership session.

**One world for all of it.** `fixtures/lead_review.py`'s world holds a Lead
Faculty member who leads the report world's course (the queue and the log answer
her 200), the teaching instructor's own **launched** session, and a sibling lead
who is given an instructor assignment here to be the two-hat person. The student
session is minted for a real `user` row through `app.services.session`, as every
leadership test in this suite mints its sessions.

**Every route, found by the sweep and not listed** (the ticket's second known
trap, `docs/MISTAKES.md` entry 53): `fixtures/leadership_gate.py::
leadership_gated_routes` walks the built application for the two dependency
objects. The first test below is the control that the sweep sees the ten
routes two other suites name, so an empty or blind sweep is a red and never a
vacuous pass (`docs/MISTAKES.md` entry 3).

**Admitted means "past the gate", per route.** Each route is driven with a fresh
uuid in every path parameter and `{}` as any write's body, so the leader's answer
on most routes is a 404 or a 422 from *behind* the gate. That is the claim
criterion 3 makes: a 401, or a 403 carrying the gate's sentence, is the gate
refusing her; anything else is the gate letting her through. The queue and the
log, which need no identifier, are also required to answer her with a 2xx.

**The refusal's layer is pinned by its sentence** (`fixtures/leadership_gate.py`
says how it is discovered without being spelled): a 403 is also what the CSRF
check, the named-set scope read and ADR 0190's dean refusal answer.

**Which failure a red is, before E7-08 lands.** Today the gate answers 401 to the
student and instructor sessions, so every test that expects the 403 FAILS on the
status, naming ruling 11 — never an ERROR. The 401-collapse test and the
leader's test pass today; they are here to hold that behaviour while the gate is
changed (each names the mutation it kills).

**Not written: "a student session ended on the server".** Criterion 2 names it
and the work order says a live session is one "not ended on the server", but
neither the ticket, the spec nor ADR 0089 (the session record) says how a
session is ended on the server: ADR 0089's session is a signed token with no
server-side record. A test would have to guess the mechanism, so the case is
reported to the coordinator instead.
"""

import base64
import json
import time
from typing import Any
from uuid import uuid4

import pytest
from fixtures.lead_review import EXCLUDE, LeadReviewWorld, is_success, lead_routes
from fixtures.leadership_gate import (
    NOT_YOUR_ROLE_STATUS,
    SIGNED_OUT_STATUS,
    body_for,
    concrete,
    leadership_gated_routes,
    not_your_role_sentence,
    signed_out_sentence,
    the_whole_body_is_the_sentence,
)
from fixtures.moderation import HARMFUL
from fixtures.named_sets import (
    DETAIL_MEMBER,
    LEADERSHIP_LANDING_ROLE,
    OPTIONS_PATH,
    SETS_PATH,
    SUBJECT_CLAIM,
    detail_of,
)
from fixtures.report_api import (
    FIRST_HELD_WEEK,
    INSTRUCTOR_ROLE,
    PATH_PARAMETER,
    STUDENT_ROLE,
    TAUGHT_COHORT,
)
from fixtures.report_views import COURSE_STREAM
from fixtures.student_read import AUTHENTICATE_HEADER
from fixtures.supervision import require_table
from fixtures.survey_windows import SECTION_CODE_COLUMN, SECTION_TABLE
from fixtures.web_identity import USER_ID_CLAIM, claims_in_session

pytestmark = pytest.mark.integration

QUEUED_TEXT = "E7-08 the held comment a reader in another role tries to decide on"

# A secret the application was certainly not built with, for a token that is
# correctly shaped and wrongly signed. This module's own value.
ANOTHER_SECRET = b"e7-08-a-secret-this-application-was-never-configured-with"

# How far in the past an expired token is issued. ADR 0089 gives a session sixty
# minutes; two days is past that by a margin no clock drift reaches, and is not
# the boundary — `tests/unit/test_session_module.py` owns the boundary pair.
EXPIRED_BY_SECONDS = 2 * 24 * 60 * 60

# The token the e2e suite already uses for "a session the server will not
# verify" (`tests/e2e/student-survey.spec.ts`).
MALFORMED = "not.a.session"

# Headers a response carries that differ between two identical requests are not
# a way to tell two tokens apart. They are measured per route (two absent-token
# requests), never listed here; this is only the one every response carries.
ALWAYS_VARIES = frozenset({"date"})


# ---------------------------------------------------------------------------
# The sessions. Every one is an input this module names; none is an answer.
# ---------------------------------------------------------------------------


def a_student(
    review: LeadReviewWorld,
    *,
    subject: str | None = None,
    user_id: Any = None,
    now: int | None = None,
    secret: bytes | None = None,
) -> tuple[str, str, Any]:
    """A `STUDENT` session for a real `user` row: `(token, subject, user_id)`.

    `subject` and `user_id` are passed back in to mint a second token for the
    **same** student, so a pair differs in exactly one thing (its issue instant or
    its key) and nothing about who it names.
    """
    if subject is None:
        subject = f"e7-08-student-{uuid4().hex[:8]}"
        user_id = review.web_identity.user(platform_id=review._platform_id(), subject=subject)
    token = review.minted(
        role=STUDENT_ROLE,
        person_id=None,
        user_id=user_id,
        subject=subject,
        now=now,
        secret=secret,
    )
    return token, subject, user_id


def issued_long_ago() -> int:
    return int(time.time()) - EXPIRED_BY_SECONDS


def unsecured(token: str) -> str:
    """The same claims re-encoded `alg: none` with an empty signature (RFC 7519 §6)."""

    def padded(segment: str) -> bytes:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))

    header_b64, claims_b64, _signature = token.split(".")
    header = {**json.loads(padded(header_b64)), "alg": "none"}
    encoded = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=")
    return f"{encoded.decode('ascii')}.{claims_b64}."


def the_two_hats(review: LeadReviewWorld) -> tuple[str, str]:
    """The sibling lead, given an instructor assignment: `(instructor session, leadership session)`.

    `LeadReviewWorld.teaches` reads the assignment back, so a person still holding
    one hat afterwards is a broken world rather than a red. Both sessions name
    the same person, subject and user; they differ only in the role.
    """
    reader = review.sibling_lead
    review.teaches(reader, TAUGHT_COHORT)
    claims = claims_in_session(reader.token)
    instructor = review.minted(
        role=INSTRUCTOR_ROLE,
        person_id=reader.person_id,
        user_id=claims.get(USER_ID_CLAIM),
        subject=claims.get(SUBJECT_CLAIM),
    )
    return instructor, reader.token


# ---------------------------------------------------------------------------
# Asking, and reading what came back.
# ---------------------------------------------------------------------------


def swept(review: LeadReviewWorld) -> list[tuple[str, str]]:
    """Every gated route, required non-empty (an empty sweep makes every loop below vacuous)."""
    routes = leadership_gated_routes(review.door.door.application)
    assert routes, (
        "The sweep found no route carrying `require_leadership` or `csrf_verified_leadership` on "
        "the built application. Every assertion in this module is a loop over that list, so an "
        "empty one would pass them all; the control test at the top says whether the sweep or the "
        "application is at fault."
    )
    return routes


def ask(review: LeadReviewWorld, method: str, path: str, token: Any) -> Any:
    return review.ask(method, concrete(path), token=token, json=body_for(method))


def detail_or_none(answered: Any) -> Any:
    try:
        body = answered.json()
    except ValueError:
        return None
    # A validation error's `detail` is a list; only a string can be a gate's sentence.
    detail = body.get(DETAIL_MEMBER) if isinstance(body, dict) else None
    return detail if isinstance(detail, str) else None


def assert_past_the_gate(answered: Any, route: str, who: str, gate_sentences: set[str]) -> None:
    """The admitted half: neither the 401 nor a 403 carrying one of the gate's sentences."""
    refused_by_the_gate = answered.status_code == SIGNED_OUT_STATUS or (
        answered.status_code == NOT_YOUR_ROLE_STATUS and detail_or_none(answered) in gate_sentences
    )
    assert not refused_by_the_gate, (
        f"{route} answered {answered.status_code} to {who}, whose session the leadership gate "
        f"admits (criterion 3: 'A leader is still admitted, beside each refusal'). Body begins "
        f"{answered.text[:400]!r}."
    )


def stable_headers(answered: Any, varies: set[str]) -> dict[str, str]:
    return {
        name.lower(): value
        for name, value in answered.headers.items()
        if name.lower() not in varies and name.lower() not in ALWAYS_VARIES
    }


def section_codes(review: LeadReviewWorld) -> list[str]:
    """Every section code in the database this world wrote into, read back whole."""
    from sqlalchemy import select

    review.session.rollback()
    table = require_table(review.world.tables, SECTION_TABLE)
    found = review.session.execute(select(table.c[SECTION_CODE_COLUMN])).scalars()
    codes = [str(code) for code in found]
    assert codes, "This world holds no section, so 'names no section' would be asked of nothing."
    return codes


# ---------------------------------------------------------------------------
# Control on the instrument. A red here means the sweep is broken, not the gate.
# ---------------------------------------------------------------------------


def test_the_sweep_finds_the_ten_leadership_routes_two_other_suites_name(
    lead_review: LeadReviewWorld,
) -> None:
    """CONTROL — green today. The sweep sees what E5-06's and E6-05's suites name, and more.

    `docs/MISTAKES.md` entry 53: "The coverage check must not be built from the
    guard's own enumeration." So the canary is taken from two other places — the
    named-set contract's seven routes (`fixtures/named_sets.py`) and the three
    moderation routes `fixtures/lead_review.py::lead_routes` finds by path — and
    a second check goes one level out: every route served under `/leadership`
    must be in the sweep, so a leadership route that dropped the gate cannot hide
    from every test here by not being swept.

    **The mutations it kills:** a sweep matching the dependency by name (the
    objects come from `app.api.deps`, so a rename is a FAILED naming it); a sweep
    walking one level of the dependency graph (`csrf_verified_leadership`'s
    routes carry `require_leadership` only beneath it, if at all); a sweep that
    reads `application.routes` without recursing into included routers (the
    whole leadership router is behind `include_router`, `fixtures/routing.py`).
    """
    review = lead_review
    application = review.door.door.application

    def shape(path: str) -> str:
        return PATH_PARAMETER.sub("{}", path.rstrip("/"))

    found = {(method, shape(path)) for method, path in swept(review)}
    moderation = lead_routes(application)
    canary = {
        ("GET", shape(moderation.queue)),
        ("GET", shape(moderation.log)),
        ("POST", shape(moderation.decision)),
        ("GET", SETS_PATH),
        ("POST", SETS_PATH),
        ("GET", OPTIONS_PATH),
        ("GET", f"{SETS_PATH}/{{}}"),
        ("PUT", f"{SETS_PATH}/{{}}"),
        ("DELETE", f"{SETS_PATH}/{{}}"),
        ("GET", f"{SETS_PATH}/{{}}/preview"),
    }
    assert canary <= found, (
        f"The sweep misses {sorted(canary - found)}. It found {sorted(found)}. These ten are the "
        "routes E5-06's and E6-05's suites drive behind the leadership gate, so a sweep blind to "
        "any of them is blind, and every test below would pass over the gap."
    )

    from fixtures.routing import every_route

    served = {
        (str(method).upper(), shape(str(route.path)))
        for route in every_route(application)
        if isinstance(getattr(route, "path", None), str)
        and str(route.path).startswith("/leadership")
        for method in (getattr(route, "methods", None) or ())
        if str(method).upper() not in {"HEAD", "OPTIONS"}
    }
    assert served <= found, (
        f"These routes are served under `/leadership` and carry neither leadership dependency: "
        f"{sorted(served - found)}. The sweep cannot see them, so no test here can say whether a "
        "student is refused there."
    )


# ---------------------------------------------------------------------------
# Criterion 1, with criterion 3 beside every refusal.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_a_student_session_gets_the_403_from_every_leadership_route(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 1 for a real student session, every route, read and write; the lead beside it.

    **The mutations it kills:** the gate left answering 401 to every refusal (red
    today); a 403 raised only on reads, with `csrf_verified_leadership` still
    answering 401 to a student's write; a 403 carrying `NOT_LEADERSHIP`, the
    ended-session sentence, which the page would read as "ended" if it ever read
    the body; and a route that answers the student 200, which no refusal test
    with a fixed list would see on a route added after the list was written.

    **The near miss it spares:** the lead on the same route and the same request
    shape, who is past the gate (criterion 3) — so the 403 is about the
    student's role and not about the request.
    """
    review = lead_review
    student, _subject, _user = a_student(review)
    gate = {signed_out_sentence()}

    for method, path in swept(review):
        route = f"{method} {path}"
        refused = ask(review, method, path, student)
        gate.add(not_your_role_sentence(refused, f"{route}, asked by a student session"))
        the_whole_body_is_the_sentence(refused, f"{route}'s refusal of a student")
        assert_past_the_gate(ask(review, method, path, review.lead.token), route, "the lead", gate)


@pytest.mark.invariant
def test_the_instructors_launched_session_gets_the_403_from_every_leadership_route(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 1 for a real instructor session — the one a launch issued — every route.

    The instructor teaches the very section this world's queue is about, which is
    the strongest instructor to refuse: the section is in her own report.

    **The mutations it kills:** a 403 decided by "the session names a student",
    which leaves an instructor on the 401; a gate that admits any staff role
    (`role is not STUDENT`), which answers the instructor past the gate. **The
    near miss it spares:** the lead beside her on each route.
    """
    review = lead_review
    gate = {signed_out_sentence()}

    for method, path in swept(review):
        route = f"{method} {path}"
        refused = ask(review, method, path, review.instructor_token)
        gate.add(not_your_role_sentence(refused, f"{route}, asked by the instructor's session"))
        the_whole_body_is_the_sentence(refused, f"{route}'s refusal of the instructor")
        assert_past_the_gate(ask(review, method, path, review.lead.token), route, "the lead", gate)


@pytest.mark.invariant
def test_the_403_is_one_sentence_for_every_role_and_route_and_names_no_route_section_or_person(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 1's body clause, and work order decision 1: "identical for every non-leadership role".

    Three sessions in another role — a student, the launched instructor, and the
    two-hat person's instructor session — over every route must be refused with
    **one** sentence, and that sentence must carry none of: a path this request
    was sent to, a section code in this database, or an identifier or subject of
    any person or user whose session asked.

    **The mutations it kills:** a sentence formatted with the route ("… is not
    available at /leadership/moderation/queue"), with the reader's role ("…
    your instructor session…" — the identity clause, since it differs by role),
    or with the section the request named; and two copy entries, one per role.
    **Why one sentence and not "contains none of"**: a constant that is the same
    across every route and every reader cannot carry anything particular to one
    of them, and the scan below is the second line, for anything fixed.
    """
    review = lead_review
    student, student_subject, student_user = a_student(review)
    two_hat_instructor, two_hat_leadership = the_two_hats(review)
    readers = {
        "a student session": student,
        "the instructor's launched session": review.instructor_token,
        "the two-hat person's instructor session": two_hat_instructor,
    }

    sentences: dict[str, set[str]] = {}
    sent_to: list[str] = []
    for method, path in swept(review):
        for who, token in readers.items():
            url = concrete(path)
            sent_to.append(url)
            refused = review.ask(method, url, token=token, json=body_for(method))
            sentence = not_your_role_sentence(refused, f"{method} {path}, asked by {who}")
            sentences.setdefault(sentence, set()).add(f"{method} {path} / {who}")

    seen_at = {sentence: sorted(where)[:4] for sentence, where in sentences.items()}
    assert len(sentences) == 1, (
        f"The 403 is {len(sentences)} different sentences: {seen_at}. Work order decision 1: one "
        "fixed sentence, identical for every non-leadership role."
    )
    (sentence,) = sentences

    people = [
        review.door.person_id,
        review.lead.person_id,
        review.sibling_lead.person_id,
        student_user,
        student_subject,
    ]
    for token in (review.instructor_token, two_hat_instructor, two_hat_leadership):
        claims = claims_in_session(token)
        people.extend([claims.get(SUBJECT_CLAIM), claims.get(USER_ID_CLAIM)])
    forbidden = {
        **{f"the path {url}": url for url in sent_to},
        **{f"the section code {code}": code for code in section_codes(review)},
        **{f"the identifier {who}": str(who) for who in people if who},
    }
    named = sorted(what for what, text in forbidden.items() if text and text in sentence)
    assert not named, f"The 403's sentence {sentence!r} names {named}."


@pytest.mark.invariant
def test_a_decision_from_a_session_in_another_role_is_refused_and_writes_no_row(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 1's "write", against a real queued comment, with the row read back.

    The sweep sends each write a fresh uuid, which a route could refuse for not
    finding as easily as for the role. Here the comment exists and the lead's own
    decision on it, made last, is what proves it was decidable — so "no row"
    after the two refusals is a statement about the gate.

    **The mutations it kills:** a decision route that answers 403 after writing;
    `csrf_verified_leadership` returning the claims for any verified session.
    **The near miss it spares:** the lead's decision, which writes.
    """
    review = lead_review
    comment = review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=QUEUED_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    student, _subject, _user = a_student(review)
    before = review.rows_of(comment)

    for who, token in (("a student", student), ("the instructor", review.instructor_token)):
        refused = review.decide(token, comment, EXCLUDE)
        not_your_role_sentence(refused, f"The decision route, asked by {who}")
        assert review.rows_of(comment) == before, f"The decision refused to {who} wrote a row."

    decided = review.decide(review.lead, comment, EXCLUDE)
    assert is_success(decided.status_code), (
        f"The lead's own decision on the comment answered {decided.status_code}, so the refusals "
        f"above prove nothing about the gate. Body begins {decided.text[:400]!r}."
    )
    assert review.rows_of(comment) != before, "The lead's decision wrote no row."


# ---------------------------------------------------------------------------
# Criterion 2: everything that is not a live session in another role is one 401.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_an_absent_malformed_expired_or_forged_token_gets_one_identical_401_from_every_route(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 2: the same status, body and headers for every token that is not a live session.

    Six credentials, every route: none at all; `not.a.session`; a correctly
    signed student token issued two days ago; a student token signed with
    another key; a **leadership** token naming the real lead, signed with another
    key; and a real student token re-encoded `alg: none`. Each must be the 401
    with today's `NOT_LEADERSHIP` sentence and a `WWW-Authenticate` challenge,
    and the six answers must be indistinguishable: equal bodies, and equal
    headers once the headers that differ between two identical absent-token
    requests are set aside (measured per route, not listed).

    **Green today, and that is its job:** it holds the collapse while the gate
    learns to tell a live session's role. **The mutations it kills:** the role
    read off the token's claims before its signature or expiry is checked — the
    forged and expired student tokens then get the 403, which tells a caller
    trying tokens which ones are real; a gate admitting the forged leadership
    token; a challenge header on some refusals and not others. **The near miss
    it spares:** the real lead, admitted on every route beside them.
    """
    review = lead_review
    student, subject, user_id = a_student(review)
    expired, _s, _u = a_student(review, subject=subject, user_id=user_id, now=issued_long_ago())
    forged_student, _s, _u = a_student(
        review, subject=subject, user_id=user_id, secret=ANOTHER_SECRET
    )
    lead_claims = claims_in_session(review.lead.token)
    forged_lead = review.minted(
        role=LEADERSHIP_LANDING_ROLE,
        person_id=review.lead.person_id,
        user_id=lead_claims.get(USER_ID_CLAIM),
        subject=lead_claims.get(SUBJECT_CLAIM),
        secret=ANOTHER_SECRET,
    )
    credentials = {
        "no token": None,
        "a malformed token": MALFORMED,
        "an expired, correctly signed student token": expired,
        "a student token signed with another key": forged_student,
        "the lead's own claims signed with another key": forged_lead,
        "a student token re-encoded alg none": unsecured(student),
    }
    expected = signed_out_sentence()

    for method, path in swept(review):
        route = f"{method} {path}"
        assert_past_the_gate(
            ask(review, method, path, review.lead.token), route, "the lead", {expected}
        )
        first = ask(review, method, path, None)
        second = ask(review, method, path, None)
        varies = {
            name
            for name in {*first.headers.keys(), *second.headers.keys()}
            if first.headers.get(name) != second.headers.get(name)
        }

        answers = {what: ask(review, method, path, token) for what, token in credentials.items()}
        for what, answered in answers.items():
            assert answered.status_code == SIGNED_OUT_STATUS, (
                f"{route} answered {answered.status_code} to {what}; every token that is not a "
                f"live session gets {SIGNED_OUT_STATUS} (criterion 2). Body begins "
                f"{answered.text[:400]!r}."
            )
            assert detail_of(answered) == expected, (
                f"{route} refused {what} with {detail_of(answered)!r}, not today's "
                f"`NOT_LEADERSHIP` sentence {expected!r}."
            )
            assert answered.headers.get(
                AUTHENTICATE_HEADER
            ), f"{route} refused {what} with no `{AUTHENTICATE_HEADER}` challenge."

        reference = answers["no token"]
        for what, answered in answers.items():
            assert answered.content == reference.content, (
                f"{route} answered {what} with a body that differs from the absent token's: "
                f"{answered.content[:300]!r} against {reference.content[:300]!r}."
            )
            assert stable_headers(answered, varies) == stable_headers(reference, varies), (
                f"{route} answered {what} with headers that differ from the absent token's: "
                f"{stable_headers(answered, varies)} against {stable_headers(reference, varies)}."
            )


@pytest.mark.invariant
def test_an_expired_student_token_gets_the_401_where_the_same_student_live_gets_the_403(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 2's named case, as a pair: one student, two tokens, differing only in when issued.

    **The mutations it kills:** the 403 decided before expiry is checked (the
    expired token then gets the 403); expiry ignored altogether. **The near
    miss:** the same student's live token, which gets the 403 on the same route —
    without it, "the expired one got 401" is equally true of a gate that still
    answers 401 to everybody (which is what it does today, so this is red today
    on the live half).
    """
    review = lead_review
    live, subject, user_id = a_student(review)
    expired, _s, _u = a_student(review, subject=subject, user_id=user_id, now=issued_long_ago())

    for method, path in swept(review):
        route = f"{method} {path}"
        not_your_role_sentence(ask(review, method, path, live), f"{route}, the live student token")
        answered = ask(review, method, path, expired)
        assert answered.status_code == SIGNED_OUT_STATUS, (
            f"{route} answered {answered.status_code} to the same student's token issued "
            f"{EXPIRED_BY_SECONDS} seconds ago. An expired session is an ended one, and the 403 would "
            f"tell its holder it is real. Body begins {answered.text[:400]!r}."
        )
        assert detail_of(answered) == signed_out_sentence()


@pytest.mark.invariant
def test_a_student_token_signed_with_another_key_gets_the_401_where_the_real_one_gets_the_403(
    lead_review: LeadReviewWorld,
) -> None:
    """Ruling 11's reason, as a pair: only the real token earns the 403; its forgery gets the 401.

    **The mutations it kills:** the role read from an unverified decode, so the
    forgery gets the 403 — which is exactly the oracle the ruling forbids ("a
    caller trying tokens still cannot tell a real one from a forgery").
    **The near miss:** the real token for the same student, which gets the 403.
    """
    review = lead_review
    real, subject, user_id = a_student(review)
    forged, _s, _u = a_student(review, subject=subject, user_id=user_id, secret=ANOTHER_SECRET)
    assert forged != real, "The forged token is the real one; the pair would compare nothing."

    for method, path in swept(review):
        route = f"{method} {path}"
        not_your_role_sentence(ask(review, method, path, real), f"{route}, the real student token")
        answered = ask(review, method, path, forged)
        assert answered.status_code == SIGNED_OUT_STATUS, (
            f"{route} answered {answered.status_code} to a student token signed with a key this "
            f"application does not hold. Body begins {answered.text[:400]!r}."
        )
        assert detail_of(answered) == signed_out_sentence()


# ---------------------------------------------------------------------------
# Criteria 3 and 4.
# ---------------------------------------------------------------------------


def test_the_lead_is_past_the_gate_on_every_leadership_route(lead_review: LeadReviewWorld) -> None:
    """Criterion 3 on its own: the leader is admitted everywhere, and answered by queue and log.

    Green today. **The mutations it kills:** a gate that answers 403 to every
    verified session (the "role" check inverted, or compared against the wrong
    enum member); a 403 raised on any session that holds an instructor-shaped
    claim. The queue and log are required to answer 2xx, because "past the gate"
    alone is also what a route that 404s everyone would show.
    """
    review = lead_review
    gate = {signed_out_sentence()}
    for method, path in swept(review):
        assert_past_the_gate(
            ask(review, method, path, review.lead.token), f"{method} {path}", "the lead", gate
        )
    for what, answered in (("queue", review.queue(review.lead)), ("log", review.log(review.lead))):
        assert is_success(answered.status_code), (
            f"The {what} answered {answered.status_code} to the lead of the world's course. Body "
            f"begins {answered.text[:400]!r}."
        )


@pytest.mark.invariant
def test_the_two_hat_persons_instructor_session_gets_403_and_her_leadership_one_is_admitted(
    lead_review: LeadReviewWorld,
) -> None:
    """Criterion 4: one person, two sessions, differing only in the role each names.

    She leads the sibling course and is given an instructor assignment on the
    taught section. **The mutations it kills:** a gate that reads the person's
    assignments rather than the session's role — it admits her instructor
    session, because she holds a leadership grant; a gate that refuses the person
    — it refuses her leadership session too. **Both halves on every route**, and
    the queue and the log answer her leadership session 2xx.
    """
    review = lead_review
    instructor, leadership = the_two_hats(review)
    gate = {signed_out_sentence()}

    for method, path in swept(review):
        route = f"{method} {path}"
        refused = ask(review, method, path, instructor)
        what = f"{route}, the two-hat person's instructor session"
        gate.add(not_your_role_sentence(refused, what))
        assert_past_the_gate(
            ask(review, method, path, leadership), route, "her leadership session", gate
        )

    for what, answered in (("queue", review.queue(leadership)), ("log", review.log(leadership))):
        assert is_success(answered.status_code), (
            f"The {what} answered {answered.status_code} to the two-hat person's leadership "
            f"session. Body begins {answered.text[:400]!r}."
        )
