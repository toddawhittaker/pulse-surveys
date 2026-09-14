"""The two refusals `scripts/seed_benchmark_history.py` owes — ticket E5-12.

**Everything this seeder generates is out of scope here, deliberately.** E4-20's
ruling stands and E5-12 repeats it in its own out-of-scope list: the world's
numbers — how many of each roster respond, how the ratings wobble, which weeks
carry an invalid response — are demonstration material rather than a contract, and
no test asserts them. What E5-12 does put a contract around is criterion 4, the
way the script says no, and that is the whole of this module:

  - run outside a development environment, it refuses, exits non-zero, says so in
    a way that names the environment, and writes nothing;
  - run in a development environment against a world where its prior-term sections
    were never launched, it refuses, exits non-zero, names a section that is
    missing, and writes nothing. Provisioning the sections itself is the defect
    `docs/MISTAKES.md` entry 48 records — the staff launch and the roster sync are
    the platform's job, and a seeder that invents their rows makes a world that no
    launch could have produced.

**They are a pair, and the pair is what makes either one mean anything.** The two
runs are made against *the same database in the same state*; the only thing that
differs is `ENVIRONMENT`. So the second run reaching the section refusal is the
green direction of the first test's guard: a guard whose comparison is inverted,
or which refuses whatever it is given, cannot produce a run that gets as far as
reading a section. And the first run refusing on the environment rather than on
the sections is what says the guard is there at all — with no environment guard,
that run would fall through to the same section refusal the second one gets, which
is why the first test asks what the refusal *says* and not only that there was one.

**This module names no section code.** E4-20's equivalent module could name
`BIOL-310-R7FF`, because that ticket spelled it; E5-12 spells none of the codes for
its prior-term sections — it fixes the shape of the world (at least three sections
of one length and level, plus one thin cohort in another pair) and leaves the codes
to the build. So the refusal is read for a code *of SPEC §2.2's shape*, which the
database must then not hold. That is a weaker statement than E4-20's and it is the
strongest one available without this suite choosing the codes on the ticket's
behalf, which would make a design decision under cover of a test.

**The world both runs meet is the demo institution**, seeded by `scripts/seed.py`
through the shared `seeded_demo` fixture, and not an empty database. That is the
world criterion 4 describes — an operator who ran `make seed` and has not yet done
the staff launches the runbook asks for — and over a database holding nothing at
all "name what is missing" has several honest answers.

**Guards are in the test bodies, never in a fixture** (`docs/MISTAKES.md` entry
44). While `scripts/seed_benchmark_history.py` does not exist, each test below
fails on a plain sentence saying so, named for the criterion it was going to check
— a FAILED rather than an ERROR at setup.
"""

from typing import Any

import pytest
from fixtures.benchmark_history import (
    CODE_BEARING_SAMPLES,
    CODE_FREE_SAMPLES,
    DEPLOYED_ENVIRONMENT_VALUE,
    DEVELOPMENT_ENVIRONMENT,
    ENVIRONMENT_VARIABLE,
    SECTION_CODE_COLUMN,
    SECTION_TABLE,
    TRACEBACK_MARKER,
    WRITABLE_TABLES,
    changed_counts,
    prior_term,
    reads_as_the_environment_refusal,
    require_the_benchmark_history_seeder,
    require_the_writable_tables,
    row_counts,
    run_the_benchmark_seeder,
    section_codes_in,
    sections_coded,
)
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def require_a_world_holding_sections(demo: Any, tables: dict[str, Any]) -> int:
    """Stop unless the database holds sections at all, and say how many it holds.

    The control that keeps "the section the seeder named is not in this database"
    from being a statement about a query that answers nothing. `scripts/seed.py`
    seeds sample sections, so a count of zero here means the seed did not run or
    the column moved, and either of those makes the refusal test's non-vacuity
    check green for a reason unrelated to what it asserts (`docs/MISTAKES.md`
    entry 3).
    """
    section = tables.get(SECTION_TABLE)
    if section is None or SECTION_CODE_COLUMN not in getattr(section, "c", {}):
        pytest.fail(
            f"There is no `{SECTION_TABLE}.{SECTION_CODE_COLUMN}` to read (tables: "
            f"{sorted(tables)}). E0-05 creates that table and names that column."
        )
    with demo.connect() as connection:
        held = connection.execute(select(func.count()).select_from(section)).scalar_one()
    if not held:
        pytest.fail(
            "This database holds no `section` rows at all, so 'the section the seeder named is not "
            "here' would be true of every string in the world. `scripts/seed.py` seeds the demo "
            "institution's sample sections (E0-17), and this module's world is one run of it — so "
            "an empty table means the seed did not run rather than that the seeder was right."
        )
    return int(held)


