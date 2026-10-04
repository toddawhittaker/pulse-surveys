"""A session whose `user_id` is not a uuid is refused on the survey read — E5.1-05, S8.

> **S8.** A malformed `user_id` claim on the survey read answers the student
> refusal, not a 500.

`GET /student/survey` turns the session's `user_id` claim into a `UUID` with no
guard, so a verified student session whose claim is some other string raises out
of the handler as a 500. The work order settles the answer: **`require_student`'s
own refusal** — 401, `WWW-Authenticate: Bearer`, and the `student.not_a_student`
sentence — because that guard already gives one answer to a malformed token, and a
token this deployment did not issue in its shape is the same case.

**What "its own refusal" is asserted as.** Not as three constants copied from
`app.api.deps` — a test that read the numbers out of the module under test would
agree with whatever that module says. It is asserted on the wire, twice over: the
status, header and detail the existing student-read suites already pin (401,
`Bearer`, the registry's `student.not_a_student` text); and **byte-identical** to
what the same route answers a request carrying no session at all, which is
`require_student`'s refusal by definition. A route that invented a fourth answer —
a 400 "bad claim", a 404, a 422 — fails the second even if a later change made the
first agree by accident.

**The pair** is the same student, the same subject, the same issuer and the same
secret, with a well-formed `user_id`: that session is answered 200. The two
tokens differ in the one claim and nothing else, so a route that refused every
minted session is caught by the pair rather than credited by the refusal.

**The session is minted, not launched**, with `tests/fixtures/submit.py`'s
`issue_student_session` — the device E2-08's suites use, signing through the same
`issue_session` both doors issue through. A launch cannot produce this token: the
door writes a real `user.id` into every session it issues, which is exactly why
the claim is unguarded today. The minted token is *verified* — right secret, right
shape — so it reaches the handler, which is where the 500 is.

**Which failure a red is, today.** The handler raises `ValueError` out of
`UUID(...)`. The test client re-raises a server exception into the test by
default, so the request is made inside a `try` that turns that into a failure
naming the 500 — a FAILED on the assertion this ticket is about, never an ERROR.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fixtures.student_read import (
    AUTHENTICATE_HEADER,
    AUTHENTICATE_SCHEME,
    DETAIL_MEMBER,
    NOT_A_STUDENT_KEY,
    REFUSED_STATUS,
    STUDENT_READ_PATH,
)
from fixtures.submit import (
    PLATFORM_ISSUER,
    USER_TABLE,
    SubmitWorld,
    issue_student_session,
    session_secret,
)

pytestmark = pytest.mark.integration

# A `user_id` claim that is a string and is not a uuid. Plain text rather than a
# near-uuid, so the case is unambiguous: no parser accepts it, and it cannot name a
# row by accident.
NOT_A_UUID = "not-a-uuid"


@contextmanager
def carrying_no_cookie(client: Any) -> Iterator[None]:
    """Empty the client's cookie jar for the body, and put it back afterwards.

    The device `tests/fixtures/student_read.py::StudentReadDoor.carrying_no_cookie`
    uses, for its reason: `httpx` merges per-request cookies over the jar rather
    than replacing it, so a request meant to carry exactly one credential has to
    be made with the jar swapped out. Nothing here launched, so the jar should be
    empty already; this makes that a fact rather than an assumption.
    """
    import httpx

    jar = client.cookies
    client.cookies = httpx.Cookies()
    try:
        yield
    finally:
        client.cookies = jar


def read_the_survey(client: Any, token: str | None, what: str) -> Any:
    """One `GET /student/survey`, Bearer `token` or no credential, never an exception.

    A server error the test client re-raises is turned into a failure naming the
    500, so the red this module expects today is an assertion rather than a
    traceback out of the transport.
    """
    headers = {"Authorization": f"{AUTHENTICATE_SCHEME} {token}"} if token is not None else {}
    try:
        with carrying_no_cookie(client):
            return client.get(STUDENT_READ_PATH, headers=headers)
    except Exception as raised:  # the 500 this ticket removes, reported by name
        pytest.fail(
            f"{what}: `GET {STUDENT_READ_PATH}` raised {type(raised).__name__}: {raised} — a 500 "
            "on the wire. E5.1-05 S8: a malformed `user_id` claim on the survey read answers "
            "`require_student`'s refusal (401, `WWW-Authenticate: Bearer`, the "
            f"`{NOT_A_STUDENT_KEY}` text), never a server error."
        )


def a_session_for(world: Any, configured_env: dict[str, str], *, user_id: Any) -> str:
    """A verified student session for `world`'s student, carrying the `user_id` given."""
    return issue_student_session(
        secret=session_secret(configured_env),
        issuer=PLATFORM_ISSUER,
        subject=world.student["lms_user_id"],
        user_id=user_id,
    )


