"""The prior term is configuration, and its start-letter map is its own — ticket E5-12.

E5-12's scope: "The prior term itself as configuration: term rows, its start-letter
map, windows — derived per §2.2, hand-entered nowhere", and its second known trap
says what that rules out:

    **A prior term's map is not this term's** — §2.2's letters are per-term data;
    copying Fall 2026's map into Spring is a silent policy.

Silent is the word that matters. A map copied from Fall 2026 into an earlier term
is a table of rows that look exactly like configuration and place every section
derived from them outside the term they belong to. Nothing refuses it: the launch
resolves a section code against the map row it finds, the section's start date
lands in September, its course weeks hang on weeks that belong to another term's
calendar, and the benchmark cohort the whole ticket exists to build is a cohort of
sections that began after their term ended. The first thing that notices is a
reader wondering why a prior-term figure lines up with this term's.

**What this module reads, and what it deliberately does not.** It reads the rows
`scripts/seed.py` writes, through one run of that script into a database of its own
— the world criterion 1 is stated over, "after the full seed sequence on a fresh
dev database". It asserts nothing about the *generated* world: no section, no
enrollment, no response, no count. That is E4-20's ruling, which E5-12's
out-of-scope list repeats, and the seeder's own self-check is what owns the counts.

**Which term is the prior one is discovered, never named.** E5-12 suggests "Spring
2026" and settles nothing; a test that required that name, or those dates, would
choose the calendar on the ticket's behalf. So the prior term here is *any* term
whose own dates end before Fall 2026 begins, and Fall 2026 is found by the start
date SPEC §3.1 and `tests/fixtures/survey_windows.py` already hold.

**How these rows are reached is a composite key, not a column.** ADR 0018 gives
`week` and `start_letter_map` one foreign key into `term` and it is
`(term_id, term_length_weeks) → term (id, length_weeks)`. The first draft of this
module followed that link with a helper that answers only for *single-column*
foreign keys, so all three tests failed on the route rather than on the rows —
`docs/disputes/E5-12-01.md`, upheld, and the reason `term_link_column` below
filters on the referenced column being a primary key. Nothing any of the three
tests asserts changed in the repair.

**Guards are in the test bodies** (`docs/MISTAKES.md` entry 44): while the seed has
no second term, each test below fails on a sentence saying which criterion it was
going to check.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from fixtures.provisioning import (
    LETTER_COLUMN,
    LETTER_LENGTH_COLUMNS,
    LETTER_START_COLUMNS,
    TERM_END_COLUMNS,
    TERM_LENGTH_COLUMNS,
    TERM_START_COLUMNS,
)
from fixtures.supervision import require_column, require_table, single_primary_key
from fixtures.survey_windows import (
    FALL_2026_TERM_START,
    TERM_TABLE,
    WEEK_NUMBER_COLUMN,
    WEEK_TABLE,
)

pytestmark = pytest.mark.integration

START_LETTER_MAP_TABLE = "start_letter_map"

# SPEC §2.2's course lengths, transcribed: "Course lengths in weeks: **3, 6, 8, 10,
# 12, 15, 16** (plus an 18-week dissertation length)". **Deliberately not derived**
# from `scripts/seed.py`'s own map — the file under test — because a length read
# out of the thing being checked agrees with whatever it says
# (`docs/MISTAKES.md` entry 19). A new length is a spec change first.
SPEC_COURSE_LENGTHS = (3, 6, 8, 10, 12, 15, 16, 18)

MONDAY = 0


def term_link_column(tables: dict[str, Any], name: str) -> str:
    """The column on `name` that names a `term` row's **primary key**.

    **The primary-key half is not tidiness**, and getting it wrong is what
    `docs/disputes/E5-12-01.md` is about. ADR 0018 gives `week` and
    `start_letter_map` one *composite* key into `term` — `(term_id,
    term_length_weeks) → term (id, length_weeks)` — so both of those columns
    reference `term`. A helper that asks for a *single-column* link finds none and
    answers `None` on every database at head, which is how the first draft of this
    module failed three correct assertions for a reason that had nothing to do with
    the rows they are about; and a helper that merely counted references would find
    two links where there is one relationship. Filtering on the referenced column
    being a primary key leaves the one column this module means to follow.

    Copied in shape from `one_foreign_key_column` in
    `tests/integration/test_demo_seed_script.py`, whose own comment records this
    trap against these same two tables. A third copy rather than a shared helper is
    deliberate: `fixtures.grading.single_column_link` is pinned by other tests for
    its strictness about composite keys, and widening it to serve this module would
    move a rule those tests depend on (`docs/MISTAKES.md` entry 13's exception — two
    callers asking genuinely different questions).
    """
    table = require_table(tables, name)
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
            "exactly one such column there is no such thing as 'the prior term's map' and this "
            "module is unaskable. A fork here is a schema question rather than something to pick a "
            "side of in a test."
        )
    return found[0]


def rows_of(demo: Any, tables: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Every row of one table, whole, as the seeded database holds it."""
    table = require_table(tables, name)
    with demo.connect() as connection:
        return [dict(row) for row in connection.execute(table.select()).mappings()]


