# E1 — deferred items

Everything an E1 ticket deferred rather than fixed, in one place, so the end
of the epic gets a cleanup pass instead of an archaeology dig. Each entry
names the ticket and pull request it came from and keeps the "done when" that
governs it. An item leaves this file by being fixed (say where) or by being
handed to a named owner outside E1 (say whom); it is never silently dropped.

Every E1 pull request that defers something adds it here in the same PR.

## From E1-01 — view sweep closure (PR #92)

1. **The catalog whole-row rule misses the join form** (MEDIUM, deferred
   under the round's declared stopping rule). Postgres drops the whole-row
   dependency row (`refobjsubid = 0`) once a view also names any column of
   the same table, so
   `SELECT to_jsonb(u) FROM enrollment e JOIN "user" u ON u.id = e.user_id`
   is invisible to the catalog half. The file-text sweep catches every
   whole-row spelling the reviewer could write, and the catalog catches every
   column-grain one — complementary blindnesses whose union is total only
   because every live view must ship through a `views_sql/` file.
   **Done when** the catalog half flags a whole-row read of a guarded table
   in the presence of a join (compare the relation edge in `pg_depend`
   against the recorded column set, disambiguating via `pg_get_viewdef`),
   proved by the join-form planted control.

2. **`PERSON_TABLES` is a hand-written closed list.** Nothing guards that a
   future person table joins it. E1-05 and E1-11 are the tickets that could
   add one; their reviews must ask the question.
   **Done when** both reviews have asked it and recorded the answer, or a
   structural source for the list exists.

3. **The two E0-34 planted-file tests have a not-load-bearing message
   check.** Pytest assertion rewriting satisfies the check without the
   message being real; E1-01 made the same one-line fix to its own control
   and left these two.
   **Done when** both tests get that one-line fix.

4. **`test_every_read_view_is_created_from_a_sql_file_under_views_sql` is
   not `invariant`-marked.** The text/catalog complementarity in item 1
   rests on it, but it runs only in the ordinary suite, not the isolated
   §4.1 pass.
   **Done when** it carries the marker and the isolated pass collects it.
