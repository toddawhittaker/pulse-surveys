"""What one GET answers for a student, right now — ticket E2-09.

E2-10's form needs one question answered: *for me, right now, what is there?*
E2-09's first acceptance criterion is that the whole of it is answerable "in one
round trip against the seeded stack, with the dev clock deciding open/closed",
and this module is that criterion, split into the behaviours it is made of: the
enrolled section with its open window and the questions to answer, whether the
window is open at all, the student's own submission when there is one, and the
copy a refusal is written in.

**What is *not* here** is SPEC §4.1 item 1 and the two §4 denials beside it —
the other section, a classmate's submission, and the sessions this path refuses.
Those are
`tests/integration/test_the_student_read_path_names_nothing_outside_the_enrollment.py`,
which sits inside the isolated invariant pass. This module is the ordinary half
and carries no `invariant` marker, deliberately: the two are different kinds of
claim and CI runs one of them twice.

**Every assertion here is spelling-independent where the ticket leaves the
spelling open**, and says so where it is. E2-09 settles what the answer *carries*
— the section, the window's instants, whether it is open now, the question rows,
the student's own answers — and settles no JSON schema for it. So an instant is
compared as an instant after parsing whatever ISO-8601 the answer wrote, a
question is looked for by the wording that was stored, and "open now" is measured
as a boolean that is true inside the window and not true on either side of it,
wherever in the answer it sits. A test that pinned key names would be choosing an
interface the ticket left to the implementer; a test that pinned nothing would
assert nothing.

**The one exception is the pair of week numbers, and it is an exception because
the spec settles it.** E2-09's work order said only "week number", while SPEC §2.2
(docs/SPEC.md:82) gives a student's course-level page the *course* week with a
quiet term-week sub-label — so the answer carries both, under exactly
`course_week` and `term_week`, and those two are the only response members any
test here names. The gap was raised rather than guessed at, and the ruling of
2026-09-01 closed it from the spec; even so the fields are found by walking the
answer rather than by indexing a shape, because *where* they sit is still the
implementer's to choose.
"""

from typing import Any

import pytest
from fixtures.student_read import (
    AFTER_THE_WINDOW,
    BEFORE_THE_WINDOW,
    COPY_STUDENT_READ_MODULE,
    COURSE_WEEK_FIELD,
    DETAIL_MEMBER,
    ENROLLED_FIRST_TERM_WEEK,
    EXPECTED_COURSE_WEEK,
    EXPECTED_TERM_WEEK,
    INSIDE_THE_WINDOW,
    NOT_A_STUDENT_KEY,
    OWN_COMMENT,
    OWN_WORKLOAD,
    STUDENT_READ_PATH,
    TERM_WEEK,
    TERM_WEEK_FIELD,
    WINDOW_CLOSES_AT,
    WINDOW_OPENS_AT,
    CopyRegistry,
    StudentReadDoor,
    booleans_in,
    decoded,
    instants_in,
    objects_carrying,
    response_surface,
)

pytestmark = [pytest.mark.integration, pytest.mark.lti]


