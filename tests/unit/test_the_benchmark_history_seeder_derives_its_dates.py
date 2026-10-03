"""E5-12 criterion 2, over the file it is stated about: no clock reading, no written date.

    "Every seeded date derives from the term calendar and section codes; nothing
    reads the wall clock (E4-22's rule, applied at write time)."

Two rules, one file, and they fail in opposite directions — which is why both are
here. A seeder that reads `date.today()` stamps a prior term's world at whatever
day the drive happened on, and the symptom is the calendar bomb E5-12's known
traps name: dates that look right in September and red the suite in January. A
seeder that instead writes `date(2026, 1, 12)` into its plan has a world that
survives the clock and contradicts the seeded calendar the moment anybody edits
`scripts/seed.py`'s term rows — the `start_letter_map` says one thing and the
sections another, with nothing comparing them. That is `docs/MISTAKES.md` entry 19
in its data form: the expectation held in a copy of the thing it should be derived
from.

**Why a sweep over the source rather than a behavioural test.** The behavioural
half — call the planning helpers with a pinned calendar and compare the dates they
answer — needs those helpers to be named, and E5-12 names none of them; a test
that invented the names would settle an interface the ticket left open. What the
criterion *can* be held to without that is the prohibition, and the prohibition is
what the trap class is about: the E4-22 incident is a stamp taken from the wrong
clock, not a derivation computed wrongly.

**What these sweeps cannot see**, said plainly so neither is cited as more than it
is. They are syntactic. A reading reached through a helper in another module, a
`getattr` over a computed name, a date parsed out of a string the script builds, or
a third-party call returning the current instant, are all invisible; so is a date
literal assembled from three integer constants held apart. They are the floor, not
the proof — and the dates the world actually lands on are asserted by the seeder's
own self-check, which recounts from the database.

**The shape is `tests/unit/test_the_window_service_asks_the_clock_for_the_time.py`'s**,
which enforces ADR 0109's review rule over `app/services/survey_windows.py`, and
the detector is deliberately a **second copy** rather than an import of that
module's. The subjects differ — a script rather than a service, and this one also
forbids `time.time` and written dates — and a shared detector would put this file's
expectation and that file's subject in one blast radius. Both carry their own
canaries, which is what keeps two copies honest.

**What this file does not assert, on purpose.** It does not require the seeder to
*reach* the clock service. Whether it asks what time it is at all is a design
question E5-12 leaves open: the prior term's windows are all closed at any clock a
drive could be run under, so a seeder that writes every week of its world without
asking is a legitimate build. Requiring the call would decide that — and the half
this omission would otherwise cost, "the module asks about time at all", is not the
hazard here. The hazard is asking the *wrong* clock.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# E5-12's work order spells the path twice. Held here as a literal rather than
# imported from `tests/fixtures/benchmark_history.py` for the reason this module's
# docstring gives about the detector: these two tests are the only ones in the
# suite that read the script as *text*, and they say where they read it from.
SEEDER_SCRIPT = REPO_ROOT / "scripts" / "seed_benchmark_history.py"

# ADR 0109's module: the one sanctioned answer to "what time is it" in this
# codebase, and the only clock whose answer the development override moves.
CLOCK_MODULE = "app.services.clock"
CLOCK_MODULE_TAIL = "clock"

# The readings this script may not take for itself. `now` and `today` are the two
# the rule is about; `utcnow` is the deprecated spelling of the first and is what a
# copied snippet arrives as; `time` and `time_ns` are `time.time()`, which the
# window service's sweep leaves alone because that module has no use for it and
# which a seeder stamping a generated row might reach for.
FORBIDDEN_READINGS = frozenset({"now", "utcnow", "today", "time", "time_ns"})

# A date written down rather than derived. The two spellings: a `date(...)` or
# `datetime(...)` built from integer constants, and an ISO date inside a string.
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
DATE_CONSTRUCTORS = frozenset({"date", "datetime"})

# Samples that must be caught, and samples that must not. Every one is whole
# lines, copied rather than retyped (`docs/MISTAKES.md` entry 3).
CLOCK_CANARIES = {
    "today's date off the system clock": (
        "from datetime import date\n" "\n" "def anchor(section):\n" "    return date.today()\n"
    ),
    "a direct reading of the system clock": (
        "from datetime import UTC, datetime\n"
        "\n"
        "def stamp():\n"
        "    return datetime.now(UTC)\n"
    ),
    "the deprecated spelling": (
        "from datetime import datetime\n" "\n" "def stamp():\n" "    return datetime.utcnow()\n"
    ),
    "the reading taken through an aliased class": (
        "from datetime import datetime as dt\n" "\n" "def stamp():\n" "    return dt.now()\n"
    ),
    "the seconds since the epoch": (
        "import time\n" "\n" "def stamp():\n" "    return time.time()\n"
    ),
}

CLOCK_ALLOWED = {
    "the clock service reached as a module": (
        "from app.services import clock\n"
        "\n"
        "def effective(session, settings):\n"
        "    return clock.now(session, settings=settings)\n"
    ),
    "the clock service's function imported by name": (
        "from app.services.clock import now\n"
        "\n"
        "def effective(session, settings):\n"
        "    return now(session, settings=settings)\n"
    ),
    "a date built out of the term calendar": (
        "from datetime import timedelta\n"
        "\n"
        "def course_week_monday(start_date, course_week):\n"
        "    return start_date + timedelta(days=(course_week - 1) * 7)\n"
    ),
    "an instant combined from a day and a wall time": (
        "from datetime import datetime\n"
        "\n"
        "def opens_at(monday, opens, zone):\n"
        "    return datetime.combine(monday, opens, tzinfo=zone)\n"
    ),
}

LITERAL_DATE_CANARIES = {
    "a term start written into the plan": (
        "from datetime import date\n" "\n" "PRIOR_TERM_START = date(2026, 1, 12)\n"
    ),
    "a window instant written into the plan": (
        "from datetime import UTC, datetime\n"
        "\n"
        "FIRST_CLOSE = datetime(2026, 1, 19, 4, 59, 59, tzinfo=UTC)\n"
    ),
    "a date written as a string": 'SPRING_2026 = {"start": "2026-01-12"}\n',
}

LITERAL_DATE_ALLOWED = {
    "a date read off a term row": (
        "def plan(term, letter_row):\n"
        "    start = letter_row.start_date\n"
        "    return start, term.start_date\n"
    ),
    "a length in weeks and a day offset": (
        "from datetime import timedelta\n"
        "\n"
        "LENGTH_WEEKS = 12\n"
        "\n"
        "def ends_on(start):\n"
        "    return start + timedelta(days=LENGTH_WEEKS * 7 - 1)\n"
    ),
    "a date parsed from a value the caller supplied": (
        "from datetime import date\n"
        "\n"
        "def as_date(value):\n"
        "    return value if isinstance(value, date) else date.fromisoformat(value)\n"
    ),
}


class ClockReadings(ast.NodeVisitor):
    """Every reading of "now" in one module, and whether it went through the clock service."""

    def __init__(self) -> None:
        self.clock_modules: set[str] = set()
        self.clock_functions: set[str] = set()
        self.direct: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast's own spelling
        for alias in node.names:
            if alias.name == CLOCK_MODULE:
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


def clock_readings_in(source: str) -> ClockReadings:
    """Walk one module's source and report what it does about time."""
    found = ClockReadings()
    found.visit(ast.parse(source))
    return found


