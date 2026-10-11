"""The on-behalf draft refuses what the instructor's draft refuses — E7-10 done-when 1.

> **The on-behalf draft refuses what the instructor's does** (invariant-coverage
> HIGH). Invariant-marked tests drive the on-behalf draft past +96h with a
> scripted draft lifting a run of an excluded, a still-flagged and a held-stream
> comment: each refused, no row written, beside an accepted control lifting a
> published comment. The same pair for a count stated beside a held stream. The
> on-behalf gather and prompt carry no comment and no count on a held theme.

Until E7-10 only the instructor's draft door was driven with a lifting draft
(`test_a_draft_quoting_a_hidden_comment_is_refused.py`,
`test_a_draft_stating_a_count_beside_a_held_stream_is_refused.py`). The lead's
on-behalf draft is published to every student of the section too (SPEC §5.3), so
a hidden comment's words in it reach exactly the readers SPEC §4.1 item 3 and
§5.2 withhold them from.

**The world.** Lead A, course week 1 of `F1WW` required and unanswered, the clock
past +96h. The comments are E7-04's planted texts (`tests/fixtures/response_draft.py`),
each lifted run forty-odd characters of its own comment and under twenty of every
other, which that file's own control measures — so a refusal is about the comment
it lifts and nothing else. The exclusion is the teacher's, through E6-03's route;
the stored summaries are dated one second after it, so the summary filter
(E7-03 done-when 10) serves them and the prompt canaries below are not withheld
for an unrelated reason. Which stream is held and what state each comment is in
are read off the teacher's own report (`docs/MISTAKES.md` entry 58), never assumed.

**The refusal's status.** The instructor's draft answers a refused model answer
with 502 and one fixed sentence (E7-04 decision 2), and E7-10 done-when 9 has
"the 502 sentence and status defined once", so the on-behalf draft is held to the
same pair.

**Which failure a red is.** On the epic head the refusal tests are expected to
FAIL on the status (the scripted draft served 2xx) if the on-behalf draft does
not run the guards, and the prompt test on the held theme's count if its gather
renders it. If the on-behalf route already refuses, those reds are green and the
module is the missing coverage the boundary review named.
"""

from datetime import datetime
from typing import Any

