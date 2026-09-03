"""SPEC §4.1 item 1, over the instant FIX-01 item 4 adds — ticket FIX-01.

Item 1: "Students never see comparables, benchmarks, university averages, or
**other sections** — in charts, text, tooltips, exports, or aria labels." FIX-01
puts a second section-scoped fact on the one student-visible read path: the
instant the next survey opens. A window instant is a fact about a course
calendar, and the sentence built out of it — "When the next survey for this
course opens at 6:00PM EDT on Friday, October 9, it appears here." — announces a
date. Announcing *another cohort's* date is item 1 in plain sight.

**Why this is a module of its own, and why the marker sits at module level.**
The security review of FIX-01 found this pin sitting in
`test_the_student_read_answer_names_the_next_window.py`, outside the isolated
invariant pass: a later loosening of the `section_id` predicate in
`next_window_for_section` would then pass the §4.1 gate while a student's page
announced another cohort's calendar. The repair is not a decorator.
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
pins one currency and refuses every other — its discriminating planted offender
is exactly a module-level `pytestmark` carrying other marks beside an
`@pytest.mark.invariant` on the one denial test — because a module half inside
the pass "reads, to every later reader, exactly like a module inside it", and the
module's *next* denial test inherits nothing.

So the pin moves out to its own module, marked at module level in the list form,
the way its sibling
`test_the_course_label_names_nothing_outside_the_students_enrollment.py` is. The
name is deliberate as well: `names_nothing` is one of that sweep's
`DENIAL_NAME_SHAPES`, so from now on the marker is **enforced** by a gate rather
than by whoever reads the next diff. That is the difference between a convention
and a guarantee (`docs/MISTAKES.md` entry 2), and it is what the review found
missing — the sweep was silent about the old module because its name made no
denial claim.

**Why the world's sibling section works as a needle here, where it does not for
the course label.** `tests/fixtures/student_read.py` seeds two sections under one
containment chain on purpose, so they share a course and therefore share a
*label* — which is why the label's denial module has to seed a foreign course.
Window instants are different: a window belongs to a section, and this world's
two sections can be given windows over **different term weeks**, so the other
one's opening instant is a value nothing correct can produce.

**And the other section's window is the earlier of the two, which is the whole
test.** The reader's own next window is term week 15's; the section they are not
enrolled in gets term week 14's. So the earliest future window in the database is
not the reader's, and a lookup ordered by `opens_at` with no section predicate
answers the wrong one. Were the reader's the earlier of the pair, that same
mutation would return the correct answer and survive with the suite green
(`docs/MISTAKES.md` entry 3) — which is the shape E2-09's own mutation battery
measured on this world's enrollment predicate.

**The near miss this must survive** is the one that has caught this project
repeatedly: an answer that returned *nothing* names no other section's window
either. So the reader's **own** instant is required to be present and correct
before anything is reported absent.
"""

import pytest
from fixtures.student_read import (
    AFTER_THE_WINDOW,
    NEXT_TERM_WEEK,
    NEXT_WINDOW_FIELD,
    NEXT_WINDOW_OPENS_AT,
    OTHER_NEXT_WINDOW_OPENS_AT,
    OTHER_SECTIONS_NEXT_TERM_WEEK,
    STUDENT_READ_PATH,
    StudentReadDoor,
    around,
    decoded,
    instant_carried,
    instants_in,
    response_surface,
    sole_entry,
)
from fixtures.survey_windows import WINDOW_OPENS_COLUMN

pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]


