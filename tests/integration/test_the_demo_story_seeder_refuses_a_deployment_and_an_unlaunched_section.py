"""The two refusals `scripts/seed_demo_story.py` owes — ticket E4-20.

**Everything this seeder generates is out of scope here, deliberately.** The owner
ruled on 2026-09-09 that the story's numbers — how many of the twenty students
respond, how many comment, how the ratings drift, which weeks carry an invalid
response — are demonstration material rather than a contract, and no test asserts
them. What the ticket does put a contract around is the two ways the script has to
say no, and that is the whole of this module:

  - run outside a development environment, it refuses, exits non-zero, says so in
    a way that names the environment, and writes nothing;
  - run in a development environment against a world where `BIOL-310-R7FF` was
    never launched, it refuses, exits non-zero, names the section that is missing,
    and writes nothing. Provisioning the section itself is the defect
    `docs/MISTAKES.md` entry 48 records — the staff launch and the roster sync are
    the platform's job, and a seeder that invents their rows makes a demo world
    that no launch could have produced.

**They are a pair, and the pair is what makes either one mean anything.** The two
runs are made against *the same database in the same state*; the only thing that
differs between them is `ENVIRONMENT`. So the second run reaching the section
refusal is the green direction of the first test's guard: a guard whose comparison
is inverted, or which refuses whatever it is given, cannot produce a run that gets
as far as reading the section. And the first run refusing on the environment rather
than on the section is what says the guard is there at all — with no environment
guard, that run would fall through to the same section refusal the second one gets,
which is why the first test asks what the refusal *says* and not only that there
was one.

**Why a process, and why its own database.** The script is a program: the ticket's
own runbook pipes it into the api container, and a test that imported it would
report a green run of nothing for a script whose work sits under `if __name__ ==
"__main__":`. It commits, too, so it gets a database created and migrated for this
module — `db_session`'s rollback cannot reach another process's connection, and
rows left in the session database are somebody else's failed non-vacuity guard
three tickets from now. That is `DemoSeed` in `tests/fixtures/seed.py`, requested
here as `demo_database` and used for the database, the environment and the
connection; only the invocation is this module's own, because that fixture's
`run` starts `scripts/seed.py` and this is a different program.

**The invocation is the ticket's, copied rather than paraphrased**
(`docs/MISTAKES.md` entry 37): `docker compose exec -T api python - <
scripts/seed_demo_story.py` pipes the file into an interpreter's standard input,
so this runs `python -` with the file's text on stdin rather than naming the path
as an argument. What that reproduces: the script's own directory is not on
`sys.path` — which is what the work order's "never imports `scripts/seed.py`"
amounts to in practice — and `__file__` is undefined, so a script that reaches for
either fails here the way it would fail in the container. What it does not
reproduce: the container's own image, its interpreter and its network. The
database is this module's, reached over the module's own `DATABASE_URL`.

**The world both runs meet is the demo institution**, seeded by `scripts/seed.py`
through the shared `seeded_demo` fixture, and not an empty database. That is the
world the criterion describes — an operator who ran `make seed` and has not yet
done the staff launch — and over a database holding nothing at all "name what is
missing" has several honest answers, only one of which is the section. Nothing
here asserts that the demo seed itself succeeded; that is E0-17's criterion and
E0-17's module. What this module asserts about the world, it reads for itself,
in the test body.

**Guards are in the test bodies, never in a fixture** (`docs/MISTAKES.md` entry
44). While `scripts/seed_demo_story.py` does not exist, each test below fails on a
plain sentence saying so, named for the criterion it was going to check — a FAILED
rather than an ERROR at setup, because an error at setup proves nothing about the
assertion the test exists to make and survives the implementation landing.
"""

import os
import subprocess
import sys
from typing import Any, NamedTuple

import pytest
from fixtures.repo import REPO_ROOT
from sqlalchemy import func, select

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Names. Each one is spelled by the ticket, by the spec, or by a schema that has
# already shipped; the ones that are this file's own choice say so.
# ---------------------------------------------------------------------------

# E4-20 item 2 spells the path, and the runbook it carries pipes exactly this file.
STORY_SEED_SCRIPT_PATH = REPO_ROOT / "scripts" / "seed_demo_story.py"

