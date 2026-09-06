"""E3-05 — a launch door with a reachable gradebook behind it, and the names its tests read.

Three things live here, and each is here rather than in a test module because more
than one module needs it: the criterion module that drives whole launches, the
trigger module that drives the service, and the timing module.

**`gradebook_door` is `launch_driver` with the gradebook wired up.** E1-10's
`launch_driver` (tests/fixtures/provisioning.py) drives a real launch at this
project's own door, and E3-04's `ags_sections` (tests/fixtures/ags_client.py)
gives a client a platform whose AGS routes it can actually reach. Neither is the
other: the first builds a tool and a platform that has never heard of the tool's
key set, and the second seeds a section rather than launching one. E3-05 is the
first ticket whose subject is the *join* — a launch arrives, and a line item
appears in the launched context's own container — so this assembles the four
things that join is made of, all of them copied from `roster_platforms` rather
than invented here:

  - the platform is started knowing where the tool publishes its key set
    (`MOCK_LMS_TOOL_JWKS_URL`, ADR 0084 decision 4), because it verifies the
    tool's `client_assertion` against that set before it will issue an AGS token;
  - the platform's own outbound client is routed at the tool, because neither
    address resolves over a network in this process;
  - the platform's driver signs with the `tool_signing_key` row the tool
    publishes, so a token this suite mints for ground truth and a token the tool
    mints for itself are accepted by the same platform;
  - the registration's `auth_token_url` is the platform's advertised
    `token_endpoint`, which is what the client resolves a grant through.

`register_platform` writes none of that last one — E1-10 had no service call to
make — so it is written here, exactly as `roster_platforms` writes it.

**`ServiceWire` is the transport the *task* speaks over.** The tool's own
`app.state.http` reaches the platform for a key-set fetch; an AGS call is made by
a Celery task with a `requests.Session` of its own, which is the seam the work
order settles as `app.services.grading.outbound_transport()`. So this hands back
the same `ServiceWire` E3-04's suite uses, with the platform mounted at the host
its container address names, and a test monkeypatches the seam to it.

**Nothing here sets `task_always_eager`.** `run_tasks_inline` is a plain function
called from a test body, for the reason `docs/MISTAKES.md` entry 44 gives about
every guard in this file: a tree where `app.jobs.celery_app` has no application on
it must produce a FAILED naming the deliverable, not an ERROR in somebody's setup.
The same rule is why `grading_module` and `grading_callable` are functions rather
than fixtures.

**The environment** is `configured_env`'s documented values over the container's
database coordinates, laid down by `tool_doors` (`docs/MISTAKES.md` entry 40). The
`ENVIRONMENT` a caller does not name is the development one, which is what makes
the mock's own cleartext container address storable at all (ADR 0081).
"""

import importlib
from collections.abc import Callable, Iterator, Mapping
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest

from fixtures.celery_broker import REDIS_URL_VARIABLE
from fixtures.client_credentials import key_pair_from_pem
from fixtures.doors import routed_through
from fixtures.provisioning import (
    MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE,
    MOCK_LMS_TOOL_LOGIN_URL_VARIABLE,
    REGISTERED_AUTHORIZATION_ENDPOINT,
    LaunchDriver,
)
from fixtures.roster_sync import (
    AUTH_TOKEN_URL_COLUMNS,
    MOCK_LMS_TOOL_JWKS_URL_VARIABLE,
    TOOL_JWKS_PATH,
    ServiceWire,
)
from fixtures.submit import closed_loopback_address
from fixtures.supervision import require_column, require_table, single_primary_key

# ---------------------------------------------------------------------------
# The identifiers E3-05's work order settles. Nothing here is discovered,
# because nothing here is left open: decisions D2, D3 and D4 name every one.
# ---------------------------------------------------------------------------

# D3: "the creation service lives in `backend/app/services/grading.py`" (SPEC §13
# line 433 names that module). The package root is `backend/`, so the import path
# is `app.services.grading`.
GRADING_MODULE = "app.services.grading"

