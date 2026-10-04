"""The one course-label composer and the one course-week rule in `section_codes`.

Every surface that names a course calls `course_label`, and every read that turns
a stored term week back into a course week calls `course_week_of` (SPEC §2.2).
The expected strings and weeks below are written out by hand rather than built
from the functions under test (`docs/MISTAKES.md` entry 19).
"""

from datetime import date

import pytest

from app.services.section_codes import course_label, course_week_of

TERM_START = date(2026, 8, 24)


def test_a_section_is_labelled_with_its_code_and_its_term() -> None:
    label = course_label(
        prefix_code="MATH",
        lms_number="140",
        lms_title="College Algebra",
        section_code="E1FF",
        term_name="Fall 2026",
    )
    assert label == "MATH 140 E1FF — College Algebra, Fall 2026"


def test_a_course_is_labelled_without_a_section_code_or_a_term() -> None:
    label = course_label(prefix_code="BIOL", lms_number="215", lms_title="Cell Biology")
    assert label == "BIOL 215 — Cell Biology"


@pytest.mark.parametrize(
    ("section_code", "term_name"),
    [("E1FF", None), (None, "Fall 2026")],
    ids=["code-without-term", "term-without-code"],
)
def test_a_label_with_only_one_of_code_and_term_is_refused(
    section_code: str | None, term_name: str | None
) -> None:
    with pytest.raises(ValueError):
        course_label(
            prefix_code="MATH",
            lms_number="140",
            lms_title="College Algebra",
            section_code=section_code,
            term_name=term_name,
        )


def test_a_section_starting_with_its_term_counts_its_weeks_as_the_terms() -> None:
    assert course_week_of(1, section_start=TERM_START, term_start=TERM_START) == 1
    assert course_week_of(5, section_start=TERM_START, term_start=TERM_START) == 5


def test_a_section_starting_in_the_terms_fourth_week_is_in_its_tenth_in_the_thirteenth() -> None:
    fourth_week = date(2026, 9, 14)
    assert course_week_of(4, section_start=fourth_week, term_start=TERM_START) == 1
    assert course_week_of(13, section_start=fourth_week, term_start=TERM_START) == 10
