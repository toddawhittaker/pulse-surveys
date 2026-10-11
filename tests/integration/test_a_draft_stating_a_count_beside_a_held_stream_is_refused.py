"""In a week with a held stream, a draft states no number of anything — residue A, fix-round G1.

E7-04's work order, residue A from the breakdown review (PR #306), began as "a draft
that states a number of comments or students ... is refused ... its twin, a shown
stream's draft stating a count, is accepted." The fix-round review then found the
phrase list missing "two of your classmates", "2 learners said", "the 7 who
responded", "Twenty students", "Both students" and "Half the class" — a phrase
list never closes — and the work order settled G1 instead: in a week with a held
stream the draft states no number of anything except one naming a course structure
("week 3", "chapter five"). Ordinals are not counts.

**Why it exists.** Decision 12 keeps a held stream's per-theme counts out of the
prompt. A summary's *prose* is not a count field, and a `summary.v3` paragraph may
well say "two students raised the dataset" — so the prose path can hand the model
the number the theme path withholds, and a draft can repeat it to every student.
SPEC §5.2: in a small week "a per-week count ... would say how many of the few who
responded" did something.

**Where each phrasing is tested.** The rule itself is one function
(`reporting.states_a_count_of_people`), and every phrasing and every twin is driven
through it in `tests/unit/test_the_held_week_count_rule_reads_every_phrasing.py`.
This module drives the route — one world per case — over one phrasing per token
class and every accepted twin, so the function is shown to be the one the route
calls and to be called only when a stream is held.

**The two worlds differ in one thing.** Both plant a course-stream summary whose
prose states a count. In the first the course stream holds one commenter and is
held; in the second it holds the configured threshold and is shown. Which is which
is read off the instructor's report (work-order decision 4), never assumed.

**What the drafts lift.** Nothing: every draft shares fewer than twenty normalized
characters with every comment in the week (asserted), so a refusal is the count
rule's and not the reuse guard's.

**Marked `invariant`**: the number of commenters in a held stream reaching every
student is §4.1 item 3's threshold crossed by arithmetic rather than by text.
"""

from typing import Any

