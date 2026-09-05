"""No post leaves the sweep without its per-week ledger — ticket E3-06, criterion 4.

> **Every posted score carries the ledger.** No post leaves this task without the
> per-week comment E3-03 produced, asserted by reading the posted comment back
> rather than by reading the code that composed it. A post with an empty or
> absent comment is a failure of this criterion, since the comment is the only
> place §3.4's arithmetic is visible to anyone (ADR 0125).

SPEC §3.4: "Each posted score carries a **per-week ledger** in its AGS comment:
one line per elapsed week, of the form `Week 1: 4 of 5 items`, in course-week
order." ADR 0125 is what makes that load-bearing rather than decorative — v1
ships no student-facing or instructor-facing view of the participation score, so
this comment is the only place the arithmetic behind a posted percentage is
visible to anyone at all. A percentage delivered without it is a number nobody
can check.

**Read back, never recomputed.** The comparison is between what
`participation_scores` answered and what `GET /mock/posted-scores` says the
platform received (ADR 0047, the only surface that can say what was *sent* —
a conformant AGS `Result` carries no comment at all). Nothing in this module
composes a ledger line: `tests/fixtures/grading.py`'s `ledger_of` exists and is
deliberately not used here, because a test holding its own rendering of the
thing under test is `docs/MISTAKES.md` entry 19, and criterion 4 asks for a
comparison between the formula's output and the platform's copy of it rather
than between two renderings this suite made.

**The two students differ, and that is the instrument.** One answers both weeks
in full; the other misses a week entirely, which §3.4 requires in the
denominator as `0 of N` rather than omitted. So their ledgers are different
strings, and a sweep that composed one ledger per section — or that reused the
last student's — fails here while a sweep that sent the right count of posts
still passes everywhere else.

**Which failure a red here is.** Before E3-06 lands this is expected red on
`pytest.fail` naming `app.services.grading` as a module that exposes no
`post_scores_for_all_sections`, raised from a plain call in the test body
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`. All are reached as fixtures rather than imported.

# The course week the second student leaves unanswered. Week 1 rather than the
# last one, so the missing week sits *inside* the ledger rather than at its end:
# a carriage that truncated the ledger, or that dropped empty weeks, moves a
# line that other students still have.
A_SKIPPED_WEEK = 1

# How many course weeks have elapsed when the sweep runs. Two, because a
# one-line ledger cannot show a carriage that took only the first line, joined
# with a comma, or re-wrapped.
ELAPSED_WEEKS = 2


def commented(entry: Any, sweep_contract: Any) -> Any:
    """The comment member of one recorded score body, however the platform stored it."""
    return sweep_contract.body(entry).get(sweep_contract.comment_member)


def recorded_for(book: Any, subject: str, sweep_contract: Any) -> list[Any]:
    """Every score body the platform holds for one student's subject, in arrival order."""
    return [
        entry for entry in book.posted() if str(entry.get(sweep_contract.user_member)) == subject
    ]


