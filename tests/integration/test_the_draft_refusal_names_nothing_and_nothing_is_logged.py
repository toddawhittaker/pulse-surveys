"""Nothing is logged, and the refusal names nothing — E7-04 done-when 5.

> Neither task logs a comment, a summary or the draft text, on success or on
> refusal. The refusal of a draft is byte-identical whichever hidden comment
> matched, and contains no word of the comment or the draft; this is tested with a
> planted distinctive run.

And work-order decision 2: the 502 carries "one fixed sentence in `copy/` saying the
assistant could not produce a usable answer — the same sentence whatever triggered
it." So the draft's refusal and the check's are compared too, and the sentence is
found in the copy registry rather than transcribed here (`docs/MISTAKES.md` entry
19: a test holding the sentence would agree with a copy edited on both sides).

**Why byte-identical matters.** The instructor writes the draft and can edit it a
word at a time; a refusal that differed by which comment matched — or quoted the
run — is an oracle for "is this phrase in a comment I am not shown", run against a
held stream's comments one guess at a time.

**The log capture is proved before it is trusted** (`docs/MISTAKES.md` entry 3):
a canary goes through each `app.*` logger the two tasks can live under, after the
drive, so a logger that does not propagate to the capture fails a control rather
than reporting a clean stream.

**Marked `invariant`.** What either half would leak is a held or excluded comment's
text, which §4.1 item 3 and §5.2 withhold.
"""

import logging
import re
from typing import Any