import pytest
from fixtures.instructor_decisions import EXCLUDED, FLAGGED, PUBLISHED
from fixtures.moderation import HARMFUL
from fixtures.report_api import COMMENT_STATUS_FIELD, FULL_WEEK_COMMENTS
from fixtures.report_comments import configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.response_draft import (
    A_PLAIN_DRAFT,
    ALLOWED_CLAUSES,
    COUNTING_CLAUSES,
    EXCLUDED_COMMENT,
    FLAGGED_COMMENT,
    HELD_COMMENT,
    HELD_SUMMARY_RESPONSES,
    HELD_SUMMARY_TEXT,
    HELD_THEME,
    HELD_THEME_COUNT,
    ORDINARY_SUMMARY_VERSION,
    PUBLISHED_COMMENT,
    RUN_OF,
    SHOWN_SUMMARY_RESPONSES,
    SHOWN_SUMMARY_TEXT,
    SHOWN_THEME_A,
    SHOWN_THEME_A_COUNT,
    SMALL_N_SUMMARY_VERSION,
    THE_GUARD_BOUND,
    UNUSABLE_ANSWER_STATUS,
    a_draft_lifting,
    a_draft_saying,
    assert_the_planted_texts_are_what_this_file_says,
    carries_number,
    check_answer,
    draft_answer,
    longest_shared_run,
    registered_sentence_in,
    stored_themes,
    strings_in,
)
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    ON_BEHALF_AFTER,
    ON_BEHALF_CHECK,
    ON_BEHALF_DRAFT,
    ON_BEHALF_WEEK,
    ONE_SECOND,
    LoopWorld,
    OnBehalfDoor,
)
from fixtures.summary_job import (
    SUMMARY_GENERATED_AT_COLUMN,
    SUMMARY_MODEL_ID_COLUMN,
    SUMMARY_PROMPT_VERSION_COLUMN,
    SUMMARY_RESPONSE_COUNT_COLUMN,
    SUMMARY_SECTION_COLUMN,
    SUMMARY_STREAM_COLUMN,
    SUMMARY_TEXT_COLUMN,
    SUMMARY_THEMES_COLUMN,
    SUMMARY_WEEK_COLUMN,
    WEEKLY_SUMMARY_TABLE,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# What the teacher's report says of each planted comment (E4-04's spellings);
# `None` is "not on the report", which is a held stream's comment.
STATE_ON_THE_REPORT = {
    PUBLISHED_COMMENT: PUBLISHED,
    EXCLUDED_COMMENT: EXCLUDED,
    FLAGGED_COMMENT: FLAGGED,
    HELD_COMMENT: None,
}

WHY_HIDDEN = {
    EXCLUDED_COMMENT: "excluded by its instructor (SPEC §5.2)",
    FLAGGED_COMMENT: "still flagged, so hidden from students (SPEC §5.2)",
    HELD_COMMENT: "in a stream held below the n-threshold (SPEC §4.1 item 3)",
}

# The extra course-stream commenters a shown week needs, written so that no draft
# here shares a long run with them (asserted in `drafted`).
A_COURSE_COMMENTER = "E7-10 course commenter {index}: the lab notes were posted promptly enough"


def plant_a_summary(
    world: LoopWorld,
    *,
    stream: str,
    text: str,
    themes: Any,
    prompt_version: str,
    response_count: int,
    generated_at: datetime,
) -> None:
    """One stored summary for the on-behalf week of `F1WW`, its `generated_at` named.

    `LoopWorld.plant_summary` with the stream and the prompt version as
    parameters, because this module needs the held course stream's `summary.v3`
    row as well as the instructor stream's (copied, `docs/MISTAKES.md` entry 37).
    """
    world.draft.world.seed(
        WEEKLY_SUMMARY_TABLE,
        {},
        **{
            SUMMARY_SECTION_COLUMN: world.hold.taught,
            SUMMARY_WEEK_COLUMN: world.hold.week_id(ON_BEHALF_WEEK),
            SUMMARY_STREAM_COLUMN: stream,
            SUMMARY_TEXT_COLUMN: text,
            SUMMARY_RESPONSE_COUNT_COLUMN: response_count,
            SUMMARY_THEMES_COLUMN: stored_themes(themes),
            SUMMARY_PROMPT_VERSION_COLUMN: prompt_version,
            SUMMARY_MODEL_ID_COLUMN: "e7-10-a-stored-summary-model",
            SUMMARY_GENERATED_AT_COLUMN: generated_at,
        },
    )
    world.draft.door.commit()


def the_week_for_the_lead(world: LoopWorld, *, course_commenters: int = 1) -> None:
    """Course week 1 of `F1WW`, required, past +96h, every kind of comment planted.

    `course_commenters` is how many comments the course stream holds: one (held)
    by default, the configured threshold for the shown twin. Read off the
    teacher's report before anything is asked of the lead.
    """
    assert_the_planted_texts_are_what_this_file_says()
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)
    world.a_comment(PUBLISHED_COMMENT)
    world.a_comment(EXCLUDED_COMMENT)
    world.a_comment(FLAGGED_COMMENT, verdict=HARMFUL)
    world.a_comment(HELD_COMMENT, stream=COURSE_STREAM)
    for index in range(1, course_commenters):
        world.a_comment(A_COURSE_COMMENTER.format(index=index), stream=COURSE_STREAM)
    after_every_removal = world.exclude(EXCLUDED_COMMENT) + ONE_SECOND
    held = course_commenters < configured_threshold()
    plant_a_summary(
        world,
        stream=INSTRUCTOR_STREAM,
        text=SHOWN_SUMMARY_TEXT,
        themes=((SHOWN_THEME_A, SHOWN_THEME_A_COUNT),),
        prompt_version=ORDINARY_SUMMARY_VERSION,
        response_count=SHOWN_SUMMARY_RESPONSES,
        generated_at=after_every_removal,
    )
    plant_a_summary(
        world,
        stream=COURSE_STREAM,
        text=HELD_SUMMARY_TEXT,
        themes=((HELD_THEME, HELD_THEME_COUNT),),
        prompt_version=SMALL_N_SUMMARY_VERSION if held else ORDINARY_SUMMARY_VERSION,
        response_count=HELD_SUMMARY_RESPONSES if held else course_commenters,
        generated_at=after_every_removal,
    )
    body = world.draft.assert_the_streams_are(instructor_held=False, course_held=held)
    if not held:
        return
    for comment, expected in STATE_ON_THE_REPORT.items():
        card = world.draft.decisions.card(body, world.draft.planted[comment])
        state = None if card is None else card.get(COMMENT_STATUS_FIELD)
        assert state == expected, (
            f"The teacher's report shows {comment!r} as {state!r}; this module needs {expected!r} "
            "(None: not on the report, as a held stream's comment is not). A broken world, not a red."
        )


