"""How many weeks this student's section runs for, on the read answer — ticket E4-17.

E4-17's first two criteria: `OpenSurvey` carries the section's own week count,
asserted **against the seeded calendar** — the start letter and the term's
start-letter map, SPEC §2.2 — rather than against `app.services.section_codes`,
the service that computed it; and the count is the section the window belongs to
and never another's.

**Why not against `section_codes`.** The deferred entry this ticket closes
(`docs/tickets/e2/deferred.md`, "The week eyebrow cannot say how long the course
runs") writes the currency into its own done-when, and the ticket repeats it as a
known trap: an expectation read out of the service that produced the number
proves only that the service agrees with itself (`docs/MISTAKES.md` entry 19).
Nothing under `backend/app/` is imported here at all. The expectation is
`SEEDED_COHORTS`, which `tests/fixtures/survey_windows.py` transcribes from
`scripts/seed.py`'s `START_LETTER_MAP` — the institution's configuration, which
§2.2 makes the source of a section's length — keyed by the start letter this
world's own `lms_section_code` begins with.

**What the ticket settles, and the one thing it does not.** It settles that the
field is on `OpenSurvey`, that it is a plain non-optional integer, and that it is
read off the `Section` `_open_survey` already holds. It does **not** spell the
member. `LENGTH_WEEKS_FIELD` is this suite's transcription and not a ruling — it
sits in `tests/fixtures/student_read.py` beside `course_week` and `course_label`,
with the reasoning for the spelling — and the gap is reported in E4-17's
manifest. If the owner spells it some other way, that is one line there and one
in `frontend/src/components/WeekEyebrow.courseLength.test.tsx`.

**The numbers this world is chosen for.** The reader's section is cohort `D` —
fifteen weeks from term week 4 — read inside a window over term week 13. So its
length is 15, its course week is 10, its term week is 13, and the term's own
length is 18. Four distinct numbers, which is what makes each wrong answer a
different one: the term's length served in the section's place is 18, the term
week in the length's place is 13, the course week is 10, and a constant is
whatever it is. The distinctness is asserted before the answer is read rather
than assumed, because a world where two of them coincided would make this test
green against the mutation it exists to kill (`docs/MISTAKES.md` entry 3).

**What is not here** is SPEC §4.1. The ticket argues in its Context that the
length is the reader's own section's attribute and discloses nothing new, and
the denial that a section the student is not enrolled in is named at all is
already asserted, in the isolated invariant pass, by
`tests/integration/test_the_student_read_path_names_nothing_outside_the_enrollment.py`.
This ticket adds no invariant-marked test and takes nothing away from that pass:
criterion 7 is met by running it unchanged with the new field carried through it.
"""

from typing import Any

import pytest
from fixtures.student_read import (
    COURSE_WEEK_FIELD,
    ENROLLED_COHORT,
    EXPECTED_COURSE_WEEK,
    EXPECTED_TERM_WEEK,
    LENGTH_WEEKS_FIELD,
    OTHER_SECTION_ENROLLED_SINCE,
    STUDENT_READ_PATH,
    TERM_WEEK,
    UNENROLLED_COHORT,
    StudentReadDoor,
    decoded,
    objects_carrying,
)
from fixtures.survey_windows import (
    FALL_2026_TERM_WEEKS,
    SECTION_CODE_COLUMN,
    SECTION_LENGTH_COLUMN,
    SEEDED_COHORTS,
)

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The other section this world seeds, and the reader's own course week in it.
# Cohort `Q` runs twelve weeks from term week 7, so term week 13 — the week both
# windows are over — is its seventh course week; the enrolled cohort `D` runs
# fifteen from term week 4, so the same week is its tenth. Written out rather
# than computed from `SEEDED_COHORTS`, because re-deriving §2.2's course-week
# arithmetic here would be a second implementation of the thing E2-09 already
# asserts, and this file only needs the two numbers to tell two entries apart.
# The canary in the pairing test is what keeps them honest.
OTHER_SECTIONS_COURSE_WEEK = 7


def length_the_start_letter_gives(section_code: str) -> int:
    """How many weeks a section runs for, from its start letter and the term's map.

    SPEC §2.2: "the start letter encodes length + start date within the term via
    a per-term **start-letter map** (admin-configured data)". `SEEDED_COHORTS` is
    that map for Fall 2026 as the test suite holds it — transcribed from
    `scripts/seed.py` and checked against its own dates by
    `tests/unit/test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py`, so it
    is neither this file's invention nor a reading of the service under test.
    """
    letter = section_code[:1]
    assert letter in SEEDED_COHORTS, (
        f"The seeded section code {section_code!r} begins with {letter!r}, which is not a start "
        f"letter in the term's map ({sorted(SEEDED_COHORTS)}). SPEC §2.2 builds a section code as "
        "`{startLetter}{ordinal}{modality}`, so a code that starts with something else means this "
        "world seeded a section whose length no calendar explains — and the expectation below "
        "would be about nothing."
    )
    return SEEDED_COHORTS[letter][0]