import pytest
from fixtures.ags_client import logged_text
from fixtures.report_api import FULL_WEEK_COMMENTS
from fixtures.response_draft import (
    A_PLAIN_DRAFT,
    AN_INVENTED_THEME,
    CHECK,
    DRAFT,
    EXCLUDED_COMMENT,
    FLAGGED_COMMENT,
    HELD_COMMENT,
    HELD_SUMMARY_TEXT,
    PUBLISHED_COMMENT,
    RUN_OF,
    SHOWN_SUMMARY_TEXT,
    SHOWN_THEME_A,
    SHOWN_THEME_A_COUNT,
    DraftDoor,
    a_draft_lifting,
    assert_unusable,
    check_with,
    draft_answer,
    registered_sentence_in,
    text_of,
    unaddressed_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The distinctive words of each hidden comment's lifted run, chosen by hand as the
# ones no refusal sentence would carry by accident. Written out rather than split
# off the run, so a common word ("answered", "questions") cannot make the test about
# English rather than about the comment.
DISTINCTIVE_WORDS = {
    EXCLUDED_COMMENT: ("rubric", "contradicted", "handout"),
    FLAGGED_COMMENT: ("seminar", "mocked"),
    HELD_COMMENT: ("forum", "silent"),
}

# The `app` loggers the two tasks, their gather, their refusals and their routes can
# write under (SPEC §13: `ai/`, `services/`, `api/`). Each gets a canary.
LOGGER_PREFIXES = ("app.ai", "app.services", "app.api")
CANARIES = {prefix: f"e7-04-canary-{prefix.replace('.', '-')}-6d2f" for prefix in LOGGER_PREFIXES}


def refused_lifting(door: DraftDoor, comment: str) -> Any:
    door.provider.script(draft_answer(a_draft_lifting(RUN_OF[comment])))
    answered = door.draft()
    assert_unusable(answered, "draft", f"reuses a run of {comment!r}")
    return answered


def words_in(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def test_a_draft_refusal_is_the_same_bytes_whichever_hidden_comment_matched(
    draft_door: DraftDoor,
) -> None:
    """Three refusals, three different hidden comments, one body — and the check's is the same.

    **The mutations this kills:** a refusal naming the matched comment, its run, its
    state ("an excluded comment") or its stream — any of which makes the bodies
    differ; and a check refusal worded apart from the draft's, which decision 2
    rules out. **The near miss it must survive:** a sentence that is fixed but not
    in the copy registry — refused by `registered_sentence_in`.
    """
    door = draft_door
    door.build_the_week()
    refusals = {comment: refused_lifting(door, comment) for comment in DISTINCTIVE_WORDS}

    bodies = {comment: answered.content for comment, answered in refusals.items()}
    assert len(set(bodies.values())) == 1, (
        "The draft's refusal differs by which hidden comment matched: "
        f"{ {comment[:30]: body[:200] for comment, body in bodies.items()} }. Done-when 5: "
        "'byte-identical whichever hidden comment matched'."
    )

    check_refusal = check_with(door, [(AN_INVENTED_THEME, 2)])
    assert_unusable(check_refusal, "check", f"names {AN_INVENTED_THEME!r}")
    assert check_refusal.content == next(iter(bodies.values())), (
        f"The check's refusal {check_refusal.text[:300]!r} differs from the draft's "
        f"{next(iter(refusals.values())).text[:300]!r}. Decision 2: 'the same sentence whatever "
        "triggered it'."
    )
    keys = {registered_sentence_in(answered, "A refusal") for answered in refusals.values()}
    keys.add(registered_sentence_in(check_refusal, "The check's refusal"))
    assert len(keys) == 1, f"The refusals resolve to {sorted(keys)} in the copy registry."


@pytest.mark.parametrize(
    "comment", tuple(DISTINCTIVE_WORDS), ids=("excluded", "still-flagged", "held-stream")
)
def test_a_draft_refusal_carries_no_word_of_the_comment_or_the_draft(
    draft_door: DraftDoor, comment: str
) -> None:
    """The planted run, its distinctive words, and the draft itself: none in the refusal.

    **The mutation this kills:** an error built by interpolating what the guard was
    holding — "draft reuses 'marking rubric for the lab session…'" — which is the
    shape a refusal written while debugging takes.
    """
    door = draft_door
    door.build_the_week()
    answered = refused_lifting(door, comment)
    said = answered.text
    draft = a_draft_lifting(RUN_OF[comment])
    present = sorted(words_in(said) & set(DISTINCTIVE_WORDS[comment]))
    assert (
        not present
    ), f"The refusal carries {present} from the hidden comment {comment!r}: {said[:400]!r}."
    for fragment in (RUN_OF[comment], comment, draft):
        assert (
            fragment.lower() not in said.lower()
        ), f"The refusal carries {fragment!r}: {said[:400]!r}."


def test_neither_task_logs_a_comment_a_summary_or_a_draft(
    draft_door: DraftDoor, caplog: pytest.LogCaptureFixture
) -> None:
    """Five requests — two successes and three refusals across both tasks — and a clean log.

    Searched: every comment of the week, every lifted run, both stored summaries,
    and every draft the model was made to answer or the check was sent. Each is the
    exact string the run handled.

    **The mutation this kills:** a `logger.info`/`warning` in either task, the gather
    or the refusal that formats the draft, the matched comment or the summary it was
    given — the work order's trap: "Never log draft or comment text (the summary
    task's logging shape)". The refusal paths are driven as well as the successes,
    because a failure path is the one written while debugging. **The near miss it
    must survive:** logging that a refusal happened, which is allowed and names
    none of these.
    """
    door = draft_door
    door.build_the_week()
    caplog.set_level(logging.DEBUG, logger="app")
    for prefix in LOGGER_PREFIXES:
        caplog.set_level(logging.DEBUG, logger=prefix)

    lifted = (PUBLISHED_COMMENT, EXCLUDED_COMMENT, HELD_COMMENT)
    drafts = [a_draft_lifting(RUN_OF[comment]) for comment in lifted] + [A_PLAIN_DRAFT]

    door.provider.script(draft_answer(a_draft_lifting(RUN_OF[PUBLISHED_COMMENT])))
    text_of(door.draft())
    refused_lifting(door, EXCLUDED_COMMENT)
    refused_lifting(door, HELD_COMMENT)
    unaddressed_of(check_with(door, [(SHOWN_THEME_A, SHOWN_THEME_A_COUNT)]))
    assert_unusable(check_with(door, [(AN_INVENTED_THEME, 2)]), CHECK, "names an invented theme")

    for prefix, canary in CANARIES.items():
        logging.getLogger(prefix).warning("control line for E7-04's log assertion: %s", canary)
    captured = [
        record
        for record in caplog.records
        if record.name == "app" or record.name.startswith("app.")
    ]
    text = logged_text(captured)
    for prefix, canary in CANARIES.items():
        assert canary in text, (
            f"The canary written through `{prefix}` is not in the captured text, so that logger "
            "does not reach this capture and a clean result below would be blindness."
        )

    forbidden = {
        **{f"comment {c[:24]!r}": c for c in (*RUN_OF, *FULL_WEEK_COMMENTS)},
        **{f"run {r!r}": r for r in RUN_OF.values()},
        "the shown summary": SHOWN_SUMMARY_TEXT,
        "the held summary": HELD_SUMMARY_TEXT,
        **{f"draft number {index}": draft for index, draft in enumerate(drafts)},
    }
    leaked = sorted(name for name, value in forbidden.items() if value in text)
    assert not leaked, (
        f"The {DRAFT} and {CHECK} tasks logged {leaked}. Done-when 5: 'Neither task logs a "
        "comment, a summary or the draft text, on success or on refusal.'"
    )
