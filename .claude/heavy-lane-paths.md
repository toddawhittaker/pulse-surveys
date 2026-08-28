# Heavy-lane paths

A ticket's diff reaching any of these paths means heavy lane, whatever the
header predicted at breakdown — build-ticket step 0 re-lanes on this,
mid-build.

| Path pattern | Heavy because |
|---|---|
| `backend/app/views_sql/` | §4/§4.1 read paths — the identity-separation guarantee lives here |
| `backend/app/services/authz`, `backend/app/models/identity`, `backend/app/models/org` | authz and purview — the supervision graph and the scoping computation |
| `backend/app/lti/`, `mock-lms/`, `mock-idp/` | the two entry doors and token handling |
| `backend/app/api/` routes for launch, callback, or session | the doors again, at the boundary where a request first authenticates |
| any test marked `invariant`, and any path matching `*audit*` or `*care*` | guarded writers — the chokepoint and the record nothing may bypass |
| `scripts/db-init/`, `scripts/seed.py`, and any migration touching an identity-bearing table | key and secret custody, and the bootstrap identity |
| `.github/workflows/`, `scripts/ci/`, and any Makefile target a CI gate depends on | CI gates |

These rows are derived from the paths `review-pr`'s reviewer-gating table
already validates, wherever the two overlap, so the two tables cannot
disagree.

This table is the authority. `CLAUDE.md`'s lane paragraph and `review-pr`'s
gating table both point at it rather than restating it.
