"""The leadership roll-ups (SPEC §5.5): the tree over a leader's purview, and one node's figures.

Two reads, each for one leadership reader whose `ActorScope` came from
`app.api.deps.leadership_scope` and from nothing else (ADR 0199):

  - **`rollup_tree`**: the whole tree over the reader's purview in one term, in
    one payload (ADR 0205). The hierarchy view for everyone, with SPEC §2.1's
    roots and labels, and the by-lead pivot for a reader holding `CHAIR` or
    higher.
  - **`rollup_figures`**: one node's own figures, a line per start cohort on the
    term axis (§2.2), each cohort's participation, and §5.6's attention cards.

**What a reader holds is the purview's sections in the viewed term, and every
node and count is derived from those sections.** A container is in the tree
because a held section sits under it, and its counts are of held sections and
of the courses, prefixes and departments those sections sit in. So a department
reached through one cross-department led course counts that course's sections
and one prefix, never the department's size. Nothing here counts by containment
from a node id: ADR 0046 gives a lead's grant no prefix ids, and a count by
containment would answer the department's whole size.

**Names come through the staff-name door, once per payload**
(`response_loop.section_staff_names`, ADR 0201), passed the reader's scope so
only purview sections reach the definer.

**Order never follows a figure** (§4.1 item 4, E9 decision 13). Tree children
sort by name, sections by code, cohorts by start date, cards by course name,
section code and rule.

**No comment, summary or theme reaches either payload** (SPEC §5.5, settled at
the E9 breakdown): the reads below never touch the comment or summary tables.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.copy import leadership_rollup as words
from app.models.identity import AssignmentRole
from app.models.org import Section
from app.models.survey import REPORT_STREAMS
from app.models.term import SurveyWindow, Term, Week
from app.schemas.rollup import (
    AttentionCard,
    AttentionRule,
    FiguresKind,
    NodeKind,
    RollupCohort,
    RollupFigures,
    RollupNode,
    RollupParticipation,
    RollupTree,
    RollupWeek,
)
from app.services import clock, reporting
from app.services.authz import ActorScope, LeadershipGrant, OrgNodeLabel, scoped_reader
from app.services.benchmarks import node_series
from app.services.comparison_sets import TermUnavailableError
from app.services.response_loop import (
    StaffName,
    StaffNameRole,
    owed_section_weeks,
    section_staff_names,
)
from app.services.section_codes import course_week_of, parse_section_code

__all__ = [
    "NodeUnavailableError",
    "TermUnavailableError",
    "attention_cards",
    "build_hierarchy",
    "rollup_figures",
    "rollup_tree",
]


class NodeUnavailableError(Exception):
    """No node of this kind and id holds a section of the reader's purview in the term.

    One error for a node outside the purview and a node that does not exist, so
    the route answers the two identically.
    """


# The roles that are offered the by-lead pivot (SPEC §2.1: "Chair and above").
# Decided from the roles held, never from the purview's size.
_BY_LEAD_ROLES = frozenset(
    {
        AssignmentRole.CHAIR,
        AssignmentRole.ASSISTANT_DEAN,
        AssignmentRole.DEAN,
        AssignmentRole.VP_ACADEMICS,
    }
)

# The tree's levels, outermost first, below the institution.
_LEVELS: tuple[NodeKind, ...] = ("college", "department", "prefix", "course", "section")

# §5.6's rate rule: a rate strictly under this is a card; exactly 40% is not.
_LOW_RESPONSE_RATE = 0.4

# The order cards of one section are listed in: §5.6's own numbering.
_RULE_ORDER: tuple[AttentionRule, ...] = (
    "instructor_trend_down",
    "course_trend_down",
    "response_rate_low",
    "response_owed",
)

_RULE_NAMES: Mapping[AttentionRule, str] = {
    "instructor_trend_down": words.INSTRUCTOR_TREND_DOWN.text,
    "course_trend_down": words.COURSE_TREND_DOWN.text,
    "response_rate_low": words.RESPONSE_RATE_LOW.text,
    "response_owed": words.RESPONSE_OWED.text,
}


# ---------------------------------------------------------------------------
# What the reader holds.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HeldSection:
    """One section of the reader's purview in the viewed term, with its containment path."""

    section_id: UUID
    code: str
    start_date: date
    course_id: UUID
    course_name: str
    prefix_id: UUID
    prefix_code: str
    department_id: UUID
    department_name: str
    college_id: UUID
    college_name: str

    def node(self, level: NodeKind) -> tuple[UUID, str]:
        """This section's node at one containment level: its id and its name."""
        return {
            "college": (self.college_id, self.college_name),
            "department": (self.department_id, self.department_name),
            "prefix": (self.prefix_id, self.prefix_code),
            "course": (self.course_id, self.course_name),
            "section": (self.section_id, self.code),
        }[level]