def ask_on_behalf(world: LoopWorld, door: OnBehalfDoor, body: Any) -> Any:
    """Lead A's request to one on-behalf door for `F1WW`, with whatever the provider was scripted.

    `LoopWorld.on_behalf` scripts a usable answer of its own first, which would
    overwrite the lifting draft a test has just scripted; so the URL is built here.
    """
    url = world.on_behalf_url(door, section_id=world.hold.taught, course_week=ON_BEHALF_WEEK)
    return world.ask(door.method, url, token=world.lead.token, json=body)


def drafted(world: LoopWorld, draft: str) -> Any:
    """Script the model to answer `draft`, and ask lead A's on-behalf draft; required to reach the model."""
    world.provider.script(draft_answer(draft))
    before = world.model_calls()
    answered = ask_on_behalf(world, ON_BEHALF_DRAFT, {})
    assert world.model_calls() > before, (
        f"Lead A's on-behalf draft answered {answered.status_code} without asking the model, so its "
        f"answer is not a verdict on the scripted draft. Body {answered.text[:300]!r}."
    )
    return answered


def served_strings(answered: Any, what: str) -> list[str]:
    """Every string a 2xx on-behalf draft answer carries (its members are not this file's to name)."""
    assert (
        200 <= answered.status_code < 300
    ), f"{what} answered {answered.status_code}. Body {answered.text[:400]!r}."
    return strings_in(answered.json())


def every_comment_text(world: LoopWorld) -> list[str]:
    """Every comment this world holds for the week, and every lifted run."""
    return [*world.draft.planted, *FULL_WEEK_COMMENTS, *RUN_OF.values()]


# ---------------------------------------------------------------------------
# The lift, three ways refused and once accepted.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hidden",
    (EXCLUDED_COMMENT, FLAGGED_COMMENT, HELD_COMMENT),
    ids=("excluded", "still-flagged", "held-stream"),
)
def test_an_on_behalf_draft_reusing_a_run_of_a_hidden_comment_is_refused_and_writes_no_row(
    response_loop: LoopWorld, hidden: str
) -> None:
    """Lead A's draft past +96h lifts forty-odd characters of a hidden comment: 502, one sentence, no row.

    **The mutations this kills, one per parameter:** the on-behalf draft route
    serving the model's text without `_reused_run` (all three pass); a comparison
    set built without the excluded leg, the flagged leg, or the held-stream leg;
    the on-behalf path calling the instructor's guards with a gather that
    collected no hidden comments ("the lead never read them"). **The near miss:**
    `test_an_on_behalf_draft_reusing_a_run_of_a_published_comment_is_accepted`,
    the same lift from a comment students already read.
    """
    world = response_loop
    the_week_for_the_lead(world)
    rows = world.response_count()

    answered = drafted(world, a_draft_lifting(RUN_OF[hidden]))

    assert answered.status_code == UNUSABLE_ANSWER_STATUS, (
        f"Lead A's on-behalf draft answered {answered.status_code} to a model draft reusing "
        f"{RUN_OF[hidden]!r} from a comment {WHY_HIDDEN[hidden]}. Done-when 1: refused as the "
        f"instructor's draft refuses it ({UNUSABLE_ANSWER_STATUS}, one fixed sentence). Body "
        f"{answered.text[:400]!r}."
    )
    registered_sentence_in(answered, "The refused on-behalf draft")
    assert RUN_OF[hidden] not in answered.text, "The refusal carries the run it refused."
    assert world.response_count() == rows, "A refused on-behalf draft wrote a response row."