# D2: `publish_once` and the two constants it owns live in
# `backend/app/jobs/celery_app.py`, moved there from `app.services.validity`.
CELERY_APP_MODULE = "app.jobs.celery_app"
PUBLISH_ONCE = "publish_once"

# D4: `create_line_item(section_id: str)` in `backend/app/jobs/tasks.py`, shaped
# exactly like `sync_section_roster`.
TASKS_MODULE = "app.jobs.tasks"
CREATE_LINE_ITEM_TASK = "create_line_item"

# E0-03's round-trip task, which has been a Celery task in `app.jobs.tasks` since
# that ticket and which `tests/unit/test_celery_app.py` asserts is one. Used by
# this module's eager control and by nothing else: it is a task whose behaviour
# E3-05 does not touch, so a round trip through it says something about the
# harness rather than about the ticket.
PING_TASK = "ping"

# D3's three names on the service. The trigger the launch door calls, the worker
# side it enqueues, and the transport seam tests substitute.
REQUEST_LINE_ITEM_CREATION = "request_line_item_creation"
ENSURE_LINE_ITEM = "ensure_line_item"
OUTBOUND_TRANSPORT = "outbound_transport"

# The roster trigger that already sits on this door, named because E3-05's
# criterion 5 times *both* publishes and because D2 moves it onto the bounded
# shape in the same change.
ROSTER_SYNC_MODULE = "app.services.roster_sync"
REQUEST_SECTION_SYNC = "request_section_sync"
SECTION_SYNC_TASK = "sync_section_roster"

# The two loggers criterion 5 reads its proof off. Each is what
# `logging.getLogger(__name__)` produces in the module that owns the enqueue, and
# they are the module paths D1 and D3 fix rather than spellings chosen here.
ROSTER_SYNC_LOGGER = ROSTER_SYNC_MODULE
GRADING_LOGGER = GRADING_MODULE

# SPEC §10's whole-round-trip figure, which the work order takes as this ticket's
# budget: "survey submit p95 < 2.5s". Written here rather than derived, and the
# separation it has to make is wide on both sides — a bounded refusal against a
# closed port was measured at 0.037s per publish and the unbounded shape this
# ticket removes costs about six seconds per publish.
#
# **Chosen against the roster debounce rather than around it** (`docs/MISTAKES.md`
# entry 7): the debounce is 300 seconds and this budget is nowhere near it, so a
# launch that came in under budget by being debounced is not a thing this number
# can be satisfied by — and the timing test asserts the section has no `nrps_call`
# row at all, so the debounce cannot fire in the first place.
LAUNCH_BUDGET_SECONDS = 2.5
ROSTER_DEBOUNCE_SECONDS = 300

# SPEC §3.4's line item, and the members E3-04 settled it by. Transcribed from
# `tests/fixtures/ags_client.py` rather than imported, for the reason that file
# gives about its own transcriptions: two inventories of one closed set that
# import each other cannot disagree, and cannot notice a drift either.
PULSE_RESOURCE_ID = "pulse-participation"
PULSE_LABEL = "Pulse Participation"
RESOURCE_ID_MEMBER = "resourceId"
LINE_ITEM_ID_MEMBER = "id"

# E3-02's two columns on `section`.
SECTION_CONTAINER_COLUMN = "lms_ags_line_items_url"
SECTION_LINE_ITEM_COLUMN = "ags_line_item_url"

# The variable a test points at a closed port so nothing waits on a broker is
# `REDIS_URL`, imported from `fixtures/celery_broker.py` rather than spelled again:
# "which variable does the application read its broker out of" is one question and
# two answers would be two copies of it (`docs/MISTAKES.md` entry 13).


