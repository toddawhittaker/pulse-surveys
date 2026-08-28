# Heavy-lane paths

A ticket's diff reaching any of these paths means heavy lane, whatever the
header predicted at breakdown — build-ticket step 0 re-lanes on this,
mid-build.

| Path pattern | Heavy because |
|---|---|
| `backend/app/views_sql/` | §4/§4.1 read paths — the identity-separation guarantee lives here |
| `backend/app/services/` | authz, session, tokens, safety, provisioning, roster sync, and identity — the supervision graph, the scoping computation, and the write paths built on them |
| `backend/app/models/` | identity, org, and audit shapes — what the authz and audit guarantees are built from |
| `backend/app/lti/`, `mock-lms/`, `mock-idp/` | the two entry doors and token handling; within the mocks, `mock-lms/app/tokens.py`, `mock-lms/app/signing.py`, and `mock-idp/app/signing.py` are the ones actually issuing and signing tokens |
| `backend/app/api/` | every route, plus `deps.py` (the dependency chain every route composes from) and `dev.py` (the dev-only bypass surface) — the doors again, at the boundary where a request first authenticates |
| any test marked `invariant`, and any path matching `*audit*` or `*care*` | guarded writers — the chokepoint and the record nothing may bypass |
| `backend/app/config.py`, `backend/app/db.py` | process-wide configuration and the database engine every guarantee above sits on |
| `scripts/db-init/`, `scripts/seed.py`, `backend/migrations/` | key and secret custody, the bootstrap identity, and schema changes underneath every read-path and authz guarantee |
| `.github/workflows/`, `scripts/ci/`, and any Makefile target a CI gate depends on | CI gates |
| `docker-compose*`, `Dockerfile*` (any directory) | the review fixture that plants a compose defect publishing the mock IdP is the proof this belongs here — a container definition is where a service gets exposed or hidden |
| `tests/conftest.py`, `tests/fixtures/` | the fixture chain the §4.1 invariant suite runs on; a broken fixture breaks the guarantee silently |
| `scripts/` (all of it, not only the subpaths named above) | scripts run with the access to make or check the guarantees above, whatever their individual purpose |

**Fail closed.** A path under `backend/app/` or `backend/migrations/` that
matches no row above is heavy until a row says otherwise. An enumeration that
defaults open is the defect class `docs/MISTAKES.md` records more than once —
this table does not repeat it. A path one of the rows above names is heavy
wherever it lives, not only under `backend/app/` or `backend/migrations/`.

This table and `review-pr`'s reviewer-gating table answer different
questions — this one decides which build lane a ticket rides, that one
decides which reviewer fires on a pull request — so they overlap without
being identical. Where both name the same path they must agree.
`review-pr`'s `app-security` trigger is still broader in places: it also
fires on `pyproject.toml`, `frontend/package.json`, `tests/evals/`, and
`backend/app/ai/`, none of which belong in a heavy-lane row.

This table is the authority for the build lane. CLAUDE.md's lane paragraph
points at it rather than restating it.