def docstring_nodes(tree: ast.AST) -> set[int]:
    """Every string node that is a docstring, by identity.

    Docstrings are excused because this seeder's module docstring *is* the runbook
    — the work order puts "The drive, end to end" in it — and a runbook that could
    not quote a date would be a worse record. The rule is about the dates the
    script computes with, and `docs/MISTAKES.md` entry 43 is the incident behind
    excusing prose rather than widening a guard to tolerate it.
    """
    excused: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                excused.add(id(first.value))
    return excused


def written_dates_in(source: str) -> list[tuple[int, str]]:
    """Every calendar date this module holds as a literal rather than deriving."""
    tree = ast.parse(source)
    excused = docstring_nodes(tree)
    written: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if (
                node.func.id in DATE_CONSTRUCTORS
                and len(node.args) >= 3
                and all(
                    isinstance(argument, ast.Constant) and isinstance(argument.value, int)
                    for argument in node.args[:3]
                )
            ):
                written.append((node.lineno, ast.unparse(node)))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in excused
            and ISO_DATE.search(node.value)
        ):
            written.append((node.lineno, node.value.strip()[:80]))
    return written


def require_the_seeder_script() -> str:
    """The script's text, or a plain sentence saying it is not there yet."""
    assert SEEDER_SCRIPT.is_file(), (
        f"{SEEDER_SCRIPT.relative_to(REPO_ROOT)} does not exist. E5-12 writes the prior-term "
        "benchmark seeder there — the work order spells the path — and criterion 2 is a rule about "
        "what is in it."
    )
    return SEEDER_SCRIPT.read_text(encoding="utf-8")


