# E4-01 — The reveal refuses a subject reached through a reporting scope

**ID:** E4-01
**Branch:** `e4/reveal-subject-guard`
**Depends on:** nothing — but E4-11 may not merge before this does
**Lane:** heavy
**Security-relevant:** entirely. This is the carried composition finding from
E1's file, it touches `backend/app/services/safety.py` (a heavy row twice
over: `services/` and the `*care*`-adjacent guarded writer), and
`privacy-authz` fires on the diff.

## Context

The carried entry ("The reveal's actor check and an instructor's read scope
compose", `docs/tickets/e1/carried-from-e0.md`) records three facts that are
individually correct and jointly not: `ActorScope` carries `holds_care`
beside the purview so Care can never be unioned into a scope;
`section_roster` hands instructor-scoped code the `user_id` of every enrolled
student, which is the view's whole point; and
`safety.reveal_identity(actor_person_id=…, subject_user_id=…)`
(`backend/app/services/safety.py:224`) checks only that the actor holds Care
and asks nothing about where the subject came from. A two-hat person — a Care
officer who also teaches, which §2.1 explicitly permits — can take a
`user_id` off her own roster and reveal it, and the audit row is
indistinguishable from a legitimate access.

E0 had no surface that renders roster-derived rows to an instructor. E4
builds the first one, which is why the entry's deadline names this epic: the
guard lands **before any instructor-facing surface renders roster rows**, and
this breakdown enforces that with a build-order edge — E4-11 waits on this
ticket — rather than with a sentence.

One fact constrains the shape. The carried done-when says "the reveal takes
its subject from a Care case rather than from any caller-supplied id, or an
equivalent guard," and there is no case model until E10 —
`safety.py:251` says so in as many words, and `reveal_identity`'s `case_id`
is nullable for exactly that reason. The guard therefore cannot lean on a
table that does not exist; it has to derive the subject from something that
already legitimately connects Care to a student.

Read first: the carried entry whole; SPEC §6.2, §4; ADRs 0042, 0043, 0071
(the reveal machinery as built); `backend/app/models/ai.py` (the
classification rows and their verdict vocabulary);
`backend/app/views_sql/reveal_student_identity_v002.sql`.

## Scope

- `reveal_identity` stops accepting a bare `subject_user_id`. The subject is
  derived server-side from the record Care is acting on, and a caller can no
  longer name an arbitrary student.
- The two-hat composition test the done-when demands: an actor who holds Care
  *and* teaches a section, a `user_id` taken from that section's roster, a
  reveal attempt that must be refused — a test that fails on the composition
  itself, not on a missing role.
- The refusal is its own distinguishable error, so E10's queue can tell "not
  Care" from "not a legitimate subject" without string-matching.
- Every existing caller and test of `reveal_identity` moves to the new
  signature in the same PR; no compatibility shim stays behind.

## Acceptance criteria

1. There is no code path by which caller-supplied identifier input reaches
   the reveal as its subject. The signature itself makes the old call
   unwritable, and a grep for the old parameter name over `backend/` comes
   back empty outside history.
2. The two-hat test: an actor holding both a Care assignment and a teaching
   assignment, a subject taken from her own section's roster, a reveal that
   is refused — and the refusal is proven to come from the subject-derivation
   guard, not from the actor check (`docs/MISTAKES.md`: pin *which* layer
   refused via the error's cause).
3. A legitimate derivation still works: a subject reached through the record
   the ADR names resolves and produces the audit row §4 requires, with actor,
   timestamp, and the (still-nullable) case column.
4. The audit write is unchanged in grain and content — this ticket narrows
   how a subject is named, not what is recorded about a reveal.
5. The §4.1 invariant suite still passes untouched, and any invariant test
   that exercised the old signature is corrected in its own commit with the
   reason stated.

## Decisions this ticket settles

- **What stands in for the Care case before E10.** The recommendation, to be
  confirmed or replaced in the ticket's ADR: the reveal takes the identifier
  of a comment (answer) whose latest classification is in the threat or
  self-harm set, and derives the subject as that comment's author. That is
  the only record in today's schema that legitimately connects Care to a
  specific student, it is exactly what §6.2's queue acts on, and E10's case
  model can wrap it without another signature change. The alternative —
  keeping `subject_user_id` and validating it against such a record — leaves
  the bare id in the signature and is the shape the carried entry warns
  about.
- **Whether the E0-26 sweep rule (only the queue imports the reveal, carried
  to E10) gets its structural test now.** Cheap to add beside this diff if
  the sweep's shape is settled; otherwise it stays E10's, and the ADR says
  which.

## Known traps

- **The moderation task does not exist yet** (it is E6's), so no production
  path writes a threat or self-harm classification today. The legitimate-path
  test plants its classification rows through the model layer the way the
  invariant suite already does — it does not wait for E6, and it does not
  invent a dev route to write them.
- **A guard test whose outcome a second defense layer also produces** proves
  nothing — the refusal in criterion 2 must be attributable to the new guard
  specifically.
- **`record_identity_reveal` is a definer function** (`safety.py:109`); the
  guard belongs in front of it, in the service, and the ADR should say
  plainly why the database function's own contract is or is not also
  tightened.

## Out of scope

- The Care queue UI, the case model, resolve-after-reveal, disposition notes,
  conflict-of-interest marking — all E10, unchanged.
- Writing real threat or self-harm classifications — E6's moderation task.
- Any report surface — the rest of this epic.
