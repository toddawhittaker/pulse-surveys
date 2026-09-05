"""What a post that did not land leaves behind, and what the next run sends — E3-06, criterion 5.

> A failed post retries under the stated policy and stops; the section is left in
> a state an operator could act on rather than in a loop.

The policy is the work order's D4, which takes ADR 0132's stance unchanged:
**there is no in-run retry and no backoff machinery — the weekly schedule is the
retry.** ADR 0132 rejected a retry loop inside the client by name ("a retry loop
inside one post has no memory across runs … against a platform under load, a
client retrying per section is every section retrying at once"), and E3-06 is
the layer that does have memory: it knows what has already been posted, so it is
where a policy about *when* to try again belongs. What an operator sees is the
`ags_call` row and the `grade_sync` row, which is what "a state an operator could
act on" means for a ticket that builds no screen (E11 builds the screen; this
decides what it will read).

Four things are asserted here and each is a different failure.

  - **A refused post is a `FAILED` row carrying the status the platform
    answered**, and the next run tries again. A section whose posts are failing
    then shows the same status once per sweep, which is a rate an eye can read.
  - **A retry re-sends the bytes the stored row holds**, never a fresh
    rendering. ADR 0052 accepts an equal timestamp as a retry of the same
    delivery, which means a re-post carrying a *new* timestamp is a new delivery
    — the ticket's own named trap: "if this ticket re-derives the percentage
    string, a retry after a network timeout can differ from the delivery it is
    retrying and the platform will take it as a second score."
  - **The score timestamp names real time**, not the development clock's
    effective now. ADR 0109 exempts protocol ordering instants from the
    override, and the ticket's traps section says why it has to be settled here:
    rewind the development clock, run a passback, and every post is strictly
    earlier than what the platform holds — which is a 409, which the client
    correctly reads as stop-and-re-read, which is a baffling demonstration.
  - **A 409 is recorded and left**, and the students beside it still post. ADR
    0052: a 409 means the platform holds something newer and there is no point
    retrying; the next sweep's fresh real-time timestamp is later than whatever
    the platform holds, so it heals itself without a loop.

**The wire is where byte identity is read.** A conformant `Result` carries no
timestamp and no comment, and `GET /mock/posted-scores` re-serialises the
number, so the only place the exact string that left this tool can be seen is
the request body recorded by `ServiceWire`.

**Which failure a red here is.** Before E3-06 lands every test is expected red on
`pytest.fail` naming `app.services.grading` as a module that exposes no
`post_scores_for_all_sections` — or, for the retry test, no
`score_timestamp_text`. Both guards are plain calls in a test body
(`docs/MISTAKES.md` entry 44).
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `ags_contract` from
# `tests/fixtures/ags_client.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`.

# The status the wire answers when this module fails a score post. A `500` and
# not a `4xx`: it is unambiguously "the platform reached and broken" rather than
# anything the tool could have sent differently, and it is not the `409` the
# conflict test poses, so the two failures cannot be confused in a row.
A_SERVER_FAILURE = 500

# When a planted `grade_sync` row says it was written. This module's own values;
# nothing reads them back as an answer.
AN_EARLIER_WRITE = datetime(2026, 10, 6, 2, 20, tzinfo=UTC)
A_LATER_WRITE = datetime(2026, 10, 13, 2, 20, tzinfo=UTC)

# How far the wire timestamp may sit outside the window this module measures
# around the call. Generous, because a container start or a slow query inside
# the sweep costs seconds and none of that is the subject; still four orders of
# magnitude inside the weeks that separate real time from the pretended clock.
A_TOLERANCE = timedelta(minutes=5)

# The smallest gap between real time and the pretended clock that makes the
# real-time assertion mean anything. A day: below that the two are close enough
# that a sweep reading the wrong clock could land inside the window above, and
# the test would pass having measured nothing.
A_MEANINGFUL_OFFSET = timedelta(days=1)


def score_posts(book: Any) -> list[Any]:
    """Every `POST` the sweep made to this line item's Score service, in order."""
    path = urlsplit(book.scores_url()).path
    return [call for call in book.wire.calls if call.path == path and call.method.upper() == "POST"]


