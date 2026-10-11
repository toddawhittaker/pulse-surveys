"""Two decisions about one comment in one transaction resolve to the second — E6-01, criterion 4.

ADR 0145 makes `moderation_state` append-only with the latest row governing, and
`decided_at` was the only thing "latest" could be read off. Two rows written in one
transaction carry the same `now()`, so a reader ordering by it alone answers with
whichever row the database happens to return first: `../e4/deferred.md` recorded
the gap, and E6-01's work order (decision 9) closes it before the first writer —
`moderation_state.sequence`, an identity column, and `reported_status_of` orders
by it.

**Both ways round, as the criterion says.** An `EXCLUDED` then a `KEPT`, and a
`KEPT` then an `EXCLUDED`, each with identical `decided_at` values. A reader that
happened to return the first-inserted row on a tie passes one case and fails the
other; one ordering by `sequence` ascending fails both; one that ignores the tie
fails at least one.

**What this does not cover, stated rather than implied.** Two *concurrent*
writers are not a same-transaction pair: an identity column orders by insert, not
by commit, and ADR 0187 records that. No test here claims otherwise.

**The read is the comment service's**, at a week at the configured threshold, so
the status is visible at all; the count is read back first (the same premise
`test_a_visible_comments_status_is_the_latest_moderation_decision.py` takes).
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.moderation import moderation_states, require_sequence
from fixtures.report_comments import CommentWorld, decided_at_column

pytestmark = pytest.mark.integration

THE_WEEK = 7
A_COMMENT = "the reading list for week seven arrived after the seminar it was for"

# One instant, after the week closed, written on both rows: the same-transaction
# tie made explicit rather than left to `now()`.
AFTER_THE_CLOSE = timedelta(hours=3)

PAIRS = {
    "excluded-then-kept": ("stored_excluded", "stored_kept", "kept"),
    "kept-then-excluded": ("stored_kept", "stored_excluded", "excluded"),
}


@pytest.mark.parametrize("pair", list(PAIRS.values()), ids=list(PAIRS))
def test_two_decisions_written_in_one_transaction_resolve_to_the_second(
    pair: tuple[str, str, str], comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Criterion 4: one comment, two decisions, one instant, one transaction — the second governs.

    **The premise, read back before the status is.** Both rows exist, they carry
    the same `decided_at`, and the second carries the larger `sequence`. Without
    the tie the test would be `test_the_latest_moderation_decision_is_the_one_the_
    read_path_reports` again; without the order it would be asserting a
    tie-break the schema does not hold.

    **The mutations this kills:** `reported_status_of` ordering by `decided_at`
    alone (the tie answered by heap order, which one of the two cases catches);
    ordering by `sequence` ascending (both cases); ordering by the row's random
    uuid (one case in two, on average, per run — the pair is what makes a run
    likely to catch it, and the docstring says so rather than claiming more).
    """
    contract = comment_contract
    world = comment_world
    require_sequence(world.tables)
    first_attribute, second_attribute, expected_attribute = pair
    first = getattr(contract, first_attribute)
    second = getattr(contract, second_attribute)
    expected = getattr(contract, expected_attribute)

    threshold = contract.threshold()
    world.build()
    world.close_week(THE_WEEK)
    planted = world.week_of_comments(
        term_week=THE_WEEK,
        texts=[f"{A_COMMENT} ({index + 1})" for index in range(threshold)],
        stream=contract.instructor_stream,
    )
    assert world.commenters_in(term_week=THE_WEEK, stream=contract.instructor_stream) == threshold
    subject = planted[0]

    at = world.instants[THE_WEEK][1] + AFTER_THE_CLOSE
    world.moderate(subject, first, decided_at=at)
    world.moderate(subject, second, decided_at=at)

    instant = decided_at_column(world.tables)
    rows = moderation_states(world.session, world.answer_key(subject))
    assert len(rows) == 2 and rows[0][instant] == rows[1][instant], (
        f"The comment carries {len(rows)} moderation rows, decided at "
        f"{[row[instant] for row in rows]}. This test is about two rows with one instant."
    )
    by_sequence = sorted(rows, key=lambda row: row["sequence"])
    assert [row["state"] for row in by_sequence] == [first, second], (
        f"Ordered by `sequence`, the rows read {[row['state'] for row in by_sequence]}; they were "
        f"written {[first, second]}. The identity column orders rows by insert (work order "
        "decision 9), so the second written carries the larger value."
    )

    comments = contract.visible()(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(THE_WEEK),
        stream=contract.instructor_stream,
    )
    statuses = {str(comment.text): str(comment.status) for comment in comments}
    text = f"{A_COMMENT} (1)"
    assert text in statuses, (
        f"The decided comment is not in what the read returned ({sorted(statuses)}); every state "
        "keeps a comment visible to its instructor above the threshold."
    )
    assert statuses[text] == expected, (
        f"`{first}` then `{second}`, written in one transaction with one `decided_at`, read back as "
        f"{statuses[text]!r}; the second written governs, so the status is {expected!r}. E6-01 "
        "criterion 4: a same-transaction pair resolves to the second, both ways round."
    )


def test_the_sequence_column_is_an_identity_column(comment_world: CommentWorld) -> None:
    """Decision 9: `moderation_state.sequence` is an identity column, assigned by the database.

    An identity, not a value a writer supplies: a writer-chosen ordinal is one more
    thing the definer, a fixture and E6-03's decision route each have to get right,
    and two of them disagreeing is the tie this column exists to break.

    **The mutation this kills:** a plain integer column a writer fills (or leaves
    null), which orders nothing anybody did not choose.
    """
    require_sequence(comment_world.tables)
    from sqlalchemy import text

    identity = comment_world.session.execute(
        text(
            "SELECT a.attidentity FROM pg_attribute a "
            "WHERE a.attrelid = 'public.moderation_state'::regclass "
            "AND a.attname = 'sequence' AND NOT a.attisdropped"
        )
    ).scalar_one_or_none()
    assert identity in ("a", "d"), (
        f"`moderation_state.sequence` has `attidentity` {identity!r}; an identity column is 'a' "
        "(always) or 'd' (by default). E6-01's work order: 'an identity column that orders rows'."
    )
