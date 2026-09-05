"""Posting stops at the drop, and the LMS keeps the column — ticket E3-06, criterion 6.

> A dropped student's score stops updating, and the value the platform holds is
> the one the last successful post sent.

SPEC §3.4's last line: "Drops: scores stop updating; the LMS owns what happens to
the column." Two halves, and only the first is this tool's to enforce — nothing
here deletes a grade, blanks a column or posts a zero, because what a gradebook
does with the entry of a student who left is the platform's decision and not
Pulse's.

**Where the stop lives, and why it is here rather than in the formula.** ADR
0131 has `participation_scores` go on computing a dropped student's score
deliberately: the formula answers what the enrolled weeks add up to, and it is
not the place that decides who is still enrolled. So the sweep is the one place
the stop exists, which means it is the one place a test can measure it — and it
also means a sweep that simply posted whatever the formula answered would keep
updating a departed student's grade every Monday for the rest of term.

**The predicate is the one `authz.py` already uses** (work order D10): a student
posts while `started_on <= clock.today AND (ended_on IS NULL OR ended_on >=
clock.today)` holds of any of their enrollment rows, so a drop-and-re-add has two
rows and the live one wins. The boundary is `ended_on = clock.today`, and it is
asserted from both sides one day apart, because that day is the whole width of
the rule: a student whose enrollment ends today was enrolled today.

**Which failure a red here is.** Before E3-06 lands both tests are expected red
on `pytest.fail` naming `app.services.grading` as a module that exposes no
`post_scores_for_all_sections`, from a plain call in the test body
(`docs/MISTAKES.md` entry 44).
"""

from datetime import date, timedelta
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`; `clock_service` from `tests/fixtures/clock.py`.

# The day the clock is stood on. **Chosen against this section's own calendar,
# not invented**: cohort `F`'s course week 1 closes on 2026-10-04 23:59:59 in
# `America/New_York` and course week 2 closes a week later, so noon on the 6th
# is a day inside which exactly one window has shut. That is the smallest world
# in which "a score exists to stop updating" is true at all.
A_DAY_AFTER_THE_FIRST_WINDOW = date(2026, 10, 6)

# How many course weeks have elapsed on that day. Asserted rather than assumed
# by the control below, because every claim in this module rests on there being
# something to post.
ELAPSED_WEEKS = 1

A_DAY = timedelta(days=1)


def outcome_of(row: dict[str, Any], sweep_contract: Any) -> str:
    value = row[sweep_contract.outcome_column]
    return str(getattr(value, "value", value))


def bodies_for(book: Any, subject: str, sweep_contract: Any) -> list[dict[str, Any]]:
    return [
        sweep_contract.body(entry)
        for entry in book.posted()
        if str(entry.get(sweep_contract.user_member)) == subject
    ]


def test_an_enrollment_that_ends_today_still_posts_and_one_that_ended_yesterday_does_not(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    clock_service: Any,
) -> None:
    """The live-enrollment boundary, both sides, one day apart, in one sweep.

    Two students in one section, answering identically, differing in exactly one
    value: one enrollment ends *today* and the other ended *yesterday*. Work
    order D10 keeps the student whose enrollment ends today — `ended_on >=
    clock.today` — because a student whose enrollment ends today was enrolled
    today, and a rule that dropped them would stop posting a day early for every
    student in every institution.

    **Both directions in one run**, which is what makes either mean anything.
    The refusing half alone is satisfied by a sweep that posts for nobody, and
    the accepting half alone by one that posts for everybody; posed together on
    one section, one clock and one platform, the only thing that can produce
    both answers is a live-enrollment test with its boundary in the right place.

    **The mutations this kills**: the predicate written `ended_on > clock.today`,
    which drops the boundary student and is invisible to any test that only
    poses a drop weeks in the past; the predicate dropped altogether, caught by
    the yesterday half; and the predicate applied to the wrong clock — it is
    `clock.today` in the institution's timezone (SPEC §3.1, ADR 0109), and this
    test stands the clock at noon so a reader that resolved the date in UTC and
    one that resolved it in `America/New_York` still agree, leaving the
    comparison itself as the only thing that can be wrong.

    **The dropped student's absence is asserted as no row and no delivery**, not
    as a zero: SPEC §3.4 gives the LMS the column, and a Pulse that posted a
    final zero for a student who left would be writing a judgement about them
    into a record it does not own.

    **The control runs first**: the effective clock has to actually stand on the
    day this test computed its two dates from, or both enrollments are on the
    same side of a boundary nobody moved.
    """
    book = gradebooks()
    staying, leaving = sweep_contract.students(book, 2)
    for student in (staying, leaving):
        sweep_contract.answered_fully(book.world, student, through=ELAPSED_WEEKS)
    book.world.rows.commit()
    today = book.world.clock_at(committed_clock_overrides, A_DAY_AFTER_THE_FIRST_WINDOW)

    effective = clock_service.today(book.session, settings=window_settings)
    assert effective == today, (
        f"The clock service reads today as {effective!r} and this test moved the override to "
        f"{today!r}. The two enrollment dates below are computed from the second, so with the two "
        "disagreeing both students sit on the same side of a boundary this test never posed."
    )
    book.world.drop(staying, ended_on=today)
    book.world.drop(leaving, ended_on=today - A_DAY)
    book.world.rows.commit()
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r}."
    kept = grade_sync_rows.for_pair(book.id, staying.user_id)
    assert (
        len(kept) == 1
        and outcome_of(kept[0], sweep_contract) == (grade_sync_rows.outcomes()["posted"])
    ), (
        f"The student whose enrollment ends today has {kept}. D10 keeps them — `ended_on >= "
        "clock.today` — because a student whose enrollment ends today was enrolled today. A "
        "predicate written with a strict `>` stops posting a day early for every student who ever "
        "leaves, which nobody notices until a term's last day."
    )
    gone = grade_sync_rows.for_pair(book.id, leaving.user_id)
    assert not gone, (
        f"The student whose enrollment ended yesterday has {gone}. SPEC §3.4: 'Drops: scores stop "
        "updating; the LMS owns what happens to the column.' ADR 0131 has "
        "`participation_scores` go on computing their score deliberately, so this sweep is the one "
        "place the stop exists — without it a departed student's grade keeps changing every Monday "
        "for the rest of term."
    )
    assert not bodies_for(book, leaving.subject, sweep_contract), (
        f"The platform recorded {bodies_for(book, leaving.subject, sweep_contract)} for the "
        "dropped student. The absent row above is only half the claim: what matters is that "
        "nothing reached the gradebook, and a sweep that posted and failed to record would satisfy "
        "the row assertion while writing into the column of somebody who left."
    )
    assert answered == {
        sweep_contract.posted_key: 1,
        sweep_contract.failed_key: 0,
    }, f"The sweep answered {answered!r} where one of two students was still enrolled."


