"""The academic calendar: terms, their weeks, the start-letter map, and survey windows.

SPEC §2.2, §3.1, §6.3 and §8. The calendar is institution *configuration* rather
than code — an admin sets a term's length and the letters that start inside it
(§6.3) — so it is data with constraints, and everything derived from it (a
section's length, start and end dates) is E0-07's arithmetic over these rows.

**Two rules here compare a row against its term, and neither is a plain CHECK.**
A week number has to fit inside its own term's length, and a start letter's
length may not exceed it. A `CHECK` constraint cannot read another table, so both
are enforced by a composite foreign key that carries the term's length alongside
its id — `(term_id, term_length_weeks)` referencing `term (id, length_weeks)` —
which turns each rule into a local comparison the server checks like any other.
[ADR 0018](../../../docs/adr/0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)
records why that and not a trigger; the short version is that a trigger commits a
violating row when a term is shortened concurrently, and this does not.

`term_length_weeks` is therefore **not a column anyone sets on purpose**. It is a
copy the foreign key keeps in step: `ON UPDATE CASCADE` rewrites it when the term
changes, and the local CHECK then refuses the change if some row no longer fits.
A row that misstates it is refused by the foreign key rather than stored.

**Timestamps are timezone-aware and refuse a naive value** (§3.1: a window opens
Friday 18:00 and closes Sunday 23:59:59 in the institution timezone). Postgres
does not refuse a naive datetime on its own — it reads one in the session's
`TimeZone` and stores whatever instant that names — so the guard sits on the
column type, `AwareDateTime` in `app.models.base`, where every writer meets it.

**Where the institution timezone itself lives.** In `app.config.Settings`, as
`INSTITUTION_TIMEZONE`, which is E0-05's decision recorded in `Institution`'s
docstring. So a term's "institution timezone reference" is `institution_id`: the
term names the institution, and the institution's timezone is configuration. A
per-term timezone column would be a second place for one value to live.

**Not here, on purpose.** Windows are not scheduled — `survey_window` carries the
columns and the constraints, and the logic that fills them is E2. A week carries
no dates: nothing needs them yet, and the section-date arithmetic that might is
E0-07's, over `start_letter_map`. The Fall 2026 seed map (§2.2) is fixture and
seed data (E0-17), never rows in a migration.
"""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base