def test_an_on_behalf_draft_reusing_a_run_of_a_published_comment_is_accepted(
    response_loop: LoopWorld,
) -> None:
    """The accepted control: the same lift from a published comment of the shown stream is served.

    **The mutation this kills:** an on-behalf guard comparing against every
    comment of the week — the over-reach that refuses a lead for answering what
    students said in the open, which SPEC §5.3 asks a response to do — and a
    route that refuses every on-behalf draft, which would pass the three
    refusals above for the wrong reason.
    """
    world = response_loop
    the_week_for_the_lead(world)
    draft = a_draft_lifting(RUN_OF[PUBLISHED_COMMENT])

    served = served_strings(
        drafted(world, draft), "Lead A's on-behalf draft lifting a published comment"
    )

    assert draft in served, (
        f"Lead A's on-behalf draft served {served!r} for a model draft of {draft!r}, which reuses "
        "only a published comment of a shown stream."
    )


# ---------------------------------------------------------------------------
# The count beside a held stream, refused; its twins, accepted.
# ---------------------------------------------------------------------------


def a_draft_lifting_nothing(world: LoopWorld, clause: str) -> str:
    """A count-rule draft, required to share no long run with any comment in the week."""
    draft = a_draft_saying(clause)
    for comment in every_comment_text(world):
        assert longest_shared_run(draft, comment) < THE_GUARD_BOUND, (
            f"The draft {draft!r} shares a long run with {comment!r}, so a refusal could be the "
            "reuse guard's rather than the count rule's. A broken input, not a red."
        )
    return draft


def test_an_on_behalf_draft_stating_a_count_beside_a_held_stream_is_refused(
    response_loop: LoopWorld,
) -> None:
    """The held week: the lead's draft says "Three of you asked …". 502, no row.

    **The mutations this kills:** the count rule (`states_a_count_of_people`) not
    called on the on-behalf path; called with a "held" flag computed for the
    instructor's reader rather than the stream. **The near misses:** the next two
    tests — no number in the same held week, and the same count in a week where
    every stream is shown.
    """
    world = response_loop
    the_week_for_the_lead(world)
    rows = world.response_count()
    draft = a_draft_lifting_nothing(world, COUNTING_CLAUSES["three-of-you"])

    answered = drafted(world, draft)

    assert answered.status_code == UNUSABLE_ANSWER_STATUS, (
        f"Lead A's on-behalf draft answered {answered.status_code} to {draft!r} in a week whose "
        "course stream is held below the threshold. Done-when 1: the count pair holds on behalf "
        f"too. Body {answered.text[:400]!r}."
    )
    registered_sentence_in(answered, "The refused on-behalf draft")
    assert world.response_count() == rows, "A refused on-behalf draft wrote a response row."


def test_an_on_behalf_draft_stating_no_number_beside_a_held_stream_is_accepted(
    response_loop: LoopWorld,
) -> None:
    """The held week's twin: no number at all. Served.

    **The mutation this kills:** an on-behalf path that refuses every draft in a
    week with a held stream.
    """
    world = response_loop
    the_week_for_the_lead(world)
    draft = a_draft_lifting_nothing(world, ALLOWED_CLAUSES["no-number"])

    served = served_strings(drafted(world, draft), "Lead A's on-behalf draft with no number")

    assert draft in served, f"Lead A's on-behalf draft served {served!r} for {draft!r}."