# The section E4-20 item 1 adds to the mock LMS and item 2's seeder reads. SPEC
# §2.2's shape: `BIOL` prefix, course number 310, start letter `R`, section 7,
# modality `FF`.
SECTION_CODE = "BIOL-310-R7FF"

# E0-05's column, the name every other module in this suite reads a section code
# off. Not this file's choice.
SECTION_TABLE = "section"
SECTION_CODE_COLUMN = "lms_section_code"

# The tables a story seeder's rows would land in, and the whole reason the
# "wrote nothing" assertions are not vacuous: a database whose tables this module
# never counted would compare equal to itself perfectly. E2-08 spells both names
# and `tests/fixtures/submit.py` reads them. Comment text is a column on `answer`
# rather than a table of its own, which is why there are two names here and not
# three.
WRITABLE_TABLES = ("response", "answer")

# The variable a deployment is named by, and the value these tests deploy under.
# Settled by ADR 0063 and by `app.config`'s own `is_development` predicate, which
# E4-20 names as the mechanism; `tests/integration/test_demo_seed_script.py` holds
# the same two constants for `scripts/seed.py` and says the same thing about them.
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEPLOYED_ENVIRONMENT_VALUE = "production"
DEVELOPMENT_ENVIRONMENT = "development"

# **What this file will read as the environment guard's own refusal, and what it
# deliberately will not.** The bare word "development" is not enough: a refusal
# about the missing section can perfectly reasonably say "launch it on your
# development stack first", and a matcher that accepted that would go green
# against a script with no environment guard at all — `docs/MISTAKES.md` entry 3's
# shape exactly, since the two runs below differ only in this variable. So the
# refusal has to name the variable, or quote the value it found. That is weaker
# than what `scripts/seed.py`'s own refusal is held to (it quotes the value it
# found *and* names the one it wants) and stronger than a sentence that could
# equally be about anything.
ENVIRONMENT_REFUSAL_MARKERS = (ENVIRONMENT_VARIABLE, DEPLOYED_ENVIRONMENT_VALUE)

# What an uncaught exception prints. Used to tell the guard's refusal from the
# process dying, which is a distinction the exit status cannot make.
TRACEBACK_MARKER = "Traceback (most recent call last)"

# How long one run may take before this stops waiting. **This file's choice**, and
# a bound rather than a requirement: both runs below are supposed to refuse before
# they do any work at all, so anything approaching this is a hang — most likely a
# script waiting on a connection it cannot open — and reporting that as a failed
# criterion would send the reader to the wrong place.
STORY_SEED_TIMEOUT_SECONDS = 180


class StoryRun(NamedTuple):
    """One execution of `scripts/seed_demo_story.py`, as the shell sees it.

    Both streams are kept, and every assertion below reads them together: which of
    the two a refusal is printed on is a free choice, and pinning it would be this
    module deciding something the ticket leaves open.
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
            f"`python - < {STORY_SEED_SCRIPT_PATH}` exited {self.returncode}.\n"
            f"stdout:\n{self.stdout[-2000:]}\nstderr:\n{self.stderr[-2000:]}"
        )


def require_the_story_seeder() -> None:
    """Stop with a plain sentence unless E4-20's script is there to run.

    In the test body and never in a fixture: `docs/MISTAKES.md` entry 44 is the
    record of a deliverable guard raised at setup turning a tests-first suite's
    reds into ERRORs, which prove nothing about the assertion each test exists to
    make and read to a hurried eye as a broken suite.
    """
    if not STORY_SEED_SCRIPT_PATH.is_file():
        pytest.fail(
            f"{STORY_SEED_SCRIPT_PATH} does not exist, so there was nothing to run. E4-20 item 2 "
            "is the ticket that writes it: a seeder shaped like `scripts/seed_exit_story.py`, "
            "piped into the api container, refusing outside a development environment and "
            "refusing a world in which the section was never launched. Both refusals are what "
            "this module asserts, and neither can be asked of a file that is not there."
        )


def run_the_story_seeder(demo: Any, **overrides: str | None) -> StoryRun:
    """Pipe the script into an interpreter against `demo`'s database, and report what happened.

    **Nothing here asserts anything.** The run is handed back and each test decides
    what it means, so that a refusal that came for the wrong reason produces a
    failed assertion naming the criterion rather than an error inside a helper.

    The environment is `DemoSeed`'s — every variable `tests/fixtures/seed.py`'s
    `seed_environment` lays down, which is the container's coordinates under every
    spelling this repository reads them by, over `.env.example`'s documented values
    — with `overrides` applied last. The parent's environment is inherited
    underneath, as it is for anything run from a shell, and then overwritten: the
    child reads the repository's `.env` too, so a test that cares about a value
    states it here rather than relying on absence (`docs/MISTAKES.md` entries 30
    and 40).
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
            input=STORY_SEED_SCRIPT_PATH.read_text(encoding="utf-8"),
            cwd=REPO_ROOT,
            env=child_environment,
            capture_output=True,
            text=True,
            timeout=STORY_SEED_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"`python - < {STORY_SEED_SCRIPT_PATH}` did not finish in "
            f"{STORY_SEED_TIMEOUT_SECONDS} seconds. Both runs in this module are supposed to "
            "refuse before doing any work, so this is a hang rather than a failed criterion — a "
            "script waiting on a connection it cannot open looks exactly like this."
        )
    return StoryRun(
        returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr
    )


