"""Which of a week's comments reach the model — tickets E4-06 and E6-01.

The ticket's scope: "per stream, gather the week's comments (under-threshold
included, **moderation-held excluded** — vacuously today, structurally forever)".
SPEC §5.1 says it of the summary itself: the summaries "exclude flagged-held
content". §5.2 is where the states come from and E6 is what writes them, so
**every `moderation_state` row in this module is planted by the test**.

**What is asserted is the prompt, not the row.** A summary's text is the model's
and this suite cannot read a held comment out of it; what it can say exactly is
which comments were *sent*. That is also the property that matters: the boundary
§5.1 draws is about what crosses to the provider.

**Two of the five comments are held and three feed, and the third is the near
miss.** A comment whose latest decision is `EXCLUDED` does not feed; a comment
whose `EXCLUDED` was superseded by a later `KEPT` does — that is §5.2's undo
("Keep for students" publishes it), and a filter written as "has an EXCLUDED row
anywhere" refuses it while passing every other assertion here. E4-02's record is
append-only precisely so that history exists (ADR 0145), and reading only the
latest row is the whole of what makes it usable.

**E6-01 replaced this module's tripwire with what the tripwire was waiting for.**
Until E6-01 the last test here pinned `ClassificationTask` to one member, because
SPEC §5.2's last bullet routes threat and self-harm classifications *around* the
moderation lifecycle (they reach Care, §6.2, and never acquire a
`moderation_state` row) and the gather then read an absent row as published — so
the day a moderation task arrived, the class of comment §6.2 keeps furthest from an
instructor would have been the one this job sent to a provider. E6-01 adds that
task, and its own instruction was that widening the tripwire's set is not the
repair. The repair is below, as planted verdicts:

  - a threat or self-harm comment never reaches the model, including when a later
    verdict on it is `clear` (E6-01's second criterion, the gather's leg);
  - a section-week with a comment that holds no verdict is not summarized at all,
    and the next walk after the verdict lands summarizes it whole (criterion 8,
    asserted over the sequence of walks — `docs/MISTAKES.md` entry 51);
  - the exit's three-response week: the definer opens a `threat_case` and the
    summary's call carries nothing of that comment (criterion 3's service half).

**Every comment here is routed a `clear` verdict by the world unless a test names
another** (`tests/fixtures/summary_job.py`), which is what keeps the two E4-06
tests meaningful under `report_comment` v004: an unverdicted comment would not
feed for a reason having nothing to do with `moderation_state`.

**Which failure a red here is.** Before E6-01 lands, every test fails in its own
body on `pytest.fail` naming `app.services.moderation.route_verdict` — the world
plants verdicts through it (`docs/MISTAKES.md` entry 44: a FAILED, not an ERROR).
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.moderation import (
    CLEAR,
    SELF_HARM,
    THREAT,
    UNMODERATED,
    moderation_verdicts,
    threat_cases,
)
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    INSTRUCTOR_COMMENT_POSITION,
    INSTRUCTOR_STREAM,
    StreamAwareGateway,
    SummaryWorld,
    comment_text,
)

# **Marked `invariant`, which puts this module in CI's isolated §4.1 pass** where a
# skip or an empty collection is a failure (`scripts/ci/check_invariants.py`).
# SPEC §5.1's "exclude flagged-held content" and §5.2's small-N concealment, which
# §4.1 item 3 is the general form of, and since E6-01 §6.2's "suppressed from all
# instructor and leadership views". A held comment fed to the model comes back
# paraphrased inside a summary the instructor reads — the suppression defeated one
# layer out, in prose nothing else in this suite inspects, and on a surface where
# the words no longer look like a comment. That the boundary is a prompt rather
# than a payload is exactly why it needs the pass that cannot be skipped.
pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The five comments, by the nonce each carries. Tokens that appear nowhere else
# in this repository, so finding one in a prompt is evidence and not a
# coincidence with the prompt template (`docs/MISTAKES.md` entry 3).
UNDECIDED = "Zx4TbMq7Lw"
LATEST_EXCLUDED = "Rj9NwPc2Vh"
EXCLUDED_THEN_KEPT = "Fm5KdYt8Bz"
LATEST_FLAGGED = "Gq2HsXn6Rd"
LATEST_PUBLISHED = "Wp7VbLk3Ty"

# How far after the window closes each planted decision was made. The two rows of
# the superseded comment are an hour apart, which is the whole subject of the
# near miss: the later one governs.
A_FIRST_DECISION = timedelta(hours=1)
A_LATER_DECISION = timedelta(hours=2)

# E6-01's planted-verdict worlds, by nonce. Same rule as above: tokens found
# nowhere else in the repository.
A_CARE_CLASS_COMMENT = "Vb3NqLp8Ws"
CLEAR_BESIDE_IT = ("Hd6RtYk2Mf", "Qc9ZwJn4Ux")
NOT_YET_MODERATED = ("Tz5GmWc7Pk", "Ry2LsFd9Nh")
MODERATED_BESIDE_THEM = "Kw8BvXq3Jt"
A_LATER_WEEKS_COMMENT = "Mn4CzHy6Ga"

# The verdict sequences E6-01's second criterion names, routed in order on one
# comment: each Care-class verdict alone, and each followed by a later `clear`.
# The second form is the near miss — "the latest verdict governs" is the rule for
# `moderation_state`, and carried over to Care-class verdicts it would publish a
# self-harm disclosure the moment a re-run answered `clear`. The criterion says
# "never when any of its verdicts, ever, is threat or self-harm".
CARE_SEQUENCES = {
    "threat": (THREAT,),
    "self-harm": (SELF_HARM,),
    "threat-then-clear": (THREAT, CLEAR),
    "self-harm-then-clear": (SELF_HARM, CLEAR),
}

# The week E6-01's gather-wait test pairs with the week under test. Inside cohort
# `Q`'s run (term weeks 7 to 18), so it closes after `A_CLOSED_TERM_WEEK` and both
# are closed when the clock stands after it.
A_LATER_CLOSED_TERM_WEEK = A_CLOSED_TERM_WEEK + 1


def a_week_with_five_decided_comments(world: SummaryWorld, contract: Any) -> None:
    """One section-week, five students, five instructor comments, four decisions planted."""
    world.build(contract.a_cohort)
    written = {
        nonce: world.respond(
            f"{nonce}-subject",
            cohort=contract.a_cohort,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=comment_text(INSTRUCTOR_STREAM, nonce),
        )
        for nonce in (
            UNDECIDED,
            LATEST_EXCLUDED,
            EXCLUDED_THEN_KEPT,
            LATEST_FLAGGED,
            LATEST_PUBLISHED,
        )
    }
    decided_at = world.closes_at(A_CLOSED_TERM_WEEK)

    def comment_of(nonce: str) -> Any:
        return written[nonce][INSTRUCTOR_COMMENT_POSITION]

    # `UNDECIDED` gets no `moderation_state` row at all: ADR 0145 makes the absence
    # of a row the initial state. It holds the `clear` moderation verdict the world
    # routes for every comment (E6-01), which is a classification and not a
    # decision, so it is still a comment nobody has decided anything about.
    world.decide(
        comment_of(LATEST_EXCLUDED), contract.excluded, decided_at=decided_at + A_FIRST_DECISION
    )
    world.decide(
        comment_of(LATEST_FLAGGED),
        contract.flagged_collapsed,
        decided_at=decided_at + A_FIRST_DECISION,
    )
    world.decide(
        comment_of(LATEST_PUBLISHED), contract.published, decided_at=decided_at + A_FIRST_DECISION
    )
    # The near miss: excluded, then kept. §5.2's undo, and the reason the record
    # is append-only rather than a column.
    world.decide(
        comment_of(EXCLUDED_THEN_KEPT), contract.excluded, decided_at=decided_at + A_FIRST_DECISION
    )
    world.decide(
        comment_of(EXCLUDED_THEN_KEPT), contract.kept, decided_at=decided_at + A_LATER_DECISION
    )

    world.clock_after(A_CLOSED_TERM_WEEK)
    world.commit()


def test_the_call_carries_the_comments_no_moderator_is_holding_and_none_of_the_ones_they_are(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The filter, with both sides of its boundary in one week and one call.

    Three comments feed the model and two do not, and every one of the five is in
    the same section-week — so a walk that sent all five, or none, or that filtered
    on the wrong column, fails on a named nonce rather than on a count.

      - **No `moderation_state` row at all → feeds.** ADR 0145: the initial state
        is the absence of a row. Since E6-01 the comment also holds the `clear`
        moderation verdict the world routes for it, which is what makes it a
        comment the view returns at all. A filter written as an inner join to the
        record sends nothing at all, and would pass a test that only asserted the
        two exclusions.
      - **Latest row `PUBLISHED` → feeds**, which is E6's explicit form of the
        same thing.
      - **Latest row `EXCLUDED` → does not feed.** §5.1: summaries exclude
        flagged-held content.
      - **Latest row `FLAGGED_COLLAPSED` → does not feed.** The state a comment
        sits in while it waits for review, which §5.2 hides from students and
        which is exactly the "held for review" §5.1 keeps out of the summary.
      - **`EXCLUDED` superseded by a later `KEPT` → feeds.** §5.2's undo: "Keep
        for students" publishes the comment. This is the near miss, and a filter
        asking "does this comment have an EXCLUDED row" refuses it while passing
        every other line above.

    **The prompt is asserted to be non-empty and to have been sent**, before
    anything is said about what is missing from it. An assertion that a held
    comment is absent is satisfied perfectly by a walk that made no call, which is
    what the tree this test is first run against does (`docs/MISTAKES.md` entry 3,
    and the reason the feeding comments are asserted first).

    **The mutations this kill:** the moderation filter omitted entirely ("no rows
    exist yet"), which the two held nonces catch; an inner join that drops every
    undecided comment, which `UNDECIDED` catches; a filter over the whole history
    rather than the latest row, which `EXCLUDED_THEN_KEPT` catches; and a filter
    that treats `KEPT` as a held state, which it catches from the other side.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    a_week_with_five_decided_comments(summary_world, summary_job_contract)
    gateway = StreamAwareGateway(summary_contracts)

    summary_job_contract.run(gateway=gateway)

    assert gateway.prompts, (
        "the walk made no model call at all for a closed week carrying five instructor comments, "
        "so there is no prompt to ask what fed it and every absence below would be an absence in "
        "nothing."
    )
    sent = "\n".join(gateway.prompts)

    fed = [nonce for nonce in (UNDECIDED, EXCLUDED_THEN_KEPT, LATEST_PUBLISHED) if nonce in sent]
    assert fed == [UNDECIDED, EXCLUDED_THEN_KEPT, LATEST_PUBLISHED], (
        f"only {fed} of the three comments no moderator is holding reached the model. A comment "
        "with no decision about it is published (ADR 0145's absence rule); one whose latest "
        "decision is `PUBLISHED` plainly is; and one whose `EXCLUDED` was superseded by a later "
        "`KEPT` is §5.2's undo — 'Keep for students' publishes the comment. A filter that reads "
        "the whole history rather than the latest row drops the third of those, and §4 makes the "
        "summary the only comment signal an instructor gets in a thin week."
    )

    held = [nonce for nonce in (LATEST_EXCLUDED, LATEST_FLAGGED) if nonce in sent]
    assert not held, (
        f"the prompt carries {held}, which a moderator is holding. SPEC §5.1: the summaries "
        "'exclude flagged-held content'. A held comment inside a generated summary cannot be taken "
        "out again — breakdown decision 2 rules out regeneration entirely — so the sentence an "
        "instructor reads keeps whatever was excluded, for the whole term."
    )


def test_a_held_comment_does_not_change_the_response_count_the_summary_states(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The count is about responses, and moderation is about comments.

    SPEC §5.1's sentence — "state the response count they draw from" — is about
    the week's responses, and E4-06's work order settles it as the count of
    `response` rows for the section-week. A moderator holding two comments has not
    made two students disappear: the week still had five respondents, and the
    rating distributions on the same report are computed over all five.

    **This is the other half of the filter**, and it is where a plausible mistake
    lands: a walk that filtered the comments and then counted what it had left
    would state three, which is a smaller, believable, wrong number under a
    summary — and the only reader who could catch it is the instructor, who cannot.

    **The mutation this kills:** `response_count=len(feeding_comments)` written
    after the moderation filter, which is exactly where the two are adjacent in
    any implementation of this walk.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    a_week_with_five_decided_comments(summary_world, summary_job_contract)
    responders = 5
    held_back = 2

    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))

    by_stream = summary_world.summaries_by_stream(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    stored = by_stream.get(summary_job_contract.stored_instructor)
    assert stored is not None, (
        f"the walk wrote {sorted(by_stream)} and no instructor summary, so there is no count to "
        "read."
    )
    assert stored[summary_job_contract.response_count_column] == responders, (
        f"the summary states {stored[summary_job_contract.response_count_column]} responses over a "
        f"week of {responders}, {held_back} of whose comments a moderator is holding. The count is "
        f"the week's responses; {responders - held_back} is the number of comments that fed the "
        "call, and a summary that states it tells the instructor their week was thinner than it "
        "was."
    )


# ---------------------------------------------------------------------------
# E6-01 — the planted-verdict tests that replace the tripwire.
# ---------------------------------------------------------------------------


def answer_key(world: SummaryWorld, written: dict[int, Any]) -> Any:
    """The `answer` key of the instructor comment one `respond` call wrote."""
    return written[INSTRUCTOR_COMMENT_POSITION][world.world.key_of("answer")]


def summaries_for_week(world: SummaryWorld, *, cohort: str, term_week: int) -> list[dict[str, Any]]:
    """Every stored summary of one section-week, read on a connection that sees commits."""
    week = world.week_id(term_week)
    return [
        row
        for row in world.summaries(section_id=world.section_id(cohort))
        if str(row["week_id"]) == str(week)
    ]


@pytest.mark.parametrize("sequence", list(CARE_SEQUENCES.values()), ids=list(CARE_SEQUENCES))
def test_a_threat_or_self_harm_comment_is_never_sent_to_the_model(
    sequence: tuple[str, ...],
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """E6-01 criterion 2, the gather's leg: a Care-class comment never reaches the provider.

    One closed section-week, three instructor comments. Two hold a `clear`
    verdict; the third holds the Care-class sequence this case names, routed
    through the definer in order. The job runs with a double that records every
    prompt.

    **The controls, asserted first.** A call was made, and both `clear` comments of
    the same week are in it. So the week was walked, it was not held back as
    unmoderated (every comment in it holds a verdict), and the gather is reading
    comments at all — an absence in a walk that sent nothing would be an absence in
    nothing (`docs/MISTAKES.md` entry 3). And the Care-class comment is read back
    holding exactly the verdicts planted, so the case under test is the one named.

    **The assertion.** The Care-class comment's nonce is in no prompt.

    **The mutations this kills:** `report_comment` v004 written with the verdict
    condition and without the Care-class exclusion (every case); the exclusion
    written against the *latest* moderation verdict rather than any verdict ever
    (the two `-then-clear` cases); and the gather keeping its own copy of the
    comment read instead of reading the view (every case, because the copy has no
    Care-class rule). **The near miss it must not be resolved by:** excluding the
    comment by giving it no verdict — the read-back control fails first.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    cohort = summary_job_contract.a_cohort
    summary_world.build(cohort)
    care = summary_world.respond(
        "e6-01-care-class-subject",
        cohort=cohort,
        term_week=A_CLOSED_TERM_WEEK,
        instructor_comment=comment_text(INSTRUCTOR_STREAM, A_CARE_CLASS_COMMENT),
        instructor_moderation=sequence,
    )
    for index, nonce in enumerate(CLEAR_BESIDE_IT):
        summary_world.respond(
            f"e6-01-clear-subject-{index}",
            cohort=cohort,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=comment_text(INSTRUCTOR_STREAM, nonce),
        )
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    held = sorted(
        row["verdict"]
        for row in moderation_verdicts(summary_world.rows.session, answer_key(summary_world, care))
    )
    assert held == sorted(sequence), (
        f"The Care-class comment holds the moderation verdicts {held}; this case planted "
        f"{list(sequence)} through the definer. Until it holds them, the absence below says nothing "
        "about Care-class verdicts."
    )

    gateway = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=gateway)

    assert gateway.prompts, (
        "The walk made no model call for a closed week carrying three verdicted instructor "
        "comments, so there is no prompt to search and the absence below would be an absence in "
        "nothing."
    )
    sent = "\n".join(gateway.prompts)
    missing = [nonce for nonce in CLEAR_BESIDE_IT if nonce not in sent]
    assert not missing, (
        f"The `clear` comments {missing} of the same section-week did not reach the model. Every "
        "comment of the week holds a verdict, so the week is moderated and is summarized whole; a "
        "Care-class verdict is a verdict, and must not hold the rest of its week back."
    )
    assert A_CARE_CLASS_COMMENT not in sent, (
        f"A comment holding the moderation verdicts {list(sequence)} reached the summary model. "
        "SPEC §6.2: threat-of-harm and self-harm comments are 'routed here immediately and "
        "suppressed from all instructor and leadership views', and a summary is an instructor view "
        "of the week's comments in the model's words. E6-01: a comment never appears when any of "
        "its verdicts, ever, is threat or self-harm — a later `clear` does not publish it."
    )


