"""What the job is allowed to write to a log stream — ticket E3-06, criterion 7.

> No log line the task emits contains a score, a ledger line, or an LMS user id —
> asserted over captured log output, with a control line proving the capture
> actually sees what the task logs.

The ticket's scope states the policy in one sentence: "the task logs the section,
the outcome and the call, and never a score, a ledger line, or an LMS user id."
This is the security surface the ticket's own header names — "its logs are the
place a participation figure would leak into a log stream" — and it is a §4
matter rather than a tidiness one. A log line naming an `lms_user_id` beside a
participation percentage is a per-student statement about somebody's standing,
written into a stream that is read by operators, shipped to whatever aggregator a
deployment runs, and retained on a schedule nobody in this project chose. SPEC §4
makes re-identification reachable only through the Care queue and only with an
audit row; a log line reaches it with neither.

**Three forbidden things and each hides differently.** The score is a short
numeric string, so the world it is asserted over is built to make it a *fraction*
— a value containing a decimal point cannot be a substring of a uuid, and a bare
`100` in a log line could be anything. The ledger lines are long and distinctive.
The `lms_user_id` is the AGS `userId` and the thing §4 is actually about.

**The capture is proved before it is trusted.** `docs/MISTAKES.md` entry 3's
canary rule: a search that has gone blind reports the same clean result as a
service that logs nothing. So a line with a string certainly present is put
through the same logger at the same level and the extractor is required to find
it — and, separately, the run under test is required to have logged **something**
of its own, because "no score in the logs" is trivially true of a service that
writes no logs at all.

**Three loggers, not two, and the third was a hole a security review found.**
This module read `app.services.grading` and `app.jobs.tasks` and stopped there,
while the sweep's every HTTP call goes through `app.lti.ags` — which is the
module that logs a call's URL and status, holds E3-04's `recorded=` redaction of
the query string, and says in its own docstring why a transport error's text is
never written out. A regression in that redaction would put a `sub` into the
stream through a logger neither test was looking at, and both would have stayed
green. The prefix is captured here now, and **each canary goes through its own
logger** so that dropping a prefix from the reader fails a control rather than
quietly narrowing the search.

**Format arguments are read, not only templates.** `logger.info("posted %s",
score)` has a template with no score in it and a record whose rendered message
carries one. `ags_contract.logged_text` folds in `getMessage()`, the raw `args`
and `exc_text` for exactly that reason, and the canary goes through a format
argument so that a build of the extractor which stopped reading them says so.

**Which failure a red here is.** Before E3-06 lands both tests are expected red
on `pytest.fail` naming `app.services.grading` as a module that exposes no
`post_scores_for_all_sections`, or `app.jobs.tasks` as one that exposes no
`post_participation_scores` — plain calls in a test body
(`docs/MISTAKES.md` entry 44).
"""