def row_counts(demo: Any, tables: dict[str, Any]) -> dict[str, int]:
    """How many rows every declared table holds, right now."""
    with demo.connect() as connection:
        return {
            name: connection.execute(select(func.count()).select_from(table)).scalar_one()
            for name, table in tables.items()
        }


def require_the_writable_tables(counts: dict[str, int]) -> None:
    """Stop unless the tables a story seeder writes are among the ones being counted.

    Without this the "wrote nothing" assertions below are satisfied by a count that
    never looked: an empty mapping compares equal to an empty mapping, and a
    seeder that filled `response` and `answer` would pass every one of them.
    `docs/MISTAKES.md` entry 3 — assert non-vacuity first, and say why it is not
    ceremony.
    """
    absent = [name for name in WRITABLE_TABLES if name not in counts]
    if absent:
        pytest.fail(
            f"{absent} are not among the tables this module counted, so 'the run wrote nothing' "
            f"would be a statement about a query that never ran. Counted: {sorted(counts)}. Those "
            "names come from E2-08's schema and are read the same way in `tests/fixtures/"
            "submit.py`; a deliberate rename is a one-line change at the top of this file."
        )


def require_no_section_with_the_story_code(demo: Any, tables: dict[str, Any]) -> None:
    """Stop unless the world really is one in which `BIOL-310-R7FF` was never launched.

    The precondition the second criterion is stated over, read rather than assumed.
    A world that already held the section would make the refusal impossible and the
    test would report the wrong thing — and a seeder which had itself provisioned
    the section on an earlier run would make its own precondition false, which is
    the failure `docs/MISTAKES.md` entry 48 is about.
    """
    section = tables.get(SECTION_TABLE)
    if section is None or SECTION_CODE_COLUMN not in getattr(section, "c", {}):
        pytest.fail(
            f"There is no `{SECTION_TABLE}.{SECTION_CODE_COLUMN}` to read (tables: "
            f"{sorted(tables)}). E0-05 creates that table and names that column, and nothing in "
            "this module can mean anything without it."
        )
    with demo.connect() as connection:
        found = connection.execute(
            select(section.c[SECTION_CODE_COLUMN]).where(
                section.c[SECTION_CODE_COLUMN] == SECTION_CODE
            )
        ).all()
    if found:
        pytest.fail(
            f"The database already holds a section coded {SECTION_CODE}, so the world this test "
            "is stated over does not exist: the criterion is what the seeder does when the staff "
            "launch has *not* happened. Nothing in this module launches anything, and "
            "`scripts/seed.py` seeds no section by that code, so a row here was written by the "
            "script under test — which is E4-20's provision-nothing rule failing, and "
            "`docs/MISTAKES.md` entry 48."
        )