@dataclass(frozen=True, slots=True)
class SectionStaff:
    """The names the staff-name door answered for one section."""

    instructors: tuple[str, ...] = ()
    lead: tuple[UUID, str] | None = None
    chair: str | None = None
    dean: str | None = None


def _held_sections(session: Session, *, scope: ActorScope, term_id: UUID) -> list[HeldSection]:
    """The purview's sections in the term, each with its path and its nodes' names.

    Two reads: the sections themselves, then every node above them through the
    org-node label view (ADR 0205), reached through `ScopedReader` because
    `pulse_app` holds nothing on `college` or `department`. Every name on the
    tree comes from that view, so a course is named the way the view names it.
    """
    held = scope.purview.section_ids
    if not held:
        return []
    rows = session.execute(
        select(Section.id, Section.lms_section_code, Section.start_date, Section.course_id).where(
            Section.id.in_(sorted(held)), Section.term_id == term_id
        )
    ).all()
    if not rows:
        return []
    labels = {
        label.node_id: label
        for label in scoped_reader(session, scope).org_node_labels(
            section_ids=[row[0] for row in rows]
        )
    }

    def above(node: OrgNodeLabel) -> OrgNodeLabel:
        if node.parent_id is None:
            raise LookupError(f"The {node.level} {node.node_id} sits in no org node.")
        return labels[node.parent_id]

    sections = []
    for section_id, code, start_date, course_id in rows:
        course = labels[course_id]
        prefix = above(course)
        department = above(prefix)
        college = above(department)
        sections.append(
            HeldSection(
                section_id=section_id,
                code=code,
                start_date=start_date,
                course_id=course.node_id,
                course_name=course.name,
                prefix_id=prefix.node_id,
                prefix_code=prefix.name,
                department_id=department.node_id,
                department_name=department.name,
                college_id=college.node_id,
                college_name=college.name,
            )
        )
    return sections


def _staff_of(
    session: Session, *, scope: ActorScope, held: Sequence[HeldSection], settings: Settings
) -> dict[UUID, SectionStaff]:
    """Every held section's staff names, through the door in one call."""
    named: dict[UUID, list[StaffName]] = defaultdict(list)
    for row in section_staff_names(
        session,
        section_ids=[section.section_id for section in held],
        reader_person_id=scope.person_id,
        scope=scope,
        settings=settings,
    ):
        named[row.section_id].append(row)
    staff: dict[UUID, SectionStaff] = {}
    for section_id, rows in named.items():
        leads = sorted(
            (row.display_name, row.person_id)
            for row in rows
            if row.role is StaffNameRole.LEAD_FACULTY
        )
        staff[section_id] = SectionStaff(
            instructors=tuple(
                sorted(row.display_name for row in rows if row.role is StaffNameRole.INSTRUCTOR)
            ),
            lead=(leads[0][1], leads[0][0]) if leads else None,
            chair=min(
                (row.display_name for row in rows if row.role is StaffNameRole.CHAIR), default=None
            ),
            dean=min(
                (row.display_name for row in rows if row.role is StaffNameRole.DEAN), default=None
            ),
        )
    return staff


