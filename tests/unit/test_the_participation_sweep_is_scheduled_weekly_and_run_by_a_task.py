"""The beat slot, the thin task, and the two module-level values they rest on — ticket E3-06.

The ticket sends this module three of its "Decisions this ticket settles":

> **The beat slot and cadence**, and how the sweep bounds its own work so a
> weekly run does not walk every section of every past term.

> **What the score timestamp names** under a development clock: the
> recomputation's effective now, or real now.

and the scope item above them — "A beat entry and a thin task on
`derive_survey_windows`'s shape."

Work order D3 settles the slot: `crontab(day_of_week="mon", hour="2",
minute="20")`, entered in `BEAT_SCHEDULE` as
`"post-participation-scores-weekly"`. Weekly because the breakdown makes a
weekly beat the ordinary trigger for the sweep; **Monday** because SPEC §3.1
closes every window on Sunday at 23:59:59 in the institution's timezone, so
Monday is the first day on which the week that just ended can be scored;
**02:20** because the reclassification passes at 00:45 and 01:45 have by then had
two attempts at the floored comments of the closing week, and the minutes 0, 15,
30 and 45 are already taken by the entries beside it. Celery beat fires on real
time (ADR 0109's own list); what the sweep *computes* uses the clock service.

**Why these are unit tests.** Nothing here needs a database, a platform or a
clock: the schedule is a declaration, the task is a registration, and
`score_timestamp_text` is a pure function. Each is a fact a mutation can change
silently — an entry renamed, a `crontab` given `hour=2` as an integer where the
neighbouring entries use strings, a rendering that drops microseconds — and none
of them would redden an integration test that drives the service directly.

**The controls come first and they must be green today. A red in that section
means these tests are broken, not the code.**

**Which failure a red here is.** Before E3-06 lands, the criterion tests are
expected red on `pytest.fail` naming `app.jobs.tasks` as a module with no
`post_participation_scores`, `app.services.grading` as one with no
`score_timestamp_text` or `TERM_SWEEP_GRACE_DAYS`, and `BEAT_SCHEDULE` as a
mapping with no entry under this ticket's name. Every one of those is a plain
call in a test body (`docs/MISTAKES.md` entry 44).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

# No `pytestmark` and no `pytest` import. `pyproject.toml` declares
# `integration`, `lti`, `invariant` and `slow` and nothing else, and
# `--strict-markers` refuses any other name; an unmarked module under
# `tests/unit/` is what every other file here is.

# `sweep_contract` comes from `tests/fixtures/grade_sweep.py`, reached as a
# fixture rather than imported: an import of a fixtures module by name depends on
# where pytest put `tests/` on `sys.path`, and an import error is not a red.

# The entry this module reads as its control that `BEAT_SCHEDULE` can be read at
# all. E2-06 put `derive_survey_windows` on the schedule and `tests/e2e/support/
# stack.ts` records the slot it runs in — "`app.jobs.schedules` runs it on
# `crontab(minute="30")`" — so it is a declaration this ticket does not touch.
AN_EXISTING_TASK = "derive_survey_windows"

# An instant with microseconds in a zone that is not UTC, and the string D5's
# definition renders it as. **Written out rather than computed**: a test that
# derived the expectation with `astimezone` and `isoformat` would agree with any
# implementation that made the same mistake (`docs/MISTAKES.md` entry 19).
#
# 2 March 2026 is before daylight time begins on 8 March, so `America/New_York`
# is UTC-5 and 09:05:09.123456 there is 14:05:09.123456 in UTC. The offset is
# spelled `+00:00` and not `Z`, which is `datetime.isoformat`'s own spelling and
# is what the mock platform's grammar requires.
A_LOCAL_INSTANT = datetime(2026, 3, 2, 9, 5, 9, 123456, tzinfo=ZoneInfo("America/New_York"))
ITS_UTC_TEXT = "2026-03-02T14:05:09.123456+00:00"

# The smallest step a `timestamptz` column tells apart (ADR 0019's type, and
# Postgres stores microseconds). A rendering that truncated to the second would
# give these two instants one string, and ADR 0052 would then read two different
# deliveries as retries of each other.
A_MOMENT = timedelta(microseconds=1)


def task_named_by(entry: Any) -> str:
    """The task an entry names, however the entry spells it.

    Celery accepts a task's registered name or the task object itself in a beat
    entry, and the work order settles neither. Both are read and reduced to a
    name, so the assertion is about *which task runs* rather than about how the
    entry was written.
    """
    named = entry.get("task") if isinstance(entry, dict) else getattr(entry, "task", None)
    return str(getattr(named, "name", named))


def schedule_of(entry: Any) -> Any:
    """The schedule an entry carries."""
    return entry.get("schedule") if isinstance(entry, dict) else getattr(entry, "schedule", None)


def beat_schedule(sweep_contract: Any) -> dict[str, Any]:
    """`BEAT_SCHEDULE`, or a failure naming what declares this project's periodic work."""
    found = sweep_contract.named_in(
        sweep_contract.schedules(),
        sweep_contract.beat_schedule_name,
        "E2-06 ships it as the one place this project's periodic work is declared, and "
        "`app.jobs.celery_app` wires it onto the Celery application.",
    )
    assert isinstance(found, dict), (
        f"`{sweep_contract.schedules_module_name}.{sweep_contract.beat_schedule_name}` is "
        f"{found!r}, which is not a mapping. Celery's `beat_schedule` is a dict of entry name to "
        "entry, and this module reads it by name."
    )
    return found


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_beat_schedule_this_module_reads_already_declares_the_window_derivation(
    sweep_contract: Any,
) -> None:
    """A control: the reader can find an entry, and can tell which task it names.

    The criterion below asserts that one entry is *present* and names one task.
    An entry lookup that answered nothing for every name, or a task reader that
    answered `None` for every entry, would fail that criterion for a reason
    having nothing to do with E3-06 — and the same two readers, run against an
    entry E2-06 put there and this ticket does not touch, say so here instead.

    Green today.
    """
    schedule = beat_schedule(sweep_contract)

    assert schedule, (
        f"`{sweep_contract.beat_schedule_name}` is empty. E2-06 put the window derivation on it and "
        "E1-11 the roster sync, so an empty mapping means this module is reading something other "
        "than the schedule the worker runs."
    )
    named = [
        name for name, entry in schedule.items() if task_named_by(entry).endswith(AN_EXISTING_TASK)
    ]
    assert len(named) == 1, (
        f"{len(named)} entries in `{sweep_contract.beat_schedule_name}` name a task ending "
        f"{AN_EXISTING_TASK!r}; the whole schedule reads "
        f"{ {name: task_named_by(entry) for name, entry in schedule.items()} }. This module's task "
        "reader is what the criterion below rests on, and against zero it cannot tell a missing "
        "entry from an entry it cannot read."
    )
    assert schedule_of(schedule[named[0]]) is not None, (
        f"The {named[0]!r} entry carries no schedule this reader can see. Then 'the new entry runs "
        "on this crontab' would be an assertion against `None`."
    )


