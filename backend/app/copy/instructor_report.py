"""The two refusals the instructor report answers with — E4-12.

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

**One surface, two sources.** These keys sit on the `report` surface beside the
four `instructor_report_*` prefixes the frontend copy modules publish, exactly
as `submit` and `student` sit beside `student_survey` on the survey. Item 5
counts the screen a person reads rather than the file a string came out of.

**Neither is the surface's confidentiality line.** They say what is not there to
read, not what happens to anybody's identity; `instructor_report_page`'s
`comments_note` is the report's one line, and these two are swept for item 4's
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

**`COPY` beside the entries, because that is the shape the package settles.**
Each copy module publishes `COPY: Mapping[str, CopyEntry]` keyed by dotted keys,
which is what `app.copy.copy_modules()`'s readers walk.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = ["COPY", "SECTION_UNAVAILABLE", "WEEK_UNAVAILABLE"]

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

COPY: Mapping[str, CopyEntry] = {
    entry.key: entry for entry in (SECTION_UNAVAILABLE, WEEK_UNAVAILABLE)
}