def offers_by_lead(scope: ActorScope) -> bool:
    """Whether the reader holds a `CHAIR` or higher assignment (SPEC §2.1, §5.5)."""
    return any(grant.role in _BY_LEAD_ROLES for grant in scope.grants)


def _grant_root(grant: LeadershipGrant, section: HeldSection) -> NodeKind:
    """Where one grant roots the tree for one of its sections (SPEC §2.1).

    VP at colleges, dean at departments, chair and lead at prefixes. An
    assistant dean's grant holds whole departments (each supervised chair's) and
    led courses: a section in a held department roots at the department, any
    other at its prefix.
    """
    if grant.role is AssignmentRole.VP_ACADEMICS:
        return "college"
    if grant.role is AssignmentRole.DEAN:
        return "department"
    if grant.role is AssignmentRole.ASSISTANT_DEAN:
        held_whole = section.department_id in grant.purview.department_ids
        return "department" if held_whole else "prefix"
    return "prefix"


def root_levels(scope: ActorScope, held: Sequence[HeldSection]) -> dict[UUID, NodeKind]:
    """Each held section's root level: the outermost any of the reader's grants gives it."""
    levels: dict[UUID, NodeKind] = {}
    for section in held:
        found = [
            _grant_root(grant, section)
            for grant in scope.grants
            if section.section_id in grant.purview.section_ids
        ]
        levels[section.section_id] = min(found, key=_LEVELS.index) if found else "prefix"
    return levels


# ---------------------------------------------------------------------------
# The tree.
# ---------------------------------------------------------------------------


def _count(number: int, one: words.CopyEntry, many: words.CopyEntry) -> str:
    return one.text if number == 1 else many.text.format(count=number)


def _joined(*parts: str | None) -> str:
    return words.LABEL_SEPARATOR.text.join(part for part in parts if part)


def _ordered(nodes: list[RollupNode]) -> list[RollupNode]:
    """Siblings by name, then key: a label and never a figure."""
    return sorted(nodes, key=lambda node: (node.name, str(node.id)))


def _one_name(names: set[str]) -> str | None:
    return min(names) if names else None


def _node(
    level: NodeKind,
    sections: Sequence[HeldSection],
    *,
    staff: Mapping[UUID, SectionStaff],
    reader: UUID,
) -> RollupNode:
    """One node over the held sections under it, with its children."""
    node_id, name = sections[0].node(level)
    section_count = len({section.section_id for section in sections})
    sections_text = _count(section_count, words.ONE_SECTION, words.SECTIONS)
    children = _children(level, sections, staff=staff, reader=reader)
    if level == "college":
        departments = len({section.department_id for section in sections})
        dean = _one_name(
            {s.dean for s in (staff.get(x.section_id) for x in sections) if s and s.dean}
        )
        return RollupNode(
            kind=level,
            id=node_id,
            name=name,
            label=_joined(
                _count(departments, words.ONE_DEPARTMENT, words.DEPARTMENTS),
                sections_text,
                None if dean is None else words.DEAN.text.format(name=dean),
            ),
            section_count=section_count,
            department_count=departments,
            staff_name=dean,
            children=children,
        )
    if level == "department":
        prefixes = len({section.prefix_id for section in sections})
        chair = _one_name(
            {s.chair for s in (staff.get(x.section_id) for x in sections) if s and s.chair}
        )
        return RollupNode(
            kind=level,
            id=node_id,
            name=name,
            label=_joined(
                _count(prefixes, words.ONE_PREFIX, words.PREFIXES),
                sections_text,
                None if chair is None else words.CHAIR.text.format(name=chair),
            ),
            section_count=section_count,
            prefix_count=prefixes,
            staff_name=chair,
            children=children,
        )
    if level == "prefix":
        courses = len({section.course_id for section in sections})
        return RollupNode(
            kind=level,
            id=node_id,
            name=name,
            label=_joined(_count(courses, words.ONE_COURSE, words.COURSES), sections_text),
            section_count=section_count,
            course_count=courses,
            children=children,
        )
    if level == "course":
        lead = _course_lead(sections, staff=staff, reader=reader)
        return RollupNode(
            kind=level,
            id=node_id,
            name=name,
            label=_joined(
                sections_text, None if lead is None else words.LEAD.text.format(name=lead)
            ),
            section_count=section_count,
            staff_name=lead,
            children=children,
        )
    found = staff.get(node_id)
    instructors = list(found.instructors) if found else []
    return RollupNode(
        kind=level,
        id=node_id,
        name=name,
        label=_joined(name, *instructors),
        section_count=1,
        instructor_names=instructors,
    )


