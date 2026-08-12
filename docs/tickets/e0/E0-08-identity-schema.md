# E0-08 — Identity schema and LTI registration tables

**ID:** E0-08
**Branch:** `e0/identity-schema`
**Depends on:** E0-04, E0-05

## Context

This ticket introduces the tables that hold who someone is — and therefore the
tables that the confidentiality guarantees in §4 exist to keep away from
instructor and leadership read paths. `person` is Pulse-owned and feeds the
supervision graph; `user` and `enrollment` are LMS-owned. Keeping the two
distinct here is what makes E0-10's view separation possible.

Read first: SPEC §8, §2.1 (data-source ownership), §4 (confidentiality), §7.3
(LTI specifics), `CLAUDE.md` (confidentiality invariants).

## Scope

- `backend/app/models/identity.py`: `user`, `person`, `enrollment`.
- `user` is keyed to the LMS user ID (§4: responses are keyed to it, and
  identity is never displayed to an instructor or leadership role). Identity
  columns — name, email — live here and nowhere else.
- `person` is the Pulse-owned record for the people graph: name, category. A
  `person` may or may not correspond to a `user`; the link is nullable and
  explicit.
- `enrollment` links a `user` to a `section` with an enrollment window (start
  and end), because the participation formula in E3 is enrollment-windowed.
- `backend/app/models/org.py` or a new `lti.py`: `lti_platform` and
  `lti_deployment` — issuer, client ID, deployment IDs, JWKS URL, last fetch.
  Key material handling is defined here even though no launch happens until E1.
- Column-level comments or a marker convention identifying every identity
  column, so E0-10's views and the CI invariant can both find them
  programmatically rather than by a hand-maintained list.

## Out of scope

- `role_assignment`, `lead_faculty_mapping`, and the supervision graph (E0-09).
- The identity-separated read views (E0-10).
- Any launch, token validation, or roster sync (E1).
- Care-role re-identification and the audit log (E10).

## Acceptance criteria

- [ ] `alembic upgrade head` creates the tables; `alembic check` is clean.
- [ ] A `user` is unique per LMS user ID per platform; the same LMS ID on two
      platforms is two users.
- [ ] `enrollment` rejects an end date before its start date.
- [ ] Overlapping enrollments for the same user and section are either rejected
      or explicitly permitted with a documented reason — decide and test it.
- [ ] Every identity-bearing column is discoverable through the marker
      convention; a test enumerates them and fails if a new one is added without
      the marker.
- [ ] `lti_platform` stores no client secret in plaintext, and a test asserts
      the column either does not exist or is encrypted at rest.

## Definition of done

**Tests apply.** Unit tests for the constraints. One test that enumerates
identity columns via the marker convention — it is the tripwire E0-10 and every
later confidentiality test depend on.

**Docs apply, briefly.** `.env.example` gains any key-handling variable the LTI
tables need.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies and matters here.** This is the first ticket that
stores personally identifiable information and LTI credentials. Review for
key material at rest, identity columns reachable from an unintended path, and
PII in logs (§10 forbids student PII in logs).
