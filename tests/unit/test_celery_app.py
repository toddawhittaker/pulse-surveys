"""The Celery application and its wiring — ticket E0-03.

E0-03 stands up a job runtime: `app.jobs.celery_app` builds a Celery
application from `Settings`, `app.jobs.schedules` is the beat schedule module,
and `app.jobs.tasks.ping` exists to prove a round trip. The round trip itself
needs a broker and lives in `tests/integration/test_celery_ping_roundtrip.py`.
What is here is everything about the application's configuration that can be
asserted without one — and, more to the point, the parts of it that every gate
in the pipeline would go green without.

Which parts those are is worth being precise about, because two of the ticket's
scope items *are* covered dynamically and are deliberately not restated here:

  - **A broker that does not answer** is caught by the worker's own health
    check. `celery inspect ping` needs the broker, so a Celery application
    pointed at nothing never reports healthy and `wait_for_health.sh` fails the
    `docker` job.
  - **A result backend that never returns a result** is caught by the
    integration test, which is where the ticket's definition of done puts it.

What nothing catches is where those two values *came from*. A Celery
application with `redis://redis:6379/0` written into it as a literal passes the
health check, passes the round trip, and passes every gate — and then ignores
`REDIS_URL` in any deployment whose broker is somewhere else, which is the one
thing `.env.example` promises it will not do. The same is true of the timezone,
with a longer fuse: SPEC §3.1 puts the survey window at Friday 18:00 in the
institution timezone, beat computes its crontabs in `app.timezone`, and an
application that never reads the setting opens every window in UTC while
reporting healthy. Nothing in E0-03 schedules anything, so the first symptom
would arrive in E2.

The tests below therefore set a value no default could be mistaken for, and
assert the application ends up holding it.

`import_app_module` (in `tests/fixtures/app_imports.py`) is what makes that
possible: it
drops `app.*` out of `sys.modules` so the module is built against the
environment the test just set, rather than against whatever the environment
held the first time some other test imported it.
"""

import zoneinfo
from collections.abc import Callable
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest

CELERY_APP_MODULE = "app.jobs.celery_app"
SCHEDULES_MODULE = "app.jobs.schedules"
TASKS_MODULE = "app.jobs.tasks"

# The ticket names the module and the task ("one trivial `ping` task"), so this
# is the ticket's spelling and not the test's choice.
PING_TASK_ATTRIBUTE = "ping"

# A broker nothing could arrive at by default, by accident, or by copying
# `.env.example`: the host is in the reserved `.invalid` TLD, the port is not
# Redis's, and the database number is not 0. Celery's own defaults are an AMQP
# broker and no result backend at all, so nothing about this value can be
# reached except by reading REDIS_URL.
SENTINEL_REDIS_URL = "redis://broker.test.invalid:6399/3"

# A real IANA zone that is neither Celery's default (UTC) nor the
# `America/New_York` default SPEC §3.1 gives, so an application that hardcodes
# either cannot pass. Same value, and the same reasoning, as
# `test_config_settings.py::VALID_NON_DEFAULT_TIMEZONE`.
SENTINEL_TIMEZONE = "Pacific/Auckland"

REDIS_URL_VARIABLE = "REDIS_URL"
INSTITUTION_TIMEZONE_VARIABLE = "INSTITUTION_TIMEZONE"

# Put into the schedule module by the wiring test and looked for on the other
# side, in the schedule beat would actually read. A token rather than a bare key
# because it goes in the entry as well: an implementation that copies the
# mapping, one that references it, and one that rebuilds entries out of it all
# carry the token somewhere, and none of them can invent it.
SCHEDULE_PROBE_MARKER = "e0-03-schedule-wiring-probe"
SCHEDULE_PROBE_ENTRY = {"task": f"{SCHEDULE_PROBE_MARKER}.never-runs", "schedule": 3600.0}

# The mapping `app.jobs.schedules` exposes for beat. The E0-03 ticket does not
# name it, and this test does not choose the name either — the module exports
# it, annotated and documented above its declaration as Celery's `beat_schedule`
# mapping. What a module exports is a fact about the module, not a guess at it.
#
# An earlier version found the mapping by shape, probing every public `dict` in
# the module because the *ticket* named none. Reviewer pass 2 objected to the
# trap rather than the style, and was right: the day `schedules.py` grows a
# second public mapping — a lookup table, per-job option defaults — a by-shape
# probe writes into that one too, on the theory that it might be the schedule.
# Renaming the attribute now breaks one line here and says which line, which is
# the better failure of the two.
SCHEDULE_MAPPING_ATTRIBUTE = "BEAT_SCHEDULE"