def test_a_section_week_is_summarized_only_once_its_last_verdict_has_landed(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """E6-01 criterion 8, over three walks: the gather waits, never summarizes a part, then runs.

    One closed section-week holds three instructor comments: one verdicted, two
    holding no verdict. A second closed week of the same section is fully
    verdicted and is the control. Then three walks, with a verdict landing between
    each:

      1. **No verdicts on two of three.** The control week is summarized and its
         comment fed; the week under test has no `weekly_summary` row at all.
      2. **One verdict of the two lands.** Still no row. A walk that summarized the
         two comments now holding verdicts would write a summary of part of a
         week, and — because summaries are written once and never regenerated
         (E4's breakdown decision 2) — the third comment would never reach a
         summary at all. This is the step a per-comment filter fails.
      3. **The last verdict lands.** The week is summarized, and its call carries
         all three comments.

    That is the work order's decision 5 for the gather: before every verdict lands
    a reader sees nothing of that week's comments, after it, all at once
    (`docs/MISTAKES.md` entries 50 and 51 — the property is over the sequence of
    walks, not one walk).

    **The mutations this kills:** no wait at all (walk 1 summarizes the week with
    the verdicted comment); a wait that counts verdicted comments rather than
    requiring every comment to hold one (walk 2); a wait that never ends because
    it counts a comment the view does not show, or because the walk does not
    revisit an unsummarized week (walk 3).
    """
    summary_job_contract.require_table(summary_world.world.tables)
    cohort = summary_job_contract.a_cohort
    summary_world.build(cohort)

    waiting = [
        summary_world.respond(
            f"e6-01-waiting-subject-{index}",
            cohort=cohort,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=comment_text(INSTRUCTOR_STREAM, nonce),
            instructor_moderation=UNMODERATED,
        )
        for index, nonce in enumerate(NOT_YET_MODERATED)
    ]
    summary_world.respond(
        "e6-01-moderated-subject",
        cohort=cohort,
        term_week=A_CLOSED_TERM_WEEK,
        instructor_comment=comment_text(INSTRUCTOR_STREAM, MODERATED_BESIDE_THEM),
    )
    summary_world.respond(
        "e6-01-later-week-subject",
        cohort=cohort,
        term_week=A_LATER_CLOSED_TERM_WEEK,
        instructor_comment=comment_text(INSTRUCTOR_STREAM, A_LATER_WEEKS_COMMENT),
    )
    summary_world.clock_after(A_LATER_CLOSED_TERM_WEEK)
    summary_world.commit()

    # Walk 1.
    first = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=first)
    assert summaries_for_week(summary_world, cohort=cohort, term_week=A_LATER_CLOSED_TERM_WEEK), (
        f"The walk wrote no summary for term week {A_LATER_CLOSED_TERM_WEEK}, whose one comment "
        "holds a verdict. That week is this test's control: until it is summarized, the absence of "
        "a summary for the week under test is what this walk does to every week."
    )
    assert A_LATER_WEEKS_COMMENT in "\n".join(
        first.prompts
    ), "The control week was summarized and its verdicted comment is not in any prompt."
    after_first = summaries_for_week(summary_world, cohort=cohort, term_week=A_CLOSED_TERM_WEEK)
    assert not after_first, (
        f"The walk summarized term week {A_CLOSED_TERM_WEEK} while two of its three comments held no "
        f"moderation verdict: it wrote {[row['stream'] for row in after_first]}. A section-week is "
        "not summarized until every comment in it holds a verdict (E6-01 criterion 8)."
    )
    leaked = [
        nonce
        for nonce in (*NOT_YET_MODERATED, MODERATED_BESIDE_THEM)
        if nonce in "\n".join(first.prompts)
    ]
    assert not leaked, f"Comments of the waiting week reached the model in walk 1: {leaked}."

    # Walk 2: one of the two verdicts lands.
    summary_world.verdict(waiting[0][INSTRUCTOR_COMMENT_POSITION], CLEAR)
    summary_world.commit()
    second = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=second)
    after_second = summaries_for_week(summary_world, cohort=cohort, term_week=A_CLOSED_TERM_WEEK)
    assert not after_second, (
        f"With two of the week's three comments verdicted and one still waiting, the walk "
        f"summarized term week {A_CLOSED_TERM_WEEK} ({[row['stream'] for row in after_second]}). "
        "That summary is of part of a week and is never regenerated, so the waiting comment never "
        "reaches a summary — and a reader who sees this week's summary now and its comments later "
        "has two views that differ by exactly one comment (`docs/MISTAKES.md` entry 51)."
    )

    # Walk 3: the last verdict lands.
    summary_world.verdict(waiting[1][INSTRUCTOR_COMMENT_POSITION], CLEAR)
    summary_world.commit()
    third = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=third)
    after_third = summaries_for_week(summary_world, cohort=cohort, term_week=A_CLOSED_TERM_WEEK)
    assert after_third, (
        f"Every comment of term week {A_CLOSED_TERM_WEEK} now holds a verdict and the next walk "
        "wrote no summary for it. The wait has to end: E6-01 criterion 8, 'once the verdict lands, "
        "the next walk summarizes it'."
    )
    sent = "\n".join(third.prompts)
    absent = [nonce for nonce in (*NOT_YET_MODERATED, MODERATED_BESIDE_THEM) if nonce not in sent]
    assert not absent, (
        f"The walk that summarized term week {A_CLOSED_TERM_WEEK} did not send {absent}. Once every "
        "verdict has landed the week is summarized whole, all at once."
    )


