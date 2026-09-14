"""Running the benchmark-history seeder twice, against rows it did not write — ticket E5-12.

Criterion 3 cites `docs/MISTAKES.md` entry 31 by name: "Running the seeder twice
is safe, proven against a database the loader did not fill (MISTAKES entry 31
verbatim)." That entry's rule is one sentence and this module is written to it:

    Test an idempotent loader against rows it did not write. Before a second-run
    test means anything, put a foreign row in its way — one that shares the
    natural key the loader matches on — and assert what the loader does with it.
    The interesting answer is usually "refuse", and a loader that has never been
    shown a foreign row has not been asked the question.

**Which natural key, and why this one.** This seeder writes no section; it *finds*
the sections the staff launches created, and the key it finds them by is
`section.lms_section_code` — the string the mock platform stamps and the roster
sync stores. That is precisely the shape entry 31 is about: a value the outside
world also supplies, matched globally rather than scoped to a row the loader
created. The incident behind the entry is `prefix.code`, where the seed did not
create a row but **adopted** one and rewrote what hung beneath it. The same
adoption here writes a term's worth of generated responses into a stranger's
section, under students who are not its roster, and every figure that section's
instructor reads on Monday is then partly invented.

**The foreign row is planted as a section the seeder's world does not contain**:
the same code, under a course, prefix and term of its own that the seeding walker
builds. Nothing about it belongs to the prior term the seeder is filling, which is
what makes it foreign rather than a re-run's own row.

**Which code, and why this module does not name one.** E5-12 spells none of its
prior-term section codes, so this module asks the seeder which sections it is
looking for — by reading the refusal it prints against a world where none of them
exists — and then occupies one of those codes. That is not the expectation being
checked against a copy of itself (`docs/MISTAKES.md` entry 19): the assertions
below are about what the seeder *does* with an occupied key, and the code is the
world's key rather than the value under test. Its correctness is asserted next
door, in the module that holds the two refusals.

**A fresh database of its own.** The planted section would break the neighbouring
module's precondition — a world where the seeder's sections do not exist — so this
one takes a database from `demo_databases` and runs `scripts/seed.py` into it
itself, rather than sharing `demo_database`. Under `-n 4` the two modules may run
in either order on either worker, and a shared database would make that order
decide the result.
"""

from typing import Any

import pytest
from fixtures.benchmark_history import (
    DEVELOPMENT_ENVIRONMENT,
    ENVIRONMENT_VARIABLE,
    SECTION_CODE_COLUMN,
    SECTION_TABLE,
    TRACEBACK_MARKER,
    changed_counts,
    require_the_benchmark_history_seeder,
    require_the_writable_tables,
    row_counts,
    run_the_benchmark_seeder,
    section_codes_in,
    sections_coded,
)

pytestmark = pytest.mark.integration