def grading_module() -> ModuleType:
    """`app.services.grading`, imported where a test can fail on it rather than error.

    Called from a test body, never from a fixture, so that on a tree where E3-05
    is unbuilt every module using this goes red on its own criterion with this
    sentence attached instead of erroring in setup on somebody's missing import
    (`docs/MISTAKES.md` entry 44). The shape is `ags_module()`'s in
    `tests/fixtures/ags_client.py`, and an `ImportError` from *inside* a module
    that exists is re-raised untouched: a service that was never written and one
    that imports something absent are different failures with different fixes.
    """
    return _module_or_named_absence(
        GRADING_MODULE,
        "E3-05's work order (D3) ships the creation service there, in the module SPEC §13 names "
        "'participation formula + AGS passback': `request_line_item_creation(session, "
        "section_id)`, which the launch door calls and which enqueues nothing for a section with "
        "no container address or with a line-item id already stored; `ensure_line_item(session, "
        "section_id, ...)`, the worker side that locks the row, calls E3-04's client and stores "
        "the id under `guard_write`; and `outbound_transport()`, the seam the task's HTTP "
        "transport comes from.",
    )


def celery_module() -> ModuleType:
    """`app.jobs.celery_app`, imported the same way and for the same reason."""
    return _module_or_named_absence(
        CELERY_APP_MODULE,
        "E0-03 ships the Celery application there and E3-05's work order (D2) adds "
        f"`{PUBLISH_ONCE}` beside it — the one bounded publish every enqueue on the launch door "
        "goes through.",
    )


def tasks_module() -> ModuleType:
    """`app.jobs.tasks`, imported the same way and for the same reason."""
    return _module_or_named_absence(
        TASKS_MODULE,
        "SPEC §13 puts the task definitions there, E1-11 put `sync_section_roster` there, and "
        f"E3-05's work order (D4) adds `{CREATE_LINE_ITEM_TASK}(section_id)` beside it.",
    )


def _module_or_named_absence(name: str, why: str) -> ModuleType:
    """Import `name`, or fail naming the deliverable and what it owes."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (absent == name or name.startswith(f"{absent}.")):
            raise
        pytest.fail(f"`{name}` does not exist. {why}")


def named_in(module: ModuleType, name: str, why: str) -> Any:
    """One attribute of a module, or a failure naming the deliverable that owes it.

    The counterpart to the module guards above, at member grain, and called from a
    test body for the same reason: a symbol the ticket settles and that is not
    there yet is a FAILED naming it, never an `AttributeError` out of somebody's
    fixture (`docs/MISTAKES.md` entry 44).
    """
    found = getattr(module, name, None)
    if found is None:
        pytest.fail(
            f"`{module.__name__}` exposes no `{name}` — it exposes "
            f"{sorted(attribute for attribute in vars(module) if not attribute.startswith('_'))}. "
            f"{why}"
        )
    return found


def run_tasks_inline(monkeypatch: pytest.MonkeyPatch, celery_application_in: Any) -> Any:
    """Run the tool's own Celery tasks in this process instead of publishing them.

    The work order's settled seam: "monkeypatch `celery_app.conf.task_always_eager
    = True`. `publish_once`'s connection is lazy (kombu connects on first use;
    `apply_async` takes the eager branch before any publish), so the default
    closed-port broker is never dialled under eager and the task runs inline."

    **Called after the tool has been built, and that is load-bearing.**
    `tool_doors` imports the application through `import_app_module`, which drops
    every `app.*` module from `sys.modules` first — so a Celery application
    imported before the door was opened is a *different object* from the one the
    door's tasks are registered on, and setting the flag on it would leave the
    launch publishing to a closed port while the test believed it was running
    inline (`docs/MISTAKES.md` entry 3). Importing here, after the build, resolves
    the module the tool itself loaded.

    `task_eager_propagates` is set as well, and it is the one thing here that is
    about diagnosis rather than about the seam. Without it Celery swallows an
    exception raised inside an eagerly-run task into a result nobody reads, so an
    AGS call that failed for a reason having nothing to do with this ticket would
    surface only as an empty container — a red whose message names the wrong
    thing. With it, the failure travels out to `request_line_item_creation`'s own
    broad `except`, which logs it and answers `False`; the launch is unaffected,
    which is the property under test, and the log carries what went wrong.
    """
    module = celery_module()
    application = celery_application_in(module)
    if application is None:
        pytest.fail(
            f"`{CELERY_APP_MODULE}` exposes no Celery application at module level, so there is "
            "nothing to run a task on and nothing `celery -A app.jobs.celery_app worker` could "
            "start either. E0-03 ships it; `tests/unit/test_celery_app.py` is where its absence "
            "is diagnosed."
        )
    monkeypatch.setattr(application.conf, "task_always_eager", True, raising=False)
    monkeypatch.setattr(application.conf, "task_eager_propagates", True, raising=False)
    return application


def reaching_the_platform(monkeypatch: pytest.MonkeyPatch, wire: Any) -> None:
    """Point the creation task's outbound transport at the in-process platform.

    D3 makes `outbound_transport()` the module-level seam the worker takes its
    `requests.Session` from — "the same role as ADR 0101's `resolve`" — and this
    is the substitution it exists for: neither the mock platform's address nor the
    tool's resolves over a network in this process, so a task that built its own
    session would reach nothing at all.

    Substituted on `app.services.grading` rather than on whatever the task
    imported, because D3 has `ensure_line_item` call it through the module: a
    `from … import outbound_transport` in `tasks.py` would bind the original and
    this substitution would silently do nothing, which is a case worth naming
    rather than discovering — if the eager tests fail with the platform never
    called, that is the first thing to look at.
    """
    module = grading_module()
    named_in(
        module,
        OUTBOUND_TRANSPORT,
        "E3-05's work order (D3) puts it at module level: `outbound_transport() -> "
        "requests.Session | None`, answering `None`, called by `ensure_line_item` when no `http` "
        "was handed in. It is the only seam a test has for reaching the platform from inside an "
        "eagerly-run task.",
    )
    monkeypatch.setattr(module, OUTBOUND_TRANSPORT, wire.session)


