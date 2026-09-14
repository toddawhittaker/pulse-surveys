"""A member course's level equals the set's declared level, enforced by the database.

E5-01 criterion 2, in the ticket's words:

> A member course whose level differs from the set's declared level is refused at
> the database; a matching one is accepted — the pair proven together, so the
> refusal is the constraint's and not an accident of the fixture (MISTAKES entry
> 3).

The rule comes from SPEC §5.1: comparability requires an exact level match, and
"a `UGGR` section is compared against other `UGGR` sections and not against `UG`
or `GR` ones, and a `DEV` section only against `DEV`". The breakdown's decision 3
puts the declaration on the set and the membership at course grain, so the only
place that sentence can be made unbreakable is here — a set holding one
off-level course produces a benchmark figure that averages two populations §5.1
says are not comparable, and no reader of the chart can see it.

**Every refusal is written beside its matching acceptance, in the same
transaction, over the same two rows' worth of seeding.** That is the criterion's
own wording and `docs/MISTAKES.md` entry 3's rule: a schema that refused every
membership row would satisfy twenty refusals and nothing else in this repository
would say so.

**This module names no column that holds the agreement**, and that is deliberate.
The ticket requires the rule "at the database, not only in a route" and leaves the
mechanism to the migration; the breakdown settles a denormalized level pair under
composite foreign keys, and `member_of` in `tests/fixtures/comparison_sets.py`
fills whatever the row carries from the set row and the course row themselves. So
a red here is the rule missing, not the rule spelled differently — and mutating
the `CHECK` in the migration is what turns these tests red.

**Which failure a red here is, before E5-01 lands.** Every test fails on its first
statement, in `comparison_set_table` or `membership_table`, with a message naming
what is missing — a FAILED and never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    COURSE_LEVEL_COLUMN,
    COURSE_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    SPEC_LEVELS,
    assert_refused_for_the_data,
    comparison_set_table,
    course_at,
    member_of,
    members_of,
    membership_table,
    one_key_column_to,
    refusal_of,
    require_columns,
    require_table,
    write_set,
)
from fixtures.supervision import single_primary_key

pytestmark = pytest.mark.integration

DECLARED_COLUMNS = (LENGTH_COLUMN, LEVEL_COLUMN)

WHERE_THE_COLUMNS_COME_FROM = (
    "E5-01 gives `comparison_set` a declared length and a declared level (breakdown decision 3), "
    "and constrains membership to courses of that level."
)

AN_ORDINARY_LENGTH = 6

# Each level paired with a different one, so every level is exercised on both
# sides of the rule: as the level a set declares and as the level a rejected
# course carries. `UG` against `UGGR` and `GR` against `UGGR` are the two pairs
# SPEC §5.1 argues about by name — the dual-credit population is the one a
# folding implementation would fold.
MISMATCHED_LEVELS = (
    ("DEV", "UG"),
    ("UG", "UGGR"),
    ("UGGR", "UG"),
    ("UGGR", "GR"),
    ("GR", "UGGR"),
    ("GR", "DR"),
    ("DR", "GR"),
)


def test_the_membership_table_names_a_set_and_a_course(metadata_tables: dict[str, Any]) -> None:
    """CONTROL — the discovery this module's every other test rests on.

    `membership_table` finds the membership relation by following foreign keys
    rather than by name, because the ticket does not name it. If that discovery
    ever answered with the wrong table — a second table growing keys to both — the
    tests below would be measuring something else entirely and would still be able
    to pass. This is the assertion that says which table they are about, and its
    failure names it.

    Red before E5-01 lands, and the red is the missing table by name; green
    afterwards, and it stays green whatever the table is called.
    """
    membership = membership_table(metadata_tables)
    comparison = comparison_set_table(metadata_tables)

    set_key = single_primary_key(comparison)
    course_key = single_primary_key(
        require_table(
            metadata_tables,
            COURSE_TABLE,
            "E0-05 builds the containment hierarchy and `tests/integration/"
            "test_org_containment_schema.py` is where a missing `course` is diagnosed.",
        )
    )

    assert one_key_column_to(membership, COMPARISON_SET_TABLE, set_key), (
        f"`{membership.name}` was found as the membership table but has no foreign key to "
        f"`{COMPARISON_SET_TABLE} ({set_key})`."
    )
    assert one_key_column_to(membership, COURSE_TABLE, course_key), (
        f"`{membership.name}` was found as the membership table but has no foreign key to "
        f"`{COURSE_TABLE} ({course_key})`. Membership is at course grain (breakdown decision 3): "
        "a section-level set ages out every term under past-referencing."
    )


@pytest.mark.parametrize("level", SPEC_LEVELS, ids=list(SPEC_LEVELS))
def test_a_course_of_the_sets_declared_level_may_be_a_member(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, level: str
) -> None:
    """Criterion 2, the accepted half: a matching course joins the set, at every level.

    One case per level, so a rule that happens to work for `UG` and not for `DR`
    names the level it fails on. The four-digit doctoral number is the one most
    likely to be handled differently, since §8 gives it a width rule of its own.

    **The mutation it kills:** a composite key pointed at the wrong referenced
    columns, or a `CHECK` written with the two sides transposed against a
    hard-coded level — either leaves the honest row refused, and this is the half
    that catches it.

    **The read-back is the non-emptiness guard.** A membership insert that
    silently stored nothing would satisfy "was not refused" perfectly
    (`docs/MISTAKES.md` entry 3), so the row is counted back off the set.
    """
    comparison = comparison_set_table(metadata_tables)
    require_columns(comparison, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)
    membership = membership_table(metadata_tables)

    stored_set = write_set(seed_rows, length=AN_ORDINARY_LENGTH, level=level)
    course = course_at(seed_rows, level)
    assert course[COURSE_LEVEL_COLUMN] == level, (
        f"The seeded course stores level {course[COURSE_LEVEL_COLUMN]!r} rather than {level!r}, so "
        "this test is not about a matching pair at all. "
        "`test_a_comparison_set_declares_one_length_and_one_level.py` diagnoses that."
    )

    refused = refusal_of(db_session, lambda: member_of(seed_rows, membership, stored_set, course))
    assert refused is None, (
        f"A {level!r} course was refused membership of a set declaring {level!r}: {refused}. That "
        "is the ordinary case — SPEC §5.1's default comparison set is 'the same Lead Faculty's "
        "courses filtered to matching length+level' — so a schema that refuses it refuses every "
        "named set anyone would build, and the refusals below would then be evidence of nothing."
    )

    members = members_of(db_session, membership, stored_set)
    assert len(members) == 1, (
        f"The set holds {len(members)} membership rows after one accepted insert. An insert the "
        "database neither refused nor stored would make every refusal in this module vacuous."
    )


@pytest.mark.parametrize(
    ("declared", "course_level"),
    MISMATCHED_LEVELS,
    ids=[f"{declared}-set-{other}-course" for declared, other in MISMATCHED_LEVELS],
)
def test_a_course_of_another_level_may_not_be_a_member(
    db_session: Any,
    metadata_tables: dict[str, Any],
    seed_rows: Any,
    declared: str,
    course_level: str,
) -> None:
    """Criterion 2, the refused half, each case beside a matching member of the same set.

    **The matching member is written first, into the same set, and required to be
    stored.** That is what isolates the refusal to the level disagreement: a
    membership table nothing can be written to would refuse the second row too,
    and the criterion says the pair is proven together for exactly this reason.

    **Why the pairs are these.** `UGGR` appears on both sides three times because
    SPEC §5.1 argues about it by name: "a `UGGR` section is compared against other
    `UGGR` sections and not against `UG` or `GR` ones". An implementation that
    folds dual credit into either neighbour passes every other case here.

    **The mutation it kills:** the `CHECK` comparing the two levels dropped from
    the migration, leaving the membership row a plain pair of keys — which is what
    the table looks like if the agreement is enforced in E5-06's route instead,
    the thing the criterion says must not be the whole of it. One step further
    out, dropping `UNIQUE (id, level)` from `course` or from `comparison_set`
    removes what the composite keys reference and the rule cannot exist at all.

    **The near miss it must tolerate:** the matching member above, which stays
    accepted.
    """
    comparison = comparison_set_table(metadata_tables)
    require_columns(comparison, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)
    membership = membership_table(metadata_tables)

    stored_set = write_set(seed_rows, length=AN_ORDINARY_LENGTH, level=declared)
    matching = course_at(seed_rows, declared)
    control = refusal_of(db_session, lambda: member_of(seed_rows, membership, stored_set, matching))
    assert control is None, (
        f"The control member — a {declared!r} course in a {declared!r} set — was refused: "
        f"{control}. Until a matching course can join, the refusal below says nothing about the "
        "level disagreement."
    )

    off_level = course_at(seed_rows, course_level)
    assert off_level[COURSE_LEVEL_COLUMN] == course_level, (
        f"The second course stores level {off_level[COURSE_LEVEL_COLUMN]!r} rather than "
        f"{course_level!r}, so this test would be attempting a matching member and calling it a "
        "mismatch."
    )

    crossed = refusal_of(
        db_session, lambda: member_of(seed_rows, membership, stored_set, off_level)
    )
    assert_refused_for_the_data(
        crossed,
        f"A {course_level!r} course named as a member of a set declaring {declared!r}",
        "SPEC §5.1: levels match exactly and no level is folded into another, because 'the "
        "dual-credit and developmental populations are the two whose experience is least like the "
        "undergraduate mean'. A set holding this row resolves to a cohort spanning two levels and "
        "produces a mean §5.1 says is not a comparison at all — visible nowhere on the chart it "
        f"is drawn on. The {declared!r} member above was accepted into this same set, so the "
        "database is not refusing membership in general.",
    )


def test_one_course_may_not_be_named_twice_in_one_set(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The pair is unique: a set is a list of courses, not a bag of them.

    A course counted twice weights that course twice in every figure the set
    produces, and — the half that matters more — twice in the **section count**
    the benchmark minimum is compared against (SPEC §4.1 item 7, breakdown
    decision 2). A duplicate can therefore carry a thin cohort over the minimum
    without adding a single section to it, which is a suppression rule defeated by
    a `UNIQUE` nobody wrote.

    **The mutation it kills:** the unique constraint on the pair left off the
    migration.

    **Its pair is the test below**, which requires one course to be nameable in
    two different sets — without it, this one is satisfied by a rule made unique
    on the course alone.
    """
    comparison = comparison_set_table(metadata_tables)
    require_columns(comparison, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)
    membership = membership_table(metadata_tables)

    stored_set = write_set(seed_rows, length=AN_ORDINARY_LENGTH, level="UG")
    course = course_at(seed_rows, "UG")

    first = refusal_of(db_session, lambda: member_of(seed_rows, membership, stored_set, course))
    assert first is None, (
        f"The first membership row was refused: {first}. Until one course can join one set, the "
        "refusal below says nothing about the pair being taken."
    )

    again = refusal_of(db_session, lambda: member_of(seed_rows, membership, stored_set, course))
    assert_refused_for_the_data(
        again,
        "The same course named twice in one set",
        "A named set is a list of member courses (breakdown decision 3). A course counted twice "
        "weights its sections twice in every comparison figure and twice in the section count the "
        "benchmark minimum is measured against, so a duplicate can lift a thin cohort over the "
        "minimum §4.1 item 7 exists to enforce.",
    )


