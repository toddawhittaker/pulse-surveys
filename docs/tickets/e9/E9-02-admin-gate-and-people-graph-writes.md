# E9-02 — The admin gate and the people-graph writes

**ID:** E9-02
**Branch:** `e9/admin-gate-and-people-graph-writes`
**Depends on:** none
**Lane:** heavy
**Why this lane:** it adds `require_admin` to `backend/app/api/deps.py`, new
`SECURITY DEFINER` functions under `backend/app/views_sql/` that write
identity tables (`person`, `role_assignment`, `lead_faculty_mapping`,
`web_login_subject`), and audit rows; its migration creates and grants on
identity tables' writers and alters `audit_log`.
**Size:** L
**Security-relevant:** these are the only writes to the people graph. A
defect here lets a non-admin create a dean, lets anyone write a teaching
grant the LMS owns, drops the audit row that ruling 1 makes the control, or
links someone else's web login to a privileged person.

## Context

`pulse_app` holds no write on the people graph today; the seed writes it, and
a web-login linkage is written by hand (ADR 0097). SPEC §6.3 puts the People &
reporting editor and the Lead Faculty mapping table in the admin console. This
ticket builds the writes and the admin's reads underneath that editor; E9-06
builds the service, routes and CSV on top.

**Ruling 1.** The editor grants every Pulse-owned role (`LEAD_FACULTY`,
`CHAIR`, `ASSISTANT_DEAN`, `DEAN`, `VP_ACADEMICS`, `CARE`, `ADMIN`) to any
person, the acting admin included. There is no refusal of Care, Admin or
self-targeted grants. The control is the audit: every grant and every
revocation writes one `audit_log` row in the same transaction, and a write
whose audit row cannot be written is not committed. SPEC §6.2 now says so.

**Decision 11.** `INSTRUCTOR` assignments are LMS-owned (§2.1, §6.3) and are
refused, as are edges whose child is an `INSTRUCTOR` assignment. Teaching
grants keep their one writer, the roster sync.

**Ruling 7.** Revoking an assignment deletes it. An assignment that others
report to cannot be deleted until they are re-pointed; the existing `RESTRICT`
on `reports_to` decides that, and the definer turns the database's refusal into
a named refusal rather than a 500.

**The writes, each an admin-checked definer** (the reader is checked inside
the function, as in `section_staff_names_v001.sql`; owned by a NOLOGIN role;
`pulse_app` holds `EXECUTE` and nothing else on the tables):

