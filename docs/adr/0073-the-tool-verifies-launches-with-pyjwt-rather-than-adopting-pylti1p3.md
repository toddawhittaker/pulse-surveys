# 0073 — The tool verifies both doors' tokens with PyJWT, and `pylti1p3` waits for E1

**Status:** Accepted
**Date:** 2026-08-21
**Ticket:** [E0-18](../tickets/e0/E0-18-e0-exit-smoke.md)

## Context

E0-18 builds the tool side of two protocols at once: an LTI 1.3 launch and an
OpenID Connect authorization code flow. Both deliver an `id_token` signed
`RS256`, and neither can be admitted without checking that signature against the
issuer's published key set.

Nothing in the locked closure could do it. The two mocks *sign* with
standard-library arithmetic, and
[ADR 0035](0035-the-mock-platform-signs-with-standard-library-rsa.md) bounds that
explicitly to a development-only service holding throwaway keys — "read that
bound before copying anything out of this file". Copying it into the tool is the
one thing that record forbids.

[SPEC §13](../SPEC.md) names `pylti1p3` for the `lti/` package, which makes this
contestable rather than obvious: the spec has already named a library, and this
is the ticket that first needs one.

## Decision

**Pin `PyJWT==2.13.0` with `cryptography==50.0.0`, and do not adopt `pylti1p3`
in E0.** Verification lives in `backend/app/services/tokens.py`, one function
called by both doors, which fetches the key set through `app.state.http`, selects
the key the `kid` header names, and calls `jwt.decode` with the algorithm list,
the issuer and the audience passed explicitly.

`cryptography` is declared as a direct dependency rather than pulled in through
PyJWT's `crypto` extra. A bare `PyJWT` locks a closure that cannot verify RS256
at all, and the failure arrives at the first launch rather than at install time.
An import this project depends on is a dependency it names.

§13 stands. `pylti1p3` is not rejected as the eventual library — it is deferred
to the ticket that restructures this code anyway.

## Alternatives rejected, and what each costs

**Adopt `pylti1p3` now.** It buys nothing E0 needs and costs more than PyJWT.
It covers one of the two doors — there is no OIDC web-login client in it — so
the web door would need a second mechanism regardless, and the project would
carry two ways of verifying a token for the length of E0. It also wants a
framework adapter (a request/session/cookie shim per web framework), and this
project has no session model until E1, so the adapter would be written against a
session that does not exist and rewritten when one does. What is given up is
real and should be said: `pylti1p3` knows things about LTI that this code does
not — deep linking, the message-type vocabulary, service-token grants, and
platform quirks §7.3 gives to `lti/platforms/` adapters. E0 needs none of them,
and E1 gets them with the ticket that needs them.

**Copy the mock's RSA verification into the tool.** Free, in the sense that the
code already exists. Rejected outright: ADR 0035's bound is that this is
throwaway arithmetic for a fake platform where nothing confidential rests on the
keys. A hand-rolled PKCS#1 v1.5 verifier in the tool would be the code deciding
whether a real LMS's launch is genuine, and the failure mode of a subtly wrong
padding check is that forgeries verify.

**Verify with `cryptography` alone and parse the JWS by hand.** One fewer
dependency, since `cryptography` is needed either way. Rejected because the
by-hand part is exactly the part with the sharp edges — the `alg` header an
attacker writes, the `none` algorithm, `exp`/`aud`/`iss` comparison, the
base64url padding — and every one of them is a known JWT vulnerability class
with a known library answer.

## Consequences

- The runtime closure gains four entries: `pyjwt`, `cryptography`, and `cffi`
  and `pycparser` behind it. The license gate is clean — MIT and
  `Apache-2.0 OR BSD-3-Clause` — and adds nothing to the two `psycopg` rows that
  already ask for a human look.
- `cryptography` ships compiled wheels. It is the first dependency in this
  project with a native component that is not the database driver, and a
  platform without a wheel would build it from source. The runtime image is
  `python:3.13-slim` on the same architecture CI builds for, so this holds today
  and would be the first thing to check on a new architecture.
- **`backend/app/lti/` exists with one module in it, not five.** §13 lists
  `registration.py`, `launch.py`, `nrps.py`, `ags.py` and `platforms/`; E0-18
  ships `launch.py`, because the other four have no caller. A module with no
  caller is a guess at an interface.
- When E1 adopts `pylti1p3`, `app/services/tokens.py` does not go away: the web
  door still needs it, and `pylti1p3` covers only the launch. The likely end
  state is one verifier for the web door and the library for the launch door,
  which is a real cost of this decision and is the reason to expect the two to
  diverge rather than to try to keep them the same.
- For this to keep working, the algorithm list must stay a constant in
  `app/services/tokens.py`. The moment it is read from a token or from
  configuration, the library's protection is gone and this record is describing
  something that no longer happens.