def test_one_get_answers_the_enrolled_sections_open_window_and_its_questions(
    student_read_door: StudentReadDoor,
) -> None:
    """Criterion 1: the form's whole question, answered in one round trip.

    One `GET`, no parameters, and everything E2-10 needs to render the form comes
    back with it: the section this student is enrolled in, the instants the week's
    window opens and closes at, and every question of the set — because a form
    that has to fetch its own questions afterwards has not answered the question
    in one round trip, and a form that is handed a window with no questions cannot
    be filled in.

    **The mutations this kills.** A route that answers the enrollment and leaves
    the caller to fetch the window, or the questions, from somewhere else. A
    question set joined so that only the first row comes back — all five are
    required by wording, so a `LIMIT` or a join that collapses the set fails here
    naming the ones that are missing. And a window rendered from the wrong week:
    the instants are compared as moments against E2-06's hand-written table for
    term week 13, so a window derived from the term's first week, or from the
    section's own start rather than the term-week Monday, is a different moment
    and is caught.

    **The near miss it must survive**: the answer may carry more than this. Only
    what the criterion names is asserted, and it is asserted as presence rather
    than as an exact shape, so a benign field arriving later does not turn this
    red for a reason unrelated to what it guards (`docs/MISTAKES.md` entry 2's
    own preference).
    """
    world = student_read_door.world
    answered = student_read_door.get()

    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student with one live "
        f"enrollment, inside that section's open window. Body begins {answered.text[:300]!r}."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")
    surface = response_surface(answered)

    assert str(world.enrolled_section_id) in surface, (
        f"The answer does not name the section this student is enrolled in "
        f"({world.enrolled_section_id}). E2-09 answers per live enrollment with the section, the "
        f"week, the window and the questions; body begins {answered.text[:300]!r}."
    )

    carried = instants_in(body)
    missing_instants = [
        instant for instant in (WINDOW_OPENS_AT, WINDOW_CLOSES_AT) if instant not in carried
    ]
    assert not missing_instants, (
        f"The answer carries no instant equal to {missing_instants}. It carries "
        f"{sorted(carried)}.\n\n"
        "Those two are when term week 13's window opens and closes, out of the hand-written table "
        "in `tests/fixtures/survey_windows.py` that E2-06's own suites are measured against — "
        "SPEC §3.1's Friday 18:00 to Sunday 23:59:59 in the institution's timezone. They are "
        "compared as moments rather than as strings, so any ISO-8601 spelling passes and a "
        "different moment does not: an instant that is close but not equal is a window derived "
        "from the wrong week, or one zone conversion applied to the pair rather than to each end."
    )

    absent = [text for text in world.question_texts if text not in surface]
    assert not absent, (
        f"{len(absent)} of the {len(world.question_texts)} questions in the set are missing from "
        f"the answer: {absent}. SPEC §3.2 gives v1 five questions and E2-10 renders them from what "
        "this read path returns; a form handed a window and no questions cannot be filled in, and "
        "one handed some of them silently drops a required field §3.3 then counts as unanswered."
    )


