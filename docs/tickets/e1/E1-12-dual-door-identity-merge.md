# E1-12 — Dual-door identity merge

**ID:** E1-12
**Branch:** `e1/dual-door-identity-merge`
**Depends on:** E1-09, E1-10
**Security-relevant (⚠ line-by-line):** all of it. Identity linkage decides
who the system believes a person is; a wrong merge here is a confidentiality
failure in every later epic.

## Context

The first carried entry governs, and its "done when" is the acceptance
criterion verbatim: one test drives the seeded two-hat person through both
doors and asserts both resolve to the **same stored identity — one row, by its
primary key**, not two rows agreeing on an email — and the constant-pinning
unit test E0-18 left (`mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID` pinned to
the mock LMS's instructor id) is **deleted in the same change**, because the
fact it stands in for is then asserted directly.

The material: E1-10 creates `user` rows from launches (`lms_user_id` = the
LTI `sub`). The web door verifies an IdP `id_token` with its own subject.
ADR 0024 puts the person→user link on `person`. What "the same stored
identity" is — the `person` row, the `user` row, or a linkage row — and how a
web subject is matched to it (pre-provisioned linkage in the seed and admin
data, never claim-equality guessing) is this ticket's central design decision.
Decide it with an ADR; the constraint that bounds the decision is that **a
merge is never inferred from a mutable claim** (email equality is the named
anti-pattern in the done-when), and an unlinked web login is a defined state,
not an error page.

Read first: the carried entry; ADR 0024, ADR 0022 (which columns are
identity-marked — anything new that names a person gets the marker and joins
the §4.1 sweep's subject matter); ADR 0028 (students: user row yes, assignment
no); §8's identity tables; E1-01's closed sweep (this ticket is the first that
could trip it — any new view or grant must pass the closed version);
`mock-idp/app/seed.py` and the seeded two-hat person.

## Scope

- The identity model decision, with its ADR: what row is "the identity," and
  the storage for the web door's subject linkage (a column or table mapping
  IdP issuer+subject to the identity). New person-naming columns carry
  ADR 0022's marker.
- Resolution on both doors: after E1-08/E1-09 verification, the session binds
  to the stored identity — launch via `lms_user_id`, web via the IdP-subject
  linkage. The session carries the identity reference from here on (E1-13
  reads assignments through it).
- The seed links the two-hat person's two subjects to one identity (behind
  the ADR 0063 guard), and gains any linkage rows other seeded web identities
  need.
- The unlinked web login state: a verified `id_token` whose subject has no
  linkage lands on a calm "no account" page — no auto-provisioning of
  identities from the web door (the IdP asserts authentication, not
  membership; §2's roles come from Pulse's own records).
- The constant-pinning test deleted in the same change, per the done-when.

## Acceptance criteria

1. The done-when's test, verbatim: two-hat person, both doors, same primary
   key; and the pinning test is gone.
2. A second person entering by launch only resolves to their own identity —
   the two-hat test cannot pass by everyone resolving to one row (the
   near-miss that distinguishes the merge from a constant; MISTAKES entry 3).
3. An unlinked web subject gets the defined state and no identity row is
   created; the forbidden state (auto-created identity) is asserted.
4. Launch-created `user` rows and web linkages are idempotent across
   re-entry; no duplicate identities after repeated logins (asserted on row
   identity).
5. The §4.1 isolated pass, including E1-01's closed sweep, stays green with
   the new columns marked.

## Out of scope

- Role/landing resolution (E1-13 — this ticket makes the person reachable;
  that one decides what they see).
- Any admin UI for linkage management (E9/E11's surfaces; the seed and, if
  needed, a documented psql path suffice for E1).
- Account provisioning flows for real IdPs (post-v1 certification).