MISSING_MODULE_MESSAGE = (
    "`{module}` does not exist. E0-03 ships it under `backend/app/jobs/` "
    "(SPEC §13 — the `jobs/` package is celery_app.py, schedules.py, tasks.py). "
    "The import root is `backend/`, so the module is `{module}` and never "
    "`backend.{module}`."
)

NO_APPLICATION_MESSAGE = (
    "`{module}` exposes no Celery application at module level. `celery -A "
    "{module} worker` resolves the application by attribute and then by scanning "
    "the module, so an application built only inside a factory function is one "
    "neither the worker service, the beat service, nor the `celery inspect ping` "
    "health check can reach."
)


def endpoint(url: str) -> tuple[str, str | None, int | None]:
    """Scheme, host, and port of a URL — the parts that say *where* it points.

    The path is deliberately left out. `REDIS_URL` carries a database number
    there, and E0-03 does not decide whether the result backend shares the
    broker's database or takes one of its own; comparing it would make that
    choice on the implementer's behalf. Which Redis the two point at is the
    property the ticket does state, and it is the one that breaks a deployment
    when it is wrong.
    """
    parts = urlsplit(url)
    return parts.scheme, parts.hostname, parts.port


def timezone_key(value: Any) -> str:
    """The IANA name of a configured Celery timezone, whatever type it arrived as.

    `Celery.timezone` returns a `tzinfo`: a `ZoneInfo` built from the configured
    name, or UTC when nothing is configured. `str()` of a `ZoneInfo` is its key
    and `str()` of UTC is `UTC`, so this reads both without caring whether the
    implementation handed Celery a string or a `ZoneInfo` — SPEC §3.1 settles
    the zone, not the type, and `test_config_settings.py` leaves the type of
    `Settings.institution_timezone` open on purpose.
    """
    return str(value)


