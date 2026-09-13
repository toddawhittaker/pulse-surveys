"""No section's report payload carries another section's comments — the boundary review's first HIGH.

SPEC §4.1 item 6: "no view may ever widen a student's visibility relative to these
rules", and §4's own first line — identity is never displayed, and what an
instructor reads is their own section's students. Every other test of this epic's
read path asks whether a section's report is *right*; this one asks whether it is
*only* that section's, and those are different questions with different failure
modes.

**The reader this is written about is entitled to both sections**, which is what
makes it a payload-boundary test rather than an authorization one. E4-07's refusal
pair already covers a section the session does not teach (404, indistinguishable
from a section that does not exist). The instructor here teaches two sections, so
no refusal is involved anywhere: both reads are 200, and the question is whether
the *contents* stay apart. An instructor who reads her own two sections and finds
one section's students quoted under the other has been handed words about people
she is entitled to read — under a heading that says they came from somewhere else,
which is what makes it a confidentiality defect rather than a labelling one. In a
small section it is also an identification channel: a comment attributed to the
wrong week and section is a comment attributed to the wrong candidate set.

**Both directions, deliberately.** A predicate dropped from one clause of a query
leaks in one direction only — the section whose read happens to be the wider one —
so a single-direction test is satisfied by exactly half the defect. Each section's
report is read and searched for the other's text.

**Searched over the raw response body rather than over the comment lists.** The
comment members are where the words are *supposed* to be, and a leak that arrived
in a summary, a distribution label, a trend point or a member added by a later
ticket would pass a check that only walked `streams.*.comments`. The body is the
whole of what crossed the wire, and that is what §4 governs — the same reading
`tests/e2e/instructor-report.spec.ts` takes of a small-N week.

**The canaries come first, and there are three.** An absence assertion is
satisfied by an empty payload, by a refused read, and by a world that planted
nothing (`docs/MISTAKES.md` entries 3 and 30). So before either absence is
asserted: both reads answer 200, each section's report carries *its own*
distinctive sentence, and neither week declares itself suppressed. Only then is
the other section's text required to be missing.

**Marked `invariant`**, which puts this module in CI's isolated §4.1 pass where a
skip or an empty collection is a failure. It is a §4.1 item 6 assertion in the
form the pass exists for: a confidentiality property proven by refusal of content
rather than by refusal of a request.

**Which failure a red is.** Every lookup goes through `report_api_contract`, whose
readers are `pytest.fail` calls naming the deliverable, and both reads are made
over HTTP against the built application — so a red is an assertion about a status,
a member or a body, never an error in setup (`docs/MISTAKES.md` entry 44).
"""

import json
from typing import Any

import pytest
from fixtures.report_api import (
    COMMENT_TEXT_FIELD,
    FULL_WEEK,
    ReportDoor,
    plant_a_second_taught_section,
)
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The second section's comments. One per respondent, and enough respondents that
# the week sits at or above SPEC §4's threshold — a suppressed week hands back no
# comments at all, and every absence below would then hold for the wrong reason.
#
# Five, because that is `RESPONDENTS` in the canonical world and the size its own
# above-threshold week is planted at; the premise assertion in each test reads the
# `small_n.suppressed` flag rather than trusting the number.
#
# The sentences are distinctive, over SPEC §3.3's twenty-five character floor, and
# share no phrase with `FULL_WEEK_COMMENTS` — a shared clause would make a
# substring search answer yes for the wrong reason, which is the whole failure mode
# this module is built to detect.
SECOND_SECTION_COMMENTS = [
    "E4-15 leak probe: the greenhouse rotation clashed with the statistics tutorial every Thursday",
    "E4-15 leak probe: the marking rubric arrived after the essay had already been handed in",
    "E4-15 leak probe: the field notebook template was the single most useful thing this term",
    "E4-15 leak probe: two of the demonstrators gave opposite answers about the same method",
    "E4-15 leak probe: the reading room closed at five which is before most of us finish",
]

# How much of a sentence is searched for. Long enough that no ordinary prose could
# contain it by chance, short enough that a payload which truncated or re-wrapped a
# comment would still be caught carrying it.
A_RECOGNISABLE_LENGTH = 48


def _fragments(texts: list[str]) -> list[str]:
    """The leading fragment of each sentence, as the body is searched for it."""
    return [text[:A_RECOGNISABLE_LENGTH] for text in texts]


