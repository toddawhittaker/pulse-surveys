"""A provider failure mid-walk, and what it costs — ticket E4-06, criterion 2.

> A provider failure mid-walk: the failed section-week has no row, every other
> section-week has its row, and the next run fills the gap — one test, three
> assertions.

and the ticket's scope beside it: "a provider failure for one section-week leaves
that row absent and the walk continuing; the next run retries it."

**The grain is the section-week and it covers both streams.** SPEC §5.1 puts two
summaries on one week's report, and E4-11 renders each comment group led by its
own. A week that ends with the instructor summary written and the course one
missing is not a partial success: it is a report whose two halves were generated
from different runs at different times, with no way for a reader to tell — and
generation is once-and-done (breakdown decision 2), so a half-written week is
half-written for good. One transaction per section-week is what makes "the next
run retries it" true of the whole week rather than of whatever failed last.

**Both streams' failures are driven, and they fail differently.** A failure on
the *second* call is the load-bearing case: by then the first stream's row exists
inside the transaction, so a walk committing per stream leaves it behind. A
failure on the first call only proves nothing was written. Both are here because
the criterion says "on either stream", and only the pair distinguishes a
transaction from an ordering accident.

**Which section fails is parametrized too, and that is not symmetry for its own
sake.** The walk's order over sections is the implementer's and nothing settles
it. If the walk *aborted* on a failure rather than continuing, a test that always
failed the same section would pass whenever that section happened to be walked
last. Failing each of the two in turn means one of the two cases catches it
whichever order the walk takes.

**Which failure a red here is.** Before E4-06 lands, expected red on
`pytest.fail` naming `app.jobs.tasks` as a module with no
`generate_weekly_summaries` — a plain call in a test body
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    StreamAwareGateway,
    SummaryWorld,
    comment_text,
)

pytestmark = pytest.mark.integration

# ADR 0056's class for "the provider did not answer", which is what a walk has to
# tolerate: nobody is waiting on a Monday report and no heuristic stands in for a
# summary (ADR 0148 point 4), so the week is left for the next run rather than
# filled with something.
UNAVAILABLE_ERROR = "AIProviderUnavailableError"

# How many students answer each section-week here. Small, because what is being
# measured is which rows exist rather than any arithmetic over them.
RESPONSES_THAT_WEEK = 3

# The four nonces, one per section and stream, so a failure can be aimed at
# exactly one model call. Tokens that appear nowhere else in this repository.
NONCES = {
    "first": {INSTRUCTOR_STREAM: "Bd8VqTn3Xw", COURSE_STREAM: "Ly5RcHm9Zk"},
    "second": {INSTRUCTOR_STREAM: "Nt2WgJp6Fv", COURSE_STREAM: "Cs4XdBr7Qm"},
}


def a_section_week(world: SummaryWorld, *, cohort: str, nonces: dict[str, str]) -> None:
    """One section's closed week, with comments in both streams carrying their nonces."""
    for index in range(RESPONSES_THAT_WEEK):
        world.respond(
            f"{nonces[INSTRUCTOR_STREAM]}-subject-{index}",
            cohort=cohort,
            term_week=A_CLOSED_TERM_WEEK,
            instructor_comment=comment_text(
                INSTRUCTOR_STREAM, f"{nonces[INSTRUCTOR_STREAM]}-{index}"
            ),
            course_comment=comment_text(COURSE_STREAM, f"{nonces[COURSE_STREAM]}-{index}"),
        )


def two_sections_with_a_closed_week(world: SummaryWorld, contract: Any) -> dict[str, str]:
    """Two sections of one term, each with the same course week closed. Answers to which cohort."""
    world.build(contract.a_cohort)
    world.add_section(contract.another_cohort)
    a_section_week(world, cohort=contract.a_cohort, nonces=NONCES["first"])
    a_section_week(world, cohort=contract.another_cohort, nonces=NONCES["second"])
    world.clock_after(A_CLOSED_TERM_WEEK)
    world.commit()
    return {"first": contract.a_cohort, "second": contract.another_cohort}