def test_the_section_code_reader_finds_a_printed_code_and_is_not_fooled_by_prose() -> None:
    """The control, run before this module's reading of any refusal counts as evidence.

    Three sentences that must yield a code and three that must not. The pairs matter
    more than either list: the environment refusal and the section refusal are both
    sentences a refusing seeder prints, and a reader that could not tell them apart
    would report the environment refusal as "a section was named" and make the
    second test below green against a script that never looked for a section at all.

    `docs/MISTAKES.md` entry 3 in its pattern-searching form: run the pattern
    against the text you claim it catches *and* against the text you claim it
    allows, and build both samples by copying whole lines.
    """
    for case, sample in sorted(CODE_BEARING_SAMPLES.items()):
        assert section_codes_in(sample), (
            f"The section-code reader found nothing in {case}:\n{sample}\nA reader that has gone "
            "blind looks exactly like a seeder that refuses without naming what is missing, and "
            "the two tests below would then be asserting nothing."
        )

    for case, sample in sorted(CODE_FREE_SAMPLES.items()):
        assert not section_codes_in(sample), (
            f"The section-code reader read {section_codes_in(sample)} out of {case}:\n{sample}\n"
            "The whole of the second test below rests on this reader saying no to a refusal that "
            "names no section."
        )


def test_the_benchmark_history_seeder_refuses_to_run_outside_a_development_environment(
    demo_database: Any, seeded_demo: Any, metadata_tables: dict[str, Any]
) -> None:
    """E5-12 criterion 4: a deployment environment gets a loud no and no rows.

    The criterion: "the seeder refuses outside the development environment, same
    mechanism as E4-20". The run below is the demo institution's own database, the
    demo institution's own world, and one variable changed —
    `ENVIRONMENT=production`.

    **The mutations this has to kill.**

      - *The guard deleted, or its call never reached.* Caught by the exit status
        and by what the refusal says. Deleting it alone does not make the run write
        rows — this world holds none of the prior-term sections, so the second
        guard would refuse next — which is why the assertion is on the *content* of
        the refusal and not only on its existence. This is the near miss that
        matters: without it, a script with no environment guard at all passes.
      - *The comparison inverted*, so a deployment is admitted and development
        refused. Caught here by the same content assertion, and caught from the
        other side by the section test below, which could not reach a section
        refusal at all under an inverted guard.
      - *The refusal replaced by a warning and a zero exit.* Caught by the status.
      - *The refusal made loud but late* — anything written before the guard runs.
        Caught by the row counts.

    **The traceback assertion is not tidiness, and it is the one most likely to
    fire.** `app.config`'s rules refuse a deployment carrying development's own
    values — a blank `AI_PROVIDER_BASE_URL`, a mock identity provider — so a seeder
    that builds a `Settings` *before* it judges the environment dies inside
    configuration validation here. That run exits non-zero and writes nothing and
    would satisfy every other assertion while proving the guard never ran, which is
    `docs/MISTAKES.md` entry 3 in one line. It is also exactly why the work order
    puts "the raw ENVIRONMENT refusal BEFORE any app import" first in its list of
    disciplines, and why ADR 0163 gives that shape rather than the exit story's.
    """
    require_the_benchmark_history_seeder()

    before = row_counts(demo_database, metadata_tables)
    require_the_writable_tables(before)
    run = run_the_benchmark_seeder(
        demo_database, **{ENVIRONMENT_VARIABLE: DEPLOYED_ENVIRONMENT_VALUE}
    )
    after = row_counts(demo_database, metadata_tables)

    assert run.returncode != 0, (
        "The benchmark-history seeder ran to a zero exit under "
        f"`{ENVIRONMENT_VARIABLE}={DEPLOYED_ENVIRONMENT_VALUE}`.\n{run.report()}\n"
        "E5-12 criterion 4: it refuses outside the development environment. An operator who pipes "
        "this at a deployment by accident has to be told no, in the status the shell reads."
    )

    changed = changed_counts(before, after)
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
        "development's values, so the configuration object raises before `is_development` is ever "
        "asked, and `app.db` builds one at import (ADR 0013). Non-zero and empty is then true of a "
        "script with no guard in it. Judge the raw `ENVIRONMENT` before importing anything from "
        "`app` — ADR 0163 records that shape for E4-20's seeder and E5-12's work order repeats it."
    )

    assert reads_as_the_environment_refusal(run.output), (
        f"The run refused and did not say the environment was why.\n{run.report()}\n"
        f"Name `{ENVIRONMENT_VARIABLE}`, or quote the value it found "
        f"({DEPLOYED_ENVIRONMENT_VALUE!r}). This is not a wording preference: this world holds "
        "none of the prior-term sections either, so a seeder with no environment guard reaches the "
        "*section* refusal here and exits non-zero having written nothing, exactly as a working "
        "guard does. What the refusal says is the only thing that tells the two apart."
    )


