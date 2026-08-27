# 0094 — A subject resolves to row ids through SECURITY DEFINER functions

## Context

Two tickets need to turn an authenticated subject into row ids. E1-12's doors
must resolve a launch `sub` to its `user` and `person` rows so a session can
bind a stored identity, and E1-11's roster sync must match each NRPS member's
`user_id` to a `user` row before it may write an enrollment. The lookup column,
`user.lms_user_id`, is the one `launch_provisioning_grants_v002.sql` revoked
from `pulse_app` during E1-10's round-3 security review: readable at table
grain, it lets the application connection enumerate every subject that ever
launched and join responses back to people. `person` carries a name and
`pulse_app` holds no privilege on it at all. The repository's grant inventory
(`tests/integration/test_identity_grants.py`) already recognises three
mechanisms by which a role may reach identity: a grant, a column grant, and
EXECUTE on a SECURITY DEFINER function — the third built for the Care reveal.

## Decision

Point-resolution functions, in `identity_resolution_v001.sql`:
`resolve_platform_user(lti_platform_id, lms_user_id) → uuid` and
`resolve_person_for_user(user_id) → uuid`. Both are SECURITY DEFINER, owned by
`pulse_resolve_definer` — a NOLOGIN role holding SELECT on exactly five
columns (`user.id`, `user.lti_platform_id`, `user.lms_user_id`, `person.id`,
`person.user_id`) and nothing else, per ADR 0043's pattern. `pulse_app` holds
EXECUTE and no new column read. The functions return a uuid or NULL, never an
identity column. Because both tickets build against the file concurrently, it
ships byte-identical from both branches, each under its own revision;
`CREATE OR REPLACE` and a guarded role creation make the second revision a
harmless replay. E1-12's web-door resolver (`resolve_web_person`) follows the
same pattern in its own file with the same owner.

## Alternatives rejected

- **Re-granting `SELECT (lms_user_id)` to `pulse_app`** reverses E1-10's
  round-3 fix: every screen's connection could again enumerate subjects and
  join responses to people. The revocation's reasoning stands.
- **A lookup view** cannot answer a filter on a column it does not expose, so
  it re-exposes `lms_user_id` and is the same re-grant wearing a view.
- **Each ticket building its own resolver** ships two near-identical doors into
  the identity tables that drift independently; one file, one owner, one
  inventory entry set is smaller and auditable.

## Consequences

- The identity-grant inventory gains EXECUTE entries for these functions, and
  the `identity_by_execute` sweep now finds `pulse_app` as well as
  `pulse_care` holding a definer door; each entry carries this ADR as its
  sentence.
- A future need to resolve in bulk (a report, an export) must not loop these
  functions; it needs its own reviewed mechanism, because point lookups are
  the property this design protects.
- Until both tickets merge, the file exists identically on two branches; after
  the second merge one revision replays it as a no-op.
