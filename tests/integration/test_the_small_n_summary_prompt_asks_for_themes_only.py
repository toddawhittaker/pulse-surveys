"""The small-N mode reaches the model — the prompt half of the owner's ruling of 2026-09-09.

The ruling: below the n-threshold a week's summary names themes only and may not
reuse the commenters' own word strings; above it, the contract is unchanged.
Work-order decision D9 settles two mechanisms, and this module is the first of
them — the prompt carries the instruction, and the service passes the mode.

**Two mechanisms rather than one, and each needs its own test.** A prompt
instruction is soft: the model may ignore it, a provider swap changes what
ignoring means, and nothing about a stored row says whether the instruction was
followed. So D9 pairs it with a structural guard at store time, and
`test_a_small_n_summary_never_reuses_a_commenters_words.py` is that half. What is
asserted here is the half the guard cannot see: that the model is *asked*. A build
with the guard and no prompt change refuses summaries it never asked to be
different, and every quiet week loses its only comment signal to a retry loop.

**Asserted at the gateway boundary**, the way
`test_the_summary_job_feeds_no_moderation_held_comment_to_the_model.py` asserts
what fed a call: the double records every prompt the walk hands it, and the two
prompts — one section below the threshold, one at it, in the same run — are
compared with each other.

**What is NOT asserted, and why.** Not the wording. No record I may read settles
the sentence the prompt carries, and a test holding a copy of it would pass
against any wording at all and go red on an edit that changed nothing a model
reads differently (`tests/e2e/landing-views.spec.ts` states this repository's rule
for governed copy, and the same reasoning applies to a prompt). What is asserted is
the *difference*: below the threshold the prompt says something it does not say
above, and the difference is not the week's comments and not its response count.
That is what a mode flag reaching the prompt looks like from outside, and it is the
strongest claim available without choosing the implementer's words.

**Marked `invariant`.** It is §4.1 item 3 one layer earlier than the payload: the
threshold's promise reaching the surface §5.1 guarantees a small-N week will have.

**Which failure a red is.** Reached through `summary_job_contract`, whose lookups
are `pytest.fail` calls naming the deliverable; a red is an assertion about the
prompts the walk produced (`docs/MISTAKES.md` entry 44).
"""

import re
from typing import Any

import pytest
from fixtures.report_comments import configured_threshold
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    A_COHORT,
    ANOTHER_COHORT,
    INSTRUCTOR_MARK,
    StreamAwareGateway,
    SummaryWorld,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The two sections' routing nonces. Tokens that appear nowhere else in this
# repository, so finding one in a prompt is evidence rather than a coincidence with
# the prompt template (`docs/MISTAKES.md` entry 3).
QUIET_SECTION = "Jn5RtWq8Xv"
BUSY_SECTION = "Cz2FbHm6Ld"

# The comment body both sections' students write, identical in both so the only
# things that differ between the two prompts are the nonce, the response count and
# whatever the mode adds.
A_COMMENT_BODY = "the seminar spent its whole hour on one worked example"

# Any run of digits, replaced before two prompt lines are compared. The response
# count differs between the two sections by definition — a week below the threshold
# and a week at it cannot hold the same number of responses — so a line that is
# identical except for its numbers is not evidence of a mode.
A_NUMBER = re.compile(r"\d+")


def a_comment_from(nonce: str) -> str:
    """One instructor-stream comment carrying its stream marker and a routing nonce."""
    return f"{INSTRUCTOR_MARK} {nonce} {A_COMMENT_BODY}"


def _lines_of(prompt: str) -> list[str]:
    """One prompt as comparable lines: whitespace collapsed, numbers blanked, blanks dropped.

    Numbers go because the response count is in the prompt and differs between the
    two weeks whatever the mode does. Whitespace collapses because a template that
    wraps differently at two lengths would otherwise read as a difference.
    """
    lines = []
    for raw in prompt.splitlines():
        collapsed = " ".join(raw.split())
        if collapsed:
            lines.append(A_NUMBER.sub("#", collapsed))
    return lines


def _the_prompt_carrying(gateway: Any, nonce: str) -> str:
    """The one prompt this run handed the model for the section carrying `nonce`."""
    found = [prompt for prompt in gateway.prompts if nonce in prompt]
    assert len(found) == 1, (
        f"{len(found)} of the {len(gateway.prompts)} prompts this run produced carry {nonce!r}. "
        "Each section's comments carry their own nonce and each section-stream is one call, so "
        "none means the walk never visited that section and two means one section's comments "
        "reached two calls."
    )
    return found[0]