def test_the_answer_names_the_course_week_and_the_term_week_the_window_is_over(
    student_read_door: StudentReadDoor,
) -> None:
    """SPEC §2.2: the course week, with the term week beside it, under both names.

    §2.2 (docs/SPEC.md:82) gives a student's course-level page the *course* week
    with a quiet term-week sub-label, so the answer carries both numbers and
    E2-10 renders one under the other. The two field names are the ruling of
    2026-09-01 and are the only response members any test in this ticket names:
    `course_week` is the ordinal from the section's own start — the window's term
    week minus the section's first active term week, plus one — and `term_week` is
    the window's week row's `number`.

    **The section is chosen so that every wrong answer is a different number.**
    Its window is over term week 13 of a section that began in term week 4, so
    the right pair is 10 and 13, and:

      - **serving the term week in the `course_week` field answers 10 → 13**, which
        is the near miss the whole pair exists for and the reason both fields are
        asserted rather than one. A page that labels term week 13 as "week 13 of
        your course" tells a student in a 15-week section that they are three
        weeks further through it than they are, and §3.4 scores participation over
        the items of every week they were enrolled for;
      - **the offset without §2.2's inclusive `+ 1` answers 9**, the ordinary
        off-by-one, which a section whose window sits in its own first week could
        never distinguish from a correct 1 minus nothing;
      - **a hard-coded or defaulted field answers 1**, which is also what every
        first-week section answers correctly — so a fixture built on one would
        have made this test agree with a constant;
      - **the two swapped answer 13 and 10**, which one field alone cannot see.

    **The expectation is written out rather than computed**, and the arithmetic is
    asserted against the cohort's own facts instead: an expectation derived by the
    same formula as the code under test agrees with an implementation that made
    the same mistake (`docs/MISTAKES.md` entry 19). The guard is what keeps the
    literal honest if the fixture's cohort ever changes.

    **The fields are found by walking the answer**, not by indexing it: the ruling
    settles the two names and settles nothing about where they sit, so one object
    per enrollment, a list under a member, or a mapping keyed by section all pass —
    and an answer carrying neither name fails saying which one it is missing.
    """
    assert TERM_WEEK - ENROLLED_FIRST_TERM_WEEK + 1 == EXPECTED_COURSE_WEEK, (
        f"The enrolled section begins in term week {ENROLLED_FIRST_TERM_WEEK} and its window is "
        f"over term week {TERM_WEEK}, which makes that the section's "
        f"{TERM_WEEK - ENROLLED_FIRST_TERM_WEEK + 1}th course week — not the "
        f"{EXPECTED_COURSE_WEEK} this test expects. The cohort in "
        "`tests/fixtures/student_read.py` has moved and the expectation there has not moved with "
        "it, so this test is pinning the wrong number."
    )
    assert TERM_WEEK == EXPECTED_TERM_WEEK, (
        f"The window this world seeds is over term week {TERM_WEEK} and this test expects "
        f"{EXPECTED_TERM_WEEK}."
    )
    assert EXPECTED_COURSE_WEEK != EXPECTED_TERM_WEEK, (
        f"The expected course week and term week are both {EXPECTED_COURSE_WEEK}, so this test "
        "cannot tell one field from the other and would pass against an answer that served the "
        "same number in both. The cohort must be one whose window is not in its own first week."
    )

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code}. Body begins "
        f"{answered.text[:300]!r}."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")

    carrying = objects_carrying(body, COURSE_WEEK_FIELD, TERM_WEEK_FIELD)
    assert carrying, (
        f"Nothing in the answer carries both `{COURSE_WEEK_FIELD}` and `{TERM_WEEK_FIELD}`: "
        f"{len(objects_carrying(body, COURSE_WEEK_FIELD))} object(s) carry the first and "
        f"{len(objects_carrying(body, TERM_WEEK_FIELD))} carry the second. Body begins "
        f"{answered.text[:300]!r}.\n\n"
        "SPEC §2.2 plots a student's course-level page on the course week with the term week as a "
        "sub-label, so E2-10 needs both from this one read — one of them alone is a number with no "
        "axis. The two names are the ruling of 2026-09-01 and are exact."
    )

    wrong = [
        found
        for found in carrying
        if (found[COURSE_WEEK_FIELD], found[TERM_WEEK_FIELD])
        != (EXPECTED_COURSE_WEEK, EXPECTED_TERM_WEEK)
    ]
    assert not wrong, (
        f"The answer reports {[(f[COURSE_WEEK_FIELD], f[TERM_WEEK_FIELD]) for f in wrong]} as "
        f"(`{COURSE_WEEK_FIELD}`, `{TERM_WEEK_FIELD}`); this window is over term week "
        f"{EXPECTED_TERM_WEEK}, which is course week {EXPECTED_COURSE_WEEK} of a section that began "
        f"in term week {ENROLLED_FIRST_TERM_WEEK}.\n\n"
        f"If the course week reads {EXPECTED_TERM_WEEK}, the term week is being served in its "
        "place — the two are different numbers for the same week and §2.2 keeps them apart because "
        "a 15-week section that started late is not thirteen weeks into itself. If it reads "
        f"{EXPECTED_COURSE_WEEK - 1}, the offset is being taken without §2.2's inclusive first "
        "week. If it reads 1, nothing is computing it at all."
    )


