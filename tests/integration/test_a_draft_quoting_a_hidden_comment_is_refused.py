"""A draft that reuses the words of a comment students will not see is refused — E7-04 done-when 4.

> A draft reusing a word run from an excluded comment, from a still-flagged
> comment, and from a comment in a held stream is each refused, beside a draft
> reusing a run from a published comment in a shown stream, which is accepted.
> Marked `invariant`.

SPEC §4.1 item 3: below the threshold "raw comments in that stream are hidden from
instructors and students alike"; §5.2 hides a flagged comment from students and
an excluded one from everybody but its instructor. A draft is published to every
student under the instructor's name, so a draft carrying such a comment's words
hands it to exactly the readers it was withheld from. The model never sees a
comment (done-when 1), but an instructor who read a comment and a model that
paraphrased a summary can still put its words in a draft; the ticket's guard is
`_reused_run` against those comments, "as `refuse_a_summary_reusing_a_comment`
does for a summary".

**Planted apart, as entry 30 requires.** The comments are planted through the
product's writers, and each draft is written separately in
`tests/fixtures/response_draft.py` as a frame around a run of its comment. The
control below measures, with this suite's own ruler, that each draft shares at
least forty normalized characters with the comment it lifts and fewer than twenty
with every other comment in the week — so a refusal is about that comment and
nothing else, and an acceptance is not a guard that happened to look elsewhere.

**Each comment's state is read off the instructor's own report first**, so
"excluded", "still flagged", "kept" and "held" are what the product says they are,
not what this file intended (`docs/MISTAKES.md` entry 58).

**Which failure a red is.** The control is green on any tree. Before E7-04 the
rest are a FAILED naming the missing route or `ResponseDraftOutput`'s draft field.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import EXCLUDED, FLAGGED, KEPT, PUBLISHED
from fixtures.report_api import COMMENT_STATUS_FIELD, FULL_WEEK
from fixtures.response_draft import (
    EXCLUDED_COMMENT,
    FLAGGED_COMMENT,
    HELD_COMMENT,
    KEPT_COMMENT,
    PUBLISHED_COMMENT,
    RUN_OF,
    DraftDoor,
    a_draft_lifting,
    assert_the_planted_texts_are_what_this_file_says,
    assert_unusable,
    draft_answer,
    text_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# What the instructor's report says of each planted comment (E4-04's spellings).
# `None` is "not on the report at all", which is a held stream's comment.
STATE_ON_THE_REPORT = {
    PUBLISHED_COMMENT: PUBLISHED,
    EXCLUDED_COMMENT: EXCLUDED,
    FLAGGED_COMMENT: FLAGGED,
    KEPT_COMMENT: KEPT,
    HELD_COMMENT: None,
}

WHY_HIDDEN = {
    EXCLUDED_COMMENT: "excluded by its instructor (SPEC §5.2)",
    FLAGGED_COMMENT: "still flagged and collapsed, so hidden from students (SPEC §5.2)",
    HELD_COMMENT: "in a stream held below the n-threshold (SPEC §4, §4.1 item 3)",
}


def the_week_as_the_report_reads_it(door: DraftDoor) -> None:
    """Build the week, then require the report to say what this module says of each comment."""
    door.build_the_week()
    body = door.assert_the_streams_are(instructor_held=False, course_held=True)
    for comment, expected in STATE_ON_THE_REPORT.items():
        card = door.decisions.card(body, door.planted[comment])
        state = None if card is None else card.get(COMMENT_STATUS_FIELD)
        assert state == expected, (
            f"The instructor's report shows {comment!r} as {state!r}; this module needs {expected!r}"
            " (None: not on the report, as a held stream's comment is not)."
        )


def drafted(door: DraftDoor, lifted: str) -> Any:
    """Script a draft lifting `lifted`'s run, and ask for a draft."""
    door.provider.script(draft_answer(a_draft_lifting(RUN_OF[lifted])))
    before = len(door.provider.completions)
    answered = door.draft(course_week=FULL_WEEK)
    assert len(door.provider.completions) > before, (
        f"The draft answered {answered.status_code} without asking the model, so its answer is not "
        "a verdict on the scripted draft."
    )
    return answered


def test_the_planted_texts_are_what_this_suite_says() -> None:
    """The control. **A red here means the fixture is wrong, not the guard.**

    Every lift at least forty normalized characters of its own comment and under
    twenty of every other; every stored count findable and unique. Must be green on
    any tree, with or without E7-04.
    """
    assert_the_planted_texts_are_what_this_file_says()


@pytest.mark.parametrize(
    "hidden",
    (EXCLUDED_COMMENT, FLAGGED_COMMENT, HELD_COMMENT),
    ids=("excluded", "still-flagged", "held-stream"),
)
def test_a_draft_reusing_a_run_of_a_hidden_comment_is_refused(
    draft_door: DraftDoor, hidden: str
) -> None:
    """Each kind of hidden comment, lifted forty-odd characters into a draft: 502.

    **The mutations this kills, one per parameter:** the comparison set built from
    the shown stream's *published* comments only (all three pass); built without
    the excluded leg; without the flagged leg; without the held-stream leg — the
    one a "the report already hides it" argument deletes; or the guard absent.
    **The near misses it must survive:** the published and kept twins below, in
    the same world, which reuse runs just as long.
    """
    door = draft_door
    the_week_as_the_report_reads_it(door)
    assert_unusable(
        drafted(door, hidden),
        "draft",
        f"reuses {RUN_OF[hidden]!r} from a comment {WHY_HIDDEN[hidden]}",
    )


def test_a_draft_reusing_a_run_of_a_published_comment_in_a_shown_stream_is_accepted(
    draft_door: DraftDoor,
) -> None:
    """The accepted twin: the same lift, from a comment every student can already read.

    **The mutation this kills:** a guard comparing against every comment of the
    week — the safe-looking over-reach that refuses a draft for answering what
    students said, which is what §5.3 asks a response to do. **And** a route that
    returns something other than the model's draft on success.
    """
    door = draft_door
    the_week_as_the_report_reads_it(door)
    draft = a_draft_lifting(RUN_OF[PUBLISHED_COMMENT])
    served = text_of(drafted(door, PUBLISHED_COMMENT))
    assert served == draft, (
        f"The draft route served {served!r} for a model draft of {draft!r}, which reuses only a "
        "published comment of a shown stream — students read that comment on their own page."
    )


def test_a_draft_reusing_a_run_of_a_kept_comment_is_accepted(draft_door: DraftDoor) -> None:
    """The near miss for the flagged leg: a comment flagged once and kept is published.

    SPEC §5.2: "Keep for students" publishes the comment. **The mutation this
    kills:** a flagged leg keyed on the AI verdict (`harmful`) rather than on the
    comment's latest state, which refuses a draft quoting a comment students see.
    """
    door = draft_door
    the_week_as_the_report_reads_it(door)
    draft = a_draft_lifting(RUN_OF[KEPT_COMMENT])
    served = text_of(drafted(door, KEPT_COMMENT))
    assert served == draft, (
        f"The draft route served {served!r} for a draft reusing only a kept comment, which SPEC "
        "§5.2 publishes to students."
    )
