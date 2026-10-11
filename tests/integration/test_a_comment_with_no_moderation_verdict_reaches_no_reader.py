"""No verdict, no comment — E6-01, criterion 1, and the section-week rule over a sequence of reads.

Until E6-01 a comment with no moderation row counted as published, and nothing
wrote one, so every comment was shown and summarized whether or not moderation had
ever run (`docs/tickets/e6/carried-from-e5.md`, "A comment with no moderation
verdict counts as published"). E6-01's first criterion: a comment holding no
moderation verdict is absent from `visible_comments`, from `released_comments`,
from every release batch, and from the gather's model-facing input.

**And a section-week is moderated or it is not** (work order decision 5, the
answer to the ticket's entries 50 and 51 question): a section-week is moderated
when every comment of it the view would otherwise show holds a verdict. Until
then the comment read returns nothing of that week, the release cut skips it, and
the gather does not summarize it; once the last verdict lands, all of it at once.
No read shows a partial set. The criterion's own words — "tests assert it over a
sequence of reads, not one read" — are why the second and third tests below read
the same week three times and two times with verdicts landing between.

**Every absence here has a present control in the same world**
(`docs/MISTAKES.md` entry 3): a verdicted comment that appears in the same reader,
read the same way, in the same test.

**Marked `invariant`**: §4.1 item 3's read path, and §6.2's "suppressed from all
instructor and leadership views" one step earlier — a comment nobody has
moderated is a comment nobody has checked for a self-harm disclosure.

**Which failure a red is, before E6-01.** Each world plants verdicts through
`app.services.moderation.route_verdict`, so the first red is a FAILED naming it
(`docs/MISTAKES.md` entry 44).
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.moderation import CLEAR, UNMODERATED
from fixtures.report_comments import CommentWorld, ReleaseRows
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.summary_job import INSTRUCTOR_STREAM as INSTRUCTOR_TOKEN
from fixtures.summary_job import StreamAwareGateway, comment_text

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Term weeks inside cohort `F`'s run (7 to 12), each given its own 2020 window by
# `CommentWorld.close_week`, so all of them are closed whatever the clock says.
HELD_A = 7
HELD_B = 8
HELD_AND_FAILED = 9
SHOWN = 10
SHOWN_AND_FAILED = 11

# When a failed moderation call is recorded: an hour after its week closed, which
# is when E6-02's sweep would first have tried.
AN_HOUR_AFTER_THE_CLOSE = timedelta(hours=1)


def texts_of(comments: Any) -> set[str]:
    return {str(comment.text) for comment in comments}


def read(world: CommentWorld, contract: Any, week: int) -> Any:
    """`visible_comments` for one week's instructor stream."""
    return contract.visible()(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(week),
        stream=INSTRUCTOR_STREAM,
    )


def released(world: CommentWorld, contract: Any) -> Any:
    return contract.released()(
        world.session,
        section_id=world.section_id(),
        term_id=world.term_id(),
        stream=INSTRUCTOR_STREAM,
    )


def plant(
    world: CommentWorld, week: int, nonces: list[str], *, moderation: Any = CLEAR
) -> list[Any]:
    """One respondent per nonce in one week, each commenting about the instructor."""
    return [
        world.submit(
            term_week=week,
            comments={INSTRUCTOR_STREAM: comment_text(INSTRUCTOR_TOKEN, nonce)},
            moderation={INSTRUCTOR_STREAM: moderation},
        )[1][INSTRUCTOR_STREAM]
        for nonce in nonces
    ]


def nonces(prefix: str, count: int) -> list[str]:
    """`count` tokens found nowhere else in the repository, so a match in a prompt is evidence."""
    return [f"E601{prefix}{index:02d}Qz" for index in range(count)]


