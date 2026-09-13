"""What status a visible comment carries — ticket E4-04, the data half of §5.2.

The ticket's scope puts it plainly: "Flag concealment: a comment whose moderation
state is not the published state is absent below threshold … and above threshold
appears per §5.2's chip rules (rendering is E4-10's; the *data* discipline is
here)." Concealment below the threshold is
`test_a_small_week_names_nothing_an_instructor_may_read.py`; this module is the
other side of that boundary — what the read path says about a comment when the
week is large enough to say anything.

Three rules, and two of them are ADR 0145's rather than SPEC's:

  - **the initial state is the absence of a row.** "A comment with no row is
    published", which is what makes E4's "exactly one value ever written during
    E4" a count of zero writes and leaves every moderation writer to E6. A read
    path that inner-joined `moderation_state` would drop every comment nobody has
    decided about, which on today's database is all of them.
  - **the vocabulary is §5.2's four**, each reported as itself. `excluded` in
    particular is a comment the instructor still reads — §5.2: "Excluded comments
    keep their text visible to the instructor, muted, above the exclusion notice"
    — so a read path that filtered excluded comments out would hide the record of
    a decision the instructor themselves made, and §5.2's whole anti-cherry-picking
    argument rests on that decision leaving a trail.
  - **the latest row governs.** The record is append-only precisely because §5.2's
    lifecycle has an undo in both directions, so a comment reaches
    `flagged-collapsed` and then `kept` — and a reader that took any row rather
    than the newest one shows a collapsed chip on a comment an instructor
    deliberately published.

**Every week here is at or above the configured threshold**, and the count is read
back before any status is asserted: below it every comment is absent whatever its
state, and this module would then be asserting things about an empty tuple.

**The instant column on `moderation_state` is discovered, not named.** No record
in this repository spells it — ADR 0145 says "the comment, the state, and when it
was decided" and `test_report_schema.py` pins only the first two — so
`decided_at_column` in `tests/fixtures/report_comments.py` finds the one
date-or-time column and fails naming the ambiguity if there is not exactly one.
That is a gap in E4-02's record rather than a choice made here.
"""

from typing import Any

import pytest
from fixtures.report_comments import CommentWorld, decided_at_column

pytestmark = pytest.mark.integration

THE_WEEK = 7

A_DECIDED_COMMENT = "the second assignment brief contradicted what was said in the seminar"
AN_UNDECIDED_COMMENT = "nobody has ever looked at this comment and it is published all the same"


def a_big_week(world: CommentWorld, contract: Any, *, extra: int = 0) -> list[Any]:
    """One week at the configured threshold, carrying `threshold + extra` comments.

    Read back before it is used: below the threshold the read returns nothing at
    all, and every assertion in this module would then be about an empty tuple
    for a reason that has nothing to do with moderation.
    """
    threshold = contract.threshold()
    size = threshold + extra
    world.build()
    world.close_week(THE_WEEK)
    planted = world.week_of_comments(
        term_week=THE_WEEK,
        texts=[f"{A_DECIDED_COMMENT} ({index + 1})" for index in range(size)],
        stream=contract.instructor_stream,
    )
    count = world.responses_in(term_week=THE_WEEK)
    assert count == size and count >= threshold, (
        f"The week holds {count} responses; this test planted {size} and the configured threshold "
        f"is {threshold}. A week below the threshold returns nothing, so every status asserted "
        "below would be a statement about an empty tuple."
    )
    return planted


def read_the_week(world: CommentWorld, contract: Any) -> Any:
    """The week's comments as the read path answers them."""
    return contract.visible()(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(THE_WEEK),
        stream=contract.instructor_stream,
    )


def status_by_text(comments: Any) -> dict[str, str]:
    """What status the read path gave each comment, keyed by its text."""
    return {str(comment.text): str(comment.status) for comment in comments}