- create a person (name, category) and edit a person's name and category;
- grant a role assignment at a scope node; revoke one; set or clear its
  `reports_to` (ADR 0044's trigger still refuses an edge that does not climb);
- map a course to a lead person and unmap it (one lead per course, by the
  existing unique constraint);
- link and unlink a web-login subject to a person.

**The admin's reads,** also admin-checked definers: people with their names
and categories, assignments with their scope and parent, mappings, and
linkages. They answer no student, no `user_identity` and no enrollment.

**The audit row.** `AuditAction` gains members for a role granted, a role
revoked, an edge set, a mapping changed and a linkage changed. Each row names
the acting admin, the person written about, and (for an assignment) the role
and scope node. `audit_log.subject_user_id` is NOT NULL today because its one
action names a student; the migration relaxes it for the new actions, as its
own column comment says the ticket adding such an action does, and adds a
nullable subject person column. A Care grant is told apart by its role, so
E10's access log can show it.

Read first: SPEC §2, §2.1, §4, §6.2 and §6.3; ADRs 0001, 0041, 0044, 0071,
0097 and 0196; `models/identity.py` and `models/audit.py` whole;
`views_sql/section_staff_names_v001.sql` and
`views_sql/teaching_grant_end_v001.sql` (the definer pattern);
`20261011_2c3d5a0de424_the_response_records_and_the_staff_name_channel.py`
(the migration pattern); `api/deps.py`'s `require_leadership` and its 403.

## Owns

- `backend/app/api/deps.py`: `require_admin` and `csrf_verified_admin`.
  A session in another role gets ADR 0196's 403 marked `insufficient_scope`;
  a missing or bad token gets the existing 401.
- `backend/app/views_sql/people_graph_v001.sql` (new): the write and read
  definers, their owner and grants.
- `backend/app/models/audit.py`: the new actions and the subject column.
- Migration **`e9a1d0c3f201`**, `down_revision = "7f679faf4b8d"`.
- `tests/integration/test_identity_grants.py`: the new grants' rows.
- `backend/app/copy/admin_people.py` (new): the definers' named refusals as
  governed sentences, and the `admin_people` surface placed in the copy
  inventory's `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` with its reason (the
  people pages show staff records and no student's data). README decision
  15.
- SPEC §13: the new view file.
- ADR **0200** (the admin's definers, every role grantable, revoke deletes,
  the audit row as the control).

## Reuse, do not rewrite

The definer pattern and NOLOGIN owner of ADR 0191; ADR 0044's edge trigger;
the existing unique constraints on `lead_faculty_mapping` and
`web_login_subject`; `person_of`; ADR 0196's `insufficient_scope` 403.

## Done when

1. **Only an admin writes.** Each write definer, called with a person key that
   holds no live `ADMIN` assignment, writes nothing and raises a named
   refusal; called by an admin, it writes. Tested for every definer with a
   dean, a Care holder and a person with no assignment as the refused
   callers, beside the admin as the passing twin. Reached through the
   connection production uses (MISTAKES entry 46).
2. **`pulse_app` cannot write around the definers.** As `pulse_app`, a direct
   `INSERT`, `UPDATE` or `DELETE` on `person`, `role_assignment`,
   `lead_faculty_mapping` and `web_login_subject` is refused by the database.
3. **Every Pulse-owned role is grantable, to anyone (ruling 1).** An admin
   grants `CARE` to another person, `ADMIN` to another person, and `CARE`,
   `ADMIN` and `DEAN` to their own person; each write succeeds.
4. **`INSTRUCTOR` stays LMS-owned (decision 11).** Granting or revoking an
   `INSTRUCTOR` assignment, and setting an edge whose child is one, are
   refused with a named refusal; the roster sync's own writes are unchanged.
5. **Every write is audited, in the same transaction.** Each grant, revoke,
   edge change, mapping change and linkage change leaves exactly one
   `audit_log` row naming the action, the acting admin's person, the person
   written about and, for an assignment, its role and scope node. A Care
   grant's row carries the `CARE` role. When the audit insert is made to
   fail, the write is not committed (planted failure, row count unchanged).
6. **Revoke deletes (ruling 7).** Revoking a childless assignment deletes the
   row. Revoking one that another assignment reports to is refused with a
   named refusal naming the children's count, and deletes nothing; after the
   children are re-pointed, it succeeds.
7. **Edges still climb.** Setting an edge from a `CHAIR` to a `LEAD_FACULTY`
   parent is refused by ADR 0044's trigger, surfaced as a named refusal, not a
   500.
8. **The linkage is admin-only and one-to-one.** Linking a web-login subject
   already linked to another person is refused; unlinking then linking
   succeeds; each is audited.
9. **The admin's reads answer no student data.** The read definers' result
   columns are compared against an allow-list: no `user` key, no
   `lms_user_id`, no email and no `user_identity` column. A non-admin caller
   gets nothing.
10. **The route gate.** `require_admin` answers a missing token 401, a
    leadership, instructor, student or Care session 403 with
    `insufficient_scope`, and an admin session through. Driven over HTTP on
    one stub route the tests mount (MISTAKES entry 47), since the real routes
    are E9-06's.
11. **The surface is placed.** The copy inventory places `admin_people` in
    `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` with its reason, and collects the
    refusal sentences under it.
12. **The records match.** ADR 0200 is written and indexed. ADR 0097's manual
    linkage step gains a line pointing at the definer. Every ADR or docstring
    that says Care and Admin are separated "in code" on the assignment path is
    found by grepping the fact and corrected (MISTAKES entry 1).
    `PERSON_TABLES` is checked against any table this ticket adds.

## Shares files with

- `api/deps.py`: 01 and 04.
- `tests/integration/test_identity_grants.py`: 03 and 12.
- `docs/SPEC.md` §13 and `docs/adr/README.md`: other ticket owners.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 17, 35, 46 and 47.

## Known traps

- **Entry 17.** Every definer sets `search_path` and names tables with their
  schema.
- **Entry 46.** A suite that drives the definers through the migrating engine
  has not tested `pulse_app`'s grants.
- **Entry 1.** "Enforced in code" appears in more records than SPEC §6.2. Grep
  the phrase and its paraphrases.
- **The audit column.** Relaxing `subject_user_id` must not let an
  `IDENTITY_REVEAL` row lose its subject: keep a check that the reveal action
  still names one.

## Not in this ticket

- `services/people.py`'s sorting, paging, CSV and dry run, and the routes
  (06).
- The editor screens (10).
- Showing the audit rows to anyone (E10).
