"""The refusals the instructor report answers with — E4-12, E5.1-03 and E6-03.

`app.api.instructor` serves SPEC §5.1's report, and it refuses two ways: a
section outside the session's teaching set or absent altogether gets one
sentence, and a course week the section has no published report for gets
another. Both were module constants in the router until this ticket, so the
inventory `app.copy.copy_modules()` publishes could not see either, and SPEC
§4.1 items 4 and 5 were asserted over neither — the state
`docs/tickets/e4/deferred.md` records under "The report API's two refusal
sentences sit outside the copy registry". The prefix a registry key needs
existed only once the report became a governed surface, which is the rest of
E4-12 (ADR 0158).

**The third is the role gate's.** `app.api.deps.require_instructor` answers a
401 to every request at an instructor route that carries no instructor's
session. Its sentence stayed a literal in `app.api.deps` after E4-12, a carried
gap, until E5.1-03 moved it here as `instructor_report.not_an_instructor`. The
report's prefix is already a governed surface, so it is swept with the other two.

**One surface, two sources.** These keys sit on the `report` surface beside the
four `instructor_report_*` prefixes the frontend copy modules publish, exactly
as `submit` and `student` sit beside `student_survey` on the survey. Item 5
counts the screen a person reads rather than the file a string came out of.

**None is the surface's confidentiality line.** They say what is not there to
read, not what happens to anybody's identity; `instructor_report_page`'s
`comments_note` is the report's one line, and these three are swept for item 4's
vocabulary along with everything else.

**Why each says so little.** The section refusal names nothing it was handed —
no section, no course, no reason — because the two cases it answers must not be
distinguishable: a reader who could tell "not yours" from "does not exist" could
enumerate the institution's sections one id at a time. The week refusal is
reached only after the section is established as this instructor's own, so it is
free to be a different sentence, and it covers a window still taking responses
and a week the section never runs with one wording for the same no-oracle
reason. The router's own header argues both at length; what is here is the
words.

**E6-03 adds the decision route's five.** One 404 for every comment the
reader's report does not return (held, another section's, not a comment,
Care-class, or nothing at all), so the answer cannot tell an instructor which of
those an id was; one 409 for an action the comment's state or its latest
decision does not allow; and three 422s for the stated reason. None names the
comment, the section or what was asked: each says what did not happen and, where
the reader can act on it, what to do instead.

**`COPY` beside the entries, because that is the shape the package settles.**
Each copy module publishes `COPY: Mapping[str, CopyEntry]` keyed by dotted keys,
which is what `app.copy.copy_modules()`'s readers walk.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = [
    "COMMENT_UNAVAILABLE",
    "COPY",
    "DECISION_NOT_ALLOWED",
    "NOT_AN_INSTRUCTOR",
    "REASON_BLANK",
    "REASON_REQUIRED",
    "REASON_TOO_LONG",
    "SECTION_UNAVAILABLE",
    "WEEK_UNAVAILABLE",
]

# The 404 both halves of the refusal pair get: a section this instructor does not
# teach, and a section that is not there at all.
SECTION_UNAVAILABLE = CopyEntry(
    key="instructor_report.section_unavailable",
    text="There is no report here for you to read.",
)

# The 404 for a course week this section has no published report for — whether
# its window is still open or the section never runs it.
WEEK_UNAVAILABLE = CopyEntry(
    key="instructor_report.week_unavailable",
    text="There is no report for that week of this section.",
)

# The 401 `app.api.deps.require_instructor` answers a request that carries no
# instructor's session — none at all, or one in another role. It names nobody and
# nothing: no section, no role, no subject. A refusal answered to anybody who can
# make a request may describe only itself. It was a literal in `app.api.deps` until
# E5.1-03 moved it here, beside the report's two other refusals.
NOT_AN_INSTRUCTOR = CopyEntry(
    key="instructor_report.not_an_instructor",
    text=(
        "This is an instructor's report, and this request does not carry an instructor's session. "
        "Open Pulse Surveys from inside your course in the LMS to read it."
    ),
)

# The 404 the decision route answers for an answer the reader's report does not
# return. One sentence for every such case, interpolating nothing, so the refusal
# says nothing about what the id was (E6-03, its work order's decision 1).
COMMENT_UNAVAILABLE = CopyEntry(
    key="instructor_report.comment_unavailable",
    text="There is no comment here for you to decide on.",
)

# The 409 for an action the comment's state does not allow: keeping a comment that
# is not waiting for review or excluded, asking for the state it already holds, or
# an Undo of something that is not your own latest decision.
DECISION_NOT_ALLOWED = CopyEntry(
    key="instructor_report.decision_not_allowed",
    text="That decision does not apply to this comment as it stands, so nothing was changed.",
)

# The three 422s for the stated reason (SPEC §5.2: excluding a comment the AI did
# not flag requires one). Checked as sent, before any trimming.
REASON_REQUIRED = CopyEntry(
    key="instructor_report.reason_required",
    text=(
        "Excluding a comment that was not flagged for review needs a stated reason. "
        "Nothing was changed."
    ),
)
REASON_BLANK = CopyEntry(
    key="instructor_report.reason_blank",
    text="A stated reason has to contain some words. Nothing was changed.",
)
REASON_TOO_LONG = CopyEntry(
    key="instructor_report.reason_too_long",
    text="A stated reason can be at most 500 characters long. Nothing was changed.",
)

COPY: Mapping[str, CopyEntry] = {
    entry.key: entry
    for entry in (
        SECTION_UNAVAILABLE,
        WEEK_UNAVAILABLE,
        NOT_AN_INSTRUCTOR,
        COMMENT_UNAVAILABLE,
        DECISION_NOT_ALLOWED,
        REASON_REQUIRED,
        REASON_BLANK,
        REASON_TOO_LONG,
    )
}
