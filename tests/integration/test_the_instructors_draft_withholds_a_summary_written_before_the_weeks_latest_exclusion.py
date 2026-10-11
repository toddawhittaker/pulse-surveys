"""No summary written before the week's latest exclusion feeds the instructor's draft or check — E7-10 done-when 2.

> **No summary written before the week's latest exclusion feeds any draft or
> check** (privacy-authz MED). The instructor's gather applies the same filter as
> the on-behalf gather; the `for_on_behalf` branch for summaries goes. A test
> excludes a comment after its summary was written: neither the instructor's
> draft nor check prompt carries that summary or its themes; a summary written
> after the decision is still fed.

**Why it is a confidentiality defect and not a tidiness one.** A summary written
before the instructor excluded a comment may paraphrase that comment. The draft
guard refuses a reused *run* of an excluded comment, not a paraphrase of one, so a
summary fed to the draft carries the excluded comment's substance into text
published to every student — SPEC §5.2's exclusion undone one layer out. The
on-behalf path already withholds such a summary (E7-03 done-when 10,
`test_on_behalf_withholds_a_summary_written_before_the_weeks_latest_exclusion.py`);
this module holds the instructor's two tasks to the same rule.

**Measured on the wire**: what the application's gateway sent the provider this
suite runs (`tests/fixtures/response_draft.py`), so a renderer that dropped the
summary while another part of the request carried it is still red.

**Each decision is the teacher's, through E6-03's route**, and its stored instant
is read back off the row; each summary is planted with a `generated_at` chosen
relative to that instant, so nothing here depends on which clock the decision
route stamps with.

**Which failure a red is.** On the epic head the instructor's gather keeps a
summary written before the exclusion (the `for_on_behalf` branch), so the
withheld cases FAIL on an assertion naming the summary found in the prompt. The
served case is green on the epic head and is the control.
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.response_draft import A_PLAIN_DRAFT, check_answer, draft_answer
from fixtures.response_loop_doors import CLEAR_PAST, ON_BEHALF_WEEK, ONE_SECOND, LoopWorld
from fixtures.the_hold import report_opens

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

SUMMARY = "E7-10 the stored instructor-stream summary: the derivations went past too quickly"
THEME = "E7-10 derivations in the Wednesday lecture"
THEME_COUNT = 613
EXCLUDED = "E7-10 a comment the instructor excluded: the lecturer read every slide aloud verbatim"


def what_the_instructors_tasks_sent(world: LoopWorld) -> dict[str, str]:
    """The teacher's draft and check for course week 1, each required to succeed; what each sent.

    The model answers are the plainest usable ones — a draft lifting and counting
    nothing, and a check naming no theme — so a success depends on the route alone
    and never on which themes the gather happened to keep.
    """
    sent: dict[str, str] = {}
    for task, answer, ask in (
        ("draft", draft_answer(A_PLAIN_DRAFT), lambda: world.draft.draft()),
        ("check", check_answer([]), lambda: world.draft.check(A_PLAIN_DRAFT)),
    ):
        world.provider.script(answer)
        before = world.model_calls()
        answered: Any = ask()
        assert answered.status_code == 200, (
            f"The teacher's {task} answered {answered.status_code} to a usable model answer, so "
            f"what it sent is not this test's subject. Body {answered.text[:400]!r}."
        )
        sent[task] = world.provider.text_since(before)
        assert sent[task].strip(), f"The teacher's {task} answered 200 and sent nothing."
    return sent


def carrying_the_summary(sent: dict[str, str]) -> dict[str, list[str]]:
    """For each task, which of the summary and its theme its request carried."""
    return {task: [v for v in (SUMMARY, THEME) if v in text] for task, text in sent.items()}


def plant(world: LoopWorld, generated_at: Any) -> None:
    world.plant_summary(text=SUMMARY, themes=((THEME, THEME_COUNT),), generated_at=generated_at)


def test_an_exclusion_after_the_summary_was_written_withholds_it_from_both_prompts(
    response_loop: LoopWorld,
) -> None:
    """Entry 51's sequence: summary written; both prompts carry it; the teacher excludes; neither does.

    **The mutations this kills:** the instructor's gather keeping the
    `for_on_behalf` branch (summaries filtered only for the lead); the filter
    applied to the draft and not the check, or the other way round; the summary
    withheld while its themes still travel. **The near miss, in the same world:**
    the first pair of requests, which carry the summary because no comment had
    yet been excluded — so the absence afterwards is the exclusion's doing.
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    world.a_comment(EXCLUDED)
    generated_at = report_opens(ON_BEHALF_WEEK) + timedelta(minutes=10)
    plant(world, generated_at)

    before = carrying_the_summary(what_the_instructors_tasks_sent(world))
    decided = world.exclude(EXCLUDED)
    after = carrying_the_summary(what_the_instructors_tasks_sent(world))

    assert decided > generated_at, (
        f"The exclusion is stored at {decided}, not after the summary's {generated_at}; this "
        "sequence needs it after. A broken world, not a red."
    )
    assert before == {"draft": [SUMMARY, THEME], "check": [SUMMARY, THEME]}, (
        f"Before any exclusion the teacher's prompts carried {before}; both should carry the "
        "summary and its theme, or the absence below proves nothing."
    )
    assert after == {"draft": [], "check": []}, (
        f"After the teacher excluded a comment written into the week, the prompts still carry "
        f"{after} from a summary written before that exclusion. Done-when 2: the instructor's "
        "gather applies the on-behalf filter, so neither prompt carries that summary or its themes."
    )


@pytest.mark.parametrize(
    ("offset", "why"),
    [
        (-ONE_SECOND, "one second before the exclusion"),
        (timedelta(0), "at the same instant as the exclusion (the tie withholds)"),
    ],
)
def test_a_summary_written_not_strictly_after_an_exclusion_feeds_neither_prompt(
    response_loop: LoopWorld, offset: timedelta, why: str
) -> None:
    """The exclusion first; a summary dated one second before it, or at it: in neither prompt.

    **The mutations this kills:** no filter on the instructor's path; `>=` where
    E7-03's rule is "not strictly earlier" (the tie fed). **The near miss:**
    `test_a_summary_written_after_the_exclusion_is_still_fed_to_both_prompts`.
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    world.a_comment(EXCLUDED)
    decided = world.exclude(EXCLUDED)
    plant(world, decided + offset)

    carried = carrying_the_summary(what_the_instructors_tasks_sent(world))

    assert carried == {
        "draft": [],
        "check": [],
    }, f"A summary written {why} reached the teacher's prompts: {carried}. Done-when 2."


def test_a_summary_written_after_the_exclusion_is_still_fed_to_both_prompts(
    response_loop: LoopWorld,
) -> None:
    """The exclusion first; the summary one second after it: both prompts carry it and its theme.

    **The mutations this kills:** a filter withholding every summary in a week
    with any decision; dropping summaries from the instructor's gather altogether
    (which passes every withheld case above).
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    world.a_comment(EXCLUDED)
    decided = world.exclude(EXCLUDED)
    plant(world, decided + ONE_SECOND)

    carried = carrying_the_summary(what_the_instructors_tasks_sent(world))

    assert carried == {"draft": [SUMMARY, THEME], "check": [SUMMARY, THEME]}, (
        f"A summary written one second after the exclusion reached the teacher's prompts as "
        f"{carried}. Done-when 2: a summary written after the decision is still fed."
    )
