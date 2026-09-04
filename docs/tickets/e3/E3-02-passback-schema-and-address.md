# E3-02 — The passback schema, and the address the launch supplies

**ID:** E3-02
**Branch:** `e3/passback-schema-and-address`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** yes. The ticket adds columns to `section`, two new
tables, and their grants; it captures an address from an untrusted launch
claim and stores it; and it decides whether either new table holds anything
that reaches a person. `backend/app/models/`, `backend/migrations/`,
`backend/app/views_sql/` and `backend/app/services/` are all heavy-lane rows.

## Context

Everything E3 writes to, built before anything writes it. The order is
deliberate: the late-schema-rule lesson from E0-33's forty-one broken
fixtures says constraints land before the write paths and fixtures that would
violate them exist.

Three things are missing today and this ticket adds all three.

**The AGS container address.** A launch carries the platform's AGS endpoint
claim, which names the `lineitems` container for the launched context. Pulse
already does exactly this job for the roster service: `Section` carries
`lms_context_memberships_url` (`backend/app/models/org.py:472`), the address
is judged by `refuse_invalid_fetched_address`
(`backend/app/models/lti.py:513`), and the columns are enumerated in
`FETCHED_COLUMNS` (`backend/app/models/lti.py:135`) and
`LOOPBACK_REFUSED_COLUMNS` (`backend/app/models/lti.py:151`). The AGS address
is the same shape of thing and gets the same treatment, in the same
enumerations, rather than a second scheme beside them.

**The line item's own id.** Once "Pulse Participation" exists in the
platform, its id is what every later post addresses. It has to be stored
somewhere the poster can find it without re-reading a container on every run.

**The two log and state tables.** `grade_sync` is named in SPEC §8's table
list and in §13's layout as `models/grades.py`, and it exists nowhere in the
tree — no model, no migration, no column list. `ags_call` is named in §8's
table list beside `nrps_call`; §6.1 promises "NRPS and AGS call
logs" and only the NRPS half was ever built, as `NrpsCall`
(`backend/app/models/lti.py:1215`). Read that model's docstring before
designing this one: it is at the grain of one HTTP call, and the reasoning
for that grain transfers whole. **The spec now names both logs as separate
tables** — §6.1 says `nrps_call` and `ags_call`, and §8's constraints put
`ags_call` beside `grade_sync` — so whether the two logs share one table is
not a question this ticket reopens. A second table is what ships.

Read first: SPEC §3.4, §6.1, §8, §13; ADR 0052 (an equal score timestamp is
accepted as a retry — the retry identity this schema has to be able to
express); ADR 0090 (a sanctioned writer passes the chokepoint by being in a
catalog); ADR 0095 (the roster sync records two windows, no status);
ADR 0107 (the org-view sweep polices a catalog closure); `NrpsCall` and the
address enumerations named above.

## Scope

- The AGS `lineitems` container address, captured from the launch claim and
  stored on `section` as an exact mirror of `lms_context_memberships_url`:
  judged by the same refusal, listed in `FETCHED_COLUMNS` and
  `LOOPBACK_REFUSED_COLUMNS`, and a refused address recorded as a launch
  defect rather than turned into a refused launch. A platform that supplies
  no AGS claim is a section with no gradebook, which is a state to record and
  not a fault to raise.
- Storage for the created line item's id.
- `grade_sync` in a new `backend/app/models/grades.py`, **append-only at the
  grain of one row per post** (ADR 0124): the score as sent, the timestamp
  sent with it, the outcome, and the student and section. A failed attempt is
  a row too. Plus the index that makes "the latest row for this student in
  this section" a cheap lookup, because that lookup is on the recompute's hot
  path once a term's worth of rows exists.
- `ags_call` at HTTP-call grain, modelled on `NrpsCall`.
- The migration, reversible and asserted so (E2-16 repaired two irreversible
  ones; this one is written reversible from the start), the grants SQL for
  both new tables, and a `SANCTIONED_WRITERS` entry
  (`backend/app/services/authz.py:1161`) for anything here that writes
  `section` — the roster catalog deliberately does not grant `section`, so a
  new writer of it is paperwork, not an accident.
