# 0021 — A section's derived calendar is NOT NULL and has exactly one writer

**Status:** Accepted
**Date:** 2026-08-15
**Tickets:** E0-07

## Context

[SPEC §8](../SPEC.md): "section `length_weeks` and start/end dates derive from
the section code via `start_letter_map` — LMS-owned data is never hand-edited in
Pulse." [§2.2](../SPEC.md) adds the modality and says "nothing is hand-entered
per section". E0-07 adds those four columns to `section` and asks that they be
populated "through this service, so there is exactly one path that sets them".

What none of them says is whether a section may exist *without* them. The
derivation needs a row in its term's start-letter map, and that map is
admin-configured (§6.3), so a section can arrive from a roster sync for a cohort
nobody has configured yet.

`course.level` answers the analogous question with a stored generated column
([ADR 0015](0015-course-level-is-a-stored-generated-column.md)), which is not
available here: a generated column may only read its own row, and every one of
these four values comes from a row in another table.

## Decision

The four columns are **`NOT NULL`**, and
`app.services.section_codes.apply_section_code` is the only thing that writes
them. It reads the section's term from `section.term_id` rather than taking a
term as an argument, so no caller can derive a section's calendar from a term it
does not belong to.

A code whose start position the term's map has no row for, or whose derived
dates leave the term, is **refused** — the section is not written with a partial
or invented calendar.

No `CHECK` constraint ties the three calendar columns to each other.

## Alternatives rejected

**Four nullable columns, filled in by a later pass.** The shape that lets a
roster sync store every section it sees and derive later. Rejected because a
section with no length is invisible to §5.1's comparison sets and has no week
axis on any report, and nothing about the row says so — it is the quiet failure,
where refusing the section is the loud one. A cohort whose calendar an admin has
not configured is a configuration gap someone has to see, and E1 sees it as a
refused section rather than as a section that reports nothing for a term.

**A `CHECK (end_date = start_date + length_weeks * 7 - 1)`.** It would make the
inclusive convention of [ADR 0020](0020-a-sections-end-date-is-its-last-day.md)
unrepresentable-otherwise, which is the instinct this codebase usually follows.
Rejected as a second authority for one rule: the arithmetic already lives in the
one service path that produces these values from a map row the database
constrains, and a copy in the schema is a thing that can drift from it while
both look right. The same reasoning kept the bands out of a `CHECK` on
`lms_number` in ADR 0015.

**A composite foreign key carrying the term's dates onto `section`**, making
"the section ends inside its term" a local `CHECK` — the shape
[ADR 0018](0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)
uses for the two length rules. Rejected because that shape exists to check a
*stored configuration* value written by a hand that never called this service,
whereas a section's dates have exactly one writer, which already holds the term
and can compare against it. It would also add two more copied columns to the
leaf table that grows fastest.

## Consequences

A section cannot be created before its term's start-letter map has a row for its
start position. E1's roster sync therefore has a failure it must surface —
"this section could not be read" — rather than a row it can quietly store, and
E0-17's seed script must create a term's map before its sections.

**Editing a term's map does not re-derive the sections already derived from
it.** Nothing reconciles them, and no gate reports the gap: a section keeps the
dates it was written with, and only a comparison against the map would show
them disagreeing. This is the same shape ADR 0018 records for `week` rows after
a term's length changes, it has the same owners — E2's scheduling and E11's
calendar editor (§6.3), which is where a map is edited in the first place — and
whoever builds that owns the re-derivation.

Because the columns are `NOT NULL` and no test fixture may leave them empty, any
future test that inserts a `section` row directly has to invent all four. The
seeding helpers in `tests/integration/` already do, by type.