def term_columns(tables: dict[str, Any]) -> tuple[str, str, str, str]:
    """`(key, start, end, length)` on `term`, each found among the candidates E0-06 left open."""
    table = require_table(tables, TERM_TABLE)
    return (
        single_primary_key(table),
        require_column(table, TERM_START_COLUMNS),
        require_column(table, TERM_END_COLUMNS),
        require_column(table, TERM_LENGTH_COLUMNS),
    )


def fall_2026(demo: Any, tables: dict[str, Any], seeded: Any) -> dict[str, Any]:
    """The term `scripts/seed.py` seeds the demo institution's current world into.

    The control every test in this module starts from, and it is not ceremony: a
    module that could not find Fall 2026 is a module reading an empty or unseeded
    database, and "there is a term before Fall 2026" would then be a statement about
    a query that answers nothing (`docs/MISTAKES.md` entry 3).
    """
    _key, start, _end, _length = term_columns(tables)
    terms = rows_of(demo, tables, TERM_TABLE)
    current = [row for row in terms if row[start] == FALL_2026_TERM_START]
    if len(current) != 1:
        pytest.fail(
            f"This database holds {len(current)} terms starting {FALL_2026_TERM_START} — it holds "
            f"{[row[start] for row in terms]}. SPEC §3.1's seeded world is Fall 2026 and "
            "`tests/fixtures/survey_windows.py` carries that date for the whole suite, so nothing "
            "in this module can be read against it until that row is there. The seed run this "
            f"world came from:\n{seeded.report()}"
        )
    return current[0]