def test_a_drop_after_a_post_leaves_the_platform_holding_what_the_last_post_sent(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """Criterion 6 in full: the stop is a stop, and nothing is taken back.

    A student is posted for while enrolled. They then drop, and a
    reclassification lowers what the formula computes for them — which is the
    case ADR 0131 makes reachable, since the formula goes on answering for a
    dropped student. The next sweep must do nothing at all: no post, no row, and
    the platform still holding the number the last successful post sent.

    **Both halves of the criterion's sentence, and the second is the one a
    "stop" alone does not give you.** A sweep that stopped posting *and* blanked
    the column, or posted a final zero, or re-posted a recomputed value once
    more on the way out, would satisfy "stops updating" in a loose reading and
    would be writing into a record §3.4 hands to the LMS.

    **The mutation this kills**: the live-enrollment predicate applied when
    *choosing* students but not when deciding to post, so the drop is honoured
    on the run after next; and the enrollment read taken once at the start of
    the walk from a stale snapshot, which this test's ordering — post, drop,
    sweep — exposes because the drop lands between two runs of the same process.

    **The precondition is asserted before the second sweep** (`docs/MISTAKES.md`
    entry 3): the reclassification is required to have actually changed what the
    formula computes, or "no second post" is true for the ordinary reason that
    nothing differed, and the drop would be doing none of the work.
    """
    book = gradebooks()
    (student,) = sweep_contract.students(book, 1)
    week_one = book.world.answer_week(student, 1)
    book.world.answer_week(student, 2)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, 2)
    before = sweep_contract.computed(book.world, student, settings=window_settings)

    first, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r} on the run that was meant to post."
    assert first == {sweep_contract.posted_key: 1, sweep_contract.failed_key: 0}, (
        f"The first sweep answered {first!r}. Criterion 6 is about what happens *after* a "
        "successful post, and with none there is no held value for the drop to preserve."
    )
    delivered = bodies_for(book, student.subject, sweep_contract)
    assert (
        len(delivered) == 1
    ), f"The platform recorded {delivered} for this student on the first sweep."

    today = book.world.clock_at(committed_clock_overrides, A_DAY_AFTER_THE_FIRST_WINDOW)
    book.world.drop(student, ended_on=today - A_DAY)
    comments = book.world.comment_positions()
    assert comments, (
        "The question set carries no comment item, so nothing can be reclassified and this test "
        "cannot make the formula's answer move."
    )
    book.world.classify(
        week_one[comments[0]],
        sweep_contract.nonsense,
        classified_at=book.world.closes_at(1) + timedelta(days=3),
    )
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, 2)
    after = sweep_contract.computed(book.world, student, settings=window_settings)

    assert after.percentage != before.percentage, (
        f"The reclassification left the computed percentage at {after.percentage!r}. ADR 0131 has "
        "the formula go on answering for a dropped student, so this test needs its answer to have "
        "*moved* — otherwise the silence below is the ordinary no-difference case and the drop is "
        "doing none of the work."
    )
    book.wire.calls.clear()

    second, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r} on the run after the drop."
    assert not book.wire.calls, (
        f"The sweep made {[f'{call.method} {call.url}' for call in book.wire.calls]} for a student "
        "who had dropped, while their computed score had changed. §3.4 stops updating at the drop."
    )
    rows = grade_sync_rows.for_pair(book.id, student.user_id)
    assert len(rows) == 1, (
        f"There are {len(rows)} `grade_sync` rows after a post, a drop and a second sweep: {rows}. "
        "One — the post made while they were enrolled. A second row is this tool still writing "
        "about somebody who left."
    )
    still = bodies_for(book, student.subject, sweep_contract)
    assert len(still) == 1, (
        f"The platform holds {still} for the dropped student. Criterion 6's second half: 'the value "
        "the platform holds is the one the last successful post sent.' A second delivery — a "
        "recomputed value, a final zero, a blanking — is this tool editing a record SPEC §3.4 "
        "hands to the LMS."
    )
    assert float(still[0].get(sweep_contract.given_member)) == float(before.percentage), (
        f"The platform holds {still[0].get(sweep_contract.given_member)!r} and the last successful "
        f"post sent {before.percentage!r}. Compared as quantities because the platform "
        "re-serialises the number; byte identity on the wire is E3-04's criterion 3."
    )