- The `PERSON_TABLES` standing review question asked and answered for both
  new tables in the pull request body, with the columns each judgement was
  made against — the shape E2-05 used.

## Acceptance criteria

1. A launch carrying an AGS endpoint claim stores the container address on
   the section; a launch carrying a loopback or otherwise refused address
   records a defect and leaves the column unset, with the launch itself still
   succeeding. Both directions asserted.
2. The new address column appears in `FETCHED_COLUMNS` and
   `LOOPBACK_REFUSED_COLUMNS`, and whatever test pins those enumerations
   fails if the column is dropped from either — the enumeration cannot
   quietly shrink (`docs/MISTAKES.md` entry 35).
3. `grade_sync` and `ags_call` exist with grants, and the org-view and
   catalog-closure sweeps pass over both without an exemption being widened
   to accommodate them.
4. The migration round-trips: upgrade, downgrade, upgrade, with the schema
   compared rather than assumed, and `alembic check` clean.
5. `grade_sync` can express the retry identity ADR 0052 depends on: the
   latest row for a `(section_id, user_id)` pair gives back what was last
   sent, exactly as sent, and when.
6. A second post for the same student writes a **second row**, and the first
   row is still readable afterwards with its original value. The test plants
   two rows carrying different values and requires both to be present and the
   newer one to be the answer — an update-in-place implementation is red on
   this, which is the whole point of the criterion.
7. The `PERSON_TABLES` question is answered for both tables in the pull
   request body, with `grade_sync` asked more carefully than `ags_call`: it
   holds a participation figure against an LMS user id, which is a statement
   about a named person's standing even though it holds no name.

## Decisions this ticket settles

- **`grade_sync`'s grain is already settled** by ADR 0124 and by §8's
  amended sentence, both landing with this breakdown: append-only, one row
  per post, latest row per `(section_id, user_id)` serving the retry
  identity. This ticket builds it and does not reopen it. What is left to
  this ticket is the column set that carries it — what "the outcome" is
  made of, and whether a failed attempt records the platform's response.
- **Where the line item id lives.** A column on `section` needs a
  `SANCTIONED_WRITERS` entry and puts platform-owned state on a
  platform-mirroring table; a Pulse-owned table avoids the sanction and adds
  a row nobody reads except the poster. Both are defensible, so whichever
  wins gets an ADR (0124 and 0125 are taken by this breakdown; 0126 is the
  next free number).
- **What a section with no AGS claim is.** Recorded as a state, in the same
  spirit as §7.3's never-synced section: a section with no gradebook address
  and a section whose gradebook is empty are different things and only one is
  a fault.

## Known traps

- **An append-only table is read wrong by asking for "the" row.** Every
  reader must ask for the *latest* row for a student and section, and a query
  that returns one row against a fixture holding one post returns the wrong
  row against a term's worth of them. This is `docs/MISTAKES.md` entry 3
  wearing a green tick, and it is why criterion 6 plants a second row rather
  than trusting the shape.
- **`PERSON_TABLES` is not what its name suggests.** It is defined in the
  test tree, three times with different contents
  (`tests/integration/test_identity_column_marker.py:222` and
  `tests/integration/test_demo_seed_script.py:292` disagree), and referenced
  from `backend/app/` only in prose. The standing question is answered by
  judgement recorded in the pull request body, not by editing a constant, and
  the structural source for it is still E13's open carried item.
- **A new writer of `section` fails closed if its paperwork is missing**
  (ADR 0090). That is the correct behaviour and it will look like a bug in a
  test run; budget it rather than discovering it.
- **Prose in a non-docstring string under `backend/app/` is read by the
  org-views SQL sweep** (`docs/MISTAKES.md` entry 43). A `Field(description=…)`
  or an error sentence in this ticket's diff that mentions `section` after a
  comma is a red gate on a file that runs no SQL. Reword the prose; never
  widen the guard.
- **A migration that adds a constraint to a table every fixture builds** is
  the E0-33 shape: forty-one tests failed inside their own seeding. The
  ancestor builders live in more than one module; grep for them before adding
  a constraint to `section`.

## Out of scope

- Calling AGS with the stored address — E3-04.
- Computing anything to put in `grade_sync` — E3-03.
- Any view over `ags_call` — E11's, per §6.1.
