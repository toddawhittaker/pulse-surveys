# E1-06 — The mock platform learns the client-credentials grant — all four parts

**ID:** E1-06
**Branch:** `e1/mock-client-credentials-grant`
**Depends on:** E1-05
**Security-relevant (⚠):** the tool-side public JWKS route (a new production
endpoint), and the mock's token endpoint only insofar as ADR 0035's bound —
throwaway signing stays in the mock and is copied nowhere.

## Context

The carried entry **"The client-credentials grant, and the four things that
move with it"** governs this ticket, and its "done when" is explicit: the grant
lands as **one change covering all four parts**, before the first conformant
service client is written, because a surface carrying some of the parts cannot
be built against any better than one carrying none. The four:

1. A `token_endpoint` in the mock's OIDC discovery document.
2. The AGS and NRPS scope strings in `scopes_supported`
   (`app.ags::ADVERTISED_SCOPES` and NRPS's own), today `["openid"]`.
3. `auth_token_url` in the mock's `/registration` document — whose keys are
   the `lti_platform` column names E1-05 added, so "paste in one step" stays
   literal.
4. Somewhere for the platform to fetch the **tool's** key set, because the
   `client_assertion` is tool-signed and the platform verifies it.

E0-28 item 6 decided the mock does not learn to authenticate in E0 precisely so
these four parts would reach whoever builds the sync *before* the client is
written; the E1-06 → E1-11 dependency is that decision enforced.

Read first: the carried entry in full; ADR 0035 and ADR 0059 (the mocks'
signing bound); ADR 0036 (the registration-as-document pattern part 3 extends);
`mock-lms/app/` (ags.py's advertised scopes, the discovery document);
`pylti1p3`'s `ServiceConnector` token request shape (the client the grant must
satisfy).

## Scope

- Parts 1–3 in `mock-lms/app/`: a token endpoint implementing the
  client-credentials grant with `client_assertion` verification against the
  tool's published key set, the scope strings advertised, and the registration
  document extended. The mock verifies assertions with the same
  standard-library machinery it signs with (ADR 0035's bound: mock-only).
- Part 4 on the tool side: a public JWKS route serving the tool's key set from
  E1-05's key pair — the tool's first cryptographic production endpoint, so
  its diff is the ⚠ here. Key rotation is out of scope; one live key, `kid`
  set, shape per RFC 7517.
- The mock's token endpoint refuses: a request with no assertion, a
  wrong-audience assertion, an unadvertised scope, an assertion signed by a
  key not in the tool's set, an **expired** assertion, and an assertion with
  no `exp` or one longer-lived than the short bound the mock enforces
  (minutes, not hours; the exact bound is the builder's, asserted in a test)
  — each refusal a test, because E1-11's client is only conformant if
  nonconformance is distinguishable, and the lifetime bound is what makes
  that client honest about assertion life: a tool-signed bearer assertion
  with unbounded `exp` is a credential that stays usable wherever it leaks.
- Compose wiring unchanged except what the new routes need; ADR 0037's
  compose-literals rule holds.

## Acceptance criteria

1. One change carries all four parts; a checklist in the PR body maps each
   part to its diff hunk (the carried entry's "partial is worse than absent"
   made literal).
2. A roster-shaped token request performed the way `pylti1p3` performs one —
   assertion signed with the tool's key, token returned, token attached —
   succeeds against the mock in an integration test **without** `pylti1p3`
   in the loop yet (the library arrives with E1-08/E1-11; this test speaks
   raw HTTP so the mock's conformance is proven independently of the client
   that will consume it).
3. The six refusal cases above fail as specified.
4. The tool's JWKS route serves the public key in every environment and never
   the private half (asserted, not assumed).

## Out of scope

- Any tool-side service call (E1-11 builds the client).
- AGS score posting (E3's; the scopes are advertised now because the token
  endpoint's scope list is one artifact, but no AGS client exists in E1).
- Deliberately wrong *launches* (E1-07 — different surface, same mock).
