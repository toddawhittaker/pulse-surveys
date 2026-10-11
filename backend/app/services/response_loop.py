"""The response loop (SPEC §5.3): who a section's staff are, by name, for a reader of it.

E7-01 builds the first piece: the one Python door to the staff-name definer,
`public.section_staff_names` (`views_sql/section_staff_names_v001.sql`, ADR 0191).
SPEC §5.3 posts a response under its author's name, and the survey page names the
section's professor, so a student has to be able to read a member of staff's
name, and `pulse_app` holds no privilege on `person`. The definer answers one
section's live teaching instructors and anyone who has published a response to
it, and only to a reader of that section. Every reader check is inside it.

**This module is the only one under `backend/app/` that names the definer**
(`tests/unit/test_only_the_response_loop_service_names_the_staff_name_definer.py`).
The definer trusts the reader key it is handed, so the one thing a caller must
get right is to pass the reader of its own session — the student's `user` key
or the member of staff's `person` key — and never a key taken from a request. A
second caller would be a second place that could get it wrong.

**A refusal is an empty list**, the same answer a section with no instructor
gives, and nothing here logs what it was asked or what it answered: no refusal
may carry a staff name (E7-01, done-when 4), and a log line of an answer is one.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

__all__ = ["StaffName", "section_staff_names"]

# The parameters are cast rather than written with `::`, because SQLAlchemy's
# `text()` stops reading a bind parameter at a colon, and an uncast null is
# untyped.
_SECTION_STAFF_NAMES = text(
    "SELECT person_id, display_name FROM public.section_staff_names("
    "CAST(:section_id AS uuid), CAST(:reader_user_id AS uuid), "
    "CAST(:reader_person_id AS uuid))"
)


@dataclass(frozen=True)
class StaffName:
    """One member of staff the definer answered: their `person` key and their name."""

    person_id: UUID
    display_name: str


def section_staff_names(
    session: Session,
    *,
    section_id: UUID,
    reader_user_id: UUID | None = None,
    reader_person_id: UUID | None = None,
) -> list[StaffName]:
    """The staff names one reader may read for one section; empty for any other reader.

    Name the reader by exactly one key: a student by `reader_user_id` (a
    launched student has no `person`, ADR 0028), a member of staff by
    `reader_person_id`. Passing neither or both is a caller's mistake and raises
    `ValueError` here, rather than reaching the definer, which would answer it
    with nothing.

    Answered in the definer's order, by name and then by key.
    """
    if (reader_user_id is None) == (reader_person_id is None):
        raise ValueError(
            "section_staff_names takes exactly one reader key: reader_user_id for a student, "
            "reader_person_id for a member of staff."
        )
    rows = session.execute(
        _SECTION_STAFF_NAMES,
        {
            "section_id": str(section_id),
            "reader_user_id": None if reader_user_id is None else str(reader_user_id),
            "reader_person_id": None if reader_person_id is None else str(reader_person_id),
        },
    ).all()
    return [StaffName(person_id=row.person_id, display_name=row.display_name) for row in rows]
