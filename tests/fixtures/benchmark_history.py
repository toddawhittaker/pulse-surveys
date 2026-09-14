"""E5-12 — the prior-term benchmark seeder, run and read the way the ticket runs it.

Four test modules ask things of `scripts/seed_benchmark_history.py`, and three of
them need the same three answers: where the script is, how it is started, and how
many rows a database held before and after a run. A copy of each in three modules
is `docs/MISTAKES.md` entry 13, so they live here.

**Nothing in this file asserts anything.** Every helper either answers a reading
or stops with `pytest.fail` naming what it could not find, and every guard is a
plain function the *test body* calls as its first statement — never a fixture.
While E5-12 is unbuilt each module has to be a wall of FAILEDs naming the missing
deliverable rather than a wall of setup ERRORs, which is `docs/MISTAKES.md`
entry 44's rule and the difference between a red suite and a broken one.

**The invocation is the ticket's, copied rather than paraphrased**
(`docs/MISTAKES.md` entry 37). The work order runs this seeder the way E4-20 runs
the demo story — `docker compose exec -T api python - < scripts/seed_benchmark_history.py`
— so `run_the_benchmark_seeder` pipes the file's text into `python -`. What that
reproduces: the script's own directory is not on `sys.path`, and `__file__` is
undefined, so a script reaching for either fails here the way it would fail in the
container. What it does not reproduce: the container's image, its interpreter and
its network. The database is the calling module's own, reached over the
environment `tests/fixtures/seed.py`'s `DemoSeed` lays down.

**This module carries no fixtures**, so it is deliberately absent from
`pytest_plugins` and listed instead in the last group of `tests/conftest.py`'s
index — the same standing `fixtures/indexes.py`, `fixtures/statements.py` and
`fixtures/migration_journey.py` have. Test modules import it directly.

**What is named here and what is deliberately not.** The script's path is the
work order's, spelled twice there. The section-code pattern is SPEC §2.2's shape
(`{startLetter}{ordinal}{modality}` under an LMS prefix and course number, as the
mock platform spells `BIOL-310-R7FF`), and it is written out here rather than
imported from anything the ticket edits, so the expectation and the thing checked
are not one fact in one blast radius (`docs/MISTAKES.md` entry 19). The
pattern has its own canary control in the refusal module beside it
(`test_the_benchmark_history_seeder_refuses_a_deployment_and_an_unlaunched_world`);
a search nobody has watched catch anything is entry 3.

The recount contract at the foot of this file was the one thing here the ticket
left open. It was **ruled on 2026-09-13** and is now a settled name and signature,
`the_cohort_recount(session, section_codes)`; the constants carrying it say which
parts the ruling spells and which two are still this suite's reading.

**The seeded calendar readers, and the launched world, are here for one reason
each.** The calendar readers — `prior_term`, `map_rows_for`, `term_link_column`
and the rest — were written in the calendar module and moved here when the
launched-world builder needed the same answers; `docs/MISTAKES.md` entry 13 is
about exactly that, and `term_link_column` in particular is a quirk worked around
(ADR 0018's composite `(term_id, term_length_weeks)` key, `docs/disputes/
E5-12-01.md`) that must not be worked around twice.

The launched world exists because **every test in this suite until now stopped at
a refusal, so the seeder's write path was never executed** — which the mutation
battery found as three survivors. `plant_a_launched_prior_term_world` builds, row
by row, the world four anchored staff launches and a roster sync would have left:
the sections the seeder names, under the courses their codes name, in the prior
term the seed wrote, with a window for every course week and a roster enrolled from
the section's first day. It plants **only what a launch and a sync write** — never
a `response` and never an `answer` — so the seeder still has all of its own work to
do, and `docs/MISTAKES.md` entry 48's rule (the tool provisions nothing) is
unchanged: the test is standing in for the platform here, not the seeder.
"""

import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from fixtures.grading import (
    ENDED_ON_COLUMN,
    ENROLLMENT_TABLE,
    RESPONSE_SECTION_COLUMN,
    RESPONSE_USER_COLUMN,
    RESPONSE_WEEK_COLUMN,
    STARTED_ON_COLUMN,
)
from fixtures.provisioning import (
    LETTER_COLUMN,
    LETTER_LENGTH_COLUMNS,
    LETTER_START_COLUMNS,
    PREFIX_CODE_COLUMNS,
    TERM_END_COLUMNS,
    TERM_LENGTH_COLUMNS,
    TERM_START_COLUMNS,
)
from fixtures.repo import REPO_ROOT
from fixtures.supervision import require_column, require_table, single_primary_key
from fixtures.survey_windows import (
    FALL_2026_TERM_START,
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SURVEY_WINDOW_TABLE,
    TERM_TABLE,
    WEEK_NUMBER_COLUMN,
    WEEK_TABLE,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
)
from fixtures.web_identity import USER_SUBJECT_COLUMN

# ---------------------------------------------------------------------------
# The program.
# ---------------------------------------------------------------------------

# E5-12's work order spells the path: "A new seeder, not a fattened demo-story:
# scripts/seed_benchmark_history.py".
BENCHMARK_HISTORY_SCRIPT_PATH = REPO_ROOT / "scripts" / "seed_benchmark_history.py"

# The variable a deployment is named by, and the two values these modules run
# under. Settled by ADR 0063 and by `app.config`'s own `is_development` predicate,
# which the work order names as the mechanism (item 1: "the raw ENVIRONMENT
# refusal BEFORE any app import plus the is_development second belt").
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEPLOYED_ENVIRONMENT_VALUE = "production"
DEVELOPMENT_ENVIRONMENT = "development"

# What this suite will read as the environment guard's own refusal, and what it
# deliberately will not. The bare word "development" is not enough: a refusal
# about a missing section can reasonably say "launch it on your development stack
# first", and a matcher that accepted that would go green against a script with no
# environment guard at all — `docs/MISTAKES.md` entry 3's shape exactly, since the
# two runs in the refusal module differ only in this variable. So the refusal has
# to name the variable or quote the value it found. Copied in substance from
# E4-20's module, which argues it at length.
ENVIRONMENT_REFUSAL_MARKERS = (ENVIRONMENT_VARIABLE, DEPLOYED_ENVIRONMENT_VALUE)

# What an uncaught exception prints. Used to tell a guard's refusal from the
# process dying, which is a distinction the exit status cannot make.
TRACEBACK_MARKER = "Traceback (most recent call last)"

# The tables a benchmark-history seeder's rows would land in, and the whole reason
# the "wrote nothing" assertions are not vacuous: a database whose tables a module
# never counted would compare equal to itself perfectly. E2-08 spells both names.
# Comment text is a column on `answer` rather than a table of its own, which is why
# there are two names here and not three.
WRITABLE_TABLES = ("response", "answer")

# How long one run may take before a test stops waiting. **This file's choice**,
# and a bound rather than a requirement: every run in these modules is supposed to
# refuse before doing any work, so anything approaching this is a hang — most
# likely a script waiting on a connection it cannot open — and reporting that as a
# failed criterion would send the reader to the wrong place.
BENCHMARK_HISTORY_TIMEOUT_SECONDS = 180

# A section code as SPEC §2.2 shapes one, under the LMS prefix and course number
# the mock platform spells it with (`BIOL-310-R7FF`): a course prefix, a course
# number, then `{startLetter}{ordinal}{modality}` with `WW` online and `FF`
# face-to-face. **Deliberately not derived** from anything E5-12 writes — a
# pattern read out of the seeder would follow a rename into matching whatever the
# seeder printed (`docs/MISTAKES.md` entry 19).
SECTION_CODE_PATTERN = re.compile(r"\b[A-Z]{2,8}-\d{3,4}-[A-Z0-9]\d{1,2}(?:WW|FF)\b")

