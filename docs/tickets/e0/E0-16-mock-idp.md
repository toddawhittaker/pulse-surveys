# E0-16 — Mock OIDC identity provider

**ID:** E0-16
**Branch:** `e0/mock-idp`
**Depends on:** E0-02, E0-08

## Context

Leadership, Care, and Admin users enter by web login rather than by LTI launch,
and both doors must resolve to the same identity and the same full purview
(§2.1). An in-repo standards-compliant OIDC provider makes that second door
testable in CI with no institutional identity provider involved (§9.2).

Read first: SPEC §9.2 (in-repo mock IdP), §2.1 (dual-door entry and the rule
that the launch context never caps what a leadership user sees), §6.3.

## Scope

- `mock-idp/` FastAPI application and `Dockerfile`, added to Compose as
  `mock-idp` with a health check.
- Discovery document at `/.well-known/openid-configuration`, plus `authorize`,
  `token`, and `jwks_uri` endpoints.
- Authorization code flow with PKCE, signed ID tokens, and a JWKS endpoint whose
  key verifies them.
- Seeded users covering every web-login role: VPAA, dean, chair, lead faculty,
  Care, and admin. Care must be seeded separately, since §2.1 makes it
  deliberately non-composable with any reporting role.
- A login form simple enough for a Playwright test to drive without brittle
  selectors.
- Configuration in `.env.example` so the tool can point at the mock, with
  placeholders only.

## Out of scope

- Tool-side OIDC login, session handling, and the unified session model that
  merges both doors (E1).
- Role and purview resolution from claims (E1, E9).
- Any real institutional identity provider integration — out of scope for the
  whole product at v1.

## Acceptance criteria

- [ ] `docker compose up -d` brings `mock-idp` to healthy.
- [ ] The discovery document validates against the OIDC discovery schema and
      lists every endpoint it actually serves.
- [ ] An authorization code flow with PKCE completes end to end and yields an ID
      token that verifies against the served JWKS.
- [ ] A code cannot be redeemed twice; the second attempt is rejected.
- [ ] A mismatched PKCE verifier is rejected.
- [ ] Every seeded role can log in, and a test enumerates them so a missing role
      fails rather than going unnoticed.
- [ ] No private key is committed; keys are generated at startup.

## Definition of done

**Tests apply.** Integration tests for the full code flow, code replay
rejection, and PKCE verifier mismatch. These are the fixtures E1's login work
builds on.

**Docs apply.** `README.md` lists the seeded users and their roles, alongside
the mock LMS users from E0-15.

**AI evals do not apply.**

**Accessibility does not apply** — a test harness, not a product surface.

**Security review applies and matters here.** An identity provider that is
lenient in the wrong place teaches the tool-side code bad habits. Review code
replay, PKCE enforcement, redirect URI validation, and token expiry. Confirm the
mock cannot be reached from a deployed environment.
