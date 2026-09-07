"""The beat slot and the task beat fires — ticket E4-06, criterion 5.

> The beat inventory test is updated in its own commit (E3-06's dispute
> E3-06-02 settled how the inventory grows), and the entry follows
> `publish_once`.

The ticket settles the slot in its "Decisions this ticket settles": **Monday
02:50**, entered in `BEAT_SCHEDULE` as `"generate-weekly-summaries"`, running
`app.jobs.tasks.generate_weekly_summaries`. Monday because SPEC §3.1 closes every
window on Sunday at 23:59:59 in the institution's timezone and makes reports
available "Monday morning", so Monday is the first day the week that just ended
can be summarized at all and the last day it can be summarized before an
instructor opens the report. 02:50 because E3-06's participation sweep has 02:20
and is provider-free: this job is provider-bound, walks the same sections, and
two jobs that each walk every section in the institution are better apart than on
one tick.

**Why these are unit tests.** Nothing here needs a database, a provider or a
clock: the schedule is a declaration and the task is a registration. Each is a
fact a mutation can change silently — an entry renamed, a `crontab` given
`hour=2` as an integer where every neighbouring entry uses a string, a task
declared and never registered — and none of them would redden an integration
test that drives the walk directly.

**The controls come first and must be green today. A red in that section means
these tests are broken, not the code.**

**Which failure a red here is.** Before E4-06 lands, the criterion tests are
expected red on `pytest.fail` naming `app.jobs.tasks` as a module with no
`generate_weekly_summaries`, and `BEAT_SCHEDULE` as a mapping with no entry under
this ticket's name. Both are plain calls in a test body
(`docs/MISTAKES.md` entry 44).

**The whole-inventory equality is not repeated here.**
`tests/unit/test_celery_app.py` holds it, over the *tasks* rather than the keys,
and E4-06 adds one entry to it in the same change as this module — one fact in
one file, which is how two records are kept from disagreeing.
"""

from typing import Any

import pytest

# No `pytestmark`: `pyproject.toml` declares `integration`, `lti`, `invariant` and
# `slow` and nothing else, and an unmarked module under `tests/unit/` is what
# every other file here is.

# `summary_job_contract` comes from `tests/fixtures/summary_job.py`, reached as a
# fixture rather than imported: an import of a fixtures module by name depends on
# where pytest put `tests/` on `sys.path`, and an import error is not a red.

# The entry this module reads as its control that `BEAT_SCHEDULE` can be read at
# all. E2-06 put `derive_survey_windows` on the schedule and this ticket does not
# touch that declaration.
AN_EXISTING_TASK = "derive_survey_windows"


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """Every criterion here imports an `app.*` module, and one of them builds `Settings`.

    `docs/MISTAKES.md` entry 40, and E3-06's own unit module measured the cost of
    leaving it out: it passed on every developer machine, where `.env` is
    exported, and failed on whichever xdist worker ran it first with a
    `ConfigurationError` naming `DATABASE_URL`. `app.jobs.tasks` imports `app.db`,
    which builds `Settings()` at module scope.

    Declared for the module rather than test by test, because the hazard is the
    module's and the next test added here would have to remember.
    """


def task_named_by(entry: Any) -> str:
    """The task an entry names, however the entry spells it.

    Celery accepts a task's registered name or the task object itself in a beat
    entry and the ticket settles neither, so both are read and reduced to a name:
    the assertion is about *which task runs* rather than about how the entry was
    written.
    """
    named = entry.get("task") if isinstance(entry, dict) else getattr(entry, "task", None)
    return str(getattr(named, "name", named))


def schedule_of(entry: Any) -> Any:
    """The schedule an entry carries."""
    return entry.get("schedule") if isinstance(entry, dict) else getattr(entry, "schedule", None)