# Sentences the pattern must find a code in, and sentences it must not. Run by the
# control test before any module's silence about a refusal counts as evidence
# (`docs/MISTAKES.md` entry 3: give a search a canary, so a search that has gone
# blind says so). The first sample is the whole refusal line E4-20's seeder prints,
# copied as a line rather than retyped from where the sentence looks like it starts.
CODE_BEARING_SAMPLES = {
    "a refusal naming one section": (
        "Refusing: BIOL-310-R7FF is not in this database. Launch it from the mock "
        "platform as the instructor, then run the roster sync, then try again."
    ),
    "a refusal naming several": ("Missing sections: BIOL-310-U1FF, BIOL-310-U2FF, BIOL-240-E1WW."),
    "a code at the end of a line": "The section this seeder fills is BIOL-310-R7FF",
}

CODE_FREE_SAMPLES = {
    "the environment refusal": (
        "Refusing to run: ENVIRONMENT is 'production'. This seeder writes demonstration data and "
        "runs only on a development stack (ADR 0063)."
    ),
    "a refusal that names nothing": "Refusing: the world this seeder needs is not there.",
    "prose carrying an ordinary hyphenated word": (
        "The prior-term world is seeded after the roster sync, week-by-week."
    ),
}


class SeederRun(NamedTuple):
    """One execution of `scripts/seed_benchmark_history.py`, as the shell sees it.

    Both streams are kept, and every assertion reads them together: which of the
    two a refusal is printed on is a free choice, and pinning it would be this
    suite deciding something the ticket leaves open.
    """

    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return f"{self.stdout}\n{self.stderr}"

    def report(self) -> str:
        """The run, rendered for a failure message, with both streams tailed."""
        return (
            f"`python - < {BENCHMARK_HISTORY_SCRIPT_PATH}` exited {self.returncode}.\n"
            f"stdout:\n{self.stdout[-2000:]}\nstderr:\n{self.stderr[-2000:]}"
        )


def require_the_benchmark_history_seeder() -> None:
    """Stop with a plain sentence unless E5-12's script is there to run.

    In the test body and never in a fixture (`docs/MISTAKES.md` entry 44).
    """
    if not BENCHMARK_HISTORY_SCRIPT_PATH.is_file():
        pytest.fail(
            f"{BENCHMARK_HISTORY_SCRIPT_PATH} does not exist, so there was nothing to run. E5-12 "
            "writes it: a second seeder modelled on `scripts/seed_demo_story.py`, piped into the "
            "api container, refusing outside a development environment, refusing a world whose "
            "prior-term sections were never launched, and provisioning no person, section, "
            "enrollment, week or window of its own. Those refusals are what this suite asserts, "
            "and none of them can be asked of a file that is not there."
        )


def run_the_benchmark_seeder(demo: Any, **overrides: str | None) -> SeederRun:
    """Pipe the script into an interpreter against `demo`'s database, and report what happened.

    **Nothing here asserts anything.** The run is handed back and each test decides
    what it means, so a refusal that came for the wrong reason produces a failed
    assertion naming the criterion rather than an error inside a helper.

    The environment is `DemoSeed`'s — every variable `tests/fixtures/seed.py`'s
    `seed_environment` lays down — with `overrides` applied last. The parent's
    environment is inherited underneath and then overwritten: the child reads the
    repository's `.env` too, so a test that cares about a value states it here
    rather than relying on absence (`docs/MISTAKES.md` entries 30 and 40).
    """
    child_environment = {**os.environ, **demo.environment}
    for name, value in overrides.items():
        if value is None:
            child_environment.pop(name, None)
        else:
            child_environment[name] = value
    try:
        # S603: the command is this interpreter, and the program arrives on
        # standard input from a path built out of the repository root. Nothing in
        # either comes from input.
        completed = subprocess.run(  # noqa: S603
            [sys.executable, "-"],
            input=BENCHMARK_HISTORY_SCRIPT_PATH.read_text(encoding="utf-8"),
            cwd=REPO_ROOT,
            env=child_environment,
            capture_output=True,
            text=True,
            timeout=BENCHMARK_HISTORY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"`python - < {BENCHMARK_HISTORY_SCRIPT_PATH}` did not finish in "
            f"{BENCHMARK_HISTORY_TIMEOUT_SECONDS} seconds. Every run in this suite is supposed to "
            "refuse before doing any work, so this is a hang rather than a failed criterion — a "
            "script waiting on a connection it cannot open looks exactly like this."
        )
    return SeederRun(
        returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )


def row_counts(demo: Any, tables: Mapping[str, Any]) -> dict[str, int]:
    """How many rows every declared table holds, right now."""
    with demo.connect() as connection:
        return {
            name: connection.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in tables.items()
        }


def require_the_writable_tables(counts: Mapping[str, int]) -> None:
    """Stop unless the tables this seeder writes are among the ones being counted.

    Without this the "wrote nothing" assertions are satisfied by a count that never
    looked: an empty mapping compares equal to an empty mapping, and a seeder that
    filled `response` and `answer` would pass every one of them
    (`docs/MISTAKES.md` entry 3).
    """
    absent = [name for name in WRITABLE_TABLES if name not in counts]
    if absent:
        pytest.fail(
            f"{absent} are not among the tables this module counted, so 'the run wrote nothing' "
            f"would be a statement about a query that never ran. Counted: {sorted(counts)}. Those "
            "names come from E2-08's schema; a deliberate rename is a one-line change in "
            "tests/fixtures/benchmark_history.py."
        )


def changed_counts(
    before: Mapping[str, int], after: Mapping[str, int]
) -> dict[str, tuple[int, int]]:
    """Every table whose row count moved between two readings, as `(before, after)`."""
    return {name: (before[name], after[name]) for name in before if before[name] != after[name]}


def reads_as_the_environment_refusal(text: str) -> bool:
    """Whether one run's output says it stopped over the environment it was given."""
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in ENVIRONMENT_REFUSAL_MARKERS)


def section_codes_in(text: str) -> list[str]:
    """Every section code, in SPEC §2.2's shape, that a run printed — in the order printed.

    Duplicates are dropped and the order of first appearance is kept, so a test that
    takes "the first section the seeder named" gets a stable answer.
    """
    seen: list[str] = []
    for match in SECTION_CODE_PATTERN.finditer(text):
        code = match.group(0)
        if code not in seen:
            seen.append(code)
    return seen


# ---------------------------------------------------------------------------
# Reading `section` in a seeded database.
#
# **Two currencies, and they are not interchangeable.** A *label* is what a person
# and a mock platform call a placement — `BIOL-310-U5FF`, a course prefix, a course
# number and SPEC §2.2's code — and it is what the seeder prints when it refuses.
# The *code* is what §2.2 actually defines and what `section.lms_section_code`
# stores: the bare `U5FF`. Every seeded section in this repository holds the bare
# form (`U1WW`, `R1FF`, `21WW`), and a lookup by label matches nothing at all.
#
# That cost this suite two rounds and one silently vacuous assertion: a check that
# "the section the refusal named is not in this database" was true of every string
# ever passed to it, because the query could not match whatever it was given —
# `docs/MISTAKES.md` entry 3, in a test that looked like it was doing its job. So
# the two currencies are named here, converted in one place, and every caller says
# which one it holds.
# ---------------------------------------------------------------------------

# E0-05's table and column, the pair every other module in this suite reads a
# section code off. Not this file's choice.
SECTION_TABLE = "section"
SECTION_CODE_COLUMN = "lms_section_code"

