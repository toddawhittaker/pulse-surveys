# E5-06 — The named-set management API

**ID:** E5-06
**Branch:** `e5/named-set-api`
**Depends on:** E5-01
**Lane:** heavy
**Security-relevant:** a new leadership-scoped write surface in
`backend/app/api/` — heavy row, and the first route file in
`api/leadership.py`. Scoping mistakes here are authorization defects.

## Context

Leadership defines named sets (§5.1); this ticket is the CRUD and the
preview read the UI (E5-09) renders. Scoping uses the authorization
machinery that exists today — the session's role assignments and
`lead_faculty_mapping` reads — not a new purview computation (breakdown
decision 4 and "What E5 deliberately does not do": the DAG is E9's).

The preview is the one read: member count and resolved section count for
the set (via E5-04 if merged, else deferred to a follow-up criterion —
see scope note), so the UI can show what a set reaches without any report
rendering it.

Read first: SPEC §5.1, §2.1 (who leadership is today), §6.3;
`backend/app/api/instructor.py` (the route conventions, `deps.py`
composition); E5-01's ADR and constraints (the API refuses nothing the
database already makes unstorable — it translates, it does not re-enforce
alone).

## Scope

- `backend/app/api/leadership.py`: list, create, edit, delete for named
  sets, leadership-scoped through the existing dependency chain.
- Validation errors that speak §5.1's vocabulary: an out-of-set length or a
  cross-level member is refused with a message naming the rule (the UI
  makes these unreachable; the API is the layer that cannot rely on that).
- The preview read: member count, and — if E5-04 has merged — the resolved
  section count across retained terms. If 04 has not merged when this PR
  is ready, the preview ships member count only and the section count is a
  named criterion moved to E5-09's join, recorded in the PR body (no
  half-wired stub).
- Grants: the write verbs on E5-01's tables land here with the writer
  (INSERT, UPDATE, DELETE as the routes actually spend them, withheld
  verbs named), versioned-grants shape — the same E4-02 precedent E5-04's
  SELECT follows; E5-01 granted nothing on purpose.
- Audit: the recommendation is that creates, edits and deletes write
  `audit_log` rows — a named set changes what leaders compare, and the
  trail is cheap. Whether the existing audit machinery fits a
  non-reveal write is this ticket's to verify; the ADR line records the
  choice either way (a decision to not log is also a decision).

## Acceptance criteria

1. Each route refuses an unauthenticated call and a student or instructor
   session, and answers a leadership session — both directions, per route,
   driven over HTTP against the built application (MISTAKES entry 47).
2. A leader reaches only sets within their scope for edit and delete; a
   planted second leader's set is refused — both directions.
3. Create and edit surface the database's constraint refusals as 4xx with
   §5.1-vocabulary messages, proven by attempting the invalid writes (the
   constraint fires; the route translates).
4. Deleting a set is refused/allowed per E5-01's member-deletion ADR, and
   the log row for each write exists — asserted by reading the audit
   trail, not the return value.
5. The preview returns counts, never section names or figures — a reader
   below the minimums learns a count of sections, which §5.1 treats as
   safe at set-definition time; the ADR line in the PR says so out loud.
6. Every route composes `deps.py`'s chain — no bespoke session read.

## Known traps

- **The two-hat reader** — a person who is both instructor and leader
  resolves scope by role assignment, not by identity; plant one
  (MISTAKES entry 35's shape: the privilege held the unusual way).
- **Refusal tests that pass for the wrong reason** — pin which layer
  refused via the error body, not the status alone (the green-tests
  memory's newest shape).

## Out of scope

- The UI — E5-09.
- Attaching a set to any report — E9 (decision 4).
- New purview machinery — E9.
