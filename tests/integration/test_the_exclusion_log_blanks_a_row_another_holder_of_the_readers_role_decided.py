"""The decider is a person, not a role: another holder of the reader's role gets a blank row — E9-14 fix round, P4.

E9-14 item 1: wherever a row's excerpt is withheld and the reader is not that
decision's decider, `reason` and `decided_on` are null. The mutation battery
on e88d4fc8 (row 3) replaced "the reader is the decider" with "the reader holds
the role the decision was made under", and every test stayed green: in each of
them the non-deciding reader held a different role from the stored one (an
instructor's decision read by a lead, a lead's read by a dean). This module
closes that: the decision is stored under the reader's own role, by somebody
else.

  - **A lead.** A held comment in lead A's course was excluded as
    `LEAD_FACULTY` by another person — the course's previous lead, say (SPEC
    §5.3: a course's lead can change). Lead A reads the row blank.
  - **A chair.** A held comment in the unled course was excluded as `CHAIR` by
    another person. The department's chair reads the row blank.

**The present twin, in each:** the reader's own decision, in the same section
and stream, carries its reason and date.

**Which failure a red is.** E9-14 implements the rule by decider on e88d4fc8,
so both tests are expected **green**; each kills battery row 3.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import STORED_EXCLUDED
from fixtures.lead_review import (
    AS_CHAIR,
    AS_LEAD_FACULTY,
    LOG_DECIDED_ON,
    LOG_EXCERPT,
    LOG_REASON,
    LOG_SECTION_LABEL,
    UNMAPPED_COHORT,
    LeadReviewWorld,
    Reader,
)
from fixtures.moderation import HARMFUL
from fixtures.report_api import FIRST_HELD_WEEK, TAUGHT_COHORT, strings_in
from fixtures.report_views import COURSE_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def two_held_exclusions(
    review: LeadReviewWorld, *, cohort: str, decided_as: str, reader: Reader
) -> tuple[str, str]:
    """Two held comments in `cohort`, one excluded by another person and one by `reader`.

    Both decisions are stored under `decided_as`, the reader's own role. Answers
    (the other person's reason, the reader's reason).
    """
    other_reason = f"E9-14 P4 {decided_as} decision by another holder of the role"
    own_reason = f"E9-14 P4 {decided_as} decision by the reader"
    for index, (by, reason) in enumerate(
        ((review.door.a_person(), other_reason), (reader.person_id, own_reason))
    ):
        comment = review.plant(
            course_week=FIRST_HELD_WEEK,
            stream=COURSE_STREAM,
            text=f"E9-14 P4 a held harmful comment in cohort {cohort}, {index}",
            verdict=HARMFUL,
            cohort=cohort,
        )
        review.plant_decision(
            comment, STORED_EXCLUDED, decided_by=by, decided_as=decided_as, reason=reason
        )
    return other_reason, own_reason


def read(review: LeadReviewWorld, reader: Reader, cohort: str) -> tuple[Any, list[dict[str, Any]]]:
    answered = review.log(reader)
    assert answered.status_code == 200, f"The log answered {answered.status_code}."
    code = review.code_of(cohort)
    rows = [row for row in review.log_rows(reader) if code in str(row.get(LOG_SECTION_LABEL))]
    return answered.json(), rows


CASES = {
    "a lead": (TAUGHT_COHORT, AS_LEAD_FACULTY, "lead"),
    "a chair": (UNMAPPED_COHORT, AS_CHAIR, "chair"),
}


@pytest.mark.parametrize("case", list(CASES))
def test_a_reader_gets_a_blank_row_for_a_withheld_decision_another_person_made_under_her_role(
    lead_review: LeadReviewWorld, case: str
) -> None:
    """The other holder's row: no reason, no date, its reason nowhere; the reader's own row: both.

    **The mutation it kills:** "the reader is the decider" read as "the reader
    holds the decision's stored role" (battery row 3), which hands a lead every
    previous lead's dated reasons for held comments. **The near miss it spares:**
    the reader's own decision in the same section and stream (the twin).
    """
    review = lead_review
    cohort, decided_as, who = CASES[case]
    reader = getattr(review, who)
    other_reason, own_reason = two_held_exclusions(
        review, cohort=cohort, decided_as=decided_as, reader=reader
    )

    body, rows = read(review, reader, cohort)
    own = [row for row in rows if row.get(LOG_REASON) == own_reason]
    assert (
        len(own) == 1 and own[0][LOG_DECIDED_ON] is not None
    ), f"The present twin: {case}'s own held row is {own}; the decider reads her reason and date."
    others = [row for row in rows if row is not own[0] and row.get(LOG_EXCERPT) is None]
    assert len(others) == 1, (
        f"{case.capitalize()}'s log carries {len(others)} other withheld rows of the section; one "
        f"was planted. Rows: {rows}."
    )
    assert (others[0].get(LOG_REASON), others[0].get(LOG_DECIDED_ON)) == (None, None), (
        f"Another person decided this held comment under {decided_as}, {case}'s own role, and "
        f"{case} reads {others[0]!r}. The rule is about the decider, not the role."
    )
    assert not [
        value for value in strings_in(body) if other_reason in value
    ], f"The other holder's reason is in {case}'s log body."