def _first_words_of_the_taught_sections_comments(door: ReportDoor, contract: Any) -> list[str]:
    """The comment texts the canonical world planted in the taught section's full week.

    Read out of that section's own payload rather than transcribed from the fixture,
    and this is the one place in this module where that is the right way round: the
    subject here is whether *these very strings* — whatever they are — turn up in
    another section's body, so the strings have to be the ones the product actually
    served. A copy transcribed here would go stale the day the fixture's sentences
    change and the module would quietly search for words nobody serves
    (`docs/MISTAKES.md` entry 19 read in the other direction: an expectation must
    not be a copy of the implementation, and an *input* must not be a copy of the
    fixture).
    """
    body, answered = door.payload(course_week=FULL_WEEK)
    found: list[str] = []
    for stream in contract.payload_stream_key:
        comments = contract.stream_member(body, stream, contract.comments_field, answered=answered)
        found.extend(
            str(comment[COMMENT_TEXT_FIELD])
            for comment in comments
            if isinstance(comment, dict) and COMMENT_TEXT_FIELD in comment
        )
    assert found, (
        "The taught section's full week carries no comments at all, so this module has nothing to "
        f"look for in the other section's body. Course week {FULL_WEEK} is planted at the "
        "n-threshold precisely so its raw comments are shown."
    )
    return found


def _assert_the_week_shows_its_comments(
    body: Any, answered: Any, contract: Any, *, where: str
) -> None:
    """One read's canary: the week is not suppressed and its own words are in it."""
    suppressed = contract.member(
        body, contract.small_n_member, contract.suppressed_field, answered=answered
    )
    assert suppressed is False, (
        f"{where} declares itself suppressed, so it hands back no comments at all and every "
        "absence this module asserts would hold for a reason that has nothing to do with the "
        "section boundary (`docs/MISTAKES.md` entry 30). The week is planted at or above the "
        "configured threshold."
    )