import pytest
from fixtures.report_comments import configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.response_draft import (
    ALLOWED_CLAUSES,
    COUNTING_CLAUSES,
    HELD_COMMENT,
    ORDINARY_SUMMARY_VERSION,
    SHOWN_SUMMARY_RESPONSES,
    SHOWN_SUMMARY_TEXT,
    SHOWN_THEME_A,
    SHOWN_THEME_A_COUNT,
    SMALL_N_SUMMARY_VERSION,
    THE_GUARD_BOUND,
    UNUSABLE_ANSWER_STATUS,
    DraftDoor,
    a_draft_saying,
    assert_the_planted_texts_are_what_this_file_says,
    assert_unusable,
    draft_answer,
    longest_shared_run,
    text_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The course stream's summary, whose prose carries a count — the residue's
# "planted summary whose prose carries a count".
A_SUMMARY_STATING_A_COUNT = (
    "E7-04 course-stream summary: two students said the dataset question went unanswered."
)
A_COURSE_THEME = "E7-04 the dataset question"
A_COURSE_THEME_COUNT = 2

# One refused phrasing per token class G1 lists, driven through the route. The
# full list is driven through the function in the unit module.
THROUGH_THE_ROUTE = (
    "digit-students",
    "three-of-you",
    "two-of-your-classmates",
    "hyphenated-compound",
    "both-students",
    "half-the-class",
    "a-few-of-you",
    "a-number-of-things",
    "and-after-weeks",
)

# The shown twin: "two of you" in a week where no stream is held (the coordinator's
# brief), and two more spellings of the same.
SHOWN_TWINS = {
    "two-of-you": "Two of you asked for slower derivations",
    "digit-students": COUNTING_CLAUSES["digit-students"],
    "half-the-class": COUNTING_CLAUSES["half-the-class"],
}


def a_week(door: DraftDoor, *, course_commenters: int) -> None:
    """Course week 1 with `course_commenters` course comments and both summaries planted."""
    assert_the_planted_texts_are_what_this_file_says()
    door.plant(HELD_COMMENT, stream=COURSE_STREAM)
    for index in range(1, course_commenters):
        door.plant(
            f"E7-04 course commenter {index}: the lab notes were posted promptly enough",
            stream=COURSE_STREAM,
        )
    held = course_commenters < configured_threshold()
    door.plant_summary(
        INSTRUCTOR_STREAM,
        text=SHOWN_SUMMARY_TEXT,
        themes=((SHOWN_THEME_A, SHOWN_THEME_A_COUNT),),
        prompt_version=ORDINARY_SUMMARY_VERSION,
        response_count=SHOWN_SUMMARY_RESPONSES,
    )
    door.plant_summary(
        COURSE_STREAM,
        text=A_SUMMARY_STATING_A_COUNT,
        themes=((A_COURSE_THEME, A_COURSE_THEME_COUNT),),
        prompt_version=SMALL_N_SUMMARY_VERSION if held else ORDINARY_SUMMARY_VERSION,
        response_count=course_commenters,
    )
    body = door.assert_the_streams_are(instructor_held=False, course_held=held)
    served = door.served_summary(body, COURSE_STREAM)
    assert isinstance(served, dict) and A_SUMMARY_STATING_A_COUNT in str(served), (
        f"The report serves {served!r} as the course stream's summary, not the planted prose "
        "stating a count — so the gather would not carry it, and the residue's premise (a "
        "summary whose prose carries a count) is not this world."
    )


def a_held_week(door: DraftDoor) -> None:
    a_week(door, course_commenters=1)


def a_shown_week(door: DraftDoor) -> None:
    a_week(door, course_commenters=configured_threshold())


def drafted(door: DraftDoor, draft: str) -> Any:
    for comment in door.planted:
        assert longest_shared_run(draft, comment) < THE_GUARD_BOUND, (
            f"The draft {draft!r} shares a long run with the planted comment {comment!r}, so a "
            "refusal could be the reuse guard's rather than the count rule's."
        )
    door.provider.script(draft_answer(draft))
    before = len(door.provider.completions)
    answered = door.draft()
    assert (
        len(door.provider.completions) > before
    ), f"The draft answered {answered.status_code} without asking the model."
    return answered


@pytest.mark.parametrize("case", THROUGH_THE_ROUTE)
def test_a_draft_stating_a_count_in_a_week_with_a_held_stream_is_refused(
    draft_door: DraftDoor, case: str
) -> None:
    """The held world: a draft carrying a count token. 502.

    **The mutations this kills, one per parameter:** the rule absent; a rule that
    matches only digits, or only number words; one that misses a quantity word
    (both, half, few), a hyphenated compound, or "classmates" in place of
    "students"; one scoped to counts of people ("3 worked examples" is a number of
    anything, which G1 forbids); and one that lets a structure word license every
    later number ("Weeks 3 and 4"). **The near misses:** the accepted twins below,
    in the same held world, and the shown-week twin.
    """
    door = draft_door
    a_held_week(door)
    answered = drafted(door, a_draft_saying(COUNTING_CLAUSES[case]))
    assert_unusable(
        answered,
        "draft",
        f"carries a count token ({COUNTING_CLAUSES[case]!r}) in a week with a stream held below "
        "the threshold, whose held summary's prose carries a count",
    )
    assert answered.status_code == UNUSABLE_ANSWER_STATUS


@pytest.mark.parametrize("case", tuple(ALLOWED_CLAUSES))
def test_a_draft_naming_a_course_structure_or_no_number_in_a_held_week_is_accepted(
    draft_door: DraftDoor, case: str
) -> None:
    """The held world's twins: "week 3", "chapter five", ordinals, and no number. 200.

    **The mutations this kills, one per parameter:** a rule refusing every digit or
    number word (no exceptions); an exception list that is case-sensitive ("Week
    4"); one that does not reach a hyphenated compound ("chapter twenty-one"); one
    that treats ordinals as counts ("first", "second"); one that misses "lab" or
    "question"; and a rule refusing every draft in a held week ("no-number").
    """
    door = draft_door
    a_held_week(door)
    draft = a_draft_saying(ALLOWED_CLAUSES[case])
    served = text_of(drafted(door, draft))
    assert served == draft, f"The draft route served {served!r} for the model's {draft!r}."


@pytest.mark.parametrize("case", tuple(SHOWN_TWINS))
def test_a_draft_stating_a_count_in_a_week_with_every_stream_shown_is_accepted(
    draft_door: DraftDoor, case: str
) -> None:
    """The residue's twin: "two of you" when no stream is held. 200, the draft served.

    **The mutation this kills:** the count rule applied to every week — the
    safe-looking over-reach that forbids "two of you asked for..." in a week where
    the comments are on the page anyway.
    """
    door = draft_door
    a_shown_week(door)
    draft = a_draft_saying(SHOWN_TWINS[case])
    served = text_of(drafted(door, draft))
    assert served == draft, f"The draft route served {served!r} for the model's {draft!r}."
