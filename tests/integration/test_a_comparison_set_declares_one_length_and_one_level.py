"""A named set declares one length and one level, and the database refuses the rest.

E5-01 criterion 1, in the ticket's words:

> A set with a length outside §2.2's set, or a level outside §8's five, is
> refused by the database — asserted by attempting the insert, both sides of each
> boundary.

SPEC §5.1 is why the pair exists at all: "to be comparable, sections must match on
**both** length (§2.2's length set) *and* level (§8's set: `DEV`, `UG`, `UGGR`,
`GR`, `DR`)", and the breakdown's decision 3 turns that into a stored shape — the
set declares the pair once, membership is constrained to courses of that level,
and resolution selects member courses' sections of that length. So a stored set
whose length is 17 is a benchmark nothing can ever resolve, and E5-04 would
compute a figure over an empty cohort rather than see the mistake.

**Every boundary is asserted from both sides, and the two sides are inside one
test.** Each refused length is written beside the accepted length nearest it and
each refused level beside an accepted one, both through the same helper, in the
same transaction — so a schema that refused every insert cannot satisfy the
refusals, and the control failing says exactly that rather than leaving twelve
green refusals over a table nothing can write to (`docs/MISTAKES.md` entry 3).

**The refusals are attempted through the ORM's declared table and answered by the
server.** The rule under test is the migration's, and the ticket's first known
trap says so: a model-side validator is inert here, because the test database is
built from migrations. A mutation of this module's subject is a mutation of the
`CHECK` in the revision.

**Nothing here names a constraint.** A name in this schema comes from
`Base.metadata`'s naming convention rather than being chosen, so holding one would
report a rename as a regression. What is asserted is that the server refused the
row, and beside it that the refusal was about the *data* — an integrity violation
or a value the type could not take — so a red cannot be a typo in this module
reading as a schema rule.

**Which failure a red here is, before E5-01 lands.** Every test fails on its first
statement, in `comparison_set_table`, with a message naming the missing table —
a FAILED and never an ERROR (`docs/MISTAKES.md` entry 44). The one exception is
the control at the top of the file, which names only `course` and is green today.
"""

from typing import Any

import pytest
from fixtures.comparison_sets import (
    COURSE_LEVEL_COLUMN,
    LENGTH_COLUMN,
    LENGTHS_OUTSIDE_THE_SET,
    LEVEL_COLUMN,
    LEVELS_OUTSIDE_THE_FIVE,
    NAME_COLUMN,
    NUMBER_BY_LEVEL,
    REFUSED_A_VALUE,
    SPEC_LENGTHS,
    SPEC_LEVELS,
    assert_refused_for_the_data,
    comparison_set_table,
    course_at,
    refusal_of,
    require_columns,
    write_set,
)

pytestmark = pytest.mark.integration

# The columns every test below writes. The failure message says where they come
# from, because while E5-01 is unbuilt this is the message that names the ticket.
DECLARED_COLUMNS = (LENGTH_COLUMN, LEVEL_COLUMN)

WHERE_THE_COLUMNS_COME_FROM = (
    "E5-01 gives `comparison_set` a declared length and a declared level (breakdown decision 3), "
    "the length constrained to SPEC §2.2's set and the level to §8's five."
)

# A length and a level that are certainly legal, for the tests whose subject is
# neither. `6` is SPEC §2.2's commonest section length and `UG` its commonest
# level, so a control row here is the ordinary case rather than an edge of it.
AN_ORDINARY_LENGTH = 6
AN_ORDINARY_LEVEL = "UG"

# One name, written twice on purpose, for the uniqueness pair.
ONE_NAME = "College of Nursing, 6-week undergraduate"
ANOTHER_NAME = "College of Nursing, 12-week undergraduate"


def test_a_course_numbered_in_each_band_really_stores_that_level(seed_rows: Any) -> None:
    """CONTROL — must be green today, and green after E5-01 lands.

    Every level test below, and every test in the membership module beside this
    one, rests on `course_at` producing a course whose **stored** level is the one
    asked for. That is a property of E0-05's generated column (ADR 0015) and of
    SPEC §8's bands rather than of anything E5-01 builds, so it is asserted here,
    once, where the failure says "the helper" instead of surfacing as a refused
    control inside a test about the set.

    A red here means this module's machinery is broken, not that the code is:
    either `NUMBER_BY_LEVEL` has drifted from §8's bands, or the derivation has.
    """
    for level, number in NUMBER_BY_LEVEL.items():
        course = course_at(seed_rows, level)
        assert course[COURSE_LEVEL_COLUMN] == level, (
            f"A course numbered {number!r} stored level {course[COURSE_LEVEL_COLUMN]!r} and this "
            f"module expects {level!r}. SPEC §8's bands are `000`-`099` DEV, `100`-`499` UG, "
            "`500`-`599` UGGR, `600`-`799` GR and `8000`-`9999` DR; `NUMBER_BY_LEVEL` in "
            "tests/fixtures/comparison_sets.py is where this module holds one number per band."
        )