def a_tool_and_a_world(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    open_now: tuple[Any, Any],
    unreachable_ai_provider: str,
) -> tuple[Any, Any]:
    """A seeded section with an open window and an enrolled student, and the tool serving it.

    The AI provider is pointed at a closed port (`unreachable_ai_provider`): the
    survey read calls no model, and a provider that cannot answer makes sure
    nothing here depends on one.
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    client = open_submit_tool(ai_base_url=unreachable_ai_provider)
    return client, world


def test_a_well_formed_student_session_reads_the_survey(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    open_now: tuple[Any, Any],
    unreachable_ai_provider: str,
    configured_env: dict[str, str],
) -> None:
    """The pair's served half: the same student, a uuid `user_id`, answered 200.

    **The mutation this kills:** a guard that refuses every minted session — the
    survey read made to require something a launch supplies and this token does
    not — which would satisfy the refusal test below by refusing everything.
    """
    client, world = a_tool_and_a_world(
        open_submit_tool, submit_world, open_now, unreachable_ai_provider
    )
    token = a_session_for(world, configured_env, user_id=world.student[world.key_of(USER_TABLE)])

    answered = read_the_survey(client, token, "A well-formed student session")
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student session whose "
        "`user_id` is her own row's uuid, enrolled in a section whose window is open. Until this "
        "is served, the refusal of a malformed claim says only that the route refuses minted "
        f"sessions. Body begins {answered.text[:400]!r}."
    )


def test_a_student_session_whose_user_id_is_not_a_uuid_is_refused_as_not_a_student(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    open_now: tuple[Any, Any],
    unreachable_ai_provider: str,
    configured_env: dict[str, str],
    registry_texts: Any,
) -> None:
    """S8: `user_id = "not-a-uuid"` gets `require_student`'s refusal, not a 500.

    **The mutations this kills:** the unguarded `UUID(claims.user_id)` (the 500);
    a guard that answers its own status or sentence — a 400, a 404, a 422, or a
    401 with a different detail — which tells a caller holding a forged-shape
    token something the ordinary refusal does not; and a guard that treats the
    malformed claim like an absent one and answers 200 with no sections, which is
    the `None` case's answer and not this one's.

    **The near miss:** a refusal that matches 401 and the header while carrying a
    different body. So the body is compared byte for byte with the answer to a
    request with no session, which is `require_student`'s own refusal.
    """
    client, world = a_tool_and_a_world(
        open_submit_tool, submit_world, open_now, unreachable_ai_provider
    )
    expected_detail = registry_texts().get(NOT_A_STUDENT_KEY)
    assert expected_detail, (
        f"The copy registry holds no `{NOT_A_STUDENT_KEY}`, so there is no sentence to compare the "
        "refusal against. E2-09 settles that key for the student read's refusal."
    )

    malformed = a_session_for(world, configured_env, user_id=NOT_A_UUID)
    refused = read_the_survey(
        client, malformed, f"A student session whose `user_id` is {NOT_A_UUID!r}"
    )
    no_session = read_the_survey(client, None, "A request carrying no session")

    assert refused.status_code == REFUSED_STATUS, (
        f"A verified student session whose `user_id` is {NOT_A_UUID!r} was answered "
        f"{refused.status_code} rather than {REFUSED_STATUS}. E5.1-05 S8: that is "
        "`require_student`'s refusal. Body begins "
        f"{refused.text[:400]!r}."
    )
    challenge = refused.headers.get(AUTHENTICATE_HEADER) or ""
    assert AUTHENTICATE_SCHEME in challenge, (
        f"The refusal carries `{AUTHENTICATE_HEADER}: {challenge!r}`, which does not name "
        f"`{AUTHENTICATE_SCHEME}`. `require_student` refuses with a Bearer challenge, and this is "
        "its refusal."
    )
    try:
        detail = refused.json().get(DETAIL_MEMBER)
    except (ValueError, AttributeError):
        detail = None
    assert detail == expected_detail, (
        f"The refusal's `{DETAIL_MEMBER}` is {detail!r}; the registry's `{NOT_A_STUDENT_KEY}` is "
        f"{expected_detail!r}."
    )
    assert no_session.status_code == REFUSED_STATUS, (
        f"A request with no session was answered {no_session.status_code}, so it is not the "
        "refusal this test compares against. Body begins "
        f"{no_session.text[:400]!r}."
    )
    assert (refused.status_code, challenge, refused.text) == (
        no_session.status_code,
        no_session.headers.get(AUTHENTICATE_HEADER) or "",
        no_session.text,
    ), (
        "The malformed-claim refusal and the no-session refusal differ.\n"
        f"  malformed `user_id`: {refused.status_code} {challenge!r} {refused.text[:300]!r}\n"
        f"  no session:          {no_session.status_code} "
        f"{no_session.headers.get(AUTHENTICATE_HEADER)!r} {no_session.text[:300]!r}\n\n"
        "The work order settles one answer: `require_student`'s own."
    )
