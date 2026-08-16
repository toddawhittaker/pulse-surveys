# E0-14 — Mock LMS: JWKS and LTI 1.3 launch

**ID:** E0-14
**Branch:** `e0/mock-lms-launch`
**Depends on:** E0-02, E0-08

## Context

An in-repo mock LMS platform makes end-to-end runs fully self-contained: no live
LMS is needed for CI, and both entry doors get exercised on every run (§9.2).
This ticket builds the platform side of an LTI 1.3 launch — the part that signs
an `id_token` — so E1 has something real to validate against.

Read first: SPEC §9.2 (in-repo mock platform), §7.3 (LTI specifics, iframe
cookie survival), §2.1 (what the launch claims must carry), §13 (`mock-lms/`).

## Scope

- `mock-lms/` FastAPI application and `Dockerfile`, added to Compose as
  `mock-lms` with a health check.
- Issuer key generation per test run, and a JWKS endpoint serving the public
  key — §9.1 calls for issuer keys generated per test run rather than fixtures
  checked into the repository.
- OIDC third-party-initiated login endpoint and the authorization redirect.
- A signed `id_token` carrying the LTI 1.3 core claims: message type, version,
  deployment ID, target link URI, resource link, context (course and section),
  and roles.

  **The context claim's `title` is optional, and `course.lms_title` is
  `NOT NULL`.** In LTI 1.3 the context claim requires only `id`; `label`, `title`
  and `type` are all optional, so a conformant platform may send a course with no
  human-readable name at all. E0-05 shipped `course.lms_title` non-nullable, which
  was a deliberate call — it is trivially relaxed with `DROP NOT NULL` and
  expensive to tighten later — but it means tool-side ingestion needs a fallback
  rather than an assumption. Have this mock exercise both shapes: at least one
  seeded context with a title and one with `id` alone, so whoever writes the
  ingestion path in E1 meets the empty case in a test rather than in a
  deployment. The fallback itself is E1's to choose; `label`, or the prefix and
  number, are the obvious candidates.
- A launch page that posts the form to the tool, so a browser-driven test can
  click through a realistic launch.
- Seeded platform registration values matching what `lti_platform` from E0-08
  expects, so a developer can register the mock in one step.

## Out of scope

- NRPS and AGS endpoints, and seeded roster or line-item data (E0-15).
- Tool-side launch validation — state, nonce, clock skew, replay (E1). The mock
  produces launches; validating them is E1's work.
- Deep Linking (E1 or later; §7.3 makes plain resource-link launch the default).
- Platform quirk profiles for Canvas, Moodle, D2L, Blackboard (E1 and beyond).

## Acceptance criteria

- [ ] `docker compose up -d` brings `mock-lms` to healthy alongside the existing
      services.
- [ ] The JWKS endpoint serves a key that verifies the signature on an issued
      `id_token`.
- [ ] Issuer keys are generated per run; no private key is committed to the
      repository.
- [ ] An issued `id_token` contains every LTI 1.3 required claim, asserted field
      by field in a test rather than by eyeballing.
- [ ] The **authorization endpoint** returns the `state` it was given, unchanged,
      and the issued `id_token` carries the `nonce` from that same authorization
      request. Two launches carry different nonces.

      This read "the login-initiation endpoint round-trips `state` and `nonce`",
      which is untestable on this side of the protocol. In LTI 1.3 the
      login-initiation endpoint is the **tool's**: the platform calls it with
      `iss`, `login_hint` and `target_link_uri`, and neither `state` nor `nonce`
      exists yet at that point. Both are minted by the tool on its *authorization
      request to the platform*; the platform echoes `state` on the redirect and
      embeds `nonce` in the `id_token`. That is the property this ticket owns.
      *Validating* either is E1's — §14.3 puts "LTI launch validation
      (state/nonce…)" in E1's exit criteria, not here.
- [ ] The launch form posts to a configurable target link URI, so it can point
      at the tool once E1 exists.

      Two distinct URLs hide in that sentence, and the criterion is not asking
      about one of them twice: the form's **action** is the tool's OIDC
      login-initiation URL, while `target_link_uri` is a **claim inside the
      token** naming where the tool should land the user. Both are asserted
      separately — the action follows configuration rather than a constant that
      happens to equal it, and the claim matches what the launch page announced.
- [ ] A test can obtain a signed launch for an arbitrary seeded user and role
      without a browser, for use as an integration fixture. "Arbitrary" needs at
      least two seeded users and at least two seeded roles to have any content;
      the larger seed set is E0-15's.

## Definition of done

**Tests apply.** Integration tests asserting claim completeness and signature
verification against the served JWKS. A reusable fixture that mints a signed
launch — E1's launch-validation tests depend on it, so its interface matters.

**Docs apply.** `README.md` explains what the mock LMS is for and how to reach
it locally.

**AI evals do not apply.**

**Accessibility does not apply** — the mock is a test harness, not a product
surface.

**Security review applies and matters here.** Review that the mock cannot be
reached from a deployed environment, that its keys are never reused as anything
but test keys, and that no shortcut in the mock — an unsigned token path, a
skipped nonce — becomes a habit the real validation in E1 inherits.
