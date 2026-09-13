"""Running the walk twice — ticket E4-06, criterion 1.

> Idempotence, driven: two consecutive runs over the same state produce identical
> tables — the second run writes nothing, proven by row identity and not by count.

The ticket names E3-06 as the pattern and gives the reason: "a beat entry as the
ordinary trigger rather than the definition of the work, and a re-run that
converges (missing rows filled, existing rows untouched)". Under that reading the
schedule is also the retry, so the walk is run again after every failure and every
restart — and a walk that rewrote what it found would put different prose under an
instructor who had already read the first version, on a summary the product does
not regenerate by design (breakdown decision 2).

**The pre-existing rows are planted by this suite, not by a first run.** That is
this ticket's inherited trap, `docs/MISTAKES.md` entry 31 — "'running it twice is
safe' was tested only against a database the loader itself had filled". A second
run compared against a first run's output cannot tell "left alone" from
"rewritten identically": the writer produces the same values either way. Rows
carrying a summary, a prompt version and a model id **no run of this job could
produce** can tell them apart, and that is what is planted here.

**Identity, never a count.** A walk that deleted a section-week's two rows and
wrote two fresh ones keeps every count in this table exactly right, changes the
primary keys and the `generated_at` of both, and replaces what an instructor read
on Monday morning with something else on Monday afternoon. So what is compared is
each row's key against the values a rewrite would move.

**Which failure a red here is.** Before E4-06 lands, expected red on
`pytest.fail` naming `app.jobs.tasks` as a module with no
`generate_weekly_summaries` — a plain call in a test body
(`docs/MISTAKES.md` entry 44).
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    StreamAwareGateway,
    SummaryWorld,
    UnreachableGateway,
    comment_text,
)

pytestmark = pytest.mark.integration

RESPONSES_THAT_WEEK = 3

# The nonces the two sections' comments carry.
FIRST_NONCE = "Jm3QdVt9Ry"
SECOND_NONCE = "Kb8ZnWl4Ph"

# What the planted rows carry, and none of it is anything this job could produce.
# The summary is prose no gateway in this suite answers with, the prompt version
# names no file `app/ai/prompts/` holds, the model id names no model, and the
# instant is years before any run. If any of these is gone after a run, the walk
# rewrote a row it should not have touched — and each of the four says so
# separately, because a walk that refreshed only the provenance is as wrong as one
# that replaced the prose.
A_SUMMARY_NOBODY_GENERATED = "Xr4WtNc7Bq — planted by the idempotence test, not by any run."
A_PROMPT_VERSION_NOBODY_RENDERED = "e4-06-planted-prompt-version"
A_MODEL_ID_NOBODY_CALLED = "e4-06-planted-model-id"
A_COUNT_THE_WEEK_DID_NOT_HAVE = 41
AN_INSTANT_BEFORE_ANY_RUN = datetime(2020, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)


def a_world_with_one_section_already_summarized(
    world: SummaryWorld, contract: Any
) -> dict[str, str]:
    """Two sections with the same week closed; the first already carries its two rows.

    The first section's rows are this suite's, planted with values no walk
    produces. The second has none, so one run has something to do — without that,
    "the second run writes nothing" would be indistinguishable from a walk that
    never writes anything at all.
    """
    world.build(contract.a_cohort)
    world.add_section(contract.another_cohort)
    for cohort, nonce in (
        (contract.a_cohort, FIRST_NONCE),
        (contract.another_cohort, SECOND_NONCE),
    ):
        for index in range(RESPONSES_THAT_WEEK):
            world.respond(
                f"{nonce}-subject-{index}",
                cohort=cohort,
                term_week=A_CLOSED_TERM_WEEK,
                instructor_comment=comment_text(INSTRUCTOR_STREAM, f"{nonce}-i{index}"),
                course_comment=comment_text(COURSE_STREAM, f"{nonce}-c{index}"),
            )
    for stream in contract.stored_streams:
        world.plant_summary(
            cohort=contract.a_cohort,
            term_week=A_CLOSED_TERM_WEEK,
            stream=stream,
            summary_text=A_SUMMARY_NOBODY_GENERATED,
            response_count=A_COUNT_THE_WEEK_DID_NOT_HAVE,
            prompt_version=A_PROMPT_VERSION_NOBODY_RENDERED,
            model_id=A_MODEL_ID_NOBODY_CALLED,
            generated_at=AN_INSTANT_BEFORE_ANY_RUN,
        )
    world.clock_after(A_CLOSED_TERM_WEEK)
    world.commit()
    return {"already": contract.a_cohort, "missing": contract.another_cohort}


def test_a_section_week_that_already_has_its_summaries_is_left_exactly_as_it_was(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The convergence half: missing rows filled, existing rows untouched, in one run.

    The ticket's scope selects "sections with closed weeks **lacking** summary
    rows", and this is that clause driven from both sides in one walk: one section
    has its two rows and must come out of the run byte for byte as it went in;
    the other has none and must come out with two.

    **The planted rows carry values no walk could produce**, which is what makes
    "untouched" checkable at all (`docs/MISTAKES.md` entry 31). Each of the four
    values is asserted on its own, because a walk that refreshed the provenance
    while leaving the prose — or the other way round — is a different defect from
    a wholesale rewrite and only one of them is visible in any single field.

    **The gateway call count is the other half of the same claim.** A walk that
    generated a summary and then decided not to store it has already spent the
    provider request, twice per already-summarized section-week, every Monday for
    the rest of the term — and a table-only assertion cannot see it. Two calls for
    the one section that needed them.

    **The mutation this kills:** the "lacking summary rows" clause dropped, so the
    walk regenerates every closed week it can see and an upsert quietly replaces
    what an instructor already read; and the clause written per *section* rather
    than per section-week, which would skip a section's later weeks for ever
    because its first week had been summarized.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    cohorts = a_world_with_one_section_already_summarized(summary_world, summary_job_contract)
    already = summary_world.section_id(cohorts["already"])
    missing = summary_world.section_id(cohorts["missing"])
    planted = summary_world.identity_of(summary_world.summaries(section_id=already))
    assert len(planted) == len(summary_job_contract.stored_streams), (
        f"this test planted {len(planted)} rows and meant to plant "
        f"{len(summary_job_contract.stored_streams)}, one per stream. Without both, the walk has a "
        "gap to fill in the section this test says it must not touch."
    )
    gateway = StreamAwareGateway(summary_contracts)

    summary_job_contract.run(gateway=gateway)

    assert summary_world.identity_of(summary_world.summaries(section_id=already)) == planted, (
        "the run changed the section-week that already had its summaries. Its rows were planted "
        f"carrying {A_SUMMARY_NOBODY_GENERATED!r}, {A_PROMPT_VERSION_NOBODY_RENDERED!r}, "
        f"{A_MODEL_ID_NOBODY_CALLED!r} and {AN_INSTANT_BEFORE_ANY_RUN}, none of which any walk "
        "produces — so a difference here is the walk rewriting a summary an instructor may already "
        "have read. Generation is once-and-done (breakdown decision 2)."
    )
    filled = summary_world.summaries(section_id=missing)
    assert sorted(str(row[summary_job_contract.stream_column]) for row in filled) == sorted(
        summary_job_contract.stored_streams
    ), (
        f"the section-week with no summaries came out of the run with {len(filled)} row(s). The "
        "same walk that left one section alone has to fill the other, or 'lacking summary rows' is "
        "being read as 'no summaries anywhere'."
    )
    assert len(gateway.calls) == len(summary_job_contract.stored_streams), (
        f"the walk made {len(gateway.calls)} model calls to fill one section-week's two streams. "
        "A walk that generates a summary for an already-summarized week and then declines to store "
        "it leaves this table looking perfect and spends two provider requests per section per "
        "Monday for the rest of the term."
    )


def test_the_second_run_over_the_same_state_writes_nothing_and_asks_nothing(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """Criterion 1: two consecutive runs, and the second one is a no-op.

    **The second run is given a gateway that fails on any attribute access at
    all.** That is a stronger statement than "the table did not change" and it is
    the one the schedule depends on: this job's only retry policy is that it runs
    again, so a walk that re-asks the provider about every already-summarized week
    would grow its bill and its runtime with the term, on a job SPEC §10 gives
    thirty minutes for five hundred sections. A double that answered politely
    would hide that entirely.

    **The table is compared by row identity**, which is the criterion's own words:
    "proven by row identity and not by count". Keys, `generated_at`, text,
    provenance and the stated count — every value a rewrite would move.

    **The first run is what makes the second mean anything.** It leaves rows the
    second run has to decline to touch; without it the second run's silence is the
    silence of a walk that found nothing at all, which is what an unbuilt tree
    does (`docs/MISTAKES.md` entry 3).

    **The mutation this kills:** an `INSERT ... ON CONFLICT DO UPDATE` in place of
    the "lacking summary rows" clause, which converges on the same table and
    rewrites every row it visits — invisible to a count, invisible to a spot check
    of the text while the gateway keeps answering the same thing, and visible here
    on `generated_at` and on the call the second run must not make.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    a_world_with_one_section_already_summarized(summary_world, summary_job_contract)

    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))
    after_the_first_run = summary_world.identity_of(summary_world.summaries())
    assert len(after_the_first_run) == 2 * len(summary_job_contract.stored_streams), (
        f"after one run the table holds {len(after_the_first_run)} rows and this world has two "
        f"closed section-weeks, each owed {len(summary_job_contract.stored_streams)}. The second "
        "run below cannot be shown to leave a full table alone when the table is not full."
    )

    summary_job_contract.run(gateway=UnreachableGateway())

    assert summary_world.identity_of(summary_world.summaries()) == after_the_first_run, (
        "a second run over unchanged state moved something. Every row's key, `generated_at`, text, "
        "provenance and stated response count are compared, because a count is kept exactly by a "
        "walk that deletes two rows and writes two more — and that walk puts different prose under "
        "an instructor between two readings of the same page."
    )
