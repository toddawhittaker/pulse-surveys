"""The window service reads the clock service and never the system clock — ticket E2-06.

ADR 0109 makes `app.services.clock` "the one place this codebase asks what time it
is for scheduling purposes", names E2-06 by name — "E2-06's window logic is written
against it from the start" — and then declines to build a repository-wide sweep:

    A test that forbade `datetime.now` outside this module would have to carry an
    exemption for every clock in the list above, which is most of them; the list
    is short, the exemptions would outnumber the catches, and an inventory that
    size is the shape `docs/MISTAKES.md` entry 35 is about.

**That argument is about a repository-wide sweep and does not reach this one.**
The subject here is a single module — `app/services/survey_windows.py` — whose
every reading of "now" is a scheduling reading by construction. There is no
exemption list, because there is nothing in that module a launch validator, an
audit timestamp or an NRPS debounce could be. So the rule ADR 0109 states as a
review rule is enforced over the one module where it has no exceptions, and
nowhere else.

**Why it is worth enforcing there.** A direct `datetime.now(UTC)` in this service
is invisible in every other test in E2-06: the derivation suites hand the service
a term and compare instants, and the read-path suites move the development clock
and would simply get real time back — which, on a machine running in 2026, is
inside the seeded Fall 2026 term and therefore answers plausibly. The symptom
would be that the `/dev` clock appears to do nothing, which is exactly the
feature E2-04 exists to provide and E2-06 exists to make useful.

**Two halves, and the second is the one that matters.** Forbidding
`datetime.now` says nothing about whether the module asks anything at all: a
service that decided open and closed without consulting any clock — comparing
dates, or trusting a value passed in from a caller — passes a prohibition
perfectly. So the module is also required to reach the clock service, which is
`docs/MISTAKES.md` entry 3's rule about a test satisfiable by emptiness.

**What this sweep cannot see**, stated so nothing here is cited as more than it
is. It is syntactic: a reading reached through a helper in another module, a
`getattr` over a computed name, or a third-party call that happens to return the
current instant is invisible. It also does not police `time.time()` or an
`func.now()` server default — the first has no legitimate use in this module and
would be caught by review, the second is a clock ADR 0109 deliberately leaves on
real time and would be a schema change rather than a line here.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_MODULE = REPO_ROOT / "backend" / "app" / "services" / "survey_windows.py"

# ADR 0109's own module, the one sanctioned answer to "what time is it".
CLOCK_MODULE = "app.services.clock"
CLOCK_MODULE_TAIL = "clock"

# The readings this module may not take for itself. `now` and `today` are the two
# the work order names; `utcnow` is the deprecated spelling of the first and is
# what a copied snippet arrives as.
FORBIDDEN_READINGS = frozenset({"now", "utcnow", "today"})

# A sample that certainly contains a forbidden reading, and one that certainly
# does not. Both are run through the detector before its answer about the real
# module is believed (`docs/MISTAKES.md` entry 3: give a search a canary, so a
# search that has gone blind says so).
CANARY_SOURCES = {
    "a direct reading of the system clock": (
        "from datetime import UTC, datetime\n"
        "\n"
        "def open_window_for_section(session, section, *, settings):\n"
        "    now = datetime.now(UTC)\n"
        "    return now\n"
    ),
    "the deprecated spelling": (
        "from datetime import datetime\n"
        "\n"
        "def derive(session):\n"
        "    return datetime.utcnow()\n"
    ),
    "today's date off the system clock": (
        "from datetime import date\n" "\n" "def derive(session):\n" "    return date.today()\n"
    ),
    "the reading taken through an aliased class": (
        "from datetime import datetime as dt\n"
        "\n"
        "def derive(session):\n"
        "    return dt.now()\n"
    ),
}

ALLOWED_SOURCES = {
    "the clock service reached as a module": (
        "from app.services import clock\n"
        "\n"
        "def open_window_for_section(session, section, *, settings):\n"
        "    return clock.now(session, settings=settings)\n"
    ),
    "the clock service's function imported by name": (
        "from app.services.clock import now\n"
        "\n"
        "def open_window_for_section(session, section, *, settings):\n"
        "    return now(session, settings=settings)\n"
    ),
    "the clock service under an alias": (
        "import app.services.clock as pulse_clock\n"
        "\n"
        "def open_window_for_section(session, section, *, settings):\n"
        "    return pulse_clock.now(session, settings=settings)\n"
    ),
    "the clock service imported and called by its whole path": (
        "import app.services.clock\n"
        "\n"
        "def open_window_for_section(session, section, *, settings):\n"
        "    return app.services.clock.now(session, settings=settings)\n"
    ),
    "a datetime built rather than read": (
        "from datetime import datetime\n"
        "\n"
        "def opens_on(monday, zone):\n"
        "    return datetime.combine(monday, OPENS_AT, tzinfo=zone)\n"
    ),
    "the time part of an instant": ("def wall_clock(instant):\n    return instant.time()\n"),
}


class ClockReadings(ast.NodeVisitor):
    """Every reading of "now" in one module, and whether it went through the clock service.

    The names bound by an import of `app.services.clock` are collected first, so
    `clock.now(...)`, `pulse_clock.now(...)` and a bare `now(...)` imported from
    that module are all recognised as the sanctioned reading — three spellings of
    one thing, none of which E2-06 settles between.
    """

    def __init__(self) -> None:
        self.clock_modules: set[str] = set()
        self.clock_functions: set[str] = set()
        self.direct: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast's own spelling
        for alias in node.names:
            if alias.name == CLOCK_MODULE:
                # `import app.services.clock` binds `app` and is then called as
                # `app.services.clock.now(...)`, so the whole dotted path counts
                # as a sanctioned receiver as well as any alias.
                self.clock_modules.add(alias.asname or CLOCK_MODULE)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast's own spelling
        module = node.module or ""
        if module == CLOCK_MODULE:
            for alias in node.names:
                self.clock_functions.add(alias.asname or alias.name)
        elif CLOCK_MODULE.startswith(f"{module}."):
            for alias in node.names:
                if alias.name == CLOCK_MODULE_TAIL:
                    self.clock_modules.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast's own spelling
        if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_READINGS:
            receiver = ast.unparse(node.func.value)
            if receiver not in self.clock_modules:
                self.direct.append((node.lineno, ast.unparse(node.func)))
        elif isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_READINGS:
            if node.func.id not in self.clock_functions:
                self.direct.append((node.lineno, node.func.id))
        self.generic_visit(node)


def readings_in(source: str) -> ClockReadings:
    """Walk one module's source and report what it does about time."""
    found = ClockReadings()
    found.visit(ast.parse(source))
    return found


