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

**The parser has to be total, because it runs before any row exists.** `NOT
NULL` columns mean nothing can be inserted and fixed up later, so the code is
read while it is still whatever the platform sent — `String(16)` is a column
width and SQLAlchemy does not enforce it in Python. That is what makes an
unbounded parse a 500 rather than a truncation, and it is why
`parse_section_code` refuses a code longer than `SECTION_CODE_MAX_LENGTH`
before reading any part of it: past `sys.get_int_max_str_digits()` digits,
`int()` raises a `ValueError` nobody can catch on purpose. The bound is the
column's own width rather than a limit on the ordinal, so it decides nothing
§2.2 leaves open. A security review found the leak on this branch; the incident
is `docs/MISTAKES.md` entry 15.

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

**Amended by E0-35, 2026-08-19: "exactly one writer" now has a check behind it,
and the check is syntactic.** When this record was written the rule was
convention. Two tests catch a second writer that *disagrees* with
`apply_section_code`, by comparing what a section ends up with against what the
code and the term's map say it should be; a second writer that **agrees** was
invisible to both, and E0-08's security review grepping and finding no bypass is
a measurement of one afternoon rather than a property of the codebase.

`tests/unit/test_a_sections_derived_calendar_has_one_assignment_site.py` asserts
it now: every place under `backend/app/` that assigns `length_weeks`,
`start_date`, `end_date` or `modality` onto a section is inside
`backend/app/services/section_codes.py`.

**The grain is the module, not the function.** This record names the function,
and a sweep at function grain would go red on a refactor that split a private
helper out of it — a change that alters nothing about the rule, because a helper
in that module called by that function is the same path.

**What the check does not see**, so that nothing here is cited as more than it
is:

- **It is syntactic, not dataflow.** It sees the shape of an assignment, never
  what is being assigned to. `setattr(row, name, value)` with a computed name, a
  bulk update built from a dict assembled at run time, or a write through a
  helper that takes the column name as an argument are invisible.
- **It reads the source rather than the running application**, so a second
  writer reached through a helper in another module, a mapper event, an ORM
  cascade or a library call is invisible too.
- **It says nothing about correctness.** A second module assigning these four
  columns with the *right* values fails it, and a `section_codes.py` assigning
  the wrong ones passes. The two tests over the derivation are the other half,
  and neither implies the other.

E0-35 offered amending this record to say the rule is unenforced as the
alternative to building the check. The check exists, so that branch does not
apply — but its own positive control is load-bearing: if the sweep ever cannot
find `apply_section_code`, it cannot see how this codebase sets these columns,
and its silence about every other module is worth nothing. The failure message
says so, because a red control there is that decision to re-make rather than a
line to adjust.
[ADR 0069](0069-three-rules-held-by-a-docstring-are-swept-out-of-the-source.md)
records why the mechanism is a sweep rather than a session-level hook.