@pytest.fixture
def also_enrolled_in_the_other_section(student_read_door: StudentReadDoor, enrol: Any) -> None:
    """Enrol this reader in the world's *other* section as well, live from its first day.

    The two sections this world already holds are the pair criterion 2 asks for:
    cohort `D` runs fifteen weeks and cohort `Q` runs twelve, both carry a window
    over term week 13, and the clock the door leaves behind is inside it — so with
    one more enrollment the same reader has two open surveys of two different
    lengths.

    **The world's second section rather than a freshly seeded one**, deliberately:
    `seed_a_course_this_student_is_not_in` gives its section the *enrolled*
    cohort's calendar, so a pair built from it would be two fifteen-week sections
    and every wrong lookup would answer correctly. Nothing here decides what the
    answer should be; the lengths are the ones the calendar already wrote
    (`docs/MISTAKES.md` entry 30).
    """
    world = student_read_door.world
    enrol.enrol(
        user_id=world.user_id,
        section_id=world.other_section_id,
        started_on=OTHER_SECTION_ENROLLED_SINCE,
        ended_on=None,
    )


def test_the_answer_says_how_many_weeks_this_students_own_section_runs(
    student_read_door: StudentReadDoor,
) -> None:
    """Criterion 1: `OpenSurvey` carries the section's week count, per the seeded calendar.

    The reader's section is `D1WW`; its start letter is `D`; the term's
    start-letter map gives `D` fifteen weeks. The answer has to carry 15.

    **The mutations this kills.** The member absent altogether, which is the state
    this test is first written red against. The term's own length served in the
    section's place — the near miss criterion 5 names, and 18 here, so it is a
    different number rather than a coincidence. The term week served in it, which
    is 13. The course week, which is 10. A constant, whatever it is, since none of
    the four numbers this world produces is the same as another. And a length read
    from the `week` or the `term` row rather than from the section, both of which
    this world seeds with 18.

    **The near miss it must survive**: the answer may carry more than this. Only
    the member the criterion names is asserted, and it is asserted wherever in the
    answer the implementer put it — `objects_carrying` walks, so no shape is
    pinned.

    **The guards, first.** The seeded row is required to agree with the map before
    the map is used as an expectation, so a fixture that drifted from §2.2 fails by
    name rather than making this test demand a number nothing in the world holds.
    And the four numbers are required to be distinct, because a green over a world
    where the section's length equalled the term's would mean nothing
    (`docs/MISTAKES.md` entry 3).
    """
    world = student_read_door.world
    section_code = world.enrolled_section[SECTION_CODE_COLUMN]
    expected = length_the_start_letter_gives(section_code)
    stored = world.enrolled_section[SECTION_LENGTH_COLUMN]
    assert stored == expected, (
        f"The seeded section {section_code!r} carries `{SECTION_LENGTH_COLUMN}` {stored!r}, and "
        f"the term's start-letter map gives its letter {expected} weeks. The two are one fact and "
        "this test uses the map as the independent currency the ticket requires, so a disagreement "
        "means `tests/fixtures/survey_windows.py` and `SEEDED_COHORTS` have drifted apart — the "
        "read path is not what failed here."
    )
    coincidences = {
        "the term's own length": FALL_2026_TERM_WEEKS,
        "the window's term week": EXPECTED_TERM_WEEK,
        "the section's course week": EXPECTED_COURSE_WEEK,
    }
    same = sorted(name for name, value in coincidences.items() if value == expected)
    assert not same, (
        f"This section runs {expected} weeks, which is also {same}. Every wrong answer this test "
        "exists to catch would then be the right one, and a green would say nothing. The world's "
        f"cohort is `{ENROLLED_COHORT}` read in term week {TERM_WEEK}; changing either is what "
        "would cause this."
    )

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student with one live "
        f"enrollment inside an open window. Body begins {answered.text[:300]!r}."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")

    entries = objects_carrying(body, LENGTH_WEEKS_FIELD)
    assert entries, (
        f"Nothing in the answer carries a `{LENGTH_WEEKS_FIELD}`. Body begins "
        f"{answered.text[:300]!r}.\n\n"
        "E4-17 adds it to `OpenSurvey` so the week eyebrow can say how long the course runs — "
        "`COURSE WK 04 / 12, TERM WK 07` — a total the frontend is forbidden to derive, because "
        "the letter-to-length map is the institution's and a TypeScript copy of it is "
        "`docs/MISTAKES.md` entry 19. The member is spelled exactly; where it sits in the answer "
        "is the implementer's to choose, and this walk finds it anywhere.\n\n"
        f"If the member is spelled some other way than `{LENGTH_WEEKS_FIELD}`, that is the naming "
        "gap E4-17's manifest reports rather than a defect in the read path: the spelling is one "
        "constant at the top of this file."
    )
    carried = [entry[LENGTH_WEEKS_FIELD] for entry in entries]
    assert carried == [expected], (
        f"The answer carries {carried} as `{LENGTH_WEEKS_FIELD}`; this student's one live "
        f"enrollment is in {section_code!r}, which the term's start-letter map runs for "
        f"{expected} weeks.\n\n"
        f"The term is {FALL_2026_TERM_WEEKS} weeks long, this window is over term week "
        f"{EXPECTED_TERM_WEEK} and the section's own course week is {EXPECTED_COURSE_WEEK} — so a "
        "value of any of those three is a number read off the wrong row, which is exactly what "
        "criterion 5's near miss names."
    )
    on_the_open_survey = [entry for entry in entries if COURSE_WEEK_FIELD in entry]
    assert on_the_open_survey == entries, (
        f"Some object carrying `{LENGTH_WEEKS_FIELD}` carries no `{COURSE_WEEK_FIELD}`. The count "
        "is a member of the open survey the student is being shown — the same object the two week "
        "numbers ride — and not a fact about the answer as a whole, because two open sections of "
        "different lengths would then have one number between them."
    )


