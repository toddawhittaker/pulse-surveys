"""A second `institution` row is refused by the database — ticket E0-22.

SPEC §8: "A deployment serves exactly one institution, and that is enforced by a
constraint permitting at most one `institution` row rather than left as an
assumption." Until E0-22 the sentence was true of the document and false of the
database. The rule is what makes the rest of `app/models/org.py` coherent —
`prefix.code` is unique across the whole table while `college.name` is unique per
institution — and without it the first object to notice a second institution was
`uq_prefix_code`, refusing that institution's `BIOL` with an error naming a
constraint, no institution, and the wrong row (ADR 0017).

**Why the second row carries a different name.** `institution.name` is unique on
its own, so a second row spelled the same way is refused whether or not the rule
under test exists — the test would pass against a database that has never heard
of it. The two rows here differ in every column a caller can set, so the only
thing left to refuse the second one is the rule, and the assertion names the
object that did the refusing rather than settling for "something failed".

**The mutations these two tests survive**, in E0-20's vocabulary, with the near
miss each must tolerate:

  - `uq_institution_one_row` dropped → the second insert lands, and
    `test_a_second_institution_row_is_refused` goes red. That is the ticket's
    stated done-when.
  - the index made non-unique, or its expression changed to `(name)` → the same
    test goes red, because a unique index on the name is exactly the object that
    already existed and does not refuse a differently-named row.
  - the index changed to something that refuses *every* insert →
    `test_the_first_institution_row_is_accepted` goes red. A rule that permits at
    most one row has to permit one, and a test suite that only asserted the
    refusal would call an empty table a pass.

**What is deliberately not asserted here: that the index exists.** Reading it out
of `pg_index` would be a second test of one mechanism, and `alembic check`
already compares this index against the model in both directions — the drop, the
`unique` flag and the expression each fail it, measured on the pinned Alembic
before the shape was chosen (ADR 0072). What the catalog cannot say is whether
the object refuses the row, which is what these tests are for.
"""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The rule's object, named here because the assertion is about *which* object
# refused the row. The model and the migration spell it the same way, and the
# `ix` naming template cannot build it for them: it interpolates a column name
# and this index is on an expression.
ONE_ROW = "uq_institution_one_row"

INSERT_INSTITUTION = "INSERT INTO public.institution (name) VALUES (:name)"
COUNT_INSTITUTIONS = "SELECT count(*) FROM public.institution"


def insert_institution(session: Any, name: str) -> None:
    """Write one institution row under the given name."""
    session.execute(text(INSERT_INSTITUTION), {"name": name})


def test_the_first_institution_row_is_accepted(db_session: Any) -> None:
    """One institution is the supported configuration, not zero.

    This is the near miss for the test below. A rule spelled as a check that
    nothing can satisfy — or an index on an expression that collides with
    itself on the first row — refuses the second insert exactly as the right
    rule does, and would be indistinguishable from it without this test.
    """
    assert db_session.execute(text(COUNT_INSTITUTIONS)).scalar_one() == 0, (
        "The migrated database is expected to hold no institution rows before this test seeds "
        "one. A row already here means a fixture seeded it and the counts below cannot be read."
    )

    insert_institution(db_session, "Franklin University")

    assert db_session.execute(text(COUNT_INSTITUTIONS)).scalar_one() == 1


def test_a_second_institution_row_is_refused(db_session: Any) -> None:
    """SPEC §8's rule, asked of the database rather than of the documentation.

    The two rows differ in name, so `uq_institution_name` cannot be what refuses
    the second one, and the message is asserted to name `uq_institution_one_row`
    so that a refusal from some other object is a failure rather than a pass.
    """
    insert_institution(db_session, "Franklin University")

    with pytest.raises(DatabaseError) as refusal, db_session.begin_nested():
        insert_institution(db_session, "A Second Institution")

    assert ONE_ROW in str(refusal.value), (
        f"A second institution row was refused, but not by {ONE_ROW}. SPEC §8 requires the "
        f"deployment's single-institution rule to be the object that refuses it, so that the "
        f"error names the row that is actually wrong. Postgres said: {refusal.value}"
    )
