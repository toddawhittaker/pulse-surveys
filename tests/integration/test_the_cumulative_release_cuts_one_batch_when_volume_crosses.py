"""The crossing, the batch, and what may and may not be in it — ticket E4-04, criterion 3.

SPEC §4, the sentence the whole of this module is about:

> Comments from under-threshold weeks are not discarded — they feed the summary,
> and they surface as raw text once the section's cumulative comment volume for
> the term crosses the threshold, **batched so that timing cannot identify an
> author**.

E4's breakdown decision 7 settles that the crossing is *stored* rather than
re-derived at read time — "a release re-derived on each read changes as data
changes, so a comment can appear and disappear, and the moment it first appears
is itself a timing signal" (ADR 0146) — and E4-04's work order settles the writer
as `cut_due_release_batches(session)`, run by a weekly beat task.

Five properties, each with its own test and each paired:

  - **the crossing is at the threshold** — a term volume one below it cuts
    nothing, and the threshold itself cuts;
  - **the batch is the whole held set, atomically** — the criterion's own words,
    "every under-threshold comment surfaces in one batch or none do";
  - **a week that is still open is never released from**, because its response
    count is not final;
  - **a week at or above the threshold is never released from**, because its
    comments are already the instructor's to read under their own week;
  - **running it twice releases nothing twice**, asserted by row identity.

**Every planted week's response count and the section's whole term volume are
read back out of the database** before any assertion rests on them, which is
E4-04's first known trap answered: a fixture bug here breaks this diff silently.

**The batches these tests read were cut by the cutter.** Nothing in
`tests/fixtures/report_comments.py` writes a `release_batch` row, because a
fixture that planted one would be supplying the value under test
(`docs/MISTAKES.md` entry 30) — and the idempotence case would then be
`docs/MISTAKES.md` entry 31, "running it twice is safe" tested against a database
the loader itself had filled. The second run here starts from the first run's own
rows.

**Which failure a red is, before E4-04 lands.** `comment_contract.cut()` is a
`pytest.fail` naming `app.services.report_comments.cut_due_release_batches` — a
FAILED assertion, not an error in setup (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.report_comments import CommentWorld, ReleaseRows

pytestmark = pytest.mark.integration

# The term weeks this module uses, all inside cohort `F`'s run (term weeks 7 to
# 12). Four are available for held comments; the last two are reserved so that a
# week at the threshold and a week that is still open are never one of them.
HELD_WEEKS = (7, 8, 9, 10)
BIG_WEEK = 11
OPEN_WEEK = 12

# The most responses a held week may hold. Two rather than one, so that a cutter
# releasing a *week* rather than a *set* is visibly wrong, and so that no held
# week's comments could be mistaken for a week at SPEC §4's default threshold of
# five. Asserted against the configured threshold before it is relied on.
SMALL_WEEK_SIZE = 2

A_HELD_COMMENT = "the pace of the reading was fine but the assessment came out of nowhere"
A_BIG_WEEK_COMMENT = "the studio sessions were the best part and there should be more of them"
AN_OPEN_WEEKS_COMMENT = "this week has not finished yet so nothing about it is final"


def plant_held_comments(world: CommentWorld, contract: Any, count: int) -> list[Any]:
    """`count` comments, spread over closed weeks that are each below the threshold.

    Weeks of at most `SMALL_WEEK_SIZE` responses, filled in order, so the number
    of comments is exactly the caller's whatever the configured threshold is and
    every week they sit in is genuinely under-threshold. Both facts are read back
    out of the database rather than assumed: E4-04's first known trap is a fixture
    that plants a different world from the one the test believes, and it breaks
    this diff without a red anywhere.

    Answers back the `answer` rows, so a test can name the comment it planted when
    it asserts what happened to it. Each text is distinct and names its week.
    """
    threshold = contract.threshold()
    assert threshold > SMALL_WEEK_SIZE, (
        f"This module plants weeks of {SMALL_WEEK_SIZE} responses and the configured threshold is "
        f"{threshold}, so those weeks are not under-threshold and nothing in them was ever held. "
        "`SMALL_WEEK_SIZE` at the top of this file is the one line that changes."
    )
    weeks_needed = -(-count // SMALL_WEEK_SIZE)
    assert weeks_needed <= len(HELD_WEEKS), (
        f"{count} comments at {SMALL_WEEK_SIZE} per week needs {weeks_needed} weeks and this "
        f"module reserves {len(HELD_WEEKS)} ({list(HELD_WEEKS)}). Cohort `F` runs term weeks 7 to "
        "12 and the last two are the big week and the open one."
    )

    planted: list[Any] = []
    remaining = count
    used: list[int] = []
    for week in HELD_WEEKS:
        if remaining <= 0:
            break
        size = min(SMALL_WEEK_SIZE, remaining)
        world.close_week(week)
        planted.extend(
            world.week_of_comments(
                term_week=week,
                texts=[
                    f"{A_HELD_COMMENT} (week {week}, response {index + 1})" for index in range(size)
                ],
                stream=contract.instructor_stream,
            )
        )
        used.append(week)
        remaining -= size

    for week in used:
        held_in_week = world.responses_in(term_week=week)
        assert 0 < held_in_week < threshold, (
            f"Term week {week} holds {held_in_week} responses and the configured threshold is "
            f"{threshold}. A held week that is empty holds nothing to release, and one at or above "
            "the threshold was never small-N — either way this world is not the one the test "
            "believes it planted."
        )

    volume = world.comment_answers_in_term()
    assert volume == count, (
        f"The section holds {volume} comment answers across the term and this test planted "
        f"{count}. The volume is what SPEC §4's cumulative rule is about, so a world that is not at "
        "the planted volume measures nothing."
    )
    return planted


def test_a_terms_volume_one_below_the_threshold_cuts_no_batch(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The lower half of the crossing pair: below the volume, nothing is released.

    SPEC §4 releases held comments "once the section's cumulative comment volume
    for the term crosses the threshold". Below it they stay held — they feed the
    summary and nothing else — because the batch is what stands between a released
    comment and the week it came from, and a batch cut one comment early is a
    batch small enough to be read back to its authors.

    **The pair is the test below**, which plants one comment more and requires a
    batch. This half on its own is passed by a cutter that never cuts anything.

    **The return value and the rows are asserted separately**, because a cutter
    that answered 0 and wrote rows would leak exactly as much as one that
    answered 1.

    **The mutation it kills:** the volume test dropped altogether, which releases
    every held comment the moment one exists; and the comparison written one
    comment loose, which releases a term's held set the week before SPEC §4 says
    it may be released.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    threshold = contract.threshold()
    plant_held_comments(world, contract, threshold - 1)

    answered = contract.cut()(world.session)

    assert answered == 0, (
        f"`{contract.cut_name}` reports {answered} batches cut over a section whose term volume is "
        f"{threshold - 1}, one below the configured threshold of {threshold}. SPEC §4 releases held "
        "comments once the volume *crosses* the threshold."
    )
    assert release_rows.batches() == [], f"A batch was cut anyway: {release_rows.batches()}."
    assert release_rows.members() == [], (
        f"Comments were released into a batch: {release_rows.members()}. The rows are asserted "
        "beside the return value because a cutter that answered 0 and wrote memberships would leak "
        "exactly as much as one that answered 1."
    )


def test_a_terms_volume_at_the_threshold_cuts_one_batch_holding_every_held_comment(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Criterion 3: the crossing releases exactly the stored batch, atomically.

    The criterion's own words: "a test drives volume across the threshold and
    every under-threshold comment surfaces in one batch or none do." Both halves
    are asserted — the membership is a set equality against what this test
    planted, and every membership is required to name **one** batch.

    **Why one batch is the property and not a tidiness preference.** ADR 0146 puts
    the only time in the design on the batch's `cut_at`, so a release split across
    several batches gives its comments several release times, and the differences
    between them are the per-comment timing SPEC §4 batches the release precisely
    to remove. A cutter writing one batch per week, or one per comment, satisfies
    "the comments were released" and undoes the guarantee.

    **The set equality runs in both directions.** Too few is a comment left held
    after the section crossed; too many is a comment released that was never
    under-threshold, which is the leak — it is already visible under its own week,
    so a batch entry shows the same student's words twice.

    **The mutation it kills:** a cutter that releases the newest held comment
    rather than all of them, or stops at the first week it finds, or carries a
    `LIMIT` on the membership insert.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    threshold = contract.threshold()
    planted = plant_held_comments(world, contract, threshold)

    answered = contract.cut()(world.session)

    assert answered == 1, (
        f"`{contract.cut_name}` reports {answered} batches cut for one section that crossed once. "
        f"The rows it left: {release_rows.batches()}."
    )

    batches = release_rows.batches()
    assert len(batches) == 1, (
        f"{len(batches)} batches were cut for one section's one crossing: {batches}.\n\n"
        "ADR 0146 puts the only time in the design on the batch's `cut_at`, so a release split "
        "across several batches gives its comments several release times — and the difference "
        "between two of them is the per-comment timing SPEC §4 batches the release to remove."
    )

    members = release_rows.members()
    named = {row[contract.batch_id_column] for row in members}
    assert named == {batches[0][release_rows.batch_key()]}, (
        f"The memberships name batches {sorted(named)} and the one batch cut is "
        f"{batches[0]}. Criterion 3: every under-threshold comment surfaces in one batch or none "
        "do."
    )

    released = {row[contract.answer_id_column] for row in members}
    expected = {world.answer_key(answer) for answer in planted}
    assert released == expected, (
        f"The batch holds {len(released)} comments and the section held {len(expected)} under the "
        f"threshold.\n\nIn the batch and not held: {sorted(released - expected)}\nHeld and not in "
        f"the batch: {sorted(expected - released)}\n\n"
        "The first list is the one to read first: a comment released that was never "
        "under-threshold is already visible under its own week, so a batch entry shows it a second "
        "time with its week stripped. The second is a comment left held after the section crossed, "
        "which criterion 3's 'one batch or none' forbids."
    )


def test_a_comment_from_a_week_that_is_still_open_is_never_released(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """A week whose count is not final cannot be a week whose count was under the threshold.

    SPEC §4's rule is about "n < 5 responses in a reporting week", and a week whose
    window is still open has no such number yet: the fifth response may arrive on
    Sunday evening. Releasing from it releases on a guess, and the guess is wrong
    in the direction that matters — a week that then reaches the threshold has its
    comments shown twice, once in a batch stripped of its week and once under the
    week itself.

    **The open week is open under any clock.** Its window opened in 2020 and
    closes in 2099 (`tests/fixtures/report_comments.py`), so the answer does not
    depend on the date CI runs on, nor on whether the implementation reads
    `app.services.clock` or the system clock.

    **The pair is in the same test**: the closed weeks' comments must all have been
    released, or this assertion is satisfied by a cutter that releases nothing.

    **The mutation it kills:** a held-comment query that filters on the response
    count and not on the window's close, which releases from a week that is still
    being answered.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    threshold = contract.threshold()
    closed = plant_held_comments(world, contract, threshold)

    world.open_week(OPEN_WEEK)
    still_open = world.week_of_comments(
        term_week=OPEN_WEEK, texts=[AN_OPEN_WEEKS_COMMENT], stream=contract.instructor_stream
    )
    assert world.responses_in(term_week=OPEN_WEEK) == 1, (
        "The open week holds no response, so it carries no comment and its exclusion below is a "
        "statement about nothing."
    )

    contract.cut()(world.session)

    released = release_rows.released_answers()
    assert released >= {world.answer_key(answer) for answer in closed}, (
        f"The closed under-threshold weeks' comments were not all released ({sorted(released)}), "
        "so the exclusion asserted below is satisfied by a cutter that released nothing."
    )

    from_the_open_week = {world.answer_key(answer) for answer in still_open} & released
    assert not from_the_open_week, (
        f"{sorted(from_the_open_week)} were released, and they belong to a week whose window has "
        "not closed. SPEC §4's threshold is a count of responses in a reporting week, and a week "
        "still taking responses has no final count — so a comment released from it may belong to a "
        "week that turns out to be at or above the threshold, and would then be shown twice: once "
        "in a batch with its week stripped, and once under its own week."
    )


