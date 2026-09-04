"""The academic calendar: terms, their weeks, the start-letter map, and survey windows.

SPEC §2.2, §3.1, §6.3 and §8. The calendar is institution *configuration* rather
than code — an admin sets a term's length and the letters that start inside it
(§6.3) — so it is data with constraints, and everything derived from it (a
section's length, start and end dates) is E0-07's arithmetic over these rows.

**Three rules here compare a row against its term, and none is a plain CHECK.**
A week number has to fit inside its own term's length, a start letter's length
may not exceed it, and a survey window's section and its week have to belong to
the same term. A `CHECK` constraint cannot read another table, so all three are
enforced by a composite foreign key that carries the term's own value alongside
an id — `(term_id, term_length_weeks)` referencing `term (id, length_weeks)` for
the first two, and `(section_id, term_id)` and `(week_id, term_id)` referencing
`section (id, term_id)` and `week (id, term_id)` for the third — which turns
each rule into a local comparison the server checks like any other.
[ADR 0018](../../../docs/adr/0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)
records why that and not a trigger; the short version is that a trigger commits a
violating row when a term is shortened concurrently, and this does not.

`term_length_weeks` is therefore **not a column anyone sets on purpose**. It is a
copy the foreign key keeps in step: `ON UPDATE CASCADE` rewrites it when the term
changes, and the local CHECK then refuses the change if some row no longer fits.
A row that misstates it is refused by the foreign key rather than stored.

**Editing a term's length is guarded in one direction only, and this is the
paragraph that has to say so**, because whoever edits one — E11's configuration
surface (§6.3) — does it through `term` and never calls the producer at the
bottom of this module. *Shortening* is refused, loudly and by name: the cascade
rewrites the copies, the local CHECK re-evaluates, and the edit fails while any
week sits past the new end. *Lengthening* is accepted and silent. Nothing creates
the weeks the term has just grown, so an 18-week term goes on holding twelve week
rows — each one internally consistent, since the cascade rewrote it — and only a
count against `length_weeks` shows the gap. E0-06 ships no reconciler and
`week_rows_for_term` cannot be one; ADR 0018's consequences carry the whole of it
and route it to E2 and E11.

**Timestamps are timezone-aware and refuse a naive value** (§3.1: a window opens
Friday 18:00 and closes Sunday 23:59:59 in the institution timezone). Postgres
does not refuse a naive datetime on its own — it reads one in the session's
`TimeZone` and stores whatever instant that names — so the guard sits on the
column type, `AwareDateTime` in `app.models.base`, where every writer meets it
([ADR 0019](../../../docs/adr/0019-a-naive-datetime-is-refused-by-the-column-type.md)).

**Where the institution timezone itself lives.** In `app.config.Settings`, as
`INSTITUTION_TIMEZONE`, which is E0-05's decision recorded in `Institution`'s
docstring. So a term's "institution timezone reference" is `institution_id`: the
term names the institution, and the institution's timezone is configuration. A
per-term timezone column would be a second place for one value to live.

**Not here, on purpose.** Windows are not scheduled here — `survey_window` carries
the columns and the constraints, and the logic that fills them is
`app.services.survey_windows` (E2-06). A week carries no dates: nothing needs them
yet, and the section-date arithmetic that might is E0-07's, over
`start_letter_map`. The Fall 2026 seed map (§2.2) is fixture and seed data
(E0-17), never rows in a migration.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AwareDateTime, Base, UuidPrimaryKey


class Term(UuidPrimaryKey, Base):
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


class Week(UuidPrimaryKey, Base):
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
        # Looks redundant beside the primary key and is not, for exactly the
        # reason `term`'s `UNIQUE (id, length_weeks)` above is not: a foreign key
        # must reference a unique constraint, and this is what lets
        # `survey_window` carry `(week_id, term_id)` as one reference and so
        # agree with its section about the term. Dropping it drops that rule.
        UniqueConstraint("id", "term_id"),
        CheckConstraint(
            "number >= 1 AND number <= term_length_weeks", name="number_is_inside_the_term"
        ),
    )

    # Leads `uq_week_term_id_number`, so a lookup of a term's weeks is served
    # without an index of its own.
    term_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # The term's length, carried so the range check above is local. Set by the
    # foreign key's cascade, not by a write path — see the module docstring.
    term_length_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)


class StartLetterMap(UuidPrimaryKey, Base):
    """What a section code's start letter means in one term: a length and a start date.

    §2.2's Fall 2026 map — 12-week U/R/Q starting 8/17, 9/7 and 9/28, 6-week
    E/F/H, and so on. Per-term, because next fall's `Q` is a different length and
    a different date, which is what `UNIQUE (term_id, letter)` allows and a
    unique `letter` alone would forbid.

    **The column is `letter`, with no `lms_` prefix.** ADR 0014's marker is for
    LMS-owned columns; this map is admin-configured Pulse-owned configuration
    (§6.3). The letter that appears *inside* a section code is LMS-owned, and
    that column is `section.lms_section_code`.

    **A start position is one character, and it is not always a letter.** §2.2
    numbers the 3-week sections 2 through 7 while every other length is
    lettered, so six of the twenty positions in the Fall 2026 seed map are
    digits. E0-06 shipped this check as `^[A-Z]$`, which refuses all six; E0-07
    widened it to `^[A-Z0-9]$` when it built the parser that reads them. The
    constraint is deliberately not narrowed to `^[A-Z2-7]$`: which positions a
    term uses is admin configuration, and 2 through 7 is what §2.2's *Fall 2026
    seed* uses, not a rule about every term. What makes a position legal is a
    row here, which is why `1` and `8` are refused by the derivation finding no
    row rather than by a range check that would have to be kept in step with
    someone's calendar. The column keeps the name `letter`: it is what E0-06's
    ticket spells, and §2.2 calls the thing a start letter throughout.
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
        CheckConstraint("letter ~ '^[A-Z0-9]$'", name="letter_is_one_start_position"),
        CheckConstraint(
            "length_weeks >= 1 AND length_weeks <= term_length_weeks",
            name="length_weeks_fits_inside_the_term",
        ),
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


