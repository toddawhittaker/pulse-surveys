# 0014 — LMS-owned columns are marked by an `lms_` name prefix

**Status:** Accepted
**Date:** 2026-08-14
**Tickets:** E0-05

## Context

[SPEC §2.1](../SPEC.md) splits the data by owner: courses, sections, section
codes, enrollments and teaching instructors are LMS-owned and read-only in
Pulse, synced hourly and at launch. [§8](../SPEC.md) restates it as a
constraint — "LMS-owned data is never hand-edited in Pulse."

Neither says how a column announces which side it is on. E0-05 is the first
ticket to create LMS-owned columns, and its scope asks for a marker on the
grounds that a comment is not enough, leaving the mechanism open: "a model-level
marker or a naming convention the authz layer can read."

The mechanism has to survive two things. It has to be readable by something
other than the models — the authorization chokepoint E0-11 builds is the assumed
reader, though see the consequences below: that assumption is weaker than it
looked when this was written. And it has to be hard to omit — the failure this
marker exists to
prevent is a later ticket adding an LMS-owned column, forgetting to mark it, and
an edit path appearing over data the LMS owns with nothing failing.

## Decision

LMS-owned columns carry an `lms_` name prefix: `course.lms_number`,
`section.lms_section_code`.

The prefix marks the column, not the value. `course.level` derives from
`lms_number` and carries no prefix — the LMS supplies the number and Pulse
computes the level, and the generated column cannot be written by anyone in any
case, which is the thing the marker exists to prevent.

`tests/unit/test_lms_owned_column_marker.py` asserts it by walking
`Base.metadata`.

## Alternatives rejected

**A `Column(..., info={"owner": "lms"})` dict.** Idiomatic SQLAlchemy, readable
from `Base.metadata` without importing the models, and it keeps column names
clean. Rejected because it can be omitted silently: a new column with no `info`
is indistinguishable from a Pulse-owned one, and the omission is invisible at
every site that reads the column. The prefix has the same weakness in principle
— a column can be named without it — but the name is in front of whoever writes
the query, not only in front of whoever wrote the definition.

**A Postgres column comment.** Visible to any client including a bare `psql`
session, which is a real advantage for an operator. Rejected because the comment
is written by the migration rather than by the model, so the two drift, and
`alembic check` does not compare comments by default — the drift would be
silent, which is the failure mode this project has spent [E0-20](../tickets/e0/E0-20-gate-fidelity.md)
cataloguing.

**Nothing but the docstring and review.** Rejected on the evidence in
[`MISTAKES.md`](../MISTAKES.md) entry 2, which is the entry with the highest
catch count in the file.

## Consequences

The prefix is noisy. It appears in every query, every view definition, and every
serializer that touches a course or a section, and it will read as redundant to
someone who already knows the schema.

A column that changes owner needs a migration to rename it. That is the intended
cost — an ownership change should be a visible schema event and not an edit to a
metadata dict.

**The marker is a convention, not an enforcement, and this ADR does not claim
otherwise.** What can be asserted from `Base.metadata` is that the columns named
so far are prefixed, and that no Pulse-owned table has grown a prefixed column.
What cannot be asserted there is the direction that matters most: an unprefixed
LMS-owned column arriving in a later ticket leaves no trace in the metadata that
distinguishes it from a Pulse-owned one. Until something closes that, the suite
carries a trap-line of unprefixed spellings that must not appear beside the
marked ones, which catches the regression and does not pretend to catch the
omission. **E0-35 closes that direction on the tables SPEC §2.1 names, and
nowhere else — see the second amendment below.**

**Amended by E0-05's review: the enforcing check may not be column-grained at
all, and if it is not, this marker becomes documentation.** An earlier version of
this section said the check simply belongs in
[E0-11](../tickets/e0/E0-11-authz-skeleton.md), asking "does the chokepoint
refuse a write to *this column*". That presumes column grain. [SPEC
§2.1](../SPEC.md)'s ownership list is stated largely per entity — *courses,
sections, section codes, enrollments, teaching instructors* — so a chokepoint
that refuses application writes to those **tables** answers §2.1 without reading
a column name, and catches the unprefixed column no name-based check can see.

That matters for this record, not only for E0-11, because "the chokepoint must
be able to read the marker" is one of the two reasons given above for choosing a
name over an `info={}` dict. **If E0-11 picks table grain, that reason is void**
and the prefix survives on its remaining merit alone: it is in front of whoever
writes the query, not only whoever wrote the definition. The decision still
stands on that, and this ADR is not superseded — but a reader arriving here to
learn how ownership is enforced should go to E0-11 for the grain rather than
assume it was settled here. E0-11 is required to choose and to say what the
chosen grain does not catch. E0-11 chose table grain, in
[ADR 0045](0045-the-chokepoint-refuses-an-lms-owned-write-at-table-grain-plus-one-row.md).

**Amended by E0-35, 2026-08-19: the marker is now documentation, and the reason
above is void.** `tests/unit/test_no_lms_owned_table_carries_an_unmarked_column.py`
asks the question at table grain rather than per column: on a table SPEC §2.1
puts on the LMS's side of the ownership sentence, every column must be one of
four things — **marked** with the `lms_` prefix, **structural** (a primary key or
a column carrying a foreign key), **unwritable** (a stored generated column, of
which `course.level` is the worked example, [ADR 0015](0015-course-level-is-a-stored-generated-column.md)),
or **recorded** in that module's `PULSE_OWNED_COLUMNS` with the record that says
why Pulse owns a value on a table the LMS owns. Anything else fails.
`course.canvas_id` is none of the four, so the column this record said leaves no
trace now turns something red.

So the direction that could not be asserted is asserted, and **the marker is no
longer what enforces anything.** "The chokepoint must be able to read the marker"
is one of the two reasons given above for a name prefix over an `info={}` dict,
and it is now void: the chokepoint reads a table name (ADR 0045) and the sweep
reads a table's whole column list, and neither needs the prefix to be accurate.
The decision still stands on the remaining reason alone — the name is in front of
whoever writes the query, not only in front of whoever wrote the definition — and
this ADR is still not superseded. An `info={}` dict would now be a defensible
choice for a *new* schema; renaming these columns to adopt one would not be,
because a rename is a migration per column bought with no enforcement gain.

**What it cost, and how far it reaches.** Three things, and none of them should
be read as smaller than it is:

- **It closes the direction on LMS-owned tables only.** An LMS-owned column
  landing on a table outside the guarded set — a column on `person`, a new
  relation from E1's sync — is invisible to this sweep and to ADR 0045's
  chokepoint alike, for the same reason this record gave in the first place:
  ownership is a fact about where data comes from, and no walk of
  `Base.metadata` recovers it once the marker is missing. What table grain buys
  is that on the tables §2.1 *does* name, the marker's accuracy stops mattering.
- **A Pulse-owned column on one of those tables now costs an entry.** It must be
  recorded in `PULSE_OWNED_COLUMNS` with a reason, and that entry is a claim
  nobody re-checks: the entries are required to name real columns, so an
  exception cannot outlive its column, but nothing can check that the reason is
  still true.
- **It reads `Base.metadata`, not the database.** A column that exists only in a
  migration is invisible to it. That is the right side to read for a marker the
  authz layer resolves through the ORM, as this record argues above, and it is
  still a limit.

[ADR 0069](0069-three-rules-held-by-a-docstring-are-swept-out-of-the-source.md)
records why the mechanism is a sweep rather than a session-level hook.
