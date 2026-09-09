"""The release gate, its three conditions, and what a cut batch may never be.

**The filename is narrower than this module now is**, and it is kept rather than
churned: the gate was one condition when the file was written and the security
round made it three. What it covers is stated here and in each test rather than
in the name (`git mv` to `..._is_gated_on_volume_respondents_and_weeks.py` is a
content-free change if the churn is ever worth paying).

SPEC §4, the sentence the whole of this module is about:

> Comments from under-threshold weeks are not discarded — they feed the summary,
> and they surface as raw text once the section's cumulative comment volume for
> the term crosses the threshold, **batched so that timing cannot identify an
> author**.

E4's breakdown decision 7 settles that the crossing is *stored* rather than
re-derived at read time (ADR 0146), and E4-04's work order settles the writer as
`cut_due_release_batches(session)` on a weekly beat.

## What the security round changed, and why

Two findings, converging on the same defect: the literal trigger in §4 counts the
wrong things.

  - **The volume is denominated in comment answers and the threshold in
    responses.** §3.2 gives every response two comment items, so five comments can
    come from three students — or from **one** student across three quiet weeks —
    and a release gated on the answer count alone goes out over an author set far
    below the number the threshold exists to protect. The batch is what stands
    between a released comment and its author; a batch of five comments by one
    person is not a batch.
  - **A volume condition stays true once crossed.** Every Monday after the first
    release the same section passes the same test, and the cutter takes whatever
    is held — which, after the first sweep, is exactly the one week that just
    closed. That is a per-week batch, and the report's own week-to-week delta
    re-attaches the week attribution ADR 0153 removed. Single-comment batches
    follow from the same shape.

So the gate is three conditions and **all** must hold before anything is cut:

  a. the cumulative comment-answer volume for the term reaches the threshold —
     §4's literal trigger, kept;
  b. the number of **distinct respondents** contributing unreleased held comments
     reaches the threshold;
  c. the unreleased held set spans at least **two** distinct under-threshold
     closed weeks.

When any fails, nothing is cut. Held is the safe direction, always: an
under-threshold comment that stays held still feeds the summary and is released
later, and a comment released early cannot be un-shown (ADR 0146: nothing in this
schema deletes a membership row).

**One honest note on isolating the three legs**, stated rather than papered over,
because a manifest claiming three independent boundary pairs would be claiming
something no test here can deliver. **Leg (b) implies both of the others.** The
respondents behind the held set are at most the number of held comments, which is
at most the cumulative volume, so (b) fails wherever (a) does; and an
under-threshold week holds fewer than `threshold` responses *by definition*, so a
held set inside one week has fewer than `threshold` respondents and (b) fails
wherever (c) does. Only (b) can be driven with the other two satisfied, and it is
— `test_five_comments_from_three_respondents_cut_nothing`. The other two are
driven as the **forbidden states** they exist to make impossible, and each of
those tests names which legs its case fails and why they cannot be pulled apart.
All three conditions are still worth writing separately: each survives a change to
another's denominator, and the reviewer asked for the property rather than for an
implementation of it.

**Every planted week's response count and the section's whole term volume are
read back out of the database** before any assertion rests on them, which is
E4-04's first known trap answered: a fixture bug here breaks this diff silently.

**The batches these tests read were cut by the cutter.** Nothing in
`tests/fixtures/report_comments.py` writes a `release_batch` row
(`docs/MISTAKES.md` entry 30), so the second-run and after-the-first-cut cases
start from the cutter's own output rather than from a planted one
(`docs/MISTAKES.md` entry 31).

**Which failure a red is.** `comment_contract.cut()` is a `pytest.fail` naming
`app.services.report_comments.cut_due_release_batches` — a FAILED assertion, not
an error in setup (`docs/MISTAKES.md` entry 44).
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fixtures.report_comments import (
    COMMENT_SERVICE_MODULE,
    CUT_FUNCTION,
    CUT_IS_OWED,
    CommentWorld,
    ReleaseRows,
    configured_threshold,
)

# **Marked `invariant`, which puts this module in CI's isolated §4.1 pass** where a
# skip or an empty collection is a failure (`scripts/ci/check_invariants.py`).
# §4.1 item 3, and ADR 0153's floors: every leg of this gate exists to keep a
# released comment's candidate author set at or above SPEC §4's threshold and its
# week set above one. A gate that opens too early releases held comments to an
# instructor who can read the gradebook's per-week completion ledger beside them
# (ADR 0125), which is the re-identification §4 exists to prevent. These are the
# tests that stop that, so they run in the pass that may never be skipped.
pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The term weeks this module uses, all inside cohort `F`'s run (term weeks 7 to
# 12). Six is exactly what the after-the-first-cut sequence needs: four to cross
# on, then one quiet week that must release nothing, then a second that must
# release with it.
HELD_WEEKS = (7, 8, 9, 10)
FIRST_QUIET_WEEK = 11
SECOND_QUIET_WEEK = 12
BIG_WEEK = 10
OPEN_WEEK = 12

A_HELD_COMMENT = "the pace of the reading was fine but the assessment came out of nowhere"
A_BIG_WEEK_COMMENT = "the studio sessions were the best part and there should be more of them"
AN_OPEN_WEEKS_COMMENT = "this week has not finished yet so nothing about it is final"
A_QUIET_WEEKS_COMMENT = "the week was quiet and hardly anybody filled the survey in at all"

# An institution's own threshold, chosen **not** to be SPEC §4's default and
# asserted to differ before it is used. Seven, so that a world of exactly five
# respondents — the spec's default — crosses under the default and does not cross
# under this one, which is the single planted world that tells a lookup from a
# literal 5 in the respondent leg.
INSTITUTIONS_OWN_N_THRESHOLD = 7


def held_week(
    world: CommentWorld,
    contract: Any,
    *,
    term_week: int,
    respondents: int | list[Any],
    streams: tuple[str, ...] | None = None,
    body: str = A_HELD_COMMENT,
) -> list[Any]:
    """One closed week below the threshold, holding one comment per stream per respondent.

    `respondents` is either how many new people answer, or the people themselves —
    the second is how a test plants the same person in two weeks, which is the
    world HIGH-1 is about and which no count can express.

    The week's response count is read back and required to be under the configured
    threshold: a week that is not is a week whose comments were never held, and
    every assertion about a release would then be about a set that is empty for a
    reason nobody chose.
    """
    streams = (contract.instructor_stream,) if streams is None else streams
    threshold = contract.threshold()
    world.close_week(term_week)

    people = (
        [world.respondent() for _ in range(respondents)]
        if isinstance(respondents, int)
        else list(respondents)
    )
    planted: list[Any] = []
    for index, person in enumerate(people):
        _response, written = world.submit(
            term_week=term_week,
            student=person,
            comments={
                stream: f"{body} (week {term_week}, respondent {index + 1}, {stream.lower()})"
                for stream in streams
            },
        )
        planted.extend(written[stream] for stream in streams)

    count = world.responses_in(term_week=term_week)
    assert 0 < count < threshold, (
        f"Term week {term_week} holds {count} responses and the configured threshold is "
        f"{threshold}. A week with none holds nothing to release, and a week at or above the "
        "threshold was never small-N — either way this is not the world the test believes it "
        "planted, which is E4-04's first known trap."
    )
    return planted


def assert_volume(world: CommentWorld, expected: int) -> None:
    """The term's comment-answer volume, read back and compared with what was planted."""
    volume = world.comment_answers_in_term()
    assert volume == expected, (
        f"The section holds {volume} comment answers across the term and this test planted "
        f"{expected}. The volume is leg (a) of the gate, so a world that is not at the planted "
        "volume measures nothing."
    )


