"""The beat slot and the thin task that runs the crossing — ticket E4-04.

E4-04's work order settles where the crossing is evaluated, which the ticket's
own "Decisions this ticket settles" left open between read-time and a job: a
**beat task** cuts the batches, and the read path only reads them. One writer,
and the read path stays pure — the same shape ADR 0146 argues for at the schema
and E4's breakdown decision 7 argues for at the epic.

The slot: `"cut-release-batches-weekly"` in `BEAT_SCHEDULE`, running
`app.jobs.tasks.cut_release_batches` on `crontab(day_of_week="mon", hour="2",
minute="40")`.

  - **Weekly, and on Monday**, because SPEC §3.1 closes every survey window on
    Sunday at 23:59:59 in the institution's timezone, so Monday is the first day a
    week that has just ended has a final response count at all — and a week's
    count is exactly what decides whether its comments were held.
  - **02:40**, because the minutes ahead of it are taken and their order matters:
    the roster sync at :00, the participation sweep at 02:20, the window
    reconciler at :30, the reclassification passes at :45. A cutter that ran
    *before* the week's classifications settled would count a volume that changes
    under it.

**Why these are unit tests.** Nothing here needs a database, a platform or a
clock: the schedule is a declaration and the task is a registration. Each is a
fact a mutation can change silently — an entry renamed, a `crontab` given
`hour=2` as an integer where its neighbours use strings, a task given a
parameter — and none of them would redden an integration test that calls the
service directly.

**The controls come first and they must be green today. A red in that section
means these tests are broken, not the code.**

**Which failure a red is, before E4-04 lands.** The criterion tests are expected
red on `pytest.fail` naming `app.jobs.tasks` as a module with no
`cut_release_batches`, and on `BEAT_SCHEDULE` as a mapping with no entry under
this ticket's name. Both are plain calls in a test body
(`docs/MISTAKES.md` entry 44).
"""

import inspect
from typing import Any

import pytest

# The entry E2-06 put on the schedule, used as this module's control that
# `BEAT_SCHEDULE` can be read at all and that an entry's task is legible. E4-04
# does not touch it.
AN_EXISTING_TASK = "derive_survey_windows"

# A minute no entry in this project uses, for the control that two crontabs
# differing in one field compare unequal.
A_MINUTE_NOBODY_USES = "17"


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """Every criterion here imports an `app.*` module, and one of them builds `Settings`.

    `docs/MISTAKES.md` entry 40, and the incident
    `tests/unit/test_the_participation_sweep_is_scheduled_weekly_and_run_by_a_task.py`
    records: `app.jobs.tasks` imports `app.db`, which builds `Settings()` at
    module scope, so this module passes on a machine with `.env` exported and
    fails on the xdist worker that happens to run it first. Declared for the
    module rather than test by test, because the hazard is the module's and the
    next test added here would have to remember.

    Nothing here reads the environment and this fixture asserts nothing — it
    states the values the imports run under, which is what entry 40 asks for.
    """


def task_named_by(entry: Any) -> str:
    """The task an entry names, however the entry spells it.

    Celery accepts a task's registered name or the task object itself, and the
    work order settles neither. Both are reduced to a name, so the assertion is
    about *which task runs* rather than about how the entry was written.
    """
    named = entry.get("task") if isinstance(entry, dict) else getattr(entry, "task", None)
    return str(getattr(named, "name", named))


