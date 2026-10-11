"""What the response loop says to a person — E7-02 adds the student results refusal.

**One sentence for every refused results read** (E7-02, decision 5). A section
the student is not enrolled in, an enrollment that has ended, a week whose report
has not opened, and a week or a section that does not exist are all answered with
the same 404 and these same words. Telling any two apart would tell a student
something about a section they cannot read: that it exists, or how long it runs.
So the sentence names nothing, and says only what a student can do.

**The key sits under `student.`**, the survey surface's registry prefix, because
the results page is a student page and SPEC §4.1 item 5 counts a screen's words
wherever they are written. E7-06 places the page's own strings.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = ["COPY", "RESULTS_UNAVAILABLE"]

RESULTS_UNAVAILABLE = CopyEntry(
    key="student.results_unavailable",
    text=(
        "There are no results to show here. Results for a week appear on the Monday morning "
        "after its survey closes."
    ),
)

COPY: Mapping[str, CopyEntry] = {entry.key: entry for entry in (RESULTS_UNAVAILABLE,)}