def test_the_benchmark_history_seeder_refuses_a_world_whose_prior_term_sections_were_never_launched(
    demo_database: Any, seeded_demo: Any, metadata_tables: dict[str, Any]
) -> None:
    """E5-12's reads-never-provisions rule: no launch, no sections, so no rows and a named no.

    The work order: the seeder is "modeled line-for-line on seed_demo_story.py's
    disciplines — ... reads-never-provisions (MISTAKES 48)", and enrollments reach
    Pulse "only through real staff launches + roster sync". The world here is the
    demo institution as `scripts/seed.py` leaves it, which is what an operator has
    after `make seed` and before the launches the runbook asks for.

    **This is also the green direction of the test above, and it is why the two are
    a pair.** The only difference between the two runs is `ENVIRONMENT`. Reaching a
    refusal that names a section proves the environment guard let a development
    environment *through* — a guard whose comparison is inverted, or which refuses
    whatever it is handed, cannot get here.

    **The mutations this has to kill.**

      - *The section check deleted, and the seeder provisions the sections it did
        not find.* That is `docs/MISTAKES.md` entry 48's defect class and the work
        order's whole reason for stating the rule: caught by the row counts over
        every table, which includes `section`, `enrollment`, `week` and
        `survey_window`.
      - *The check made lenient* — missing sections treated as "nothing to do" and
        a zero exit. Caught by the status. A demo drive that looks like it worked
        and produced nothing is found out on Monday's report.
      - *The refusal made anonymous* — non-zero with a sentence that does not say
        what was missing. Caught by the code assertion. The operator meeting this
        has forgotten a launch, and the refusal is the only thing that tells them
        which placement to launch.
      - *The environment guard inverted*, as above.

    **The last assertion is the one that keeps this honest.** A code the seeder
    printed has to be a code the database does not hold; otherwise a seeder that
    printed the code of a section it had itself provisioned on an earlier run would
    pass, which is entry 48 from the other direction.
    """
    require_the_benchmark_history_seeder()

    require_a_world_holding_sections(demo_database, metadata_tables)
    before = row_counts(demo_database, metadata_tables)
    require_the_writable_tables(before)
    run = run_the_benchmark_seeder(demo_database, **{ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})
    after = row_counts(demo_database, metadata_tables)

    assert run.returncode != 0, (
        "The benchmark-history seeder exited zero against a world in which none of its prior-term "
        f"sections was ever launched.\n{run.report()}\n"
        "E5-12's work order: it reads the sections, the enrollments, the weeks and the windows and "
        "refuses by name where one is missing. A zero exit here is a demo drive that looks like it "
        "worked and seeded nothing."
    )

    changed = changed_counts(before, after)
    assert not changed, (
        f"The refused run changed rows: {changed} (name: before, after).\n{run.report()}\n"
        "This seeder provisions nothing: no person, section, enrollment, week or survey window. "
        "The launch and the roster sync write those, and a seeder that writes them itself builds a "
        "world no launch could have produced — `docs/MISTAKES.md` entry 48, the recorded defect "
        "this rule exists for, and the reason E5-12 says the seed must reach Pulse's own database "
        "the way E4-20's does."
    )

    named = section_codes_in(run.output)
    assert named, (
        f"The run refused without naming a section.\n{run.report()}\n"
        "Two things rest on that name. The operator's: the refusal is the sentence that tells them "
        "which placements to launch, and 'something is missing' does not. And this suite's: the "
        f"run above is made against the same world with `{ENVIRONMENT_VARIABLE}` set to a "
        "deployment name, so a refusal naming a section is the evidence that this run got past the "
        "environment guard rather than being stopped by it. The code is read in SPEC §2.2's shape "
        "— a prefix, a course number, then `{startLetter}{ordinal}{modality}` — because E5-12 "
        "spells no codes of its own; a refusal that names its sections some other way is a finding "
        "for the pull request, not a rule this suite should relax."
    )

    # **By the bare §2.2 code, and narrowed to the prior term.** Both halves were
    # wrong at first and the check was therefore vacuous: it looked the whole label
    # up in a column that stores only the code, so the query matched nothing
    # whatever it was handed and this assertion was true of every possible world —
    # `docs/MISTAKES.md` entry 3, in a line written to prevent exactly that. The
    # narrowing is the second half: a code is per-term data, so an unnarrowed lookup
    # answers about Fall 2026's section of the same name.
    earlier = prior_term(demo_database, metadata_tables, seeded_demo)
    unlaunched = [
        label
        for label in named
        if not sections_coded(demo_database, metadata_tables, label, term=earlier)
    ]
    assert unlaunched, (
        f"Every section the refusal named is already in the prior term: {named}.\n{run.report()}\n"
        "The criterion is what the seeder does when the staff launches have *not* happened. "
        "Nothing in this module launches anything and `scripts/seed.py` seeds no section under "
        "these codes, so a row here was written by the script under test — which is the "
        "provision-nothing rule failing, and `docs/MISTAKES.md` entry 48."
    )