def test_one_course_may_be_named_in_two_different_sets(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The other half of the uniqueness pair: sets overlap, and that is ordinary.

    Leadership defines cohorts for different questions and the same course belongs
    to several of them. A uniqueness rule written on the course alone would refuse
    the second row here and pass the test above.

    **The mutation it kills:** `UNIQUE (course_id)` in place of the pair.
    """
    comparison = comparison_set_table(metadata_tables)
    require_columns(comparison, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)
    membership = membership_table(metadata_tables)

    course = course_at(seed_rows, "UG")
    one = write_set(seed_rows, length=AN_ORDINARY_LENGTH, level="UG", name="One cohort")
    another = write_set(seed_rows, length=12, level="UG", name="Another cohort")

    first = refusal_of(db_session, lambda: member_of(seed_rows, membership, one, course))
    second = refusal_of(db_session, lambda: member_of(seed_rows, membership, another, course))

    assert first is None and second is None, (
        f"One course could not be named in two sets: {first!r} then {second!r}. Nothing in SPEC "
        "§5.1 makes membership exclusive — a course sits in as many named cohorts as leadership "
        "has questions — and a schema that refuses the second row makes the second set "
        "undefinable."
    )

    assert len(members_of(db_session, membership, one)) == 1, (
        "The first set holds no membership row after an accepted insert, so this test compared "
        "two writes that went nowhere."
    )
    assert (
        len(members_of(db_session, membership, another)) == 1
    ), "The second set holds no membership row after an accepted insert."
