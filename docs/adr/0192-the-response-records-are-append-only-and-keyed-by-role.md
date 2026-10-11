# 0192 — The response loop's two records are append-only, keyed by role, and are their own audit

**Status:** Accepted
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
  `weekly_summary` keys it), `author_person_id` (`RESTRICT`), `role`, `ai_seeded`,
  `body`, `published_at` and `sequence`.
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
- **A `now()` default on the time columns.** The dev clock moves the application's
  time and not the server's, so a response would carry a time that disagrees with
  every deadline computed beside it.
- **An `audit_log` row as well.** `audit_log.subject_user_id` must hold a student,
  and a second record of one event disagrees the first time either is written
  alone.

## Consequences

- E7-02 and E7-03 write through these grants and add no migration.
- A response's author is a `person` key. Its name reaches a reader only through
  the staff-name definer ([ADR 0191](0191-a-staff-name-reaches-a-reader-through-one-definer.md)),
  which answers a published response's author to readers of the section.
- `instructor_response.body` is staff-written text published to students. Nothing
  structural stops a person typing a name into it, as with
  `moderation_state.reason`.
