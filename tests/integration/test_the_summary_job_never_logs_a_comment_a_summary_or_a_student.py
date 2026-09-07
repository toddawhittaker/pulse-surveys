"""What the Monday walk may write to a log stream — ticket E4-06, criterion 6.

> No log line from a planted failing run contains comment text or an identifier —
> asserted with log capture widened to this module, the E3-06 pattern.

and the ticket's scope: "log discipline: section, outcome, duration — never
comment text, never a summary, never a user id (E3's decision 10, extended)."

This is a SPEC §4 matter rather than a tidiness one. §10 requires no student
personally identifiable information in logs; §4 makes identity reachable only
through the Care queue and only with an audit row, and a log line reaches it with
neither. A comment is the most identifying thing a student writes — §4 randomises
comment display order and never shows a timestamp beside one, precisely because
*when* somebody said something narrows who said it, and a log line carries a
timestamp by construction. This job reads **every comment in the system** on its
way through, which is what its own ticket header names as the review surface.

**A generated summary is on the forbidden list beside the comments**, and it is
the addition this job makes to E3's decision 10. A summary of a three-comment
week is a paraphrase of three students, sitting in an operator's stream with the
section beside it — and unlike a comment, it is a value the walk is holding at
exactly the moment it is most tempted to log something ("stored summary X for
section Y").

**The run is a failing one, on purpose.** The success path's log lines are
written by somebody thinking about a happy case; the failure path is written by
somebody debugging, and it is the one that interpolates what it was holding.

**The capture is proved before it is trusted** — `docs/MISTAKES.md` entry 3's
canary rule, twice over. A canary goes through each logger prefix this module
reads, so a prefix that has stopped being read fails a control rather than
quietly narrowing the search; and the run itself is required to have logged
something of its own, because "no comment in the logs" is trivially true of a job
that writes no logs at all — which is exactly the tree this module is first run
against.

**`app.ai` is deliberately outside this search, and the reason is a boundary
rather than an oversight.** What the summary task and the gateway put in a message
is E4-05's subject and has its own two modules asserting it
(`tests/unit/test_the_weekly_summary_task.py` and
`tests/integration/test_ai_gateway_summary_roundtrip.py`, both of which plant a
needle comment and read the whole exception chain). What is asserted here is what
*this job* writes, under the two package prefixes the walk can live in.

**This module is in the §4.1 invariant pass.** What it forbids a log stream to
carry is a student's comment text and their LMS user id — SPEC §4's first line
reaching the one surface every operator can read without a role at all. A denial
nobody runs is a rule that ships unenforced, so CI runs it in the isolated pass
and treats a skip, an xfail or an empty collection as a failure
(`scripts/ci/check_invariants.py`).

**Which failure a red here is.** Before E4-06 lands, expected red on
`pytest.fail` naming `app.jobs.tasks` as a module with no
`generate_weekly_summaries` — a plain call in a test body
(`docs/MISTAKES.md` entry 44).
"""

import logging
from typing import Any

import pytest
from fixtures.ags_client import logged_text
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    A_SUMMARY_TEXT,
    A_THEME_LABEL,
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    StreamAwareGateway,
    SummaryWorld,
    comment_text,
)

pytestmark = [pytest.mark.invariant, pytest.mark.integration]

UNAVAILABLE_ERROR = "AIProviderUnavailableError"

RESPONSES_THAT_WEEK = 3

# The two package prefixes the walk can live under: the task is in
# `app.jobs.tasks` and the ticket leaves the walk itself free to sit in a service
# module (SPEC §13 puts services under `backend/app/services/`). Both are read,
# and each gets a canary of its own so a dropped prefix fails a control instead of
# narrowing the search in silence (`docs/MISTAKES.md` entry 35).
JOB_LOGGER_PREFIXES = ("app.jobs", "app.services")

# One canary per prefix, in tokens of its own so a failure says *which* logger
# went uncaptured. Each travels as a **format argument** rather than in the
# template, so a reader that looked at `record.msg` alone fails here rather than
# reporting a clean stream elsewhere.
CANARIES = {
    "app.jobs": "e4-06-canary-jobs-5b71c2",
    "app.services": "e4-06-canary-services-9f30da",
}
A_CANARY_TEMPLATE = "control line for the summary job's log-policy assertion: %s"

# The nonces the two sections' comments carry, and the subjects their students
# hold. Tokens that appear nowhere else in this repository, so a match in a log
# stream is evidence rather than a coincidence.
HEALTHY_NONCE = "Dq6VmXt2Nb"
FAILING_NONCE = "Sy9WkRz5Cp"