def test_the_clock_sweep_catches_a_direct_reading_and_allows_the_sanctioned_one() -> None:
    """The control, run before this file's silence over the service counts as evidence.

    Four samples that must be caught, six that must not. The pairs matter more
    than either list: `clock.now(session, settings=settings)` and
    `datetime.now(UTC)` are both a call to something named `now`, and a rule that
    could not tell them apart is either red against every correct implementation or
    blind to every wrong one.

    The last two allowed samples are the ones a careless rule breaks on.
    `datetime.combine(monday, OPENS_AT, tzinfo=zone)` is how this service is
    expected to *build* an instant — a wall time in the institution's zone, which
    is exactly what SPEC §3.1 describes — and it is not a reading of anything;
    `instant.time()` takes the time part off a value already in hand.
    """
    for case, sample in sorted(CANARY_SOURCES.items()):
        found = readings_in(sample)
        assert found.direct, (
            f"The sweep found no direct clock reading in {case}:\n{sample}\nA detector that has "
            "gone blind reads exactly like a service that asks the clock service for the time."
        )

    for case, sample in sorted(ALLOWED_SOURCES.items()):
        found = readings_in(sample)
        assert not found.direct, (
            f"The sweep read {found.direct} out of {case}:\n{sample}\nEvery assertion below rests "
            "on the detector saying no to the way ADR 0109 asks this service to be written."
        )


