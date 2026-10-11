"""Who the three routes answer, and who they refuse — ticket E6-05, criteria 5 and 11.

> 5. A person holding only an instructor grant is refused by every route here,
>    over HTTP against the built application, and a leadership person in the
>    same world is answered (entry 47).
> 11. A person whose only leadership grant is `ASSISTANT_DEAN` gets the refusal,
>    as ADR 0108 says, until E9.

**Both directions, per route** (`docs/MISTAKES.md` entry 47): an application that
never registered these routes refuses everybody, so the admitted half runs over
the same world and the same comment and is what keeps the refusals honest.

**Three refused subjects, each a different layer:**

  - the teaching instructor's **own launched session** — refused at the door by
    `require_leadership`, which the body pins: the `NOT_LEADERSHIP` sentence and
    the `WWW-Authenticate: Bearer` challenge E5-06 put on that dependency;
  - a **leadership-role session minted for that same instructor**, who holds no
    leadership grant — past the door, refused by the own-grant scope (work order
    decision 3);
  - a **leadership-role session for an `ASSISTANT_DEAN` alone** — refused by the
    same scope, because an assistant dean's own grant is empty until E9's
    supervision walk (ADR 0108's consequences).

**What "refused" means for the last two.** The work order settles that they get
"the refusal" and not its status. So the assertion is the one every refusal shape
satisfies and an empty answer does not: a 4xx, no planted comment's text anywhere
in the body, and — for the decision — no row. A 200 carrying an empty queue is
red here: the ticket says the reader is refused, and an empty answer is the
absence the house rule says not to assert (a queue that found nothing for an
unrelated reason gives the same empty list).

Marked `invariant` per test on the refusing halves, the way
`test_the_named_set_routes_admit_leadership_and_refuse_everybody_else.py` marks
its own: the isolated §4.1 pass refuses a skip.

**Which failure a red is, before E6-05 lands.** `lead_routes` fails naming the
routes — a FAILED, never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.lead_review import (
    ASSISTANT_DEAN_ROLE,
    EXCLUDE,
    LeadReviewWorld,
    is_a_client_refusal,
    is_success,
)
from fixtures.moderation import HARMFUL
from fixtures.named_sets import NOT_LEADERSHIP, detail_of, refusal_sentence
from fixtures.report_api import FIRST_HELD_WEEK, TAUGHT_COHORT
from fixtures.report_views import COURSE_STREAM
from fixtures.student_read import AUTHENTICATE_HEADER

pytestmark = pytest.mark.integration

ROUTES = ("queue", "log", "decision")
ROLE_REFUSED = 401

QUEUED_TEXT = "E6-05 the held harmful comment every refused reader is asked about"


def a_queued_comment(review: LeadReviewWorld) -> Any:
    return review.plant(
        course_week=FIRST_HELD_WEEK,
        stream=COURSE_STREAM,
        text=QUEUED_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )


def ask(review: LeadReviewWorld, route: str, token: Any, comment: Any) -> Any:
    if route == "queue":
        return review.queue(token)
    if route == "log":
        return review.log(token)
    return review.decide(token, comment, EXCLUDE)


def an_assistant_dean(review: LeadReviewWorld) -> Any:
    return review.a_leader(
        "the-assistant-dean", grants=((ASSISTANT_DEAN_ROLE, review.college),)
    ).token


@pytest.mark.parametrize("route", ROUTES)
def test_a_lead_holding_a_grant_is_answered_by_every_route(
    route: str, lead_review: LeadReviewWorld
) -> None:
    """The admitted half of criterion 5: the same world, the same comment, the lead's session.

    **The mutations this kill:** a router built and never included in
    `create_app`; a route wired to a dependency the leadership session fails.
    """
    review = lead_review
    comment = a_queued_comment(review)
    answered = ask(review, route, review.lead.token, comment)
    assert is_success(answered.status_code), (
        f"The {route} route answered {answered.status_code} to the lead of the comment's course. "
        f"Body begins {answered.text[:400]!r}."
    )


@pytest.mark.invariant
@pytest.mark.parametrize("route", ROUTES)
def test_the_instructors_own_session_is_refused_at_the_door_by_every_route(
    route: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 5 through the instructor's launched session: 401, `NOT_LEADERSHIP`, no row.

    The instructor teaches the very section the queued comment is in, which is
    the strongest subject for the refusal: their own report holds the section.

    **The body pins the layer**, as the named-set module's refusals do: a 401 is
    answered by several things in this stack, and `NOT_LEADERSHIP` belongs to the
    dependency alone. **The mutations this kill:** a route carrying
    `require_instructor` or no role dependency at all; a POST wired to
    `csrf_verified_instructor` (the instructor's Bearer session is admitted and a
    row is written). **The control** is the admitted test beside this one.
    """
    review = lead_review
    comment = a_queued_comment(review)
    before = review.rows_of(comment)

    answered = ask(review, route, review.instructor_token, comment)

    assert answered.status_code == ROLE_REFUSED, (
        f"The {route} route answered {answered.status_code} to the teaching instructor's own "
        f"session; `require_leadership` refuses it with {ROLE_REFUSED}. Body begins "
        f"{answered.text[:400]!r}."
    )
    assert detail_of(answered) == refusal_sentence(NOT_LEADERSHIP), (
        f"The {route} route refused the instructor's session with {detail_of(answered)!r} rather "
        "than the `NOT_LEADERSHIP` sentence, so the refusal did not come from the leadership gate."
    )
    assert answered.headers.get(
        AUTHENTICATE_HEADER
    ), f"The {route} route's refusal carries no `{AUTHENTICATE_HEADER}` challenge."
    assert review.rows_of(comment) == before, f"The refused {route} request wrote a row."