@pytest.mark.parametrize("length", SPEC_LENGTHS, ids=[str(n) for n in SPEC_LENGTHS])
def test_a_set_declaring_a_length_the_calendar_uses_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, length: int
) -> None:
    """Criterion 1, the accepted side: each of SPEC §2.2's eight lengths is storable.

    One case per length rather than one assertion over the set, so the failure
    output names the length that cannot be stored: a rule written `IN (3, 6, 8,
    10, 12, 15, 16)` makes every dissertation-length set unwritable, and "§2.2's
    length set" includes the 18 the same sentence puts in parentheses.

    **The mutation it kills:** `18` left out of the `CHECK` in the migration, and
    its mirror — a `CHECK` written as a range, `length_weeks BETWEEN 3 AND 18`,
    which passes all eight of these and is caught only by the refusals below.

    **Its pair** is `test_a_set_declaring_a_length_outside_the_calendars_set_is_refused`.
    Neither half means anything alone: this one alone is satisfied by a table with
    no constraint at all, and that one alone by a table nothing can be written to.
    """
    table = comparison_set_table(metadata_tables)
    require_columns(table, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)

    refused = refusal_of(
        db_session, lambda: write_set(seed_rows, length=length, level=AN_ORDINARY_LEVEL)
    )

    assert refused is None, (
        f"A set declaring a length of {length} weeks was refused: {refused}. SPEC §2.2 lists the "
        "course lengths as 3, 6, 8, 10, 12, 15 and 16 weeks 'plus an 18-week dissertation "
        "length', so all eight are lengths this institution runs and a set that cannot name one "
        "of them is a cohort leadership cannot define."
    )


@pytest.mark.parametrize(
    ("length", "accepted_neighbour"),
    LENGTHS_OUTSIDE_THE_SET,
    ids=[f"{refused}-beside-{accepted}" for refused, accepted in LENGTHS_OUTSIDE_THE_SET],
)
def test_a_set_declaring_a_length_outside_the_calendars_set_is_refused(
    db_session: Any,
    metadata_tables: dict[str, Any],
    seed_rows: Any,
    length: int,
    accepted_neighbour: int,
) -> None:
    """Criterion 1, the refused side, each case beside the accepted length nearest it.

    The control is written first and required to be stored, which is what makes
    the refusal below a statement about this length rather than about the table:
    a schema that refused every set would otherwise pass all twelve of these
    (`docs/MISTAKES.md` entry 3).

    **Why the near misses and not round numbers.** `17` is the case a range check
    `BETWEEN 3 AND 18` accepts and no other test here would catch; `4`, `5`, `7`,
    `9`, `11`, `13` and `14` are the interior gaps the same check accepts; `0` and
    `-1` are what an `integer` column takes when nothing says otherwise, and a set
    declaring a length of zero resolves against no section ever.

    **The mutation it kills:** the `CHECK` dropped from the migration altogether,
    and — the near miss that matters more — the `CHECK` rewritten as a range,
    which every accepted case above passes.

    **Why the length set is hard-coded in the migration rather than read from the
    start-letter map**, said here because a reader will ask: the map is per-term
    data and a set outlives terms, so a set validated against this term's letters
    would become invalid when the letters changed. ADR 0164 records it.
    """
    table = comparison_set_table(metadata_tables)
    require_columns(table, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)

    control = refusal_of(
        db_session,
        lambda: write_set(seed_rows, length=accepted_neighbour, level=AN_ORDINARY_LEVEL),
    )
    assert control is None, (
        f"The control set — {accepted_neighbour} weeks, one of SPEC §2.2's lengths — was refused: "
        f"{control}. Until an ordinary set inserts, the refusal below says nothing about "
        f"{length}."
    )

    outside = refusal_of(
        db_session, lambda: write_set(seed_rows, length=length, level=AN_ORDINARY_LEVEL)
    )
    assert_refused_for_the_data(
        outside,
        f"A set declaring a length of {length} weeks",
        f"SPEC §2.2's lengths are {list(SPEC_LENGTHS)} and {length} is not one of them. A stored "
        "set nothing can resolve is worse than a refused one: E5-04 selects member courses' "
        "sections *of the declared length*, so this row is a benchmark that silently computes "
        f"over nothing. The {accepted_neighbour}-week set above was accepted in this same "
        "transaction, so the database is not refusing sets in general.",
    )