def _course_lead(
    sections: Sequence[HeldSection], *, staff: Mapping[UUID, SectionStaff], reader: UUID
) -> str | None:
    """A course's lead's name, or none in the lead's own view (SPEC §2.1)."""
    leads = {
        found.lead
        for found in (staff.get(section.section_id) for section in sections)
        if found is not None and found.lead is not None
    }
    if not leads:
        return None
    person, name = min(leads, key=lambda lead: (lead[1], str(lead[0])))
    return None if person == reader else name


def _children(
    level: NodeKind,
    sections: Sequence[HeldSection],
    *,
    staff: Mapping[UUID, SectionStaff],
    reader: UUID,
) -> list[RollupNode]:
    if level == "section":
        return []
    below = _LEVELS[_LEVELS.index(level) + 1]
    groups: dict[UUID, list[HeldSection]] = defaultdict(list)
    for section in sections:
        groups[section.node(below)[0]].append(section)
    return _ordered([_node(below, group, staff=staff, reader=reader) for group in groups.values()])


def build_hierarchy(
    held: Sequence[HeldSection],
    *,
    roots: Mapping[UUID, NodeKind],
    staff: Mapping[UUID, SectionStaff],
    reader: UUID,
) -> list[RollupNode]:
    """The hierarchy view: the roots, each with the held sections beneath it.

    A root is the node at a section's root level. A root under another root is
    not one: its sections hang under the outer root, so a union of a chair's
    prefixes and a dean's departments shows each section once.
    """
    root_keys = {
        (roots[section.section_id], section.node(roots[section.section_id])[0]) for section in held
    }
    groups: dict[tuple[NodeKind, UUID], list[HeldSection]] = defaultdict(list)
    for section in held:
        level = next(level for level in _LEVELS if (level, section.node(level)[0]) in root_keys)
        groups[(level, section.node(level)[0])].append(section)
    return _ordered(
        [_node(level, group, staff=staff, reader=reader) for (level, _), group in groups.items()]
    )


def _lead_group_of(
    section: HeldSection, staff: Mapping[UUID, SectionStaff]
) -> tuple[NodeKind, UUID]:
    """A section's by-lead group: its course's lead, or its department if nobody leads it."""
    found = staff.get(section.section_id)
    if found is not None and found.lead is not None:
        return ("lead", found.lead[0])
    return ("no_lead", section.department_id)


def build_by_lead(
    held: Sequence[HeldSection], *, staff: Mapping[UUID, SectionStaff], reader: UUID
) -> list[RollupNode]:
    """The by-lead pivot: the purview's courses under their lead, and unled ones under the chair."""
    groups: dict[tuple[NodeKind, UUID], list[HeldSection]] = defaultdict(list)
    for section in held:
        groups[_lead_group_of(section, staff)].append(section)
    nodes = []
    for (kind, group_id), sections in groups.items():
        courses = len({section.course_id for section in sections})
        section_count = len(sections)
        counts = (
            _count(courses, words.ONE_COURSE, words.COURSES),
            _count(section_count, words.ONE_SECTION, words.SECTIONS),
        )
        children = _children("prefix", sections, staff=staff, reader=reader)
        if kind == "lead":
            lead = staff[sections[0].section_id].lead or (group_id, "")
            nodes.append(
                RollupNode(
                    kind=kind,
                    id=group_id,
                    name=lead[1],
                    label=_joined(*counts),
                    section_count=section_count,
                    course_count=courses,
                    staff_name=lead[1],
                    children=children,
                )
            )
        else:
            chair = _one_name(
                {s.chair for s in (staff.get(x.section_id) for x in sections) if s and s.chair}
            )
            nodes.append(
                RollupNode(
                    kind=kind,
                    id=group_id,
                    name=words.NO_LEAD_GROUP.text.format(department=sections[0].department_name),
                    label=_joined(
                        *counts, None if chair is None else words.CHAIR.text.format(name=chair)
                    ),
                    section_count=section_count,
                    course_count=courses,
                    staff_name=chair,
                    children=children,
                )
            )
    return _ordered(nodes)