class _Held:
    """An object with a `.client`, which is all `routed_through` asks of a driver."""

    def __init__(self, client: Any) -> None:
        self.client = client


class GradebookDoor:
    """One tool, one registered platform whose gradebook the tool can reach, and the wire.

    `driver` is E1-10's `LaunchDriver`, so every launch travels the real route —
    the login leg, the tool's own `state`/`nonce`, and the platform's signature.
    Everything else on this object is about the container that launch names.
    """

    def __init__(
        self,
        tool: Any,
        driver: LaunchDriver,
        platform: Any,
        registration: Any,
        wire: ServiceWire,
    ) -> None:
        self.tool = tool
        self.driver = driver
        self.platform = platform
        self.registration = registration
        self.wire = wire

    def instructor_offer(self, contract: Any) -> Any:
        return self.driver.offer_for_role(contract.instructor_role_urn)

    def student_offer(self, contract: Any) -> Any:
        return self.driver.offer_for_role(contract.learner_role_urn)

    def container_of(self, signed: Any) -> str:
        """The AGS line-item container the platform advertised on this launch."""
        return self.platform.line_items_url(signed)

    def items_in(self, signed: Any) -> list[dict[str, Any]]:
        """Every line item the launched context's container holds, walked to the last page.

        Walked rather than read one page deep, for the reason E3-04's suite gives
        about the same read: "a second Pulse Participation column can never
        appear" is a claim about the whole container, and a first-page read of a
        container that pages at five would satisfy it while the duplicate sat on
        page two.
        """
        return [item for page in self.platform.line_item_pages(signed) for item in page]

    def pulse_items_in(self, signed: Any) -> list[dict[str, Any]]:
        """Every line item in that container carrying SPEC §3.4's resource id."""
        return [
            item
            for item in self.items_in(signed)
            if str(item.get(RESOURCE_ID_MEMBER)) == PULSE_RESOURCE_ID
        ]

    def plant_a_line_item(
        self, signed: Any, *, resource_id: str = PULSE_RESOURCE_ID
    ) -> dict[str, Any]:
        """Create a line item on the platform that nothing in Pulse created.

        With the default `resource_id` it is criterion 6's subject — "a container
        that already holds a 'Pulse Participation' item produced by something other
        than Pulse is reconciled to, not duplicated". With one of this suite's own
        it is a column that is not Pulse's, which is what a test proving its
        container reader can *see* anything uses, so that an assertion of emptiness
        elsewhere is known to be a real emptiness.

        Created through the platform driver's own credentialed helper, so it is a
        line item the platform really holds rather than a row this suite wrote into
        a column of its own.
        """
        return self.platform.create_line_item(
            signed, **{RESOURCE_ID_MEMBER: resource_id, "label": PULSE_LABEL}
        )


