"""Deleting a member course is refused; deleting the set takes its members with it.

E5-01 criterion 3, in the ticket's words:

> Deleting a course that is a member does not orphan silently: the behavior
> (restrict or cascade) is chosen in the ADR and asserted.

and the decision the ticket settles beside it:

> **The member-deletion rule** (criterion 3): the recommendation is restrict — a
> set silently shrinking is a benchmark silently changing — with the ADR recording
> the alternative.

The two halves are opposite directions on purpose and both are asserted here.
Towards the course, deletion is **refused**: a named set is a deliberate cohort,
and a set that loses a course without anybody saying so produces a different
benchmark next Monday from the same page, with no trace on the chart. Towards the
set, deletion **cascades**: the set is the aggregate root, so deleting it deletes
its membership rows and leaves every course exactly where it was. ADR 0164 records
both and the alternative to each.

**Each direction is asserted beside the case that must still work**, which is what
keeps a refusal from being a fact about deletion in general and a cascade from
being a fact about a database that stored nothing (`docs/MISTAKES.md` entry 3):
a course no set names is deleted successfully, and after the cascade the member's
course is read back and still there.

**Which failure a red here is, before E5-01 lands.** Every test fails on its first
statement, in `comparison_set_table` or `membership_table`, with a message naming
what is missing — a FAILED and never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.comparison_sets import (
    COURSE_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    assert_refused_for_the_data,
    comparison_set_table,
    course_at,
    member_of,
    members_of,
    membership_table,
    refusal_of,
    require_columns,
    require_table,
    write_set,
)
from fixtures.supervision import single_primary_key
from sqlalchemy import select

pytestmark = pytest.mark.integration

DECLARED_COLUMNS = (LENGTH_COLUMN, LEVEL_COLUMN)

WHERE_THE_COLUMNS_COME_FROM = (
    "E5-01 gives `comparison_set` a declared length and a declared level (breakdown decision 3)."
)

A_LENGTH = 6
A_LEVEL = "UG"


def delete_row(session: Any, table: Any, row: Any) -> Any:
    """A callable that deletes one row of `table` by its primary key.

    A callable rather than the deletion itself, because every caller hands it to
    `refusal_of`, which runs it inside a savepoint and answers with the error it
    provoked — the same shape the schema modules use for an insert.
    """
    key = single_primary_key(table)
    return lambda: session.execute(table.delete().where(table.c[key] == row[key]))


def rows_of(session: Any, table: Any) -> list[Any]:
    """Every row of `table` this transaction can see."""
    return list(session.execute(select(table)).mappings().all())


def test_a_course_no_set_names_can_be_deleted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """CONTROL for the refusal below: deleting an unreferenced course works.

    Without it, "deleting a member course is refused" is equally true of a schema
    where no course can ever be deleted — by a trigger, by another ticket's
    foreign key, or because this module builds a course with something hanging off
    it. This is the assertion that tells those apart, and it names only tables
    E0-05 built, so it is green today and must stay green.
    """
    course_table = require_table(
        metadata_tables,
        COURSE_TABLE,
        "E0-05 builds the containment hierarchy; "
        "`tests/integration/test_org_containment_schema.py` diagnoses a missing `course`.",
    )

    course = course_at(seed_rows, A_LEVEL)
    refused = refusal_of(db_session, delete_row(db_session, course_table, course))

    assert refused is None, (
        f"Deleting a course that nothing references was refused: {refused}. Then the refusal in "
        "the test below would be a fact about courses rather than about membership, and criterion "
        "3 would be satisfied by a schema that has no membership rule at all."
    )


def test_deleting_a_course_a_set_names_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 3: the member course cannot be deleted out from under the set.

    The ticket settles restrict, and the sentence is the reason: a set silently
    shrinking is a benchmark silently changing. Past-referencing makes it worse
    than it sounds — SPEC §5.1 compares week N against prior terms too, so a course
    removed today changes figures that were already published, and the only record
    that anything moved would be the difference between two Mondays' charts
    (`docs/MISTAKES.md` entry 51's shape, arriving through the data rather than
    through the payload).

    **The mutation it kills:** `ondelete="CASCADE"` on the membership row's course
    key — one word in the migration, and the set quietly loses a course. `SET
    NULL` is the same defect wearing a different word, and it is caught here too
    because the delete would succeed.

    **The control** is the unreferenced course above; and the read-back below is
    the second half of the same guard — a refusal proves nothing if the membership
    row was never stored.
    """
    comparison = comparison_set_table(metadata_tables)
    require_columns(comparison, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)
    membership = membership_table(metadata_tables)
    course_table = require_table(metadata_tables, COURSE_TABLE, "E0-05 builds it.")

    stored_set = write_set(seed_rows, length=A_LENGTH, level=A_LEVEL)
    course = course_at(seed_rows, A_LEVEL)
    member_of(seed_rows, membership, stored_set, course)

    assert len(members_of(db_session, membership, stored_set)) == 1, (
        "The set holds no membership row, so the course below is not a member and the delete "
        "would be the control's case rather than this one's."
    )

    refused = refusal_of(db_session, delete_row(db_session, course_table, course))
    assert_refused_for_the_data(
        refused,
        "Deleting a course that a named set holds as a member",
        "E5-01 settles the member-deletion rule as restrict (ADR 0164): the set is a deliberate "
        "cohort and a benchmark that shrinks without anybody deciding it is a figure nobody can "
        "audit. A course leaving the institution is a real event; it is one somebody edits the "
        "set for, not one the database performs silently.",
    )

    assert len(members_of(db_session, membership, stored_set)) == 1, (
        "The membership row is gone after a delete the database refused, which means the refusal "
        "and the row are not describing the same transaction."
    )


