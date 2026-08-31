# E2-02 — A staff launch binds a roster address only inside the launcher's purview

**ID:** E2-02
**Branch:** `e2/staff-launch-purview`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** the whole ticket. This is the E1 boundary review's M9
finding, verified: write/ingest integrity on the first sanctioned writer.

## Context

The carried entry governs (`carried-from-e1.md`, "A leadership assignment
anywhere is an unscoped roster-ingestion trigger"). §7.3's leadership limb
admits any holder of a live leadership assignment as a staff-launch trigger
with no reference to the launch's context: a Lead Faculty enrolled as a
Learner in a sibling lead's course can launch from it, and Pulse binds that
section, stores its roster address permanently
(`backend/app/services/provisioning.py`, `provision_from_launch`, the
`lms_context_memberships_url` write), and pulls the full membership —
including the squat hazard on the `(course, term, section_code)` name.

**Deadline (ruled 2026-08-28):** fixed before any surface renders
roster-derived data. E2's student surface is that surface, so this ticket
lands before E2-09 and E2-10 merge.

The fix needs a design answer first, and the ticket makes it rather than
inheriting one: a dean's legitimate first launch into a brand-new course that
no purview yet covers must keep working. Transitive purview is E9's
(`transitive_purview` raises by design, ADR 0003), so the condition here is
built from what exists today: enrollment, live role assignments and their
scope columns, and the launch's own context claims.

Read first: the carried entry in full (M9 in
`docs/tickets/e1/boundary-review.md`); SPEC §7.3 and §2.1;
`provision_from_launch` and `_is_a_staff_launch`; ADR 0091 (first-writer-wins
binding); `docs/tickets/e1/deferred.md` E1-10 item 4.

## Scope

- A purview condition on storing the discovered roster address: a staff
  launch stores an address only for a section within the launcher's resolved
  purview. The first-launch case (a context Pulse has never seen, launched by
  someone whose LTI roles claim makes them staff *of that context*) is
  settled and recorded — an ADR if the choice is contestable, which it is.
- A launch outside the condition records a defect row (the `launch_defect`
  mechanism exists) rather than binding, and the launch itself still lands
  the person on their landing view — refusing the *binding*, not the entry.
- A two-directional test pair pins both sides: the sibling-lead Learner
  launch does not bind and leaves the defect row; the in-purview launch (and
  the dean's first launch) binds exactly as before (MISTAKES entry 2 — assert
  the forbidden state, and the near miss).
- The roster low findings the carried block assigns "alongside M9":
  - the roster walk's cycle/page-cap terminator
    (`backend/app/services/roster_sync.py`, `_walked_roster`) discards the
    members it already read; make that branch return the prefix with
    `complete=False` like its sibling failure exits;
  - the stored roster host joins `unpinned_hosts` in every environment while
    the docstring calls that entry development-only; narrow the entry or make
    the docstring state what the code does;
  - the `DESC` on `ix_nrps_call_section_id_called_at_desc` serves no query
    and is what hides the declaration from `alembic check`; make the index
    comparable (plain ascending composite) or give the `DESC` a reader.

## Acceptance criteria

1. The carried entry's done-when, in full: in-purview binds, out-of-purview
   records a defect row and does not bind, the first-launch case is settled
   and recorded, and the test pair pins both directions.
2. The cycle-cap branch returns an incomplete prefix, proven by a test that
   feeds a `next`-forever page sequence and sees the read members kept.
3. `unpinned_hosts` and its docstring agree; the index is visible to
   `alembic check` (run it) or the `DESC` has a named reader.
4. The existing staff-launch and sync suites stay green — the condition must
   not break the seeded dean's first launch (`driving the E1 stack` is the
   manual check; the e2e specs are the enforced one).

## Out of scope

- Reconciling or aging out an already-squatted binding — E11's, per ADR 0091
  and the carried file.
- Transitive purview and the Hypothesis purview properties — E9's.
- Any change to NRPS token handling (settled in E1, ADR 0099 boundary).
