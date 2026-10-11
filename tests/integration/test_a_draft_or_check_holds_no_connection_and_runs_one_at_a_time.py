"""A model call holds no database connection, and one person runs one at a time — E7-10 done-when 3.

> **A model call holds no database connection, and one person runs one at a time**
> (app-security MED). Every draft and check path (instructor and on-behalf) does
> all its reads before the model call and ends its transaction first; a test's
> gateway stub asserts the pool has no checked-out connection at call time. A
> second draft or check from the same person while one is in flight is refused
> 429 with one fixed sentence before any model call; a test asserts the stub is
> never called for it.

**Why.** A draft or a check waits thirty to sixty seconds on the model. Holding a
pooled connection (an open transaction) for that long means a handful of
concurrent drafts empties the pool, and then every request — a student's submit
included — fails. The work order settles the shape (decision 1): one in-process,
person-keyed in-flight limit shared by all four routes, refused 429 with one
sentence from `copy/`, released in `finally`; the reads, then the commit, then
the model call.

**How "at call time" is measured.** `tests/fixtures/response_draft.py`'s stub
provider runs `before_answer` on its own thread after it has recorded a
completion request and before it answers — that is, while the application is
blocked waiting on the model. The engines are the ones the built application
holds, found by `fixtures.doors.engines_behind` rather than named. The test's own
sessions are on other engines (`application_engine`, `migrated_engine`), so a
checked-out connection in the application's pool at that instant is the
request's. **The control** is read in the same instant: the pool holds at least
one connection, so it is the pool the request read through and not an idle
engine nobody uses.

**How "in flight" is posed.** The first request's model call is held open by the
stub (`before_answer` waits on an event); the second is sent from another thread
while it is held. If the second has not answered within `SECOND_LIMIT` seconds
while the first is held, that is reported as a premise failure (the server would
not serve two requests at once), never as a pass.

**Which failure a red is.** On the epic head the pool test is expected to FAIL on
the checked-out count (the route's session is open across the call), and the
in-flight tests on the status (the second is admitted, and reaches the model).
"""

import threading
from typing import Any
from uuid import uuid4

import pytest
from fixtures.doors import engines_behind
from fixtures.report_api import FULL_WEEK
from fixtures.response_draft import (
    A_PLAIN_DRAFT,
    CHECK,
    DRAFT,
    check_answer,
    draft_answer,
    draft_route,
    registered_sentence_in,
    url_for,
    week_value_for,
)
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    ON_BEHALF_AFTER,
    ON_BEHALF_CHECK,
    ON_BEHALF_DRAFT,
    ON_BEHALF_WEEK,
    LoopWorld,
)
from fixtures.student_read import AUTHENTICATE_SCHEME

pytestmark = pytest.mark.integration

TOO_MANY_REQUESTS = 429

# The four paths done-when 3 names.
INSTRUCTOR_DRAFT = "the instructor's draft"
INSTRUCTOR_CHECK = "the instructor's check"
ON_BEHALF_DRAFT_PATH = "the on-behalf draft"
ON_BEHALF_CHECK_PATH = "the on-behalf check"
EVERY_PATH = (INSTRUCTOR_DRAFT, INSTRUCTOR_CHECK, ON_BEHALF_DRAFT_PATH, ON_BEHALF_CHECK_PATH)

# How long, in seconds, the first request may take to reach the model, how long
# the second has to answer while the first is held, and the outer bound on the
# hold itself (so a red never hangs the worker).
ARRIVAL_LIMIT = 30.0
SECOND_LIMIT = 20.0
HOLD_LIMIT = 60.0


def every_path_is_open(world: LoopWorld) -> None:
    """Course week 1 of `F1WW`, required, unanswered, past +96h: all four paths answer."""
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)


def is_a_check(path: str) -> bool:
    return path in (INSTRUCTOR_CHECK, ON_BEHALF_CHECK_PATH)


def script_a_usable_answer(world: LoopWorld, path: str) -> None:
    world.provider.script(check_answer([]) if is_a_check(path) else draft_answer(A_PLAIN_DRAFT))


def request_for(world: LoopWorld, path: str) -> tuple[str, str, dict[str, str], Any]:
    """Method, URL, headers and body of one path's request, as its person's Bearer session.

    Built here and sent straight through the tool, rather than through the
    world's helpers, because those swap the client's cookie jar around each call
    and two calls in flight on two threads would swap it under each other.
    """
    body: Any = {"draft": A_PLAIN_DRAFT} if is_a_check(path) else {}
    if path in (INSTRUCTOR_DRAFT, INSTRUCTOR_CHECK):
        route = draft_route(world.application, CHECK if is_a_check(path) else DRAFT)
        url = url_for(
            route,
            section_id=world.hold.taught,
            week=week_value_for(route, world.draft.door, FULL_WEEK),
        )
        return "POST", url, world.draft.door.credential(), body
    door = ON_BEHALF_CHECK if is_a_check(path) else ON_BEHALF_DRAFT
    url = world.on_behalf_url(door, section_id=world.hold.taught, course_week=ON_BEHALF_WEEK)
    return door.method, url, {"authorization": f"{AUTHENTICATE_SCHEME} {world.lead.token}"}, body


