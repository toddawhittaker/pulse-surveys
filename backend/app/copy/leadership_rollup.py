"""The sentences the leadership roll-ups serve — E9-05, the `leadership_rollup` surface.

E9's README decision 15 registers this surface, and E9-07 and E9-11 file their
strings under the same prefix. It owes no confidentiality line: roll-ups show
figures over sections, attention cards and staff names, never a comment, a
summary or a single response (ruling 2), and the drill-down reuses the
instructor report's surface and its line.

The named-set series route serves one sentence: the refusal for a term that is
not there. The line's legend and its withheld notice are drawn by E9-11 in the
frontend's copy module under this prefix, because the API serves no words for
them.

The roll-up routes (`app.services.rollups`) serve the rest: the tree's row
labels (SPEC §2.1's "N departments · N sections · Dean: {name}" and its kin,
built from the counting and naming pieces below), the cohort label (§2.2), the
four attention rules' names (§5.6), the calm empty state, and the refusal for a
node the reader does not hold. A count is of sections, courses, prefixes or
departments and never of people (§4.1 item 4). The `{…}` fields are filled
with `str.format` by the service.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = [
    "CHAIR",
    "COHORT",
    "COPY",
    "COURSES",
    "COURSE_TREND_DOWN",
    "DEAN",
    "DEPARTMENTS",
    "INSTRUCTOR_TREND_DOWN",
    "LABEL_SEPARATOR",
    "LEAD",
    "NODE_UNAVAILABLE",
    "NOTHING_NEEDS_ATTENTION",
    "NO_LEAD_GROUP",
    "ONE_COURSE",
    "ONE_DEPARTMENT",
    "ONE_PREFIX",
    "ONE_SECTION",
    "PREFIXES",
    "RESPONSE_OWED",
    "RESPONSE_RATE_LOW",
    "SECTIONS",
    "TERM_UNAVAILABLE",
]

# The 404 for a `term_id` no term carries. Term existence is no secret, so the
# sentence says only that there is nothing here to read.
TERM_UNAVAILABLE = CopyEntry(
    key="leadership_rollup.term_unavailable",
    text="There is no term here.",
)

# The 404 for a roll-up node this reader does not hold, worded exactly as for a
# node that does not exist, because the two are one answer.
NODE_UNAVAILABLE = CopyEntry(
    key="leadership_rollup.node_unavailable",
    text="There is nothing here to read.",
)

# §5.6's calm empty state.
NOTHING_NEEDS_ATTENTION = CopyEntry(
    key="leadership_rollup.attention.empty",
    text="Nothing needs attention this week",
)

# §5.6's four rules, one name each; a card names its rule and, for a trend, its
# stream, which is why the two trend rules are two entries.
INSTRUCTOR_TREND_DOWN = CopyEntry(
    key="leadership_rollup.attention.instructor_trend_down",
    text="Instructor trend down two or more consecutive weeks",
)
COURSE_TREND_DOWN = CopyEntry(
    key="leadership_rollup.attention.course_trend_down",
    text="Course trend down two or more consecutive weeks",
)
RESPONSE_RATE_LOW = CopyEntry(
    key="leadership_rollup.attention.response_rate_low",
    text="Response rate under 40%",
)
RESPONSE_OWED = CopyEntry(
    key="leadership_rollup.attention.response_owed",
    text="Response required, not yet published after 48 hours",
)

# The pieces a tree row's label is joined from, with `LABEL_SEPARATOR`.
LABEL_SEPARATOR = CopyEntry(key="leadership_rollup.label.separator", text=" · ")
ONE_SECTION = CopyEntry(key="leadership_rollup.label.one_section", text="1 section")
SECTIONS = CopyEntry(key="leadership_rollup.label.sections", text="{count} sections")
ONE_COURSE = CopyEntry(key="leadership_rollup.label.one_course", text="1 course")
COURSES = CopyEntry(key="leadership_rollup.label.courses", text="{count} courses")
ONE_PREFIX = CopyEntry(key="leadership_rollup.label.one_prefix", text="1 prefix")
PREFIXES = CopyEntry(key="leadership_rollup.label.prefixes", text="{count} prefixes")
ONE_DEPARTMENT = CopyEntry(key="leadership_rollup.label.one_department", text="1 department")
DEPARTMENTS = CopyEntry(key="leadership_rollup.label.departments", text="{count} departments")
DEAN = CopyEntry(key="leadership_rollup.label.dean", text="Dean: {name}")
CHAIR = CopyEntry(key="leadership_rollup.label.chair", text="Chair: {name}")
LEAD = CopyEntry(key="leadership_rollup.label.lead", text="Lead: {name}")

# The by-lead pivot's group for a department's courses nobody leads, which fall
# to the chair (§2.1).
NO_LEAD_GROUP = CopyEntry(
    key="leadership_rollup.label.no_lead_group",
    text="No Lead Faculty: {department}",
)

# §2.2's cohort selector label: "U sections · started 8/17".
COHORT = CopyEntry(
    key="leadership_rollup.label.cohort",
    text="{letters} sections · started {month}/{day}",
)

COPY: Mapping[str, CopyEntry] = {
    entry.key: entry
    for entry in (
        TERM_UNAVAILABLE,
        NODE_UNAVAILABLE,
        NOTHING_NEEDS_ATTENTION,
        INSTRUCTOR_TREND_DOWN,
        COURSE_TREND_DOWN,
        RESPONSE_RATE_LOW,
        RESPONSE_OWED,
        LABEL_SEPARATOR,
        ONE_SECTION,
        SECTIONS,
        ONE_COURSE,
        COURSES,
        ONE_PREFIX,
        PREFIXES,
        ONE_DEPARTMENT,
        DEPARTMENTS,
        DEAN,
        CHAIR,
        LEAD,
        NO_LEAD_GROUP,
        COHORT,
    )
}