class SurveyWindow(UuidPrimaryKey, Base):
    """When one section's survey opens and closes in one week of the term (§3.1).

    Both timestamps are timezone-aware and refuse a naive value: the default
    rhythm is Friday 18:00 to Sunday 23:59:59 *in the institution timezone*, and
    a value with no offset means two different moments on two differently
    configured connections.

    One window per section per week, which is what `UNIQUE (section_id, week_id)`
    says and the whole of what it says. §3.1's stronger rule — a student sees
    exactly one open survey at a time per section — also needs the windows not to
    overlap in time, which no constraint here expresses; that falls to
    `app.services.survey_windows` (E2-06), the only thing that sets these two
    columns, where consecutive Friday-to-Sunday spans cannot overlap by
    construction and
    `tests/integration/test_at_most_one_survey_window_is_open_at_a_time.py`
    asserts it rather than assuming it.

    **The section and the week belong to the same term, and the server refuses a
    window where they do not.** ADR 0018 named this as the rule this table had
    available and did not take, and E2-05 takes it: the window states its own
    `term_id`, and each of the two references is a composite foreign key carrying
    that term — `(section_id, term_id)` into `section (id, term_id)` and
    `(week_id, term_id)` into `week (id, term_id)`. A window pairing a section in
    one term with a week in another finds no matching row on one limb or the
    other. Without it a window opens a section's survey against a week its own
    calendar does not contain, and §3.4's participation denominator — the items of
    every week the student was enrolled for — is counted over two different
    calendars.

    **`term_id` is NOT NULL, and that is what makes both limbs bite.** Postgres
    evaluates a composite foreign key under `MATCH SIMPLE`, which skips the check
    entirely when any column of the key is null — so a nullable term column would
    be a documented way to store the very row this refuses. The table was empty in
    every environment when E2-05 added the column, so it arrived with no backfill
    and no server default — E2-06 is what began writing these rows, and a seeded
    development stack has carried them since.

    **No `ON UPDATE` action on either limb.** A section or a week whose term is
    edited under an open window is a change to be refused rather than followed:
    the window's instants were computed from the term's calendar, and cascading
    the new term into the window would keep the row valid while making it wrong.
    That is the opposite of the `ON UPDATE CASCADE` on `week` and
    `start_letter_map` above, where the carried value is a copy of the term's
    length that nobody sets on purpose.

    **Nothing here schedules anything.** `app.services.survey_windows` computes
    these instants from the section's calendar and §3.1's rhythm (E2-06); this
    table is where they land, with the constraints that make a nonsensical row
    unwritable.
    """

    __tablename__ = "survey_window"
    __table_args__ = (
        ForeignKeyConstraint(
            ["section_id", "term_id"],
            ["section.id", "section.term_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["week_id", "term_id"],
            ["week.id", "week.term_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("section_id", "week_id"),
        CheckConstraint("closes_at > opens_at", name="closes_after_it_opens"),
    )

    # Leads `uq_survey_window_section_id_week_id`, which serves the read the
    # student and instructor surfaces make: this section's windows.
    section_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    # Indexed for the read this anticipates: every window of the week that has
    # just ended, which is what SPEC §3.4's "recomputed after each week closes"
    # will ask for. **E3 is where that read is built; nothing in the tree makes it
    # today** (E2-16 item 6, which keeps the index and corrects the tense this
    # comment used to claim). The column leads no constraint, so nothing else
    # would serve it.
    week_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    # The term both of the above have to agree on. Carried rather than derived,
    # because a `CHECK` cannot read another table — which is the whole of ADR
    # 0018. Not indexed on its own: no read starts from a term here, and the two
    # composite foreign keys each index nothing by themselves.
    term_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    opens_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
    closes_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)


# A term, however the caller is holding one. A `Term` instance is what the admin
# editor (E11) and the ORM hand around; a `RowMapping` is what a Core insert with
# `RETURNING` hands back, which is how the seed script (E0-17) creates a term.
# Both are read below without knowing which is which, because a producer that
# accepted only one of them would push a conversion onto every caller holding the
# other.
TermRow = Term | Mapping[str, Any]


def term_value(term: TermRow, name: str) -> Any:
    """One field of a term, whichever of the two shapes the caller is holding.

    The whole of the `Mapping`-or-attribute dispatch, in one place. Every reader
    of a `TermRow` needs it and each used to make the same `isinstance` check
    itself — here and in `app.services.section_codes` — which is the shape
    `docs/MISTAKES.md` entry 13 describes: one quirk of a type, worked around
    separately everywhere it is met.

    Here rather than in the service because `section_codes` already imports from
    this module and the dependency runs that way only. A term's *shapes* are a
    fact about the model, and this is the model.

    `name` is a field of `Term` in every call, and a wrong one raises — `KeyError`
    from the mapping, `AttributeError` from the instance — rather than returning
    `None`. That difference is deliberate: a silent `None` here would be a term
    date or a term length that reads as "not set".
    """
    if isinstance(term, Mapping):
        return term[name]
    return getattr(term, name)


def _identity_and_length(term: TermRow) -> tuple[UUID, int]:
    """A term's id and length, from an ORM instance or from a row mapping."""
    return term_value(term, "id"), term_value(term, "length_weeks")


def week_rows_for_term(term: TermRow) -> list[Week]:
    """Every `week` row a term should have: 1 to its length, contiguous, in order.

    The one producer of these rows. A term's week set is not something a caller
    should assemble itself — a gap leaves a week of the term with no row, so
    every query that walks the term axis skips it silently, and a range that
    starts at 0 or stops one short is an off-by-one nothing else would catch.

    Returns unsaved rows rather than writing them, so the caller owns the session
    and the transaction. `session.add_all(week_rows_for_term(term))` is the whole
    usage.

    **For a term that has no weeks yet.** The result always starts at 1, so
    adding it to a term that already has week rows is refused by
    `uq_week_term_id_number` on the first number that exists — measured, and it
    is week 1 that reports it. No argument changes that: this function is handed
    a term and nothing else, so it cannot see what is already in the table.

    **Changing a term's length afterwards leaves this table behind, and nothing
    complains.** Measured: lengthening a 12-week term to 18 is accepted, and the
    foreign key cascades so every existing row now says `term_length_weeks = 18`.
    Each row looks right; only a count shows the term is six weeks short of
    itself. Shortening is the loud direction — the same cascade drives the local
    CHECK, so the edit is refused while a week sits past the new end
    ([ADR 0018](../../../docs/adr/0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)).

    **Nothing in E0-06 reconciles that, and this is not the place to fix it.**
    Emitting only the missing weeks means seeing the rows that exist, which means
    a session; and the questions an edit raises — whether shortening deletes the
    weeks past the new end, and what becomes of a `survey_window` keyed to one —
    are scheduling and admin policy. They belong to E2 and to E11's calendar
    editor (§6.3), which is where a term's length gets edited in the first place.
    Whoever builds that owns the reconciliation, and owns the assertion this
    function cannot make: that a term's weeks are 1..N *after* an edit, not only
    at creation.

    `term_length_weeks` is set here because a new row has to state the length it
    was checked against; from then on the foreign key's cascade owns it.
    """
    term_id, length_weeks = _identity_and_length(term)
    return [
        Week(term_id=term_id, term_length_weeks=length_weeks, number=number)
        for number in range(1, length_weeks + 1)
    ]