class Term(Base):
    """One academic term — Fall 2026 — and how many weeks it runs.

    **The length is stored, not derived from the two dates.** SPEC §2.2 states
    term lengths as institution configuration (18 for fall and spring, 12 for
    summer), which is a value someone sets; and the spec says neither whether
    `end_date` is inclusive nor what a span that is not a whole number of weeks
    would mean. Both cross-row rules in this module compare against the length,
    so deriving it would rest them on arithmetic the spec does not specify.

    For the same reason there is **no constraint tying the length to the dates**.
    `end_date > start_date` is asserted because it is true under any reading; an
    equality between the length and the span would decide the inclusive question
    in a CHECK constraint, which is not this ticket's to decide.

    `UNIQUE (id, length_weeks)` looks redundant next to the primary key and is
    not: a foreign key must reference a unique constraint, and it is what lets
    `week` and `start_letter_map` carry `(term_id, term_length_weeks)` as one
    reference. Dropping it drops both cross-table rules with it.
    """

    __tablename__ = "term"
    __table_args__ = (
        UniqueConstraint("institution_id", "name"),
        UniqueConstraint("id", "length_weeks"),
        CheckConstraint("length_weeks >= 1", name="length_weeks_is_at_least_one"),
        CheckConstraint("end_date > start_date", name="end_date_is_after_start_date"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # No index of its own: it leads `uq_term_institution_id_name`, which already
    # serves a lookup by institution. Same reasoning as `course.prefix_id` in
    # `app/models/org.py`.
    institution_id: Mapped[UUID] = mapped_column(
        ForeignKey("institution.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    length_weeks: Mapped[int] = mapped_column(Integer, nullable=False)


class Week(Base):
    """Week `number` of a term, so the term axis (§2.2) is data rather than arithmetic.

    Aggregate pages plot TERM 01 to 18 with one line per start cohort, and every
    join through that axis needs a row per week to join to. Uniqueness over
    `(term_id, number)` is what keeps one point per week on it.

    The rows for a term are produced by `week_rows_for_term` below. Contiguity —
    the set is exactly 1..N with no gaps — is a property of that function rather
    than a constraint, because "no gaps" is a statement about a *set* of rows and
    Postgres has no row-level constraint that can see one.
    """

    __tablename__ = "week"
    __table_args__ = (
        ForeignKeyConstraint(
            ["term_id", "term_length_weeks"],
            ["term.id", "term.length_weeks"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("term_id", "number"),
        CheckConstraint(
            "number >= 1 AND number <= term_length_weeks", name="number_is_inside_the_term"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Leads `uq_week_term_id_number`, so a lookup of a term's weeks is served
    # without an index of its own.
    term_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # The term's length, carried so the range check above is local. Set by the
    # foreign key's cascade, not by a write path — see the module docstring.
    term_length_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)


class StartLetterMap(Base):
    """What a section code's start letter means in one term: a length and a start date.

    §2.2's Fall 2026 map — 12-week U/R/Q starting 8/17, 9/7 and 9/28, 6-week
    E/F/H, and so on. Per-term, because next fall's `Q` is a different length and
    a different date, which is what `UNIQUE (term_id, letter)` allows and a
    unique `letter` alone would forbid.

    **The column is `letter`, with no `lms_` prefix.** ADR 0014's marker is for
    LMS-owned columns; this map is admin-configured Pulse-owned configuration
    (§6.3). The letter that appears *inside* a section code is LMS-owned, and
    that column is `section.lms_section_code`.
    """

    __tablename__ = "start_letter_map"
    __table_args__ = (
        ForeignKeyConstraint(
            ["term_id", "term_length_weeks"],
            ["term.id", "term.length_weeks"],
            onupdate="CASCADE",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("term_id", "letter"),
        CheckConstraint("letter ~ '^[A-Z]$'", name="letter_is_one_upper_case_letter"),
        CheckConstraint(
            "length_weeks >= 1 AND length_weeks <= term_length_weeks",
            name="length_weeks_fits_inside_the_term",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Leads `uq_start_letter_map_term_id_letter`, so a lookup of a term's whole
    # map — which is how E0-07 reads this table — is served without an index of
    # its own.
    term_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # The term's length, carried so the length check above is local.
    term_length_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    letter: Mapped[str] = mapped_column(String(1), nullable=False)
    length_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)


class SurveyWindow(Base):
    """When one section's survey opens and closes in one week of the term (§3.1).

    Both timestamps are timezone-aware and refuse a naive value: the default
    rhythm is Friday 18:00 to Sunday 23:59:59 *in the institution timezone*, and
    a value with no offset means two different moments on two differently
    configured connections.

    One window per section per week — students see exactly one open survey at a
    time per section (§3.1) — which `UNIQUE (section_id, week_id)` is.

    **Nothing here schedules anything.** E2 computes these instants; this table
    is where they land, with the constraints that make a nonsensical row
    unwritable.
    """

    __tablename__ = "survey_window"
    __table_args__ = (
        UniqueConstraint("section_id", "week_id"),
        CheckConstraint("closes_at > opens_at", name="closes_after_it_opens"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Leads `uq_survey_window_section_id_week_id`, which serves the read the
    # student and instructor surfaces make: this section's windows.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False
    )
    # Indexed, because the other read is by week — closing every window for the
    # week that has just ended (§3.4 recomputes participation after each one) —
    # and this column leads no constraint.
    week_id: Mapped[UUID] = mapped_column(
        ForeignKey("week.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    opens_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    closes_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)


# A term, however the caller is holding one. A `Term` instance is what the admin
# editor (E11) and the ORM hand around; a `RowMapping` is what a Core insert with
# `RETURNING` hands back, which is how the seed script (E0-17) creates a term.
# Both are read below without knowing which is which, because a producer that
# accepted only one of them would push a conversion onto every caller holding the
# other.
TermRow = Term | Mapping[str, Any]


def _identity_and_length(term: TermRow) -> tuple[UUID, int]:
    """A term's id and length, from an ORM instance or from a row mapping."""
    if isinstance(term, Mapping):
        return term["id"], term["length_weeks"]
    return term.id, term.length_weeks


def week_rows_for_term(term: TermRow) -> list[Week]:
    """Every `week` row a term should have: 1 to its length, contiguous, in order.

    The one producer of these rows. A term's week set is not something a caller
    should assemble itself — a gap leaves a week of the term with no row, so
    every query that walks the term axis skips it silently, and a range that
    starts at 0 or stops one short is an off-by-one nothing else would catch.

    Returns unsaved rows rather than writing them, so the caller decides the
    session, the transaction and whether this is a fresh term or a repair.
    `session.add_all(week_rows_for_term(term))` is the whole usage.

    `term_length_weeks` is set here because a new row has to state the length it
    was checked against; from then on the foreign key's cascade owns it.
    """
    term_id, length_weeks = _identity_and_length(term)
    return [
        Week(term_id=term_id, term_length_weeks=length_weeks, number=number)
        for number in range(1, length_weeks + 1)
    ]
