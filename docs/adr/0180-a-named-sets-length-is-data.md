# 0180 — A named set's length is data, not a list in the schema

**Status:** Accepted — E5-14. Supersedes the length-set decision of
[ADR 0164](0164-a-named-comparison-set-is-courses-plus-one-declared-length-and-level.md);
the rest of ADR 0164 stands.

## Context

ADR 0164 held a named set's length to a hard-coded list,
`CHECK (length_weeks IN (3, 6, 8, 10, 12, 15, 16, 18))`, mirrored as
`CALENDAR_LENGTHS` in `app/models/benchmark.py`, citing SPEC §2.2. But §2.2's
first sentence is "The academic calendar is institution configuration, not
code", and the lengths it lists are Franklin's reference model. The E5
boundary's adr-docs-completeness review found the contradiction: an
institution running a 4-week section could not define a set for it, and
adding a length needed a migration. The owner ruled on 2026-09-22 that a named
set's length is data.

## Decision

- The `CHECK` on `comparison_set.length_weeks` becomes `length_weeks >= 1`,
  the same rule `section` has.
- `CALENDAR_LENGTHS` is removed.
- The definition form's options (`definition_options`) offer the distinct
  `section.length_weeks` values present in the database, sorted.
- A length below one week is refused with the existing copy key
  `LENGTH_NOT_A_CALENDAR_LENGTH`, whose sentence now reads "A comparison set's
  length is at least one week."

## Alternatives rejected

- **Keep the list and add lengths by migration.** Rejected because it keeps
  the calendar in code, which §2.2 says it is not, and every institution with
  a different calendar would need a schema change.
- **Validate against the per-term start-letter map.** ADR 0164 rejected this
  and the reason still holds: the map is one term's data and a set outlives
  terms. Offering the lengths sections actually carry, across every term, is a
  different rule: it reads what exists, and it never makes a stored set
  unsaveable, because the table only asks for at least one week.
- **Offer any positive number in the form.** Rejected because §5.1 asks the
  form to make invalid choices impossible, and a length no section runs
  resolves to nothing.

## Consequences

- The form offers exactly the lengths a comparison can resolve, so the UI half
  of §5.1's "impossible rather than erroring" now comes from the data.
- The API accepts any length of a week or more, including one no section runs
  (17, say). ADR 0164 refused 17 because nothing can resolve it. Such a set
  now stores and resolves to nothing, and every figure from it is suppressed
  (§4.1 item 7), which is what an empty set already did. That is the accepted
  cost of not keeping a calendar in the schema.
- The length set now lives in one place for a named set: the sections. SPEC
  §2.2 describes it, and nothing in code copies it.
- ADR 0164's rejected alternatives and its other decisions are unchanged.