def test_the_comment_the_platform_received_is_the_ledger_the_formula_produced(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """Criterion 4, asserted between two things this module did not write.

    Two students, two different ledgers, one sweep. For each of them the comment
    the platform received is required to equal, byte for byte, the `ledger`
    field `participation_scores` answered — and the two students' ledgers are
    required to differ from each other, so a sweep that sent one string to
    everybody cannot pass.

    **The mutations this kills:**

      - the comment omitted from the post, or sent empty. A gradebook shows the
        percentage either way, so nothing an instructor or a student can see
        would change and no other test in this suite would notice; what
        disappears is the only explanation of the number that exists anywhere
        (ADR 0125).
      - the ledger composed by the sweep instead of taken from the formula's
        answer, which puts §3.4's arithmetic in two places and makes the comment
        agree with itself rather than with the score beside it.
      - the ledger computed once per section and reused, which the differing
        pair catches and a single-student test cannot.

    **The `grade_sync` row is asserted against the same string**, because ADR
    0124 has the row record what was sent and ADR 0052's retry reconstruction
    re-sends it: a row whose `ledger_text` disagrees with the comment on the
    wire cannot reconstruct the delivery it describes, and the retry would be a
    new one.

    **Two non-vacuity guards run first** (`docs/MISTAKES.md` entry 3). The
    ledger the formula produced has to be non-empty and to span more than one
    line, or "the comment equals the ledger" is satisfied by a sweep sending an
    empty string and a formula answering one; and the two students' ledgers have
    to differ, or the per-student assertion is one assertion made twice.
    """
    book = gradebooks()
    complete, partial = sweep_contract.students(book, 2)
    for course_week in range(1, ELAPSED_WEEKS + 1):
        book.world.answer_week(complete, course_week)
        if course_week != A_SKIPPED_WEEK:
            book.world.answer_week(partial, course_week)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, ELAPSED_WEEKS)
    expected = {
        student.subject: sweep_contract.computed(book.world, student, settings=window_settings)
        for student in (complete, partial)
    }

    assert expected[complete.subject].ledger != expected[partial.subject].ledger, (
        f"Both students' ledgers are {expected[complete.subject].ledger!r}. One answered every "
        f"item of both weeks and the other missed course week {A_SKIPPED_WEEK} entirely, so §3.4 "
        "gives them different arithmetic — with the two equal, a sweep that composed one comment "
        "per section would pass every assertion below."
    )
    for subject, score in expected.items():
        assert score.ledger and "\n" in score.ledger, (
            f"The ledger the formula produced for {subject!r} is {score.ledger!r}, which is empty "
            f"or a single line over {ELAPSED_WEEKS} elapsed weeks. §3.4 gives it one line per "
            "elapsed week, and against a one-line value 'the comment equals the ledger' cannot see "
            "a carriage that truncated, re-wrapped or joined with a comma."
        )

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r} rather than posting two scores."
    assert answered[sweep_contract.posted_key] == 2, (
        f"The sweep reports {answered!r} where two students each needed a first post. With fewer, "
        "the comment assertions below would be about a delivery that never happened."
    )
    for student in (complete, partial):
        bodies = recorded_for(book, student.subject, sweep_contract)
        assert len(bodies) == 1, (
            f"The platform recorded {len(bodies)} scores for {student.subject!r}: {bodies}. There "
            "is one delivery to read a comment off, and zero of them means this student's post "
            "never left."
        )
        carried = commented(bodies[0], sweep_contract)
        assert carried, (
            f"The score the platform received for {student.subject!r} carries "
            f"{carried!r} as its `{sweep_contract.comment_member}`. Criterion 4: 'A post with an "
            "empty or absent comment is a failure of this criterion' — the percentage arrives "
            "either way, and the only account of how it was arrived at does not."
        )
        assert carried == expected[student.subject].ledger, (
            f"The platform holds the comment {carried!r} for {student.subject!r} and the formula "
            f"produced {expected[student.subject].ledger!r}. These are compared rather than "
            "inspected because the criterion is a comparison: a ledger the sweep composed for "
            "itself would look perfectly well formed and would be a second implementation of "
            "§3.4's arithmetic, disagreeing with the first the moment a question set version "
            "changes a week's denominator."
        )
        rows = grade_sync_rows.for_pair(book.id, student.user_id)
        assert rows, (
            f"There is no `grade_sync` row for {student.subject!r} after their score was posted. "
            "ADR 0124 makes every attempt a row, and the next sweep compares against it."
        )
        assert rows[0][sweep_contract.ledger_text_column] == carried, (
            f"The row records the ledger {rows[0][sweep_contract.ledger_text_column]!r} and the "
            f"platform received {carried!r}. A row that disagrees with what was sent cannot "
            "reconstruct the delivery it describes, so ADR 0052's retry would carry a different "
            "body and the platform would take it as a second score."
        )
