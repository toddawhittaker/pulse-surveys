# Heavy-lane paths

A ticket's diff reaching any of these paths means heavy lane, whatever the
header predicted at breakdown. build-ticket step 0 re-lanes on this,
mid-build. The heavy lane is for security code only: the places where a
defect lets someone see or do what they should not. The aim is that about
one ticket in five is heavy.

| Path pattern | Heavy because |
|---|---|
| `backend/app/views_sql/` | §4/§4.1 read paths; the identity separation and the n-threshold suppression live here |
| `backend/app/services/authz.py` | the supervision graph and the purview computation (§2.1) |
| `backend/app/services/identity.py`, `backend/app/models/identity.py`, `backend/app/models/org.py` | the identity and org shapes the authz and identity-separation guarantees are built from |
| `backend/app/services/session.py`, `backend/app/services/tokens.py`, `backend/app/api/auth.py`, `backend/app/api/deps.py`, `backend/app/api/dev.py` | session and token handling, the dependency chain every route authenticates through, and the dev-only bypass |
| `backend/app/lti/`, `backend/app/api/lti.py`, `mock-lms/app/tokens.py`, `mock-lms/app/signing.py`, `mock-idp/app/signing.py` | the LTI entry door and the code that issues and signs tokens |
| `backend/app/services/safety.py`, and any path matching `*audit*` or `*care*` | the Care role (§6.2), safety routing, and the audit record nothing may bypass |
| `scripts/db-init/` | database roles and grants, which the identity separation rests on (ADR 0001) |
| any test marked `invariant` | the §4.1 invariant suite |

One more case is heavy but is not a path: a migration that creates, alters,
or grants on an identity, org, audit, or Care table, or on a view. The
ticket's author decides this at breakdown from what the migration does.

Everything else is light: other routes, services, and models, jobs, the AI
code, the frontend, other migrations, scripts, fixtures, and Docker and
Compose files. Light paths still get the per-PR security review that
`review-pr` picks from the diff, and the full reviewer battery at the epic
boundary. CI files and gate settings are not ticket work at all: they ride
a `process/` PR (the merger's refusal list names them). If
a security reviewer judges that a light diff needs the heavy loop, the
ticket is re-laned, and the PR says so.

**Light is the default.** A path no row names is light. What stays closed
is the security review: every PR gets one, whatever its lane, so an
unlisted path is still reviewed before it merges.

This table decides the build lane. `review-pr`'s gating table decides which
reviewer fires on a pull request. They overlap without being identical,
and where both name the same path they must agree.