def require_application(
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> Any:
    """The Celery application, or a failed assertion naming what is missing.

    Both steps assert, because "no application" and "no module" are different
    failures with different fixes, and a test whose first line raises
    `AttributeError` on `None` reports neither.
    """
    module = import_app_module(CELERY_APP_MODULE)
    assert module is not None, MISSING_MODULE_MESSAGE.format(module=CELERY_APP_MODULE)

    application = celery_application_in(module)
    assert application is not None, NO_APPLICATION_MESSAGE.format(module=CELERY_APP_MODULE)
    return application


def test_the_jobs_package_exposes_a_celery_application(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> None:
    """`app.jobs.celery_app` exists and holds a Celery application.

    The precondition every other test in this module and in the integration test
    depends on, asserted on its own so that "the ticket has not been built yet"
    reports as one legible failure rather than as six.
    """
    application = require_application(import_app_module, celery_application_in)

    assert application is not None


@pytest.mark.parametrize("setting_name", ["broker_url", "result_backend"])
def test_broker_and_result_backend_point_at_the_configured_redis(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
    setting_name: str,
) -> None:
    """Both come from `REDIS_URL`, not from a literal in the source.

    E0-03 scope: "Celery application configured from `Settings`, Redis broker and
    result backend". `.env.example` documents `REDIS_URL` as the broker and
    result backend, and `test_config_settings.py` already asserts `Settings`
    reads it; this is the other end of that wire.

    Asserted per setting rather than together, because an application that reads
    the variable for its broker and hardcodes its backend is a real and specific
    defect — the broker half is exercised by every gate, so it is the half that
    gets written first and the half a copy-paste gets right.
    """
    monkeypatch.setenv(REDIS_URL_VARIABLE, SENTINEL_REDIS_URL)
    application = require_application(import_app_module, celery_application_in)

    configured = getattr(application.conf, setting_name, None)

    assert configured, (
        f"`{setting_name}` is {configured!r}. Celery leaves the result backend unset and "
        "defaults the broker to AMQP, so an empty value here is what an application that "
        "never read REDIS_URL looks like — and it is also what would make an equality "
        "check below pass against nothing. Read it from `Settings`."
    )
    assert endpoint(str(configured)) == endpoint(SENTINEL_REDIS_URL), (
        f"`{setting_name}` is {configured!r}, which does not point at the "
        f"{REDIS_URL_VARIABLE} this test set ({SENTINEL_REDIS_URL}). A literal broker "
        "address in `celery_app.py` passes the Compose health check and the round-trip "
        "test — both run against the Compose `redis` service, which is where the literal "
        "would point — and then silently ignores the configured broker in every "
        "deployment whose Redis is somewhere else. The database number is not compared: "
        "whether the backend shares the broker's is E0-03's to choose."
    )


def test_the_celery_timezone_follows_the_institution_timezone(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> None:
    """E0-03 scope: "timezone from institution config".

    Beat computes every schedule in `Celery.timezone`, and SPEC §3.1 puts the
    survey window at Friday 18:00 to Sunday 23:59:59 *in the institution
    timezone*. An application that never reads the setting runs on Celery's
    default UTC, which is five hours off the spec's own default and reports
    healthy while being so.

    This is the assertion that stops the line being deleted. Nothing in E0-03
    schedules anything — every real entry is E2, E4 or E13 — so until one lands
    there is no behaviour to notice, and by then the wrong window looks like a
    scheduling bug rather than a configuration one.
    """
    assert zoneinfo.ZoneInfo(SENTINEL_TIMEZONE), (
        f"This machine's IANA database does not resolve {SENTINEL_TIMEZONE}, so this test "
        "cannot tell a Celery application that ignored the setting from a missing tzdata "
        "package. `tzdata` is a pinned runtime dependency precisely so this holds."
    )
    monkeypatch.setenv(INSTITUTION_TIMEZONE_VARIABLE, SENTINEL_TIMEZONE)
    application = require_application(import_app_module, celery_application_in)

    configured = timezone_key(application.timezone)

    assert configured == SENTINEL_TIMEZONE, (
        f"The Celery application runs in {configured!r} with "
        f"{INSTITUTION_TIMEZONE_VARIABLE}={SENTINEL_TIMEZONE} set. `UTC` here means the "
        "timezone was never configured — Celery's default — and any other value means it "
        "was configured from something other than the institution setting. Either way "
        "beat's crontabs fire at the wrong hour (SPEC §3.1)."
    )


def test_the_schedule_beat_reads_is_the_one_the_schedule_module_exposes(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> None:
    """E0-03 scope: the schedule module is "wired and importable", not just present.

    Importable alone is worth nothing here. `app.jobs.schedules` exists to be the
    place a scheduled job goes, and if nothing connects its entries to
    `conf.beat_schedule` then the first entry E2 adds is read by no process:
    beat starts, reports healthy, and runs an empty schedule forever. That
    failure has no symptom — a window that never opens looks like a window
    nobody configured.

    **An earlier version of this test asserted that the module had been
    imported, and that is not the same property.** Reviewer pass 1 on pull
    request #16 demonstrated it by mutation: deleting the two lines that assign
    the mapping to `conf.beat_schedule` and naming the module in the
    application's `include=[...]` instead left this file entirely green.
    `include` makes the *worker* import a module for its task registry and does
    nothing whatever for the beat schedule. Both mechanisms mention the module,
    so no assertion about the module can tell them apart.

    So the mapping itself is followed end to end: put a probe entry into what
    `schedules.py` exposes, then read the schedule the application hands beat
    and require the probe to be in it. That asserts the property and not a
    mechanism — assignment by reference, a copy taken at import, and entries
    rebuilt through `add_periodic_task` all carry the probe across, and nothing
    that merely imports the module can.

    Ordering is load-bearing and is the reason this test does not use
    `require_application`. `import_app_module` empties `app.*` out of
    `sys.modules` before the body runs, so the schedule module must be imported
    and mutated *first*: an implementation that copies the mapping at import
    time copies whatever is in it at that moment, and importing the application
    first would take the copy before the probe existed.
    """
    schedules = import_app_module(SCHEDULES_MODULE)
    assert schedules is not None, MISSING_MODULE_MESSAGE.format(module=SCHEDULES_MODULE)

    exposed = getattr(schedules, SCHEDULE_MAPPING_ATTRIBUTE, None)
    assert isinstance(exposed, dict), (
        f"`{SCHEDULES_MODULE}.{SCHEDULE_MAPPING_ATTRIBUTE}` is {exposed!r} rather than a "
        "mapping, so this test has nothing to put a probe into and cannot tell a wired "
        "schedule from an unwired one. If the mapping has been renamed, point "
        "`SCHEDULE_MAPPING_ATTRIBUTE` at the new name — one line, and the rename stays "
        "visible in the diff. If the schedule is now built some other way — a function, a "
        "signal handler — rewrite the probe around that. What must not happen is falling "
        "back to asserting that the module was imported, which is the assertion reviewer "
        "pass 1 walked straight through."
    )
    exposed[f"{SCHEDULE_PROBE_MARKER}-entry"] = dict(SCHEDULE_PROBE_ENTRY)

    application = require_application(import_app_module, celery_application_in)
    beat_schedule = application.conf.beat_schedule
    if beat_schedule is None:
        beat_schedule = {}

    # Identity is accepted as well as the probe arriving. The two answer the same
    # question at different moments: an implementation that assigns the mapping
    # by reference is wired whether or not the copy timing happened to suit the
    # probe, and saying so here costs one line and removes a false failure that
    # would be very hard to read.
    #
    # `or {}` would have been wrong on this line and worth naming: it swaps an
    # empty mapping for a fresh one, and the identity check below would then be
    # comparing against an object nothing wired.
    carried = SCHEDULE_PROBE_MARKER in repr(dict(beat_schedule))
    shared = exposed is beat_schedule

    assert carried or shared, (
        f"The probe entry put into `{SCHEDULES_MODULE}` does not appear in the schedule the "
        f"application hands beat, which holds {sorted(dict(beat_schedule))}. Nothing "
        "connects the two: beat would read an empty schedule however many entries the "
        "module grows. Naming the module in `include` or `imports` is not this — that "
        "imports it for the worker's task registry and leaves `beat_schedule` untouched. "
        "Assign what the module exposes to `conf.beat_schedule` (or feed it through "
        "`add_periodic_task`)."
    )


# E1-08's entry — the daily purge of the launch replay ledger — and the only
# thing landed in the beat schedule as of this ticket. ADR 0089: the launch
# nonce is stored in Postgres rather than Redis, "and that the native TTL a
# Redis store would have had is replaced by a daily Celery-beat purge." SPEC
# §9.1 requires single-use nonces; a ledger only ever appended to (`INSERT`,
# per `RUNTIME_BASE_TABLE_PRIVILEGES` in `test_identity_grants.py`) grows
# without bound absent this job, so it is part of what makes the
# Postgres-over-Redis choice sustainable rather than an optional extra.
PURGE_NONCES_SCHEDULE_KEY = "purge-expired-launch-nonces"
PURGE_NONCES_TASK_NAME = f"{TASKS_MODULE}.purge_launch_nonces"

# E1-11's entry, spelled by that ticket's work order (D10): "`schedules.py`
# `BEAT_SCHEDULE` gains `"roster-sync-hourly"`, `crontab(minute="0")`", running
# `app.jobs.tasks.sync_rosters`, which walks every section with a stored roster
# address. SPEC §7.3 is where the cadence comes from — "Roster sync: NRPS pulled
# on schedule and on launch (debounced)" — and the stored address is the only
# discovery the scheduled half has: "it has no way of its own to learn that a
# section exists."
ROSTER_SYNC_SCHEDULE_KEY = "roster-sync-hourly"
ROSTER_SYNC_TASK_NAME = f"{TASKS_MODULE}.sync_rosters"
SECTION_ROSTER_TASK_NAME = f"{TASKS_MODULE}.sync_section_roster"

# The minute of the hour that entry fires on, as a `crontab` spells it. Asserted
# because "hourly" and "every 3600 seconds" are different schedules and only one
# of them is what a `crontab(minute="0")` produces: a `timedelta`-scheduled entry
# drifts with every restart, so the hour a section is synced in depends on when
# beat last came up.
ROSTER_SYNC_MINUTE = "0"

# E2-06's entry: the survey-window reconciler, running
# `app.jobs.tasks.derive_survey_windows` on `crontab(minute="30")` — that
# ticket's work order, decision 5. It walks every section and derives the windows
# its calendar implies, so a section that appeared mid-term gets its windows
# without anybody running anything; staleness of up to an hour is accepted and
# recorded in ADR 0111. Minute 30 because minute 0 is the roster sync's, and two
# jobs that both walk every section in the institution are better apart.
#
# **The key this entry is filed under is not asserted, and that is deliberate.**
# The work order settles the task, the module and the cadence and settles no name
# for the schedule entry, so the entry is found by the task it runs. Pinning a key
# here would be this test choosing an identifier the ticket left open.
WINDOW_DERIVATION_TASK_NAME = f"{TASKS_MODULE}.derive_survey_windows"
WINDOW_DERIVATION_MINUTE = "30"


def test_the_beat_schedule_holds_exactly_the_three_entries_that_have_landed(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> None:
    """E1-08 landed the first entry, E1-11 the second and E2-06 the third; this test is the record.

    **Rewritten by E1-08, per this test's own instruction at E0-03.** The
    original docstring: "This test is a record with a shelf life, and that is
    deliberate. The first real entry is meant to make it fail, so that adding
    it is a conversation about which ticket owns the job rather than a line
    that slips in. Whoever lands that entry rewrites this test in the same
    change." E1-08 was that ticket — `purge-expired-launch-nonces`, running
    `app.jobs.tasks.purge_launch_nonces` (ADR 0089's daily purge of the
    replay ledger `app.lti.replay_guard` claims nonces into).

    **E1-11 is the second, and this test is being changed by it exactly as the
    instruction above asks.** `roster-sync-hourly`, running
    `app.jobs.tasks.sync_rosters` on `crontab(minute="0")` — that ticket's work
    order, D10 — because SPEC §7.3 pulls NRPS "on schedule and on launch
    (debounced)" and the scheduled half has no discovery of its own but the
    stored roster address.

    **E2-06 is the third, and the instruction is being followed once more.** The
    survey-window reconciler, running `app.jobs.tasks.derive_survey_windows` on
    `crontab(minute="30")`, which walks every section and derives the windows its
    calendar implies. It exists because the derivation has to reach a section that
    appears in the middle of a term — a launch or a roster sync creates one at any
    hour — and E2-06 deliberately does not hook the writer into those flows, which
    would put its diff inside E2-02's ingestion surface. ADR 0111 records the
    choice and the staleness it accepts. Of the jobs E0-03 named, Monday reports
    are still E4's and retention purges still E13's; if one of those has now landed
    too, this test is again the record that has to change with it.

    **An equality rather than a superset, and E1-11 paid for that choice while
    E2-06 pays for it again.** Widening it to "contains these" would let a fourth
    entry land with no diff here, and an entry in this mapping is a job that runs
    against every section in the institution on a cadence nobody at the keyboard
    sees. Being made to edit this test is the whole point of the equality.

    **The third entry is found by its task and not by its key**, because E2-06's
    work order settles the task name, the module and the cadence and settles no
    name for the schedule key. Asserting a key here would pin an identifier the
    ticket leaves open; asserting the task is asserting what the ticket says.

    The name-and-task assertion is the strong half of the pair and is not
    left to stand on its own: a module that does not exist produces an empty
    schedule that would vacuously fail to contain anything, so
    `app.jobs.schedules` is imported first and asserted to be real. The
    wiring test above — that the entries this module holds are the ones beat
    reads — is the other half, and without it "the schedule holds this entry"
    here would be indistinguishable from "this module holds it, unread by
    beat".
    """
    schedules = import_app_module(SCHEDULES_MODULE)
    assert schedules is not None, MISSING_MODULE_MESSAGE.format(module=SCHEDULES_MODULE)

    application = require_application(import_app_module, celery_application_in)
    entries = dict(application.conf.beat_schedule or {})

    def member(entry: Any, name: str) -> Any:
        return entry.get(name) if isinstance(entry, dict) else getattr(entry, name, None)

    tasks = sorted(str(member(entry, "task")) for entry in entries.values())
    expected_tasks = sorted(
        {PURGE_NONCES_TASK_NAME, ROSTER_SYNC_TASK_NAME, WINDOW_DERIVATION_TASK_NAME}
    )
    assert tasks == expected_tasks, (
        f"The beat schedule runs {tasks}, not exactly {expected_tasks} — its keys are "
        f"{sorted(entries)}. E1-08 landed the daily purge of the launch replay ledger (ADR 0089), "
        "E1-11 the hourly roster sync SPEC §7.3 asks for, and E2-06 the hourly survey-window "
        "reconciler that reaches a section which appeared mid-term. No other ticket has landed "
        "one: reports are E4, retention is E13. If one of those has now landed too, this test is "
        "again the record that has to change with it — say which ticket owns the new entry and "
        "assert what it is, rather than widening this equality to a superset check."
    )

    assert {PURGE_NONCES_SCHEDULE_KEY, ROSTER_SYNC_SCHEDULE_KEY} <= set(entries), (
        f"The beat schedule declares {sorted(entries)} and the two entries that landed before "
        f"E2-06 are filed under {sorted({PURGE_NONCES_SCHEDULE_KEY, ROSTER_SYNC_SCHEDULE_KEY})}. "
        "Those two keys are E1-08's and E1-11's own and are not E2-06's to rename."
    )

    entry = entries[PURGE_NONCES_SCHEDULE_KEY]
    task = member(entry, "task")
    assert task == PURGE_NONCES_TASK_NAME, (
        f"`{PURGE_NONCES_SCHEDULE_KEY}` runs {task!r}, not {PURGE_NONCES_TASK_NAME!r}. E1-08's "
        "entry has to run the nonce-purge task specifically, or the schedule fires something "
        "beat was never told to run."
    )
    schedule = member(entry, "schedule")
    assert schedule, (
        f"`{PURGE_NONCES_SCHEDULE_KEY}` declares no `schedule` ({schedule!r}). ADR 0089 gives "
        "the nonce ledger 'a daily Celery-beat purge' in place of the native TTL a Redis store "
        "would have supplied — an entry with no period runs on no cadence at all."
    )

    roster = entries[ROSTER_SYNC_SCHEDULE_KEY]
    roster_task = member(roster, "task")
    assert roster_task == ROSTER_SYNC_TASK_NAME, (
        f"`{ROSTER_SYNC_SCHEDULE_KEY}` runs {roster_task!r}, not {ROSTER_SYNC_TASK_NAME!r}. E1-11's "
        "hourly entry walks every section that has a stored roster address; the per-section task "
        f"beside it, `{SECTION_ROSTER_TASK_NAME}`, is what the launch trigger enqueues for one "
        "section, and scheduling that one instead would sync a single section every hour and "
        "leave the rest of the institution unsynced."
    )
    roster_schedule = member(roster, "schedule")
    assert getattr(roster_schedule, "minute", None) == {int(ROSTER_SYNC_MINUTE)}, (
        f"`{ROSTER_SYNC_SCHEDULE_KEY}` is scheduled as {roster_schedule!r}. E1-11's work order "
        f'settles `crontab(minute="{ROSTER_SYNC_MINUTE}")`, and a `timedelta(hours=1)` is not the '
        "same schedule: it drifts with every restart, so which minute of the hour an institution's "
        "rosters are pulled in depends on when beat last came up. `crontab.minute` is the set of "
        "minutes an entry fires on, so this reads the schedule rather than its repr."
    )

    derivations = [
        entry for entry in entries.values() if member(entry, "task") == WINDOW_DERIVATION_TASK_NAME
    ]
    assert len(derivations) == 1, (
        f"{len(derivations)} beat entries run {WINDOW_DERIVATION_TASK_NAME!r}; the schedule holds "
        f"{sorted(entries)}. E2-06 lands one hourly reconciler, and two entries running it would "
        "walk every section in the institution twice an hour."
    )
    derivation_schedule = member(derivations[0], "schedule")
    assert getattr(derivation_schedule, "minute", None) == {int(WINDOW_DERIVATION_MINUTE)}, (
        f"The survey-window reconciler is scheduled as {derivation_schedule!r}. E2-06's work order "
        f'settles `crontab(minute="{WINDOW_DERIVATION_MINUTE}")` — minute 30 because minute 0 is '
        "the roster sync's, and two jobs that each walk every section in the institution are "
        "better an hour apart than on the same tick. A `timedelta(hours=1)` is not the same "
        "schedule either: it drifts with every restart, so which minute a section's windows are "
        "reconciled at depends on when beat last came up."
    )


def test_the_ping_task_is_registered_with_that_same_application(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> None:
    """`app.jobs.tasks.ping` is a task the worker will actually accept.

    E0-03 scope: "one trivial `ping` task used only to prove the round-trip",
    and criterion 2 calls it from the API container. A worker started as
    `celery -A app.jobs.celery_app worker` runs the tasks registered on *that*
    application and nothing else, so a `ping` defined against a second Celery
    instance — the shape a copied snippet arrives in — is enqueued by the API
    and never executed by the worker. The symptom is a hang until the timeout,
    which reads as a broker problem.

    The registry is asserted rather than the return value: the ticket says the
    task is trivial and does not say what it returns, so pinning `"pong"` here
    would decide that for the implementer.
    """
    application = require_application(import_app_module, celery_application_in)
    tasks = import_app_module(TASKS_MODULE)
    assert tasks is not None, MISSING_MODULE_MESSAGE.format(module=TASKS_MODULE)

    ping = getattr(tasks, PING_TASK_ATTRIBUTE, None)
    assert ping is not None, (
        f"`{TASKS_MODULE}` defines no `{PING_TASK_ATTRIBUTE}`. E0-03 ships one trivial "
        "task by that name to prove the round trip."
    )
    task_name = getattr(ping, "name", None)
    assert task_name, (
        f"`{TASKS_MODULE}.{PING_TASK_ATTRIBUTE}` is a plain function, not a Celery task: "
        "it has no `.name`, so it cannot be enqueued and nothing can execute it remotely."
    )
    assert task_name in application.tasks, (
        f"`{task_name}` is not registered on the application in `{CELERY_APP_MODULE}` "
        f"(it holds {sorted(n for n in application.tasks if not n.startswith('celery.'))}). "
        "The worker runs that application's registry, so a task registered elsewhere is "
        "enqueued and never run."
    )


@pytest.mark.parametrize(
    "name", [ROSTER_SYNC_TASK_NAME, SECTION_ROSTER_TASK_NAME], ids=["all-sections", "one-section"]
)
def test_both_roster_sync_tasks_are_registered_with_that_same_application(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
    name: str,
) -> None:
    """E1-11's two tasks, and the reason there are two rather than one.

    D10: "`backend/app/jobs/tasks.py` gains `sync_rosters` (walk sections with a
    stored address, sync each) and `sync_section_roster(section_id)` (one section),
    thin wrappers over `roster_sync` service functions." SPEC §7.3 is why the pair
    exists — NRPS is "pulled on schedule **and on launch** (debounced)" — and the
    two halves enqueue different work: beat runs the first every hour, and a staff
    launch enqueues the second for the one section it just touched.

    **Registration is the assertion, for the reason the `ping` test gives**: a
    worker runs the tasks registered on the application `celery -A
    app.jobs.celery_app worker` starts, so a task defined against a second Celery
    instance is enqueued by the launch door and never executed — and the symptom is
    a section that never syncs, which looks exactly like a platform that withheld
    the roster address.

    **The parametrisation is what makes a missing half visible.** One test asserting
    both would name whichever failed first; two report which one is absent, and the
    per-section task is the one a debounced launch trigger cannot work without.
    """
    application = require_application(import_app_module, celery_application_in)
    tasks = import_app_module(TASKS_MODULE)
    assert tasks is not None, MISSING_MODULE_MESSAGE.format(module=TASKS_MODULE)

    attribute = name.rsplit(".", 1)[-1]
    task = getattr(tasks, attribute, None)
    assert task is not None, (
        f"`{TASKS_MODULE}` defines no `{attribute}` — it defines "
        f"{sorted(n for n in vars(tasks) if not n.startswith('_'))}. E1-11's work order (D10) puts "
        "both roster-sync tasks there, following `purge_launch_nonces`' shape."
    )
    assert getattr(task, "name", None) == name, (
        f"`{TASKS_MODULE}.{attribute}` has `.name` {getattr(task, 'name', None)!r} rather than "
        f"{name!r}, so it is either a plain function — which cannot be enqueued at all — or a task "
        "registered under a name the beat schedule and the launch trigger do not use."
    )
    assert name in application.tasks, (
        f"`{name}` is not registered on the application in `{CELERY_APP_MODULE}` (it holds "
        f"{sorted(n for n in application.tasks if not n.startswith('celery.'))}). The worker runs "
        "that application's registry, so this task would be enqueued and never run — and a section "
        "that never syncs looks exactly like one whose platform withheld the roster address."
    )
