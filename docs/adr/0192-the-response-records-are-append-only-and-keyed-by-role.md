# 0192 — The response loop's two records are append-only, keyed by role, and are their own audit

**Status:** Accepted. Superseded in part by [ADR 0193](0193-the-hold-reads-a-per-course-policy-row-fixed-at-report-open.md): a policy row now covers one course, and its index is `(course_id, sequence)`.
**Date:** 2026-10-11
**Ticket:** [E7-01](../tickets/e7/E7-01-response-records-and-name-channel.md)

## Context

SPEC §5.3 lets an instructor publish a short response to the week's report, lets
the Lead Faculty respond on the instructor's behalf, and lets a lead require a
response for their courses. The owner's rulings for E7 (`../tickets/e7/README.md`)
settle the behaviour: a policy covers only its setter's own courses in a prefix
(ruling 1); every edit is a new row and the latest is what students see (ruling
3); a chair acts as lead for a course with no lead (ruling 5); and these two
tables are the record, with no `audit_log` row (ruling 7). They leave open how a
row records the on-behalf case, and how a person who both leads courses and
chairs the department is keyed.

## Decision

Two tables in `backend/app/models/loop.py`, created by M1 (`2c3d5a0de424`):

- **`instructor_response`**: `section_id`, `week_id` (the course week, as
  `weekly_summary` keys it), `term_id`, `author_person_id` (`RESTRICT`), `role`,
  `ai_seeded`, `body`, `published_at` and `sequence`. The week belongs to the
  section's term: two composite keys, `(section_id, term_id) → section (id,
  term_id)` and `(week_id, term_id) → week (id, term_id)`, the pattern `response`
  uses ([ADR 0018](0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)).
- **`response_policy`**: `prefix_id`, `set_by_person_id` (`RESTRICT`), `role`,
  `mode`, `set_at` and `sequence`.

**On-behalf is the role.** A response records the role its author wrote under:
`INSTRUCTOR`, `LEAD_FACULTY`, or `CHAIR` for the chair acting as lead. There is no
separate on-behalf flag that could disagree with it.

**A policy row is keyed by prefix, person and role.** A person who both leads
courses and chairs the department may hold two switches in one prefix. The
`LEAD_FACULTY` row covers the courses in the prefix that `authz.lead_review_courses`
gives them as `LEAD_FACULTY`, and the `CHAIR` row covers the ones it gives them as
`CHAIR` (the department's courses that nobody leads). The two sets cannot
overlap. The latest row for a (prefix, person, role) is the policy in force.
E7-02 builds that lookup.

**Append-only, ordered by `sequence`.** `sequence` is a database identity column,
as `moderation_state.sequence` is
([ADR 0187](0187-moderation-verdicts-govern-the-read-path.md)), and "latest"
reads it, never a time. The two time columns are written by the application from
`services/clock.now`, so the development clock stays coherent. `pulse_app` holds
`SELECT` and column-grain `INSERT` on both tables, without `id` or `sequence`, and
no `UPDATE`, `DELETE` or `TRUNCATE`
(`backend/app/views_sql/response_loop_grants_v001.sql`).

**Who may write a row is checked when it is written**
(`backend/app/views_sql/response_loop_guard_v001.sql`). A grant cannot say who
a row may name, so each table has a `BEFORE INSERT` trigger, `SECURITY DEFINER`
and owned by the NOLOGIN `pulse_response_guard_definer`, which reads the grants
and mappings and writes nothing. `pulse_app` holds no `EXECUTE` on either
function. A refusal is SQLSTATE 42501 and names no person.

- A response is refused unless its author holds the stated role for the
  section: `INSTRUCTOR` the section's `INSTRUCTOR` grant; `LEAD_FACULTY` the
  assignment and the mapping for the section's course; `CHAIR` the chair of
  the course's department, where nobody leads the course.
- **One author per section-week** (ruling 3): a response is refused when the
  section-week already holds a row by somebody else. The trigger first takes a
  transaction-scoped advisory lock on the section-week, so two writers racing
  for one week are serialised and only the first lands.
- A policy is refused unless its setter holds the stated role in the prefix:
  `LEAD_FACULTY` the assignment and the mapping for at least one course in the
  prefix; `CHAIR` a `CHAIR` assignment on the prefix's department.

**The rows' own rules sit in the database.** The roles and the mode are `CHECK`ed
vocabularies. The text holds at least one character Python's `str.strip()` would
keep, and at most `RESPONSE_TEXT_MAX = 4000` characters, one constant the `CHECK`
is written from. `ai_seeded` is `NOT NULL`.

**No `audit_log` row** for a response, an on-behalf response or a policy change.
The tables name the person and the role, so they are the record. SPEC §8's
`audit_log` line no longer claims either.

**The downgrade refuses** while either table holds a row, as the E6 moderation
downgrades do.

## Alternatives rejected

- **A boolean `on_behalf` beside the author.** It can say "on behalf" for an
  instructor's own response. The role says everything the flag would, and more.
- **A policy keyed by prefix and person only.** A lead who chairs the department
  would then hold one switch for two different course sets, and turning it off as
  chair would turn it off as lead.
- **The writer check in the service that will write the rows (E7-02, E7-03)
  only.** The staff-name definer answers whoever a row names, so a row written
  around the service would hand a name to the application connection.
- **A unique constraint for one author per section-week.** Every edit is a new
  row by the same author, so no unique key over the existing columns says
  "one author", and a constraint cannot read the other rows.
- **A `now()` default on the time columns.** The dev clock moves the application's
  time and not the server's, so a response would carry a time that disagrees with
  every deadline computed beside it.
- **An `audit_log` row as well.** `audit_log.subject_user_id` must hold a student,
  and a second record of one event disagrees the first time either is written
  alone.

## Consequences

- E7-02 and E7-03 write through these grants and add no migration, and map the
  trigger's 42501 to their own refusals.
- `response_policy` has one index, `(prefix_id, set_by_person_id, role,
  sequence)`, for the one read it is made for: the latest row for a prefix,
  person and role. `instructor_response` has one, `(section_id, week_id)`.
- A response's author is a `person` key. Its name reaches a reader only through
  the staff-name definer ([ADR 0191](0191-a-staff-name-reaches-a-reader-through-one-definer.md)),
  which answers a published response's author to readers of the section.
- `instructor_response.body` is staff-written text published to students. Nothing
  structural stops a person typing a name into it, as with
  `moderation_state.reason`.