def test_a_comment_nobody_has_decided_about_is_published(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """ADR 0145's initial state, asserted through the read rather than through the table.

    "A comment with no `moderation_state` row is published." E4 writes no
    moderation row at all — every writer is E6's — so on today's database *every*
    comment is in this state, and a read path that got this wrong would return an
    empty report for every instructor in the product.

    **The likely defect is an inner join**, not a wrong constant: the obvious query
    joins `moderation_state` to find the state, and an inner join silently drops
    the comments nobody has decided about. ADR 0145 names it in its own
    consequences: "every read of this table is a `LEFT JOIN` with a default".

    **The mutation it kills:** `JOIN moderation_state` where `LEFT JOIN … COALESCE`
    was meant, which empties the report; and a default of anything other than
    published, which would put a chip on every comment in the institution.
    """
    contract = comment_contract
    world = comment_world
    planted = a_big_week(world, contract)
    assert planted, "The week planted no comments, so there is no status to read."

    statuses = status_by_text(read_the_week(world, contract))
    assert len(statuses) == len(planted), (
        f"The week returned {len(statuses)} comments and {len(planted)} were written, none of "
        "which carries a `moderation_state` row. ADR 0145 makes the absence of a row the initial "
        "state, so a read that inner-joins that table returns nothing — which is what an empty "
        "answer here means."
    )
    wrong = {text: status for text, status in statuses.items() if status != contract.published}
    assert not wrong, (
        f"Comments nobody has decided about came back as {wrong}, and ADR 0145 settles the initial "
        f"state as {contract.published!r}: 'a comment with no row is published'. E4 writes no "
        "moderation row anywhere, so this is the state of every comment in the product today, and "
        "§5.2 puts a chip on a comment only once a classifier or an instructor has said something "
        "about it."
    )


@pytest.mark.parametrize(
    "stored",
    ("stored_published", "stored_flagged", "stored_excluded", "stored_kept"),
)
def test_each_moderation_state_reaches_the_read_path_as_its_own_status(
    comment_world: CommentWorld, comment_contract: Any, stored: str
) -> None:
    """§5.2's four states, one case each, above the threshold where they are visible.

    **A case per state rather than one test over the set**, because a read path
    that mapped three of the four passes any test that plants one of the three,
    and the failure output should name the state that came back wrong.

    **`excluded` is the case worth reading twice.** §5.2: "Excluded comments keep
    their text visible to the instructor, muted, above the exclusion notice." A
    read path that filtered them out looks careful and removes the trail §5.2's
    anti-cherry-picking mechanism is built on — the instructor stops seeing the
    thing they excluded, and nothing on their own report records that they did.

    **The pair is inside the test**: the comments beside the decided one are
    required to come back published, so a case that passes because the read gave
    every comment the same status fails here instead.

    **The mutation it kills:** any one of the four dropped from the mapping, and
    `excluded` filtered out of the result rather than reported.
    """
    contract = comment_contract
    world = comment_world
    planted = a_big_week(world, contract, extra=1)
    subject = planted[0]
    state = getattr(contract, stored)
    world.moderate(subject, state)

    statuses = status_by_text(read_the_week(world, contract))
    text = f"{A_DECIDED_COMMENT} (1)"
    expected = contract.status_of_stored[state]

    assert text in statuses, (
        f"The comment carrying `{state}` is not in what the read returned ({sorted(statuses)}).\n\n"
        "Every state in §5.2's lifecycle keeps the comment visible to the instructor above the "
        "threshold: a flagged one appears collapsed with its chip, a kept one is published outright"
        ", and an excluded one 'keeps its text visible to the instructor, muted, above the "
        "exclusion notice'. A read path that drops a state rather than reporting it removes the "
        "record of a decision from the report of the person who made it."
    )
    assert statuses[text] == expected, (
        f"A comment whose latest `moderation_state` row is `{state}` came back as "
        f"{statuses[text]!r} and E4-04's work order settles {expected!r}. The whole vocabulary is "
        f"{list(contract.statuses)}, which is §5.2's lifecycle plus the initial state, and E4-10 "
        "renders each of them differently."
    )

    others = {
        other: status
        for other, status in statuses.items()
        if other != text and status != contract.published
    }
    assert not others, (
        f"The comments beside the decided one came back as {others}, and none of them carries a "
        f"`moderation_state` row. A read that gave every comment {statuses[text]!r} would satisfy "
        "the assertion above while reporting one decision as the state of a whole week."
    )


def test_the_latest_moderation_decision_is_the_one_the_read_path_reports(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The record is append-only, so "the state" is an ordering question.

    §5.2's lifecycle moves a comment from `flagged-collapsed` to `kept` when an
    instructor reviews it and chooses "Keep for students", and has an undo in both
    directions; §8 requires both directions logged. ADR 0145 therefore makes the
    record append-only with the latest row governing, and names the consequence:
    "a reader of a comment's moderation state has to write a window function, or
    its equivalent … That is E4-04's and E6's to write once."

    **The failure this catches is the ordinary one.** A reader that takes any row —
    `SELECT state … LIMIT 1` with no `ORDER BY`, or one ordered ascending — reports
    the *first* decision and never moves. Since a flag is what puts a row on the
    table in the first place, the first decision is almost always
    `flagged-collapsed`, so the defect shows up as a collapsed chip on a comment
    the instructor deliberately published, forever.

    **The pair is the first row read alone**, asserted before the second is
    written: without it, "the read says kept" is satisfied by a reader that
    ignores the table and answers the default, which happens not to be `kept` —
    so the flagged reading is what proves the reader can see the table at all.

    **The mutation it kills:** `ORDER BY` omitted or written ascending on the
    moderation lookup, which is invisible to every test that writes one row.
    """
    contract = comment_contract
    world = comment_world
    planted = a_big_week(world, contract)
    subject = planted[0]
    text = f"{A_DECIDED_COMMENT} (1)"

    decided_at = decided_at_column(world.tables)
    first_at = world.instants[THE_WEEK][0]
    world.moderate(subject, contract.stored_flagged, decided_at=first_at)

    after_the_flag = status_by_text(read_the_week(world, contract))
    assert after_the_flag.get(text) == contract.flagged, (
        f"With one `{contract.stored_flagged}` row on the table the read reports "
        f"{after_the_flag.get(text)!r}, not {contract.flagged!r}. Until the reader can see a single "
        "decision, the ordering asserted below says nothing — it would be satisfied by a reader "
        f"that ignored `{contract.moderation_table}` entirely, whose answer happens not to be "
        "`kept`."
    )

    world.moderate(subject, contract.stored_kept, decided_at=first_at + contract.a_later_decision)

    after_the_review = status_by_text(read_the_week(world, contract))
    assert after_the_review.get(text) == contract.kept, (
        f"After a later `{contract.stored_kept}` row was appended, the read still reports "
        f"{after_the_review.get(text)!r}.\n\n"
        f"The two rows differ only in their `{decided_at}`, and ADR 0145 makes the latest one "
        "govern: '`moderation_state` holds one row per decision … and the latest row governs'. "
        "§5.2 moves a comment to `kept` when an instructor chooses 'Keep for students', which "
        "publishes it — so a reader that takes the first row shows a collapsed chip on a comment "
        "its own instructor deliberately published, and never stops."
    )
