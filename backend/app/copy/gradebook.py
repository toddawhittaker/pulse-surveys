"""The two strings Pulse writes into somebody else's gradebook — E4-12.

SPEC §3.4 gives every section one AGS line item, labelled "Pulse Participation",
and gives every posted score a per-week ledger in its AGS comment. Both are
sentences this product writes and an instructor reads; that the surface drawing
them belongs to another product is a fact about rendering rather than about
authorship, and it is not a reason for SPEC §4.1 items 4 and 5 to stop applying.
They were literals beside the code that posts them until this ticket, which is
the state E3 recorded as a carried gap: the copy inventory collected neither, so
the vocabulary rules read neither.

**This surface owes item 5 no confidentiality line.** The label names a course
activity and the ledger states the arithmetic behind a percentage. Neither tells
a student what happens to their identity, so item 5's sentence would have no
subject here, and a reassuring sentence added to a gradebook column would be a
second copy of the product's promise made where nothing keeps it. The inventory
records the surface in its no-line map with that reason written out, and ADR
0158 records the split.

**What is deliberately not here.** The line item's `resourceId`, which is an
identifier a tool matches on rather than a word anybody reads (ADR 0133); the
newline the ledger's lines are joined with, which is punctuation belonging to
the code that assembles them; and the percentage itself, which is a number the
formula produces.

**The texts are pinned byte-for-byte elsewhere and are moved rather than
rewritten.** The grading and AGS suites assert the exact characters of both,
because an AGS body differing by a character is a different body; this module is
where they are now written, and `app.lti.ags` and `app.services.grading` read
them from here.
"""

from collections.abc import Mapping

from app.copy import CopyEntry

__all__ = ["COPY", "LEDGER_LINE", "LINE_ITEM_LABEL"]

# SPEC §3.4: "One AGS line item per section: **'Pulse Participation'**, created
# by the tool on first launch." What a person reads at the top of the column in
# their own gradebook.
LINE_ITEM_LABEL = CopyEntry(
    key="gradebook.line_item_label",
    text="Pulse Participation",
)

# SPEC §3.4's ledger: "one line per elapsed week, of the form `Week 1: 4 of 5
# items`, in course-week order". The holes are filled by
# `app.services.grading`, which is also where the lines are joined. Since v1
# renders no participation score anywhere, this comment is the only place the
# arithmetic behind a posted percentage is visible to anybody (ADR 0125).
LEDGER_LINE = CopyEntry(
    key="gradebook.ledger_line",
    text="Week {course_week}: {completed} of {total} items",
)

COPY: Mapping[str, CopyEntry] = {entry.key: entry for entry in (LINE_ITEM_LABEL, LEDGER_LINE)}