# The rest of the table and column names the launched world is planted through.
# Each is spelled by the schema that shipped it — E0-05's containment tables and
# their `lms_number`, E2-05's survey tables — and read the same way in
# `tests/fixtures/benchmark_views.py` and `tests/fixtures/submit.py`.
COURSE_NUMBER_COLUMN = "lms_number"
USER_TABLE = "user"
RESPONSE_TABLE = "response"
ANSWER_TABLE = "answer"


def bare_code(label: str) -> str:
    """SPEC §2.2's code out of a label: `BIOL-310-U5FF` → `U5FF`.

    The one place the conversion happens. A label that is already bare is handed
    back unchanged, so a caller holding either form gets the stored currency.
    """
    return label if "-" not in label else parse_section_code(label)[2]


def sections_coded(
    demo: Any,
    tables: Mapping[str, Any],
    label: str,
    *,
    term: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    """Every `section` row carrying `label`'s **code**, whole, as the database holds it now.

    `term` narrows the answer to one term, and callers asking "was this placement
    ever launched" should pass it: §2.2's codes are per-term data, so `U1WW` names
    a different section in every term that has a `U` letter, and an unnarrowed
    lookup answers about a section in another term.
    """
    section = tables.get(SECTION_TABLE)
    if section is None or SECTION_CODE_COLUMN not in getattr(section, "c", {}):
        pytest.fail(
            f"There is no `{SECTION_TABLE}.{SECTION_CODE_COLUMN}` to read (tables: "
            f"{sorted(tables)}). E0-05 creates that table and names that column, and nothing in "
            "this suite can mean anything without it."
        )
    statement = section.select().where(section.c[SECTION_CODE_COLUMN] == bare_code(label))
    if term is not None:
        link = primary_key_link(section, TERM_TABLE)
        if link is None:
            pytest.fail(
                f"`{SECTION_TABLE}` does not name a `{TERM_TABLE}` row's primary key through one "
                f"column; it has {[one.name for one in section.columns]}. A lookup narrowed to a "
                "term cannot be made without it."
            )
        key = single_primary_key(require_table(dict(tables), TERM_TABLE))
        statement = statement.where(section.c[link] == term[key])
    with demo.connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings()]


# ---------------------------------------------------------------------------
# The self-check's recount, as the ruling of 2026-09-13 settles it.
# ---------------------------------------------------------------------------

# The name `scripts/seed_benchmark_history.py` is imported under. Not
# `seed_benchmark_history`, which is a plausible name for something else on
# `sys.path` to own, and not `scripts.seed_benchmark_history`, which would imply a
# package that does not exist. The same choice `tests/fixtures/seed.py` makes for
# `scripts/seed.py`.
BENCHMARK_HISTORY_MODULE_NAME = "pulse_benchmark_history_seed"

# The self-check's recount, **as the owner's ruling of 2026-09-13 settles it**:
# "the seeder exports `the_cohort_recount(session, section_codes)` — first
# parameter a SQLAlchemy Session, second an explicit sequence of section codes
# naming the sections whose cohorts to recount. It returns counts per
# (length_weeks, level, course_week): distinct section count and distinct student
# count, recounted from the database, never from the plan. main() aims it at the
# seeder's own codes and separately compares against the two benchmark_min_*
# config values, exiting nonzero on failure."
#
# So the name and both parameters are the ruling's and not this file's, and they
# are positional here because that is how the ruling writes the signature. The
# explicit code list is what lets a test recount a world it planted itself: before
# the ruling, a recount narrowed to the seeder's own codes could not have been
# exercised by any test at all.
RECOUNT_FUNCTION_NAME = "the_cohort_recount"

# The key of a recounted row, spelled by the same ruling: "counts per
# (length_weeks, level, course_week)". No alternatives, because there is now a
# record to read them off.
COHORT_KEY_FIELDS = {
    "length_weeks": ("length_weeks",),
    "level": ("level",),
    "course_week": ("course_week",),
}
# How the two counts are spelled on a returned row. **The two things the ruling
# leaves open**: it names the quantities — "distinct section count and distinct
# student count" — and not the attribute names, so these stay candidate lists.
# Each first entry is the column E5-03's `benchmark_cohort_week` view already
# returns for exactly that quantity, which is the likeliest source the recount
# reads from.
RESPONDENT_COUNT_FIELDS = (
    "respondent_count",
    "student_count",
    "distinct_students",
    "students",
    "respondents",
)
SECTION_COUNT_FIELDS = ("section_count", "sections", "distinct_sections")


def benchmark_history_module() -> Any:
    """`scripts/seed_benchmark_history.py` as a module, for the question a subprocess cannot ask.

    Called from a test body, never a fixture, so that an unbuilt E5-12 is a FAILED
    naming the script rather than an ERROR in setup (`docs/MISTAKES.md` entry 44).

    Imported by path, because `scripts/` is not a package and nothing puts it on
    `sys.path` — `tests/fixtures/seed.py`'s `seed_module` does the same for
    `scripts/seed.py` and explains why. **Imported under `ENVIRONMENT=development`**,
    which is the opposite of the safety net that fixture uses, and the reason is
    the work order's item 1: this seeder's environment guard reads the raw
    `ENVIRONMENT` *before any app import*, so under any other value the import
    itself is refused and nothing in the module can be reached. A module that seeds
    at import time rather than under `if __name__ == "__main__":` is therefore
    reported here as what it is.
    """
    require_the_benchmark_history_seeder()

    specification = importlib.util.spec_from_file_location(
        BENCHMARK_HISTORY_MODULE_NAME, BENCHMARK_HISTORY_SCRIPT_PATH
    )
    if specification is None or specification.loader is None:
        pytest.fail(
            f"Python cannot build an import specification for {BENCHMARK_HISTORY_SCRIPT_PATH}, so "
            "it cannot be imported as a module. That is a defect in this helper or a file that is "
            "not Python."
        )

    cached = sys.modules.get(BENCHMARK_HISTORY_MODULE_NAME)
    if cached is not None:
        return cached

    module = importlib.util.module_from_spec(specification)
    sys.modules[BENCHMARK_HISTORY_MODULE_NAME] = module
    previous = os.environ.get(ENVIRONMENT_VARIABLE)
    os.environ[ENVIRONMENT_VARIABLE] = DEVELOPMENT_ENVIRONMENT
    try:
        specification.loader.exec_module(module)
    except SystemExit as refused:
        sys.modules.pop(BENCHMARK_HISTORY_MODULE_NAME, None)
        pytest.fail(
            f"Importing {BENCHMARK_HISTORY_SCRIPT_PATH} under "
            f"`{ENVIRONMENT_VARIABLE}={DEVELOPMENT_ENVIRONMENT}` exited ({refused}). The script's "
            "own guard is the likeliest cause, and under a development environment it is supposed "
            "to pass — so either the guard's comparison is inverted, which the refusal module "
            "asserts from the other side, or the script does its work at import time instead of "
            'under `if __name__ == "__main__":`.'
        )
    except Exception as broke:  # pragma: no cover - a red, not a branch
        sys.modules.pop(BENCHMARK_HISTORY_MODULE_NAME, None)
        pytest.fail(
            f"Importing {BENCHMARK_HISTORY_SCRIPT_PATH} raised {broke!r}. Nothing in E5-12 asks "
            "this script to be importable *as such*; what it asks is that the counting the "
            "self-check does can be exercised, and importing the module is how this suite reaches "
            "it. A script that cannot be imported at all without connecting to something is a "
            "finding for the pull request rather than a red this suite can interpret."
        )
    finally:
        if previous is None:
            os.environ.pop(ENVIRONMENT_VARIABLE, None)
        else:
            os.environ[ENVIRONMENT_VARIABLE] = previous
    return module