def test_two_crontabs_this_module_could_confuse_compare_unequal(sweep_contract: Any) -> None:
    """A control: the schedule comparison below can actually fail.

    The criterion asserts a `crontab` equals the one D3 settles. `crontab`
    implements its own `__eq__`, and an implementation that compared loosely —
    or a comparison against something that is not a `crontab` at all and
    answers `NotImplemented`, falling back to identity — would make that
    assertion unfalsifiable. So two schedules that differ in one field only are
    required to compare unequal here.

    Green today. This is arithmetic on Celery's own class.
    """
    from celery.schedules import crontab

    settled = crontab(
        day_of_week=sweep_contract.beat_day_of_week,
        hour=sweep_contract.beat_hour,
        minute=sweep_contract.beat_minute,
    )

    assert settled == crontab(
        day_of_week=sweep_contract.beat_day_of_week,
        hour=sweep_contract.beat_hour,
        minute=sweep_contract.beat_minute,
    ), "Two identically-built crontabs compare unequal, so the criterion below can never pass."
    assert settled != crontab(
        day_of_week=sweep_contract.beat_day_of_week,
        hour=sweep_contract.beat_hour,
        minute="45",
    ), (
        "A crontab differing only in its minute compares equal to the settled one, so the "
        "criterion below cannot see a slot that moved."
    )
    assert settled != crontab(
        day_of_week="tue", hour=sweep_contract.beat_hour, minute=(sweep_contract.beat_minute)
    ), (
        "A crontab differing only in its day compares equal to the settled one, so the criterion "
        "below cannot see a weekly job that moved off Monday."
    )