def test_the_window_service_takes_no_reading_of_the_system_clock() -> None:
    """ADR 0109's review rule, enforced over the one module it has no exemptions in.

    **The mutation this kills**: `datetime.now(UTC)` inside
    `open_window_for_section`, which is the shortest way to write the comparison
    and is invisible everywhere else. Every read-path test in E2-06 moves the
    development clock and asks which window is open; against a service reading the
    system clock those tests get real time — plausible, inside the seeded term
    while it is 2026, and wrong — and the visible symptom is that the `/dev` clock
    control appears to do nothing at all. That control is the whole reason E2-04
    was built and the reason E2-06 was asked to be interactive.

    **The near miss it must not fire on**: `datetime.combine(...)`, which is how
    the service turns a Monday and a wall-clock time into an instant. The control
    above holds that pair apart.
    """
    assert SERVICE_MODULE.is_file(), (
        f"{SERVICE_MODULE.relative_to(REPO_ROOT)} does not exist. E2-06 ships the window service "
        "there (SPEC §13), and it is the module this rule is about."
    )

    found = readings_in(SERVICE_MODULE.read_text(encoding="utf-8"))

    assert not found.direct, "\n".join(
        [
            f"{SERVICE_MODULE.relative_to(REPO_ROOT)} reads the system clock directly:",
            *(f"  line {line}: {expression}" for line, expression in found.direct),
            "",
            "ADR 0109: `app.services.clock` is the one place this codebase asks what time it is "
            "for scheduling purposes, and it names this ticket — 'E2-06's window logic is written "
            "against it from the start'. A direct reading here is a window that cannot be driven "
            "by the development clock, in the two processes that both have to agree about what "
            "time it is: the tool answers a student, and the worker derives the rows.",
        ]
    )


def test_the_window_service_reaches_the_clock_service_at_all() -> None:
    """The half a prohibition cannot assert: the service does ask.

    "No direct reading" is true of a module that never asks anything about time —
    one that compares dates, or that takes an instant from whatever caller happens
    to pass one. That module passes the test above and fails the ticket: E2-06's
    scope is "the open-window question, answered by one function reading the E2-04
    clock", and ADR 0109's whole argument for a database-held override is that the
    tool and the worker must read the same clock.

    `docs/MISTAKES.md` entry 3: where a test can be satisfied by emptiness, assert
    non-emptiness first, and say why the guard is not ceremony.

    **The mutation this kills**: an `open_window_for_section` that reads its `at`
    argument and never falls back to the clock when it is `None`. That signature
    is settled — `at: datetime | None = None`, so that a test can stand exactly on
    a boundary — and it is also the shape in which the clock quietly goes missing.
    The four exact-instant cases in
    `tests/integration/test_at_most_one_survey_window_is_open_at_a_time.py` pass
    `at=` and would be green over such a service; the one-second cases beside them
    would go red, and so does this, which says the same thing about the source
    rather than about one behaviour. `None` is what every production caller passes,
    and on the running stack the symptom is a `/dev` clock that appears to do
    nothing.
    """
    assert SERVICE_MODULE.is_file(), (
        f"{SERVICE_MODULE.relative_to(REPO_ROOT)} does not exist, so there is nothing to check "
        "for a clock reading."
    )

    found = readings_in(SERVICE_MODULE.read_text(encoding="utf-8"))

    assert found.clock_modules or found.clock_functions, (
        f"{SERVICE_MODULE.relative_to(REPO_ROOT)} does not import `{CLOCK_MODULE}`, so it asks "
        "nothing about what time it is. The service that decides whether a survey window is open "
        "has to read the clock ADR 0109 built, or the development override reaches the page and "
        "not the answer — which is the one thing this epic was asked to make work."
    )
