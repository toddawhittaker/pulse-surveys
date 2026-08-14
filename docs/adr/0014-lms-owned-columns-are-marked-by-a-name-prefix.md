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

The mechanism has to survive two things. It has to be readable by the
authorization chokepoint E0-11 builds, which is a different module from the
models. And it has to be hard to omit — the failure this marker exists to
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
distinguishes it from a Pulse-owned one. Closing that requires the write path,
so the enforcing check belongs in [E0-11](../tickets/e0/E0-11-authz-skeleton.md),
where the question becomes answerable in the form it is actually asked — does
the chokepoint refuse a write to this column. Until then the suite carries a
trap-line of unprefixed spellings that must not appear beside the marked ones,
which catches the regression and does not pretend to catch the omission.