def test_an_on_behalf_draft_stating_a_count_when_every_stream_is_shown_is_accepted(
    response_loop: LoopWorld,
) -> None:
    """The shown week's twin: the same "Three of you …" with the course stream at the threshold. Served.

    **The mutation this kills:** the count rule applied to every on-behalf draft
    whatever the week — which forbids "three of you" where the comments are on
    the page anyway.
    """
    world = response_loop
    the_week_for_the_lead(world, course_commenters=configured_threshold())
    draft = a_draft_lifting_nothing(world, COUNTING_CLAUSES["three-of-you"])

    served = served_strings(drafted(world, draft), "Lead A's on-behalf draft in a shown week")

    assert draft in served, f"Lead A's on-behalf draft served {served!r} for {draft!r}."


# ---------------------------------------------------------------------------
# The gather and the prompt.
# ---------------------------------------------------------------------------


def what_the_on_behalf_tasks_sent(world: LoopWorld) -> dict[str, str]:
    """Lead A's on-behalf draft and check, each required to succeed; what each sent the provider."""
    sent: dict[str, str] = {}
    for door, answer, body in (
        (ON_BEHALF_DRAFT, draft_answer(A_PLAIN_DRAFT), {}),
        (ON_BEHALF_CHECK, check_answer([]), {"draft": A_PLAIN_DRAFT}),
    ):
        world.provider.script(answer)
        before = world.model_calls()
        answered = ask_on_behalf(world, door, body)
        assert 200 <= answered.status_code < 300, (
            f"Lead A's on-behalf {door.name} answered {answered.status_code} to a usable model "
            f"answer, so what it sent is not this test's subject. Body {answered.text[:400]!r}."
        )
        sent[door.name] = world.provider.text_since(before)
        assert sent[door.name].strip(), f"The on-behalf {door.name} sent the provider nothing."
    return sent


def test_the_on_behalf_prompts_carry_no_comment_and_no_held_themes_count(
    response_loop: LoopWorld,
) -> None:
    """What the on-behalf draft and check sent: the summaries and the held theme by name; no comment, no held count.

    **The canaries, in the same request** (`docs/MISTAKES.md` entry 3): the shown
    stream's stored summary and its theme's count (so counts reach the prompt),
    and the held theme's label (so the held theme reached it and only its count
    did not). **The mutations this kills:** an on-behalf gather reading comments
    (any of the week's, the published one included — the ticket says no
    comment); one rendering every stored theme with its count whatever the
    stream; one built apart from `response_gather` that skips the held-stream
    filter.
    """
    world = response_loop
    the_week_for_the_lead(world)

    sent = what_the_on_behalf_tasks_sent(world)

    for task, text in sent.items():
        assert SHOWN_SUMMARY_TEXT in text, (
            f"The on-behalf {task}'s request does not carry the shown stream's stored summary, so "
            "the absences below are a search of the wrong request."
        )
        assert carries_number(text, SHOWN_THEME_A_COUNT), (
            f"The on-behalf {task}'s request does not carry {SHOWN_THEME_A_COUNT}, the shown "
            "theme's count; without it a gather sending no number at all passes the held check."
        )
        assert HELD_THEME in text, (
            f"The on-behalf {task}'s request does not carry the held theme {HELD_THEME!r} by name, "
            "so the missing count below would only be a missing theme."
        )
        assert not carries_number(text, HELD_THEME_COUNT), (
            f"The on-behalf {task}'s request carries {HELD_THEME_COUNT}, the held theme's stored "
            "count. Done-when 1: the on-behalf gather and prompt carry no count on a held theme."
        )
        leaked = sorted({c for c in every_comment_text(world) if c in text})
        assert not leaked, (
            f"The on-behalf {task}'s request carries comment text: {leaked}. Done-when 1: the "
            "on-behalf gather and prompt carry no comment."
        )