def sent(call: Any) -> dict[str, Any]:
    """One recorded request's body as a document, or a failure saying it was not one."""
    body = call.body
    if isinstance(body, bytes | bytearray):
        body = body.decode("utf-8")
    try:
        loaded = json.loads(body)
    except (TypeError, ValueError) as unreadable:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"The score post's body is not a JSON document ({unreadable}): {call.body!r}. AGS 2.0 "
            "puts a Score in `application/vnd.ims.lis.v1.score+json`, and this module reads the "
            "exact string that left the tool off the wire because nothing else can see it."
        )
    assert isinstance(loaded, dict), (
        f"The score post carried {loaded!r}, which is not a JSON object. A Score is one object per "
        "student per post."
    )
    return loaded


def raw(call: Any) -> str:
    """One recorded request's body as text, for the assertions about characters."""
    body = call.body
    if isinstance(body, bytes | bytearray):
        return body.decode("utf-8")
    return str(body)


def outcome_of(row: dict[str, Any], sweep_contract: Any) -> str:
    value = row[sweep_contract.outcome_column]
    return str(getattr(value, "value", value))


def a_student_with_a_score(
    gradebooks: Any,
    sweep_contract: Any,
    committed_clock_overrides: Any,
    *,
    students: int = 1,
) -> tuple[Any, list[Any]]:
    """One section past its first window's close, with `students` fully answered."""
    book = gradebooks()
    people = sweep_contract.students(book, students)
    for student in people:
        sweep_contract.answered_fully(book.world, student, through=1)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, 1)
    return book, people


# ---------------------------------------------------------------------------
# A refused post: recorded with the status, and tried again next run.
# ---------------------------------------------------------------------------