def test_deleting_a_set_takes_its_members_and_leaves_the_courses(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The other direction: the set is the aggregate root, so its membership cascades.

    Deleting a named cohort is an ordinary act of leadership (E5-06 builds the
    delete), and a membership row surviving its set is a row pointing at nothing —
    the orphan the criterion's word "silently" is about. The courses themselves are
    untouched, which is the half that makes this a cascade rather than a purge: a
    course is org structure the LMS owns (SPEC §2.1) and no benchmark decision
    deletes one.

    **The mutation it kills:** the membership row's set key left without
    `ondelete="CASCADE"` — which makes deleting a set fail with a foreign key
    violation, so E5-06's delete cannot work at all — and its opposite, a cascade
    written on the *course* key that takes the course away with the set.

    **The non-emptiness guard comes first:** the membership row is counted before
    the delete, because "no membership rows afterwards" is trivially true of a set
    that never had one (`docs/MISTAKES.md` entry 3).
    """
    comparison = comparison_set_table(metadata_tables)
    require_columns(comparison, DECLARED_COLUMNS, WHERE_THE_COLUMNS_COME_FROM)
    membership = membership_table(metadata_tables)
    course_table = require_table(metadata_tables, COURSE_TABLE, "E0-05 builds it.")

    stored_set = write_set(seed_rows, length=A_LENGTH, level=A_LEVEL)
    course = course_at(seed_rows, A_LEVEL)
    member_of(seed_rows, membership, stored_set, course)

    before = members_of(db_session, membership, stored_set)
    assert len(before) == 1, (
        f"The set holds {len(before)} membership rows before the delete. A cascade that removes "
        "nothing looks exactly like a correct one when there was nothing to remove."
    )

    refused = refusal_of(db_session, delete_row(db_session, comparison, stored_set))
    assert refused is None, (
        f"Deleting a set that has a member was refused: {refused}. E5-06 builds the delete at "
        "leadership scope, so a set whose membership rows hold it in place is a set nobody can "
        "remove — and the API's only way out would be to delete the members first, which is the "
        "aggregate root's job rather than the caller's."
    )

    assert not members_of(db_session, membership, stored_set), (
        "The membership row outlived the set it belongs to. A row whose set is gone is the "
        f"orphan criterion 3 is about: nothing in `{membership.name}` says which cohort it "
        "described, and the next set to take that key inherits it."
    )

    key = single_primary_key(course_table)
    surviving = {row[key] for row in rows_of(db_session, course_table)}
    assert course[key] in surviving, (
        "The member course was deleted along with the set. A course is org structure the LMS owns "
        "(SPEC §2.1) and E5-01 deletes none of it; a cascade written on the course key would take "
        "a real course, its sections and every response under them out of the institution because "
        "somebody removed a benchmark."
    )