def schedule_of(entry: Any) -> Any:
    """The schedule an entry carries."""
    return entry.get("schedule") if isinstance(entry, dict) else getattr(entry, "schedule", None)


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_beat_schedule_this_module_reads_already_declares_the_window_derivation(
    comment_contract: Any,
) -> None:
    """A control: the reader can find an entry, and can tell which task it names.

    The criterion below asserts that one entry is present and names one task. An
    entry lookup that answered nothing for every name, or a task reader that
    answered `None` for every entry, would fail that criterion for a reason having
    nothing to do with E4-04 — and the same two readers, run against an entry
    E2-06 put there and this ticket does not touch, say so here instead.

    Green today.
    """
    schedule = comment_contract.schedule()

    assert schedule, (
        f"`{comment_contract.beat_schedule_name}` is empty. Five entries had landed before this "
        "ticket, so an empty mapping means this module is reading something other than the "
        "schedule the worker runs."
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


def test_two_crontabs_this_module_could_confuse_compare_unequal(comment_contract: Any) -> None:
    """A control: the schedule comparison below can actually fail.

    The criterion asserts a `crontab` equals the one the work order settles.
    `crontab` implements its own `__eq__`, and a comparison against something that
    is not a `crontab` at all answers `NotImplemented` and falls back to identity,
    which would make that assertion unfalsifiable. So two schedules differing in
    one field are required to compare unequal here.

    Green today. This is arithmetic on Celery's own class.
    """
    from celery.schedules import crontab

    settled = crontab(
        day_of_week=comment_contract.beat_day_of_week,
        hour=comment_contract.beat_hour,
        minute=comment_contract.beat_minute,
    )

    assert settled == crontab(
        day_of_week=comment_contract.beat_day_of_week,
        hour=comment_contract.beat_hour,
        minute=comment_contract.beat_minute,
    ), "Two identically-built crontabs compare unequal, so the criterion below can never pass."
    assert settled != crontab(
        day_of_week=comment_contract.beat_day_of_week,
        hour=comment_contract.beat_hour,
        minute=A_MINUTE_NOBODY_USES,
    ), (
        "A crontab differing only in its minute compares equal to the settled one, so the "
        "criterion below cannot see a slot that moved."
    )
    assert settled != crontab(
        day_of_week="tue",
        hour=comment_contract.beat_hour,
        minute=comment_contract.beat_minute,
    ), (
        "A crontab differing only in its day compares equal to the settled one, so the criterion "
        "below cannot see a weekly job that moved off Monday."
    )


# ---------------------------------------------------------------------------
# The beat entry and the task.
# ---------------------------------------------------------------------------


def test_the_beat_schedule_cuts_release_batches_weekly_on_monday_morning(
    comment_contract: Any,
) -> None:
    """The slot, asserted as the entry a worker would actually run.

    One entry, under this ticket's own name, naming
    `app.jobs.tasks.cut_release_batches` and carrying
    `crontab(day_of_week="mon", hour="2", minute="40")`.

    **Why the day is load-bearing and not a preference.** SPEC §3.1 closes every
    window on Sunday at 23:59:59 in the institution's timezone. A week's response
    count is what decides whether its comments were held below the threshold, and
    that count is not final until the window closes — so Monday is the first day
    the week that just ended can be judged at all.

    **Why the minute is.** The passes ahead of it settle the data this one counts:
    the reclassification sweeps at 00:45 and 01:45 decide which comments survive
    §3.3's validity rule, and 02:20 is the participation sweep's. A cutter running
    in front of them counts a volume that is still moving, and a volume that
    crosses and then un-crosses is a release cut on a number that was wrong.

    **What this does not assert** is that the entry is the only one, or where in
    the mapping it sits. The schedule grows with the project, and the equality
    over the whole set is `tests/unit/test_celery_app.py`'s.

    **The mutations this kills**: the entry declared and never wired, which the
    name lookup catches; the entry pointing at the wrong task, which is a slot
    that runs something else on Monday morning and looks scheduled; and a schedule
    that fires more often than weekly, which for a job that walks every section in
    the institution is a walk that may not finish before the next one starts.
    """
    from celery.schedules import crontab

    schedule = comment_contract.schedule()

    assert comment_contract.beat_entry_name in schedule, (
        f"`{comment_contract.beat_schedule_name}` has no "
        f"{comment_contract.beat_entry_name!r} entry; it declares {sorted(schedule)}. E4-04's work "
        "order adds it, and without it the cutter has no ordinary trigger at all — the crossing "
        "would be evaluated only when somebody ran a task by hand, and SPEC §4's 'they surface as "
        "raw text once the volume crosses' would never happen for any section."
    )
    entry = schedule[comment_contract.beat_entry_name]
    assert task_named_by(entry).endswith(comment_contract.task_name), (
        f"The {comment_contract.beat_entry_name!r} entry names the task "
        f"{task_named_by(entry)!r} rather than one ending {comment_contract.task_name!r}. A slot "
        "that runs the wrong task on Monday morning is worse than an empty one, because it looks "
        "scheduled."
    )
    assert schedule_of(entry) == crontab(
        day_of_week=comment_contract.beat_day_of_week,
        hour=comment_contract.beat_hour,
        minute=comment_contract.beat_minute,
    ), (
        f"The entry runs on {schedule_of(entry)!r} and E4-04's work order settles "
        f"`crontab(day_of_week={comment_contract.beat_day_of_week!r}, "
        f"hour={comment_contract.beat_hour!r}, minute={comment_contract.beat_minute!r})`. Monday "
        "because SPEC §3.1 closes every window on Sunday at 23:59:59 institution time, so it is "
        "the first day a week's response count is final; 02:40 because the 00:45 and 01:45 "
        "reclassification passes and the 02:20 participation sweep have run by then, and a cutter "
        "in front of them counts a comment volume that is still moving."
    )


def test_the_task_that_cuts_the_batches_is_a_celery_task_taking_no_arguments(
    comment_contract: Any,
) -> None:
    """The thin task, asserted as the thing beat can actually fire.

    `derive_survey_windows`' shape exactly: no arguments, so beat can call it with
    none; registered on the Celery application, so the worker finds it; and
    publishable, so the schedule entry above has something to enqueue.

    **The mutation this kills**: the cutter's task given a parameter — a section
    id, a term, a "since" instant — which reads as flexibility and makes the beat
    entry impossible to fire without arguments nobody has decided. A parameter
    with a *default* is caught too, because a default in a task signature is the
    value every scheduled run will use, chosen where nobody reviewing the schedule
    would look.

    **What this does not assert** is the task's registered name. Celery derives
    one from the module and the function, the work order settles neither a `name=`
    override nor its absence, and the entry above is asserted against the
    function's own name by suffix for the same reason.
    """
    task = comment_contract.task()

    assert callable(getattr(task, "delay", None)), (
        f"`{comment_contract.tasks_module}.{comment_contract.task_name}` has no `delay`, so it is "
        "a plain function rather than a registered Celery task and nothing on the beat schedule "
        f"could enqueue it. It is {task!r}. `tests/unit/test_celery_app.py` is where the "
        "registration of the tasks beside it is asserted."
    )
    underlying = getattr(task, "run", task)
    parameters = list(inspect.signature(underlying).parameters.values())
    required = [
        parameter
        for parameter in parameters
        if parameter.default is parameter.empty
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    assert not required, (
        f"`{comment_contract.task_name}` requires {[p.name for p in required]}. The work order "
        "gives it `derive_survey_windows`' shape — no arguments — because a beat entry fires it "
        "with none, and an argument here is a policy decision (which sections, since when) written "
        "into a signature instead of into the work order."
    )
    optional = [parameter for parameter in parameters if parameter.default is not parameter.empty]
    assert not optional, (
        f"`{comment_contract.task_name}` takes {[p.name for p in optional]} with defaults. A "
        "scheduled run takes no arguments, so a default here is the same policy decision one step "
        "further out of sight."
    )
