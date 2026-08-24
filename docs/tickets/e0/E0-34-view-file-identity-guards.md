# E0-34 — A view file that reads identity must fail on that ground

**ID:** E0-34
**Branch:** `e0/view-file-identity-guards`
**Depends on:** E0-10, E0-11

## Context

Three findings from two different reviewers, on two different tickets, that turn
out to be one hole in one place. They were tracked as [E0-32](E0-32-gate-gaps-the-selftest-found.md)
items 2 and 3 and [E0-27](E0-27-review-debt-from-e0-11.md) item 2.

The hole: **`backend/app/views_sql/` is a directory of SQL files that create
owner's-rights views, and nothing reads those files looking for identity.**

- `test_no_view_reads_a_column_the_identity_marker_names` reads `pg_depend` out
  of the migrated database, so it only sees views a migration has executed. A
  file that joins `user_identity` and selects a name sits in the canonical
  directory and passes that invariant **vacuously**.
- `view_sql_files()` is consumed by the file-presence check and the
  schema-qualification sweep. Neither looks for identity columns.
- The file goes live the day somebody appends its name to a `SCRIPTS` tuple in an
  unrelated ticket, and no grant is consulted on the way, because all five views
  are owned by `pulse_admin` with `security_invoker` off. That ownership is
  deliberate and load-bearing — it is what lets `pulse_app` read
  `role_assignment` and the containment tables while holding no grant on any of
  them — and its consequence is that **the grant model does not protect the view
  files themselves.**

**And the guard that does fire points away from the defect.** The same file is
caught by `test_every_relation_a_view_sql_file_names_is_schema_qualified`, whose
failure message is about missing `public.` prefixes. The invited repair is to add
four prefixes, after which the identity join and the grant are untouched and the
pipeline is green. A red whose message points away from the defect is worse than
no red, because it spends the one moment somebody was looking.

What stands there today is [ADR 0041](../../adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md)'s
rule — a view ships as a new immutable versioned file, so the join appears in a
diff somebody reads. That is review, not the server refusing it, and E0-11
tripled the number of owner's-rights views sitting over the tables the resolver
must not reach past.

Read first: SPEC §4 and §4.1, [ADR 0001](../../adr/0001-identity-separation-by-database-role.md),
ADR 0041, and `docs/MISTAKES.md` entries 2 and 3.

## Scope

One guard, reading `views_sql/*.sql` as text, that fails when a file names an
identity-bearing column — whether or not a migration has executed it, and whether
or not the file is in a `SCRIPTS` tuple.

Two things the guard has to get right, because both were found by measurement
rather than by reading:

- **It must not rely on the file being in `SCRIPTS`.** That is the whole of item
  2: reachability is what the current check tests, and reachability is what
  changes in an unrelated ticket.
- **Its failure message must name the identity column.** That is the whole of
  item 3. If the schema-qualification sweep fires first on the same file, the
  author fixes the prefixes and moves on.

The identity-marker vocabulary already exists — the marker sweep in
`tests/integration/test_identity_column_marker.py` is where it lives, including
the one-hop walk and the `("name", "email")` fragments E0-10 corrected. Reuse it
rather than writing a second list; two lists in two files with nothing comparing
them is `docs/MISTAKES.md` entry 3's shape.

## Out of scope

- **Making the server refuse it.** That would mean `security_invoker` on views
  that need owner's rights to work, and it is not what E0-11 or E0-10 chose. If
  the answer here turns out to be "nothing catches it and that is acceptable
  given ADR 0041", say so plainly in the record — E0-27's criterion allows that
  and E0-32's does not, which is a disagreement this ticket resolves in favour of
  building the guard.
- The catalog comparison. That is [E0-33](E0-33-catalog-drift-assertions.md).
- §4.1 item 1, which E0-10 defers to E2 on the record.

## Acceptance criteria

- [ ] A `views_sql/*.sql` file naming an identity column fails a test whose
      message names the identity column, whether or not the file is in a
      `SCRIPTS` tuple and whether or not a migration has executed it.
- [ ] The schema-qualification sweep firing on the same file does not mask it —
      demonstrate by planting a file that trips both and confirming the identity
      failure is visible in the output.
- [ ] Verified by mutation: plant the file, watch the named test fail, restore.
      Confirm the plant landed before believing the red.
- [ ] If ADR 0041 stops being the only thing holding this, it gains a line
      saying so.

## Definition of done

**Tests apply**, and they are the deliverable.

**Docs apply, briefly** — the ADR 0041 line above.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies.** This is the one route [ADR 0001](../../adr/0001-identity-separation-by-database-role.md)'s
grants cannot close.