def test_a_post_the_platform_refuses_is_a_failed_row_with_its_status_and_the_next_run_retries(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """Criterion 5, both halves, on one section.

    The Score service answers `500`. Afterwards there is one `grade_sync` row
    for the student, marked failed, carrying `500` — not NULL, which
    `nrps_call` and ADR 0129 reserve for a call that never reached the platform
    at all, and which is the difference between "the platform refused us" and
    "we could not get there". The sweep reports one failure and no posts, and
    the platform holds nothing.

    Then the endpoint recovers and the same sweep runs again. A second row
    appears, marked posted; the first is still there carrying its failure; and
    the platform now holds the score. That is the whole of "retries under the
    stated policy and stops": the schedule is the retry, so what has to be
    demonstrated is that a later run picks the section up and that the failed
    attempt was not thrown away in the meantime.

    **The mutations this kills:**

      - a failure swallowed with no row, which leaves an operator with a
        gradebook that stopped updating and nothing anywhere saying why.
      - the failure row rolled back with the section's savepoint. The work order
        (D1) puts each section's work in a savepoint so an unexpected failure
        steps over rather than stopping the walk, and a savepoint that also
        discarded the account of the attempt would leave the same silence — the
        defect this epic already met once, on a failed line-item creation that
        kept the calls it had recorded.
      - `response_code` written NULL for a call that got an answer, which
        collapses ADR 0129's two states into one.
      - an in-run retry loop, caught by the count: one refusal is one post
        attempt and one row, not five.

    **Its pair is the recovery half**, without which every assertion here holds
    of a sweep that fails always — and the failure count is asserted from the
    returned dict as well as from the row, because the task hands that dict to
    E11's dashboard and a sweep that recorded correctly and reported zero
    failures tells an operator nothing is wrong.
    """
    book, people = a_student_with_a_score(gradebooks, sweep_contract, committed_clock_overrides)
    student = people[0]
    outcomes = grade_sync_rows.outcomes()
    book.wire.failing(book.scores_url(), A_SERVER_FAILURE)
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, (
        f"The sweep raised {raised!r} when one student's post was refused. D1 has a failing "
        "section logged and stepped over: an escape here stops every section after it in the walk, "
        "and one platform's bad afternoon becomes the whole institution's."
    )
    assert answered == {sweep_contract.posted_key: 0, sweep_contract.failed_key: 1}, (
        f"The sweep answered {answered!r} after its only post was refused {A_SERVER_FAILURE}. The "
        "task returns this dict and E11's job dashboard renders it; a run that reports no failures "
        "while a section's gradebook has stopped updating is the state this ticket exists to make "
        "visible."
    )
    refused = grade_sync_rows.for_pair(book.id, student.user_id)
    assert len(refused) == 1, (
        f"There are {len(refused)} `grade_sync` rows after one refused post: {refused}. SPEC §8: "
        "'a failed attempt is a row too'. None means the attempt left no trace — and a savepoint "
        "that rolled the row back with the failure it recorded produces exactly this. More than "
        "one is an in-run retry loop, which ADR 0132 rejects by name."
    )
    assert outcome_of(refused[0], sweep_contract) == outcomes["failed"], (
        f"The row carries outcome {outcome_of(refused[0], sweep_contract)!r} after the platform "
        f"answered {A_SERVER_FAILURE}. A refused attempt recorded as a post is a gradebook Pulse "
        "believes it has written to, and the next sweep will compare against it and post nothing."
    )
    assert refused[0][sweep_contract.response_code_column] == A_SERVER_FAILURE, (
        f"The row's `{sweep_contract.response_code_column}` is "
        f"{refused[0][sweep_contract.response_code_column]!r} and the platform answered "
        f"{A_SERVER_FAILURE}. ADR 0129 gives NULL one meaning — the call never reached the "
        "platform — so a status written NULL turns a platform that refused us into a network we "
        "could not cross, which is a different thing to tell an operator."
    )
    assert not book.posted(), (
        f"The platform recorded {book.posted()} while its Score service was answering "
        f"{A_SERVER_FAILURE}. Then the failure is this module's harness rather than the platform's "
        "answer, and everything above is measuring the wrong refusal."
    )

    book.wire.recovering(book.scores_url())
    book.wire.calls.clear()

    recovered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r} on the recovery run."
    assert recovered == {sweep_contract.posted_key: 1, sweep_contract.failed_key: 0}, (
        f"The recovery run answered {recovered!r}. The weekly schedule is this ticket's whole retry "
        "policy (ADR 0132), so a section left failed that the next run does not pick up is a "
        "gradebook that never updates again — and without this half every assertion above holds of "
        "a sweep that can only fail."
    )
    rows = grade_sync_rows.for_pair(book.id, student.user_id)
    assert len(rows) == 2, (
        f"There are {len(rows)} `grade_sync` rows after a refusal and a successful retry: {rows}. "
        "The table is append-only at the grain of one row per post (ADR 0124), so the failed "
        "attempt has to still be there — it is the account of what Pulse tried to do to this "
        "gradebook, and it is what tells an operator the column was stuck for a week."
    )
    assert (
        outcome_of(rows[0], sweep_contract) == outcomes["posted"]
    ), f"The newest row carries {outcome_of(rows[0], sweep_contract)!r} after a successful post."
    assert rows[-1][sweep_contract.response_code_column] == A_SERVER_FAILURE, (
        f"The older row's response code is now "
        f"{rows[-1][sweep_contract.response_code_column]!r} rather than the "
        f"{A_SERVER_FAILURE} it recorded. The retry rewrote the row it was retrying, which is the "
        "one thing an append-only log exists not to do."
    )
    assert len(book.posted()) == 1, (
        f"The platform recorded {book.posted()} after the retry. One delivery: the refused attempt "
        "never arrived and the retry did."
    )


# ---------------------------------------------------------------------------
# The retry carries the bytes the row holds.
# ---------------------------------------------------------------------------


