# 0064 — The demo seed is idempotent by matching natural keys, not by reloading

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-17

## Context

E0-17's scope says `scripts/seed.py` is "idempotent: running it twice leaves the
same database state rather than duplicating rows", and its acceptance criteria
add "no duplicate rows and no constraint violation". Neither says *how*, and the
two obvious readings differ in what they leave behind.

Every primary key in this schema is a server-generated uuid
([ADR 0016](0016-primary-keys-are-database-generated-uuids.md)), so a second run
cannot name the row a first run created. Something else has to identify it.

A developer runs `make seed` again after every schema change. The failure to
avoid is not an error — it is a second copy of the institution, where every
roll-up count is doubled, every purview test has two answers, and nothing is red.

## Decision

Every row is found by the **natural key the schema already enforces**, and
re-used where it is found. One helper, `upsert(session, model, key, **values)`,
does it for every table:

| Table | Natural key |
|---|---|
| `institution` | `name` |
| `college` | `(institution_id, name)` |
| `department` | `(college_id, name)` |
| `prefix` | `code` |
| `course` | `(prefix_id, lms_number)` |
| `term` | `(institution_id, name)` |
| `start_letter_map` | `(term_id, letter)` |
| `section` | `(course_id, term_id, lms_section_code)` |
| `lti_platform` | `(issuer, client_id)` |
| `lti_deployment` | `(lti_platform_id, deployment_id)` |
| `user` | `(lti_platform_id, lms_user_id)` |
| `user_identity` | `user_id` |
| `person` | `user_id` |
| `role_assignment` | `(person_id, role, the one populated scope column)` |
| `lead_faculty_mapping` | `course_id` |

**Every one of those is a `UNIQUE` constraint in the schema, with one exception.**
`role_assignment` carries no uniqueness rule at all — E0-09 declined to invent
one, because two chairs of one department is a policy question §6.3's People
editor owns — so the key in that row is a property of *this seed's own data*
rather than of the table. That difference is the one thing about this decision a
reader has to hold, and the consequences below say what it costs.

Two consequences of that choice are deliberate:

- **`person` is matched on `user_id`**, which is why every demo person is linked
  to a `user` row even though the schema allows a person with none (a dean who
  has never launched still supervises chairs, [ADR 0024](0024-the-person-to-user-link-is-carried-by-person.md)).
  `person` has no other unique column, and matching on `identity_name` would key
  the graph to a display string.
- **Non-key columns are compared before they are set**, so a second run over
  unchanged data issues no `UPDATE`, and a row edited by hand is put back the way
  the file describes it.

The whole load is one transaction. A run that fails half way leaves nothing, so
the next run does not build on a partial institution.

## Alternatives rejected

**Reload: delete everything this script owns, then insert it fresh.** Simpler to
write and the reason it loses is what it does to everybody else's fixtures. New
uuids on every run means a developer's bookmarked URL, a Playwright fixture's
recorded id and anything E9 built against yesterday's seed all point at rows that
no longer exist. It is also a `DELETE` this script cannot get right: `ON DELETE
RESTRICT` is on every containment key by design, so the delete order is a second
copy of the dependency graph, and a table added by a later ticket would be missed
silently.

**`INSERT ... ON CONFLICT DO UPDATE`.** The idiom, and it very nearly wins. It
loses on `role_assignment`, which has no unique constraint to name in the
conflict target, so the one table where the seeding is least obvious would need
the select-then-insert shape anyway — and then there are two mechanisms doing one
job, and the reader has to know which tables use which. One boring path
everywhere beat one clever path with an exception.

**A marker row, or a `seeded_at` column, so a second run can exit early.** It
makes the seed all-or-nothing: a run interrupted after the courses and before the
people would be recorded as done, and the repair is to work out what is missing
by hand. Matching per row means an interrupted run is finished by the next one.

**Deterministic uuids — uuid5 over a namespace and the natural key.** Genuinely
attractive, and it would make the seed reproducible across databases. Rejected
because it puts the key generation in the application, which contradicts the
`gen_random_uuid()` server default every table already carries, and because the
namespace becomes a thing that must never change or every future seed writes a
second copy of the institution.

## Consequences

**Editing this file's data changes the database on the next run, and deleting
from it does not.** Rename a course title and the next `make seed` updates the
row; remove a course from `COURSES` and the row stays, because nothing here
deletes. That is the right default for a demo — an accidental deletion should not
take a developer's data with it — and it means a genuinely removed row is removed
by hand or by dropping the database.

**The `role_assignment` key is this seed's property, not the schema's.** If a
later edit gives one person two assignments in the same role over the same node —
which the schema permits — the second would be matched onto the first and never
written. That is a defect the file would have to notice, and the reason the key
is spelled out here.

**`tests/integration/test_demo_seed_script.py` deliberately does not pin uuids.**
It compares rows by their values with every foreign key resolved into the label
of the row it names, so both this decision and the reload it rejected would pass.
The test is not evidence for this choice; this record is.