def test_the_two_detectors_catch_what_they_claim_and_allow_what_they_claim() -> None:
    """The control, run before either sweep's silence about the seeder counts as evidence.

    Eight samples that must be caught and seven that must not, and the pairs matter
    more than the lists. `clock.now(session, settings=settings)` and
    `datetime.now(UTC)` are both a call to something named `now`; `date(2026, 1, 12)`
    and `date.fromisoformat(value)` are both a date being made. A rule that cannot
    tell each pair apart is either red against every correct build or blind to every
    wrong one, and `docs/MISTAKES.md` entry 3 says a pattern nobody has watched
    catch anything is not evidence of the thing it was searched for.
    """
    for case, sample in sorted(CLOCK_CANARIES.items()):
        assert clock_readings_in(sample).direct, (
            f"The clock sweep found no direct reading in {case}:\n{sample}\nA detector that has "
            "gone blind reads exactly like a seeder that derives every date it writes."
        )

    for case, sample in sorted(CLOCK_ALLOWED.items()):
        found = clock_readings_in(sample)
        assert not found.direct, (
            f"The clock sweep read {found.direct} out of {case}:\n{sample}\nThe last two allowed "
            "samples are the ones a careless rule breaks on: a date built out of a term's own "
            "calendar, and an instant combined from a day and a wall time, are both how this "
            "seeder is expected to work."
        )

    for case, sample in sorted(LITERAL_DATE_CANARIES.items()):
        assert written_dates_in(sample), (
            f"The written-date sweep found nothing in {case}:\n{sample}\nEach of these is a date "
            "the world would then hold twice — once in `scripts/seed.py`'s calendar rows and once "
            "here — which is the silent policy E5-12's known traps name."
        )

    for case, sample in sorted(LITERAL_DATE_ALLOWED.items()):
        assert not written_dates_in(sample), (
            f"The written-date sweep read {written_dates_in(sample)} out of {case}:\n{sample}\n"
            "Deriving a date from a term row, from a length in weeks, or from a value handed in is "
            "exactly what criterion 2 asks for, and a rule that flagged those would be red against "
            "every correct build."
        )


def test_the_benchmark_history_seeder_takes_no_reading_of_the_system_clock() -> None:
    """E5-12 criterion 2's first half, and the E4-22 trap class it names.

    **The mutation this kills**: `date.today()` — or `datetime.now(UTC).date()` —
    anywhere in the seeder's plan. It is the shortest way to write "when is now",
    and it is invisible in every other test of this ticket: the guard refusals never
    get far enough to compute a date, and the self-check recounts whatever was
    written without knowing what it should have been.

    What it costs when it ships is the E4-22 incident, which the work order calls
    the load-critical step: the roster sync stamps `enrollment.started_on` from the
    effective development clock, and anything else in the drive that takes its date
    from the real clock puts a prior term's students in the present. Every windowed
    figure for the cohort is then silently wrong, and the world reads as plausible
    until somebody asks why a benchmark is empty.

    **The near miss it must not fire on**: `datetime.combine(...)` and
    `start + timedelta(...)`, which are how a seeder turns a term's calendar into
    the instants it writes. The control above holds the pair apart.
    """
    found = clock_readings_in(require_the_seeder_script())

    assert not found.direct, "\n".join(
        [
            f"{SEEDER_SCRIPT.relative_to(REPO_ROOT)} reads the system clock directly:",
            *(f"  line {line}: {expression}" for line, expression in found.direct),
            "",
            "E5-12 criterion 2: every seeded date derives from the term calendar and the section "
            "codes, and nothing reads the wall clock at write time. ADR 0109 makes "
            f"`{CLOCK_MODULE}` the one place this codebase asks what time it is, and it is the "
            "only clock the development override moves — which is the clock this whole drive is "
            "anchored to before a single launch happens.",
        ]
    )


def test_the_benchmark_history_seeder_writes_no_calendar_date_of_its_own() -> None:
    """E5-12 criterion 2's second half, and the silent policy its known traps name.

    **The mutation this kills**: a plan that carries the prior term's dates as
    literals — `PRIOR_TERM_START = date(2026, 1, 12)`, a start-letter start date, a
    window instant — instead of reading the rows `scripts/seed.py` seeded. Every
    other test of this ticket is green against that seeder, because the numbers it
    produces are not asserted anywhere and a literal agrees with itself.

    What it costs is the trap stated in the ticket: "a prior term's map is not this
    term's", and the same thing one level down. The calendar is configuration; the
    moment somebody moves the prior term's start by a week, the seeded map rows move
    and this script's constants do not, and the world holds two calendars that
    disagree with no gate between them. `docs/MISTAKES.md` entry 19 is that failure
    in its general form.

    **The near misses it must not fire on**: a date read off a term or map row, a
    length in weeks, a `timedelta` offset, and a date parsed from something handed
    in. The control above holds all four. Docstrings are excused, because this
    script's module docstring is the drive's runbook and quoting a date in a runbook
    is a record rather than a policy.
    """
    written = written_dates_in(require_the_seeder_script())

    assert not written, "\n".join(
        [
            f"{SEEDER_SCRIPT.relative_to(REPO_ROOT)} holds calendar dates of its own:",
            *(f"  line {line}: {found}" for line, found in written),
            "",
            "E5-12 scope: 'the prior term itself as configuration: term rows, its start-letter "
            "map, windows — derived per §2.2, hand-entered nowhere', and criterion 2 applies the "
            "same rule to what this script writes. The term row and the `start_letter_map` rows "
            "are where those dates live; read them. If one of these is genuinely not a calendar "
            "date, say so in the pull request — the rule is worth a sentence of explanation rather "
            "than a widened sweep (`docs/MISTAKES.md` entry 43).",
        ]
    )