@pytest.fixture
def gradebook_door(
    mock_platforms: Any,
    door_contract: Any,
    tool_doors: Any,
    register_platform: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    stored_signing_key: str,
) -> Iterator[Callable[..., GradebookDoor]]:
    """Open the launch door with a platform whose AGS routes the tool can reach.

    A factory rather than a fixture, because two callers need different
    environments: the timing module points `REDIS_URL` at a closed port and takes
    the real publish, and the criterion module runs its tasks inline. Anything
    passed as a keyword is an environment variable, set through `tool_doors` so a
    module that builds something out of `Settings` at import is built under it
    (`docs/MISTAKES.md` entry 40).

    The order below is not incidental. The platform is started first, because the
    registration is written from the offer it advertises; the tool is built next,
    because the platform's outbound client has to be pointed at a tool that
    exists; and the platform's own key pair is replaced last, so an assertion this
    suite signs is signed with the row the tool publishes at `/lti/jwks` rather
    than with the driver's own throwaway key — without which every AGS token in
    these tests would be refused `invalid_client` for a reason that has nothing to
    do with E3-05 (`docs/MISTAKES.md` entry 22).
    """
    tool_jwks_url = f"{door_contract.public_base_url}{TOOL_JWKS_PATH}"
    tool_host = urlsplit(door_contract.public_base_url).hostname or ""

    def open_it(**environment: str) -> GradebookDoor:
        platform = mock_platforms(
            {
                MOCK_LMS_TOOL_LOGIN_URL_VARIABLE: (
                    f"{door_contract.public_base_url}{door_contract.lti_login}"
                ),
                MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE: (
                    f"{door_contract.public_base_url}{door_contract.lti_launch}"
                ),
                MOCK_LMS_TOOL_JWKS_URL_VARIABLE: tool_jwks_url,
            }
        )
        discovery = platform.discovery() or {}
        jwks_url = discovery.get("jwks_uri")
        token_url = discovery.get("token_endpoint")
        assert isinstance(jwks_url, str) and jwks_url, (
            "The mock platform's discovery document advertises no `jwks_uri` (it carries "
            f"{sorted(discovery)}), so there is nothing to register and no launch can verify."
        )
        assert isinstance(token_url, str) and token_url, (
            "The mock platform's discovery document advertises no `token_endpoint`, so there is "
            "no address to register under `auth_token_url` and the tool could request no AGS "
            "token at all. E1-06 adds it; `test_mock_lms_client_credentials_grant.py` is where "
            "its absence is diagnosed."
        )

        registration = register_platform(
            platform.require_offers()[0], jwks_url, REGISTERED_AUTHORIZATION_ENDPOINT
        )
        # `register_platform` writes no token endpoint — E1-10 had no service call
        # to make — and every AGS call the tool makes begins with a
        # client-credentials grant against this column. Written exactly as
        # `roster_platforms` writes it.
        registration.rewrite(
            registration.platform_table,
            registration.platform_row,
            require_column(registration.platform_table, AUTH_TOKEN_URL_COLUMNS),
            token_url,
        )

        values = {door_contract.settings["public_base_url"]: door_contract.public_base_url}
        values.update(environment)
        tool = tool_doors(values, {urlsplit(jwks_url).hostname: platform})

        # The platform fetches the tool's key set while it verifies an assertion
        # (ADR 0084 decision 4). Installed after the platform's lifespan has run,
        # and it replaces the driver's own default: the key set the platform
        # verifies against is the real tool's, served out of `tool_signing_key`.
        platform.application.state.http = routed_through({tool_host: _Held(tool)})
        platform.tool_key_pair = key_pair_from_pem("e3-05-stored-tool-key", stored_signing_key)

        wire = ServiceWire({})
        wire.hosts[urlsplit(token_url).hostname or ""] = platform
        for context in platform.seeded_contexts():
            container = platform.line_items_url(context.launches[0])
            wire.hosts[urlsplit(container).hostname or ""] = platform

        return GradebookDoor(
            tool,
            LaunchDriver(tool, door_contract, platform, registration),
            platform,
            registration,
            wire,
        )

    yield open_it


