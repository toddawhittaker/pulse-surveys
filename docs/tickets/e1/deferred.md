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
   *E1-05 asked it and the answer is no.* It adds one table,
   `tool_signing_key`, holding an `id` and a private key PEM. It carries no
   subject, no name and no address, nothing joins it to a person, and nothing
   reads it until E1-06 signs with it — so `PERSON_TABLES` is unchanged.
   Recorded in [ADR 0082](../../adr/0082-the-tools-signing-key-lives-in-the-database.md)
   and beside the model. E1-11 still owes its half.

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

## From E1-05 — registration owns its endpoints and its keys

1. **A non-development deployment has no way to supply the tool's signing key.**
   Custody is a `tool_signing_key` row
   ([ADR 0082](../../adr/0082-the-tools-signing-key-lives-in-the-database.md)),
   and the only thing that writes one is the demo seed, which refuses to run
   anywhere but development (ADR 0063). So a deployment has no key, and nothing
   deployed signs today — E1-06 and E1-11 both run against the mock platform in
   development — which is what makes the gap survivable for now rather than a
   hole. It is a deliberate omission, not an oversight: the alternative was a
   configuration variable holding a private key, which
   [ADR 0082](../../adr/0082-the-tools-signing-key-lives-in-the-database.md)
   rejects, and inventing a supply route before anything needs one would fix the
   shape of it in the wrong ticket.
   **Done when** a non-development deployment has a documented and tested way to
   put a signing key in that table — with the rotation question answered too,
   since the one-row rule forbids the two-key overlap a real rotation needs.
   **Owner:** the epic that first registers a real platform and therefore first
   needs a production signer.

2. **The address rules judge spellings, not addresses** (security review,
   LOW). Rules 3 and 4 of ADR 0081 accept `127.1`, bare-decimal and
   dotted-hex literals, and resolver-backed names (`metadata.google.internal`)
   for the exact addresses they refuse — ADR 0081's residue paragraph holds
   the measurements. Capped by rule 1 (cleartext off this machine is refused
   regardless of spelling) and by the seed being the only writer today.
   **Done when** the two helpers resolve the host and judge every returned
   address, or refuse integer/dotted-hex host literals, with test pairs on
   both sides — before E11's console becomes a second writer.

3. **The write-time chokepoint is a call convention** (security review,
   LOW). Nothing — mapper event, sweep, or grant — makes a future writer of
   `lti_platform` call `refuse_invalid_registration_addresses`; a writer
   going through SQLAlchemy without the call is as unjudged as the raw-SQL
   writer ADR 0081 records.
   **Done when** the call is structural (a `before_insert`/`before_update`
   event on `LtiPlatform`) or a sweep asserts every write site calls it —
   in the same change that adds the second writer, E11 at the latest.

## From E1-03 — TypeScript 7 with typescript-eslint, one change

1. **The TypeScript 7 pair did not move, because no released
   `typescript-eslint` accepts TypeScript 7.** The ticket's own escape clause
   was taken: nothing was pinned, nothing was forced, and the measurement is
   recorded under entry 3 of
   [`../deps-triage-2026-08-24.md`](../deps-triage-2026-08-24.md). The
   repository stays on `typescript` 6.0.3 with `typescript-eslint` 8.67.0, both
   exact-pinned and both green. Forcing the pair past npm's peer check installs
   and then fails the lint gate outright, so there is no partial move to take
   either.
   **Done when** `npm view typescript-eslint peerDependencies` reports a
   `typescript` range admitting 7.x, and the pair then lands in one change with
   `npm ci` resolving and the four Node-facing gates green — that is triage
   entry 3's "done when", unchanged.
   **Owner:** whichever epic is running when that range widens; it is no longer
   E1's to wait for.