def rollup_tree(
    session: Session, *, scope: ActorScope, term_id: UUID, settings: Settings
) -> RollupTree:
    """The whole tree over the reader's purview in one term (SPEC §2.1, §5.5).

    Raises `TermUnavailableError` for a term id no term carries. A reader whose
    purview holds no section in the term gets an empty tree.
    """
    if session.get(Term, term_id) is None:
        raise TermUnavailableError
    held = _held_sections(session, scope=scope, term_id=term_id)
    staff = _staff_of(session, scope=scope, held=held, settings=settings)
    return RollupTree(
        term_id=term_id,
        hierarchy=build_hierarchy(
            held, roots=root_levels(scope, held), staff=staff, reader=scope.person_id
        ),
        by_lead=build_by_lead(held, staff=staff, reader=scope.person_id)
        if offers_by_lead(scope)
        else None,
    )


# ---------------------------------------------------------------------------
# One node's figures.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SectionWeekFigures:
    """What §5.6's rules read about one section: its published weeks and their facts.

    `means` is keyed by (stream, course week); `responses` and `enrolled` are
    the latest published week's.
    """

    published: tuple[int, ...]
    means: Mapping[tuple[str, int], float | None]
    responses: int
    valid_responses: int
    enrolled: int


def _trend_down(figures: SectionWeekFigures, stream: str) -> bool:
    """Down two or more consecutive weeks: the last three published weeks each lower than before."""
    if len(figures.published) < 3:
        return False
    last = figures.published[-3:]
    if last != (last[0], last[0] + 1, last[0] + 2):
        return False
    means = [figures.means.get((stream, week)) for week in last]
    if any(mean is None for mean in means):
        return False
    first, second, third = (float(mean) for mean in means if mean is not None)
    return first > second > third


def attention_cards(
    sections: Sequence[HeldSection],
    *,
    figures: Mapping[UUID, SectionWeekFigures],
    owed: set[tuple[UUID, int]],
) -> list[AttentionCard]:
    """§5.6's four rules over a node's sections, as cards ordered by labels and never by figures."""
    instructor, course = REPORT_STREAMS
    cards: list[AttentionCard] = []

    def card(section: HeldSection, rule: AttentionRule, stream: str | None, week: int) -> None:
        cards.append(
            AttentionCard(
                rule=rule,
                rule_name=_RULE_NAMES[rule],
                stream=None if stream is None else (instructor if stream == instructor else course),
                section_id=section.section_id,
                section_code=section.code,
                course_name=section.course_name,
                course_week=week,
            )
        )

    for section in sections:
        found = figures.get(section.section_id)
        if found is not None and found.published:
            latest = found.published[-1]
            if _trend_down(found, instructor):
                card(section, "instructor_trend_down", instructor, latest)
            if _trend_down(found, course):
                card(section, "course_trend_down", course, latest)
            if found.enrolled > 0 and found.responses / found.enrolled < _LOW_RESPONSE_RATE:
                card(section, "response_rate_low", None, latest)
        for week in sorted(week for owed_id, week in owed if owed_id == section.section_id):
            card(section, "response_owed", None, week)
    return sorted(
        cards,
        key=lambda c: (
            c.course_name,
            c.section_code,
            _RULE_ORDER.index(c.rule),
            c.course_week,
            str(c.section_id),
        ),
    )


