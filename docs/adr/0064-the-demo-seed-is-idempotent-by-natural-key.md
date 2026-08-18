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
| `prefix` | `code` — **not scoped to anything; see below** |
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
rather than of the table.

### What a natural key here has to be, and the one that was not

An earlier version of this record listed the keys and stopped there, which hid
the distinction that matters. Matching on a natural key is only safe if the key
cannot match a row somebody else created. Every key above is one of two things:

- **Scoped to a row this seed created** — `(college_id, name)`, `(term_id,
  letter)`, `(course_id, term_id, lms_section_code)`, `user_id`, and so on. The
  parent was matched first, so the child can only be one of ours.
- **A root, matched by a value this file invents** — `institution.name` is
  `Pulse Demo University`, `lti_platform` is `(https://lms.pulse-demo.invalid,
  pulse-demo-tool)`. Nothing sits above these to scope them, so the safety comes
  from the value being one nobody else would choose.

**`prefix.code` was neither, and that is a defect this record shipped with.**
`prefix` is `UNIQUE (code)` across the whole table rather than per institution
([ADR 0017](0017-prefix-codes-are-unique-across-the-deployment.md)), and `MATH`
is a name a real institution uses too. So the match was not "find my prefix" but
"find *the* prefix", and the update that follows re-pointed a real one at Pulse
Demo University.

Measured against a database holding a real institution before the guard existed:
`MATH` moved from `Real Mathematics` to the demo's `Mathematics`, the real
`MATH 210` was reached by `(prefix_id, lms_number)` and its title overwritten
with `Calculus I`, and the run **exited 0 and printed its success line**. The
yield is an authorization change rather than a cosmetic one, because purview is
computed from the containment tree and from `lead_faculty_mapping`: demo
leadership gains purview over real courses, and the real lead loses the mapping
that granted theirs.

**The seed now refuses instead of adopting.** Where a prefix with a seeded code
exists and does not already belong to the department this file wants, it raises,
naming the code and the department that holds it — the same shape
`seed_calendar` uses for a term whose weeks it cannot reconcile. A prefix
already pointing at the wanted department is this seed's own row from an earlier
run and is reused, so the second run stays idempotent. Re-measured after the
guard: exit 2, the real rows untouched, and no partial demo institution left
behind, because the whole load is one transaction.

**The rule for anyone adding a table to this loader:** the key must be scoped to
a row the seed created, or be a value the seed invented. If it is neither,
refuse rather than match.

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
