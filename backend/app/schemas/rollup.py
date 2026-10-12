"""The leadership roll-up payloads (SPEC §5.5): the tree, and one node's figures and attention.

`app.services.rollups` builds both; `app.api.leadership` serves them. **No
member here carries a comment, a summary, a theme or a count of comments** (SPEC
§5.5, settled at the E9 breakdown): a leader reads comments only inside a
section's drill-down. A unit sweep over this module holds that by member name.

**Every list is ordered by a label or a code, never by a figure** (§4.1 item 4):
tree children by name, section rows by code, cohorts by start date, attention
cards by course name, section code and rule.
"""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# The kinds of node a roll-up tree holds. The first five are SPEC §2.1's
# containment levels below the institution; `lead` and `no_lead` are the by-lead
# pivot's groups (a Lead Faculty member's courses, and a department's courses
# nobody leads, which fall to the chair).
NodeKind = Literal["college", "department", "prefix", "course", "section", "lead", "no_lead"]

# The kinds a node's figures may be asked for. A section's own figures are its
# report, read through the drill-down.
FiguresKind = Literal["college", "department", "prefix", "course", "lead", "no_lead"]

AttentionRule = Literal[
    "instructor_trend_down",
    "course_trend_down",
    "response_rate_low",
    "response_owed",
]


class RollupNode(BaseModel):
    """One row of the tree, with its children.

    Every count is over the sections the reader holds, in the viewed term, so a
    container the reader holds part of counts that part only. `staff_name` is
    the row's Dean, Chair or Lead (absent for a course in its own lead's view,
    and where nobody holds the post); `instructor_names` is a section row's
    teaching instructors. `label` is SPEC §2.1's row label, joined from those.
    """

    model_config = ConfigDict(frozen=True)

    kind: NodeKind
    id: UUID
    name: str
    label: str
    section_count: int
    course_count: int | None = None
    prefix_count: int | None = None
    department_count: int | None = None
    staff_name: str | None = None
    instructor_names: list[str] = []
    children: list["RollupNode"] = []


class RollupTree(BaseModel):
    """The whole tree over the reader's leadership purview in one term.

    `hierarchy` holds the roots (SPEC §2.1: the highest useful nodes, several
    for a union of assignments). `by_lead` is the by-lead pivot, offered only to
    a reader holding a `CHAIR` or higher assignment, and absent otherwise.
    """

    model_config = ConfigDict(frozen=True)

    term_id: UUID
    hierarchy: list[RollupNode]
    by_lead: list[RollupNode] | None


class RollupWeek(BaseModel):
    """One course week of one cohort, on both week axes; `None` where nobody answered."""

    model_config = ConfigDict(frozen=True)

    course_week: int
    term_week: int
    instructor_mean: Decimal | None
    course_mean: Decimal | None
    workload_mean: Decimal | None
    workload_median: Decimal | None


class RollupParticipation(BaseModel):
    """A cohort's response rate and validity rate in its latest published week."""

    model_config = ConfigDict(frozen=True)

    course_week: int
    response_rate: float | None
    validity_rate: float | None


class RollupCohort(BaseModel):
    """One start cohort of a node's sections, its line on the term axis, and its participation."""

    model_config = ConfigDict(frozen=True)

    section_start_date: date
    label: str
    weeks: list[RollupWeek]
    participation: RollupParticipation | None


class AttentionCard(BaseModel):
    """One §5.6 rule met by one section: the rule, its stream, and where its report is."""

    model_config = ConfigDict(frozen=True)

    rule: AttentionRule
    rule_name: str
    stream: Literal["INSTRUCTOR", "COURSE"] | None
    section_id: UUID
    section_code: str
    course_name: str
    course_week: int


class RollupFigures(BaseModel):
    """One node's figures in one term: a line per start cohort, and the attention cards.

    `attention_empty` is §5.6's calm sentence when no card is due, and absent
    when one is.
    """

    model_config = ConfigDict(frozen=True)

    kind: FiguresKind
    id: UUID
    term_id: UUID
    cohorts: list[RollupCohort]
    attention: list[AttentionCard]
    attention_empty: str | None
