"""`moderation_state`'s decision columns, held by the database — ticket E6-03's M2.

The ticket's "Owns" settles M2's columns and their rules:

  - `decided_by_person_id`, nullable, a `person` foreign key with `RESTRICT`, as
    `audit_log.actor_person_id` is;
  - `decided_as`, the role the decision was made under, from a closed vocabulary —
    `INSTRUCTOR`, `LEAD_FACULTY`, `CHAIR` (work order decision 5);
  - `reason`, nullable, non-blank and bounded when present —
    `length(reason) BETWEEN 1 AND 500` and `btrim(reason) <> ''` (decision 4);
  - `is_undo boolean NOT NULL DEFAULT false` (decision 3);
  - `CHECK`s: a decider names a role and a role names a decider; a row with no
    decider is the router's and is `FLAGGED_COLLAPSED`; a reason needs a decider.

Criterion 2's database half — "a blank reason, or one over the bound, is refused …
by the database" — is the first test here; the route's half is
`test_an_unflagged_exclusion_needs_a_reason_checked_as_sent.py`.

**Every refusal is a refused statement with its SQLSTATE** — 23514 for a `CHECK`,
23502 for `NOT NULL`, 23503 for the foreign key — never "the insert raised", because
a missing column or a type error raises too and would read as the rule working
(`docs/MISTAKES.md` entry 3). **Every refusal sits beside an accepted row one value
away**, in the same transaction, so a table that refuses everything is red.

Rows with a decider are written on the bootstrap connection, through `seed_rows`,
every decision column named on every insert — the seeding walker's decider fill
(`tests/fixtures/supervision.py::fill_a_decider`) steps aside for a row that names
either column, so nothing here is a value the fixture chose. **Rows with no decider
are written as `pulse_moderation_definer`**, by `SET ROLE` inside the savepoint:
the ruled trigger refuses a decider-less row from every other role, so a `CHECK`
about decider-less rows can only be told apart from the trigger when the definer is
the one writing (the trigger itself is
`test_a_moderation_state_row_with_no_decider_is_the_routers_alone.py`). Each
statement runs in a savepoint that is always rolled back, which also undoes the
`SET ROLE`.

**Which failure a red is, before M2 lands:** `require_decision_columns`, the first
statement of every test, fails naming the four columns (`docs/MISTAKES.md`
entry 44).
"""

from collections.abc import Callable
from typing import Any

import pytest
from fixtures.instructor_decisions import (
    ANSWER_COLUMN,
    AS_CHAIR,
    AS_INSTRUCTOR,
    AS_LEAD_FACULTY,
    DECIDED_AS_COLUMN,
    DECIDER_COLUMN,
    IS_UNDO_COLUMN,
    MODERATION_STATE_TABLE,
    REASON_BOUND,
    REASON_COLUMN,
    STATE_COLUMN,
    STORED_EXCLUDED,
    STORED_FLAGGED,
    STORED_KEPT,
    STORED_PUBLISHED,
    a_reason,
    require_decision_columns,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

MODERATION_DEFINER_ROLE = "pulse_moderation_definer"
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
FOREIGN_KEY_VIOLATION = "23503"


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def attempted(session: Any, write: Callable[[], Any]) -> Any:
    """Run `write` in a savepoint that is always rolled back; answer its error or `None`."""
    savepoint = session.begin_nested()
    try:
        write()
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


class Rows:
    """One comment and two people, and a writer of decision rows about the comment."""

    def __init__(self, db_session: Any, seed_rows: Any) -> None:
        self.session = db_session
        self.seed = seed_rows
        self.answer = seed_rows(
            "answer", {}, comment_text="e6-03 a comment M2's rules are asked about"
        )
        self.person = seed_rows("person", {})["id"]

    def write(
        self,
        *,
        state: str,
        decided_by: Any,
        decided_as: Any,
        reason: Any = None,
        **more: Any,
    ) -> Callable[[], Any]:
        values = {
            ANSWER_COLUMN: self.answer["id"],
            STATE_COLUMN: state,
            DECIDER_COLUMN: decided_by,
            DECIDED_AS_COLUMN: decided_as,
            REASON_COLUMN: reason,
            **more,
        }
        return lambda: self.seed(MODERATION_STATE_TABLE, {}, **values)

    def as_router(
        self, *, state: str, decided_as: Any = None, reason: Any = None
    ) -> Callable[[], Any]:
        """A row with no decider, written as the routing definer's owner.

        The `SET ROLE` is undone by the savepoint rollback `attempted` always takes,
        so it is never reset here — a `RESET ROLE` after a refused insert would run
        in an aborted transaction and replace the refusal with its own error.
        """

        def write() -> None:
            self.session.execute(text(f'SET ROLE "{MODERATION_DEFINER_ROLE}"'))
            self.session.execute(
                text(
                    "INSERT INTO public.moderation_state (answer_id, state, decided_as, reason) "
                    "VALUES (CAST(:answer AS uuid), :state, :decided_as, :reason)"
                ),
                {
                    "answer": str(self.answer["id"]),
                    "state": state,
                    "decided_as": decided_as,
                    "reason": reason,
                },
            )

        return write

    def decided(self, **values: Any) -> Callable[[], Any]:
        """An instructor's exclusion, with whatever the caller overrides."""
        base: dict[str, Any] = {
            "state": STORED_EXCLUDED,
            "decided_by": self.person,
            "decided_as": AS_INSTRUCTOR,
        }
        base.update(values)
        return self.write(**base)

    def accepted(self, write: Callable[[], Any], what: str) -> None:
        failure = attempted(self.session, write)
        assert failure is None, (
            f"{what} was refused: {failure} (SQLSTATE {sqlstate(failure)}). Until it is accepted, "
            "the refusals beside it may be a table that refuses every row."
        )

    def refused(self, write: Callable[[], Any], what: str, code: str = CHECK_VIOLATION) -> None:
        failure = attempted(self.session, write)
        assert failure is not None and sqlstate(failure) == code, (
            f"{what} was answered {failure!r} (SQLSTATE {sqlstate(failure)}), not refused with "
            f"{code}. E6-03's M2 makes the database hold this rule, whatever the route checks."
        )


@pytest.fixture
def rows(db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]) -> Rows:
    return Rows(db_session, seed_rows)


