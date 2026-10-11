"""What the response loop says to a person — E7-02's student refusal, E7-03's door refusals.

**One sentence for every refused results read** (E7-02, decision 5). A section
the student is not enrolled in, an enrollment that has ended, a week whose report
has not opened, and a week or a section that does not exist are all answered with
the same 404 and these same words. Telling any two apart would tell a student
something about a section they cannot read: that it exists, or how long it runs.
So the sentence names nothing, and says only what a student can do.

**The key sits under `student.`**, the survey surface's registry prefix, because
the results page is a student page and SPEC §4.1 item 5 counts a screen's words
wherever they are written. E7-06 places the page's own strings.

**E7-03's keys sit with the screens that show them.** The instructor's two 409s
are under `instructor_report.`, because the composer is on the report page
(E7-05). The policy switch's and the on-behalf doors' 404s are under
`leadership_response.`, the leadership response screens E7-07 builds, a surface
of its own in the copy governance map.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = [
    "COPY",
    "NO_POLICY_TO_SET",
    "NOT_YOURS_TO_EDIT",
    "ON_BEHALF_UNAVAILABLE",
    "RESPONSE_ALREADY_PUBLISHED",
    "RESULTS_UNAVAILABLE",
]

RESULTS_UNAVAILABLE = CopyEntry(
    key="student.results_unavailable",
    text=(
        "There are no results to show here. Results for a week appear on the Monday morning "
        "after its survey closes."
    ),
)

# E7-03, decision 1: the instructor's publish when the week already has a response.
# The response may be the instructor's own or one written on their behalf; either
# way the instructor's report shows it, so saying so reveals nothing.
RESPONSE_ALREADY_PUBLISHED = CopyEntry(
    key="instructor_report.response_already_published",
    text="This week already has a response. Only the person who published it can edit it.",
)

# E7-03, decision 1: an edit with no response yet, or by someone who did not
# first publish it. One sentence for both, so a refusal never says who published.
NOT_YOURS_TO_EDIT = CopyEntry(
    key="instructor_report.response_not_editable",
    text="There is no response of yours to edit for this week.",
)

# E7-03, decision 2: a policy switch for a prefix where the reader sets no course,
# and for a prefix that does not exist. One sentence, naming nothing.
NO_POLICY_TO_SET = CopyEntry(
    key="leadership_response.no_policy_to_set",
    text="There is no response policy here that you set.",
)

# E7-03, decision 5: every refusal of every on-behalf door. A course outside the
# reader's own, a section they teach or taught, a week not yet open on behalf, a
# week not required, a week already answered, a week not published, and a key
# nothing holds all answer these same words, so the refusal says nothing about
# the section or its week.
ON_BEHALF_UNAVAILABLE = CopyEntry(
    key="leadership_response.on_behalf_unavailable",
    text="There is nothing to respond to on behalf of anyone here.",
)

COPY: Mapping[str, CopyEntry] = {
    entry.key: entry
    for entry in (
        RESULTS_UNAVAILABLE,
        RESPONSE_ALREADY_PUBLISHED,
        NOT_YOURS_TO_EDIT,
        NO_POLICY_TO_SET,
        ON_BEHALF_UNAVAILABLE,
    )
}