@pytest.mark.parametrize("level", SPEC_LEVELS, ids=list(SPEC_LEVELS))
def test_a_set_declaring_one_of_the_five_levels_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, level: str
) -> None:
    """Criterion 1, the accepted side of the level boundary: all five, one case each.

    All five and not three. SPEC §5.1 spends a paragraph on exactly this: "levels
    match **exactly**; no level is folded into another … the dual-credit and
    developmental populations are the two whose experience is least like the
    undergraduate mean". A schema that could not store a `DEV` or a `UGGR` set
    would make those two populations undefinable as a named cohort, which is the
    opposite of what the paragraph asks for.

    **The mutation it kills:** a level column typed against a three-value
    vocabulary, or a `CHECK` listing `('UG', 'GR', 'DR')` — the three a reader
    remembers.

    **Its pair** is `test_a_set_declaring_a_level_outside_the_five_is_refused`.
    """
    table = comparison_set_table(metadata_tables)
    require_columns(table, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)

    refused = refusal_of(
        db_session, lambda: write_set(seed_rows, length=AN_ORDINARY_LENGTH, level=level)
    )

    assert refused is None, (
        f"A set declaring level {level!r} was refused: {refused}. SPEC §8 bands every course into "
        f"one of {list(SPEC_LEVELS)} and §5.1 requires each to be compared only against itself, "
        "so all five are levels a named set may declare."
    )


@pytest.mark.parametrize(
    ("level", "accepted_control"),
    LEVELS_OUTSIDE_THE_FIVE,
    ids=[
        f"{refused or 'empty'}-beside-{accepted}" for refused, accepted in LEVELS_OUTSIDE_THE_FIVE
    ],
)
def test_a_set_declaring_a_level_outside_the_five_is_refused(
    db_session: Any,
    metadata_tables: dict[str, Any],
    seed_rows: Any,
    level: str,
    accepted_control: str,
) -> None:
    """Criterion 1, the refused side of the level boundary, each beside an accepted level.

    **The refusal may be an integrity violation or a value the type could not
    take, and both are accepted here.** The breakdown settles that this column
    uses the existing `course_level` enumerated type, which refuses an unknown
    label at input conversion with `22P02`; a schema holding the rule as a `CHECK`
    over text refuses it at `23514`. The criterion is that the database refuses
    the row, and pinning the SQLSTATE would pin the mechanism instead.

    **The mutation it kills:** the column declared as plain `text` with no rule at
    all, which takes every one of these. `'ug'` is the near miss that separates a
    real enumeration from a check written with `lower()`, and `''` the one that
    separates it from a check written as "not empty".

    **The control** is an accepted level written first in the same transaction,
    so a refusal here cannot be about sets being unwritable.
    """
    table = comparison_set_table(metadata_tables)
    require_columns(table, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)

    control = refusal_of(
        db_session,
        lambda: write_set(seed_rows, length=AN_ORDINARY_LENGTH, level=accepted_control),
    )
    assert control is None, (
        f"The control set — level {accepted_control!r}, one of SPEC §8's five — was refused: "
        f"{control}. Until an ordinary set inserts, the refusal below says nothing about "
        f"{level!r}."
    )

    outside = refusal_of(
        db_session, lambda: write_set(seed_rows, length=AN_ORDINARY_LENGTH, level=level)
    )
    assert_refused_for_the_data(
        outside,
        f"A set declaring level {level!r}",
        f"SPEC §8's levels are {list(SPEC_LEVELS)} and {level!r} is not one of them. A set "
        "declaring a level no course can carry can never gain a member, and §5.1's exact-match "
        f"rule is what the five exist for. The {accepted_control!r} set above was accepted in this "
        "same transaction.",
        classes=REFUSED_A_VALUE,
    )