def test_a_reason_is_non_blank_and_at_most_500_characters(
    rows: Rows, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 2's database half: `length(reason) BETWEEN 1 AND 500` and `btrim(reason) <> ''`.

    Accepted: one character, and exactly 500. Refused with 23514: the empty string,
    whitespace alone, and 501 characters.

    **The mutations this kills:** no `CHECK` on the reason (a route that forgot the
    rule stores a blank or an essay); a `length >= 1` check without the `btrim` (a
    space is stored as a stated reason); a bound of 501, or of `length < 500`.
    """
    require_decision_columns(metadata_tables)
    longest = a_reason(REASON_BOUND)
    too_long = a_reason(REASON_BOUND + 1)
    rows.accepted(rows.decided(reason="x"), "A one-character reason")
    rows.accepted(rows.decided(reason=longest), "A reason of exactly 500 characters")
    rows.refused(rows.decided(reason=""), "An empty reason")
    rows.refused(rows.decided(reason="   \t"), "A reason of whitespace alone")
    rows.refused(rows.decided(reason=too_long), "A reason of 501 characters")


def test_a_reason_needs_a_decider(rows: Rows, metadata_tables: dict[str, Any]) -> None:
    """ "A reason needs a decider": a router-shaped row carrying a reason is refused.

    Both written as the definer, so the trigger lets both through and only the
    `CHECK` can refuse the second. **The control** is the same row without the
    reason — the router's own flag, which the database must keep accepting or
    E6-01's definer stops working.

    **The mutation this kills:** the rule left out, which lets the router write a
    reason on a row nobody decided — an exclusion log line with a justification and
    no author.
    """
    require_decision_columns(metadata_tables)
    rows.accepted(
        rows.as_router(state=STORED_FLAGGED),
        "The router's flag, with no decider and no reason, written by the definer",
    )
    rows.refused(
        rows.as_router(state=STORED_FLAGGED, reason="a reason"),
        "A row with no decider carrying a reason, written by the definer",
    )


def test_a_decider_names_a_role_and_a_role_names_a_decider(
    rows: Rows, metadata_tables: dict[str, Any]
) -> None:
    """Both halves of the pairing rule, beside the row that carries both.

    **The mutations this kills:** a decider with no role (ruling 4 has the log show
    the decider's *role*, so the line has nothing to show); a role with no decider (a
    decision attributed to a role and to nobody).
    """
    require_decision_columns(metadata_tables)
    rows.accepted(rows.decided(), "A decision naming a decider and a role")
    rows.refused(rows.decided(decided_as=None), "A decider with no role")
    rows.refused(
        rows.as_router(state=STORED_FLAGGED, decided_as=AS_INSTRUCTOR),
        "A role with no decider, written by the definer",
    )


@pytest.mark.parametrize("state", [STORED_PUBLISHED, STORED_EXCLUDED, STORED_KEPT])
def test_a_row_with_no_decider_is_the_routers_and_is_only_ever_a_flag(
    state: str, rows: Rows, metadata_tables: dict[str, Any]
) -> None:
    """ "A row with no decider is the router's and is `FLAGGED_COLLAPSED`."

    A case per other state, decider-less, written by the definer — the one role the
    trigger lets write a decider-less row — and refused with 23514; **the control**
    is the same comment's decider-less flag, accepted.

    **The mutation this kills:** the rule written for one of the three states only —
    an `EXCLUDED` row with nobody behind it is a comment hidden from students with no
    entry in the exclusion log, which is the anti-cherry-picking mechanism bypassed,
    and the router is the one writer that could still produce it.
    """
    require_decision_columns(metadata_tables)
    rows.accepted(rows.as_router(state=STORED_FLAGGED), "The router's flag")
    rows.refused(
        rows.as_router(state=state), f"A {state} row with no decider, written by the definer"
    )


@pytest.mark.parametrize("role", [AS_INSTRUCTOR, AS_LEAD_FACULTY, AS_CHAIR])
def test_each_role_in_the_vocabulary_is_accepted(
    role: str, rows: Rows, metadata_tables: dict[str, Any]
) -> None:
    """Decision 5: the vocabulary includes the chair, so E6-05 needs no migration of its own.

    **The mutation this kills:** a vocabulary of the instructor alone, or without the
    chair who decides for a course with no lead (SPEC §8's `lead_faculty_mapping`).
    """
    require_decision_columns(metadata_tables)
    rows.accepted(rows.decided(decided_as=role), f"A decision made as {role}")


@pytest.mark.parametrize("role", ["DEAN", "instructor", ""], ids=["dean", "lower-case", "empty"])
def test_a_role_outside_the_vocabulary_is_refused(
    role: str, rows: Rows, metadata_tables: dict[str, Any]
) -> None:
    """Decision 5's closed set: a role that reads like one and is not in it, refused with 23514.

    **The control** is the instructor's role on the same row. **The mutation this
    kills:** `decided_as` as a plain text column with no `_in_the_vocabulary`
    `CHECK`, which stores `DEAN` and puts a role in the log no door decides as.
    """
    require_decision_columns(metadata_tables)
    rows.accepted(rows.decided(), "A decision made as INSTRUCTOR")
    rows.refused(rows.decided(decided_as=role), f"A decision made as {role!r}")


def test_is_undo_defaults_to_false_and_is_never_null(
    rows: Rows, db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """Decision 3: `is_undo boolean NOT NULL DEFAULT false`.

    A decision written without naming the column reads back `false`; one written
    with `NULL` is refused with 23502.

    **The mutations this kill:** a nullable column (an undo nobody can tell from a
    decision); a default of `true`, or none.
    """
    require_decision_columns(metadata_tables)
    stored = rows.seed(
        MODERATION_STATE_TABLE,
        {},
        **{
            ANSWER_COLUMN: rows.answer["id"],
            STATE_COLUMN: STORED_EXCLUDED,
            DECIDER_COLUMN: rows.person,
            DECIDED_AS_COLUMN: AS_INSTRUCTOR,
        },
    )
    assert (
        stored[IS_UNDO_COLUMN] is False
    ), f"A decision written without `{IS_UNDO_COLUMN}` reads back {stored[IS_UNDO_COLUMN]!r}."
    rows.refused(
        rows.decided(**{IS_UNDO_COLUMN: None}),
        "A decision with `is_undo` NULL",
        NOT_NULL_VIOLATION,
    )


def test_a_decider_cannot_be_deleted_from_under_a_decision(
    rows: Rows, db_session: Any, seed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """The foreign key is `RESTRICT`, as `audit_log.actor_person_id` is.

    A person who made a decision cannot be deleted (23503); a person who made none
    can — the control that keeps the refusal about the decision.

    **The mutations this kill:** `ON DELETE CASCADE` (deleting a staff member erases
    their exclusions — the trail is gone); `ON DELETE SET NULL` (the row becomes a
    decider-less exclusion, which the state rule should refuse anyway, and an
    exclusion log line with nobody behind it).
    """
    require_decision_columns(metadata_tables)
    rows.decided()()
    bystander = seed_rows("person", {})["id"]

    def delete(person: Any) -> Callable[[], Any]:
        return lambda: db_session.execute(
            text("DELETE FROM public.person WHERE id = :id"), {"id": person}
        )

    assert attempted(db_session, delete(bystander)) is None, (
        "A person with no decisions could not be deleted, so the refusal below is not about "
        "the decision."
    )
    rows.refused(
        delete(rows.person), "Deleting a person who made a decision", FOREIGN_KEY_VIOLATION
    )