# ---------------------------------------------------------------------------
# The beat entry and the task.
# ---------------------------------------------------------------------------


def test_the_beat_schedule_runs_the_participation_sweep_weekly_on_monday_morning(
    sweep_contract: Any,
) -> None:
    """D3's slot, asserted as the entry a worker would actually run.

    One entry, under this ticket's own name, naming
    `app.jobs.tasks.post_participation_scores` and carrying
    `crontab(day_of_week="mon", hour="2", minute="20")`.

    **Why the day is load-bearing and not a preference.** SPEC §3.1 closes every
    window on Sunday at 23:59:59 in the institution's timezone and makes reports
    available "Monday morning". A sweep on any other day either scores a week
    that has not finished or leaves the week that has just finished unposted for
    up to six days, which is the delay a student sees.

    **Why the minute is.** The reclassification passes run at 00:45 and 01:45, so
    by 02:20 the floored comments of the week that just closed have had two
    attempts at a real verdict — and a sweep that ran *before* them would post a
    score computed from provisional verdicts and then post again a day later when
    they landed, turning §3.3's fail-open promise into two visible grade changes
    for the same week.

    **The mutations this kills**: the entry declared and never wired, which the
    name lookup catches; the entry pointing at the wrong task, which is a slot
    that runs something else on Monday morning; and the schedule changed to
    something that fires more often than weekly, which against every section in
    an institution is a walk that never finishes before the next one starts.

    **What this does not assert** is that the entry is the only one, or where in
    the mapping it sits. The schedule grows with the project.
    """
    schedule = beat_schedule(sweep_contract)
    from celery.schedules import crontab

    assert sweep_contract.beat_entry_name in schedule, (
        f"`{sweep_contract.beat_schedule_name}` has no {sweep_contract.beat_entry_name!r} entry; "
        f"it declares {sorted(schedule)}. E3-06's work order (D3) adds it, and without it the "
        "sweep has no ordinary trigger at all — the service exists and nothing ever calls it, "
        "which is a gradebook that updates only when somebody runs a task by hand."
    )
    entry = schedule[sweep_contract.beat_entry_name]
    assert task_named_by(entry).endswith(sweep_contract.task_name), (
        f"The {sweep_contract.beat_entry_name!r} entry names the task {task_named_by(entry)!r} "
        f"rather than one ending {sweep_contract.task_name!r}. A slot that runs the wrong task on "
        "Monday morning is worse than an empty one, because it looks scheduled."
    )
    assert schedule_of(entry) == crontab(
        day_of_week=sweep_contract.beat_day_of_week,
        hour=sweep_contract.beat_hour,
        minute=sweep_contract.beat_minute,
    ), (
        f"The entry runs on {schedule_of(entry)!r} and D3 settles "
        f"`crontab(day_of_week={sweep_contract.beat_day_of_week!r}, "
        f"hour={sweep_contract.beat_hour!r}, minute={sweep_contract.beat_minute!r})`. Monday "
        "because §3.1 closes every window on Sunday at 23:59:59 institution time, so it is the "
        "first day the week that ended can be scored; 02:20 because the 00:45 and 01:45 "
        "reclassification passes have by then had two attempts at that week's floored comments, "
        "and a sweep in front of them posts a provisional score and then posts again."
    )