def beat_schedule(contract: Any) -> dict[str, Any]:
    """`BEAT_SCHEDULE`, or a failure naming what declares this project's periodic work."""
    found = contract.named_in(
        contract.schedules(),
        contract.beat_schedule_name,
        "E2-06 ships it as the one place this project's periodic work is declared, and "
        "`app.jobs.celery_app` wires it onto the Celery application.",
    )
    assert isinstance(found, dict), (
        f"`{contract.schedules_module_name}.{contract.beat_schedule_name}` is {found!r}, which is "
        "not a mapping. Celery's `beat_schedule` is a dict of entry name to entry, and this module "
        "reads it by name."
    )
    return found


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_beat_schedule_this_module_reads_already_declares_the_window_derivation(
    summary_job_contract: Any,
) -> None:
    """A control: the reader can find an entry, and can tell which task it names.

    The criterion below asserts that one entry is present and names one task. An
    entry lookup that answered nothing for every name, or a task reader that
    answered `None` for every entry, would fail that criterion for a reason having
    nothing to do with E4-06 — and the same two readers, run against an entry
    E2-06 put there and this ticket does not touch, say so here instead.

    Green today.
    """
    schedule = beat_schedule(summary_job_contract)

    assert schedule, (
        f"`{summary_job_contract.beat_schedule_name}` is empty. Five entries have landed since "
        "E1-08, so an empty mapping means this module is reading something other than the schedule "
        "the worker runs."
    )
    named = [
        name for name, entry in schedule.items() if task_named_by(entry).endswith(AN_EXISTING_TASK)
    ]
    assert len(named) == 1, (
        f"{len(named)} entries name a task ending {AN_EXISTING_TASK!r}; the whole schedule reads "
        f"{ {name: task_named_by(entry) for name, entry in schedule.items()} }. This module's task "
        "reader is what the criterion below rests on, and against zero it cannot tell a missing "
        "entry from an entry it cannot read."
    )
    assert schedule_of(schedule[named[0]]) is not None, (
        f"The {named[0]!r} entry carries no schedule this reader can see. Then 'the new entry runs "
        "on this crontab' would be an assertion against `None`."
    )


def test_two_crontabs_this_module_could_confuse_compare_unequal(summary_job_contract: Any) -> None:
    """A control: the schedule comparison below can actually fail.

    The criterion asserts a `crontab` equals the one this ticket settles.
    `crontab` implements its own `__eq__`, and a comparison against something
    that is not a `crontab` at all answers `NotImplemented` and falls back to
    identity — which would make that assertion unfalsifiable. So two schedules
    differing in one field only are required to compare unequal here, and the
    field varied is the **minute**, because the minute is the whole of what
    separates this entry from E3-06's on the same morning.

    Green today. This is arithmetic on Celery's own class.
    """
    from celery.schedules import crontab

    settled = crontab(
        day_of_week=summary_job_contract.beat_day_of_week,
        hour=summary_job_contract.beat_hour,
        minute=summary_job_contract.beat_minute,
    )

    assert settled == crontab(
        day_of_week=summary_job_contract.beat_day_of_week,
        hour=summary_job_contract.beat_hour,
        minute=summary_job_contract.beat_minute,
    ), "Two identically-built crontabs compare unequal, so the criterion below can never pass."
    assert settled != crontab(
        day_of_week=summary_job_contract.beat_day_of_week,
        hour=summary_job_contract.beat_hour,
        minute="20",
    ), (
        "A crontab differing only in its minute compares equal to the settled one, so the criterion "
        "below cannot tell this job's 02:50 from the participation sweep's 02:20 — which is the "
        "one difference between the two entries."
    )
    assert settled != crontab(
        day_of_week="tue",
        hour=summary_job_contract.beat_hour,
        minute=summary_job_contract.beat_minute,
    ), (
        "A crontab differing only in its day compares equal to the settled one, so the criterion "
        "below cannot see a weekly job that moved off Monday."
    )


# ---------------------------------------------------------------------------
# The beat entry and the task.
# ---------------------------------------------------------------------------


def test_the_beat_schedule_runs_the_summary_generation_job_weekly_on_monday_morning(
    summary_job_contract: Any,
) -> None:
    """The ticket's settled slot, asserted as the entry a worker would actually run.

    One entry, under this ticket's own name, naming
    `app.jobs.tasks.generate_weekly_summaries` and carrying
    `crontab(day_of_week="mon", hour="2", minute="50")`.

    **Why the day is load-bearing and not a preference.** SPEC §3.1 closes every
    window on Sunday at 23:59:59 institution time and makes the report available
    Monday morning. A job on any other day either summarizes a week that has not
    finished or leaves the week that has finished unsummarized until after the
    instructor has read the report it leads — and generation is once-and-done
    (breakdown decision 2), so a summary that arrives late never arrives at all
    for that week's reader.

    **Why the minute is.** 02:20 belongs to E3-06's participation sweep, which
    walks every section in the institution without touching a provider; this one
    walks the same sections and makes up to two model calls per section-week. Two
    such walks on one tick contend for the same rows and the same worker pool for
    no reason, and thirty minutes is the gap the ticket settles.

    **The mutations this kills**: the entry declared and never wired, which the
    name lookup catches; the entry pointing at a different task, which is a slot
    that runs something else on Monday morning and looks scheduled; and the
    schedule replaced by a `timedelta`, which drifts with every restart so that
    which hour a week's summaries are generated in depends on when beat last came
    up — and this is the one job whose output an instructor is waiting on at a
    fixed hour.

    **What this does not assert** is that the entry is the only one, or where in
    the mapping it sits. `tests/unit/test_celery_app.py` holds the whole-inventory
    equality; the schedule grows with the project.
    """
    from celery.schedules import crontab

    schedule = beat_schedule(summary_job_contract)

    assert summary_job_contract.beat_entry_name in schedule, (
        f"`{summary_job_contract.beat_schedule_name}` has no "
        f"{summary_job_contract.beat_entry_name!r} entry; it declares {sorted(schedule)}. E4-06 "
        "adds it, and without it the walk has no ordinary trigger at all — the job exists and "
        "nothing ever calls it, which is a Monday report whose AI panels fill in only when "
        "somebody runs a task by hand."
    )
    entry = schedule[summary_job_contract.beat_entry_name]
    assert task_named_by(entry).endswith(summary_job_contract.task_name), (
        f"The {summary_job_contract.beat_entry_name!r} entry names the task "
        f"{task_named_by(entry)!r} rather than one ending {summary_job_contract.task_name!r}. A "
        "slot that runs the wrong task on Monday morning is worse than an empty one, because it "
        "looks scheduled."
    )
    assert schedule_of(entry) == crontab(
        day_of_week=summary_job_contract.beat_day_of_week,
        hour=summary_job_contract.beat_hour,
        minute=summary_job_contract.beat_minute,
    ), (
        f"The entry runs on {schedule_of(entry)!r} and this ticket settles "
        f"`crontab(day_of_week={summary_job_contract.beat_day_of_week!r}, "
        f"hour={summary_job_contract.beat_hour!r}, minute={summary_job_contract.beat_minute!r})`. "
        "Monday because §3.1 closes every window on Sunday at 23:59:59 institution time and puts "
        "the report on Monday morning; 02:50 because 02:20 is E3-06's provider-free sweep over the "
        "same sections."
    )


