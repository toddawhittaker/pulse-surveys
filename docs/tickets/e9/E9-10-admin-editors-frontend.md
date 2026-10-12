# E9-10 — The admin editors, frontend

**ID:** E9-10
**Branch:** `e9/admin-editors-frontend`
**Depends on:** 06
**Lane:** light
**Why this lane:** frontend only, over E9-06's routes, with its strings under
the `admin_people` prefix E9-02 placed.
**Size:** M
**Security-relevant:** low. The routes refuse every non-admin; the screen
must not apply an import the admin has not seen in its dry run.

## Context

SPEC §6.3: the People & reporting editor and the Lead Faculty mapping table,
both with column sorting, pagination, and CSV import and export where import
always shows a dry-run diff before applying. Ruling 1: every Pulse-owned role
is offered, Care and Admin included, for any person, the admin included.

- **People & reporting.** A sortable, paged table of people with their
  category, role assignments and reports-to. Add a person; grant or revoke an
  assignment (revoking one with children shows the server's sentence naming
  how many to re-point); set reports-to from a selector that lists only the
  server's offered parents; link or unlink a web login.
- **Lead Faculty mapping.** A sortable, paged table of course → lead, with
  "falls to chair" for an unmapped course.
- **Import.** Choose a file, see the dry-run diff ("2 mappings added · 1
  changed · BIOL 441 unmapped, falls to chair"), then apply or cancel. Apply
  sends the dry run's digest; a refusal because the data changed shows the
  server's sentence and offers a fresh dry run.
- **Export** downloads the CSV.
- A person holding two lead assignments shows both, with each one's chair.

Read first: SPEC §6.3; `docs/DESIGN_BRIEF.md`, `design/tokens.css`, §7.6;
`design/AdminConsole.dc.html` and `design/Admin Console - States.dc.html`;
E9-06's contract; `frontend/src/routes/leadership/` for page patterns.

## Owns

- `frontend/src/routes/admin/` (new): both tables and the import screen.
- `frontend/src/api/admin.ts` (new).
- `frontend/src/copy/adminPeople.ts` (new), keys under `admin_people.`.
- `frontend/src/router.tsx`: the admin routes.

## Reuse, do not rewrite

The generated wire types; the existing table, pagination and page-state
components if any fit; the frontend copy registry pattern.

## Done when

1. **Both tables sort and page** by the server's order; a name column sorts by
   last name with titles stripped, shown with a test that renders the
   server's order unchanged.
2. **Every Pulse-owned role is offered** in the grant control, Care and Admin
   included, and no instructor role.
3. **No apply without a dry run.** The apply control is absent until a dry run
   has answered, and sends that dry run's digest; a changed-data refusal shows
   the server's sentence.
4. **Revoke with children** shows the server's sentence and removes nothing.
5. **Not an admin.** A leadership or Care session opening an admin route sees
   "This page is not part of your role" through ADR 0196's `insufficient_scope`
   reading.
6. **Words and basics.** Every string is under `admin_people.` in the copy
   registry and passes the inventory with no change to the inventory test;
   keyboard and screen-reader basics hold, including the diff table read as a
   table.
7. **One e2e path:** an admin imports a mapping file, reads the diff, applies
   it, and sees the table change.

## Shares files with

- `frontend/src/router.tsx`: 11.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 18 and 23.

## Known traps

- **Entry 23.** A disabled apply button that the keyboard can still trigger is
  the appearance of a dry-run rule; test the control is absent.

## Not in this ticket

- The backend (06).
- The audit view (E10).
