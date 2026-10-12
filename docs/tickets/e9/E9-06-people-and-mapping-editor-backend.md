# E9-06 — The people and mapping editor, backend

**ID:** E9-06
**Branch:** `e9/people-and-mapping-editor-backend`
**Depends on:** 02
**Lane:** light
**Why this lane:** a service, routes and schemas over E9-02's definers. It
calls `require_admin` and the definers and changes neither, adds no view, no
migration and no `invariant`-marked test.
**Size:** L
**Security-relevant:** the admin's editor. A defect here imports a mapping
the admin did not see in the dry run, or applies half an import.

## Context

SPEC §6.3: the People & reporting editor (name, category, role assignments,
reports-to, built top-down) and the Lead Faculty mapping table (person →
courses), both with column sorting, pagination, and CSV import and export
where an import always shows a dry-run diff before applying. SPEC §2.1 gives
the diff's shape: "2 mappings added · 1 changed · BIOL 441 unmapped, falls to
chair". Ruling 1: every Pulse-owned role is grantable, Care and Admin
included, to anyone, the admin included. Ruling 7: revoking deletes.

- **Sorting.** Name columns sort by last name with titles stripped ("Dr.",
  "Prof." and the like, from one list in the service); category sorts by
  hierarchy rank. No column sorts by any figure (there are none here).
- **Pagination** on both tables.
- **The reports-to selector** lists only assignments whose role ranks above
  the child's (ADR 0044's rule, read from the same rank table the trigger
  uses), so a new person's selector lists only people already in the graph.
- **The web-login linkage field** links or unlinks a subject through E9-02's
  definer (the carried linkage entry).
- **CSV export and import** for both tables. An import first answers a dry
  run: the diff of what would be added, changed, removed and left unmapped,
  computed by applying the import inside a transaction that is rolled back.
  Applying sends the same file back with the dry run's digest, and the apply
  is refused if the database changed since the dry run. An apply is all or
  nothing.
- **A teaching grant with a child edge** cannot be made (the carried entry):
  one test that the editor's edge write under an `INSTRUCTOR` assignment is
  refused.
- **One person, two lead assignments** (E9-01 done-when 9): the people view
  shows both assignments and their chairs, so the admin can see that both
  chairs reach every course mapped to that person.

Read first: SPEC §2.1 (data sources), §6.2 and §6.3; ADRs 0044, 0097 and
0200; E9-02's definers; `api/leadership.py` and its schemas for the route
and copy patterns; `design/AdminConsole.dc.html`.

## Owns

- `backend/app/services/people.py` (new: nothing in `authz.py`, the read
  chokepoint, or `identity.py`, which resolves a verified subject, fits).
- `backend/app/api/admin.py` (new; SPEC §13 already plans it) and its router
  registration.
- `backend/app/schemas/admin.py` (new), and sentences added to
  `backend/app/copy/admin_people.py` under the `admin_people` prefix E9-02
  placed (README decision 15).
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- SPEC §13: the three new files, and `api/admin.py`'s line no longer "not
  built yet".
- ADR **0204** (the CSV's keys, the dry run as a rolled-back apply, the
  digest that ties the apply to its dry run).

## Reuse, do not rewrite

E9-02's definers and `require_admin`; the role rank table behind ADR 0044's
trigger; the copy registry pattern in `backend/app/copy/`.

## Done when

1. **Every route is admin-only.** Each route answers a non-admin session 403
   and no session 401, driven over HTTP.
2. **Sorting.** "Dr. Ana Zeller" sorts after "Bo Adams" and before "Prof.
   Cy Zimmer" by last name; category sorts in rank order; tested with titled
   and untitled names.
3. **Pagination** answers stable pages with a total, and a page past the end
   answers empty.
4. **Every Pulse-owned role can be granted (ruling 1).** The grant route
   accepts `CARE` and `ADMIN`, including for the acting admin's own person,
   and refuses `INSTRUCTOR` with a governed sentence.
5. **Revoke (ruling 7).** Revoking a childless assignment removes it; one with
   children answers a governed sentence naming how many must be re-pointed.
6. **The selector lists only higher ranks.** For a new `LEAD_FACULTY`
   assignment the selector lists chair, assistant dean, dean and VP
   assignments only; for a `CHAIR`, no lead.
7. **The dry run changes nothing.** An import's dry run answers the diff
   (added, changed, removed, unmapped with "falls to chair"), and afterwards
   the tables are identical to before, row for row.
8. **The apply is the dry run.** Applying with the dry run's digest makes
   exactly the diff's changes; applying after another write changed the
   tables is refused and changes nothing; a file with one bad row applies
   nothing and names the row.
9. **Export round-trips.** Exporting and re-importing the same file answers an
   empty diff.
10. **No edge under a teaching grant.** The edge write under an `INSTRUCTOR`
    assignment is refused (the carried entry's one test).
11. **The linkage.** Linking and unlinking a web-login subject through the
    route works and is refused for a subject linked to someone else.
12. **Words.** Every new sentence is in the copy registry under
    `admin_people.` and passes the copy inventory with no change to the
    inventory test.
13. **The acting admin is the session's person.** A grant request carrying
    another admin's person id in the query string, the path or the body is
    applied as the session's own person, and the audit row names the
    session's person. Every route passes the definers the key from the
    verified session only (E9-02 says why the route is the real check).
14. **The records match.** ADR 0204 is written and indexed; SPEC §13 draws
    the new files.

## Shares files with

- `openapi.json`, `wire.gen.ts`: 04, 05, 07, 08 and 09.
- `docs/SPEC.md` §13, `docs/adr/README.md`: other owners.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 23, 29 and 31.

## Known traps

- **Entry 31.** "Running the import twice is safe" must be tested against a
  database the importer did not fill.
- **Entry 29.** A bad row is refused, never repaired into a good one.

## Not in this ticket

- The screens (10).
- The definers (02).
- Showing audit rows (E10).
