"""Which of a week's comments reach the model — ticket E4-06.

The ticket's scope: "per stream, gather the week's comments (under-threshold
included, **moderation-held excluded** — vacuously today, structurally forever)".
SPEC §5.1 says it of the summary itself: the summaries "exclude flagged-held
content". §5.2 is where the states come from and E6 is what writes them; E4 writes
none at all (ADR 0145 — the initial state is the absence of a row), so **every
`moderation_state` row in this module is planted by the test**.

That is the whole reason this module exists rather than being deferred to E6.
"Vacuously today" is how a filter comes to be written as a convention and
discovered missing two epics later, when a comment an instructor excluded is
already sitting inside a generated summary — and a summary is not regenerated
(breakdown decision 2), so it stays there. Planting the rows now makes the filter
a behaviour with a test rather than a sentence in a scope.

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

**And there is a third subject in here, which is not a filter but an alarm on the
one this filter does not have.** SPEC §5.2's last bullet routes threat and
self-harm classifications *around* the moderation lifecycle entirely — they go
straight to Care (§6.2) and are "never shown to the instructor" — so a comment in
that class never acquires a `moderation_state` row at all, and the filter above,
which reads an absent row as published, would send it to the provider. That is not
a defect today and cannot be: `ClassificationTask` has one member and nothing
writes a harm verdict. It becomes one the moment E6's classifier does. The last
test in this module is the tripwire that fires first, and its docstring carries the
instruction.

**Which failure a red here is.** Before E4-06 lands, expected red on
`pytest.fail` naming `app.jobs.tasks` as a module with no
`generate_weekly_summaries`; before E4-02, on the `moderation_state` table. Both
are plain calls in a test body (`docs/MISTAKES.md` entry 44). The tripwire is
green today and is required to be.
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    INSTRUCTOR_COMMENT_POSITION,
    INSTRUCTOR_STREAM,
    StreamAwareGateway,
    SummaryWorld,
    comment_text,
)

pytestmark = pytest.mark.integration

# The module the classification vocabulary lives in, and the one member it has
# today. **Written out here rather than read off the enum** (`docs/MISTAKES.md`
# entry 19): an expectation taken from the thing it checks agrees with it whatever
# either says, and the whole point of the assertion below is to notice the enum
# changing.
CLASSIFICATION_MODELS_MODULE = "app.models.ai"
CLASSIFICATION_TASK_ENUM = "ClassificationTask"
CLASSIFICATION_TASKS_TODAY = frozenset({"COMMENT_VALIDITY"})

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

    # `UNDECIDED` gets no row at all: ADR 0145 makes the absence of a row the
    # initial state, and that is the state every comment in shipped E4 is in.
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
        is the absence of a row, which is the state every comment in shipped E4 is
        in. A filter written as an inner join to the record sends nothing at all,
        and would pass a test that only asserted the two exclusions.
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


def test_no_harm_classification_task_exists_yet_for_this_filter_to_have_missed(
    summary_contracts: Any,
) -> None:
    """The tripwire on the exclusion this gather does **not** have. Green today, and required to be.

    **What the gap is.** SPEC §5.2's last bullet: "Threat/self-harm classifications
    bypass this flow entirely (§6.2) and are never shown to the instructor." Bypass
    the flow means bypass the record: a comment routed to Care never acquires a
    `moderation_state` row, because no moderator ever decided anything about it.
    The filter this module's other tests measure reads an absent row as published —
    ADR 0145's absence rule, and correct for every state that exists — so the day a
    harm classifier writes its first verdict, the one class of comment §6.2 keeps
    furthest from an instructor becomes the one class this walk sends to the
    provider and paraphrases into instructor-visible prose. Generation is
    once-and-done (E4's breakdown decision 2), so it stays there for the term.

    **Why the answer is this test and not a filter.** There is no harm vocabulary
    to filter on. `ClassificationTask` has exactly one member and nothing in the
    system writes a harm verdict, so a predicate written now would be a guess at an
    enum E6 has not designed — asserted against nothing, unfalsifiable, and
    `docs/MISTAKES.md` entry 24's shape (a test asserting a property no
    implementation can satisfy). What can be made mechanical is the *precondition*
    of the deferral: while the vocabulary has one member the gap cannot fire, and
    the moment it gains a second it can. So the deferral is recorded with an owner
    in `docs/tickets/e4/deferred.md` (owner E6) and this is the alarm that goes off
    before, rather than after, the thing it is about becomes reachable.

    **This is a §6.2 confidentiality tripwire, not enum bookkeeping**, and the
    difference is what the red means. A test that merely pinned an enum would be
    satisfied by anyone editing the expected set to match reality — that is the
    ordinary way an inventory test is resolved. Here that resolution is the defect:
    widening `CLASSIFICATION_TASKS_TODAY` makes this green while leaving a
    self-harm disclosure on the path to a model and to a paraphrase an instructor
    reads. **When this reds, the repair is in the gather**, in
    `docs/tickets/e4/deferred.md`'s terms, and it lands *before* the classifier
    writes its first verdict — not in the same pull request as the classifier, and
    not after it.

    **The mutation it kills:** a second `ClassificationTask` member — a moderation
    or harm task — added with no change to the summary gather. That is a diff no
    other test in this repository has anything to say about: it adds a vocabulary,
    breaks nothing, and silently widens what crosses to the provider.

    **The near miss it must not be resolved by:** this test's own set widened to
    match the enum. It is written as a literal at the top of this module rather
    than derived from `ClassificationTask` for exactly that reason
    (`docs/MISTAKES.md` entry 19) — a set read off the thing it checks agrees with
    it whatever either says — and the failure message says so in as many words, so
    the cheap fix cannot be made without reading why it is wrong.

    **Not marked `invariant`, deliberately, and the reason is what the marker
    means.** SPEC §4.1 is seven enumerated visibility rules and this is not one of
    them; `tests/integration/test_application_role_privileges.py` draws the same
    line for the same reason ("preconditions for the §4.1 invariants rather than
    instances of them"). More decisively, every test in that pass asserts a
    *denial* — a query refused, a column unreadable — and this asserts an
    inventory. Marking it would put a claim in the isolated §4.1 pass that the §6.2
    exclusion is enforced, and it is not: it is deferred, with this as the alarm.
    What replaces the marker's protection is that the assertion is unconditional
    and an equality — no skip path, no xfail, no floor — in a module CI runs on
    every pull request.

    **The token the schema stores is pinned elsewhere** and is not this test's
    subject: `COMMENT_VALIDITY_TASK` in `tests/fixtures/grading.py` carries it,
    held by ADR 0055's per-task `CHECK`. What is asserted here is how many kinds of
    classification exist, which is the only fact the gap depends on.
    """
    module = summary_contracts.module(
        CLASSIFICATION_MODELS_MODULE,
        "SPEC §13 puts the classification rows there, and ADR 0055 gives them a `task` column "
        "typed as an enum with one member today.",
    )
    tasks = summary_contracts.named(
        module,
        CLASSIFICATION_TASK_ENUM,
        "ADR 0055 settles the classification vocabulary as an enum of tasks, with the verdict set "
        "closed per task by a check constraint.",
    )

    try:
        members = frozenset(member.name for member in tasks)
    except TypeError:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{CLASSIFICATION_MODELS_MODULE}.{CLASSIFICATION_TASK_ENUM}` is {tasks!r}, which does "
            "not enumerate its members. ADR 0055 settles the classification vocabulary as an enum; "
            "if it has become something else, this tripwire has to be rewritten around whatever "
            "now answers 'how many kinds of classification are there' — not deleted, because the "
            "§6.2 gap it watches is unchanged."
        )
    assert members, (
        f"`{CLASSIFICATION_MODELS_MODULE}.{CLASSIFICATION_TASK_ENUM}` has no members at all, so "
        "the equality below holds of an empty enum and this tripwire is asserting nothing. "
        "Something is being read that is not the classification vocabulary."
    )
    assert members == CLASSIFICATION_TASKS_TODAY, (
        f"`{CLASSIFICATION_TASK_ENUM}` offers {sorted(members)} and this tripwire was written when "
        f"it offered {sorted(CLASSIFICATION_TASKS_TODAY)}.\n\n"
        "**Do not resolve this by editing the set above.** That is the near miss this test exists "
        "to refuse. A second classification task means a moderation or harm classifier is "
        "arriving, and SPEC §5.2's last bullet routes threat and self-harm classifications around "
        "the moderation lifecycle entirely — they reach Care (§6.2) and never acquire a "
        "`moderation_state` row. This walk's gather reads an absent row as published, so from the "
        "moment that classifier writes its first verdict the comments §6.2 keeps furthest from an "
        "instructor are the ones this job sends to a provider and paraphrases into a summary the "
        "instructor reads — and nothing regenerates a summary (E4's breakdown decision 2), so it "
        "stays there for the term.\n\n"
        "**The repair is in the gather, and it lands before the classifier does.** "
        "`docs/tickets/e4/deferred.md` carries the entry with its owner (E6) and its done-when: "
        "the summary gather excludes comments whose current classification is in the threat or "
        "self-harm set, asserted with a planted verdict of that class, before any writer of one "
        "exists. Widening the set here makes this test green and changes nothing about what "
        "crosses to the provider."
    )