def test_the_task_beat_fires_is_registered_and_takes_no_argument_but_its_gateway_seam(
    summary_job_contract: Any,
    celery_application_in: Any,
    import_app_module: Any,
) -> None:
    """The task, asserted as the thing beat can actually fire — and as a thing a test can drive.

    Two properties, and each fails differently:

      - **Registered on the application `celery -A app.jobs.celery_app worker`
        starts.** A worker runs that application's registry and nothing else, so a
        task defined against a second Celery instance is enqueued by beat and
        never executed. The symptom is a report whose AI panels are empty every
        Monday, which reads exactly like a provider that is refusing.
      - **No required argument, and a `gateway` seam with a default.** Beat fires
        it with none, so a required parameter is a policy decision (which
        sections, since when) written into a signature where nobody reviewing the
        schedule would look. The optional `gateway` is the work order's settled
        seam, threaded to `summarize_stream`, and it is what every integration
        test in this ticket stands a provider failure or a known answer behind.
        A default is what keeps both true at once.

    **The mutations this kill**: `@shared_task` against a second application; the
    walk given a `section_id` parameter "for the dev trigger", which makes the
    beat entry above unfireable; and the gateway seam omitted, which leaves the
    provider unsubstitutable and criterion 2 unwritable.

    **What this does not assert** is the task's registered name string. Celery
    derives one from the module and the function, the ticket settles neither a
    `name=` override nor its absence, and the beat entry above is matched by
    suffix for the same reason.
    """
    import inspect

    application = celery_application_in(import_app_module("app.jobs.celery_app"))
    task = summary_job_contract.task()

    assert callable(getattr(task, "delay", None)), (
        f"`{summary_job_contract.tasks_module_name}.{summary_job_contract.task_name}` has no "
        f"`delay`, so it is a plain function rather than a registered Celery task and nothing on "
        f"the beat schedule could enqueue it. It is {task!r}."
    )
    registered = getattr(task, "name", None)
    assert registered and registered in application.tasks, (
        f"`{registered}` is not registered on the application in `app.jobs.celery_app` (it holds "
        f"{sorted(n for n in application.tasks if not n.startswith('celery.'))}). The worker runs "
        "that application's registry, so this task would be enqueued every Monday and never run."
    )

    underlying = getattr(task, "run", task)
    parameters = [
        parameter
        for parameter in inspect.signature(underlying).parameters.values()
        if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    required = [parameter.name for parameter in parameters if parameter.default is parameter.empty]
    assert not required, (
        f"`{summary_job_contract.task_name}` requires {required}. A beat entry fires it with no "
        "arguments, so an argument here is a policy decision written into a signature instead of "
        "into the ticket."
    )
    assert any(
        parameter.name == summary_job_contract.gateway_parameter for parameter in parameters
    ), (
        f"`{summary_job_contract.task_name}{inspect.signature(underlying)}` offers no "
        f"`{summary_job_contract.gateway_parameter}` parameter. The work order settles the walk's "
        "optional gateway seam, defaulting to `process_gateway()` — the same seam E4-05 already "
        "publishes on `summarize_stream` — and without it nothing can stand a provider failure or "
        "a known answer in front of this walk, which makes the ticket's second criterion "
        "unwritable rather than merely awkward."
    )
