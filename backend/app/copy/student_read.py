"""What the student read path says to a person — E2-09.

One string today: what somebody is told when they ask this path for a weekly
survey and the request carries no student session. It is here rather than in
`app.api.deps` beside the guard that serves it, because SPEC §4.1 items 4 and 5
are checked over the inventory `app.copy.copy_modules()` walks, and a sentence
written into a handler is a sentence that inventory cannot read.

**One sentence for two events, deliberately.** "You are signed in, but not as a
student" and "you are not signed in" are refused with the same status, the same
challenge and this same string, because the difference between them is a fact
about who holds the token — and a path that spells the two differently hands
whoever is trying tokens a way to tell a real session from a forged one apart
from the answer itself.

**It names nobody and asks for nothing.** The refusal is answered to anyone who
can make a request, so it carries no section, no subject and no role; what it can
do is say where a student's weekly survey is actually opened from, which for a
student is the LMS course (SPEC §2.1 gives the student row one entry point).

**One sentence for two surfaces.** `student.not_a_student` is the key E2-08's work
order settles for the refusal `app.api.deps.require_student` serves, and that one
guard is carried by the read path here and by the submit path next door. So the
key is published once, from this module, and both surfaces serve the same words —
two entries under one key would be two sentences for the inventory to pick between
and for the two routes to drift apart in.

**`COPY` beside the entry, because that is the shape the package settles.** Each
copy module publishes `COPY: Mapping[str, CopyEntry]` keyed by dotted keys, which
is what `app.copy.copy_modules()`'s readers walk; a module presenting its entries
some other way is a module an inventory has to be taught about.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = ["COPY", "NOT_A_STUDENT"]

NOT_A_STUDENT = CopyEntry(
    key="student.not_a_student",
    text=(
        "This is a student's weekly survey, and this request does not carry a student's session. "
        "Open Pulse Surveys from inside your course in the LMS to answer this week's survey."
    ),
)

COPY: Mapping[str, CopyEntry] = {entry.key: entry for entry in (NOT_A_STUDENT,)}