def prior_term(demo: Any, tables: dict[str, Any], seeded: Any) -> dict[str, Any]:
    """The term this ticket adds: any term whose dates end before Fall 2026 begins.

    Discovered rather than named, for the reason this module's docstring gives. More
    than one is not a failure — a world may hold several prior terms — but this
    suite reads the one that ends latest, which is the term a benchmark reaches back
    into first.
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
            "`scripts/seed.py` beside Fall 2026 — a term row with its own dates, its own "
            "start-letter map and its own week rows — because the exit line says 'benchmarked "
            "against prior terms' and nothing seeded today lives in one. The terms this database "
            f"holds start on {[row[start] for row in rows_of(demo, tables, TERM_TABLE)]}."
        )
    return sorted(earlier, key=lambda row: row[end])[-1]


def map_rows_for(demo: Any, tables: dict[str, Any], term: dict[str, Any]) -> list[dict[str, Any]]:
    """Every `start_letter_map` row belonging to one term."""
    link = term_link_column(tables, START_LETTER_MAP_TABLE)
    key, _start, _end, _length = term_columns(tables)
    return [row for row in rows_of(demo, tables, START_LETTER_MAP_TABLE) if row[link] == term[key]]


def test_the_seed_calendar_holds_a_term_before_fall_2026_with_week_rows_of_its_own(
    demo_database: Any, seeded_demo: Any, metadata_tables: dict[str, Any]
) -> None:
    """E5-12's scope: the prior term is seeded configuration, weeks included.

    **The mutations this kills.**

      - *The term row added and its weeks forgotten.* A response hangs on a `week`
        row, so a prior term with no weeks is a term nothing can be seeded into —
        and the failure arrives much later, inside the benchmark seeder, as a
        foreign-key error nobody can place. Caught by the week-number comparison.
      - *The weeks numbered from the wrong end, or one short.* Caught by comparing
        the whole set against the term's own declared length rather than counting
        them: a set comparison says which numbers are missing, and a count of 18
        is equally true of weeks numbered 0 to 17.
      - *The prior term seeded to overlap Fall 2026.* Caught by the discovery rule
        itself — a term that does not end before Fall begins is not found at all,
        and the failure says so. Two overlapping terms make "which term is this
        section in" ambiguous, which is the section-code resolution question E5-12's
        traps say to raise rather than code around.

    **The control** is Fall 2026, read first: a database where that row is missing
    is one where the seed did not run, and every assertion here would otherwise be
    vacuously true of an empty calendar.
    """
    _key, start, end, length = term_columns(metadata_tables)
    fall = fall_2026(demo_database, metadata_tables, seeded_demo)
    earlier = prior_term(demo_database, metadata_tables, seeded_demo)

    assert earlier[end] < fall[start], (
        f"The prior term runs {earlier[start]}-{earlier[end]} and Fall 2026 begins {fall[start]}, "
        "so the two overlap. A section code resolves against the map of the term its dates fall "
        "in; two terms covering one day make that resolution ambiguous, which E5-12's traps say "
        "is a finding to raise rather than something to build on."
    )

    week_link = term_link_column(metadata_tables, WEEK_TABLE)
    term_key = single_primary_key(require_table(metadata_tables, TERM_TABLE))
    numbered = {
        row[WEEK_NUMBER_COLUMN]
        for row in rows_of(demo_database, metadata_tables, WEEK_TABLE)
        if row[week_link] == earlier[term_key]
    }

    assert numbered == set(range(1, int(earlier[length]) + 1)), (
        f"The prior term ({earlier[start]}-{earlier[end]}, {earlier[length]} weeks) carries week "
        f"rows numbered {sorted(numbered)}. E5-12 seeds its weeks 'via week_rows_for_term()', the "
        "same mechanism Fall 2026's use, so the set should be 1 to the term's own declared length "
        "with nothing missing at either end. A response is hung on one of these rows; a week that "
        "is not there is a week the benchmark world cannot hold."
    )


def test_the_prior_terms_start_letter_map_dates_are_its_own_and_not_fall_2026s(
    demo_database: Any, seeded_demo: Any, metadata_tables: dict[str, Any]
) -> None:
    """E5-12's second known trap, pinned: a copied map is a silent policy.

    **The mutation this kills**: `START_LETTER_MAP`'s Fall 2026 rows written under
    the prior term's id — the one-line version of "the prior term needs a map", and
    the version that is invisible everywhere else. The letters resolve, the launch
    succeeds, `apply_section_code` writes a section whose start date is in
    September, and a prior-term cohort's sections carry this term's calendar. Every
    figure computed over that cohort is then an average across two terms wearing one
    term's name.

    **The near miss it must not fire on**: repeated *letters*. §2.2's map is
    per-term data and nothing says a prior term may not reuse `U`, `R` or `E` — the
    work order says so in as many words, "letters may repeat, dates may not". So
    this test compares dates and never letters.

    **The controls.** Fall 2026's own map is read first and required to be
    non-empty: a comparison against an empty set is satisfied by anything, and a
    module that found no Fall rows would report a copied map as clean
    (`docs/MISTAKES.md` entry 3). The prior term's map is required to be non-empty
    for the same reason from the other side — no rows is not "its own rows", it is
    a term no section code can resolve against.
    """
    table = require_table(metadata_tables, START_LETTER_MAP_TABLE)
    start_column = require_column(table, LETTER_START_COLUMNS)
    _key, term_start, term_end, _length = term_columns(metadata_tables)

    fall = fall_2026(demo_database, metadata_tables, seeded_demo)
    earlier = prior_term(demo_database, metadata_tables, seeded_demo)
    fall_map = map_rows_for(demo_database, metadata_tables, fall)
    prior_map = map_rows_for(demo_database, metadata_tables, earlier)

    assert fall_map, (
        "Fall 2026 carries no start-letter map rows at all, so this test's comparison would be "
        "against an empty set and a map copied wholesale would pass it. SPEC §2.2 names that seed "
        "map — '12-week U/R/Q starting 8/17, 9/7, 9/28' — and E0-17 seeds it."
    )
    assert prior_map, (
        f"The prior term ({earlier[term_start]}-{earlier[term_end]}) carries no start-letter map "
        "rows. SPEC §2.2 makes the map per-term configuration, and a term without one is a term "
        "whose section codes resolve against nothing: no length, no start date, no course weeks. "
        "E5-12's scope asks for 'its OWN start-letter map'."
    )

    outside = [
        row
        for row in prior_map
        if not (earlier[term_start] <= row[start_column] <= earlier[term_end])
    ]
    assert not outside, (
        "The prior term's start-letter map holds start dates outside its own term: "
        f"{[(row[LETTER_COLUMN], row[start_column]) for row in outside]}, against a term running "
        f"{earlier[term_start]}-{earlier[term_end]}. A section's start date derives from its "
        "letter, so a map row outside the term produces sections that began before or after the "
        "term they are recorded in."
    )

    shared = sorted(
        {row[start_column] for row in prior_map} & {row[start_column] for row in fall_map}
    )
    assert not shared, (
        f"The prior term's map and Fall 2026's share start dates: {shared}. That is the copied map "
        "E5-12's known traps name — 'copying Fall 2026's map into Spring is a silent policy'. The "
        "letters may repeat and this test does not look at them; the dates are the term's own "
        "configuration and they cannot."
    )


def test_every_prior_term_start_letter_row_derives_from_that_terms_calendar(
    demo_database: Any, seeded_demo: Any, metadata_tables: dict[str, Any]
) -> None:
    """SPEC §2.2, over the rows this ticket adds: a letter is a length and a term-week Monday.

    §2.2: "the start letter encodes length + start date within the term", and "Section
    start/end dates derive from the letter + term calendar; nothing is hand-entered
    per section". So each row of the prior term's map has to be a row the term's own
    calendar could have produced.

    **The mutations this kills.**

      - *A start date that is not a term-week Monday* — a map row typed by hand, or
        shifted by a day when the term's start moved. A section derived from it is
        off by that many days against every other cohort, and its course weeks no
        longer line up with any term week, which is the sub-label SPEC §2.2 puts on
        every course-level page.
      - *A length the institution does not run*, which is a cohort nothing else in
        the product is built for (the comparison sets in E5-01 are keyed by declared
        length).
      - *A cohort that runs off the end of its term.* Caught by the last assertion.
        ADR 0021 refuses to write a section whose dates leave its term, so such a
        letter is a launch that fails at the counter rather than a world that
        builds — which in this drive means a staff launch that cannot be done at
        all, discovered by hand.

    The arithmetic is written out here rather than read from any seeding helper: a
    test that computed the expected Monday with the same function the seed used
    would move with it and stay green (`docs/MISTAKES.md` entry 19).
    """
    table = require_table(metadata_tables, START_LETTER_MAP_TABLE)
    start_column = require_column(table, LETTER_START_COLUMNS)
    length_column = require_column(table, LETTER_LENGTH_COLUMNS)
    _key, term_start, term_end, _term_length = term_columns(metadata_tables)

    earlier = prior_term(demo_database, metadata_tables, seeded_demo)
    prior_map = map_rows_for(demo_database, metadata_tables, earlier)
    assert prior_map, (
        f"The prior term ({earlier[term_start]}-{earlier[term_end]}) carries no start-letter map "
        "rows, so there is nothing here to check against its calendar. E5-12's scope asks for its "
        "own map."
    )

    faults: list[str] = []
    for row in prior_map:
        letter = row[LETTER_COLUMN]
        starts_on: date = row[start_column]
        length = int(row[length_column])
        offset = (starts_on - earlier[term_start]).days
        if starts_on.weekday() != MONDAY:
            faults.append(f"{letter} starts {starts_on}, which is not a Monday")
        if offset % 7:
            faults.append(
                f"{letter} starts {starts_on}, {offset} days after the term began — not a whole "
                "number of weeks, so it begins inside a term week rather than on one"
            )
        if length not in SPEC_COURSE_LENGTHS:
            faults.append(
                f"{letter} runs {length} weeks, which is not one of SPEC §2.2's lengths "
                f"{list(SPEC_COURSE_LENGTHS)}"
            )
        ends_on = starts_on + timedelta(days=length * 7 - 1)
        if ends_on > earlier[term_end]:
            faults.append(
                f"{letter} runs {length} weeks from {starts_on} and so ends {ends_on}, after the "
                f"term ends on {earlier[term_end]}"
            )

    assert not faults, "\n".join(
        [
            "The prior term's start-letter map holds rows its calendar could not have produced:",
            *(f"  {fault}" for fault in faults),
            "",
            f"The term runs {earlier[term_start]}-{earlier[term_end]}. SPEC §2.2: the start letter "
            "encodes a length and a start date *within the term*, and section dates derive from "
            "the letter plus the term calendar with nothing hand-entered. ADR 0020's convention is "
            "that a length in weeks is inclusive of its last day, which is the arithmetic the last "
            "check uses.",
        ]
    )