def _chosen(
    held: Sequence[HeldSection],
    *,
    kind: FiguresKind,
    node_id: UUID,
    staff: Mapping[UUID, SectionStaff],
) -> list[HeldSection]:
    if kind in ("lead", "no_lead"):
        return [section for section in held if _lead_group_of(section, staff) == (kind, node_id)]
    return [section for section in held if section.node(kind)[0] == node_id]


def _section_week_figures(
    session: Session, *, term: Term, chosen: Sequence[HeldSection], settings: Settings
) -> dict[UUID, SectionWeekFigures]:
    """Each section's published weeks, rating means, and latest week's responses and enrolment.

    Three set-based reads (the windows, the response counts, the rating
    counts), then one enrolment count per section for its latest week, through
    the report's own `_enrolled_students` so the denominator is the report's.
    """
    ids = sorted(section.section_id for section in chosen)
    by_id = {section.section_id: section for section in chosen}
    now = clock.now(session, settings=settings)
    zone = ZoneInfo(settings.institution_timezone)
    weeks: dict[UUID, dict[int, reporting._SectionWeek]] = defaultdict(dict)
    for section_id, week_id, number, opens_at, closes_at in session.execute(
        select(
            SurveyWindow.section_id,
            SurveyWindow.week_id,
            Week.number,
            SurveyWindow.opens_at,
            SurveyWindow.closes_at,
        )
        .join(Week, Week.id == SurveyWindow.week_id)
        .where(SurveyWindow.section_id.in_(ids))
    ):
        if not reporting.week_is_published(closes_at, now=now, zone=zone):
            continue
        course_week = course_week_of(
            number, section_start=by_id[section_id].start_date, term_start=term.start_date
        )
        weeks[section_id][course_week] = reporting._SectionWeek(
            week_id=week_id,
            term_week=number,
            course_week=course_week,
            opens_at=opens_at,
            closes_at=closes_at,
        )
    week_ids = sorted({week.week_id for found in weeks.values() for week in found.values()})
    counts = {
        (row[0], row[1]): (int(row[2]), int(row[3]))
        for row in session.execute(
            select(
                reporting.RESPONSE_COUNTS_VIEW.c.section_id,
                reporting.RESPONSE_COUNTS_VIEW.c.week_id,
                reporting.RESPONSE_COUNTS_VIEW.c.responses,
                reporting.RESPONSE_COUNTS_VIEW.c.valid_responses,
            ).where(
                reporting.RESPONSE_COUNTS_VIEW.c.section_id.in_(ids),
                reporting.RESPONSE_COUNTS_VIEW.c.week_id.in_(week_ids),
            )
        )
    }
    ratings: dict[tuple[UUID, UUID, str], dict[int, int]] = defaultdict(dict)
    view = reporting.RATING_DISTRIBUTION_VIEW
    for section_id, week_id, stream, rating, responses in session.execute(
        select(
            view.c.section_id, view.c.week_id, view.c.stream, view.c.rating, view.c.responses
        ).where(view.c.section_id.in_(ids), view.c.week_id.in_(week_ids))
    ):
        ratings[(section_id, week_id, str(stream))][int(rating)] = int(responses)
    sections = {row.id: row for row in session.scalars(select(Section).where(Section.id.in_(ids)))}
    figures: dict[UUID, SectionWeekFigures] = {}
    for section_id in ids:
        published = weeks.get(section_id, {})
        if not published:
            figures[section_id] = SectionWeekFigures(
                published=(), means={}, responses=0, valid_responses=0, enrolled=0
            )
            continue
        latest = published[max(published)]
        figures[section_id] = SectionWeekFigures(
            published=tuple(sorted(published)),
            means={
                (stream, course_week): reporting._mean_of(
                    ratings.get((section_id, week.week_id, stream), {})
                )
                for course_week, week in published.items()
                for stream in REPORT_STREAMS
            },
            responses=counts.get((section_id, latest.week_id), (0, 0))[0],
            valid_responses=counts.get((section_id, latest.week_id), (0, 0))[1],
            enrolled=reporting._enrolled_students(
                session, section=sections[section_id], week=latest, settings=settings
            ),
        )
    return figures