def test_the_prompt_for_a_week_below_the_threshold_says_something_the_other_does_not(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The mode reaches the model: two sections, one run, two prompts that differ.

    One section's week holds two responses and the other's holds exactly the
    configured threshold. Both weeks close together, both are walked in one run, and
    both students write the same sentence — so the comments contribute the same text
    to both prompts and the nonce is the only part of them that differs.

    The below-threshold prompt must carry at least one line the other does not, once
    the comments and the numbers are set aside. That line is the themes-only
    instruction, whatever the implementer words it as.

    **The mutations this kills:** the mode flag computed and never passed to the
    task, and the task taking it and never putting it in the prompt — which are two
    different defects with one symptom, and both leave the store-time guard
    refusing summaries the model was never asked to write differently. **The near
    miss it must survive:** a prompt that differs only in the week's response count,
    which every build produces whether or not a mode exists; the numbers are blanked
    before the comparison for exactly that reason, and the control test below proves
    the blanking is not so aggressive that it would hide a real difference.

    **What it does not reach** (`docs/MISTAKES.md` entry 14): whether the
    instruction says anything sensible. That is SPEC §9.3's question and
    `tests/evals/summary/` is where it is asked — the eval case this ticket adds
    beside it drives what the model does with it.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    threshold = configured_threshold()
    assert threshold >= 3, (
        f"The configured n-threshold is {threshold}; this world needs a week strictly under it "
        "holding at least two respondents and a week at it."
    )

    summary_world.build(A_COHORT)
    summary_world.add_section(ANOTHER_COHORT)
    for index in range(2):
        summary_world.respond(
            f"{QUIET_SECTION}-subject-{index}",
            cohort=A_COHORT,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=a_comment_from(QUIET_SECTION),
        )
    for index in range(threshold):
        summary_world.respond(
            f"{BUSY_SECTION}-subject-{index}",
            cohort=ANOTHER_COHORT,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=a_comment_from(BUSY_SECTION),
        )
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=gateway)

    assert gateway.prompts, (
        "The walk made no model call at all over two closed weeks each carrying instructor "
        "comments, so there is no prompt to compare and every claim below would be about nothing."
    )
    quiet = _lines_of(_the_prompt_carrying(gateway, QUIET_SECTION))
    busy = _lines_of(_the_prompt_carrying(gateway, BUSY_SECTION))

    # The comments themselves are in both prompts and are not the mode.
    said_only_to_the_quiet_week = [
        line
        for line in quiet
        if line not in busy and QUIET_SECTION not in line and INSTRUCTOR_MARK not in line
    ]

    assert said_only_to_the_quiet_week, (
        "The prompt for a week of two responses says nothing the prompt for a week at the "
        f"threshold of {threshold} does not, once the comments and the numbers are set aside.\n\n"
        "The owner's ruling of 2026-09-09 is that below the threshold a summary names themes only "
        "and may not reuse the commenters' word strings, and D9 puts that instruction in the "
        "prompt with the service passing the mode. Nothing here pins the wording — what is "
        "required is that there *is* an instruction, because the store-time guard beside it "
        "refuses a summary the model was never asked to write differently, and a quiet week then "
        "loses the only comment signal SPEC §5.1 promises it.\n\n"
        f"The quiet week's prompt lines: {quiet}\n\nThe other's: {busy}"
    )


def test_the_prompts_are_otherwise_the_same_so_the_difference_is_the_mode(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The control. **A red here means this module is broken, not the prompt.**

    The test above says "the quiet week's prompt carries a line the other's does
    not". That claim is worth nothing if the two prompts differ everywhere — if the
    template varies with the section, the cohort, the ordering, or anything else
    this world does not hold constant, then a difference is guaranteed whether or
    not a mode exists, and the assertion passes against a build with no ruling in it
    at all.

    So this drives the *same* comparison over two sections that are both below the
    threshold, with the same comment text and the same number of responses. Every
    line except the ones carrying a nonce must be shared. A difference here is the
    template varying on something this module does not control, and the test above
    is measuring that variation rather than the mode.

    **The mutation it kills:** a prompt that embeds the section's own name, code or
    key — which would make every pair of prompts differ and the mode assertion
    vacuous.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    threshold = configured_threshold()

    summary_world.build(A_COHORT)
    summary_world.add_section(ANOTHER_COHORT)
    for cohort, nonce in ((A_COHORT, QUIET_SECTION), (ANOTHER_COHORT, BUSY_SECTION)):
        for index in range(2):
            summary_world.respond(
                f"{nonce}-subject-{index}",
                cohort=cohort,
                term_week=A_CLOSED_TERM_WEEK,
                instructor_comment=a_comment_from(nonce),
            )
    assert threshold > 2, f"The configured n-threshold is {threshold}; both weeks must be under it."
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()

    gateway = StreamAwareGateway(summary_contracts)
    summary_job_contract.run(gateway=gateway)

    first = _lines_of(_the_prompt_carrying(gateway, QUIET_SECTION))
    second = _lines_of(_the_prompt_carrying(gateway, BUSY_SECTION))
    differing = [
        line
        for line in first
        if line not in second and QUIET_SECTION not in line and INSTRUCTOR_MARK not in line
    ]

    assert not differing, (
        f"Two sections, both below the threshold, both holding two responses and the same comment "
        f"text, were sent prompts differing in {differing}.\n\n"
        "Nothing about the mode differs between them, so this is the template varying on the "
        "section itself — its name, its code, its key, or the order the walk visited it in. While "
        "that is true, the test above cannot tell a themes-only instruction from ordinary "
        "per-section variation, and its green means nothing."
    )