def two_sections_one_of_which_fails(world: SummaryWorld, contract: Any) -> dict[str, list[str]]:
    """Two sections with the same week closed, and everything a log line may not carry.

    Answers with the comment texts and the LMS user ids this world holds, which is
    what the prohibition is written over: the *exact* strings this run read, never
    strings composed here to look like them.
    """
    world.build(contract.a_cohort)
    world.add_section(contract.another_cohort)
    comments: list[str] = []
    subjects: list[str] = []
    for cohort, nonce in (
        (contract.a_cohort, HEALTHY_NONCE),
        (contract.another_cohort, FAILING_NONCE),
    ):
        for index in range(RESPONSES_THAT_WEEK):
            subject = f"{nonce}-subject-{index}"
            instructor = comment_text(INSTRUCTOR_STREAM, f"{nonce}-i{index}")
            course = comment_text(COURSE_STREAM, f"{nonce}-c{index}")
            world.respond(
                subject,
                cohort=cohort,
                term_week=A_CLOSED_TERM_WEEK,
                instructor_comment=instructor,
                course_comment=course,
            )
            comments.extend((instructor, course))
            subjects.append(subject)
    world.clock_after(A_CLOSED_TERM_WEEK)
    world.commit()
    return {"comments": comments, "subjects": subjects}


def records_under(caplog: pytest.LogCaptureFixture, *prefixes: str) -> list[Any]:
    """Every captured record written by one of `prefixes` or by a child of it."""
    return [
        record
        for record in caplog.records
        if any(record.name == prefix or record.name.startswith(f"{prefix}.") for prefix in prefixes)
    ]