def assert_no_batch_is_one_week_or_too_few_authors(
    release_rows: ReleaseRows, threshold: int
) -> None:
    """The three forbidden states, asserted over **every** batch the cutter has written.

    Called wherever a cut happens rather than being a test of its own, because the
    property is about each batch as it is written and not about one moment: the
    shape the security round found is a *second* batch, cut a Monday later, which
    is fine by every assertion made about the first.

      - **No batch maps to a single week.** Its week set is what the report's
        week-to-week delta would re-attach, so a one-week batch is the week
        attribution ADR 0153 removed, arriving by another route.
      - **No batch's author set is smaller than the threshold.** The batch is what
        stands between a released comment and its author; a batch of five comments
        by three people is a set of three candidates, which is the inference §4's
        threshold exists to prevent.
      - **No batch holds a single comment.** It follows from the two above and is
        asserted outright because it is the end state a reader recognises: a
        release of one comment, dated by its own `cut_at`, is the per-comment
        timing the batching removes.

    The walk from a membership to an author and a week is two joins the *product*
    must never make and a test may — `ReleaseRows.members_by_batch` says so.
    """
    members = release_rows.members_by_batch()
    weeks = release_rows.weeks_by_batch()
    authors = release_rows.authors_by_batch()

    one_week = {str(batch): len(found) for batch, found in weeks.items() if len(found) < 2}
    assert not one_week, (
        f"These batches hold comments from a single week (batch: week count) {one_week}.\n\n"
        "A batch whose comments all come from one week is the week attribution back again: the "
        "instructor's report shows a release that was not there last Monday, and the week that "
        "closed in between is the week it came from. ADR 0153 drops week attribution on release "
        "precisely because SPEC §3.4's per-week participation ledger, which ADR 0125 accepts is "
        "instructor-visible in the gradebook, narrows the author to whoever completed that week's "
        "comment item — and in a quiet week that intersection can be one person."
    )

    thin = {str(batch): len(found) for batch, found in authors.items() if len(found) < threshold}
    assert not thin, (
        f"These batches carry comments from fewer than {threshold} distinct respondents "
        f"(batch: author count) {thin}.\n\n"
        "SPEC §4's threshold is a number of people, not a number of sentences: §3.2 gives every "
        "response two comment items, so a volume that reaches the threshold can come from three "
        "students, or from one across three quiet weeks. A batch is what stands between a released "
        "comment and its author, and a batch with three authors is a set of three candidates."
    )

    alone = {str(batch): len(rows) for batch, rows in members.items() if len(rows) < 2}
    assert not alone, (
        f"These batches hold a single comment: {alone}. ADR 0146 makes the batch's `cut_at` the "
        "only time in the design because it is a fact about a *set*; a batch of one comment gives "
        "that comment its own release time, which is the per-comment timing SPEC §4 batches the "
        "release to remove."
    )


# ---------------------------------------------------------------------------
# Leg (b) — the respondents behind the held set. The one leg that isolates.
# ---------------------------------------------------------------------------


