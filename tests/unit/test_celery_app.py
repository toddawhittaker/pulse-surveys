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

`import_app_module` (in `tests/conftest.py`) is what makes that possible: it
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


def test_the_beat_schedule_holds_no_real_entries_yet(
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    celery_application_in: Callable[[ModuleType], Any],
) -> None:
    """E0-03 scope: the schedule module is "empty of real entries".

    Every scheduled job in the product is somebody else's ticket — window
    open and close is E2, Monday reports are E4, roster sync is E1, retention
    purges are E13 — and E0-03 puts all of them out of scope explicitly. An
    entry that lands here now runs on a beat whose only verification is that it
    starts.

    **This test is a record with a shelf life, and that is deliberate.** The
    first real entry is meant to make it fail, so that adding it is a
    conversation about which ticket owns the job rather than a line that slips
    in. Whoever lands that entry rewrites this test in the same change.

    The empty assertion is the weak half of the pair and is not left to stand on
    its own: an empty schedule is exactly what a module that does not exist
    would produce, so `app.jobs.schedules` is imported first and asserted to be
    real. The wiring test above — that the entries this module holds are the
    ones beat reads — is the other half, and without it "empty" here would be
    indistinguishable from "connected to nothing".
    """
    schedules = import_app_module(SCHEDULES_MODULE)
    assert schedules is not None, MISSING_MODULE_MESSAGE.format(module=SCHEDULES_MODULE)

    application = require_application(import_app_module, celery_application_in)
    entries = dict(application.conf.beat_schedule or {})

    assert not entries, (
        f"The beat schedule declares {sorted(entries)}. E0-03 puts every real scheduled "
        "task out of scope: window scheduling is E2, reports are E4, roster sync is E1, "
        "retention is E13. If one of those has now landed, this test is the record that "
        "has to change with it — say which ticket owns the entry and assert what it is, "
        "rather than deleting the assertion."
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