def test_each_open_section_is_answered_with_its_own_week_count(
    student_read_door: StudentReadDoor, also_enrolled_in_the_other_section: None
) -> None:
    """Criterion 2: the count is the window's own section's, and never another's.

    This reader now has two open surveys: a fifteen-week section in its tenth
    course week and a twelve-week one in its seventh. Each entry has to carry its
    own length, and the pair is asserted as a pair — which is both directions at
    once, and is the only reading that a swap fails.

    **The mutations this kill**, none of which a one-section world can reach: a
    length looked up once and repeated on every entry, which answers `{10: 15, 7:
    15}`; the two paired the wrong way round, which answers `{10: 12, 7: 15}` and
    is what a join written from `section` down to the window rather than up from
    it produces; and a length taken from whichever section the query returned
    first, which is one of those two depending on the order.

    **The near miss it must survive** is the correct answer with the entries in
    either order. They are matched by the course week each one carries — E2-09's
    own settled member, asserted separately from this ticket — rather than by
    position, because no ticket settles an order for them.

    **The canary, first.** The two course weeks are required to be exactly 10 and
    7 before either length is looked at. If the read path's course week is wrong,
    this test would otherwise fail on a pairing it could not make and read as a
    defect in E4-17's field; that is E2-09's subject and the message says so.
    """
    world = student_read_door.world
    mine = length_the_start_letter_gives(world.enrolled_section[SECTION_CODE_COLUMN])
    theirs = length_the_start_letter_gives(world.other_section[SECTION_CODE_COLUMN])
    assert mine != theirs, (
        f"Both of this reader's sections run {mine} weeks, so this test cannot tell a per-section "
        f"count from one lookup repeated. The world seeds cohort `{ENROLLED_COHORT}` and cohort "
        f"`{UNENROLLED_COHORT}`, whose lengths differ in `SEEDED_COHORTS`; a change there is what "
        "would cause this."
    )

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student with two live "
        f"enrollments, both inside an open window. Body begins {answered.text[:300]!r}."
    )
    entries = objects_carrying(decoded(answered, f"`GET {STUDENT_READ_PATH}`"), LENGTH_WEEKS_FIELD)
    assert len(entries) == 2, (
        f"{len(entries)} objects carry `{LENGTH_WEEKS_FIELD}` and this reader has two live "
        f"enrollments with open windows. Body begins {answered.text[:400]!r}. Nought means the "
        "member is not on the wire at all, which is the first test's subject; one means the second "
        "enrollment is missing from the answer entirely, which is E2-09's `_live_enrollments` and "
        "not this."
    )
    # A set rather than a sorted list, so an entry carrying no course week at all
    # arrives here as a clean mismatch rather than as a `TypeError` raised while
    # ordering `None` against an integer — a canary that fails by exception says
    # less than one that fails by assertion (`docs/MISTAKES.md` entry 44's spirit).
    course_weeks = {entry.get(COURSE_WEEK_FIELD) for entry in entries}
    assert course_weeks == {EXPECTED_COURSE_WEEK, OTHER_SECTIONS_COURSE_WEEK}, (
        f"The two entries report course weeks {course_weeks}; in term week {TERM_WEEK} a cohort "
        f"`{ENROLLED_COHORT}` section is in its {EXPECTED_COURSE_WEEK}th course week and a cohort "
        f"`{UNENROLLED_COHORT}` one in its {OTHER_SECTIONS_COURSE_WEEK}th (SPEC §2.2). That is "
        "E2-09's assertion, not this ticket's — it is checked here only because the two entries "
        "are told apart by it below, and a wrong course week would make this test fail for a "
        "reason that has nothing to do with the week count."
    )

    by_course_week = {entry[COURSE_WEEK_FIELD]: entry[LENGTH_WEEKS_FIELD] for entry in entries}
    assert by_course_week == {EXPECTED_COURSE_WEEK: mine, OTHER_SECTIONS_COURSE_WEEK: theirs}, (
        f"The answer pairs course week with week count as {by_course_week}; this reader's sections "
        f"are a {mine}-week one in course week {EXPECTED_COURSE_WEEK} and a {theirs}-week one in "
        f"course week {OTHER_SECTIONS_COURSE_WEEK}.\n\n"
        "Both entries carrying one number is a length looked up once and repeated. The two "
        "swapped is a count paired with whichever section the query reached first rather than with "
        "the one the window belongs to — invisible in a world with a single enrollment, which is "
        "why this test seeds a second."
    )
