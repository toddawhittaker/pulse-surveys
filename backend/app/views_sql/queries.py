"""Typed ways into the read views, so no screen has to spell the SELECT (SPEC §13).

§13 puts "migrations + query helpers" in this package. What these helpers are is
typed convenience over the view SQL: each view's column list written out once, in
the order the view declares it, so a screen that needs a roster gets frozen rows
with names on them rather than a `SELECT` copied into every caller.

**What forecloses the hand-written base-table join is the database, not this
module**, and an earlier version of this docstring had it backwards. It argued
that a screen finding no helper writes `SELECT … FROM enrollment JOIN …` against
the base tables "which works, because `pulse_app` can read the view's *sources*
through the view's owner", and that "the refusal only fires when somebody reaches
for `user_identity`". Owner privileges chain through the view object and nowhere
else: a query naming a base table directly is checked against its own privileges.
Measured on this branch with `SET ROLE pulse_app` — `public.enrollment` 42501,
`public.section` 42501, `public.user_identity` 42501, `public.section_roster`
permitted. So a hand-rolled join is refused by Postgres rather than quietly
working, and identity is not the only thing it is refused. `CONTRIBUTING.md`'s
"Read paths go through `views_sql/`" states the same rule the right way round.

**`services/authz.py` is the only caller.** It imports every helper here, and
`ScopedReader.section_roster`, `ScopedReader.section_enrollment_counts` and
`ScopedReader.org_node_labels` check the purview and then pass the session
and keys straight through to them — the chokepoint is the one door these are
reached from, not a second way in beside it. One helper is unscoped on purpose:
`org_nodes_at_level`, which `authz.admin_grant_nodes` calls for the admin's
grant picker, lists every node of a level from `org_node_label`, and its one
caller is `api/admin.py` behind `require_admin` (ADR 0200, ADR 0205).

**These return plain frozen rows, not ORM entities, and deliberately.** A view is
not on `Base.metadata` (E0-10: views ship "as Alembic migrations under
`views_sql/`, not as ORM constructs"), so there is no mapped class to hand back,
and there should not be one: a mapped view invites a write path into a relation
that cannot take one, and makes `alembic check` compare a table that is not one.

**Nothing here filters by who is asking.** Scoping a read to an actor's purview
is `services/authz.py`'s single chokepoint, which is E0-11's, and a second
half-answer to the same question living here is how the two come apart. These
helpers take the keys they are given.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

__all__ = [
    "OrgNodeChoice",
    "OrgNodeLabel",
    "SectionEnrollmentCount",
    "SectionRosterRow",
    "org_node_labels_above",
    "org_nodes_at_level",
    "section_enrollment_counts",
    "section_roster",
]

# The view columns, spelled once. Ordered as the view declares them, so a reader
# comparing this against `section_roster_v001.sql` is comparing two lists in the
# same order rather than looking each one up.
_SECTION_ROSTER = text(
    "SELECT enrollment_id, user_id, section_id, started_on, ended_on,"
    " course_id, term_id, lms_section_code, length_weeks,"
    " section_start_date, section_end_date"
    " FROM public.section_roster"
    " WHERE section_id = :section_id"
    " ORDER BY started_on, enrollment_id"
)

_SECTION_ENROLLMENT_COUNTS = text(
    "SELECT section_id, course_id, term_id, lms_section_code, enrolled_count"
    " FROM public.section_enrollment_count"
    " WHERE course_id = :course_id"
    " ORDER BY lms_section_code"
)

# Every org node above a set of sections, read upward from each section's course
# through `parent_id`. `UNION` rather than `UNION ALL`, so a node above several
# of the sections is answered once and the walk stops at the institution.
_ORG_NODE_LABELS_ABOVE = text(
    "WITH RECURSIVE above AS ("
    " SELECT label.level, label.node_id, label.name, label.parent_id"
    " FROM public.org_node_label AS label"
    " JOIN public.section AS held ON held.course_id = label.node_id"
    " WHERE label.level = 'course' AND held.id = ANY(CAST(:section_ids AS uuid[]))"
    " UNION"
    " SELECT label.level, label.node_id, label.name, label.parent_id"
    " FROM public.org_node_label AS label"
    " JOIN above ON label.node_id = above.parent_id"
    ")"
    " SELECT level, node_id, name, parent_id FROM above"
)

# Every node of one level with its parent's name, for the admin's grant picker.
# The parent is read from the same view, so no table is named here. The institution
# has no parent, hence the outer join.
_ORG_NODES_AT_LEVEL = text(
    "SELECT label.level, label.node_id, label.name, parent.name AS parent_name"
    " FROM public.org_node_label AS label"
    " LEFT JOIN public.org_node_label AS parent ON parent.node_id = label.parent_id"
    " WHERE label.level = :level"
    " ORDER BY label.name, parent.name, label.node_id"
)


@dataclass(frozen=True, slots=True)
class SectionRosterRow:
    """One person's membership of one section, by key.

    No name and no email address, because `public.section_roster` selects
    neither — and the view's own column list is the whole of why. A view is read
    with its owner's privileges, so a view that *did* select an identity column
    would hand it to `pulse_app` without its empty grant on
    `public.user_identity` ever being consulted (§4, §8). What keeps that from
    happening is the structural sweep in
    `tests/integration/test_identity_column_marker.py`, not this connection.
    """

    enrollment_id: UUID
    user_id: UUID
    section_id: UUID
    started_on: date
    ended_on: date | None
    course_id: UUID
    term_id: UUID
    lms_section_code: str
    length_weeks: int
    section_start_date: date
    section_end_date: date


@dataclass(frozen=True, slots=True)
class SectionEnrollmentCount:
    """How many people one section holds."""

    section_id: UUID
    course_id: UUID
    term_id: UUID
    lms_section_code: str
    enrolled_count: int


@dataclass(frozen=True, slots=True)
class OrgNodeLabel:
    """One org node's display name and the node it sits in (`org_node_label_v001.sql`).

    `level` is one of institution, college, department, prefix and course;
    `parent_id` is None for the institution and only for it.
    """

    level: str
    node_id: UUID
    name: str
    parent_id: UUID | None


def org_node_labels_above(
    session: Session, *, section_ids: Sequence[UUID]
) -> Sequence[OrgNodeLabel]:
    """The course, prefix, department, college and institution above each section, once each."""
    rows = session.execute(_ORG_NODE_LABELS_ABOVE, {"section_ids": list(section_ids)}).mappings()
    return [OrgNodeLabel(**row) for row in rows]


def section_roster(session: Session, *, section_id: UUID) -> Sequence[SectionRosterRow]:
    """Everybody enrolled in `section_id`, oldest enrollment first."""
    rows = session.execute(_SECTION_ROSTER, {"section_id": section_id}).mappings()
    return [SectionRosterRow(**row) for row in rows]


def section_enrollment_counts(
    session: Session, *, course_id: UUID
) -> Sequence[SectionEnrollmentCount]:
    """One count per section of `course_id`, including the sections holding nobody."""
    rows = session.execute(_SECTION_ENROLLMENT_COUNTS, {"course_id": course_id}).mappings()
    return [SectionEnrollmentCount(**row) for row in rows]


@dataclass(frozen=True, slots=True)
class OrgNodeChoice:
    """One org node an admin may grant a role at, and its parent's name if it has a parent."""

    level: str
    node_id: UUID
    name: str
    parent_name: str | None


def org_nodes_at_level(session: Session, *, level: str) -> Sequence[OrgNodeChoice]:
    """Every org node of `level`, named, by name. Nothing here checks who is asking."""
    rows = session.execute(_ORG_NODES_AT_LEVEL, {"level": level}).mappings()
    return [OrgNodeChoice(**row) for row in rows]
