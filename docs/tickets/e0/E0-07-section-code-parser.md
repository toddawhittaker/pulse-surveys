# E0-07 — Section-code parser and date derivation

**ID:** E0-07
**Branch:** `e0/section-code-parser`
**Depends on:** E0-05, E0-06

## Context

Section codes look like `R3WW` or `Q2FF`: a start letter encoding length and
start date via the term's start-letter map, an ordinal, and a modality suffix.
Everything about a section's calendar derives from that code plus the term —
nothing is hand-entered per section (§2.2). This is pure logic over the E0-06
tables and is the natural home for property-based tests.

Read first: SPEC §2.2 in full, §9.1 (the invariant suite mentions section-code
parsing across the full start-letter map), §8.

## Scope

- `backend/app/services/section_codes.py`: parse a code into start letter,
  ordinal, and modality; reject malformed codes with a specific error naming
  what failed.
- Derive `length_weeks`, `start_date`, `end_date`, and `modality` from the code
  and the section's term, reading `start_letter_map`.
- Modality mapping: `WW` online, `FF` face-to-face. Unknown suffixes are an
  error, not a silent default.
- Handle the 3-week case, which §2.2 numbers 2–7 rather than lettering.
- Add the derived section columns and populate them through this service, so
  there is exactly one path that sets them. **They are not on `section` yet.**
  E0-05 shipped that table with its course foreign key and `lms_section_code`
  and nothing else: a length or a start date has no value it could be given
  until this parser exists, and a start date additionally needs the term
  foreign key, which E0-06 adds. So the columns arrive with the code that fills
  them rather than as four nullable columns waiting for it.
- Hypothesis property tests across the full letter map: every letter in a seeded
  map round-trips to a length and a start date inside its term.

## Out of scope

- The two week axes — course week versus term week — as a *display* concern
  (E4 for the instructor report, E9 for aggregates). The offset arithmetic
  belongs here; the charts do not.
- Roster sync and launch-time ingestion that supply real codes (E1).
- The admin course-catalog viewer (E11).

## Acceptance criteria

- [ ] Every letter in the Fall 2026 seed map (§2.2) parses to the documented
      length and start date.
- [ ] `R3WW` and `Q2FF` parse to the values §2.2 describes.
- [ ] A code with an unknown start letter, an unknown modality, or a missing
      ordinal raises a distinct error naming the offending part.
- [ ] `end_date` equals `start_date` plus `length_weeks`, landing on the correct
      weekday, for every letter in the map.
- [ ] A section whose derived end date falls outside its term's dates is
      rejected, with a test covering it.
- [ ] Hypothesis generates letter-map and code combinations without finding a
      case where parsing succeeds but derivation produces a date outside the
      term.
- [ ] Course-week to term-week offset is computed and tested for a section that
      starts five weeks into a term.

## Definition of done

**Tests apply, heavily — this is the point of the ticket.** Unit tests for
parsing and derivation, Hypothesis property tests across the letter map per
§9.1, and explicit boundary cases for the 3-week numbered sections.

**Docs do not apply** — internal service with no operator surface yet.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies but is light.** Section codes arrive from the LMS, so
confirm parsing is total: no unbounded loop, no exception type that escapes as a
500, and no code path where a malformed code silently produces a valid-looking
section.