def reads_as_the_environment_refusal(text: str) -> bool:
    """Whether one run's output says it stopped over the environment it was given.

    Two markers, either of which will do: the variable a deployment is named by, or
    the value this module deployed under. See `ENVIRONMENT_REFUSAL_MARKERS` above
    for what is deliberately not in that list and why.
    """
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in ENVIRONMENT_REFUSAL_MARKERS)


def names_the_missing_section(text: str) -> bool:
    """Whether one run's output names the section it could not find."""
    return SECTION_CODE.lower() in text.lower()


def test_the_demo_story_seeder_refuses_to_run_outside_a_development_environment(
    demo_database: Any, seeded_demo: Any, metadata_tables: dict[str, Any]
) -> None:
    """E4-20's first refusal: a deployment environment gets a loud no and no rows.

    The ticket: the seeder refuses "to run unless `app.config.is_development`". The
    run below is the demo institution's own database, the demo institution's own
    world, and one variable changed — `ENVIRONMENT=production`.

    **The mutations this has to kill.**

      - *The guard deleted, or its call never reached.* Caught by the exit status
        and by what the refusal says. Deleting it alone does not make the run write
        rows — the world has no `BIOL-310-R7FF`, so the second guard would refuse
        next — which is why the assertion is on the *content* of the refusal and
        not only on its existence. This is the near miss that matters: without it,
        a script with no environment guard at all passes this test.
      - *The comparison inverted*, so a deployment is admitted and development
        refused. Caught here by the same content assertion, and caught from the
        other side by the section test below, which could not reach a section
        refusal at all under an inverted guard.
      - *The refusal replaced by a warning and a zero exit.* Caught by the status.
      - *The refusal made loud but late* — anything written before the guard runs.
        Caught by the row counts.

    **The traceback assertion is not tidiness, and it is the assertion most likely
    to be the one that fires.** `app.config`'s configuration rules refuse a
    deployment that carries development's own values — a blank `AI_PROVIDER_BASE_URL`
    and a mock identity provider are both refused outside `development` — so a
    seeder that builds a `Settings` *before* it judges the environment dies inside
    configuration validation here. That run exits non-zero and writes nothing and
    would satisfy every other assertion in this test while proving that the guard
    never ran, which is `docs/MISTAKES.md` entry 3 in one line. ADR 0063 wants the
    check first for the same reason from the other direction: "a refused run opens
    no connection at all".
    """
    require_the_story_seeder()

    before = row_counts(demo_database, metadata_tables)
    require_the_writable_tables(before)
    run = run_the_story_seeder(demo_database, **{ENVIRONMENT_VARIABLE: DEPLOYED_ENVIRONMENT_VALUE})
    after = row_counts(demo_database, metadata_tables)

    assert run.returncode != 0, (
        "The demo story seeder ran to a zero exit under "
        f"`{ENVIRONMENT_VARIABLE}={DEPLOYED_ENVIRONMENT_VALUE}`.\n{run.report()}\n"
        "E4-20 item 2: it 'refus[es] to run unless `app.config.is_development`'. An operator who "
        "pipes this at a deployment by accident has to be told no, in the status the shell reads."
    )

    changed = {name: (before[name], after[name]) for name in before if before[name] != after[name]}
    assert not changed, (
        f"The refused run changed rows: {changed} (name: before, after).\n{run.report()}\n"
        "A guard that refuses after writing has not refused. This counts every table declared on "
        f"`Base.metadata`, and {list(WRITABLE_TABLES)} are among them by the check at the top of "
        "this test."
    )

    assert TRACEBACK_MARKER not in run.output, (
        f"The run printed a traceback rather than a refusal.\n{run.report()}\n"
        "So the process died; it did not decide. A `Settings` built before the environment is "
        "judged is the way that happens: `app.config`'s own rules refuse a deployment carrying "
        "development's values — a blank `AI_PROVIDER_BASE_URL`, a mock identity provider — so the "
        "configuration object raises before `is_development` is ever asked. Non-zero and empty is "
        "then true of a script with no guard in it. Judge the environment before building "
        "anything that a deployment's configuration could refuse; ADR 0063 puts the check first "
        "for the neighbouring reason, that 'a refused run opens no connection at all'."
    )

    assert reads_as_the_environment_refusal(run.output), (
        f"The run refused and did not say the environment was why.\n{run.report()}\n"
        f"Name `{ENVIRONMENT_VARIABLE}`, or quote the value it found "
        f"({DEPLOYED_ENVIRONMENT_VALUE!r}). This is not a wording preference: this world has no "
        f"{SECTION_CODE} in it either, so a seeder with no environment guard reaches the *section* "
        "refusal here and exits non-zero having written nothing, exactly as a working guard does. "
        "What the refusal says is the only thing that tells the two apart, and a sentence that "
        "says no more than 'not a development environment' does not tell them apart either — a "
        "refusal about the missing section may reasonably mention a development stack."
    )


