# 0136 — The grade passback writer holds one table in the catalog and one column in the database

## Context

`section` is LMS-owned. SPEC §2.1 and §8 make it a table Pulse never hand-edits,
and `app.services.authz.guard_write` refuses a write to it unless the writer is
in `SANCTIONED_WRITERS`. Two writers were catalogued before this ticket:
`launch_provisioning`, which discovers courses and sections, and `roster_sync`,
which writes members, enrollments and the teaching instructor's row.

E3-05 records the id of the line item a platform served on
`section.ags_line_item_url` (ADR 0128), so SPEC §3.4's participation score can be
posted without walking a container again and ADR 0052's retry identity has
something to address. That is a write to `section` by a path neither existing
writer owns, and E3-02 created the column while deliberately granting nothing:
"E3-05 is its writer and is the ticket that spends the privilege."

Two layers have to be settled and they are not the same question. The
application-layer catalog decides which named writer may pass the chokepoint for
which table. The database decides what the application's connection can do at
all, and it is the layer that still holds when a caller does not call the guard —
which ADR 0045 names as the way a chokepoint is bypassed.

## Decision

**A third catalogue entry, holding one table.** `SANCTIONED_WRITERS` gains
`"grade_passback": frozenset({"section"})`, and `app.services.grading` resolves
its sanction once at import. Every write of `ags_line_item_url` is preceded by
`guard_write(table="section", sanction=SANCTION)` spelled in that module.

**A column-scoped grant, and only that column.**
`backend/app/views_sql/grade_passback_grants_v002.sql` issues `GRANT UPDATE
(ags_line_item_url) ON public.section TO pulse_app`, executed by migration
`e5b83c60f7a1`. Nothing else on the table is granted, and no other privilege
anywhere is touched.

**The downgrade revokes at column grain**, naming the column rather than the
table or the role.

## Alternatives rejected

**`GRANT UPDATE ON public.section`, table-wide.** One line shorter and it hands
the application connection `lms_section_code`, the launch binding columns and ADR
0021's four derived calendar columns — every one of which is a launch's own
discovery, and the section code is the identifier the confidentiality model's
section grain is keyed to. The catalog would still refuse a write through the
guard, and a write path that does not call the guard is exactly what the grant
exists to stop.

**No catalog entry, on the grounds that the column grant is narrower.** It would
make the database the only control, and a writer that never appears in
`SANCTIONED_WRITERS` is a writer nobody reviewing that list can see. The two
controls answer different questions — which code may write, and what the
connection can do — and neither is the other's backstop.

**No grant, on the grounds that the catalog already sanctions the writer.** The
mirror of the above, and worse: the write would fail at run time with a Postgres
permission error out of a Celery task, on a path a person is not watching.

**Reusing `launch_provisioning`'s entry**, since it already holds `section`. It
is the shortest change and it makes the catalog a worse record than it is now:
the launch writer would appear to be what records line-item ids, and the day
somebody asks what may write `ags_line_item_url` the answer would name the wrong
module. It would also spend `launch_provisioning`'s existing table grant on a
column it was never granted, since the database narrowing is per column.

## Consequences

- Adding a table to `grade_passback` is a visible diff in
  `tests/unit/test_a_sanctioned_writer_satisfies_the_chokepoint.py`, whose
  expected catalog is an equality, and adding a privilege is a visible diff in
  `RUNTIME_COLUMN_PRIVILEGES` in `tests/integration/test_identity_grants.py`.
  Both were edited by E3-05's own test commit.
- E3-06 posts scores and appends to `grade_sync` and `ags_call`; both of those
  are E3-02's grants and neither is a write to an LMS-owned table, so E3-06
  needs no entry of its own. If it ever writes `section` again — a column
  recording the last successful post, say — it inherits this entry rather than
  adding one.
- The revoke's grain is a property nothing else in the suite would notice, since
  the privilege inventory is pinned at head. It has its own test
  (`tests/integration/test_the_line_item_grant_is_given_back_by_a_downgrade.py`)
  because a table-grain revoke against a column ACL reads as correct, runs
  without error, and leaves the privilege exactly where it was.