def send(world: LoopWorld, path: str) -> Any:
    method, url, headers, body = request_for(world, path)
    return world.review.tool.request(method, url, headers=headers, json=body)


def the_applications_engines(world: LoopWorld) -> list[Any]:
    """Every engine the built application holds whose pool can say how many connections are out."""
    engines = [
        engine
        for engine in engines_behind(world.application)
        if callable(getattr(engine.pool, "checkedout", None))
        and callable(getattr(engine.pool, "checkedin", None))
    ]
    if not engines:
        pytest.fail(
            "The built application holds no SQLAlchemy engine whose pool reports `checkedout()` "
            f"and `checkedin()` (it holds {engines_behind(world.application)!r}). Done-when 3 is "
            "measured on that pool; this is a premise failure, not a red."
        )
    return engines


class Background:
    """One request sent on its own thread; its answer, or what it raised."""

    def __init__(self, call: Any) -> None:
        self.answered: Any = None
        self.raised: BaseException | None = None
        self.thread = threading.Thread(target=self._run, args=(call,), daemon=True)
        self.thread.start()

    def _run(self, call: Any) -> None:
        try:
            self.answered = call()
        except BaseException as failure:
            self.raised = failure

    def finished(self, within: float) -> bool:
        self.thread.join(within)
        return not self.thread.is_alive()

    def result(self, what: str) -> Any:
        if self.raised is not None:
            raise AssertionError(f"{what} raised {self.raised!r}") from self.raised
        assert self.answered is not None, f"{what} never answered."
        return self.answered


def hold_the_model(world: LoopWorld) -> tuple[threading.Event, threading.Event]:
    """Make every completion request wait until released; (arrived, release)."""
    arrived, release = threading.Event(), threading.Event()

    def hold() -> None:
        arrived.set()
        release.wait(HOLD_LIMIT)

    world.provider.before_answer = hold
    return arrived, release


def second_while_first_is_held(world: LoopWorld, first: str, second: str) -> tuple[Any, Any, int]:
    """`first` held at the model; `second` sent meanwhile. (first's answer, second's, model calls meanwhile)."""
    script_a_usable_answer(world, first)
    arrived, release = hold_the_model(world)
    before = world.model_calls()
    held = Background(lambda: send(world, first))
    meanwhile: Background | None = None
    try:
        if not arrived.wait(ARRIVAL_LIMIT):
            pytest.fail(
                f"{first} never reached the model within {ARRIVAL_LIMIT}s, so nothing was in "
                "flight for the second request to meet. A premise failure, not a red."
            )
        meanwhile = Background(lambda: send(world, second))
        second_answered_in_time = meanwhile.finished(SECOND_LIMIT)
        calls_meanwhile = world.model_calls() - before
    finally:
        release.set()
        world.provider.before_answer = None
    assert held.finished(HOLD_LIMIT), f"{first} did not finish once released."
    assert meanwhile is not None and meanwhile.finished(HOLD_LIMIT), f"{second} never finished."
    if calls_meanwhile == 1 and not second_answered_in_time:
        pytest.fail(
            f"{second} did not answer within {SECOND_LIMIT}s while {first} was held at the model, "
            "and it did not reach the model either: the server is not serving a second request "
            "while one waits on the model (a synchronous model call inside an async route would "
            "do this). The limit cannot be posed; a premise failure, not a pass."
        )
    return held.result(first), meanwhile.result(second), calls_meanwhile


# ---------------------------------------------------------------------------
# No connection is held across the model call.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", EVERY_PATH)
def test_no_pooled_connection_is_checked_out_while_the_model_is_asked(
    response_loop: LoopWorld, path: str
) -> None:
    """At the instant the stub receives the completion request, the application's pool has none out.

    **The mutations this kills, one per parameter:** the route's session left
    open (an autobegun transaction) across `run_task`; the reads moved before the
    call but the commit or rollback left until after it; a dependency-held session
    (the authorisation read) still open while the model is asked; one of the four
    paths fixed and another not. **The control, in the same instant:** the pool
    holds at least one connection, so the zero is read from the pool the request
    used.
    """
    world = response_loop
    every_path_is_open(world)
    engines = the_applications_engines(world)
    seen: list[tuple[int, int]] = []

    def measure() -> None:
        out = sum(engine.pool.checkedout() for engine in engines)
        idle = sum(engine.pool.checkedin() for engine in engines)
        seen.append((out, out + idle))

    script_a_usable_answer(world, path)
    world.provider.before_answer = measure
    try:
        answered = send(world, path)
    finally:
        world.provider.before_answer = None

    assert 200 <= answered.status_code < 300, (
        f"{path} answered {answered.status_code} to a usable model answer. Body "
        f"{answered.text[:400]!r}."
    )
    assert seen, f"{path} answered without a completion request reaching the stub."
    assert all(pooled >= 1 for _, pooled in seen), (
        f"The application's pool held no connection at all at call time ({seen}), so its zero "
        "checked-out count is not about the pool the request read through. A premise failure."
    )
    assert [out for out, _ in seen] == [0] * len(seen), (
        f"While {path} waited on the model, the application's pool had {[o for o, _ in seen]} "
        "connection(s) checked out. Done-when 3: every draft and check path does all its reads "
        "before the model call and ends its transaction first, so a thirty-second model call "
        "holds no pooled connection."
    )