@pytest.mark.invariant
@pytest.mark.parametrize("route", ROUTES)
def test_a_leadership_session_for_a_person_with_only_an_instructor_grant_is_refused(
    route: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 5 one level out: the right session role, and no leadership grant behind it.

    The work order puts the gate in two places — the session's role at the door,
    and the reader's own leadership grant in the read. This session passes the
    first, so only the second can refuse it.

    **The mutations this kill:** a scope read off `resolve_scope`, which holds the
    instructor's taught section and would answer the queue with this very
    comment; a door that, finding no grant, falls back to "every flagged comment".
    **The near miss:** a 200 with an empty list — refused here, because the ticket
    says refused.
    """
    review = lead_review
    comment = a_queued_comment(review)
    before = review.rows_of(comment)
    token = review.a_leadership_session_for_the_instructor()

    answered = ask(review, route, token, comment)

    assert is_a_client_refusal(answered.status_code), (
        f"The {route} route answered {answered.status_code} to a leadership session naming a "
        "person whose only grant is an instructor's. They hold no leadership grant, so the route "
        f"refuses them (criterion 5). Body begins {answered.text[:400]!r}."
    )
    assert QUEUED_TEXT[:40] not in answered.text, f"The {route} refusal carries the comment's text."
    assert review.rows_of(comment) == before, f"The refused {route} request wrote a row."


@pytest.mark.invariant
@pytest.mark.parametrize("route", ROUTES)
def test_an_assistant_dean_alone_is_refused_by_every_route(
    route: str, lead_review: LeadReviewWorld
) -> None:
    """Criterion 11: an `ASSISTANT_DEAN` assignment and nothing else gets the refusal.

    ADR 0108: an assistant dean's own grant is empty by construction, because
    their purview comes from the supervision graph, which is E9's. The world's
    college is theirs; the comment is in a course of it.

    **The mutations this kill:** the own-grant function reading the assistant
    dean's college scope as a grant (the whole college, every lead's course);
    a leadership read that answers any `LEADERSHIP` session with everything
    flagged. **The near miss:** a 200 with an empty queue, which is red here.
    """
    review = lead_review
    comment = a_queued_comment(review)
    before = review.rows_of(comment)
    token = an_assistant_dean(review)

    answered = ask(review, route, token, comment)

    assert is_a_client_refusal(answered.status_code), (
        f"The {route} route answered {answered.status_code} to a person whose only leadership "
        "grant is `ASSISTANT_DEAN`. ADR 0108 fails them closed until E9; the ticket's criterion 11 "
        f"says they get the refusal. Body begins {answered.text[:400]!r}."
    )
    assert QUEUED_TEXT[:40] not in answered.text, f"The {route} refusal carries the comment's text."
    assert review.rows_of(comment) == before, f"The refused {route} request wrote a row."
