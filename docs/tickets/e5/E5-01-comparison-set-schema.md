# E5-01 — The comparison-set schema

**ID:** E5-01
**Branch:** `e5/comparison-set-schema`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** a new table and its grants under
`backend/app/models/` and `backend/migrations/` — heavy rows both. The table
holds no person and no response; the risk is a constraint gap that lets an
invalid set exist for the resolution service to trust.

## Context

SPEC §13 names `benchmark.py` for `comparison_set`: named,
leadership-defined sets. The default set is computed, never stored (§13), so
this table holds only what leadership deliberately creates. Breakdown
decision 3 rules the shape: a set declares **one length and one level**, and
its membership is a list of **courses** of that level; resolution (E5-04)
selects member courses' sections of the declared length, across terms.
Course-level membership is what survives past-referencing — a section-level
set would age out every term.

Read first: SPEC §2.2 (the length set), §5.1 (the comparison-sets
paragraph), §8 (the level bands and how level derives from the course
number), §13; `backend/app/models/org.py` (course and section shapes, and
how derived attributes are held); an existing model+migration pair for the
conventions (`backend/app/models/report.py` and its E4-02 migration).

## Scope

- `backend/app/models/benchmark.py`: the `comparison_set` table (name,
  declared length, declared level, creator, timestamps) and its membership
  relation to courses.
- Database constraints making decision 3's rule unstorable to break: the
  declared length is one of §2.2's length set; the declared level is one of
  §8's five; a member course's level equals the set's declared level,
  enforced at the database, not only in a route.
- **No grants, on purpose** — corrected at cut time to follow E4-02's
  precedent ("a privilege lands in the change that spends it", quoted in
  `weekly_summary_grants_v001.sql`): the first reader is E5-04 and the
  writer is E5-06, so each grants what it spends in its own PR. This
  ticket proves the *absence* of privilege instead.
- A migration taking the first chain slot off `e5a2b81c47d3` (before E5-03;
  whichever merges later re-points).
- The ADR for decision 3: membership unit and declared-pair shape, with the
  rejected alternatives (section membership, filter-defined sets).

## Acceptance criteria

1. A set with a length outside §2.2's set, or a level outside §8's five, is
   refused by the database — asserted by attempting the insert, both sides
   of each boundary.
2. A member course whose level differs from the set's declared level is
   refused at the database; a matching one is accepted — the pair proven
   together, so the refusal is the constraint's and not an accident of the
   fixture (MISTAKES entry 3).
3. Deleting a course that is a member does not orphan silently: the
   behavior (restrict or cascade) is chosen in the ADR and asserted.
4. The table carries no identity column and no response data; the
   identity-column marker sweep covers it.
5. `alembic upgrade`/`downgrade` both succeed; `alembic check` is clean.
6. Grants: `pulse_app` holds **no** privilege on the new tables, proven
   through the connection production uses (MISTAKES entry 46), not through
   the migrating engine — a refused SELECT and a refused INSERT, both
   asserted; and the `RUNTIME_BASE_TABLE_PRIVILEGES` equality record in
   `tests/integration/test_identity_grants.py` stays consistent with that
   in whichever direction the record's convention requires.

## Decisions this ticket settles

- **The member-deletion rule** (criterion 3): the recommendation is
  restrict — a set silently shrinking is a benchmark silently changing —
  with the ADR recording the alternative.
- **Whether a set may be empty.** The recommendation is yes at the schema
  (a set under construction), with resolution treating an empty set as
  suppressed; the service ticket asserts that half.

## Known traps

- **Constraints tested only through the ORM** — mutate the constraint in
  the migration (model-side is inert; the test database builds from
  migrations) and watch the test fail.
- **Level lives on the course as a derived attribute** — do not re-derive
  it here from the course number; read the stored column, one source
  (MISTAKES entry 13).

## Out of scope

- Resolution, minimums, past-referencing — E5-04.
- Routes and scoping — E5-06.
- Any UI — E5-09.
