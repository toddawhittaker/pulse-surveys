"""What the benchmark-history seeder does when it can actually write — ticket E5-12.

Every other test of this seeder stops at a refusal, which is where the risk of a
*seeder* usually is and is not where all of it is: the mutation battery found three
survivors, all of them mutations to code that no test ever executed, because no
world in the suite was complete enough for the write path to run. This module is
that world.

**What is planted, and by whom.** `plant_a_launched_prior_term_world` writes the
rows the anchored staff launches (one per prior-term section the seeder names, five
since E5-14's exit-demo fix) and a roster sync would have left — the sections
the seeder itself names, under the courses their codes name, in the term
`scripts/seed.py` seeded, with a window for every course week and a roster enrolled
from the section's first day — and **not one `response` or `answer`**. The seeder's
own work is all still to do. The test standing in for the platform here is not the
seeder provisioning its own world: `docs/MISTAKES.md` entry 48's rule is about the
*tool* inventing rows a launch would have written, and the two refusal modules next
door are what hold the seeder to it.

**The world is built out of the seeder's own refusals**, not out of a list of codes
written here. The seeder is run, whatever it says is missing is planted, and it is
run again, until it exits zero. So this module never names a section, never counts
them, and does not care whether a refusal lists one missing section or all of them.
What it does care about is that the run at the end of that loop exited zero, which
is the only evidence in this suite that the write path ran at all.

**The E4-20 ruling still holds** and is why nothing below asserts a number the
generator chose. Not how many students answered, not the ratings, not the workload.
What is asserted is structure: one row per `(student, section, week)`, more weeks
than pairs, the same rows after a second run, and a row the seeder's plan cannot
account for refused rather than walked past. Every one of those is true of any
generator.

**Two rows that look alike and are not.** A response whose whole key is in the
seeder's deterministic plan is its own row, whoever wrote it, and a second run
adopting it is the idempotency criterion 3 asks for — that is the second test here.
A response by somebody the plan never mentions, in a week the seeder filled, is the
row entry 31 is about — that is the third. Getting those two the wrong way round is
how the third test came to demand a refusal for the one case that must not refuse.

**Cost, stated rather than discovered.** Each of these worlds is a migrated
database, a `scripts/seed.py` run, a few hundred planted rows and two or three runs
of the seeder writing a term's worth of responses. The two idempotency tests share
one world, module-scoped; the foreign-response test takes a database of its own
because it deletes rows, and a world that changed under the test beside it would
make the pair order-dependent under `-n 4`.

**Guards are in the test bodies** (`docs/MISTAKES.md` entry 44). The builder never
raises: it hands back a world carrying `problem`, and `require_the_world` is the
first statement of every test.
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.benchmark_history import (
    ANSWER_TABLE,
    DEVELOPMENT_ENVIRONMENT,
    ENVIRONMENT_VARIABLE,
    RESPONSE_TABLE,
    TRACEBACK_MARKER,
    USER_TABLE,
    LaunchedWorld,
    launch_of_section,
    plant_a_launched_prior_term_world,
    plant_a_stranger,
    require_the_world,
    response_keys,
    response_rows,
    row_counts,
    rows_of,
    run_the_benchmark_seeder,
)
from fixtures.grading import (
    RESPONSE_SECTION_COLUMN,
    RESPONSE_USER_COLUMN,
    RESPONSE_WEEK_COLUMN,
)
from fixtures.supervision import require_table, single_primary_key

pytestmark = pytest.mark.integration

# Columns left out of the row-by-row comparison between two runs. **One name, and
# it is the only one this module is willing to excuse**: a housekeeping stamp an
# ORM moves on any `UPDATE`, including one that wrote the same values back. Every
# other column is compared, `created_at` most of all — a seeder that deleted its
# rows and wrote equivalent ones would pass a comparison by value and fails this
# one, which is the shape `docs/MISTAKES.md` entry 31's E4-04 instance is about.
HOUSEKEEPING_COLUMNS = ("updated_at",)

# The subject of the one person in this world the seeder does not govern. **It has
# to fall outside the roster prefix** — `mock-lms-user-<label>-student-` — because
# that prefix is what the seeder reads a roster by, and a person inside it is
# somebody every plan of its own already describes. `plant_a_stranger` refuses a
# subject that begins with the prefix rather than trusting this constant to stay
# outside it. The spelling says what the row is for, which is what an operator
# meeting it in a database would need.
STRANGER_SUBJECT = "transfer-student-enrolled-by-hand-not-on-the-mock-roster"

# How far the stranger's submission is moved from the one the seeder wrote in the
# same week. A minute earlier, and the direction matters less than that it differs:
# nothing about this row should be mistakable for a copy of a planned one. It also
# carries no `answer` rows at all.
FOREIGN_SUBMISSION_SHIFT = timedelta(minutes=1)
SUBMITTED_AT_COLUMN = "submitted_at"


@pytest.fixture(scope="module")
def launched_world(
    demo_databases: Any, plant_in: Any, metadata_tables: dict[str, Any]
) -> LaunchedWorld:
    """One database, seeded, planted as the prior-term launches would have left it, and written.

    Module-scoped because building it is the expensive part and the two tests that
    read it only read. It **asserts nothing**, for `docs/MISTAKES.md` entry 44's
    reason: a `pytest.fail` here is an error in setup that proves nothing about
    either criterion, so a build that could not finish comes back as a world
    carrying `problem` and each test fails on that sentence instead.
    """
    demo = demo_databases()
    seeded = demo.run()
    if not seeded.succeeded:
        return LaunchedWorld(
            demo=demo,
            problem=(
                "`scripts/seed.py` failed against a fresh migrated database, so the world these "
                f"tests are stated over never existed.\n{seeded.report()}\nE0-17 owns whether that "
                "run succeeds and its module is where a failure here should be read."
            ),
        )
    return plant_a_launched_prior_term_world(demo, plant_in, metadata_tables, seeded)


def comparable(row: dict[str, Any]) -> dict[str, Any]:
    """One row with the housekeeping stamps dropped, for comparing two runs."""
    return {name: value for name, value in row.items() if name not in HOUSEKEEPING_COLUMNS}


def test_the_seeder_writes_a_separate_response_for_each_week_a_student_answered(
    launched_world: LaunchedWorld, metadata_tables: dict[str, Any]
) -> None:
    """The week is part of the key a repeat write is matched on, and this is where that shows.

    **The mutation this kills**: the week dropped from the predicate the seeder
    matches an existing response on — `Response.week_id == ...` deleted from the
    lookup. Nothing refuses that build. It writes a student's week-1 response,
    then finds "their" row again in week 2 and **updates** it, so a term of weekly
    rows collapses into one row per student per section, carrying the last week's
    answers. Every refusal test in this suite is green against it; the recount would
    report a respondent count that still looks plausible; and the benchmark it
    produces is a term-long cohort whose every week holds the same handful of
    responses.

    **The assertion that catches it is a count of keys, not of rows generated.**
    There are more `(student, section, week)` keys than there are
    `(student, section)` pairs — which is true of any generator that writes more
    than one week, and says nothing about how many students answered or what they
    said (the E4-20 ruling).

    **Two controls in front of it**, and neither is ceremony. Responses exist at all:
    without that, every count below is zero and the comparison of two zeros is a
    pass. And responses exist in at least two distinct weeks: if the planted world
    somehow carried one windowed week, then one row per pair would be *correct* and
    this test would be red against a correct seeder — so the control names that
    case as a defect in the world rather than in the code.

    The uniqueness of the key is asserted too, though E2-05's
    `uq_response_user_id_section_id_week_id` already refuses a duplicate: what it
    documents here is which key the rest of this test is counting.
    """
    world = require_the_world(launched_world)

    rows = response_rows(world.demo, metadata_tables)
    assert rows, (
        "The seeder exited zero over the launched world and wrote no `response` row at all, so "
        "every count in this test is a count of nothing. Either the write path did nothing, or the "
        "world this module planted is not one it recognises as ready.\n"
        f"{world.writing_run.report() if world.writing_run else 'no run was made'}"
    )

    keys = response_keys(rows)
    weeks = {week for _user, _section, week in keys}
    assert len(weeks) > 1, (
        f"Every response in this world is in one week ({weeks}). This test compares keys against "
        "pairs, and with a single week the two are equal for a correct seeder as well as for a "
        "broken one. That is a defect in the planted world — `plant_one_launch` writes a "
        "`survey_window` for every course week of every section — rather than in the seeder."
    )

    assert len(keys) == len(set(keys)), (
        f"{len(keys) - len(set(keys))} responses share a `(student, section, week)` key. E2-05's "
        "`uq_response_user_id_section_id_week_id` should have refused that, so this is the schema "
        "and the seeder disagreeing about what a week's response is."
    )

    pairs = {(user, section) for user, section, _week in keys}
    assert len(keys) > len(pairs), (
        f"The seeder wrote {len(keys)} responses across {len(pairs)} (student, section) pairs and "
        f"{len(weeks)} distinct weeks — so no student holds a response in more than one week of a "
        "section they are enrolled in. That is what a repeat-write lookup that has lost its week "
        "predicate produces: the second week's write finds the first week's row and updates it, "
        "and a term of weekly rows becomes one row per student. SPEC §3.1 gives a student one "
        "response per section per week, over every week the section runs."
    )


def test_a_second_run_of_the_seeder_changes_no_row_it_wrote(
    launched_world: LaunchedWorld, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 3's run-twice proof, finally made on the write path.

    Until now "running it twice is safe" was asserted only where the second run
    refused — which is `docs/MISTAKES.md` entry 31's own complaint in a new coat: a
    claim about a second run's interaction with rows that are already there, tested
    where there are none. Here the first run wrote a term of responses and the
    second meets them.

    **The mutations this kills.**

      - *The repeat-write lookup dropped altogether*, so the second run inserts
        again: refused by E2-05's unique key, which surfaces here as a non-zero exit
        with a traceback rather than as a clean re-run.
      - *Rows deleted and rewritten* on the second run — equivalent content, new
        identity. Caught because the comparison is row by row including
        `created_at`, not a count and not a set of values.
      - *A value that drifts on a re-run* — a regenerated rating, a re-picked
        respondent — which would mean the generator is not seeded from the section
        and the week after all, and that every demo drive produces a different
        world. Caught by comparing every column but the housekeeping stamp.

    **What is deliberately not asserted**: any of the numbers. This compares the
    second run's rows with the first run's, so a generator that changed entirely
    between two *tickets* is not this test's business (the E4-20 ruling), while a
    generator that changes between two *runs* is.
    """
    world = require_the_world(launched_world)

    before = response_rows(world.demo, metadata_tables)
    answers_before = row_counts(world.demo, metadata_tables).get(ANSWER_TABLE)
    assert before, (
        "The first run wrote no `response` row, so the second run has nothing to meet and this "
        "test would compare two empty lists — `docs/MISTAKES.md` entry 31's defect exactly, which "
        "is the one this test exists to close.\n"
        f"{world.writing_run.report() if world.writing_run else 'no run was made'}"
    )

    again = run_the_benchmark_seeder(world.demo, **{ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})

    assert TRACEBACK_MARKER not in again.output, (
        f"The second run printed a traceback.\n{again.report()}\nA seeder that re-inserts rather "
        "than matching meets `uq_response_user_id_section_id_week_id` here, which is what this "
        "looks like. Criterion 3 asks for a second run that is *safe*, and an operator re-running "
        "the drive after a hiccup is the ordinary case rather than the exotic one."
    )
    assert again.returncode == 0, (
        f"The second run exited {again.returncode} over the world its own first run wrote.\n"
        f"{again.report()}"
    )

    after = response_rows(world.demo, metadata_tables)
    answers_after = row_counts(world.demo, metadata_tables).get(ANSWER_TABLE)

    assert [comparable(row) for row in after] == [comparable(row) for row in before], (
        f"The second run changed the rows the first one wrote: {len(before)} responses before, "
        f"{len(after)} after, and they do not compare equal row by row. The comparison is sorted "
        "by primary key and keeps `created_at`, so a run that deleted its rows and wrote "
        "equivalent ones fails here and would pass a comparison of counts or of values — that is "
        "`docs/MISTAKES.md` entry 31's E4-04 instance, where only row identity could see the "
        f"defect. Housekeeping columns excused: {list(HOUSEKEEPING_COLUMNS)}."
    )
    assert answers_after == answers_before, (
        f"The `{ANSWER_TABLE}` table held {answers_before} rows before the second run and "
        f"{answers_after} after. The responses compared equal, so this is answers being added "
        "beside rows that were matched rather than written — the half of a re-run that a "
        "response-only comparison cannot see."
    )