def test_a_comment_from_a_week_at_the_threshold_is_never_released(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Disjointness: what an instructor already reads by week is never also in a batch.

    A comment in a week at or above the threshold is the instructor's to read
    under its own week, with its stream and its moderation status. Putting it in a
    release batch as well shows it a second time with its week removed, which
    conceals nothing and adds a second copy of one student's words to one report.

    **The pair is in the same test**: the small weeks' comments must be released,
    or a cutter that never releases anything passes this.

    **The mutation it kills:** a held-comment query written as "every comment not
    yet in a batch" — which is every comment in the section. That is the filter
    that gets dropped first, because the batch table is what the query already
    joins against and the threshold test looks redundant beside it.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    threshold = contract.threshold()
    small = plant_held_comments(world, contract, threshold)

    world.close_week(BIG_WEEK)
    big = world.week_of_comments(
        term_week=BIG_WEEK,
        texts=[f"{A_BIG_WEEK_COMMENT} ({index + 1})" for index in range(threshold)],
        stream=contract.instructor_stream,
    )
    at_the_boundary = world.responses_in(term_week=BIG_WEEK)
    assert at_the_boundary == threshold, (
        f"The big week holds {at_the_boundary} responses and the configured threshold is "
        f"{threshold}, so it is not a week whose comments an instructor already reads and the "
        "exclusion below is about the wrong week."
    )

    contract.cut()(world.session)

    released = release_rows.released_answers()
    assert released >= {world.answer_key(answer) for answer in small}, (
        f"The under-threshold weeks' comments were not all released ({sorted(released)}), so the "
        "exclusion below is satisfied by a cutter that released nothing."
    )

    from_the_big_week = {world.answer_key(answer) for answer in big} & released
    assert not from_the_big_week, (
        f"{sorted(from_the_big_week)} were released, and they belong to a week of {threshold} "
        "responses — a week at the configured threshold, whose comments the instructor already "
        "reads under their own week. A release entry for one of them puts the same student's words "
        "on the report twice, the second time with the week stripped off, and conceals nothing."
    )


def test_a_second_run_releases_nothing_and_leaves_the_first_batchs_rows_untouched(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The cutter runs weekly, so a second run is the ordinary case rather than the edge.

    E4-04's work order puts the crossing on a beat entry, so the cutter meets its
    own previous output every Monday for the rest of the term. A second run that
    re-released the same comments would cut a second batch with a second `cut_at`
    — the per-comment timing ADR 0146 removes — and one that deleted and rewrote
    the memberships would do the same thing while looking like a no-op.

    **Asserted by row identity**, which is why `ReleaseRows.identities` carries
    each membership's own key: a comparison over `(batch, comment)` pairs alone is
    satisfied by a run that deleted every row and wrote an equivalent one back.

    **The first run's rows are the starting state, and no fixture wrote them.**
    `docs/MISTAKES.md` entry 31 is "'running it twice is safe' was tested only
    against a database the loader itself had filled"; here the loader is the thing
    under test on its first call, and the first call's result is asserted before
    the second is made.

    **What this does not require.** A comment released twice is refused by the
    membership's `UNIQUE (answer_id)` (ADR 0146), and nothing here asks the cutter
    to swallow that error: the ADR leaves "whether that is caught or is a defect
    to see" to this ticket, and the work order settles it as a defect to see. So
    this test asserts the cutter does not *attempt* a second release, which is the
    property, rather than asserting how it would behave if it did.

    **The mutation it kills:** the "not already released" filter dropped from the
    held-comment query. On a fresh database that mutation is invisible — the first
    run behaves identically — and only a second run catches it.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    plant_held_comments(world, contract, contract.threshold())

    cut = contract.cut()
    first = cut(world.session)
    after_the_first = release_rows.identities()
    assert first == 1 and after_the_first, (
        f"The first run reported {first} batches and left {len(after_the_first)} memberships. "
        "Until it releases something, running it a second time proves nothing — this test would be "
        "comparing two empty sets and reporting success (`docs/MISTAKES.md` entry 3)."
    )

    second = cut(world.session)
    after_the_second = release_rows.identities()

    assert second == 0, (
        f"The second run reports {second} batches cut over a section whose held comments are all "
        "already released. A weekly beat entry meets this state every Monday for the rest of the "
        "term."
    )
    assert after_the_second == after_the_first, (
        "The membership rows changed between the two runs.\n\n"
        f"Added: {sorted(after_the_second - after_the_first)}\n"
        f"Removed: {sorted(after_the_first - after_the_second)}\n\n"
        "Each tuple is `(the membership's own key, its batch, its comment)`, so a run that deleted "
        "every row and wrote an equivalent one back shows up here and would not show up in a "
        "comparison of `(batch, comment)` pairs. ADR 0146 makes the batch's `cut_at` the only time "
        "in the design, and a comment moved into a new batch is a comment given a new release time."
    )
    assert len(release_rows.batches()) == 1, (
        f"The second run left {len(release_rows.batches())} batches: {release_rows.batches()}. An "
        "empty second batch is still a `cut_at` about this section, and the count of batches is "
        "what a later reader would use to date the term's releases."
    )