def test_a_retry_of_a_failed_delivery_re_sends_the_stored_bytes_rather_than_a_new_rendering(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """ADR 0052's retry identity, reconstructed from the row — and its other direction.

    A `FAILED` row is planted whose `(score_text, ledger_text)` equals what the
    formula computes and whose `score_timestamp` is a distinctive instant in the
    past, carrying microseconds. Work order D4: that pair is **a retry of that
    delivery**, so the sweep re-sends the stored bytes —
    `score_timestamp_text(latest.score_timestamp)` on the wire, not a fresh
    instant. ADR 0052 has the platform accept an equal timestamp as a repeat of
    the same delivery and a *different* one as a new score, so this single field
    is the difference between a retry and a second grade.

    **The planted row is this test's, not a first run's** (`docs/MISTAKES.md`
    entry 31). And the instant is chosen so no fresh clock read can produce it:
    `2026-03-02T14:05:09.123456+00:00` is months in the past and carries
    microseconds, so a re-derivation through `datetime.now(UTC)` misses it by
    weeks and one through a whole-second render misses it by six digits.

    **The other direction, on the same section.** A newer `FAILED` row is then
    planted whose pair *differs* from the computed value. D4 makes that a new
    delivery rather than a retry, so the wire timestamp must no longer be the
    stored one — without which this test is satisfied by a sweep that always
    sends whatever timestamp it last found in a row, which would freeze a
    section's deliveries at one instant for ever and make every later
    correction invisible to the platform's ordering rule.

    **The mutation this kills**: the timestamp re-derived on the retry path, and
    the score string re-rendered with it. Both are invisible in a gradebook —
    the number is the same — and both turn ADR 0052's retry into a second
    delivery that a platform may accept twice or refuse.

    **`score_timestamp_text` is called rather than reimplemented.** D5 makes it
    the one place a wire timestamp is rendered, so the expectation here is the
    project's own rendering of the instant this test planted rather than a
    second spelling of `isoformat` — a test holding its own copy of the format
    would agree with a wrong one (`docs/MISTAKES.md` entry 19).
    """
    book, people = a_student_with_a_score(gradebooks, sweep_contract, committed_clock_overrides)
    student = people[0]
    expected = sweep_contract.computed(book.world, student, settings=window_settings)
    render = sweep_contract.timestamp_text()
    outcomes = grade_sync_rows.outcomes()
    grade_sync_rows.plant(
        section_id=book.id,
        user_id=student.user_id,
        score_text=expected.percentage,
        ledger_text=expected.ledger,
        outcome=outcomes["failed"],
        score_timestamp=sweep_contract.a_stored_timestamp,
        created_at=AN_EARLIER_WRITE,
        response_code=A_SERVER_FAILURE,
    )
    stored_text = render(sweep_contract.a_stored_timestamp)
    book.wire.calls.clear()

    _answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r} while retrying a failed delivery."
    posts = score_posts(book)
    assert len(posts) == 1, (
        f"The sweep made {len(posts)} posts to the Score service: "
        f"{[f'{call.method} {call.url}' for call in book.wire.calls]}. A `FAILED` latest row whose "
        "stored pair equals the computed one is a delivery to retry (D4), so exactly one post "
        "should have left — none means the sweep read a failed row as 'already posted' and a "
        "section whose posts failed once would never be retried at all."
    )
    body = sent(posts[0])
    assert body.get(sweep_contract.timestamp_member) == stored_text, (
        f"The retry went out with `{sweep_contract.timestamp_member}` = "
        f"{body.get(sweep_contract.timestamp_member)!r} and the row it is retrying stored "
        f"{sweep_contract.a_stored_timestamp!r}, which `{sweep_contract.timestamp_text_name}` "
        f"renders as {stored_text!r}. ADR 0052: an equal timestamp is accepted as a retry of the "
        "same delivery and a different one is a new score. A retry stamped with a fresh clock is "
        "therefore not a retry at all, and the platform — which has no way to tell — records a "
        "second grade."
    )
    assert expected.percentage in raw(posts[0]), (
        f"The retry's body is {raw(posts[0])!r} and the stored score string is "
        f"{expected.percentage!r}. ADR 0124 stores 'the exact string, not a number to be "
        "re-rendered': `61.5` and `61.50` are one quantity and two bodies, and a retry composed "
        "from a re-derived number is not provably the delivery it retries."
    )

    grade_sync_rows.plant(
        section_id=book.id,
        user_id=student.user_id,
        score_text=sweep_contract.a_differing_score,
        ledger_text=sweep_contract.a_differing_ledger,
        outcome=outcomes["failed"],
        score_timestamp=sweep_contract.a_stored_timestamp,
        created_at=A_LATER_WRITE,
        response_code=A_SERVER_FAILURE,
    )
    book.wire.calls.clear()

    _second, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r} on the differing-pair run."
    fresh = score_posts(book)
    assert len(fresh) == 1, (
        f"The sweep made {len(fresh)} posts when the latest row's stored pair differed from the "
        "computed one. D4 makes that a new delivery rather than a retry, so one post should have "
        "left."
    )
    assert sent(fresh[0]).get(sweep_contract.timestamp_member) != stored_text, (
        f"A delivery whose stored pair *differs* from the computed value still went out carrying "
        f"the retry timestamp {stored_text!r}. Then the sweep re-sends whatever instant it last "
        "found in a row, this section's deliveries are frozen at one moment for ever, and every "
        "later correction is refused by the platform's own ordering rule or silently ignored — "
        "and the retry assertion above would hold of a sweep that never derives a timestamp at all."
    )


# ---------------------------------------------------------------------------
# The timestamp names real time, whatever the development clock says.
# ---------------------------------------------------------------------------