def test_the_seeder_refuses_a_response_its_plan_cannot_account_for(
    demo_databases: Any, plant_in: Any, metadata_tables: dict[str, Any]
) -> None:
    """`docs/MISTAKES.md` entry 31, at the row this seeder's plan does **not** describe.

    **What "foreign" means here, which is the nuance worth stating.** This seeder's
    writes are deterministic: for each section it plans, per week, which of the
    roster's students answered. So a response whose whole natural key —
    `(student, section, week)` — is in that plan **is its own row by definition**,
    whoever put it there, and adopting it is not a defect but the idempotency
    criterion 3 asks for; the second-run test above is what pins that. The row entry
    31 is about is the other one: a `(student, week)` pair inside a section it wrote
    that its plan cannot account for at all.

    The first draft of this test got that backwards. It learned a key the seeder had
    actually written and planted a copy there, which is precisely the row the seeder
    is entitled to normalise — so it demanded a refusal for the one case that must
    *not* refuse, and it was the test's world that was wrong rather than the guard.

    **The stranger.** A transfer student: a `user` whose subject is not the mock
    platform's generated roster pattern for the placement, enrolled in the section
    from its first day, with one response in a week the seeder wrote. Nothing in any
    plan describes that pair, the section is one the seeder fills, and the row
    belongs to somebody. That is the world the refusal exists for, and on a real
    database it is a real student's submitted response.

    **The mutations this kills.**

      - *The foreign-row check deleted.* The run writes its own plan, walks past the
        stranger's row and exits zero, leaving a benchmark week carrying a response
        nobody's plan accounts for and nobody was told about. Caught by the status.
        This is the survivor the battery found — the refusal existed and nothing
        ever reached it.
      - *The check narrowed to the plan's own students*, so a response by anybody
        outside the roster is invisible. Caught by the same assertion, and it is why
        the stranger is outside the roster prefix rather than inside it.
      - *The refusal made anonymous.* Caught by the naming assertion: an operator
        meeting this has one row in the way somewhere in a term of them, and the
        section is the least they need to be told.
      - *The collision cleared* — the stranger's row deleted or rewritten so the run
        can proceed. Caught by reading it back whole; the work order states the same
        rule from the connection's side, that this seeder holds no `DELETE` on
        `response`.

    **What is deliberately not asserted**: that the run wrote nothing at all.
    Whether the seeder scans every section before writing any, or refuses when it
    reaches the section that carries the stranger, is a design question E5-12 does
    not settle, and a test that pinned it would be choosing.

    **A database of its own**, because this test adds a person and a row to the
    world. The two tests above read a world they share, and a fixture that changed
    under them would make all three order-dependent.
    """
    demo = demo_databases()
    seeded = demo.run()
    assert (
        seeded.succeeded
    ), f"`scripts/seed.py` failed against a fresh migrated database.\n{seeded.report()}"
    world = require_the_world(
        plant_a_launched_prior_term_world(demo, plant_in, metadata_tables, seeded)
    )

    written = response_rows(demo, metadata_tables)
    assert written, (
        "The seeder wrote no response over the launched world, so there is no week of a section it "
        "fills for the stranger to answer in, and this test could not fail.\n"
        f"{world.writing_run.report() if world.writing_run else 'no run was made'}"
    )
    # One row the seeder wrote, used only for **where** — the section and the week.
    # Its student is not reused: that person is on the roster, and a response of
    # theirs in that week is a row the seeder's own plan describes.
    beside = written[0]
    launch = launch_of_section(world, beside[RESPONSE_SECTION_COLUMN])

    stranger = plant_a_stranger(demo, plant_in, metadata_tables, launch, STRANGER_SUBJECT)
    key = single_primary_key(require_table(metadata_tables, RESPONSE_TABLE))
    user_key = single_primary_key(require_table(metadata_tables, USER_TABLE))
    values = {
        name: value
        for name, value in beside.items()
        if name not in (key, "created_at", *HOUSEKEEPING_COLUMNS)
    }
    values[RESPONSE_USER_COLUMN] = stranger[user_key]
    if SUBMITTED_AT_COLUMN in values and values[SUBMITTED_AT_COLUMN] is not None:
        values[SUBMITTED_AT_COLUMN] = values[SUBMITTED_AT_COLUMN] - FOREIGN_SUBMISSION_SHIFT
    plant_in(demo, RESPONSE_TABLE, None, **values)

    planted = rows_of(
        demo,
        metadata_tables,
        RESPONSE_TABLE,
        **{
            RESPONSE_USER_COLUMN: stranger[user_key],
            RESPONSE_SECTION_COLUMN: beside[RESPONSE_SECTION_COLUMN],
            RESPONSE_WEEK_COLUMN: beside[RESPONSE_WEEK_COLUMN],
        },
    )
    assert len(planted) == 1, (
        f"Planting the stranger's response left {len(planted)} rows at their key. Every assertion "
        "below compares that row against itself after the run, and a comparison that starts from "
        "nothing is satisfied by a run that deleted everything."
    )
    foreign = planted[0]

    run = run_the_benchmark_seeder(demo, **{ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})

    assert run.returncode != 0, (
        f"The seeder exited zero over a database holding a response its plan cannot account for: "
        f"{STRANGER_SUBJECT}, who is enrolled in {launch.label} and is not on the roster it reads, "
        f"answered in week {beside[RESPONSE_WEEK_COLUMN]} of that section.\n{run.report()}\n"
        "`docs/MISTAKES.md` entry 31: a loader that meets rows it did not write has to be asked "
        "what it does with them. A row whose whole key is in the plan is the seeder's own and "
        "adopting it is right — this is not that row. A zero exit here leaves a benchmark week "
        "carrying somebody's real submitted response that no plan describes, with nobody told."
    )

    assert TRACEBACK_MARKER not in run.output, (
        f"The run printed a traceback rather than a refusal.\n{run.report()}\nA collision met as "
        "an unhandled integrity error exits non-zero and satisfies the status assertion above "
        "while telling the operator nothing they can act on. Criterion 3 asks what the seeder "
        "*does* with a row it did not write; dying is not a decision."
    )

    after = rows_of(
        demo,
        metadata_tables,
        RESPONSE_TABLE,
        **{
            RESPONSE_USER_COLUMN: stranger[user_key],
            RESPONSE_SECTION_COLUMN: beside[RESPONSE_SECTION_COLUMN],
            RESPONSE_WEEK_COLUMN: beside[RESPONSE_WEEK_COLUMN],
        },
    )
    assert after == [foreign], (
        f"The stranger's response is not as this test left it. Before: {foreign}. After: {after}.\n"
        f"{run.report()}\nA row no plan of this seeder's describes is refused by name and never "
        "rewritten, never deleted: it belongs to whoever put it there, and on a real database that "
        "is a student's own submission."
    )

    assert launch.label.lower() in run.output.lower(), (
        f"The run refused without naming {launch.label}, the section whose week holds the "
        f"stranger's response.\n{run.report()}\nThe operator meeting this has one row in the way "
        "somewhere in a term of them; 'a response is in the way' sends them to read the seeder's "
        "source."
    )