def recount_callable(module: Any) -> Any:
    """`the_cohort_recount` off the imported seeder, or a failure naming the deliverable."""
    found = getattr(module, RECOUNT_FUNCTION_NAME, None)
    if not callable(found):
        defined = sorted(name for name in vars(module) if not name.startswith("_"))
        pytest.fail(
            f"The benchmark-history seeder exposes no callable `{RECOUNT_FUNCTION_NAME}`; it "
            f"exposes {defined}. The ruling of 2026-09-13 settles that name and its signature, "
            f"`{RECOUNT_FUNCTION_NAME}(session, section_codes)`, and E5-12 criterion 1 is what it "
            "is for: a self-check that recounts from the database — per cohort-week, the number of "
            "distinct sections and of distinct students. A recount reachable only by running the "
            "whole drive is a number no test can check the currency of, which is "
            "`docs/MISTAKES.md` entry 50's defect with a printed reassurance on top."
        )
    return found


def call_recount(module: Any, session: Any, section_codes: Sequence[str]) -> Sequence[Any]:
    """Call `the_cohort_recount(session, section_codes)` and hand back its rows.

    Positionally, as the ruling writes the signature. Nothing is discovered here
    any more: a `TypeError` from this call is a signature that does not match the
    ruling, and reporting it as anything else would hide which of the two is wrong.
    """
    recount = recount_callable(module)
    answered = recount(session, list(section_codes))
    if answered is None:
        pytest.fail(
            "The recount returned nothing at all. The self-check compares its counts against "
            "`benchmark_min_sections` and `benchmark_min_respondents` and exits non-zero on a "
            "shortfall, so the counts have to be values before they are printed; a recount that "
            "only prints is a number this suite cannot check the currency of."
        )
    return list(answered)


def field_of(row: Any, candidates: Sequence[str]) -> Any:
    """One field off a recounted row, whether the row is a mapping or an object.

    `None` when the row carries none of `candidates`, so a caller can say which
    field it could not find rather than raising something a reader has to decode.
    """
    for candidate in candidates:
        if isinstance(row, Mapping):
            if candidate in row:
                return row[candidate]
        elif hasattr(row, candidate):
            return getattr(row, candidate)
    return None


def cohort_week_row(rows: Sequence[Any], *, length_weeks: int, level: str, course_week: int) -> Any:
    """The one recounted row for one cohort-week key, or a failure saying why there is none.

    The key is the ruling's: "counts per (length_weeks, level, course_week)". The
    term is not part of it, which is what the ruling says and is also the only
    reading that works — the codes handed in decide which sections are counted, so
    a term column would be a fourth key nothing supplies.
    """
    matched = [
        row
        for row in rows
        if field_of(row, COHORT_KEY_FIELDS["length_weeks"]) == length_weeks
        and field_of(row, COHORT_KEY_FIELDS["level"]) == level
        and field_of(row, COHORT_KEY_FIELDS["course_week"]) == course_week
    ]
    if not matched:
        pytest.fail(
            f"The recount answered no row for the cohort ({length_weeks}-week {level}, course week "
            f"{course_week}) this test planted. It answered {list(rows)!r}. The section codes for "
            "that cohort's sections were handed in explicitly, as the ruling's signature requires, "
            "so this is the recount not finding sections it was given rather than a scope this "
            "suite failed to reach: a lookup that resolves a code against the wrong term, or "
            "against a single row where two sections share a cohort, looks exactly like this."
        )
    if len(matched) > 1:
        pytest.fail(
            f"The recount answered {len(matched)} rows for one cohort-week key: {matched!r}. One "
            "key, one row — a second row for one key is a grouping defect, and it is how a count "
            "looks right because only the first of two rows was ever read."
        )
    return matched[0]


def respondent_count_of(row: Any) -> int:
    """The number of distinct students one recounted cohort-week row carries."""
    value = field_of(row, RESPONDENT_COUNT_FIELDS)
    if value is None:
        pytest.fail(
            f"The recounted row {row!r} carries none of {list(RESPONDENT_COUNT_FIELDS)}, so there "
            "is no respondent figure to check the currency of. E5-12's third known trap: the "
            "self-check counts distinct students per cohort-week, 'the unit the minimums compare' "
            "(`docs/MISTAKES.md` entry 50), and a row that does not carry one cannot be the thing "
            "the criterion is about."
        )
    return int(value)


def section_count_of(row: Any) -> int:
    """The number of distinct sections one recounted cohort-week row carries."""
    value = field_of(row, SECTION_COUNT_FIELDS)
    if value is None:
        pytest.fail(
            f"The recounted row {row!r} carries none of {list(SECTION_COUNT_FIELDS)}. The "
            "self-check compares a section count against `benchmark_min_sections` as well as a "
            "respondent count against `benchmark_min_respondents`, and the thin cohort exists to "
            "be under the first of those."
        )
    return int(value)


# ---------------------------------------------------------------------------
# Reading the seeded calendar. Written in
# `tests/integration/test_the_seed_gives_the_prior_term_its_own_start_letter_map.py`
# and moved here when the launched-world builder below needed the same answers
# (`docs/MISTAKES.md` entry 13).
# ---------------------------------------------------------------------------

START_LETTER_MAP_TABLE = "start_letter_map"
COURSE_TABLE = "course"
PREFIX_TABLE = "prefix"


def rows_of(demo: Any, tables: Mapping[str, Any], name: str, **equals: Any) -> list[dict[str, Any]]:
    """Every row of one table, whole, narrowed by whichever columns the caller named."""
    table = require_table(dict(tables), name)
    statement = table.select()
    for column, value in equals.items():
        if column not in table.c:
            pytest.fail(
                f"`{name}` has no column `{column}`; it has "
                f"{[one.name for one in table.columns]}."
            )
        statement = statement.where(table.c[column] == value)
    with demo.connect() as connection:
        return [dict(row) for row in connection.execute(statement).mappings()]