@pytest.fixture
def a_closed_broker() -> str:
    """A `REDIS_URL` on a closed loopback port, refusing immediately.

    The measurement surface `docs/MISTAKES.md` entry 41 asks for — "time the
    enqueue against a closed port rather than trusting the flags" — and the
    carried E2 entry's done-when names it in as many words: "a test that times a
    staff launch against a broker at a closed port under a stated budget".

    A released port rather than the `.env.example` default, which names the
    Compose service `redis`: that name does not resolve here, so a publish against
    it waits on a name lookup whose duration is the resolver's business rather
    than the enqueue's, and a slow refusal would hide a slow enqueue. Shared with
    `tests/fixtures/submit.py`, whose `closed_loopback_address` this is.
    """
    return f"redis://{closed_loopback_address()}/0"


@pytest.fixture
def line_item_contract() -> Any:
    """The names E3-05's test modules read the creation path through.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module in this suite gives: an import of a fixtures module by name depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class LineItemContract:
        grading_module_name = GRADING_MODULE
        celery_module_name = CELERY_APP_MODULE
        tasks_module_name = TASKS_MODULE
        roster_sync_module_name = ROSTER_SYNC_MODULE

        publish_once = PUBLISH_ONCE
        create_line_item_task = CREATE_LINE_ITEM_TASK
        section_sync_task = SECTION_SYNC_TASK
        ping_task = PING_TASK
        request_line_item_creation = REQUEST_LINE_ITEM_CREATION
        request_section_sync = REQUEST_SECTION_SYNC
        ensure_line_item = ENSURE_LINE_ITEM
        outbound_transport = OUTBOUND_TRANSPORT

        roster_sync_logger = ROSTER_SYNC_LOGGER
        grading_logger = GRADING_LOGGER

        budget_seconds = LAUNCH_BUDGET_SECONDS
        debounce_seconds = ROSTER_DEBOUNCE_SECONDS

        resource_id = PULSE_RESOURCE_ID
        label = PULSE_LABEL
        resource_id_member = RESOURCE_ID_MEMBER
        line_item_id_member = LINE_ITEM_ID_MEMBER
        container_column = SECTION_CONTAINER_COLUMN
        line_item_column = SECTION_LINE_ITEM_COLUMN

        redis_url_variable = REDIS_URL_VARIABLE

        grading = staticmethod(grading_module)
        celery = staticmethod(celery_module)
        tasks = staticmethod(tasks_module)
        named_in = staticmethod(named_in)
        run_tasks_inline = staticmethod(run_tasks_inline)
        reaching_the_platform = staticmethod(reaching_the_platform)
        set_section_values = staticmethod(committed_section_values)
        section_row = staticmethod(committed_section_row)

    return LineItemContract()


class Enqueues:
    """Every enqueue of one task, recorded instead of performed.

    E1-11's recorder in
    `tests/integration/test_the_roster_sync_is_discovered_and_debounced.py`, moved
    here because E3-05 needs the same device on a second task and two copies of it
    would be two copies of one rule (`docs/MISTAKES.md` entry 13).

    **Both spellings are intercepted**, and that module's reason is stronger here:
    D2 has every enqueue go through `publish_once`, which calls `apply_async`, and
    a recorder watching only `delay` would read every publish as "not enqueued" —
    the answer the refusing half of each pair below asserts, so the tests would
    pass for the wrong reason on every case at once (`docs/MISTAKES.md` entry 3).
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, task_name: str, why: str) -> None:
        self.calls: list[tuple[Any, ...]] = []
        tasks = tasks_module()
        task = named_in(tasks, task_name, why)
        for spelling in ("delay", "apply_async"):
            monkeypatch.setattr(task, spelling, self.record, raising=False)

    def record(self, *arguments: Any, **keywords: Any) -> None:
        self.calls.append((arguments, keywords))

    def __len__(self) -> int:
        return len(self.calls)