def test_a_failing_run_names_the_section_and_quotes_no_student(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    summary_contracts: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Criterion 6, over a run where one section-week's provider call fails.

    Three things must be in the captured stream and four kinds of thing must not.

    **Present.** The section the walk was working on, so an operator reading a
    failed Monday can tell which section to look at — the ticket's scope names
    "section, outcome, duration" as what a line carries. Either handle satisfies
    it: the section's key or its `lms_section_code`, because the ticket settles
    that the section is named and not how, and both name it exactly. And an
    outcome distinguishable from a clean run, asserted as a record at `WARNING`
    or above rather than as a sentence — which words a line uses is the
    implementer's, and a test that pinned one would be writing the log message
    rather than the rule.

    **Absent.** Every comment the run read, the summary it generated for the
    section that succeeded, the theme label the model wrote, and every student's
    `lms_user_id`. Each is the exact string this run handled, taken from the
    world rather than composed here.

    **Three controls stand in front of the prohibition and all must hold.** A
    canary through each of the two logger prefixes, so a reader that had stopped
    seeing one says so instead of reporting a clean stream; the run's own output,
    so the silence is discipline rather than a job that says nothing; and the
    forbidden values proved to have been *handled* — the comments reached the
    gateway and the summary reached the table — because a message cannot leak text
    that was never there.

    **The whole record is read and not the template**, through
    `fixtures/ags_client.py`'s `logged_text`: `logger.info("stored %s", summary)`
    has a template carrying nothing and a rendered message carrying everything,
    and `exc_text` is folded in because a traceback carries the arguments a raise
    was built from.

    **The mutations these kill:** `logger.info("summarized %s for %s", summary,
    section)`, which is the line somebody writes while checking the walk works and
    never takes out; a failure path that logs the caught exception's own
    arguments; a debug line dumping the comments a stream was about to send; and
    a per-student line naming the `lms_user_id` of whoever wrote a comment.

    **What this does not assert** is that any particular sentence is logged, and
    it does not assert the duration the ticket's scope also names — a number of
    seconds has no checkable form and a test that invented one would be pinning a
    log format the ticket does not settle. What is fixed here is the set of values
    that may not appear, which is `docs/MISTAKES.md` entry 2's rule: asserting the
    forbidden state keeps working when a legitimate second log line arrives.
    """
    summary_job_contract.require_table(summary_world.world.tables)
    planted = two_sections_one_of_which_fails(summary_world, summary_job_contract)
    failing_section = summary_world.section_id(summary_job_contract.another_cohort)
    failing_row = dict(summary_world.world.sections[summary_job_contract.another_cohort])
    unavailable = summary_contracts.error(UNAVAILABLE_ERROR)
    gateway = StreamAwareGateway(
        summary_contracts,
        fail_on=f"{FAILING_NONCE}-c",
        failure=unavailable("the provider did not answer this request"),
    )

    caplog.set_level(logging.DEBUG)
    for prefix in JOB_LOGGER_PREFIXES:
        caplog.set_level(logging.DEBUG, logger=prefix)

    summary_job_contract.run(gateway=gateway)

    # -- the forbidden values were really handled by this run -----------------
    sent = "\n".join(gateway.prompts)
    reached = [comment for comment in planted["comments"] if comment in sent]
    assert reached, (
        "not one of the comments this world planted reached the gateway, so a prohibition on "
        "logging them would hold of a run that read nothing (`docs/MISTAKES.md` entry 3)."
    )
    healthy = summary_world.summaries(
        section_id=summary_world.section_id(summary_job_contract.a_cohort)
    )
    assert any(row[summary_job_contract.text_column] == A_SUMMARY_TEXT for row in healthy), (
        f"no row carries {A_SUMMARY_TEXT!r}, so the summary this test forbids the logs to quote "
        "was never generated and that half of the prohibition is about nothing."
    )

    # -- the capture can see what the job writes ------------------------------
    written = records_under(caplog, *JOB_LOGGER_PREFIXES)
    assert written, (
        f"the run wrote no log record at all under {list(JOB_LOGGER_PREFIXES)}. The ticket's scope "
        "gives the job a line per section carrying the section, the outcome and the duration, and "
        "§6.1's console is what reads them. With none, the prohibition below is satisfied by a job "
        "that says nothing about anything — which is what an unbuilt walk does, so this guard is "
        "what stops this test going green for the wrong reason."
    )
    for prefix, canary in CANARIES.items():
        logging.getLogger(prefix).info(A_CANARY_TEMPLATE, canary)
    text = logged_text(records_under(caplog, *JOB_LOGGER_PREFIXES))
    for prefix, canary in CANARIES.items():
        assert canary in text, (
            f"the canary {canary!r} is not in the captured text, and it was written through "
            f"`{prefix}` at info as a format argument. So either this capture cannot see that "
            "logger, or the reader is looking at templates rather than rendered messages — and "
            "either way the search below has gone blind and would report a clean stream whatever "
            "the walk wrote."
        )

    # -- what a line must name ------------------------------------------------
    section_handles = [str(failing_section), str(failing_row.get("lms_section_code", ""))]
    assert any(handle and handle in text for handle in section_handles), (
        f"nothing the run logged names the section it failed on ({section_handles}). The ticket's "
        "scope gives a line the section, the outcome and the duration, and a Monday that failed "
        "for one section out of five hundred is unreadable without the first of those. Either "
        "handle counts — the key or the section code — because the ticket settles that the section "
        f"is named and not which spelling. What was logged:\n{text}"
    )
    assert any(record.levelno >= logging.WARNING for record in written), (
        "every record this run wrote is below `WARNING`, and one section-week's provider call "
        "failed. The outcome is half of what the scope puts on a line; a failure an operator has "
        "to grep for at debug level is a failure nobody sees. Which words the line uses is not "
        "asserted — only that a failed section is distinguishable from a clean one."
    )

    # -- what no line may carry ----------------------------------------------
    forbidden: dict[str, str] = {}
    for comment in planted["comments"]:
        forbidden[comment] = (
            "a comment's text — the most identifying thing a student writes, which §4.1 item 3 "
            "keeps from instructors below the threshold and which §4 never shows with a timestamp "
            "beside it. A log line has a timestamp by construction"
        )
    for subject in planted["subjects"]:
        forbidden[subject] = (
            "an LMS user id — SPEC §4 keys every response to it and makes re-identification "
            "reachable only through the Care queue with an audit row; a log line reaches it with "
            "neither"
        )
    forbidden[A_SUMMARY_TEXT] = (
        "a generated summary — a paraphrase of a week's comments, which in a small-N week is a "
        "paraphrase of two or three students, sitting in an operator's stream with the section "
        "beside it"
    )
    forbidden[A_THEME_LABEL] = (
        "a theme label — prose the model wrote out of the week's own words, which is how a "
        "student's phrase reaches a log without any comment being logged"
    )

    leaked = sorted(value for value in forbidden if value in text)
    assert not leaked, (
        f"the captured log stream carries {leaked[:3]}, and {forbidden[leaked[0]]}. The ticket's "
        "scope: 'section, outcome, duration — never comment text, never a summary, never a user "
        "id.' A log stream is read by operators, shipped to whatever aggregator a deployment runs, "
        "and retained on a schedule this project did not choose.\n\n"
        "The two shapes worth checking first are an f-string in a per-section line and a caught "
        "exception interpolated into a message — E4-05's task is careful never to quote the week "
        "back into what it raises, and a job that logs `repr(error)` beside its own inputs undoes "
        f"that in one line.\n\nThe whole captured text was:\n{text}"
    )