def test_two_sets_may_not_share_a_name(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """One name means one set, so leadership cannot create two cohorts nobody can tell apart.

    A deployment serves exactly one institution (SPEC §8), so a set's name is
    unique across the whole table rather than per anything — the same rule
    `prefix.code` carries and for the same reason. Without it the management API
    E5-06 builds lists two rows a viewer reads as one, and E5-09's form offers
    both.

    **The mutation it kills:** the unique constraint left off `name` in the
    migration.

    **Its pair is the test below**, which requires two differently named sets to
    be accepted — without it this one is satisfied by a schema that refuses every
    second set.
    """
    require_columns(
        comparison_set_table(metadata_tables),
        (*DECLARED_COLUMNS, NAME_COLUMN),
        WHERE_THE_COLUMNS_COME_FROM,
    )

    first = refusal_of(
        db_session,
        lambda: write_set(
            seed_rows, length=AN_ORDINARY_LENGTH, level=AN_ORDINARY_LEVEL, name=ONE_NAME
        ),
    )
    assert first is None, (
        f"The first set named {ONE_NAME!r} was refused: {first}. Until one inserts, the refusal "
        "below says nothing about the name being taken."
    )

    again = refusal_of(
        db_session,
        lambda: write_set(
            seed_rows, length=AN_ORDINARY_LENGTH, level=AN_ORDINARY_LEVEL, name=ONE_NAME
        ),
    )
    assert_refused_for_the_data(
        again,
        f"A second set named {ONE_NAME!r}",
        "A named set is named so a person can choose it, and two rows with one name are two "
        "cohorts a viewer cannot tell apart — in E5-06's list, in E5-09's form, and in whatever "
        "E9 attaches to a report.",
    )


def test_two_sets_with_different_names_are_both_stored(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The other half of the uniqueness pair: the table holds more than one set.

    **The mutation it kills:** a uniqueness rule written over the wrong columns —
    `UNIQUE (length_weeks, level)`, say, which reads plausibly and would refuse
    the second set here while passing the test above. Leadership defines as many
    6-week undergraduate cohorts as it has reasons for.
    """
    require_columns(
        comparison_set_table(metadata_tables),
        (*DECLARED_COLUMNS, NAME_COLUMN),
        WHERE_THE_COLUMNS_COME_FROM,
    )

    first = refusal_of(
        db_session,
        lambda: write_set(
            seed_rows, length=AN_ORDINARY_LENGTH, level=AN_ORDINARY_LEVEL, name=ONE_NAME
        ),
    )
    second = refusal_of(
        db_session,
        lambda: write_set(
            seed_rows, length=AN_ORDINARY_LENGTH, level=AN_ORDINARY_LEVEL, name=ANOTHER_NAME
        ),
    )

    assert first is None and second is None, (
        f"Two sets with different names were not both stored: {first!r} then {second!r}. Both "
        "declare the same length and level, which is ordinary — SPEC §5.1 lets leadership define "
        "any number of named cohorts, and two of them may well cover the same 6-week "
        "undergraduate population for different reasons."
    )


def test_a_set_with_no_members_is_stored(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """A set under construction is a row: the ticket's second settled decision, asserted.

    > **Whether a set may be empty.** The recommendation is yes at the schema (a
    > set under construction), with resolution treating an empty set as
    > suppressed; the service ticket asserts that half.

    So this is the schema half and only the schema half. What an empty set *means*
    at resolution is E5-04's, and nothing here says anything about it.

    **The mutation it kills:** a rule that makes membership mandatory — a `CHECK`
    on a member count, or a trigger requiring one row — which would make E5-06's
    create-then-add flow impossible and force the API to invent a placeholder
    member.

    **The non-emptiness guard is the read-back**, and it is not ceremony: this
    test would otherwise be satisfied by an insert the database swallowed, so the
    row is read back by its own key before the assertion is believed
    (`docs/MISTAKES.md` entry 3).
    """
    from fixtures.supervision import single_primary_key
    from sqlalchemy import select

    table = comparison_set_table(metadata_tables)
    require_columns(table, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)

    refused = refusal_of(
        db_session,
        lambda: write_set(seed_rows, length=AN_ORDINARY_LENGTH, level=AN_ORDINARY_LEVEL),
    )
    assert refused is None, (
        f"A set with no members was refused: {refused}. E5-01 settles that a set may be empty at "
        "the schema — a set under construction — and E5-04 owns what an empty set means when it "
        "is resolved."
    )

    key = single_primary_key(table)
    stored = db_session.execute(select(table)).mappings().all()
    assert stored, (
        f"`{table.name}` reports no row after an insert the database did not refuse, so the "
        f"assertion above is about a write that went nowhere. The key is `{key}`."
    )