def test_the_taught_sections_report_carries_no_word_of_the_other_section_she_teaches(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Direction one: the canonical section's report, searched for the second section's comments.

    The instructor teaches both. Both weeks are above the threshold and both reports
    are 200. Nothing in the first section's body may be a sentence a student of the
    second one wrote.

    **The mutation this kills:** the `section_id` predicate dropped or weakened in
    the comment read — in the `report_comment` view's own `WHERE`, or in
    `_comments_with_their_status`'s filter, or in the join between them. A read
    filtered on the week and the stream and not on the section answers every
    section's comments for that week, which reads on the page as a busy week rather
    than as a defect.

    **The near miss it must survive:** a predicate that filters on the section but
    joins the *week* loosely, so the leak arrives only for weeks two sections share.
    This world is built for exactly that case — both sections hold a closed week in
    term week 7 — so a section-correct, week-loose read still crosses here.

    **What it does not reach**, said plainly (`docs/MISTAKES.md` entry 14): a leak
    that arrives only across a *term* boundary, or only between sections with no
    week in common. Both sections here sit in one term and share a term week, which
    is the case the fixture world can build.
    """
    contract = report_api_contract
    second = plant_a_second_taught_section(
        report_door, comments=SECOND_SECTION_COMMENTS, stream=INSTRUCTOR_STREAM
    )

    # Canary one: the second section's own report answers, and carries its own
    # words. Without this, a grant that never landed and a section that leaked
    # nothing are the same green.
    second_body, second_answered = _read(report_door, second.course_week, second.section_id)
    _assert_the_week_shows_its_comments(
        second_body, second_answered, contract, where="The second section's own week"
    )
    assert any(
        fragment in second_answered.text for fragment in _fragments(SECOND_SECTION_COMMENTS)
    ), (
        "The second section's own report carries none of the sentences planted into it. Either the "
        "teaching grant written for it never landed, or its week was not planted — and either way "
        "the absence asserted below would be an absence from a report of nothing. Body begins "
        f"{second_answered.text[:400]!r}."
    )

    # Canary two: the taught section's own week shows its own comments.
    body, answered = report_door.payload(course_week=FULL_WEEK)
    _assert_the_week_shows_its_comments(
        body, answered, contract, where=f"The taught section's course week {FULL_WEEK}"
    )
    own = _first_words_of_the_taught_sections_comments(report_door, contract)
    assert any(text[:A_RECOGNISABLE_LENGTH] in answered.text for text in own), (
        "The taught section's report does not carry its own comments, so it is not a report this "
        "module can ask a question of."
    )

    # And the assertion.
    for fragment in _fragments(SECOND_SECTION_COMMENTS):
        assert fragment not in answered.text, (
            f"The report for the taught section's course week {FULL_WEEK} carries "
            f"{fragment!r}, which a student of a different section wrote.\n\n"
            "SPEC §4.1 item 6: no view may widen a student's visibility. The instructor is "
            "entitled to both sections and to neither section's students under the other's "
            "heading — a comment served under the wrong section is a comment served against the "
            "wrong candidate set, which in a small week is an identification channel rather than a "
            "labelling slip. The predicate to look at is the section filter in the comment read: "
            "the view's own `WHERE`, the service's filter, or the join between them.\n\n"
            f"Body begins {answered.text[:400]!r}."
        )


def test_the_second_sections_report_carries_no_word_of_the_first(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Direction two: the second section's report, searched for the canonical section's comments.

    The pair of the test above, and not a duplicate of it. A predicate dropped from
    one clause leaks one way: whichever read ends up the wider one carries the
    other's rows, and the narrower one is unchanged. A suite that drove only the
    first direction is green against exactly half of the defect, and which half is
    decided by which query the implementer edited.

    **The mutation this kills:** the same one, seen from the other side — and, on
    its own, a section filter applied in the service but not in the view, which
    answers correctly wherever the service happens to be the narrower of the two.

    **The near miss it must survive:** a report that carries no comments at all in
    this direction, which would satisfy the absence trivially. The canaries assert
    this week is unsuppressed and carries its own five sentences first.
    """
    contract = report_api_contract
    second = plant_a_second_taught_section(
        report_door, comments=SECOND_SECTION_COMMENTS, stream=INSTRUCTOR_STREAM
    )

    # The strings to look for, taken from what the taught section actually serves.
    own_of_the_first = _first_words_of_the_taught_sections_comments(report_door, contract)

    second_body, second_answered = _read(report_door, second.course_week, second.section_id)
    _assert_the_week_shows_its_comments(
        second_body, second_answered, contract, where="The second section's own week"
    )
    assert any(
        fragment in second_answered.text for fragment in _fragments(SECOND_SECTION_COMMENTS)
    ), (
        "The second section's report carries none of its own planted sentences, so the absence "
        "asserted below would be an absence from a report of nothing. Body begins "
        f"{second_answered.text[:400]!r}."
    )

    for fragment in _fragments(own_of_the_first):
        assert fragment not in second_answered.text, (
            f"The second section's report for course week {second.course_week} carries "
            f"{fragment!r}, which a student of the *other* section she teaches wrote.\n\n"
            "This is the same defect as its sibling test read from the other side, and it is a "
            "separate assertion because a predicate dropped from one clause of one query leaks in "
            "one direction only.\n\n"
            f"Body begins {second_answered.text[:400]!r}."
        )


def test_the_two_sections_answer_two_different_weeks_on_the_course_axis(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The control under both tests above: the two reads are two sections, not one twice.

    Both absences are statements about two distinct sections. If the second section
    were never created — if `world.section` handed back the taught section's row for
    a cohort it already held, or if the grant were written against the section the
    launch granted — then both reads would be the same report, both canaries would
    pass, and both absences would hold for the emptiest possible reason
    (`docs/MISTAKES.md` entry 30).

    So this asserts the two things that make them two: the section keys differ, and
    the same term week answers a different course-week number on each — course week
    1 of the taught cohort and course week 7 of this one, which is §2.2's two axes
    doing the discriminating.

    **The mutation this kills:** a fixture that plants the "second" section into the
    cohort already built, which is the shape `world.section`'s cache produces if the
    cohort constants ever collide. A red here means this module is broken, not the
    read path.
    """
    contract = report_api_contract
    second = plant_a_second_taught_section(
        report_door, comments=SECOND_SECTION_COMMENTS, stream=INSTRUCTOR_STREAM
    )

    assert str(second.section_id) != str(report_door.rows.taught_section_id), (
        "The second taught section is the section the launch already granted, so both reads in "
        "this module are of one report and neither absence means anything."
    )

    body, answered = _read(report_door, second.course_week, second.section_id)
    course_week = contract.member(
        body, contract.week_member, contract.course_week_field, answered=answered
    )
    term_week = contract.member(
        body, contract.week_member, contract.term_week_field, answered=answered
    )
    assert (course_week, term_week) == (second.course_week, second.term_week), (
        f"The second section's report answers course week {course_week} of term week {term_week}; "
        f"the fixture planted its only week at course week {second.course_week} of term week "
        f"{second.term_week}. The two sections share that term week and number it differently "
        "(SPEC §2.2's two axes), which is what makes the pair of reads distinguishable at all."
    )


def _read(door: ReportDoor, course_week: int, section_id: Any) -> tuple[Any, Any]:
    """One report read for a named section, with its status guarded.

    Not `ReportDoor.payload`, which defaults to the taught section and would quietly
    read the wrong one of the two sections this module is about if a caller forgot
    the argument.
    """
    answered = door.report(course_week=course_week, section_id=section_id)
    assert answered.status_code == 200, (
        f"The report for course week {course_week} of section {section_id} answered "
        f"{answered.status_code} for an instructor who teaches it. A 404 here is the teaching "
        "grant this module's fixture wrote not having landed, which makes every absence below an "
        f"absence from a refusal. Body begins {answered.text[:400]!r}."
    )
    return json.loads(answered.text), answered