def test_the_demo_story_seeder_refuses_a_world_whose_section_was_never_launched(
    demo_database: Any, seeded_demo: Any, metadata_tables: dict[str, Any]
) -> None:
    """E4-20's second refusal: no launch, no section, so no rows and a named no.

    The ticket: the seeder provisions "no person, section, enrollment, week or
    window — it reads them and exits non-zero naming what is missing (the staff
    launch and roster sync are the platform's job, done first)". The world here is
    the demo institution as `scripts/seed.py` leaves it, which is what an operator
    has after `make seed` and before the one staff launch the runbook asks for.

    **This is also the green direction of the test above, and it is why the two are
    a pair.** The only difference between the two runs is `ENVIRONMENT`. Reaching a
    refusal that names the section proves the environment guard let a development
    environment *through* — a guard whose comparison is inverted, or which refuses
    whatever it is handed, cannot get here, and would fail this test on the content
    of its refusal rather than on its exit status. A test that only asserted the
    first refusal would be green against a script that refuses everything.

    **The mutations this has to kill.**

      - *The section check deleted, and the seeder provisions the section it did
        not find.* That is `docs/MISTAKES.md` entry 48's defect class and E4-20's
        whole reason for stating the rule: caught by the row counts, and caught
        again by the precondition check the next run of this test would make.
      - *The check made lenient* — a missing section treated as "nothing to do" and
        a zero exit. Caught by the status.
      - *The refusal made anonymous* — non-zero with a sentence that does not say
        what was missing. Caught by the content assertion. An operator meeting this
        has forgotten the launch, and the refusal is the only thing that will tell
        them which section to launch.
      - *The environment guard inverted*, as above.
    """
    require_the_story_seeder()

    require_no_section_with_the_story_code(demo_database, metadata_tables)
    before = row_counts(demo_database, metadata_tables)
    require_the_writable_tables(before)
    run = run_the_story_seeder(demo_database, **{ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})
    after = row_counts(demo_database, metadata_tables)

    assert run.returncode != 0, (
        f"The demo story seeder exited zero against a world holding no {SECTION_CODE}.\n"
        f"{run.report()}\n"
        "E4-20 item 2: it reads the section, the enrollment, the weeks and the windows and "
        "'exits non-zero naming what is missing'. A zero exit here is a demo drive that looks "
        "like it worked and produced nothing, and the operator finds out on Monday's report."
    )

    changed = {name: (before[name], after[name]) for name in before if before[name] != after[name]}
    assert not changed, (
        f"The refused run changed rows: {changed} (name: before, after).\n{run.report()}\n"
        "E4-20 provisions nothing: no person, section, enrollment, week or survey window. The "
        "launch and the roster sync write those, and a seeder that writes them itself builds a "
        "world no launch could have produced — `docs/MISTAKES.md` entry 48, which is the recorded "
        "defect this rule exists for."
    )

    assert names_the_missing_section(run.output), (
        f"The run refused without naming {SECTION_CODE}.\n{run.report()}\n"
        "Two things rest on that name. The operator's: the refusal is the sentence that tells "
        "them which placement to launch, and 'something is missing' does not. And this suite's: "
        f"the run above this one is made against the same world with `{ENVIRONMENT_VARIABLE}` set "
        "to a deployment name, so a refusal that names the section is the evidence that this run "
        "got past the environment guard rather than being stopped by it. If what is printed here "
        "is the environment refusal, the guard is inverted; if it names something else the world "
        "is missing, say so in the pull request — the world this ran against is `scripts/seed.py`'s "
        "demo institution, where the section is the thing a staff launch would have created."
    )