def test_the_exits_three_response_week_opens_a_case_and_sends_the_model_nothing_of_it(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """E6-01 criterion 3, the service half: a self-harm comment in a 3-response week.

    The E6 exit's own world: three students answer a week, one of them writes a
    comment the moderator classifies `self_harm`, the other two `clear`. Routed
    through the definer, as every verdict is.

      - **The route.** Exactly one `threat_case` row names the self-harm comment,
        and it names the classification row that holds the verdict; the two
        `clear` comments have none (the pair: the definer opens a case for a
        Care-class verdict and only for one).
      - **The summary.** The week is summarized — a Care-class verdict is a verdict,
        so the week is moderated — and the call carries the two `clear` comments
        and nothing of the self-harm one.

    The payload half — what the instructor's report carries — is
    `tests/integration/test_a_care_class_comment_reaches_no_reader.py`.

    **The mutations this kills:** a definer that writes the verdict and no case
    (or a case for every verdict); a case naming the wrong classification; and any
    gather that sends a Care-class comment (see the test above).
    """
    summary_job_contract.require_table(summary_world.world.tables)
    cohort = summary_job_contract.a_cohort
    summary_world.build(cohort)
    disclosed = summary_world.respond(
        "e6-01-self-harm-subject",
        cohort=cohort,
        term_week=A_CLOSED_TERM_WEEK,
        instructor_comment=comment_text(INSTRUCTOR_STREAM, A_CARE_CLASS_COMMENT),
        instructor_moderation=SELF_HARM,
    )
    beside = [
        summary_world.respond(
            f"e6-01-exit-clear-subject-{index}",
            cohort=cohort,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=comment_text(INSTRUCTOR_STREAM, nonce),
        )
        for index, nonce in enumerate(CLEAR_BESIDE_IT)
    ]
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    session = summary_world.rows.session
    disclosed_key = answer_key(summary_world, disclosed)
    cases = threat_cases(session, disclosed_key)
    verdicts = moderation_verdicts(session, disclosed_key)
    assert len(cases) == 1, (
        f"The self-harm comment carries {len(cases)} `threat_case` rows. The routing definer opens "
        "exactly one for a threat or self-harm verdict, in the same call that writes the verdict "
        "(work order decision 2); none means the comment reached nobody — not the instructor, and "
        "not Care either."
    )
    assert [row["id"] for row in verdicts] == [cases[0]["classification_id"]], (
        f"The case names classification {cases[0]['classification_id']}, and the comment's "
        f"moderation verdicts are {[(row['id'], row['verdict']) for row in verdicts]}. The case is "
        "opened by the verdict that routed it, and says which one."
    )
    for written in beside:
        assert not threat_cases(session, answer_key(summary_world, written)), (
            "A `clear` comment of the same week has a `threat_case`. The definer opens a case for a "
            "threat or self-harm verdict and for nothing else."
        )

    gateway = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=gateway)
    assert summaries_for_week(summary_world, cohort=cohort, term_week=A_CLOSED_TERM_WEEK), (
        "The three-response week was not summarized. Every comment in it holds a verdict, so it is "
        "moderated; a week held back forever by its Care-class comment is a week whose instructor "
        "never gets the summary §5.1 promises a thin week."
    )
    sent = "\n".join(gateway.prompts)
    assert all(nonce in sent for nonce in CLEAR_BESIDE_IT), (
        "The week was summarized and its two `clear` comments are not both in the call, so the "
        "absence below would be an absence from a call that carried nothing."
    )
    assert A_CARE_CLASS_COMMENT not in sent, (
        "The self-harm comment of the exit's three-response week reached the summary model, and a "
        "summary of a three-response week is exactly the surface a reader can attribute."
    )