# ---------------------------------------------------------------------------
# One in flight per person.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (INSTRUCTOR_DRAFT, INSTRUCTOR_DRAFT),
        (INSTRUCTOR_DRAFT, INSTRUCTOR_CHECK),
        (INSTRUCTOR_CHECK, INSTRUCTOR_DRAFT),
        (ON_BEHALF_DRAFT_PATH, ON_BEHALF_DRAFT_PATH),
        (ON_BEHALF_DRAFT_PATH, ON_BEHALF_CHECK_PATH),
        (ON_BEHALF_CHECK_PATH, ON_BEHALF_DRAFT_PATH),
    ],
)
def test_a_second_request_from_the_same_person_while_one_is_in_flight_is_refused_429(
    response_loop: LoopWorld, first: str, second: str
) -> None:
    """The first held at the model; the same person's second: 429, one registered sentence, no model call.

    **The mutations this kills, one per pair:** no limit at all; a limit on one
    route only (the draft's, not the check's — the cross-route pairs); a limit
    keyed per route rather than per person; a limit checked after the gather or
    the model call (the stub then sees a second completion request); a 429 with
    no registered sentence, or an ad hoc one. **The near misses:** the next two
    tests — another person at the same moment, and the same person once the
    first has finished.
    """
    world = response_loop
    every_path_is_open(world)

    held, refused, calls = second_while_first_is_held(world, first, second)

    assert calls == 1, (
        f"While {first} was in flight the stub received {calls} completion requests; {second} "
        "from the same person must be refused before any model call. Done-when 3."
    )
    assert refused.status_code == TOO_MANY_REQUESTS, (
        f"{second} from the same person while {first} was in flight answered "
        f"{refused.status_code}. Done-when 3: refused {TOO_MANY_REQUESTS} with one fixed sentence. "
        f"Body {refused.text[:400]!r}."
    )
    registered_sentence_in(refused, f"The {TOO_MANY_REQUESTS} for {second}")
    assert 200 <= held.status_code < 300, (
        f"{first}, the request in flight, answered {held.status_code} once released. Body "
        f"{held.text[:300]!r}."
    )


def test_another_person_at_the_same_moment_is_admitted(response_loop: LoopWorld) -> None:
    """The teacher's draft held at the model; lead A's on-behalf draft meanwhile: admitted, and asks the model.

    **The mutation this kills:** a global limit (one draft in flight for the whole
    application), which is a denial of service handed to whoever drafts first.
    """
    world = response_loop
    every_path_is_open(world)

    held, other, calls = second_while_first_is_held(world, INSTRUCTOR_DRAFT, ON_BEHALF_DRAFT_PATH)

    assert 200 <= other.status_code < 300, (
        f"Lead A's on-behalf draft, sent while the teacher's draft was in flight, answered "
        f"{other.status_code}. The limit is per person (work-order decision 1). Body "
        f"{other.text[:400]!r}."
    )
    assert calls == 2, f"The stub saw {calls} completion requests; two people, two calls."
    assert 200 <= held.status_code < 300, f"The teacher's held draft answered {held.status_code}."


def test_the_limit_is_released_after_a_request_that_failed(response_loop: LoopWorld) -> None:
    """A check whose model answer is refused (502); the same person's next draft: admitted.

    **The mutation this kills:** the in-flight mark released on success only (not
    in `finally`), which locks a person out of drafting for the life of the
    process after one refused model answer. **The near miss:** the refusal itself,
    asserted first, so the path taken was the failing one.
    """
    world = response_loop
    every_path_is_open(world)

    world.provider.script(check_answer([(f"E7-10 a theme nobody stored {uuid4().hex[:6]}", 3)]))
    failed = send(world, INSTRUCTOR_CHECK)
    script_a_usable_answer(world, INSTRUCTOR_DRAFT)
    before = world.model_calls()
    again = send(world, INSTRUCTOR_DRAFT)

    assert 500 <= failed.status_code < 600, (
        f"A check naming a theme no summary stores answered {failed.status_code}; this test needs "
        "the failing path. A premise failure."
    )
    assert again.status_code == 200, (
        f"After a check that failed, the same person's draft answered {again.status_code}. "
        f"Done-when 3 (work-order decision 1): the in-flight mark is released in `finally`. Body "
        f"{again.text[:400]!r}."
    )
    assert world.model_calls() > before, "The admitted draft made no model call."
