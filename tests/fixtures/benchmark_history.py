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
"""

import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

import pytest
from sqlalchemy import func, select

from fixtures.repo import REPO_ROOT

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
# ---------------------------------------------------------------------------

# E0-05's table and column, the pair every other module in this suite reads a
# section code off. Not this file's choice.
SECTION_TABLE = "section"
SECTION_CODE_COLUMN = "lms_section_code"


def sections_coded(demo: Any, tables: Mapping[str, Any], code: str) -> list[Mapping[str, Any]]:
    """Every `section` row carrying `code`, whole, as the database holds it now."""
    section = tables.get(SECTION_TABLE)
    if section is None or SECTION_CODE_COLUMN not in getattr(section, "c", {}):
        pytest.fail(
            f"There is no `{SECTION_TABLE}.{SECTION_CODE_COLUMN}` to read (tables: "
            f"{sorted(tables)}). E0-05 creates that table and names that column, and nothing in "
            "this suite can mean anything without it."
        )
    with demo.connect() as connection:
        rows = connection.execute(
            section.select().where(section.c[SECTION_CODE_COLUMN] == code)
        ).mappings()
        return [dict(row) for row in rows]


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