def test_the_task_that_runs_the_sweep_is_a_celery_task_taking_no_arguments(
    sweep_contract: Any,
) -> None:
    """D2's thin task, asserted as the thing beat can actually fire.

    `derive_survey_windows`' shape exactly: no arguments, so beat can call it
    with none; registered on the Celery application, so `app.jobs.tasks` is
    somewhere the worker will find it; and publishable, so the schedule entry
    above has something to enqueue.

    **The mutation this kills**: the sweep given a parameter — a section id, a
    term, a "since" instant — which reads as flexibility and makes the beat entry
    above impossible to fire without arguments nobody has decided. A parameter
    with a default is caught too, because the criterion is that a scheduled run
    takes none: a default value in a task signature is a policy decision hidden
    in a signature rather than written in the work order.

    **What this does not assert** is the task's registered name. Celery derives
    one from the module and function and the work order settles neither a
    `name=` override nor its absence, so pinning it here would decide something
    the ticket left open; the beat entry above is asserted against the function's
    own name by suffix for the same reason.
    """
    import inspect

    task = sweep_contract.task()

    assert callable(getattr(task, "delay", None)), (
        f"`{sweep_contract.tasks_module_name}.{sweep_contract.task_name}` has no `delay`, so it is "
        "a plain function rather than a registered Celery task and nothing on the beat schedule "
        f"could enqueue it. It is {task!r}. `tests/unit/test_celery_app.py` is where the "
        "registration of the tasks beside it is asserted."
    )
    underlying = getattr(task, "run", task)
    required = [
        parameter
        for parameter in inspect.signature(underlying).parameters.values()
        if parameter.default is parameter.empty
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    assert not required, (
        f"`{sweep_contract.task_name}` requires {[p.name for p in required]}. D2 gives it "
        "`derive_survey_windows`' shape — no arguments — because a beat entry fires it with none, "
        "and an argument here is a policy decision (which sections, since when) written into a "
        "signature instead of into the work order."
    )
    optional = [
        parameter
        for parameter in inspect.signature(underlying).parameters.values()
        if parameter.default is not parameter.empty
    ]
    assert not optional, (
        f"`{sweep_contract.task_name}` takes {[p.name for p in optional]} with defaults. A "
        "scheduled run takes no arguments, so a default here is the same policy decision one step "
        "further out of sight: it is what the weekly run will always use, chosen where nobody "
        "reviewing the schedule would look."
    )


# ---------------------------------------------------------------------------
# The two module-level values the sweep's behaviour rests on.
# ---------------------------------------------------------------------------


def test_the_canonical_score_timestamp_is_utc_isoformat_and_keeps_its_microseconds(
    sweep_contract: Any,
) -> None:
    """D5, and why it is a named function rather than a line inside the poster.

    `score_timestamp_text(instant)` is `instant.astimezone(UTC).isoformat()`, and
    what rests on it is ADR 0052's retry identity: a `grade_sync` row stores the
    instant that was sent, and a retry re-renders that stored instant and must
    produce the exact bytes the platform already accepted. One rendering, in one
    place, is what makes that reconstruction sound; two would drift the first
    time somebody preferred `Z` to `+00:00`.

    **Three properties, and each kills a different rendering.**

      - A non-UTC aware instant is **converted**, not relabelled. An instant
        rendered with its original offset is the same moment and different bytes,
        so a stored timestamptz — which Postgres hands back in UTC — would
        re-render differently from what was sent.
      - Microseconds survive. A whole-second rendering gives two instants one
        microsecond apart the same text, and ADR 0052 then reads two different
        deliveries as retries of each other; the comparison it settles is
        "between instants rather than strings or dates" precisely because a
        second is the whole width of the rule.
      - The offset is spelled `+00:00`. That is `isoformat`'s own spelling and
        the one the mock platform's grammar accepts; a client that round-tripped
        the value through a `datetime` and re-rendered it as `Z` would send a
        different body for the same instant.

    **The expected string is written out rather than computed** — a test that
    derived it with `astimezone` and `isoformat` would agree with any
    implementation that made the same mistake (`docs/MISTAKES.md` entry 19).
    """
    render = sweep_contract.timestamp_text()

    assert render(A_LOCAL_INSTANT) == ITS_UTC_TEXT, (
        f"`{sweep_contract.timestamp_text_name}({A_LOCAL_INSTANT!r})` answered "
        f"{render(A_LOCAL_INSTANT)!r} and D5 settles {ITS_UTC_TEXT!r}. The instant is 09:05:09 in "
        "`America/New_York` on a day before daylight time begins, so UTC-5 puts it at 14:05:09Z. "
        "An answer carrying `-05:00` is the same moment relabelled rather than converted, and it "
        "will not match what the same instant re-renders as after a round trip through a "
        "`timestamptz` column."
    )
    assert render(A_LOCAL_INSTANT).endswith("+00:00"), (
        f"The rendering is {render(A_LOCAL_INSTANT)!r}. `datetime.isoformat` spells a UTC offset "
        "`+00:00`; `Z` is the same instant and a different body, and ADR 0052's retry identity is "
        "byte equality of a body the platform already accepted."
    )
    moment = datetime(2026, 3, 2, 14, 5, 9, 123456, tzinfo=UTC)
    assert render(moment) != render(moment + A_MOMENT), (
        f"Two instants one microsecond apart both render as {render(moment)!r}. Postgres stores "
        "microseconds in the column this value comes back from (ADR 0019), so a rendering that "
        "drops them makes two deliveries indistinguishable — and ADR 0052 has the platform accept "
        "the second as a retry of the first, silently."
    )


def test_the_sweep_stops_two_weeks_after_a_term_ends(sweep_contract: Any) -> None:
    """D7's constant, pinned where its value is decided rather than where it is used.

    `TERM_SWEEP_GRACE_DAYS = 14`. Fourteen days is two more weekly sweeps after a
    term's `end_date`: one for the final week's post, one corrective pass for a
    reclassification that lands late. The reason it stops rather than running for
    ever is SPEC §4's retention — raw responses are deleted at the end of the
    retention period and only aggregates persist, so a sweep still walking a
    finished term would eventually recompute every student's score against
    comments that are no longer there and post the answer into a gradebook years
    later.

    **The mutation this kills**: the constant widened — to 30, to 365, to a
    setting — which nothing else in the suite would notice.
    `test_the_sweep_walks_only_sections_whose_term_ended_recently.py` asserts the
    *behaviour* at the boundary and computes both of its dates from this same
    value, so it stays green under any widening; this is the test that says which
    number the boundary is.

    **Why a bare integer rather than a configuration field.** The ticket settles
    it as a decision rather than as a knob, and a value on §6.3's configuration
    surface is one a deployment can set to a number that reaches back past its own
    retention rule. If that ever becomes a knob it needs a bound and a record,
    which is a different change from this one.
    """
    value = sweep_contract.grace()

    assert value == sweep_contract.grace_days_value, (
        f"`{sweep_contract.grace_days_name}` is {value!r} and E3-06's work order (D7) settles "
        f"{sweep_contract.grace_days_value!r}. Two sweeps after a term ends cover the last week's "
        "post plus one corrective pass; a larger number keeps recomputing a finished term until "
        "§4's retention has deleted the comments it is computing from, and a smaller one can miss "
        "the final week's own post."
    )
    assert isinstance(value, int) and not isinstance(value, bool), (
        f"`{sweep_contract.grace_days_name}` is {value!r}, a {type(value).__name__}. It is added to "
        "a date, so a non-integer is a failure at the comparison rather than here."
    )