def test_five_comments_from_three_respondents_cut_nothing(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """HIGH-1's world, planted exactly: the volume is there and the people are not.

    Two respondents answer both of SPEC §3.2's comment questions in one quiet
    week, and enough single-comment respondents answer in the next to bring the
    section's comment-answer volume to exactly the threshold — from strictly fewer
    people than the threshold, across two under-threshold closed weeks.

    **This is the only case in this module that isolates one leg**, and it is why
    the leg exists. Leg (a) holds: the volume reaches the threshold. Leg (c) holds:
    the held set spans two weeks. Only the respondent count is short, and a gate
    that reads §4's sentence literally cuts here.

    **What it would release.** A threshold's worth of comments over three authors,
    with their weeks stripped, on a report whose reader can open the gradebook:
    SPEC §3.4 posts a per-week completion ledger there and ADR 0125 accepts that
    an instructor reads it. Three candidates for five comments is the inference
    §4's threshold exists to prevent, reached through the release rather than
    through a week.

    **The pair is the test below**, which plants the same volume over `threshold`
    respondents and requires a cut. This half alone is passed by a cutter that
    never cuts anything.

    **The mutation it kills:** the respondent leg deleted, leaving §4's literal
    comment-answer count — which is what shipped before the security round, and
    what every other test in this epic was green against.
    **The near miss it distinguishes:** counting distinct *responses* rather than
    distinct *respondents*. Two of these comments share one response, so a
    response count is also short here and is also caught — and the distinction
    matters, because the two numbers come apart in exactly this world.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 5, (
        f"The configured n-threshold is {threshold}, and this world needs room for a volume that "
        "reaches it out of strictly fewer people: two respondents writing two comments each, plus "
        "at least one more in a second week. Below 5 there is no such arrangement, and the "
        "arithmetic below would ask for a week with no respondents in it."
    )

    world.build()
    both = (contract.instructor_stream, contract.course_stream)
    doubling_up = held_week(world, contract, term_week=HELD_WEEKS[0], respondents=2, streams=both)
    remaining = threshold - len(doubling_up)
    singles = held_week(world, contract, term_week=HELD_WEEKS[1], respondents=remaining)

    assert_volume(world, threshold)
    contributors = 2 + remaining
    assert contributors < threshold, (
        f"This world has {contributors} respondents behind a volume of {threshold}, which is not "
        "fewer than the threshold — so it is not HIGH-1's world, and the assertion below would be "
        "about a section that ought to be released."
    )
    assert doubling_up and singles, "One of the two weeks planted nothing."

    answered = contract.cut()(world.session)

    assert answered == 0, (
        f"`{contract.cut_name}` cut {answered} batch(es) over a section holding {threshold} comment "
        f"answers written by {contributors} people across two under-threshold weeks.\n\n"
        "SPEC §4's threshold is a count of responses in a reporting week — a number of people — "
        "and §3.2 gives every response two comment items, so a volume that reaches it can come "
        "from far fewer authors. Releasing here hands the instructor a threshold's worth of "
        f"comments with their weeks stripped and an author set of {contributors}, which is the "
        "inference the threshold exists to prevent."
    )
    assert release_rows.members() == [], (
        f"Comments were released into a batch anyway: {release_rows.members()}. The return value "
        "and the rows are asserted separately because a cutter that answered 0 and wrote rows "
        "would leak exactly as much as one that answered 1."
    )


def test_the_same_volume_from_enough_respondents_is_released_as_one_batch(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The pair: `threshold` comments from `threshold` people over two weeks are released.

    The world above with its authors spread out — the same number of comments, one
    each, across two under-threshold closed weeks. All three legs hold and the
    release happens, which is what says the gate is a gate rather than a wall.

    **Without this half the suite has no test that a release ever happens under the
    new rules**, and a cutter that returned 0 unconditionally would pass every
    other assertion in this module (`docs/MISTAKES.md` entry 3).

    **The forbidden states are asserted over the batch it writes** — not one week,
    not fewer than `threshold` authors, not one comment — because the moment there
    is a batch, those are the properties that make it a batch rather than a
    disclosure.

    **The mutation it kills:** a respondent leg written with `>` where `>=` was
    meant, which withholds a section's held comments for the whole term at exactly
    the size §4 says is enough.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 4, f"The configured n-threshold is {threshold}; this world needs 4 or more."

    world.build()
    first_size = threshold // 2
    first = held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size)
    second = held_week(world, contract, term_week=HELD_WEEKS[1], respondents=threshold - first_size)

    assert_volume(world, threshold)
    assert len(first) + len(second) == threshold, (
        f"The two weeks planted {len(first)} and {len(second)} comments, not {threshold} between "
        "them."
    )

    answered = contract.cut()(world.session)

    assert answered == 1, (
        f"`{contract.cut_name}` cut {answered} batch(es) over a section holding {threshold} comment "
        f"answers from {threshold} distinct respondents across two under-threshold closed weeks — "
        "every leg of the gate satisfied. SPEC §4 releases held comments once the section crosses, "
        f"and a gate that never opens withholds them for the term. What it wrote: "
        f"{release_rows.batches()}."
    )
    released = {row[contract.answer_id_column] for row in release_rows.members()}
    expected = {world.answer_key(answer) for answer in [*first, *second]}
    assert released == expected, (
        f"In the batch and not held: {sorted(released - expected)}\nHeld and not in the batch: "
        f"{sorted(expected - released)}\n\nCriterion 3: every under-threshold comment surfaces in "
        "one batch or none do."
    )
    assert_no_batch_is_one_week_or_too_few_authors(release_rows, threshold)


def test_one_respondent_short_of_the_threshold_cuts_nothing_and_one_more_cuts(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The respondent leg's own boundary, both sides, with the volume leg held clear.

    `threshold - 1` people each answer **both** of SPEC §3.2's comment questions,
    across two under-threshold closed weeks. Nothing may be cut. Then one more
    person answers, and it may.

    **Why the doubled comments are the point.** They put the volume at
    `2 x (threshold - 1)`, which is past the threshold for any threshold above two,
    so leg (a) is satisfied on both sides of this boundary and cannot be what
    refuses the first half. Leg (c) is satisfied on both sides too — two weeks
    throughout. The only thing that moves between the two halves is the number of
    distinct respondents, from one below the threshold to exactly it.

    **The mutation it kills:** the respondent comparison loosened by one —
    `>= threshold - 1` where `>= threshold` was meant, or `>` written as `>=`
    against a decremented bound. That is the off-by-one a boundary has, and it is
    invisible to every other test in this module: the world in
    `test_five_comments_from_three_respondents_cut_nothing` sits *two* or more
    below the threshold, so a gate loosened by one still refuses it, and the
    worlds that cut sit exactly on the threshold, where a loosened gate cuts too.
    This is the only case that sits on the loosened bound itself.

    **Why the volume leg cannot mask it here**, which is the correction the
    re-mutation battery forced elsewhere in this module: with one comment per
    respondent the volume and the respondent count are the same number, so a
    volume-only gate refuses the first half for the volume reason and the test
    proves nothing about the respondent leg. Doubling the comments separates them,
    and the setup assertion below says so before the cutter is called.

    **The pair is inside this test** rather than in a sibling, because the two
    halves must be the same world one respondent apart: a pair built from two
    separately planted worlds could differ in the week split or the volume, and
    then the boundary would not be the only thing that moved.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 4, (
        f"The configured n-threshold is {threshold}. This world needs `threshold - 1` respondents "
        "spread over two weeks that are each still under the threshold, which needs 4 or more."
    )

    world.build()
    both = (contract.instructor_stream, contract.course_stream)
    one_short = threshold - 1
    first_size = one_short // 2
    held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size, streams=both)
    held_week(
        world, contract, term_week=HELD_WEEKS[1], respondents=one_short - first_size, streams=both
    )

    volume = len(both) * one_short
    assert_volume(world, volume)
    assert volume >= threshold, (
        f"The planted volume is {volume} and the threshold is {threshold}, so leg (a) fails here "
        "too and a volume-only gate would refuse the first half for the volume reason — which "
        "would make this test say nothing about the respondent boundary. The doubled comments "
        "exist to keep the two numbers apart."
    )

    refused = contract.cut()(world.session)
    assert refused == 0, (
        f"`{contract.cut_name}` cut {refused} batch(es) over a section holding {volume} comment "
        f"answers from {one_short} distinct respondents — one short of the configured threshold of "
        f"{threshold} — across two under-threshold closed weeks.\n\n"
        "The volume leg is satisfied and so is the two-week leg, so the only thing that may refuse "
        "this release is the respondent count, and it is one below. A gate that releases here is "
        "comparing against `threshold - 1`, and the batch it writes carries one author fewer than "
        "SPEC §4's threshold asks for — which is one candidate fewer for an instructor reading it "
        "beside the gradebook's per-week completion ledger (ADR 0125)."
    )
    assert (
        release_rows.members() == []
    ), f"Comments were released into a batch anyway: {release_rows.members()}."

    # The pair: one more person answers, in a week that is still under the
    # threshold, and nothing else about the world changes.
    held_week(world, contract, term_week=HELD_WEEKS[0], respondents=1, streams=both)
    cut = contract.cut()(world.session)
    assert cut == 1, (
        f"With one more respondent — {threshold} of them now, exactly the configured threshold — "
        f"`{contract.cut_name}` cut {cut} batch(es). A gate written with `>` where `>=` was meant "
        "withholds a section's held comments for the whole term at exactly the size §4 says is "
        "enough, and this half is what tells that from the refusal above."
    )
    assert_no_batch_is_one_week_or_too_few_authors(release_rows, threshold)


def test_the_respondent_count_is_of_the_unreleased_held_set_and_not_of_the_term(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Which comments the respondent leg counts over — the unreleased ones, and only those.

    A term with a release already in it. The first batch went out over a
    threshold's worth of people across two weeks; two new quiet weeks then close,
    carrying comments from **two** people. Nothing may be cut, even though the
    section's term-wide distinct respondents are now well past the threshold and
    its term-wide volume is too.

    **This is what makes "every batch carries at least a threshold's worth of
    authors" a claim a mutation can break.** A respondent count taken over the
    section's whole term is the natural way to write leg (b) — it is the same
    shape leg (a) has, and §4's own sentence says "the section's cumulative comment
    volume for the term" — and it is monotonic: once the term has enough people in
    it, the leg is satisfied for ever. The cutter then takes whatever is
    unreleased, which after the first sweep is the last week or two, and writes a
    batch whose authors are the two people who answered a quiet week. The floor
    `assert_no_batch_is_one_week_or_too_few_authors` asserts is real only if the
    denominator is the held set, and this is the test that says which denominator
    it is.

    **Every other test in this module has an empty release table when the cutter
    runs**, so term-wide and unreleased-held are the same set in all of them and
    the mutation is invisible. The first batch here is cut by the real cutter
    rather than planted (`docs/MISTAKES.md` entry 30: nothing in the fixtures
    writes a batch), which also makes it the second run's honest starting state
    (entry 31).

    **The two quiet weeks are two rather than one on purpose**, so leg (c) is
    satisfied and cannot be what refuses: the held set spans two under-threshold
    closed weeks, its volume is past the threshold term-wide, and the *only*
    condition that fails is the number of distinct people behind the unreleased
    comments.

    **The mutation it kills:** the respondent leg's denominator widened from the
    unreleased held set to the section's whole term — which is HIGH-2's shape
    reached through leg (b) rather than through leg (a), and which produces a
    second batch below ADR 0153's author floor on the very next Monday.
    **The near miss it distinguishes:** a gate that correctly refuses here and
    never releases the quiet weeks at all. That one is caught by
    `test_one_quiet_week_closing_after_a_first_cut_releases_nothing_and_two_release_together`,
    whose third Monday requires the release to happen once enough people are behind
    it; this test is the refusal half and says so rather than asserting both.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 4, (
        f"The configured n-threshold is {threshold}. This world needs a first wave that crosses "
        "and a quiet tail strictly under it, which needs 4 or more."
    )

    world.build()

    # The first release, cut by the cutter itself.
    first_size = threshold // 2
    held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size)
    held_week(world, contract, term_week=HELD_WEEKS[1], respondents=threshold - first_size)
    first = contract.cut()(world.session)
    assert first == 1, (
        f"The first run cut {first} batch(es) over a section holding {threshold} comments from "
        f"{threshold} respondents across two under-threshold weeks. Until a release exists, the "
        "term-wide and unreleased-held sets are the same and this test's whole subject — the "
        "difference between them — does not exist yet."
    )
    after_the_first = release_rows.identities()
    assert after_the_first, "The first run left no memberships, so there is no release to be after."
    assert_no_batch_is_one_week_or_too_few_authors(release_rows, threshold)

    # Two quiet weeks close. Two people between them, and they are new people, so
    # the term's own respondent count grows past the threshold while the
    # unreleased-held count is two.
    quiet: list[Any] = []
    for week in (FIRST_QUIET_WEEK, SECOND_QUIET_WEEK):
        quiet.extend(
            held_week(world, contract, term_week=week, respondents=1, body=A_QUIET_WEEKS_COMMENT)
        )

    unreleased_respondents = len(quiet)
    term_wide_respondents = threshold + unreleased_respondents
    assert unreleased_respondents < threshold <= term_wide_respondents, (
        f"The unreleased held set has {unreleased_respondents} respondents behind it and the term "
        f"has {term_wide_respondents}, against a threshold of {threshold}. This test needs the "
        "first number below the threshold and the second at or above it — otherwise the two "
        "denominators give the same answer and the mutation it exists for is invisible."
    )
    assert_volume(world, threshold + unreleased_respondents)

    answered = contract.cut()(world.session)

    assert answered == 0, (
        f"`{contract.cut_name}` cut {answered} batch(es). The section's term-wide volume and its "
        f"term-wide respondent count are both past the threshold of {threshold}, and the held set "
        f"spans two under-threshold closed weeks — but only {unreleased_respondents} people wrote "
        "the comments that are still unreleased.\n\n"
        "A respondent leg counted over the section's whole term is monotonic: once enough people "
        "have ever answered, it is satisfied for ever, and the cutter then takes whatever is "
        f"unreleased — here, {unreleased_respondents} comments by {unreleased_respondents} people. "
        "That batch is below the author floor SPEC §4's threshold sets, and no assertion about the "
        "*first* batch would notice, because the first batch is fine. The denominator is the "
        "unreleased held set."
    )
    assert release_rows.identities() == after_the_first, (
        "The membership rows changed.\n\nAdded: "
        f"{sorted(release_rows.identities() - after_the_first)}\nRemoved: "
        f"{sorted(after_the_first - release_rows.identities())}\n\nThe return value and the rows "
        "are asserted separately because a cutter that answered 0 and wrote memberships would leak "
        "exactly as much as one that answered 1."
    )
    assert len(release_rows.batches()) == 1, (
        f"The section holds {len(release_rows.batches())} batches: {release_rows.batches()}. An "
        "empty second batch is still a `cut_at` about this section."
    )


def test_the_respondent_leg_follows_an_institutions_own_threshold(
    comment_world: CommentWorld,
    comment_contract: Any,
    release_rows: ReleaseRows,
    documented_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """SPEC §4's "threshold value is configurable", driven on the leg the round added.

    **Which leg the refusal isolates, and this is the whole design of the world.**
    SPEC §4's default number of respondents each answer *both* of §3.2's comment
    questions, across two under-threshold closed weeks. Under an institution whose
    configured threshold is `INSTITUTIONS_OWN_N_THRESHOLD`:

      - leg (a) **holds** — the volume is twice the spec default, comfortably past
        the configured threshold;
      - leg (c) **holds** — the held set spans two weeks;
      - leg (b) **fails** — five distinct respondents where the institution asks
        for seven.

    So nothing may be cut, and the refusal can come from no other leg.

    **The first version of this test got that wrong, and the red run caught it.**
    It planted one comment per respondent, so the volume was five as well; the
    volume-only gate that shipped refused for the volume reason, and the test
    passed against an implementation with no respondent leg in it at all — a guard
    whose outcome a second layer also produces, which is `docs/MISTAKES.md` entry
    3 in the shape that reads as coverage. The doubled comments are what separate
    the two numbers, and the two setup assertions below are what say so before the
    cutter is called.

    **The respondent count is exactly SPEC §4's default**, which is what makes the
    assertion discriminate rather than merely hold: a respondent leg carrying a
    literal 5 sees five respondents and releases, and one that reads
    `Settings.n_threshold_default` sees five against seven and holds.

    **Why the module is re-imported.** A module that builds something out of
    `Settings` may read the environment once, at import time, and
    `import_app_module` exists for that. Re-importing after the override makes
    this true of a cutter that reads `Settings` per call *and* of one that holds a
    `Settings` from import, so it asserts the criterion rather than an
    implementation of it — the reasoning
    `tests/integration/test_a_resolved_scope_holds_care_beside_the_purview.py`
    records for the same configuration value. The world is seeded before the
    re-import, because `import_app_module` empties `app.*` out of `sys.modules`.

    **Only the fails-closed half is driven here**, deliberately: a world that
    crosses under 7 needs seven respondents over weeks that each stay under 7,
    which is a larger world, and the opens half of this leg is already asserted at
    the configured value by the test above. What this test is for is the literal.

    **The mutation it kills:** `>= 5`, or any other literal, in place of the
    `Settings` lookup in the respondent leg — green against every other test in
    this epic, because the suite's own environment carries 5.
    """
    contract = comment_contract
    world = comment_world
    documented = documented_env.get(contract.threshold_variable)
    assert documented is not None and int(documented) == contract.spec_default_threshold, (
        f"`.env.example` documents `{contract.threshold_variable}` as {documented!r} and SPEC §4's "
        f"default is {contract.spec_default_threshold}. That is a configuration defect rather than "
        "a cutter one, and this test cannot pose its question without it."
    )
    assert contract.spec_default_threshold < INSTITUTIONS_OWN_N_THRESHOLD, (
        f"This test runs under a threshold of {INSTITUTIONS_OWN_N_THRESHOLD}, which is not above "
        f"SPEC §4's default of {contract.spec_default_threshold}, so the planted world is not "
        "between the two numbers and a cutter holding the default would answer it the same way."
    )

    world.build()
    # **Both comment questions each**, so the volume is twice the respondent count:
    # leg (a) is satisfied under the institution's higher threshold while leg (b)
    # is not. One comment each would leave the volume equal to the respondent count
    # and below the override, and the refusal would then be the volume leg's —
    # which is how this test read green against an implementation that has no
    # respondent leg.
    both = (contract.instructor_stream, contract.course_stream)
    at_the_spec_default = contract.spec_default_threshold
    first_size = at_the_spec_default // 2
    held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size, streams=both)
    held_week(
        world,
        contract,
        term_week=HELD_WEEKS[1],
        respondents=at_the_spec_default - first_size,
        streams=both,
    )
    volume = len(both) * at_the_spec_default
    assert_volume(world, volume)
    assert volume >= INSTITUTIONS_OWN_N_THRESHOLD, (
        f"The planted volume is {volume} and the institution's threshold is "
        f"{INSTITUTIONS_OWN_N_THRESHOLD}, so leg (a) fails here too — a volume-only gate would "
        "refuse for the volume reason, and the assertion below would be true of an implementation "
        "with no respondent leg in it. That is exactly how this test read green on its first run."
    )
    assert at_the_spec_default < INSTITUTIONS_OWN_N_THRESHOLD, (
        f"The planted respondent count is {at_the_spec_default} and the institution asks for "
        f"{INSTITUTIONS_OWN_N_THRESHOLD}; if it were not below, the refusal asserted below could "
        "not come from the respondent leg either."
    )

    monkeypatch.setenv(contract.threshold_variable, str(INSTITUTIONS_OWN_N_THRESHOLD))
    configured = configured_threshold()
    assert configured == INSTITUTIONS_OWN_N_THRESHOLD, (
        f"`Settings.n_threshold_default` reads {configured} after `{contract.threshold_variable}` "
        f"was set to {INSTITUTIONS_OWN_N_THRESHOLD}, so the override never reached configuration "
        "and this is a failure of the test's setup rather than of the cutter."
    )

    module = import_app_module(COMMENT_SERVICE_MODULE)
    assert module is not None, f"There is no `{COMMENT_SERVICE_MODULE}` module. {CUT_IS_OWED}"
    cut = getattr(module, CUT_FUNCTION, None)
    assert callable(cut), (
        f"`{COMMENT_SERVICE_MODULE}` exposes no callable `{CUT_FUNCTION}`; it exposes "
        f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n{CUT_IS_OWED}"
    )

    answered = cut(world.session)

    assert answered == 0, (
        f"`{CUT_FUNCTION}` cut {answered} batch(es) over a section holding {volume} comment answers "
        f"written by {at_the_spec_default} respondents across two under-threshold weeks, under an "
        f"institution whose configured threshold is {INSTITUTIONS_OWN_N_THRESHOLD}.\n\n"
        f"The volume leg is satisfied here ({volume} is past {INSTITUTIONS_OWN_N_THRESHOLD}) and so "
        "is the two-week leg, so the only thing that may refuse this release is the respondent "
        f"count — and {at_the_spec_default} is SPEC §4's *default*, which this institution's "
        "configuration deliberately is not: 'Threshold value is configurable (default 5).' A "
        "release here is a respondent leg comparing against a literal rather than against "
        "`Settings.n_threshold_default`, which is a rule that stops being the institution's the "
        "day they change it."
    )
    assert release_rows.members() == [], f"Comments were released anyway: {release_rows.members()}."


# ---------------------------------------------------------------------------
# Leg (c) — two weeks, asserted as the forbidden state it makes impossible.
# ---------------------------------------------------------------------------


def test_a_held_set_confined_to_one_week_is_never_released(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """No batch may map to a single week, driven at the largest single week there is.

    One under-threshold week, filled to `threshold - 1` respondents — the most a
    week can hold and still be small-N — each answering both of §3.2's comment
    questions, so the volume is `2 x (threshold - 1)` and leg (a) is comfortably
    satisfied. Nothing may be cut.

    **Which legs this case fails, said plainly.** Legs (b) and (c) both, and they
    cannot be pulled apart: an under-threshold week holds fewer than `threshold`
    responses by definition, so a held set inside one week has fewer than
    `threshold` respondents however many comments each of them wrote. That is why
    this is written as the forbidden state — "no batch ever maps to a single week"
    — rather than as a boundary pair on leg (c) alone, and why the module docstring
    says leg (b) implies leg (c). Keeping (c) as its own condition is still worth
    the line: it is the one that survives if (b)'s denominator is ever changed.

    **What leg (a) alone would do here is the point of the case.** The volume is
    nearly twice the threshold, so a gate reading §4's sentence literally releases
    a single week's comments — stripped of their week — to an instructor whose
    report showed nothing there last Monday. The delta names the week.

    **The pair is in the second half of this test**: one more under-threshold week,
    and the section is released. Otherwise this is passed by a cutter that never
    cuts.

    **The mutation it kills:** the two-week condition deleted, on the reasoning
    that the respondent leg already covers it. It does today; it stops covering it
    the first time somebody counts responses instead of respondents, and this is
    the test that notices.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 3, (
        f"The configured n-threshold is {threshold}; a single week below it cannot hold two "
        "respondents and there is nothing to confine."
    )

    world.build()
    both = (contract.instructor_stream, contract.course_stream)
    inside_one_week = held_week(
        world, contract, term_week=HELD_WEEKS[0], respondents=threshold - 1, streams=both
    )
    volume = 2 * (threshold - 1)
    assert_volume(world, volume)
    assert volume >= threshold, (
        f"A single week of {threshold - 1} respondents writing two comments each gives a volume of "
        f"{volume}, which does not reach the threshold of {threshold} — so leg (a) fails here too "
        "and this case no longer shows what a volume-only gate would do."
    )
    assert len(inside_one_week) == volume, "The week did not plant the comments this test counted."

    answered = contract.cut()(world.session)
    assert answered == 0, (
        f"`{contract.cut_name}` cut {answered} batch(es) over a section whose entire held set — "
        f"{volume} comments, a volume well past the threshold of {threshold} — sits in one "
        "under-threshold week.\n\n"
        "A batch holding one week's comments is the week attribution back again by another route: "
        "the instructor's report shows a release that was not there last Monday, and the week that "
        "closed in between is the week it came from. ADR 0153 drops the week on release because "
        "SPEC §3.4's per-week participation ledger, instructor-visible in the gradebook "
        "(ADR 0125), narrows the author to whoever completed that week's comment item."
    )
    assert release_rows.members() == [], f"Comments were released: {release_rows.members()}."

    # The pair: the same section, one more under-threshold week, and now it may go
    # out. Every leg is satisfied — the volume was already past the threshold, the
    # held set now spans two weeks, and the respondents behind it reach it.
    held_week(world, contract, term_week=HELD_WEEKS[1], respondents=threshold - 1)
    second = contract.cut()(world.session)
    assert second == 1, (
        f"With a second under-threshold week holding {threshold - 1} more respondents' comments, "
        f"`{contract.cut_name}` cut {second} batch(es). A cutter that still refuses is a wall "
        "rather than a gate, and this section's students never see their comments answered."
    )
    assert_no_batch_is_one_week_or_too_few_authors(release_rows, threshold)


# ---------------------------------------------------------------------------
# Leg (a) — SPEC §4's literal trigger, kept.
# ---------------------------------------------------------------------------


def test_a_terms_volume_one_below_the_threshold_cuts_no_batch(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Below §4's own trigger, nothing is released — the leg the spec states literally.

    `threshold - 1` comments from that many respondents across two under-threshold
    closed weeks.

    **Which leg this green refusal isolates: none of them, and that is stated
    rather than assumed.** Leg (c) holds; legs (a) and (b) fail together and cannot
    be separated in this direction, because the respondents behind a held set are
    at most the number of comments in it — so a volume below the threshold has
    fewer authors than the threshold too. A green here is therefore consistent with
    a gate that has only the volume leg, only the respondent leg, or both, and this
    test is not evidence about which. What it *is* evidence for is SPEC §4's own
    sentence: below the trigger, nothing goes out. The test that discriminates the
    respondent leg is `test_five_comments_from_three_respondents_cut_nothing`, and
    the one that discriminates the lookup from a literal is
    `test_the_respondent_leg_follows_an_institutions_own_threshold`.

    **The pair is
    `test_the_same_volume_from_enough_respondents_is_released_as_one_batch`**,
    which plants one comment more and requires a cut.

    **This test kills no mutation, and the claim that it did was false.** An
    earlier draft of this docstring said it killed "the volume test dropped
    altogether"; the round's re-mutation battery deleted exactly that and the whole
    suite stayed green, for the reason the paragraph above already gives — leg (b)
    fails wherever leg (a) does, so the respondent leg refuses every world in which
    the volume leg would have, and removing the volume leg changes no outcome any
    test here can observe. The earlier paragraph is the true record and this one
    replaces the claim rather than sitting beside it (`docs/MISTAKES.md` entry 1:
    a record that went on asserting something a change had made false).

    **So what is this test for?** It records SPEC §4's own sentence as a
    behaviour — below the trigger, nothing goes out — at the value the spec states
    it at. That is worth keeping even where it is subsumed: leg (a) is the
    condition §4 actually writes down, and the day somebody changes leg (b)'s
    denominator to something that is no longer bounded by the comment count, this
    is the test that stops the volume condition disappearing with it. It is a
    record, not a guard, and saying so is the honest version.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 3, f"The configured n-threshold is {threshold}; nothing is plantable below."

    world.build()
    first_size = (threshold - 1) // 2
    held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size)
    held_week(world, contract, term_week=HELD_WEEKS[1], respondents=threshold - 1 - first_size)
    assert_volume(world, threshold - 1)

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


# ---------------------------------------------------------------------------
# HIGH-2 — what the second Monday, and the third, may do.
# ---------------------------------------------------------------------------


def test_one_quiet_week_closing_after_a_first_cut_releases_nothing_and_two_release_together(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The reviewer's exact scenario, run as three Mondays.

    A section crosses and its held comments go out as one batch. The next week is
    quiet — a couple of responses — and its window closes. **The next run must cut
    nothing**, because the only thing unreleased is that one week and it has
    neither enough respondents nor a second week beside it. A second quiet week
    closes, and now the two go out **together, as one batch**.

    **This is the finding, and it is not an edge case.** A volume condition stays
    true once crossed: the term's cumulative comment count only grows, so every
    Monday after the first release the section passes the same test and the cutter
    takes whatever is held — which, after the first sweep, is exactly the one week
    that just closed. That is a per-week batch every week, and the instructor's
    report re-attaches the week for free: the release that was not there last
    Monday came from the week that closed in between. Single-comment batches follow
    in any week where one person wrote something.

    **Three assertions, one per Monday**, because a cutter can be right on the
    first and wrong on the second. The first cut is what makes the second run's
    silence meaningful — a cutter that never cuts passes step two trivially — and
    the third is what says the silence was a hold rather than a refusal: held
    comments must eventually surface, or §4's "they surface as raw text" is a
    sentence rather than a behaviour.

    **The second batch is asserted to hold both quiet weeks' comments and nothing
    else**, in both directions. Too few is a comment still held after the section
    crossed a second time; too many is the first batch's comments released twice,
    which ADR 0146's `UNIQUE (answer_id)` refuses at the database — so it would
    arrive as an error rather than as a duplicate, and the equality names it either
    way.

    **The mutation it kills:** the unreleased-held set replaced by the term's whole
    held set in the respondent and week legs, so the legs are evaluated against
    comments already in a batch and stay satisfied for ever — the exact defect the
    round found.
    **The near miss it distinguishes:** a cutter that correctly holds the first
    quiet week and then never releases it, which step three catches.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 4, (
        f"The configured n-threshold is {threshold}. This sequence needs a first quiet week "
        "strictly under it and a second that carries the pair over it, which needs 4 or more."
    )

    world.build()

    # Monday one: four under-threshold weeks, two respondents each, cross and cut.
    first_wave: list[Any] = []
    for week in HELD_WEEKS:
        first_wave.extend(held_week(world, contract, term_week=week, respondents=2))
    assert_volume(world, 2 * len(HELD_WEEKS))
    first = contract.cut()(world.session)
    assert first == 1, (
        f"The first run cut {first} batch(es) over a section holding {2 * len(HELD_WEEKS)} comments "
        f"from {2 * len(HELD_WEEKS)} respondents across {len(HELD_WEEKS)} under-threshold weeks. "
        "Until it releases something, the silence asserted next is what this cutter does to "
        "everything (`docs/MISTAKES.md` entry 3)."
    )
    after_the_first = release_rows.identities()
    assert_no_batch_is_one_week_or_too_few_authors(release_rows, threshold)

    # Monday two: one quiet week has closed since. Nothing may go out.
    quiet_respondents = 2
    assert quiet_respondents < threshold, (
        f"The quiet week holds {quiet_respondents} respondents and the threshold is {threshold}; a "
        "quiet week that is not under it is not the week this scenario is about."
    )
    quiet_one = held_week(
        world,
        contract,
        term_week=FIRST_QUIET_WEEK,
        respondents=quiet_respondents,
        body=A_QUIET_WEEKS_COMMENT,
    )
    second = contract.cut()(world.session)
    assert second == 0, (
        f"The second run cut {second} batch(es). The only thing unreleased is one quiet week "
        f"holding {quiet_respondents} respondents' comments — fewer than the threshold of "
        f"{threshold}, and confined to a single week.\n\n"
        "A volume condition stays true once crossed, so a gate that reads only the term's "
        "cumulative count passes here and every Monday after it, and takes whatever is held: "
        "exactly the week that just closed. That is a per-week batch, and the report's own delta "
        "re-attaches the week — the release that was not there last Monday came from the week that "
        "closed in between."
    )
    assert release_rows.identities() == after_the_first, (
        "The membership rows changed on the second run.\n\nAdded: "
        f"{sorted(release_rows.identities() - after_the_first)}\nRemoved: "
        f"{sorted(after_the_first - release_rows.identities())}"
    )

    # Monday three: a second quiet week has closed. The two go out together.
    quiet_two = held_week(
        world,
        contract,
        term_week=SECOND_QUIET_WEEK,
        respondents=threshold - quiet_respondents,
        body=A_QUIET_WEEKS_COMMENT,
    )
    third = contract.cut()(world.session)
    assert third == 1, (
        f"The third run cut {third} batch(es). Two quiet weeks are now unreleased between them, "
        f"holding {threshold} respondents' comments — every leg satisfied. A cutter that holds them "
        "for ever is a wall: SPEC §4 says under-threshold comments 'surface as raw text once the "
        "section's cumulative comment volume for the term crosses the threshold', and a section "
        "whose quiet weeks never surface has lost them."
    )

    batches = release_rows.batches()
    assert (
        len(batches) == 2
    ), f"The section holds {len(batches)} batches after three runs: {batches}."
    assert first_wave, "The first wave planted nothing, so the difference below is the whole table."
    grew = release_rows.identities() - after_the_first
    released_now = {member[2] for member in grew}
    expected_now = {world.answer_key(answer) for answer in [*quiet_one, *quiet_two]}
    assert released_now == expected_now, (
        f"The second batch holds {len(released_now)} comments and the two quiet weeks between them "
        f"held {len(expected_now)}.\n\nIn the batch and not a quiet week's: "
        f"{sorted(released_now - expected_now)}\nA quiet week's and not in the batch: "
        f"{sorted(expected_now - released_now)}\n\nThe first list is the first wave released a "
        "second time, which ADR 0146's `UNIQUE (answer_id)` refuses at the database. The second is "
        "a comment left held after the section crossed again."
    )
    assert_no_batch_is_one_week_or_too_few_authors(release_rows, threshold)


# ---------------------------------------------------------------------------
# What may not be in a batch, whatever the gate says.
# ---------------------------------------------------------------------------


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
    released, or this is satisfied by a cutter that releases nothing.

    **The mutation it kills:** a held-comment query that filters on the response
    count and not on the window's close, which releases from a week still being
    answered.
    **The near miss it distinguishes:** an open week's respondent counted toward
    the gate's second leg. They are not counted here — the closed weeks already
    carry the gate — so what this test reports is the *membership*, which is where
    the difference shows.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 4, f"The configured n-threshold is {threshold}; this world needs 4 or more."

    world.build()
    closed: list[Any] = []
    first_size = threshold // 2
    closed.extend(held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size))
    closed.extend(
        held_week(world, contract, term_week=HELD_WEEKS[1], respondents=threshold - first_size)
    )

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
    threshold = contract.threshold()
    assert threshold >= 4, f"The configured n-threshold is {threshold}; this world needs 4 or more."

    world.build()
    small: list[Any] = []
    first_size = threshold // 2
    small.extend(held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size))
    small.extend(
        held_week(world, contract, term_week=HELD_WEEKS[1], respondents=threshold - first_size)
    )

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
    """Two runs with nothing new in between: the same rows, and no second batch.

    The cutter runs weekly, so it meets its own previous output every Monday for
    the rest of the term. This is the simplest form of that — nothing has closed in
    between — and
    `test_one_quiet_week_closing_after_a_first_cut_releases_nothing_and_two_release_together`
    is the form the security round found the defect in.

    **Asserted by row identity**, which is why `ReleaseRows.identities` carries
    each membership's own key: a comparison over `(batch, comment)` pairs alone is
    satisfied by a run that deleted every row and wrote an equivalent one back,
    which would give every released comment a new `cut_at`.

    **The first run's rows are the starting state, and no fixture wrote them.**
    `docs/MISTAKES.md` entry 31 is "'running it twice is safe' was tested only
    against a database the loader itself had filled"; here the loader is the thing
    under test on its first call, and that call's result is asserted before the
    second is made.

    **What this does not require.** A comment released twice is refused by
    `UNIQUE (answer_id)` (ADR 0146), and nothing here asks the cutter to swallow
    that error: the ADR leaves "whether that is caught or is a defect to see" to
    this ticket and the work order settles it as a defect to see.

    **The mutation it kills:** the "not already released" filter dropped from the
    held-comment query. On a fresh database that mutation is invisible — the first
    run behaves identically — and only a second run catches it.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 4, f"The configured n-threshold is {threshold}; this world needs 4 or more."

    world.build()
    first_size = threshold // 2
    held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size)
    held_week(world, contract, term_week=HELD_WEEKS[1], respondents=threshold - first_size)

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
        "already released and where nothing has closed in between."
    )
    assert after_the_second == after_the_first, (
        "The membership rows changed between the two runs.\n\n"
        f"Added: {sorted(after_the_second - after_the_first)}\n"
        f"Removed: {sorted(after_the_first - after_the_second)}\n\n"
        "Each tuple is `(the membership's own key, its batch, its comment)`, so a run that deleted "
        "every row and wrote an equivalent one back shows up here and would not in a comparison of "
        "`(batch, comment)` pairs. ADR 0146 makes the batch's `cut_at` the only time in the design, "
        "and a comment moved into a new batch is a comment given a new release time."
    )
    assert len(release_rows.batches()) == 1, (
        f"The second run left {len(release_rows.batches())} batches: {release_rows.batches()}. An "
        "empty second batch is still a `cut_at` about this section, and the count of batches is "
        "what a later reader would use to date the term's releases."
    )


def test_the_gate_is_read_per_section_so_one_crossing_releases_one_sections_comments(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The three conditions are a section's, not an institution's.

    Two sections of one term. One holds enough respondents across enough weeks to
    cross; the other holds two quiet weeks with one respondent each and does not.
    Only the first is released.

    **Why this is worth its own test now.** Each of the three legs is a count, and
    a count is exactly the thing that gets computed one scope too wide: a
    respondent count taken over the term rather than over the section carries a
    small section across on its neighbours' students, and every other test in this
    module has one section in it and would not notice.

    **Which leg the quiet section's refusal isolates: none, and it does not need
    to.** Two comments from two people over two weeks fails legs (a) and (b)
    together on its own rows. The property under test is the *grouping* rather than
    the leg — whichever leg is mis-scoped, computing it over the term instead of
    over `(section, term)` lifts the quiet section over the line on its
    neighbour's students, and the assertion below sees that as a second batch
    holding comments this section's students never wrote.

    **The pair is inside the test**: the crossing section must be released, or a
    cutter that releases nothing passes.

    **The mutation it kills:** any of the three legs grouped by term instead of by
    `(section, term)`.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 4, f"The configured n-threshold is {threshold}; this world needs 4 or more."

    world.build()
    quiet_cohort = "Q"
    world.section(quiet_cohort)

    first_size = threshold // 2
    crossing: list[Any] = []
    crossing.extend(held_week(world, contract, term_week=HELD_WEEKS[0], respondents=first_size))
    crossing.extend(
        held_week(world, contract, term_week=HELD_WEEKS[1], respondents=threshold - first_size)
    )

    # The quiet section: two weeks, one respondent each. Two people in total, so
    # neither the volume nor the author set reaches the threshold on its own rows.
    quiet: list[Any] = []
    for week in (HELD_WEEKS[0], HELD_WEEKS[1]):
        world.close_week(week)
        _response, written = world.submit(
            term_week=week,
            cohort=quiet_cohort,
            comments={contract.instructor_stream: f"{A_QUIET_WEEKS_COMMENT} (week {week})"},
        )
        quiet.append(written[contract.instructor_stream])
        count = world.responses_in(term_week=week, cohort=quiet_cohort)
        assert count == 1, f"The quiet section's week {week} holds {count} responses, not one."

    answered = contract.cut()(world.session)

    assert answered == 1, (
        f"`{contract.cut_name}` cut {answered} batch(es) over two sections, one of which crossed "
        f"and one of which holds {len(quiet)} comments from {len(quiet)} people. One is the answer: "
        "two means the quiet section was released on its neighbour's students, and zero means the "
        "crossing section was held on its neighbour's silence."
    )

    released = release_rows.released_answers()
    assert released == {world.answer_key(answer) for answer in crossing}, (
        f"Released: {sorted(released)}.\n\nThe quiet section's comments are "
        f"{sorted(world.answer_key(answer) for answer in quiet)} and none of them may be in a "
        "batch: that section holds two comments from two people, which is neither the volume nor "
        "the author set SPEC §4's threshold asks for. Each of the three legs is a count, and a "
        "count taken over the term rather than over the section carries a small section across on "
        "somebody else's students."
    )
    assert_no_batch_is_one_week_or_too_few_authors(release_rows, threshold)