def test_the_benchmark_history_seeder_refuses_a_foreign_section_holding_a_code_it_looks_for(
    demo_databases: Any, plant_in: Any, metadata_tables: dict[str, Any]
) -> None:
    """E5-12 criterion 3: a key it did not create is refused, not adopted and not deleted.

    **The mutations this has to kill.**

      - *The section lookup matched on the code alone, and the row adopted.* The
        seeder finds a section carrying one of its codes, decides the world is
        ready, and writes generated responses against a section it never launched —
        rows under a foreign section, a foreign course and a foreign term. Caught by
        the exit status and by the row counts, which move on `response` and `answer`
        the moment an adoption is acted on. This is entry 31's own defect, one
        table over.
      - *The lookup scoped correctly but the refusal made silent* — a zero exit and
        nothing written, which reads to an operator as a drive that worked. Caught
        by the status.
      - *The refusal made anonymous.* Caught by the last assertion: the operator
        meeting this holds a database with a code collision in it, and the only
        thing that will let them find it is the seeder naming the code.
      - *The collision cleared rather than refused* — the foreign section deleted or
        re-pointed into the prior term so the run can proceed. Caught by reading the
        planted row back whole and requiring it unchanged. The work order states the
        same rule from the connection's side: the seeder holds no `DELETE` on
        `response`, and foreign rows are refused by name rather than removed.

    **The near miss this must not fire on.** A seeder that resolves its sections by
    `(term, code)` and therefore never sees the planted row at all is *correct*, and
    it reaches the same missing-section refusal it gave before the plant: non-zero,
    nothing written, the code named. Every assertion below is satisfied by that
    seeder, which is deliberate — the criterion is that a foreign row is not
    adopted, not that a particular lookup is written.

    **The controls, in order, and why each is not ceremony.** The demo seed must
    have succeeded, or the world is not the one the criterion is stated over. The
    first run must name a section, or there is no key to occupy and the plant would
    be a section the seeder never looks for — a test that could not fail. And the
    planted row must be readable back before the second run, or "the foreign row is
    still there, unchanged" is a comparison between two empty lists
    (`docs/MISTAKES.md` entry 3).
    """
    require_the_benchmark_history_seeder()

    demo = demo_databases()
    seeded = demo.run()
    assert seeded.succeeded, (
        "`scripts/seed.py` failed against a fresh migrated database, so this test never got as far "
        f"as its own subject.\n{seeded.report()}\nThe world criterion 3 is stated over is the demo "
        "institution after `make seed`; E0-17 owns whether that run succeeds and its module is "
        "where a failure here should be read."
    )

    first = run_the_benchmark_seeder(demo, **{ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})
    looked_for = section_codes_in(first.output)
    assert looked_for, (
        "Against a world where none of its sections was launched, the seeder named none of them, "
        f"so this test has no code to occupy.\n{first.report()}\nThat refusal is asserted in "
        "`test_the_benchmark_history_seeder_refuses_a_world_whose_prior_term_sections_were_never_"
        "launched`, and this module needs it only as the question 'which sections do you look "
        "for?'. A plant made against a code the seeder never looks for is a test that cannot fail."
    )
    absent = [code for code in looked_for if not sections_coded(demo, metadata_tables, code)]
    assert absent, (
        f"Every code the seeder named is already in this database: {looked_for}. There is nothing "
        "for this test to occupy, and a database holding those sections after nothing but "
        "`scripts/seed.py` and a refused run is `docs/MISTAKES.md` entry 48 — the seeder "
        "provisioning what a launch should have."
    )
    code = absent[0]

    plant_in(demo, SECTION_TABLE, None, **{SECTION_CODE_COLUMN: code})
    foreign = sections_coded(demo, metadata_tables, code)
    assert len(foreign) == 1, (
        f"After planting one section coded {code}, this database holds {len(foreign)} of them: "
        f"{foreign}. Every assertion below compares this row against itself after the run, and a "
        "comparison that starts from nothing is satisfied by a run that deleted everything."
    )

    before = row_counts(demo, metadata_tables)
    require_the_writable_tables(before)
    second = run_the_benchmark_seeder(demo, **{ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})
    after = row_counts(demo, metadata_tables)

    assert second.returncode != 0, (
        f"The seeder exited zero against a database holding a section coded {code} that it did not "
        f"launch.\n{second.report()}\nThat row is not part of the world this seeder fills: it "
        "hangs under a course, a prefix and a term of its own, seeded by this test. Entry 31's "
        "rule is that a loader shown a foreign row sharing its natural key must be asked what it "
        "does with it, and a zero exit says it treated a stranger's section as its own."
    )

    changed = changed_counts(before, after)
    assert not changed, (
        f"The run changed rows: {changed} (name: before, after).\n{second.report()}\n"
        "A seeder that writes generated responses against a section it never launched has adopted "
        "it — `docs/MISTAKES.md` entry 31's defect, where the loader did not create a row but "
        "re-pointed one the outside world had put there. `response` and `answer` are among the "
        "tables counted, by the check above this run."
    )

    assert sections_coded(demo, metadata_tables, code) == foreign, (
        f"The planted section coded {code} is not as this test left it. Before: {foreign}. After: "
        f"{sections_coded(demo, metadata_tables, code)}.\n{second.report()}\nA collision this "
        "seeder clears out of its way is worse than one it adopts, because the row it removed "
        "belonged to whoever put it there. The work order holds the same line from the "
        "connection's side: this seeder holds no DELETE on the rows it reads, and a foreign row is "
        "refused by name."
    )

    assert TRACEBACK_MARKER not in second.output, (
        f"The run printed a traceback rather than a refusal.\n{second.report()}\nA collision met "
        "as an unhandled `MultipleResultsFound` or an integrity error exits non-zero and writes "
        "nothing, so it satisfies every assertion above while telling the operator nothing they "
        "can act on. Criterion 3 asks what the seeder *does* with a row it did not write, and "
        "dying is not a decision."
    )

    assert code.lower() in second.output.lower(), (
        f"The run refused without naming {code}.\n{second.report()}\nThe operator meeting this has "
        "a database in which somebody else's section carries one of the demo world's codes, and "
        "the refusal is the only thing that will tell them which one. 'Something is in the way' "
        "sends them to read the seeder's source."
    )