def test_the_next_window_named_is_the_readers_own_sections_and_no_other(
    student_read_door: StudentReadDoor,
) -> None:
    """SPEC §4.1 item 1: the instant named is this reader's section's, and no other's.

    **Why this test is in the unskippable pass.** CLAUDE.md makes the §4.1 suite
    one CI runs in isolation, treating a skip, an xfail or an empty collection as
    a failure. This assertion is the only thing standing between a widened
    `next_window_for_section` and a student's page announcing another cohort's
    survey date; outside that pass it is a test that can be skipped, and a skipped
    confidentiality test is indistinguishable from one nobody wrote.

    Two sections are closed at this instant and both have a window ahead. The one
    the reader is enrolled in opens in term week 15; the one they are **not**
    enrolled in opens in term week 14, a week *earlier*. So a read that asked
    "which window opens next" without saying whose section it is asking about
    answers the wrong one.

    **The mutations this kills.** A next-window lookup with no `section_id`
    predicate. One joined to the course, or to the term, or to the week rather
    than to the section — the two sections here are siblings under one course of
    one term, so all three reach the other's row. And one scoped to the section
    but ordered descending, which returns the *last* window rather than the next.

    **The near misses it must survive.** The correct answer, which names term week
    15's instant and nothing else. And an answer that carries no instant at all,
    which names no other section's window either — so the reader's own is
    asserted first, before the denial, rather than instead of it
    (`docs/MISTAKES.md` entry 3).

    **The canaries, first.** The two windows are required to exist at the instants
    this test names, the other section's is required to be the earlier, and both
    are required to be ahead of the clock — without which an unscoped query has
    nothing wrong to reach and this test cannot fail.
    """
    world = student_read_door.world
    assert OTHER_NEXT_WINDOW_OPENS_AT < NEXT_WINDOW_OPENS_AT, (
        f"The other section's next window ({OTHER_NEXT_WINDOW_OPENS_AT}) is not earlier than this "
        f"reader's ({NEXT_WINDOW_OPENS_AT}). It has to be earlier, or a lookup that ignores the "
        "section returns the reader's own window anyway and this test passes against the mutation "
        "it exists to kill."
    )
    assert AFTER_THE_WINDOW < OTHER_NEXT_WINDOW_OPENS_AT, (
        f"{OTHER_NEXT_WINDOW_OPENS_AT} is not ahead of the instant this test reads at "
        f"({AFTER_THE_WINDOW}), so it is not a window an unscoped 'next' query would reach."
    )

    mine = world.seed_window_over(world.enrolled_section, NEXT_TERM_WEEK)
    theirs = world.seed_window_over(world.other_section, OTHER_SECTIONS_NEXT_TERM_WEEK)
    assert (mine[WINDOW_OPENS_COLUMN], theirs[WINDOW_OPENS_COLUMN]) == (
        NEXT_WINDOW_OPENS_AT,
        OTHER_NEXT_WINDOW_OPENS_AT,
    ), (
        f"The two seeded windows open at {mine[WINDOW_OPENS_COLUMN]} and "
        f"{theirs[WINDOW_OPENS_COLUMN]}; term weeks {NEXT_TERM_WEEK} and "
        f"{OTHER_SECTIONS_NEXT_TERM_WEEK} of Fall 2026 open at {NEXT_WINDOW_OPENS_AT} and "
        f"{OTHER_NEXT_WINDOW_OPENS_AT}."
    )
    student_read_door.pretend(AFTER_THE_WINDOW)

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code}. Body begins "
        f"{answered.text[:300]!r}. A refusal names no other section's window either, so this sweep "
        "cannot be allowed to pass over one."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")
    entry = sole_entry(body, answered)

    assert entry[NEXT_WINDOW_FIELD] is not None, (
        f"The answer carries no `{NEXT_WINDOW_FIELD}` at all, so the denial below would be a "
        f"statement about an empty member. Body begins {answered.text[:400]!r}. Until FIX-01 item "
        "4 lands this is the assertion that reds, and it names the deliverable."
    )
    assert instant_carried(entry, answered) == NEXT_WINDOW_OPENS_AT, (
        f"The answer names {entry[NEXT_WINDOW_FIELD]!r} as this reader's next opening. Their own "
        f"section's next window opens at {NEXT_WINDOW_OPENS_AT}; the section they are not enrolled "
        f"in opens at {OTHER_NEXT_WINDOW_OPENS_AT}, a week earlier.\n\n"
        "The earlier instant here is a lookup with no section predicate, or one joined to the "
        "course, the term or the week — the two sections are siblings under one course of one "
        "term, so every one of those reaches the other's row."
    )

    surface = response_surface(answered)
    leaked = sorted(
        spelling
        for spelling in (
            OTHER_NEXT_WINDOW_OPENS_AT.isoformat(),
            OTHER_NEXT_WINDOW_OPENS_AT.isoformat().replace("+00:00", "Z"),
        )
        if spelling in surface
    )
    assert not leaked and OTHER_NEXT_WINDOW_OPENS_AT not in instants_in(body), (
        f"The answer names {OTHER_NEXT_WINDOW_OPENS_AT}, which is when a survey opens for a "
        "section this student is not enrolled in. It carries the instants "
        f"{sorted(instants_in(body))}"
        + (f", and the text sits in {around(surface, leaked[0])!r}" if leaked else "")
        + ".\n\nSPEC §4.1 item 1: a student is never shown another section, in any surface. A "
        "window instant is a fact about somebody else's course calendar, and it reaches the page "
        "the moment a 'when does the next one open' lookup stops naming a section."
    )