def test_the_score_timestamp_is_real_time_even_while_the_development_clock_is_moved(
    gradebooks: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    clock_service: Any,
) -> None:
    """Work order D6, and the ticket's own named trap.

    > The development clock makes a 409 reachable in a demo. Elapsed weeks count
    > off `clock.now` while the beat fires on real time, and the development
    > override accepts a past instant. Rewind it, run a passback, and the score
    > timestamp is strictly earlier than the one the platform already holds —
    > which is a 409.

    ADR 0109 lists the clocks the override deliberately does not reach, and the
    reason each is on that list is the reason this one belongs there: they are
    protocol and observability instants rather than calendar ones. An AGS
    `timestamp` is a *protocol ordering* value — the platform compares it
    against the one it holds and refuses anything strictly earlier — so a tool
    stamping it from a movable clock has made its own ordering rule movable too.

    **Content is effective-clock, delivery is real-clock**, and this test pins
    the second while the first is demonstrably in force: the clock is moved
    weeks forward so that a window has closed and there is something to post at
    all, and the instant that leaves on the wire is required to fall inside the
    span of real time this test measured around the call.

    **The mutation this kills**: `clock.now(session, settings=settings)` used
    for the score timestamp instead of `datetime.now(UTC)` — which is the more
    natural-looking line of the two, because every other instant this service
    reads comes from the clock service.

    **The control that keeps it from being vacuous** (`docs/MISTAKES.md` entry
    3): the pretended clock is required to sit at least a day away from real
    time before anything is asserted. If a machine's own clock ever wandered
    into the window this section's calendar occupies, the two readings would be
    indistinguishable and this test would pass having measured nothing — so it
    says so instead.
    """
    book, _people = a_student_with_a_score(gradebooks, sweep_contract, committed_clock_overrides)
    effective = clock_service.now(book.session, settings=window_settings)
    real = datetime.now(UTC)

    assert abs(effective - real) > A_MEANINGFUL_OFFSET, (
        f"The development clock reads {effective!r} and real time is {real!r}, which are less than "
        f"{A_MEANINGFUL_OFFSET} apart. This test tells a real-time stamp from an effective-clock "
        "one by which of the two the wire value is near, and it cannot do that while they are the "
        "same value. The override is set from this section's own window calendar, so a machine "
        "clock inside Fall 2026 is what produces this."
    )
    book.wire.calls.clear()

    before = datetime.now(UTC)
    _answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )
    after = datetime.now(UTC)

    assert raised is None, f"The sweep raised {raised!r}."
    posts = score_posts(book)
    assert len(posts) == 1, (
        f"The sweep made {len(posts)} score posts, and this test needs exactly one instant to read. "
        f"It called {[f'{call.method} {call.url}' for call in book.wire.calls]}."
    )
    stamped = sent(posts[0]).get(sweep_contract.timestamp_member)
    assert isinstance(stamped, str) and stamped, (
        f"The score post carried `{sweep_contract.timestamp_member}` = {stamped!r}. AGS 2.0 "
        "requires an ISO 8601 instant on every Score, and it is the field the platform's ordering "
        "rule compares."
    )
    delivered = datetime.fromisoformat(stamped)
    assert before - A_TOLERANCE <= delivered <= after + A_TOLERANCE, (
        f"The score went out stamped {stamped!r}. Real time around the call ran from {before!r} to "
        f"{after!r}, and the development clock was reading {effective!r}. A delivery stamped from "
        "the moved clock is the ticket's own trap: rewind the clock in a demo and every post is "
        "strictly earlier than what the platform holds, which is a 409 the client correctly reads "
        "as stop-and-re-read — a correct behaviour and a baffling demonstration. ADR 0109 exempts "
        "protocol ordering instants from the override for this reason."
    )


# ---------------------------------------------------------------------------
# A conflict is recorded, and the student beside it still posts.
# ---------------------------------------------------------------------------