@pytest.fixture
def creation_enqueues(monkeypatch: pytest.MonkeyPatch) -> Callable[[], Enqueues]:
    """The creation task's enqueue, intercepted for the length of one test.

    A factory rather than an `Enqueues` directly, so the interception happens
    inside the test body: on a tree where `app.jobs.tasks` has no
    `create_line_item` on it, the red is a FAILED naming that task rather than an
    ERROR in this fixture (`docs/MISTAKES.md` entry 44).
    """

    def intercept() -> Enqueues:
        return Enqueues(
            monkeypatch,
            CREATE_LINE_ITEM_TASK,
            f"E3-05's work order (D4) adds `{CREATE_LINE_ITEM_TASK}(section_id)` there, shaped "
            f"exactly like `{SECTION_SYNC_TASK}`, and D3 has `{REQUEST_LINE_ITEM_CREATION}` "
            "publish it. Without the task there is nothing for the launch trigger to enqueue and "
            "nothing for this test to count.",
        )

    return intercept


def committed_section_values(
    rows: Any, tables: Mapping[str, Any], section_id: Any, **values: Any
) -> None:
    """Set columns on one committed `section` row, and commit.

    `tests/fixtures/ags_client.py::rewrite_section`, reached through that module's
    own `ags_sections` factory wherever a test can; this exists for the sections a
    *launch* created, which no factory in this suite holds a handle on.

    It runs on `committed_rows`' connection, bound to the migrating engine rather
    than to `pulse_app`: a fixture that needed the application role's `UPDATE` on
    `ags_line_item_url` would be spending the grant E3-05 is being asked to add,
    from inside the setup of the tests that check it.
    """
    table = require_table(dict(tables), "section")
    missing = [name for name in values if name not in table.c]
    if missing:
        pytest.fail(
            f"`section` declares no {missing} (it declares "
            f"{[column.name for column in table.columns]}). E3-02 adds "
            f"`{SECTION_CONTAINER_COLUMN}` and `{SECTION_LINE_ITEM_COLUMN}`."
        )
    key = single_primary_key(table)
    rows.session.execute(table.update().where(table.c[key] == section_id).values(**values))
    rows.commit()


def committed_section_row(rows: Any, tables: Mapping[str, Any], section_id: Any) -> dict[str, Any]:
    """One `section` row, read on a connection that sees another connection's commits.

    The read transaction is ended first, for the reason `ProvisionedRows.all_of`
    gives: the eagerly-run task and the worker both open sessions of their own, so
    a session that has been holding a transaction since it seeded would go on
    seeing the row as it was before they wrote it — and "the column was not
    written" is what this suite would read that as.
    """
    table = require_table(dict(tables), "section")
    key = single_primary_key(table)
    rows.session.rollback()
    found = list(rows.session.execute(table.select().where(table.c[key] == section_id)).mappings())
    assert len(found) == 1, (
        f"There are {len(found)} `section` rows keyed {section_id!r}, and this reader needs "
        f"exactly one: {[dict(row) for row in found]}."
    )
    return dict(found[0])