def test_a_failed_moderation_run_leaves_its_comment_out_of_all_four_readers(
    summary_job_environment: Any,
    committed_rows: Any,
    committed_comment_world: CommentWorld,
    committed_release_rows: ReleaseRows,
    comment_contract: Any,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """Criterion 1, as the ticket words it: a failed moderation run, and all four readers.

    Two comments whose moderation call failed — a `moderation_attempt` row and no
    verdict — one in a week large enough to be shown and one in a week small
    enough to be held, because no single week reaches all four readers: a shown
    week's comments are never batched, and a held week's are never shown under it.
    Beside them, in the same section and term, verdicted comments that reach each
    reader:

      - `visible_comments` — the shown week at the threshold, all `clear`: its
        comments are returned. The failed comment's own week returns no comment
        of it.
      - the cut and `released_comments` — two held weeks whose `clear` comments
        carry more than a threshold of distinct authors: the cutter cuts them,
        and the released list carries them. The failed held comment is in no
        batch and not in the list.
      - the gather — the walk's calls carry the shown week's comments, and nothing
        of either failed comment.

    **The mutations this kills:** v004's verdict condition left out (every reader
    shows or sends the failed comments); the gather keeping its own read of
    `answer` (the gather leg); the cut reading `answer` rather than the view (the
    batch leg).
    """
    contract = comment_contract
    world = committed_comment_world
    threshold = contract.threshold()
    assert threshold >= 3, (
        f"The configured n-threshold is {threshold}; this world holds a two-comment week under it, "
        "which needs 3 or more."
    )
    world.build()
    for week in (HELD_A, HELD_B, HELD_AND_FAILED, SHOWN, SHOWN_AND_FAILED):
        world.close_week(week)

    held_a = nonces("HA", threshold - 1)
    held_b = nonces("HB", 2)
    shown = nonces("SH", threshold)
    beside_failed_held = nonces("BF", 1)
    beside_failed_shown = nonces("BS", threshold)
    failed_held, failed_shown = "E601FAILHELDQz", "E601FAILSHOWNQz"

    released_answers = plant(world, HELD_A, held_a) + plant(world, HELD_B, held_b)
    plant(world, HELD_AND_FAILED, beside_failed_held)
    plant(world, SHOWN, shown)
    plant(world, SHOWN_AND_FAILED, beside_failed_shown)
    failures = {
        failed_held: plant(world, HELD_AND_FAILED, [failed_held], moderation=UNMODERATED)[0],
        failed_shown: plant(world, SHOWN_AND_FAILED, [failed_shown], moderation=UNMODERATED)[0],
    }
    for nonce, answer in failures.items():
        week = HELD_AND_FAILED if nonce == failed_held else SHOWN_AND_FAILED
        closed_at = world.instants[week][1]
        world.failed_moderation(answer, attempted_at=closed_at + AN_HOUR_AFTER_THE_CLOSE)
    committed_rows.commit()

    def failed_texts() -> set[str]:
        return {comment_text(INSTRUCTOR_TOKEN, nonce) for nonce in failures}

    # Reader 1: the comment read.
    shown_week = texts_of(read(world, contract, SHOWN))
    assert shown_week == {comment_text(INSTRUCTOR_TOKEN, nonce) for nonce in shown}, (
        f"The shown week returned {sorted(shown_week)}; it holds {threshold} `clear` comments from "
        f"{threshold} distinct students. Until it is returned whole, the absence below is what this "
        "read gives every week."
    )
    for week in (HELD_AND_FAILED, SHOWN_AND_FAILED):
        leaked = texts_of(read(world, contract, week)) & failed_texts()
        assert not leaked, (
            f"`{contract.visible_name}` returned {sorted(leaked)} for term week {week}: a comment "
            "whose moderation call failed and which holds no verdict. E6-01 criterion 1."
        )

    # Readers 2 and 3: the cut, its batch, and the released list.
    cut = contract.cut()(world.session)
    committed_rows.commit()
    assert cut == 1, (
        f"`{contract.cut_name}` cut {cut} batches. Two closed held weeks carry "
        f"{len(released_answers)} `clear` comments from as many distinct students — every leg of "
        "the gate open — so there is a batch for the failed comment to be absent from."
    )
    members = committed_release_rows.released_answers()
    expected_members = {world.answer_key(answer) for answer in released_answers}
    assert expected_members <= members, (
        f"The batch does not hold the held weeks' verdicted comments: missing "
        f"{sorted(expected_members - members)}."
    )
    failed_keys = {world.answer_key(answer) for answer in failures.values()}
    assert not (members & failed_keys), (
        f"A comment with no moderation verdict is a release batch member: "
        f"{sorted(members & failed_keys)}. A batch cannot be un-released (ADR 0146), so this is "
        "an unmoderated comment shown for the rest of the term."
    )
    released_texts = texts_of(released(world, contract))
    assert (
        {comment_text(INSTRUCTOR_TOKEN, nonce) for nonce in held_a + held_b} <= released_texts
    ), f"`{contract.released_name}` answers {sorted(released_texts)}, without the batch it cut."
    assert not (released_texts & failed_texts()), (
        f"`{contract.released_name}` answers an unmoderated comment: "
        f"{sorted(released_texts & failed_texts())}."
    )

    # Reader 4: the gather.
    gateway = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=gateway)
    sent = "\n".join(gateway.prompts)
    assert all(nonce in sent for nonce in shown), (
        "The walk's calls do not carry the shown week's `clear` comments, so the absence below would "
        "be an absence from calls that carried nothing of this world."
    )
    reached = [nonce for nonce in failures if nonce in sent]
    assert not reached, (
        f"Comments whose moderation call failed reached the summary model: {reached}. A comment "
        "nobody has moderated is a comment nobody has checked for a self-harm disclosure, and a "
        "summary is never regenerated."
    )