def _cohort_label(start_date: date, sections: Sequence[HeldSection]) -> str:
    letters = sorted({parse_section_code(section.code).start_letter for section in sections})
    return words.COHORT.text.format(
        letters="/".join(letters), month=start_date.month, day=start_date.day
    )


def _participation(
    cohort_sections: Sequence[HeldSection],
    *,
    figures: Mapping[UUID, SectionWeekFigures],
) -> RollupParticipation | None:
    """The cohort's rates in its latest published week, over the sections that have that week."""
    latest = max(
        (
            figures[s.section_id].published[-1]
            for s in cohort_sections
            if figures[s.section_id].published
        ),
        default=None,
    )
    if latest is None:
        return None
    responses = valid = enrolled = 0
    for section in cohort_sections:
        found = figures[section.section_id]
        if found.published and found.published[-1] == latest:
            responses += found.responses
            valid += found.valid_responses
            enrolled += found.enrolled
    return RollupParticipation(
        course_week=latest,
        response_rate=None if enrolled == 0 else responses / enrolled,
        validity_rate=None if responses == 0 else valid / responses,
    )


def rollup_figures(
    session: Session,
    *,
    scope: ActorScope,
    term_id: UUID,
    kind: FiguresKind,
    node_id: UUID,
    settings: Settings,
) -> RollupFigures:
    """One node's figures and attention cards in one term (SPEC §5.5, §5.6).

    Raises `TermUnavailableError` for an unknown term, then
    `NodeUnavailableError` for a node holding none of the reader's sections in
    the term, whether it exists or not. The by-lead groups are refused to a
    reader who is not offered the pivot, exactly as a missing node is.
    """
    term = session.get(Term, term_id)
    if term is None:
        raise TermUnavailableError
    if kind in ("lead", "no_lead") and not offers_by_lead(scope):
        raise NodeUnavailableError
    held = _held_sections(session, scope=scope, term_id=term_id)
    staff = (
        _staff_of(session, scope=scope, held=held, settings=settings)
        if kind in ("lead", "no_lead")
        else {}
    )
    chosen = _chosen(held, kind=kind, node_id=node_id, staff=staff)
    if not chosen:
        raise NodeUnavailableError
    figures = _section_week_figures(session, term=term, chosen=chosen, settings=settings)
    owed = owed_section_weeks(
        session,
        section_ids=[section.section_id for section in chosen],
        now=clock.now(session, settings=settings),
        settings=settings,
    )
    by_id = {section.section_id: section for section in chosen}
    cohorts = [
        RollupCohort(
            section_start_date=cohort.section_start_date,
            label=_cohort_label(
                cohort.section_start_date, [by_id[i] for i in sorted(cohort.section_ids)]
            ),
            weeks=[
                RollupWeek(
                    course_week=week.course_week,
                    term_week=week.term_week,
                    instructor_mean=week.instructor_mean,
                    course_mean=week.course_mean,
                    workload_mean=week.workload_mean,
                    workload_median=week.workload_median,
                )
                for week in cohort.weeks
            ],
            participation=_participation([by_id[i] for i in cohort.section_ids], figures=figures),
        )
        for cohort in node_series(session, section_ids=list(by_id), term=term, settings=settings)
    ]
    cards = attention_cards(chosen, figures=figures, owed=owed)
    return RollupFigures(
        kind=kind,
        id=node_id,
        term_id=term_id,
        cohorts=cohorts,
        attention=cards,
        attention_empty=None if cards else words.NOTHING_NEEDS_ATTENTION.text,
    )