def test_the_answer_says_open_only_while_the_development_clock_is_inside_the_window(
    student_read_door: StudentReadDoor,
) -> None:
    """Criterion 1's second half: the dev clock decides open and closed.

    Three reads of the same route by the same student, differing only in what the
    `clock_override` row pretends the instant is: before the window opens, inside
    it, and after it closes. The answer must say "open" in the middle read and not
    in either of the others.

    **Measured as a boolean that flips, rather than as a key name.** E2-09 settles
    that the answer carries "whether open now" and settles no name for it, so the
    booleans of all three answers are collected by the path they sit at and the
    test requires at least one path that is `true` inside the window and not
    `true` on either side. A field absent from the closed answers counts as not
    open, which is the honest reading of "the open window **if any**" — what is
    forbidden is an answer that says open when it is not.

    **The mutations this kills.** A hard-coded `true`, which never flips. A window
    compared against the process clock rather than through `app.services.clock`,
    which answers the same thing at all three pretended instants because the real
    clock did not move. And a comparison that uses only one edge — `opens_at <=
    now` with no upper bound, or `now <= closes_at` with no lower — each of which
    is true in two of these three reads and is caught by the third.

    **The near miss it must survive**: the two closed reads still answer 200 and
    still name the enrolled section. A route that answered nothing at all outside
    the window would satisfy a boolean sweep and fail here, because a student
    whose window has closed is still enrolled and still has to be told so.
    """
    world = student_read_door.world
    assert BEFORE_THE_WINDOW < WINDOW_OPENS_AT < INSIDE_THE_WINDOW < WINDOW_CLOSES_AT, (
        f"The instants this test pretends do not sit where it says: {BEFORE_THE_WINDOW} / "
        f"{INSIDE_THE_WINDOW} against a window of {WINDOW_OPENS_AT} to {WINDOW_CLOSES_AT}. They are "
        "constants in `tests/fixtures/student_read.py` and the window is E2-06's own table; if "
        "either has moved, this test is measuring the wrong sides of the wrong window."
    )
    assert WINDOW_CLOSES_AT < AFTER_THE_WINDOW, (
        f"{AFTER_THE_WINDOW} is not after the window closes at {WINDOW_CLOSES_AT}, so the third "
        "read below is not the closed case it claims to be."
    )

    seen: dict[str, dict[str, bool]] = {}
    for name, instant in (
        ("inside", INSIDE_THE_WINDOW),
        ("before", BEFORE_THE_WINDOW),
        ("after", AFTER_THE_WINDOW),
    ):
        student_read_door.pretend(instant)
        answered = student_read_door.get()
        assert answered.status_code == 200, (
            f"With the development clock pretending {instant} ({name} the window), "
            f"`GET {STUDENT_READ_PATH}` answered {answered.status_code}. Body begins "
            f"{answered.text[:300]!r}. A student whose window has not opened, or has closed, is "
            "still enrolled: the answer says there is nothing open, it does not refuse."
        )
        assert str(world.enrolled_section_id) in response_surface(answered), (
            f"With the clock {name} the window, the answer no longer names the section this "
            f"student is enrolled in ({world.enrolled_section_id}). Body begins "
            f"{answered.text[:300]!r}. The enrollment does not come and go with the window."
        )
        seen[name] = booleans_in(decoded(answered, f"the `{name}` read"))

    open_flags = sorted(
        path
        for path, value in seen["inside"].items()
        if value is True
        and seen["before"].get(path) is not True
        and seen["after"].get(path) is not True
    )
    assert open_flags, (
        "No part of the answer says the window is open inside it and stops saying so outside it.\n"
        f"  inside the window: {seen['inside']}\n"
        f"  before it opens:   {seen['before']}\n"
        f"  after it closes:   {seen['after']}\n\n"
        "E2-09 answers whether the window is open now, and SPEC §3.1 makes that a comparison "
        "against the institution's clock — which in development is the `clock_override` row this "
        "test moved between the three reads (ADR 0109). A flag that never flips is one that was "
        "hard-coded, or one compared against the process clock, which did not move; a flag that is "
        "true on one side and not the other is a comparison written with one edge instead of two."
    )


def test_the_students_own_submission_comes_back_with_the_open_window(
    student_read_door: StudentReadDoor,
) -> None:
    """The resubmit case: what this student already answered is in the answer.

    E2-10 lets a student revise a submission while the window is open, and it can
    only render the form pre-filled if this read path returns what they wrote. So
    the student submits — a comment and an hours figure, the two currencies §3.2's
    five questions answer in — and both come back.

    **The mutations this kills.** A read path that returns the window and the
    questions and no submission at all, which makes every resubmission look like a
    first one and quietly discards what the student wrote. A lookup that finds the
    `response` row and never joins its `answer` rows, which returns "you have
    submitted" and nothing to render. And a join that returns only one kind of
    answer — the comment but not the workload — which is what a filter on
    `comment_text IS NOT NULL` does, and which E2-05's own "an answer holds
    exactly one value" makes easy to write.

    **The near miss it must survive** is next door and is asserted there: the same
    read, by the same student, with a classmate's submission stored and none of
    their own, must carry nothing. Together the two are the boundary pair —
    echoed when it is theirs, absent when it is not.
    """
    world = student_read_door.world
    world.submit_own()

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} after this student submitted. "
        f"Body begins {answered.text[:300]!r}."
    )
    surface = response_surface(answered)

    mine = world.anything_shaped_like_my_own_answer()
    unstored = world.not_stored(mine)
    assert not unstored, (
        f"This student's own {unstored} are not in the `answer` table, so the assertion below "
        f"would be about values nothing wrote. What is stored: "
        f"{sorted(world.stored_answer_values())[:8]}."
    )

    absent = sorted(value for value in mine if value not in surface)
    assert not absent, (
        f"The answer does not carry this student's own {absent}. They wrote "
        f"{OWN_COMMENT!r} and {OWN_WORKLOAD} hours, both stored against their `response` row for "
        f"this section and week; body begins {answered.text[:300]!r}.\n\n"
        "E2-09 answers with 'own current submission (answers) if any' precisely so E2-10's form "
        "can render the resubmit case. A comment returned without the hours, or the other way "
        "round, is a join that reads one of `answer`'s three value columns and not the row."
    )