import logging
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks` and `sweep_contract` come from `tests/fixtures/grade_sweep.py`;
# `ags_contract` from `tests/fixtures/ags_client.py`; `line_item_contract` from
# `tests/fixtures/line_item_creation.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`.

# A question set of three, so a student who answers one week in full and one week
# in part earns a fraction rather than a round number. **This is the instrument,
# not a decoration**: a score of `90` is a two-character string that occurs in
# hexadecimal identifiers, in byte counts and in durations, so a search for it
# across a log stream would report leaks that are not there — and a search
# narrowed enough to avoid that would miss the leak it exists to catch. A value
# carrying a decimal point cannot appear inside a uuid at all.
A_QUESTION_COUNT = 3

# The string the canary line carries. Nothing else in this repository contains
# it, and it travels as a **format argument** rather than in the template, so an
# extractor that read `record.msg` alone fails here rather than reporting a clean
# log stream elsewhere.
A_CANARY = "e3-06-canary-8f21c4"

# The second canary, written through `app.lti.ags` and through nothing else. A
# string of its own rather than the one above, because what it has to be able to
# report is *which* logger went uncaptured: with one shared value, a reader that
# had lost the AGS prefix would still find the canary the grading logger carried
# and the control would pass over a search that no longer looks at the HTTP path.
AN_AGS_CANARY = "e3-06-canary-ags-3d70b2"

# What the canary line's template says. Deliberately carries no value of its own.
A_CANARY_TEMPLATE = "control line for the log-policy assertion: %s"


def records_from(caplog: pytest.LogCaptureFixture, *prefixes: str) -> list[Any]:
    """Every captured record written by one of `prefixes` or by a child of it."""
    return [
        record
        for record in caplog.records
        if any(record.name == prefix or record.name.startswith(f"{prefix}.") for prefix in prefixes)
    ]


def a_world_with_a_fractional_score(
    gradebooks: Any,
    sweep_contract: Any,
    committed_clock_overrides: Any,
) -> tuple[Any, Any]:
    """One section, one student, two elapsed weeks and a score that is not a round number."""
    book = gradebooks(question_count=A_QUESTION_COUNT)
    (student,) = sweep_contract.students(book, 1)
    book.world.answer_week(student, 1)
    book.world.answer_week(student, 2, positions=[1])
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, 2)
    return book, student


def forbidden_in(score: Any, student: Any) -> dict[str, str]:
    """The strings no log line may carry, each with the reason it may not.

    Taken from the formula's own answer and from the `user` row, never composed
    here: what must not leak is the exact value this run computed and the exact
    subject it computed it for.
    """
    forbidden = {
        score.percentage: (
            "a participation score — §3.4's figure for one named student, which is a statement "
            "about their standing"
        ),
        student.subject: (
            "an LMS user id — SPEC §4 keys every response to it and makes re-identification "
            "reachable only through the Care queue with an audit row; a log line reaches it with "
            "neither"
        ),
    }
    for line in score.ledger.splitlines():
        if line.strip():
            forbidden[line] = (
                "a ledger line — §3.4's per-week arithmetic, which is the score itemised and is "
                "therefore the score plus how it was reached"
            )
    return forbidden


def assert_nothing_forbidden(text: str, forbidden: dict[str, str], where: str) -> None:
    """Require that none of `forbidden` appears in `text`, naming the first that does."""
    leaked = sorted(value for value in forbidden if value in text)
    assert not leaked, (
        f"{where} contains {leaked}, and {forbidden[leaked[0]]}. The ticket's scope: 'the task logs "
        "the section, the outcome and the call, and never a score, a ledger line, or an LMS user "
        "id.' A log stream is read by operators, shipped to whatever aggregator a deployment runs, "
        "and retained on a schedule this project did not choose.\n\n"
        "The two shapes worth checking first are an f-string in a per-student line, and an "
        "exception interpolated into a message — `app/lti/ags.py` documents why a transport error's "
        "text is never written out, because the URL inside it can carry a `sub`.\n\n"
        f"The whole captured text was:\n{text}"
    )


def test_the_sweep_logs_the_section_and_the_outcome_and_never_the_figures(
    gradebooks: Any,
    sweep_contract: Any,
    ags_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Criterion 7 over the service, where every per-section and per-student line is written.

    One section, one student with a fractional score, one sweep. Afterwards
    nothing written under `app.services.grading` **or under `app.lti.ags`**, or
    below either, carries the score, any line of the ledger, or the student's
    `lms_user_id`. The second prefix is where the sweep's HTTP calls are logged
    and it was outside this search until a security review said so: the redaction
    that keeps a `sub` out of a recorded URL lives there, and nothing in this
    module could see it fail.

    **Three controls stand in front of the assertion and all must hold.**

      - The canary: a line carrying a string certainly present, through the same
        logger at the same level, with the value in a *format argument*. If the
        extractor cannot find that, it cannot find a leak either and a green
        here means nothing.
      - A second canary through `app.lti.ags`, so that the widened search is
        proved rather than declared. A reader that lost that prefix would still
        find the first canary and would report a clean stream having stopped
        looking at the HTTP path.
      - The run's own output: at least one record from the sweep itself. D11
        gives it per-section counts at info or warning and a task-level summary,
        and without any of them "the logs carry no score" is true of a service
        that logs nothing — which is precisely the tree this test was written
        against, so the guard is what stops it going green for the wrong reason
        the day a stub lands.

    **The mutations this kills**: a per-student `logger.info("posted %s for %s",
    score, user.lms_user_id)`, which is the line somebody writes while debugging
    and never takes out; a warning that interpolates the `ParticipationScore`
    object, whose `repr` carries both the percentage and the ledger; a failure
    path that logs a caught exception's text, which for a transport error can
    carry a URL with a `sub` in it (`app/lti/ags.py` says so in its own
    docstring); and — since the capture widened — E3-04's `recorded=` redaction
    dropped, which puts the `userId` in a Score URL's query string into the call
    log through a logger this test used to be blind to.

    **What this deliberately does not assert** is that any particular sentence is
    logged. Which words a line uses is the implementer's; what the ticket fixes
    is the set of values that may not appear, and asserting the forbidden state
    rather than the permitted one is `docs/MISTAKES.md` entry 2's rule — it goes
    on working when a legitimate second log line arrives.
    """
    book, student = a_world_with_a_fractional_score(
        gradebooks, sweep_contract, committed_clock_overrides
    )
    score = sweep_contract.computed(book.world, student, settings=window_settings)
    assert "." in score.percentage, (
        f"The formula answered {score.percentage!r}, which carries no decimal point. This test "
        "searches a whole log stream for that string, and a short round number occurs inside "
        "hexadecimal identifiers, byte counts and durations — so the search would report leaks that "
        f"are not there. The world is built with a {A_QUESTION_COUNT}-question set and one partly "
        "answered week precisely to produce a fraction; a change to either can undo that."
    )
    forbidden = forbidden_in(score, student)
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=sweep_contract.grading_logger)
    caplog.set_level(logging.DEBUG, logger=ags_contract.module)

    _answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r}, so there is no ordinary run to read."
    written = records_from(caplog, sweep_contract.grading_logger)
    assert written, (
        f"The sweep wrote no log record at all under `{sweep_contract.grading_logger}`. D11 gives "
        "it per-section counts at info or warning, and §6.1's console is what reads them. With "
        "none, the assertion below is satisfied by a service that says nothing about anything — "
        "which is what a stub does, so this guard is what stops this test going green for the "
        "wrong reason."
    )

    logging.getLogger(sweep_contract.grading_logger).info(A_CANARY_TEMPLATE, A_CANARY)
    logging.getLogger(ags_contract.module).info(A_CANARY_TEMPLATE, AN_AGS_CANARY)
    text = ags_contract.logged_text(
        records_from(caplog, sweep_contract.grading_logger, ags_contract.module)
    )

    assert A_CANARY in text, (
        f"The canary {A_CANARY!r} is not in the captured text, and it was written through "
        f"`{sweep_contract.grading_logger}` at info as a format argument. So this capture cannot "
        "see what the sweep logs, or the extractor is reading templates rather than rendered "
        "messages — and either way the search below has gone blind and would report a clean log "
        "stream whatever the sweep wrote (`docs/MISTAKES.md` entry 3)."
    )
    assert AN_AGS_CANARY in text, (
        f"The second canary {AN_AGS_CANARY!r} is not in the captured text, and it was written "
        f"through `{ags_contract.module}` — the logger the sweep's every HTTP call goes through. "
        "That prefix is read here because E3-04 redacts the query string of a URL it records and "
        "logs a transport error's status rather than its text; a regression in either writes a "
        "`sub` into this stream, and while this control is failing the search below is not looking "
        "at that logger at all (the review's LOW 4)."
    )
    assert_nothing_forbidden(
        text,
        forbidden,
        f"What the sweep logged under `{sweep_contract.grading_logger}` and `{ags_contract.module}`",
    )


def test_the_task_that_runs_the_sweep_logs_its_totals_and_no_students_figures(
    gradebooks: Any,
    sweep_contract: Any,
    ags_contract: Any,
    line_item_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 7 over the thing the criterion actually names: the task.

    The criterion says "no log line **the task** emits", and the task is a layer
    of its own: D2 gives it a summary line carrying the run's totals, which is
    the one place a number is legitimately written. So this drives
    `app.jobs.tasks.post_participation_scores` — no arguments, its own session,
    one commit — and applies the same three prohibitions to everything written
    under `app.jobs.tasks`, under `app.services.grading` and under `app.lti.ags`
    during it. The third arrived with a security review: the task's HTTP calls
    are logged there, including the URL of every Score post, and neither test in
    this module was reading that logger.

    **The transport seam is substituted, which is the only way a task can reach
    the platform in this process.** D1 has `http` default to
    `outbound_transport()`, the module-level seam E3-05 put there, and neither
    the mock platform's address nor the tool's resolves over a network here.
    `reaching_the_platform` is `tests/fixtures/line_item_creation.py`'s and it
    substitutes the name on `app.services.grading`, so a sweep that built a
    session of its own would post nothing and this test would be reading the
    logs of a run that failed for the harness's reason. That is why the returned
    counts are asserted too.

    **The mutation this kills**: the task's summary line written per section
    rather than in total — "section X: 27 posted" is a count and not a score,
    and it is still one line per section per week naming courses in a stream
    §6.1 already has a console for — and, the one that matters, a summary that
    interpolates the service's return value along with the per-student detail
    somebody added to it.

    **A red that names a session or a connection is this test's own environment
    rather than the ticket's**: the task opens a session through `app.db`, which
    reads `DATABASE_URL`, and the door built by `ags_sections` is what lays that
    down. That case is caught and reported as itself below rather than left to
    read as a log-policy failure.
    """
    book, student = a_world_with_a_fractional_score(
        gradebooks, sweep_contract, committed_clock_overrides
    )
    score = sweep_contract.computed(book.world, student, settings=window_settings)
    forbidden = forbidden_in(score, student)
    task = sweep_contract.task()
    line_item_contract.reaching_the_platform(monkeypatch, book.wire)
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=sweep_contract.tasks_logger)
    caplog.set_level(logging.DEBUG, logger=sweep_contract.grading_logger)
    caplog.set_level(logging.DEBUG, logger=ags_contract.module)

    try:
        answered = task()
    except Exception as escaped:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{sweep_contract.tasks_module_name}.{sweep_contract.task_name}()` raised {escaped!r}. "
            "D2 gives it `derive_survey_windows`'s shape — open a session, call the service, commit "
            "once, return the service's dict — and a raise out of it is a Celery task failure an "
            "operator reads as a traceback.\n\n"
            "If the message names a database connection rather than the sweep, that is this test's "
            "environment: the task opens its own session through `app.db`, whose `DATABASE_URL` is "
            "laid down by the tool the gradebook fixture builds."
        )

    assert answered == {sweep_contract.posted_key: 1, sweep_contract.failed_key: 0}, (
        f"The task answered {answered!r} where one student needed one post. D2 has it return the "
        "service's dict unchanged, and E11's job dashboard is the reader; a run that posted nothing "
        "would also log nothing about a student, so every assertion below would be vacuous."
    )
    written = records_from(caplog, sweep_contract.tasks_logger, sweep_contract.grading_logger)
    assert written, (
        f"Nothing was written under `{sweep_contract.tasks_logger}` or "
        f"`{sweep_contract.grading_logger}` during a task run that posted a score. D11 gives the "
        "task one summary line with the totals; with no records at all the prohibition below holds "
        "of a job that reports nothing to anybody."
    )

    logging.getLogger(sweep_contract.tasks_logger).info(A_CANARY_TEMPLATE, A_CANARY)
    logging.getLogger(ags_contract.module).info(A_CANARY_TEMPLATE, AN_AGS_CANARY)
    text = ags_contract.logged_text(
        records_from(
            caplog,
            sweep_contract.tasks_logger,
            sweep_contract.grading_logger,
            ags_contract.module,
        )
    )

    assert A_CANARY in text, (
        f"The canary {A_CANARY!r} is not in the captured text, and it was written through "
        f"`{sweep_contract.tasks_logger}` at info as a format argument. The search below has gone "
        "blind (`docs/MISTAKES.md` entry 3)."
    )
    assert AN_AGS_CANARY in text, (
        f"The second canary {AN_AGS_CANARY!r} is not in the captured text, and it was written "
        f"through `{ags_contract.module}` — the logger every HTTP call the task makes goes "
        "through. While this control is failing, the assertion below is not reading the module "
        "that records a Score URL, and E3-04's redaction of that URL's query string could be "
        "regressed without a single test in this suite mentioning it (the review's LOW 4)."
    )
    assert_nothing_forbidden(
        text, forbidden, "What the task, the service and the AGS client logged"
    )