def test_a_week_shows_nothing_until_its_last_verdict_lands_and_then_everything(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Decision 5 for the comment read, over three reads of one week.

    One closed week, `threshold + 2` commenters: `threshold` hold `clear`, two hold
    nothing. So the verdicted comments alone are enough to be shown — which is what
    makes this the test of the rule rather than of the threshold.

      1. **Two without a verdict** → the read returns `()`, the existing empty
         shape and no new payload member.
      2. **One verdict lands** → still `()`. `threshold + 1` comments now hold a
         verdict; a read that showed them would show the week twice, a comment
         short and then complete, and the difference is one student's comment
         (`docs/MISTAKES.md` entry 51).
      3. **The last verdict lands** → every comment of the week, at once.

    The third read is the present control for the first two: same world, same
    reader, same arguments.

    **The mutations this kills:** v004's verdict condition with no section-week
    rule (reads 1 and 2 return the verdicted comments — a partial set); the rule
    written as "most comments hold a verdict" (read 2); and a rule that never lets
    the week through (read 3).
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    world.build()
    world.close_week(SHOWN)
    verdicted = nonces("RV", threshold)
    waiting = nonces("RW", 2)
    plant(world, SHOWN, verdicted)
    late = plant(world, SHOWN, waiting, moderation=UNMODERATED)
    assert world.commenters_in(term_week=SHOWN, stream=INSTRUCTOR_STREAM) == threshold + 2

    first = read(world, contract, SHOWN)
    assert tuple(first) == (), (
        f"With two of its {threshold + 2} comments holding no moderation verdict, the week returned "
        f"{sorted(texts_of(first))}. A section-week shows no comment until every comment in it holds "
        "a verdict (E6-01, work order decision 5)."
    )

    world.verdict(late[0], CLEAR)
    second = read(world, contract, SHOWN)
    assert tuple(second) == (), (
        f"With one comment still waiting, the week returned {len(second)} comments. That is part "
        "of a week, and the next read — once the last verdict lands — differs from it by exactly "
        "the waiting student's comment."
    )

    world.verdict(late[1], CLEAR)
    third = texts_of(read(world, contract, SHOWN))
    expected = {comment_text(INSTRUCTOR_TOKEN, nonce) for nonce in verdicted + waiting}
    assert third == expected, (
        f"Every comment of the week now holds a verdict and the read returned {sorted(third)}; it "
        f"holds {sorted(expected)}. Once the last verdict lands the week is shown, all at once."
    )


def test_the_release_cut_skips_a_week_until_its_last_verdict_lands(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Decision 5 for the cut, over two cuts: a waiting week's comments join a later cut.

    Two closed held weeks. The first holds `threshold - 1` `clear` comments; the
    second holds one `clear` comment and one with no verdict. Counted per comment,
    the verdicted comments are `threshold` distinct authors over two weeks — all
    three legs open. Counted per section-week, the second week is not moderated and
    the cut skips it, leaving one week: no leg (c), no batch.

      1. **First cut** → nothing cut, nothing released.
      2. **The waiting verdict lands; second cut** → one batch holding every comment
         of both weeks.

    **The mutation this kills:** the cut filtering unverdicted comments one by one
    instead of skipping their week — it releases the second week's verdicted
    comment in the first cut, and the waiting comment, released later, is then
    alone in a batch with its week known. **The pair** is the second cut.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 2
    world.build()
    world.close_week(HELD_A)
    world.close_week(HELD_B)
    first_week = plant(world, HELD_A, nonces("CA", threshold - 1))
    second_week = plant(world, HELD_B, nonces("CB", 1))
    waiting = plant(world, HELD_B, nonces("CW", 1), moderation=UNMODERATED)
    assert world.commenters_in(term_week=HELD_A, stream=INSTRUCTOR_STREAM) == threshold - 1
    assert world.commenters_in(term_week=HELD_B, stream=INSTRUCTOR_STREAM) == 2

    early = contract.cut()(world.session)
    assert early == 0 and release_rows.members() == [], (
        f"`{contract.cut_name}` cut {early} batch(es), releasing {release_rows.members()}, while one "
        "of the two held weeks still had a comment with no verdict. That week is not moderated and "
        "the cut skips it; its comments join a later cut (E6-01, work order decision 5)."
    )

    world.verdict(waiting[0], CLEAR)
    later = contract.cut()(world.session)
    assert later == 1, (
        f"With the last verdict landed, `{contract.cut_name}` cut {later} batch(es). Both weeks are "
        f"moderated and their comments carry {threshold + 1} distinct authors over two weeks."
    )
    expected = {world.answer_key(answer) for answer in first_week + second_week + waiting}
    assert release_rows.released_answers() == expected, (
        f"The batch holds {sorted(release_rows.released_answers())}; both weeks' comments, all of "
        f"them, are {sorted(expected)}."
    )