def term_columns(tables: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """`(key, start, end, length)` on `term`, each found among the candidates E0-06 left open."""
    table = require_table(dict(tables), TERM_TABLE)
    return (
        single_primary_key(table),
        require_column(table, TERM_START_COLUMNS),
        require_column(table, TERM_END_COLUMNS),
        require_column(table, TERM_LENGTH_COLUMNS),
    )


def primary_key_link(table: Any, target_table: str) -> str | None:
    """The one column on `table` that names `target_table`'s **primary key**, or `None`.

    See `term_link_column` below for why the primary-key half is not tidiness: a
    composite key into a table whose referenced columns are not all primary keys —
    ADR 0018's `(term_id, term_length_weeks)` — has exactly one column that is, and
    that is the one to follow when you want "which row of `target_table` is this".
    """
    found = sorted(
        {
            key.parent.name
            for key in table.foreign_keys
            if key.column.table.name == target_table and key.column.primary_key
        }
    )
    return found[0] if len(found) == 1 else None


def term_link_column(tables: Mapping[str, Any], name: str) -> str:
    """The column on `name` that names a `term` row's **primary key**.

    **The primary-key half is not tidiness**, and getting it wrong is what
    `docs/disputes/E5-12-01.md` is about. ADR 0018 gives `week` and
    `start_letter_map` one *composite* key into `term` — `(term_id,
    term_length_weeks) → term (id, length_weeks)` — so both of those columns
    reference `term`. A helper that asks for a single-column link finds none and
    answers `None` on every database at head, which is how three correct
    assertions came to fail on their route rather than on their rows; and a helper
    that merely counted references would find two links where there is one
    relationship. Filtering on the referenced column being a primary key leaves the
    one column to follow.

    Copied in shape from `one_foreign_key_column` in
    `tests/integration/test_demo_seed_script.py`, whose own comment records this
    trap against these same two tables. A copy rather than a widening of
    `fixtures.grading.single_column_link`: other tests pin that helper's
    strictness about composite keys, and moving it would move a rule they depend on.
    """
    table = require_table(dict(tables), name)
    found = sorted(
        {
            key.parent.name
            for key in table.foreign_keys
            if key.column.table.name == TERM_TABLE and key.column.primary_key
        }
    )
    if len(found) != 1:
        pytest.fail(
            f"`{name}` names `{TERM_TABLE}`'s primary key through {len(found)} columns ({found}); "
            f"it has {[column.name for column in table.columns]}. SPEC §2.2 makes the weeks and "
            "the start-letter map per-term data and E0-06 gives both tables that link, so without "
            "exactly one such column there is no such thing as 'the prior term's map' and the "
            "modules reading it are unaskable. A fork here is a schema question rather than "
            "something to pick a side of in a test."
        )
    return found[0]


def fall_2026(demo: Any, tables: Mapping[str, Any], seeded: Any) -> dict[str, Any]:
    """The term `scripts/seed.py` seeds the demo institution's current world into.

    The control every caller starts from, and it is not ceremony: a module that
    could not find Fall 2026 is a module reading an empty or unseeded database, and
    "there is a term before Fall 2026" would then be a statement about a query that
    answers nothing (`docs/MISTAKES.md` entry 3).
    """
    _key, start, _end, _length = term_columns(tables)
    terms = rows_of(demo, tables, TERM_TABLE)
    current = [row for row in terms if row[start] == FALL_2026_TERM_START]
    if len(current) != 1:
        pytest.fail(
            f"This database holds {len(current)} terms starting {FALL_2026_TERM_START} - it holds "
            f"{[row[start] for row in terms]}. SPEC §3.1's seeded world is Fall 2026 and "
            "`tests/fixtures/survey_windows.py` carries that date for the whole suite, so nothing "
            "read against it can mean anything until that row is there. The seed run this world "
            f"came from:\n{seeded.report()}"
        )
    return current[0]


def prior_term(demo: Any, tables: Mapping[str, Any], seeded: Any) -> dict[str, Any]:
    """The term E5-12 adds: any term whose dates end before Fall 2026 begins.

    Discovered rather than named: E5-12 suggests "Spring 2026" and settles nothing,
    so a helper that required that name would choose the calendar on the ticket's
    behalf. More than one is not a failure — a world may hold several prior terms —
    but this reads the one that ends latest, which is the term a benchmark reaches
    back into first.
    """
    _key, start, end, _length = term_columns(tables)
    fall = fall_2026(demo, tables, seeded)
    earlier = [
        row
        for row in rows_of(demo, tables, TERM_TABLE)
        if row[end] is not None and row[end] < fall[start]
    ]
    if not earlier:
        pytest.fail(
            "The seeded calendar holds no term ending before Fall 2026 begins, so there is no "
            "prior term for a benchmark to reach into. E5-12's scope puts one in "
            "`scripts/seed.py` beside Fall 2026 - a term row with its own dates, its own "
            "start-letter map and its own week rows - because the exit line says 'benchmarked "
            "against prior terms' and nothing seeded today lives in one. The terms this database "
            f"holds start on {[row[start] for row in rows_of(demo, tables, TERM_TABLE)]}."
        )
    return sorted(earlier, key=lambda row: row[end])[-1]


def map_rows_for(
    demo: Any, tables: Mapping[str, Any], term: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Every `start_letter_map` row belonging to one term."""
    link = term_link_column(tables, START_LETTER_MAP_TABLE)
    key, _start, _end, _length = term_columns(tables)
    return [row for row in rows_of(demo, tables, START_LETTER_MAP_TABLE) if row[link] == term[key]]


# ---------------------------------------------------------------------------
# The launched prior-term world: what four staff launches and a roster sync leave
# behind, planted row by row so the seeder's **write path** can be executed.
# ---------------------------------------------------------------------------

# How many students each planted roster holds. **This suite's choice**, and it is
# the world order's number — "each with a 20-student roster" — rather than a
# convenience: the seeder chooses its weekly respondents out of the roster it
# finds, and a roster smaller than the one the design describes asks it for a
# sample it may not be able to draw.
STUDENTS_PER_SECTION = 20

# How many times the builder will run the seeder, read the sections it says are
# missing, and plant them. **A bound, not a requirement.** The world is built out
# of the program's own refusals rather than out of a list of codes written here, so
# that no test has to know which sections E5-12 chose; this stops that loop turning
# into a hang if the seeder names a new section on every run.
PLANTING_ROUNDS = 6

# SPEC §3.1's rhythm and the institution's default zone, for the windows a launch's
# derivation would have written: "opens Friday 18:00, closes Sunday 23:59:59 ... in
# the institution timezone (default `America/New_York`)". Transcribed from the spec
# and deliberately not read from `app.services.survey_windows`, which is one of the
# things a seeded world is checked against.
INSTITUTION_ZONE = "America/New_York"
WINDOW_OPENS_AT = time(18, 0, 0)
WINDOW_CLOSES_AT = time(23, 59, 59)
FRIDAY_AFTER_MONDAY = 4
SUNDAY_AFTER_MONDAY = 6

# **A roster is a set of subjects, not a count of rows.** The seeder does not ask
# "how many students are enrolled in this section"; it asks for the students whose
# `user.lms_user_id` begins with the mock platform's own generated prefix for that
# placement, and its refusal quotes that prefix in full:
#
#   BIOL-310-U5FF holds no enrollment for any student whose subject begins
#   'mock-lms-user-biol-310-u5ff-student-'
#
# Twenty enrollments whose users carry invented subjects are therefore not a roster
# at all — which is what the builder planted for one round, and the refusal was
# right. The prefix is built from the label the way the mock platform builds it,
# lowercased; the two-digit tail is this file's own choice, because the seeder
# matches on the prefix and needs only that each subject differs. Transcribed from
# the refusal rather than imported from the seeder: a prefix read out of the thing
# under test would follow a rename into agreeing with itself
# (`docs/MISTAKES.md` entry 19).
ROSTER_SUBJECT_PREFIX = "mock-lms-user-{label}-student-"


def roster_subject_prefix(label: str) -> str:
    """The prefix the seeder reads one section's roster by, as its refusal quotes it."""
    return ROSTER_SUBJECT_PREFIX.format(label=label.lower())


def roster_subject(label: str, number: int) -> str:
    """The `user.lms_user_id` the mock platform would have issued for one student."""
    return f"{roster_subject_prefix(label)}{number:02d}"


@dataclass
class PlantedLaunch:
    """One section as a launch and a roster sync would have left it.

    `label` is the whole `BIOL-310-U5FF` a refusal prints; `code` is the bare
    `U5FF` that `section.lms_section_code` stores. Both are kept because both are
    read, and keeping only one is what let a lookup by the wrong currency match
    nothing for two rounds.
    """

    label: str
    code: str
    section: dict[str, Any]
    section_id: Any
    course_weeks: dict[int, dict[str, Any]] = field(default_factory=dict)
    windows: dict[int, dict[str, Any]] = field(default_factory=dict)
    students: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LaunchedWorld:
    """The planted world, and — if the build could not finish — why.

    **`problem` rather than a raised failure**, because this is built in a
    module-scoped fixture and a `pytest.fail` there is an ERROR in setup that
    proves nothing about any criterion (`docs/MISTAKES.md` entry 44). Every test
    calls `require_the_world` as its first statement instead.
    """

    demo: Any = None
    term: dict[str, Any] | None = None
    launches: dict[str, PlantedLaunch] = field(default_factory=dict)
    runs: list[SeederRun] = field(default_factory=list)
    problem: str | None = None

    @property
    def writing_run(self) -> SeederRun | None:
        """The last run the builder made — the one that found the world complete and wrote it."""
        return self.runs[-1] if self.runs else None

    @property
    def codes(self) -> list[str]:
        return sorted(self.launches)


def require_the_world(world: LaunchedWorld) -> LaunchedWorld:
    """Stop with the build's own sentence unless the launched world is there."""
    if world.problem is not None:
        pytest.fail(world.problem)
    return world


def launch_of_section(world: LaunchedWorld, section_id: Any) -> PlantedLaunch:
    """The launch this world planted for one section id — its label and its row.

    Read off the world rather than out of the database, because the row carries only
    the bare code while a refusal names the label, and because a caller planting
    beside that section wants the row it already has. A section id this world did not
    plant is a caller's mistake rather than a missing row, and says so.
    """
    for launch in world.launches.values():
        if launch.section_id == section_id:
            return launch
    pytest.fail(
        f"This world planted no section with id {section_id}; it planted "
        f"{[(launch.label, str(launch.section_id)) for launch in world.launches.values()]}."
    )
    raise AssertionError  # pragma: no cover - `pytest.fail` does not return


def parse_section_code(code: str) -> tuple[str, str, str]:
    """`(prefix, course number, the §2.2 code)` for a section code like `BIOL-310-U5FF`.

    SPEC §2.2 shapes the last part — `{startLetter}{ordinal}{modality}` — and E0-05
    stores the whole string in `section.lms_section_code`; the two parts in front of
    it are the course's prefix and number, which is how every seeded code in this
    repository is spelled.
    """
    parts = code.split("-")
    if len(parts) != 3 or not all(parts):
        pytest.fail(
            f"{code!r} is not a section code this suite can take apart. SPEC §2.2's codes are a "
            "course prefix, a course number and `{startLetter}{ordinal}{modality}`, joined by "
            "hyphens, as `BIOL-310-R7FF` is."
        )
    return parts[0], parts[1], parts[2]


def link_values(table: Any, target: Any, target_row: Mapping[str, Any]) -> dict[str, Any]:
    """Every column on `table` that names a row of `target`, filled from `target_row`.

    **Why the linkage is written out rather than left to the seeding walker's
    chain.** The walker invents whatever ancestor a row needs that the caller did
    not supply, and an invented ancestor is exactly the failure this builder cannot
    afford: a section hung on a *new* term is a section the seeder's
    `(prefix, course number, term, code)` lookup will never find, and the symptom is
    a refusal naming sections that are visibly in the database. Supplying every
    naming column by hand leaves nothing to invent.

    **Two ways a row can name another, and this follows both.**

      - *A foreign key*, followed rather than guessed at, so a **composite** link is
        filled in full: ADR 0018 gives the calendar tables `(term_id,
        term_length_weeks) → term (id, length_weeks)`, and a helper that filled only
        the id would leave the walker to invent the other half of the pair.
      - *A column with no constraint of its own to follow.* `survey_window` carries
        `term_id` and holds **no** foreign key into `term`: its only constraint into
        the calendar is the composite `(week_id, term_id)` into `week`, which is
        E2-05's "window's term rule" — a window's term is its week's term, enforced
        through the week rather than beside it. Asking for a key that is not there
        was this builder's second failure in two runs, and it raised inside a fixture,
        so what it cost was a wall of setup errors. Where the constraint is absent
        and the column is there, it is filled from `target_row`'s primary key.

    Where both apply, the foreign key wins: it is the value the database will check.
    """
    values: dict[str, Any] = {}
    for key in table.foreign_keys:
        if key.column.table.name != target.name:
            continue
        referenced = key.column.name
        if referenced not in target_row:
            pytest.fail(
                f"`{table.name}.{key.parent.name}` references `{target.name}.{referenced}`, and "
                f"the row handed in does not carry that column; it carries {sorted(target_row)}."
            )
        values[key.parent.name] = target_row[referenced]
    if values:
        return values

    key_column = single_primary_key(target)
    named = f"{target.name}_{key_column}"
    if named in table.c:
        if key_column not in target_row:
            pytest.fail(
                f"`{table.name}.{named}` names a `{target.name}` row, and the row handed in does "
                f"not carry `{key_column}`; it carries {sorted(target_row)}."
            )
        return {named: target_row[key_column]}

    pytest.fail(
        f"`{table.name}` neither references `{target.name}` nor carries a `{named}` column; its "
        f"columns are {[one.name for one in table.columns]}. This builder plants a world by "
        "following the links a row really has, so a link that exists in neither form is a schema "
        "question rather than something to work around here."
    )
    raise AssertionError  # pragma: no cover - `pytest.fail` does not return


def window_instants(monday: date) -> tuple[datetime, datetime]:
    """SPEC §3.1's Friday-to-Sunday window over the week beginning `monday`, in UTC."""
    zone = ZoneInfo(INSTITUTION_ZONE)
    opens = datetime.combine(
        monday + timedelta(days=FRIDAY_AFTER_MONDAY), WINDOW_OPENS_AT, tzinfo=zone
    )
    closes = datetime.combine(
        monday + timedelta(days=SUNDAY_AFTER_MONDAY), WINDOW_CLOSES_AT, tzinfo=zone
    )
    return opens.astimezone(UTC), closes.astimezone(UTC)


def plant_one_launch(
    demo: Any,
    plant: Callable[..., Any],
    tables: Mapping[str, Any],
    term: Mapping[str, Any],
    label: str,
    *,
    students: int = STUDENTS_PER_SECTION,
) -> PlantedLaunch:
    """Plant the rows one staff launch and one roster sync would have written for `label`.

    Takes the **label** a refusal prints (`BIOL-310-U5FF`) and stores the **bare**
    §2.2 code (`U5FF`) in `section.lms_section_code`, which is the currency that
    column holds; the prefix and the course number go where they belong, on the
    course and its prefix. Planting the label into that column is a section no
    lookup can match, and it cost this suite two rounds.

    **The roster is a set of subjects, not a count of enrollments.** Each student is
    planted with the `user.lms_user_id` the mock platform would have issued for this
    placement (`roster_subject` above), because that prefix is what the seeder reads
    a roster by; twenty enrollments under invented subjects are twenty rows and no
    roster.

    Every date is derived, never chosen: the section's length and start date come
    from the prior term's own `start_letter_map` row for the code's start letter
    (SPEC §2.2), its end date from ADR 0020's inclusive convention, each window from
    the term week its course week falls in, and each enrollment from the section's
    first day — which is the E4-22 anchor rule written as rows instead of as a
    clock move.

    **Every link is written out through `link_values`, and the seeding
    walker's `chain` is not used at all.** The first version passed the term and the
    prefix as chain entries and let the walker fill the rest; the seeder then refused
    over a database that visibly held all four of its sections, because a section
    hung on anything but the seed's own prior-term row is a section its
    `(prefix, course number, term, code)` lookup cannot find. Naming every
    referencing column leaves the walker nothing to invent, and
    `describe_the_sections` reports all four keys when a refusal says otherwise.
    """
    tables = dict(tables)
    term_key, term_start, _term_end, _term_length = term_columns(tables)
    prefix_code, course_number, section_code = parse_section_code(label)
    letter = section_code[0]

    letter_row = None
    for row in map_rows_for(demo, tables, term):
        if str(row[LETTER_COLUMN]) == letter:
            letter_row = row
    if letter_row is None:
        pytest.fail(
            f"The prior term's start-letter map holds no row for {letter!r}, which is the start "
            f"letter of {label} — the seeder's own section. SPEC §2.2 derives a section's length "
            "and start date from that row, so a launch of this code could not have happened in "
            "this term at all. The map holds "
            f"{sorted(str(row[LETTER_COLUMN]) for row in map_rows_for(demo, tables, term))}."
        )
    map_table = require_table(tables, START_LETTER_MAP_TABLE)
    start_column = require_column(map_table, LETTER_START_COLUMNS)
    length_column = require_column(map_table, LETTER_LENGTH_COLUMNS)
    starts_on: date = letter_row[start_column]
    length_weeks = int(letter_row[length_column])
    first_term_week = ((starts_on - term[term_start]).days // 7) + 1

    prefix_column = require_column(require_table(tables, PREFIX_TABLE), PREFIX_CODE_COLUMNS)
    prefixes = [
        row for row in rows_of(demo, tables, PREFIX_TABLE) if str(row[prefix_column]) == prefix_code
    ]
    if len(prefixes) != 1:
        pytest.fail(
            f"This database holds {len(prefixes)} prefixes coded {prefix_code!r}, which {label} "
            "hangs "
            "under it. `scripts/seed.py` seeds the prefixes the demo institution teaches, and a "
            "seeder naming a section under a prefix the seed does not hold is the NURS "
            "`unknown_prefix` incident — `docs/MISTAKES.md` entry 48: a launch cannot invent the "
            "containment chain, so the prefix is added to the seed rather than planted here."
        )
    prefix = prefixes[0]
    prefix_table = require_table(tables, PREFIX_TABLE)
    term_table = require_table(tables, TERM_TABLE)
    course_table = require_table(tables, COURSE_TABLE)
    under_the_prefix = link_values(course_table, prefix_table, prefix)
    existing = [
        row
        for row in rows_of(demo, tables, COURSE_TABLE, **under_the_prefix)
        if str(row[COURSE_NUMBER_COLUMN]) == course_number
    ]
    course = (
        existing[0]
        if existing
        else plant(
            demo,
            COURSE_TABLE,
            None,
            **{COURSE_NUMBER_COLUMN: course_number, **under_the_prefix},
        )
    )

    section_table = require_table(tables, SECTION_TABLE)
    section = plant(
        demo,
        SECTION_TABLE,
        None,
        **{
            # The **bare** §2.2 code, which is what this column stores — every
            # seeded section in the repository holds `U1WW` or `R1FF`, never the
            # whole label, and a section planted under the label is one the
            # seeder's `Section.lms_section_code == code` can never match. The
            # course and its prefix carry the other two parts of the label, which
            # is why nothing is lost by storing only this.
            SECTION_CODE_COLUMN: section_code,
            SECTION_LENGTH_COLUMN: length_weeks,
            SECTION_START_COLUMN: starts_on,
            SECTION_END_COLUMN: starts_on + timedelta(days=length_weeks * 7 - 1),
            **link_values(section_table, course_table, course),
            **link_values(section_table, term_table, term),
        },
    )
    section_key = single_primary_key(require_table(tables, SECTION_TABLE))
    launch = PlantedLaunch(
        label=label,
        code=section_code,
        section=dict(section),
        section_id=section[section_key],
    )

    window_table = require_table(tables, SURVEY_WINDOW_TABLE)
    week_table = require_table(tables, WEEK_TABLE)
    week_link = term_link_column(tables, WEEK_TABLE)
    term_weeks = {
        int(row[WEEK_NUMBER_COLUMN]): row
        for row in rows_of(demo, tables, WEEK_TABLE, **{week_link: term[term_key]})
    }
    for course_week in range(1, length_weeks + 1):
        term_week = first_term_week + course_week - 1
        week_row = term_weeks.get(term_week)
        if week_row is None:
            pytest.fail(
                f"The prior term has no week {term_week}, which is course week {course_week} of "
                f"{label}. It has {sorted(term_weeks)}. A section whose course weeks run off the "
                "end of its term is a world no launch could have produced, so this is the seeded "
                "calendar disagreeing with its own start-letter map rather than a planting choice."
            )
        launch.course_weeks[course_week] = dict(week_row)
        monday = term[term_start] + timedelta(days=7 * (term_week - 1))
        opens_at, closes_at = window_instants(monday)
        launch.windows[course_week] = dict(
            plant(
                demo,
                SURVEY_WINDOW_TABLE,
                None,
                # The term goes in first and the week last, deliberately. E2-05
                # constrains a window's `(week_id, term_id)` into `week`, so the
                # week row carries the term the database will check this window
                # against; if the two ever disagreed, the constrained value is the
                # one that has to win.
                **{
                    WINDOW_OPENS_COLUMN: opens_at,
                    WINDOW_CLOSES_COLUMN: closes_at,
                    **link_values(window_table, term_table, term),
                    **link_values(window_table, section_table, section),
                    **link_values(window_table, week_table, week_row),
                },
            )
        )

    enrollment = require_table(tables, ENROLLMENT_TABLE)
    user_table = require_table(tables, USER_TABLE)
    for student_number in range(1, students + 1):
        student = plant(
            demo,
            USER_TABLE,
            None,
            **{USER_SUBJECT_COLUMN: roster_subject(label, student_number)},
        )
        plant(
            demo,
            ENROLLMENT_TABLE,
            None,
            **{
                STARTED_ON_COLUMN: starts_on,
                ENDED_ON_COLUMN: None,
                **link_values(enrollment, user_table, student),
                **link_values(enrollment, section_table, section),
            },
        )
        launch.students.append(dict(student))
    return launch


def describe_the_sections(
    demo: Any, tables: Mapping[str, Any], labels: Sequence[str], term: Mapping[str, Any]
) -> str:
    """Every section carrying one of `labels`' codes, by the keys the seeder looks one up on.

    The seeder resolves a section by prefix code, course number, term and the bare
    §2.2 code. When it says a section is missing and the section is visibly there,
    one of those four does not match — and a builder that only reports "it refused"
    leaves the next reader to guess which. This prints all four, beside the two
    counts that say whether the launch's other rows landed.

    Takes labels, because a refusal prints labels; looks up codes, because the
    column stores codes. The line says both, so a reader can see the conversion
    that was made rather than assume it.
    """
    tables = dict(tables)
    term_key, _start, _end, _length = term_columns(tables)
    section_table = require_table(tables, SECTION_TABLE)
    course_table = require_table(tables, COURSE_TABLE)
    prefix_table = require_table(tables, PREFIX_TABLE)
    prefix_column = require_column(prefix_table, PREFIX_CODE_COLUMNS)
    course_link = primary_key_link(section_table, COURSE_TABLE)
    prefix_link = primary_key_link(course_table, PREFIX_TABLE)
    section_in_term = primary_key_link(section_table, TERM_TABLE)
    window_link = primary_key_link(require_table(tables, SURVEY_WINDOW_TABLE), SECTION_TABLE)
    enrollment_link = primary_key_link(require_table(tables, ENROLLMENT_TABLE), SECTION_TABLE)
    section_key = single_primary_key(section_table)
    course_key = single_primary_key(course_table)
    prefix_key = single_primary_key(prefix_table)

    lines: list[str] = []
    for label in sorted(labels):
        code = bare_code(label)
        found = rows_of(demo, tables, SECTION_TABLE, **{SECTION_CODE_COLUMN: code})
        if not found:
            lines.append(
                f"  {label}: no `section` row carries the code {code!r} at all "
                f"(the column stores the bare §2.2 code, never the whole label)."
            )
            continue
        for row in found:
            parts = [f"  {label} (code {code!r}):"]
            if course_link is not None:
                courses = rows_of(demo, tables, COURSE_TABLE, **{course_key: row[course_link]})
                course = courses[0] if courses else None
                number = course[COURSE_NUMBER_COLUMN] if course else "?"
                prefix_code = "?"
                if course is not None and prefix_link is not None:
                    prefixes = rows_of(
                        demo, tables, PREFIX_TABLE, **{prefix_key: course[prefix_link]}
                    )
                    prefix_code = str(prefixes[0][prefix_column]) if prefixes else "?"
                parts.append(f"prefix {prefix_code}, course number {number!r},")
            if section_in_term is not None:
                its_term = row[section_in_term]
                same = "the prior term" if its_term == term[term_key] else "ANOTHER TERM"
                parts.append(f"term {its_term} ({same}),")
            if window_link is not None:
                windows = rows_of(
                    demo, tables, SURVEY_WINDOW_TABLE, **{window_link: row[section_key]}
                )
                parts.append(f"{len(windows)} windows,")
            if enrollment_link is not None:
                enrollments = rows_of(
                    demo, tables, ENROLLMENT_TABLE, **{enrollment_link: row[section_key]}
                )
                parts.append(f"{len(enrollments)} enrollments,")
            parts.append(f"id {row[section_key]}")
            lines.append(" ".join(parts))
    return "\n".join(lines) if lines else "  (nothing planted yet)"


def safely_describe_the_sections(
    demo: Any, tables: Mapping[str, Any], codes: Sequence[str], term: Mapping[str, Any]
) -> str:
    """`describe_the_sections`, but never able to replace the failure it is explaining.

    It runs inside the builder's own `except`-guarded block, so a raise here would
    swallow the seeder's refusal — the one piece of evidence the reader needs — and
    report a defect in the description instead. `docs/MISTAKES.md` entry 26: a
    fallback path that hides the thing that triggered it.
    """
    try:
        return describe_the_sections(demo, tables, codes, term)
    except Exception as broke:
        return f"  (this builder could not describe its own sections: {broke!r})"


def plant_a_launched_prior_term_world(
    demo: Any,
    plant: Callable[..., Any],
    tables: Mapping[str, Any],
    seeded: Any,
    *,
    students: int = STUDENTS_PER_SECTION,
) -> LaunchedWorld:
    """Build, out of the seeder's own refusals, the world its launches would have left.

    **The world is discovered, not written down here.** The seeder is run; whatever
    sections it says are missing are planted; it is run again. No test has to know
    which codes E5-12 chose, how many there are, or whether a refusal lists one or
    all of them — which keeps this independent of the thing under test in the one
    way that matters, since the codes are the world's key rather than any value
    being asserted.

    The loop ends when the seeder exits zero, which means its write path ran to
    completion: that run is the caller's "first run". A run that refuses while
    naming nothing new is the interesting failure — the world is short of something
    other than a section — and the whole output is handed back in `problem` rather
    than summarised, because that sentence is the next reader's only clue.

    Returns rather than raises; see `LaunchedWorld.problem`.
    """
    world = LaunchedWorld(demo=demo)
    try:
        require_the_benchmark_history_seeder()
        world.term = prior_term(demo, tables, seeded)
        for _round in range(PLANTING_ROUNDS):
            run = run_the_benchmark_seeder(demo, **{ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})
            world.runs.append(run)
            if run.returncode == 0:
                return world
            # Labels, which is the currency a refusal prints and the currency
            # `world.launches` is keyed by; the bare codes live on the planted rows.
            named = section_codes_in(run.output)
            unplanted = [label for label in named if label not in world.launches]
            if not unplanted:
                described = safely_describe_the_sections(
                    demo, tables, sorted(world.launches), world.term or {}
                )
                world.problem = (
                    "The benchmark-history seeder refused over a world holding every section it "
                    f"has named so far ({sorted(world.launches)}), and named no new one, so this "
                    "builder has nothing left to plant and the write path was never reached.\n"
                    f"{run.report()}\n"
                    "The sections this builder planted, described by the four things the seeder "
                    "looks one up on — prefix code, course number, term, section code — and the "
                    "two counts that say whether the rest of the launch landed:\n"
                    f"{described}\n"
                    "If all four match and the seeder still cannot see them, the mismatch is in "
                    "something this builder does not plant — a question set, a lead-faculty "
                    "mapping, a platform registration — and `plant_one_launch` in "
                    "tests/fixtures/benchmark_history.py is where it is added. If one of them does "
                    "not match, that line says which, and it is a defect in this builder. Neither "
                    "is a defect in the seeder."
                )
                return world
            for label in unplanted:
                world.launches[label] = plant_one_launch(
                    demo, plant, tables, world.term, label, students=students
                )
        world.problem = (
            f"The seeder named a section this builder had not planted in each of "
            f"{PLANTING_ROUNDS} rounds, so the world never settled. Planted: "
            f"{sorted(world.launches)}.\n{world.runs[-1].report()}"
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as broke:
        # **`BaseException`, and that is the point.** `pytest.fail` raises `Failed`,
        # which derives from `BaseException` rather than from `Exception`, so the
        # `except Exception` this used to carry did not see the guards inside
        # `plant_one_launch` at all: the first schema assumption that turned out
        # wrong came back as two ERRORs at setup and read as a broken suite rather
        # than as a builder with a wrong idea in it — `docs/MISTAKES.md` entry 44,
        # met from the one direction a returning builder still had open. The two
        # exceptions that mean "stop the run" are re-raised above.
        world.problem = (
            f"{broke}\n\n"
            f"(Raised while planting the launched prior-term world: {broke!r}. That is a defect in "
            "this builder, or a schema it no longer matches — not a failed criterion. The tests "
            "that ask for this world report it here so the red is a failure naming it rather than "
            "an error in somebody's setup.)"
        )
    return world


def response_rows(demo: Any, tables: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every `response` row, whole, sorted by primary key so two runs compare row by row."""
    key = single_primary_key(require_table(dict(tables), RESPONSE_TABLE))
    return sorted(rows_of(demo, tables, RESPONSE_TABLE), key=lambda row: str(row[key]))


def response_keys(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, str, str]]:
    """The natural key of each response — `(user, section, week)` — as comparable text."""
    return [
        (
            str(row[RESPONSE_USER_COLUMN]),
            str(row[RESPONSE_SECTION_COLUMN]),
            str(row[RESPONSE_WEEK_COLUMN]),
        )
        for row in rows
    ]


def plant_a_stranger(
    demo: Any,
    plant: Callable[..., Any],
    tables: Mapping[str, Any],
    launch: PlantedLaunch,
    subject: str,
) -> dict[str, Any]:
    """One student the seeder does not govern, enrolled in a section it does.

    **A transfer student, in the world's own terms**: a `user` whose subject is not
    the mock platform's generated roster pattern for this placement, enrolled from
    the section's first day. The seeder reads its roster by that prefix, so this
    person is outside every plan it makes while being an ordinary member of the
    section — which is the only way to put a row in front of it that its plan cannot
    account for.
    """
    tables = dict(tables)
    if subject.startswith(roster_subject_prefix(launch.label)):
        pytest.fail(
            f"{subject!r} begins with {roster_subject_prefix(launch.label)!r}, which is the prefix "
            f"the seeder reads {launch.label}'s roster by — so this person is on the roster and "
            "anything written for them is a row the seeder's own plan describes. A stranger has to "
            "be outside that prefix or the test built on them proves nothing."
        )
    student = plant(demo, USER_TABLE, None, **{USER_SUBJECT_COLUMN: subject})
    enrollment = require_table(tables, ENROLLMENT_TABLE)
    plant(
        demo,
        ENROLLMENT_TABLE,
        None,
        **{
            STARTED_ON_COLUMN: launch.section[SECTION_START_COLUMN],
            ENDED_ON_COLUMN: None,
            **link_values(enrollment, require_table(tables, USER_TABLE), student),
            **link_values(enrollment, require_table(tables, SECTION_TABLE), launch.section),
        },
    )
    return dict(student)