def test_a_conflict_is_recorded_as_a_failure_carrying_409_and_the_other_student_still_posts(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    ags_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """The one refusal a retry cannot fix, and the walk that carries on past it.

    The 409 is planted by giving the platform something **newer** rather than by
    canning a status: a score for one student at an instant far ahead of any
    real clock, posted directly, so the sweep's own real-time stamp is strictly
    earlier — which is exactly the out-of-order passback AGS's 409 exists for
    (ADR 0052).

    Work order D4: a conflict is recorded as a `FAILED` row carrying the literal
    `409` — the typed conflict error the client raises carries no status of its
    own, and an operator reading E11's console has to be able to tell this
    refusal from a `500`, because this one will not be fixed by waiting.

    **The second student is the point of the test.** D4: "A failed student post
    does not stop the section's other students." A sweep that let one 409 end
    the section's walk would leave every student after the alphabetically first
    one ungraded, and the section would look half-posted for the rest of term
    with nothing but a single row to say why.

    **The mutations this kills**: the conflict caught and dropped, leaving no
    row; the conflict recorded with a NULL response code, which ADR 0129 makes
    mean "never reached the platform" and this call plainly did; the conflict
    allowed to escape the student loop, which the second student's post catches;
    and an in-run retry of a 409, which ADR 0052 makes a loop that can only ever
    be refused.

    **The precondition is asserted before the sweep**: the planted score is
    required to have landed, or the "conflict" below would be an ordinary
    successful post wearing this test's name.
    """
    book, people = a_student_with_a_score(
        gradebooks, sweep_contract, committed_clock_overrides, students=2
    )
    conflicted, ordinary = people
    outcomes = grade_sync_rows.outcomes()
    planted = book.platform.post_score(
        book.line_item,
        {
            ags_contract.user_member: conflicted.subject,
            ags_contract.timestamp_member: sweep_contract.a_future_timestamp,
            ags_contract.activity_member: ags_contract.conformant_activity,
            ags_contract.grading_member: ags_contract.conformant_grading,
            ags_contract.given_member: sweep_contract.a_held_score,
            ags_contract.maximum_sent_member: ags_contract.score_maximum,
        },
    )
    assert planted.status_code == 200, (
        f"Planting the newer score answered {planted.status_code}, so the platform holds nothing "
        f"newer and the sweep's post below would simply be accepted. Body begins "
        f"{planted.text[:300]!r}."
    )
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, (
        f"The sweep raised {raised!r} when one student's post met a 409. A conflict is a normal "
        "outcome of a passback against a gradebook somebody has edited, and it must not stop the "
        "walk."
    )
    refused = grade_sync_rows.for_pair(book.id, conflicted.user_id)
    assert len(refused) == 1, (
        f"There are {len(refused)} `grade_sync` rows for the student whose post was refused 409: "
        f"{refused}. SPEC §8 makes a failed attempt a row too, and ADR 0132 makes the `ags_call` "
        "row plus this one the whole of what an operator sees for a section whose posts are "
        "failing."
    )
    assert outcome_of(refused[0], sweep_contract) == outcomes["failed"], (
        f"The conflicted row carries outcome {outcome_of(refused[0], sweep_contract)!r}. A 409 "
        "means the platform kept what it already had, so a row saying we posted is a record of a "
        "grade this tool did not set."
    )
    assert refused[0][sweep_contract.response_code_column] == 409, (
        f"The conflicted row's `{sweep_contract.response_code_column}` is "
        f"{refused[0][sweep_contract.response_code_column]!r} rather than 409. D4 writes the "
        "literal status here because the typed conflict error carries none, and 409 is the one "
        "refusal an operator must be able to tell from the rest: waiting fixes a 500, and only a "
        "later timestamp fixes this."
    )
    posted = grade_sync_rows.for_pair(book.id, ordinary.user_id)
    assert len(posted) == 1 and outcome_of(posted[0], sweep_contract) == outcomes["posted"], (
        f"The student beside the conflict has {posted}. D4: a failed student post does not stop "
        "the section's other students — a walk that ended on the first 409 leaves everyone after "
        "them ungraded for the rest of term, and the section looks half-posted with one row to "
        "explain it."
    )
    assert answered == {
        sweep_contract.posted_key: 1,
        sweep_contract.failed_key: 1,
    }, f"The sweep answered {answered!r} where one post landed and one met a 409."
    held = [
        sweep_contract.body(entry)
        for entry in book.posted()
        if str(entry.get(sweep_contract.user_member)) == conflicted.subject
    ]
    assert len(held) == 1, (
        f"The platform holds {held} for the conflicted student. Only the planted score should be "
        "there: a refused post recorded anyway would mean the 409 came from somewhere other than "
        "the staleness rule, and this test would be measuring a different refusal."
    )
