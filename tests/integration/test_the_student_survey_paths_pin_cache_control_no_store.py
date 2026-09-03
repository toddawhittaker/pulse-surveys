"""E2-15 item 1 / criterion 1 — `Cache-Control: no-store` on both student-survey routes.

`docs/tickets/e2/E2-15-student-surface-and-local-gate-repairs.md` scope item 1:

> The GET returns the student's own prior free-text comment
> (`SubmittedAnswer.comment_text`) and sets no caching header (measured: 200
> with no `Cache-Control`), while the POST sets `no-store`
> (`backend/app/api/student.py:216`). The POST's header is itself pinned by no
> test (measured: removing it survives). Add the header to the GET and a test
> asserting both, so neither can silently vanish.

Criterion 1: "The GET answers with `Cache-Control: no-store`, and removing
either route's header turns a test red (both directions proven once)."

`docs/tickets/e2/boundary-review.md`'s finding is the same shape, from the
docs/ADR completeness check: "`GET /student/survey` sets no `Cache-Control:
no-store` while returning the student's own prior free text; the POST sets it,
and verification found the POST's header is itself pinned by no test."

**Why this is not a §4.1 confidentiality assertion and carries no `invariant`
mark.** `no-store` is caching hygiene on a response that already belongs to
the requesting student — a browser or intermediate cache holding a stale copy
of *their own* prior comment after they have revised or signed out on a shared
machine — not a line about one student seeing another's data. §4.1's own
denial modules are the right home for a cross-student leak; this is an
ordinary pair of tests.

**One test per route, deliberately, rather than one test reading both
responses.** Each route's header is a separate line the implementer can drop
independently — one recipe, one `response.headers[...] =` statement — so
"removing either route's header turns a test red" is proven once per route
rather than by a single assertion that could pass with only one of the two
lines in place.
"""

from typing import Any

import pytest
from fixtures.submit import SubmitWorld, a_valid_submission

pytestmark = pytest.mark.integration

NO_STORE = "no-store"
CACHE_CONTROL_HEADER = "Cache-Control"


def _student_in_an_open_window(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> Any:
    """The standing arrangement this module needs: a seeded world, a running
    tool, and a student signed in — the same shape
    `tests/integration/test_the_submit_path_answers_the_validity_matrix.py`
    builds, written out here rather than imported from it because that module
    is E2-14's this round (the partition in E2-15's work order) and importing
    a helper from a sibling test module would couple two tickets' files that
    have to be able to move independently.
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    return signed_in_student(client, world)


@pytest.mark.lti
def test_the_get_answers_cache_control_no_store(student_read_door: Any) -> None:
    """Criterion 1, first half: `GET /student/survey` answers with `Cache-Control: no-store`.

    The route returns the student's own prior free-text comment
    (E2-09's `test_the_students_own_submission_comes_back_with_the_open_window`
    is the read half of that), so a cache that kept a copy after the student
    revised it, or on a shared machine after they signed out, would go on
    showing it.

    **The mutation this kills:** the GET handler answering with no
    `Cache-Control` header at all, which is the measured state the boundary
    review found — the whole reason this ticket exists.

    **The near miss it must survive:** a header present but spelled some other
    way — `no-cache`, `private`, `max-age=0` — which still lets an
    intermediate cache retain the body under some conditions; only `no-store`
    refuses to retain it at all, and it is compared as an exact value rather
    than as "some caching header is present".
    """
    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET /student/survey` answered {answered.status_code} for a student with one live "
        f"enrollment, inside that section's open window. Body begins {answered.text[:300]!r}."
    )
    header = answered.headers.get(CACHE_CONTROL_HEADER)
    assert header == NO_STORE, (
        f"`GET /student/survey` answered with `{CACHE_CONTROL_HEADER}: {header!r}` rather than "
        f"`{NO_STORE}`. The route returns this student's own prior free-text comment, and E2-15 "
        "item 1 requires the same header the POST already sets, so a cache cannot go on serving a "
        "comment the student has revised or signed out from behind."
    )


def test_the_post_answers_cache_control_no_store(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """Criterion 1, second half, and a must-be-green control at once.

    `backend/app/api/student.py:216` already sets `response.headers["Cache-
    Control"] = "no-store"` on the POST — the boundary review's own measurement
    ("removing it survives") is that nothing pins it. This test is that pin: on
    a clean tree it is expected to pass today, and it is written anyway,
    because a route that answers success while writing nothing is a state
    every *other* test in this ticket would still pass against
    (`docs/MISTAKES.md` entry 2 — behaviour shipped with nothing asserting
    it).

    The submission carries no comment (`a_valid_submission(comment=None)`),
    which needs no verdict from the classifier: the instructor rating is
    above §3.2's "Required if Q1 ≤ 2" threshold and the course comment is
    left blank, so this test is about the header on a plain accepted
    response and nothing about the validity matrix.

    **The mutation this kills:** deleting the `response.headers["Cache-
    Control"] = "no-store"` line from the POST handler — today green,
    the header line removed, red.
    """
    student = _student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    answered = student.submit(a_valid_submission(comment=None))

    assert 200 <= answered.status_code < 300, (
        f"A complete submission with no comment answered {answered.status_code} rather than "
        f"success. Body begins {answered.text[:400]!r}. This test is about the response header, "
        "and the header assertion below means nothing against a response that was refused."
    )
    header = answered.headers.get(CACHE_CONTROL_HEADER)
    assert header == NO_STORE, (
        f"The submit path answered with `{CACHE_CONTROL_HEADER}: {header!r}` rather than "
        f"`{NO_STORE}`. `backend/app/api/student.py` sets this header on every accepted "
        "submission, and E2-15's boundary-review finding is that nothing in this suite pinned it "
        "— this is that pin."
    )