def test_the_refusal_copy_is_served_from_the_registry_rather_than_the_router(
    student_read_door: StudentReadDoor, copy_registry: CopyRegistry
) -> None:
    """E2-09's scope: "whatever refusal copy this path serves is externalized".

    The refusal a request with no session gets must be the string the copy
    registry holds under `student.not_a_student` — not a string written into the
    router beside it. E2-11 reads that registry to check this project's whole
    user-facing vocabulary against SPEC §4.1 items 4 and 5, and a string spelled
    in a handler is a string that inventory cannot see.

    **The mutations this kills.** The detail written as a literal in
    `app/api/deps.py`, which passes every other test in these two modules and
    leaves the copy inventory one entry short of the truth. And an entry present
    in the registry under a different key, which E2-11 would find as an orphan and
    this path would not be using.

    **What it deliberately does not assert** is the wording. What the refusal
    *says* is a copy decision E2-11 owns and this ticket does not settle; what is
    asserted is that the two are the same string, whatever it is.
    """
    assert copy_registry.entries, (
        f"`{copy_registry.package.__name__}.copy_modules()` yielded "
        f"{[module.__name__ for module in copy_registry.modules]} and no `CopyEntry` was found on "
        "any of them, so this test is comparing a refusal against an empty registry. E2-09 adds "
        "`app/copy/student_read.py` carrying this path's user-facing strings."
    )
    module_names = {module.__name__ for module in copy_registry.modules}
    assert COPY_STUDENT_READ_MODULE in module_names, (
        f"`copy_modules()` does not yield `{COPY_STUDENT_READ_MODULE}`; it yields "
        f"{sorted(module_names)}. E2-09 puts this path's copy there, and `copy_modules()` is what "
        "E2-11 discovers it through — a module the discovery does not reach is copy nothing "
        "inventories."
    )
    expected = copy_registry.entries.get(NOT_A_STUDENT_KEY)
    assert expected, (
        f"The registry holds no entry keyed `{NOT_A_STUDENT_KEY}`; it holds "
        f"{sorted(copy_registry.entries)}. That key is E2-09's settled name for the refusal this "
        "path serves a session that is not a student's."
    )

    refused = student_read_door.get_without_a_session()
    body = decoded(refused, f"`GET {STUDENT_READ_PATH}` with no session")
    detail = body.get(DETAIL_MEMBER) if isinstance(body, dict) else None

    assert detail == expected, (
        f"The refusal's `{DETAIL_MEMBER}` is {detail!r} and the registry's "
        f"`{NOT_A_STUDENT_KEY}` is {expected!r}.\n\n"
        "E2-09's scope: the refusal copy this path serves is externalized in the registry shape "
        "E2-08 established, for E2-11 to read. A literal in the router is a string the copy "
        "inventory cannot see, and §4.1 items 4 and 5 are checked over that inventory."
    )


def test_the_answer_is_json_a_form_can_read(student_read_door: StudentReadDoor) -> None:
    """The read path answers a structured document, not a page.

    Small, and here because every other assertion in this module rests on it: the
    answer is decoded as JSON, so a route that answered HTML — or a `204` with no
    body — would fail each of them for a reason that reads as a defect in the
    scan. This one says it once, plainly, and names what came back.

    **The mutation it kills:** an HTML surface where an API contract belongs.
    E2-10's form is a React route (SPEC §13) fetching this path through the
    generated client, and §7.6's OpenAPI contract is what generates it.
    """
    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code}. Body begins "
        f"{answered.text[:300]!r}."
    )
    body: Any = decoded(answered, f"`GET {STUDENT_READ_PATH}`")
    assert isinstance(body, dict | list), (
        f"The answer decoded to {type(body).__name__} ({body!r}). E2-09 answers the form's whole "
        "question in one round trip, which is an object or a list of them — one per live "
        "enrollment — and not a bare scalar."
    )
