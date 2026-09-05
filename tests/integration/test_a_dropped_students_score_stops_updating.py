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
rows and the live one wins.

**It has two boundaries and both are asserted from both sides, one day apart**,
because a day is the whole width of each rule. `ended_on = clock.today` is the
one the criterion's own sentence is about: a student whose enrollment ends today
was enrolled today. `started_on = clock.today` is the other end of the same
`AND`, and it went unasserted until a mutation battery mutated `<=` to `<` and
watched the whole suite stay green — a student is enrolled on the day they
arrive, and a strict comparison silently withholds the first post of everybody
who is added on a Monday morning. Each boundary gets one test posing both of its
sides in one run, for the reason each of those tests states.

**Which failure a red here is.** Before E3-06 lands all three tests are expected
red on `pytest.fail` naming `app.services.grading` as a module that exposes no
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

# The course week the `started_on` pair below dates its platform window from.
# Course week 1 rather than the term week it falls in: SPEC §3.4's tier 1 is "the
# earliest course week whose `closes_at` is at or after `lms_window_start`", so a
# window start at week 1's *opening* instant credits a student from week 1
# whatever day Pulse first saw them. That is what lets those two students differ
# in `started_on` and in nothing else the formula can see.
#
# The opening instant rather than the closing one, though tier 1's comparison is
# inclusive and either would credit week 1: the open sits a clear three days
# inside the week on both sides of that `>=`, so this test cannot go red on the
# one-character question `test_the_first_enrolled_week_follows_the_three_tiers.py`
# owns.
THE_FIRST_COURSE_WEEK = 1

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


def subjects_for(book: Any, count: int) -> list[str]:
    """`count` subjects for this section: the platform's own first, then this module's.

    `sweep_contract.students` cannot be used by the `started_on` test below — it
    enrolls every student on the section's own start date, which is the one value
    that test varies — so the subject half of what it does is repeated here. The
    padding is safe for the same reason it is safe there: a mock platform records
    a score against whatever `userId` it is sent — and the first subject, which
    is the platform's own wherever the seeded context offers one, goes to the
    student that test requires a real delivery for.
    """
    subjects = list(book.section.subjects)
    while len(subjects) < count:
        subjects.append(f"e3-06-start-boundary-{len(subjects) + 1}")
    return subjects[:count]


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


def test_an_enrollment_that_starts_today_posts_and_one_that_starts_tomorrow_does_not(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    clock_service: Any,
) -> None:
    """The other end of D10's predicate, both sides, one day apart, in one sweep.

    `started_on <= clock.today`. Two students in one section, answering
    identically and credited from the same course week, differing in exactly one
    value: one enrollment starts *today* and the other starts *tomorrow*. A
    student is enrolled on the day they arrive, so the first must be posted for
    and the second must not.

    **The mutations this kills, and the first one survived a full battery run.**
    The predicate written `started_on < clock.today`, which withholds the first
    post of every student added on the morning of a sweep — invisible to every
    other test in these eight modules, because they all enroll their students on
    the section's own start date, weeks before any clock this suite stands on.
    And the condition dropped altogether, caught by the tomorrow half: without it
    a section's whole future roster gets a score the day the row appears.

    **Both directions in one run**, for the reason the `ended_on` test above
    gives: the refusing half alone is satisfied by a sweep that posts for nobody
    and the accepting half alone by one that posts for everybody.

    **The two students are made identical to the formula, and that control is the
    whole instrument.** `lms_window_start` is set to course week 1's *opening*
    instant for both, which is SPEC §3.4's tier 1 — the platform's own dated
    window, which outranks `started_on` — so both are credited from week 1 and
    `participation_scores` answers the same score for each. Without that, the
    student starting tomorrow would have no elapsed enrolled week for the
    *formula's* reason, no post would be made for them whatever the sweep's
    predicate said, and this test would report a killed mutant while measuring
    nothing (`docs/MISTAKES.md` entry 3). The equality is asserted before the
    sweep runs, so a red there is this construction failing rather than the
    criterion.

    A member the platform dated earlier than Pulse first saw them is the ordinary
    shape rather than a contrived one: it is what tier 1 exists for, and it is
    what a roster sync writes for anybody added between two syncs.

    **The control on the clock runs first**, as above: the effective date has to
    be the one both enrollment dates were computed from, or the two students sit
    on the same side of a boundary nobody posed.
    """
    book = gradebooks()
    today_subject, tomorrow_subject = subjects_for(book, 2)
    window_start = book.world.opens_at(THE_FIRST_COURSE_WEEK)
    arriving_today = book.world.student(
        today_subject,
        started_on=A_DAY_AFTER_THE_FIRST_WINDOW,
        lms_window_start=window_start,
    )
    arriving_tomorrow = book.world.student(
        tomorrow_subject,
        started_on=A_DAY_AFTER_THE_FIRST_WINDOW + A_DAY,
        lms_window_start=window_start,
    )
    for student in (arriving_today, arriving_tomorrow):
        sweep_contract.answered_fully(book.world, student, through=ELAPSED_WEEKS)
    book.world.rows.commit()
    today = book.world.clock_at(committed_clock_overrides, A_DAY_AFTER_THE_FIRST_WINDOW)

    effective = clock_service.today(book.session, settings=window_settings)
    assert effective == today, (
        f"The clock service reads today as {effective!r} and this test moved the override to "
        f"{today!r}. The two enrollment dates are computed from the second, so with the two "
        "disagreeing both students sit on the same side of a boundary this test never posed."
    )
    arrived = sweep_contract.computed(book.world, arriving_today, settings=window_settings)
    arriving = sweep_contract.computed(book.world, arriving_tomorrow, settings=window_settings)
    assert arriving == arrived, (
        f"The formula answers {arriving!r} for the student starting tomorrow and {arrived!r} for "
        "the one starting today. They are seeded identically but for `started_on`, and both carry "
        "the same `lms_window_start` — SPEC §3.4's tier 1, which outranks it — so the two scores "
        "have to be the same score. Where they are not, the silence below belongs to the formula "
        "and not to the sweep's live-enrollment predicate, and a mutation to that predicate would "
        "leave this test green (`docs/MISTAKES.md` entry 3)."
    )
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r}."
    kept = grade_sync_rows.for_pair(book.id, arriving_today.user_id)
    assert (
        len(kept) == 1
        and outcome_of(kept[0], sweep_contract) == (grade_sync_rows.outcomes()["posted"])
    ), (
        f"The student whose enrollment starts today has {kept}. D10's predicate is `started_on <= "
        "clock.today` and a student is enrolled on the day they arrive; written with a strict `<` "
        "it withholds the first post of everybody added on the morning of a sweep, and every other "
        "test in these modules enrolls its students weeks earlier and never notices."
    )
    ahead = grade_sync_rows.for_pair(book.id, arriving_tomorrow.user_id)
    assert not ahead, (
        f"The student whose enrollment starts tomorrow has {ahead}. Their row exists — a roster "
        "sync can record a future add — and until the day it names they are not enrolled, so a "
        "sweep that posts for them is writing a participation grade for somebody who has not "
        "started the course."
    )
    assert not bodies_for(book, arriving_tomorrow.subject, sweep_contract), (
        f"The platform recorded {bodies_for(book, arriving_tomorrow.subject, sweep_contract)} for "
        "the student who starts tomorrow. The absent row above is only half the claim: a sweep "
        "that posted and failed to record would satisfy it while writing into that student's "
        "column."
    )
    assert answered == {
        sweep_contract.posted_key: 1,
        sweep_contract.failed_key: 0,
    }, f"The sweep answered {answered!r} where one of two students had started."


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