@pytest.mark.parametrize("failing_section", ["first", "second"])
@pytest.mark.parametrize(
    "failing_stream",
    [INSTRUCTOR_STREAM, COURSE_STREAM],
    ids=["fails-on-the-first-call", "fails-on-the-second-call"],
)
def test_a_provider_failure_costs_its_own_section_week_and_nothing_else(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
    failing_section: str,
    failing_stream: str,
) -> None:
    """Criterion 2's three assertions, over two sections and two runs.

    One provider failure, aimed at one stream of one section-week.

      1. **That section-week has no rows.** Not one, not the stream that
         succeeded: SPEC §5.1's report reads its two comment groups from the pair,
         and E4-11 tolerates an absent summary honestly. A half-written week is
         the state nothing renders correctly and nothing ever repairs, because the
         next run finds rows for that section-week and moves on.
      2. **Every other section-week has its rows.** The walk continues. A
         provider that refuses one section's call for its own reason — a length,
         a content filter, a transient fault — must not cost an institution its
         Monday.
      3. **The next run fills the gap**, which is the whole of the ticket's
         retry policy: there is no backoff and no queue, the schedule is the
         retry, and that only works if a walk that already succeeded is
         idempotent over what it wrote. So the second run's assertions are two:
         the failed section-week now has its two rows, and the section that
         succeeded first carries *the same rows* — same keys, same
         `generated_at`, same text — rather than fresh ones.

    **The failure class is named rather than left as any exception**
    (`docs/MISTAKES.md` entry 49: establish which layer refused). ADR 0056 makes
    the four gateway classes the interface callers branch on, and a walk that
    caught bare `Exception` would swallow a programming error in its own body as
    if the provider had been down — which is the mutation the sibling test below
    is about.

    **The mutations these kill:** the transaction opened per stream rather than
    per section-week, which the "fails-on-the-second-call" case catches and the
    other cannot see; the failure not caught at all, which stops the walk and is
    caught by assertion 2 in whichever parametrization puts the failing section
    first; and a run that rewrites what it already stored, which assertion 3's
    identity check catches and a row count never would.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    cohorts = two_sections_with_a_closed_week(summary_world, summary_job_contract)
    failing_cohort = cohorts[failing_section]
    healthy_cohort = cohorts["second" if failing_section == "first" else "first"]
    unavailable = summary_contracts.error(UNAVAILABLE_ERROR)

    summary_job_contract.run(
        gateway=StreamAwareGateway(
            summary_contracts,
            fail_on=NONCES[failing_section][failing_stream],
            failure=unavailable("the provider did not answer this request"),
        )
    )

    failed_section = summary_world.section_id(failing_cohort)
    healthy_section = summary_world.section_id(healthy_cohort)

    assert summary_world.summaries(section_id=failed_section) == [], (
        f"the section-week whose {failing_stream} call the provider refused ended with "
        f"{len(summary_world.summaries(section_id=failed_section))} summary row(s). One "
        "transaction covers a section-week's two streams, so a failure on either leaves the week "
        "with neither — a week carrying one of §5.1's two summaries is a report whose halves came "
        "from different runs, and nothing regenerates it (breakdown decision 2)."
    )
    healthy_after_the_failure = summary_world.summaries(section_id=healthy_section)
    assert sorted(
        str(row[summary_job_contract.stream_column]) for row in healthy_after_the_failure
    ) == sorted(summary_job_contract.stored_streams), (
        f"the section the provider answered for ended with {len(healthy_after_the_failure)} "
        "summary row(s). One section-week's provider failure is contained to that section-week; "
        "the walk continues, or one refused call costs an institution its whole Monday."
    )

    before = summary_world.identity_of(healthy_after_the_failure)
    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))

    filled = summary_world.summaries(section_id=failed_section)
    assert sorted(str(row[summary_job_contract.stream_column]) for row in filled) == sorted(
        summary_job_contract.stored_streams
    ), (
        f"the next run left the failed section-week with {len(filled)} summary row(s). The "
        "schedule is this job's only retry — there is no backoff and no queue — so a gap the next "
        "run does not fill is a week with no summary for the rest of the term."
    )
    assert summary_world.identity_of(summary_world.summaries(section_id=healthy_section)) == (
        before
    ), (
        "the second run changed the rows the first run had already written for the section that "
        "succeeded. Their keys, `generated_at` and text are what say so, and a row count would "
        "not: a walk that deleted two rows and wrote two more keeps the count exactly, and puts "
        "different prose under an instructor who has already read the first."
    )


def test_a_failure_that_is_not_the_providers_is_not_swallowed(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
) -> None:
    """The pair to the test above: what the walk tolerates is bounded.

    The walk absorbs a provider failure because SPEC's design says so — nobody is
    waiting, there is no floor for a summary (ADR 0148 point 4), and the schedule
    is the retry. Nothing in that argument covers a defect in the walk itself. A
    `try/except Exception` around the call turns a broken query, a wrong keyword,
    or a schema mismatch into "the provider was unavailable, we will try again on
    Monday" — every Monday, forever, with a job that reports a clean run and a
    report that is silently empty.

    **`docs/MISTAKES.md` entry 26 is the shape** — a fallback path swallowing the
    defect that triggered it — and entry 49 is why the assertion is the raise
    rather than a return value: a walk that collapses "refused" and "broken" into
    one outcome offers nothing a test can read.

    **The second half is the control, and it is not ceremony.** With the same
    world and a gateway that answers, the run must produce its rows — so the raise
    above is a walk that let an unexpected failure through rather than a world
    this suite could not build in the first place.

    **The mutation this kills:** `except Exception` where the ticket means the
    gateway's own error classes, which is the one-word difference between a
    tolerated outage and a permanently silent job.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    cohorts = two_sections_with_a_closed_week(summary_world, summary_job_contract)
    broken = RuntimeError("this is not a provider failure")

    with pytest.raises(RuntimeError) as raised:
        summary_job_contract.run(
            gateway=StreamAwareGateway(
                summary_contracts,
                fail_on=NONCES["first"][INSTRUCTOR_STREAM],
                failure=broken,
            )
        )

    assert raised.value is broken, (
        f"the walk raised {raised.value!r} rather than the failure this test planted. Something "
        "else in the run failed, so this says nothing about what the walk swallows."
    )

    summary_job_contract.run(gateway=StreamAwareGateway(summary_contracts))
    for cohort in cohorts.values():
        section = summary_world.section_id(cohort)
        assert sorted(
            str(row[summary_job_contract.stream_column])
            for row in summary_world.summaries(section_id=section)
        ) == sorted(summary_job_contract.stored_streams), (
            f"the control for the raise above: with a gateway that answers, section {section} "
            f"ended with {summary_world.summaries(section_id=section)} rather than its two rows. "
            "So this world was never one the walk could complete, and the raise proved nothing "
            "about what it tolerates."
        )
