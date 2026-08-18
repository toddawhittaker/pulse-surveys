# E0-30 — Review debt from E0-16

**ID:** E0-30
**Branch:** `e0/review-debt-e0-16`
**Depends on:** E0-16

## Status — what is left here

**Built as written.** All four items are in `mock-idp/` or in the one Compose
line that points at it, so this ticket is already the batch.

Item 1 is the work — the reviewer's estimate is about 40 lines plus tests, and
the split point already exists in `begin()` immediately after `redirect_uri`
validates. Items 2 and 4 are records that ride with it.

Item 3 stays here rather than moving to [E0-18](E0-18-e0-exit-smoke.md), because
it is a `mock-idp` variable — but **E0-18 settles its value**, since only E0-18
knows how the browser reaches `api`. Confirmed still
`http://api:8000/auth/oidc/callback` in `docker-compose.yml`.


## Context

What E0-16's two review passes found and could not close in place, collected the
way E0-21 collects E0-05's and the tickets after it collect theirs. What could be
closed in E0-16's own pull request was, and it is indexed at the bottom.

**One item here is on E1's path and should not slide past it.** The rest are
limits of a gate, a Compose address E0-18 will have to change, and a strictness
choice worth affirming.

Read first: [ADR 0058](../../adr/0058-the-mock-provider-publishes-its-registration-and-its-seed.md),
[ADR 0062](../../adr/0062-a-request-is-parsed-once-at-the-edge.md), SPEC §9.2 and
§2.1, and `docs/MISTAKES.md` entries 2, 3, 13 and 29.

## Scope

### 1. RFC 6749 §4.1.2.1 error redirects are not implemented — and E1 needs them

Every refusal this provider makes after `client_id` and `redirect_uri` have
validated is a **400 page**. RFC 6749 §4.1.2.1 requires the error to be added to
the redirection URI's query once the redirect target is known good, carrying
`error`, `error_description` and `state`.

Holding the page for the first two checks is correct and required — you must not
redirect to a URI you have not validated. Extending it to everything else is not.

**Why it is E1's problem rather than a conformance footnote.** E1's
`/auth/oidc/callback` has an error branch — parse `error`, match the returned
`state` against the stored one, consume the pending login — that this mock makes
**unreachable**, so E1 ships it untested or does not ship it. E0-18's Playwright
specs cannot assert "the tool shows a login-failed page", because the browser
never leaves the mock. And the case that will actually occur in use is the user
cancelling, which is `access_denied` arriving by redirect.

**It got modestly more costly during E0-16, not less.** The ordering in `begin()`
is the right shape and the split point already exists immediately after
`redirect_uri` validates — but the fix rounds added three more refusals below that
line (unknown scope, malformed challenge, duplicate parameter), and
`AuthorizationRequestError` still carries prose with no `error` member. Unchanged
in structure, larger in volume. Reviewer's estimate: about 40 lines plus tests.

The sharpest instance, worth keeping in front of whoever decides: **the scope
refusal's own message cites "§4.1.2.1 `invalid_scope`" while being delivered by
the one mechanism §4.1.2.1 says not to use.**

Done when: either the redirect path exists for post-validation refusals, or SPEC
records that this mock deliberately does not implement it and says what E1 builds
its error branch against instead.

### 2. The ADR 0062 gate's three limits

`tests/unit/test_the_provider_judges_the_value_that_arrived.py` sweeps every
`strip`, `lower`, `upper`, `casefold`, `split` and `unquote` under `mock-idp/app/`
by AST against four permitted shapes. ADR 0062 now states what it covers **and**
what it does not, which is the half that matters:

- **The swept set is six names because six were measured against this tree.**
  `rstrip`, `lstrip` and `replace` are not swept. Widening the set without
  measuring would fail the gate on ground nobody has looked at.
- **It is syntactic, not dataflow.** It sees the shape of a call, never where the
  value came from.
- **It reads the source, not the running application**, so a normalisation reached
  through `getattr` or inside a library call is invisible.

A sixth mechanism arriving by another route is still caught by review or by
nothing. That is now a true statement about the residue rather than about the
whole rule, which is the improvement — but it is residue, and E1 adds a second
service that will want the same gate.

### 3. `MOCK_IDP_TOOL_REDIRECT_URI` will need repointing for E0-18

It is `http://api:8000/auth/oidc/callback`. Two things are unsettled: E1 has not
chosen that path, and a browser on the host reaches `api` at `localhost:8000`
rather than at the Compose service name. E0-18 drives this with Playwright from
the host, so it is one Compose line — but it is a line somebody has to know to
change, and the failure if they do not is a redirect the browser cannot follow.

### 4. A strictness choice to affirm rather than fix

`openid␠␠email` — an empty token between two valid ones — is **refused**, because
an empty token is not RFC 6749 Appendix A.4's `1*NQCHAR`. Some real servers
tolerate it. The reasoning for keeping it strict: a client that satisfies this
provider satisfies every real one, and the reverse leniency is the whole subject
of E0-28. Worth an explicit affirmation so the next person meeting a refused
double space does not read it as a bug.

## Out of scope

- Tool-side OIDC login, session handling, and the unified session model (E1).
- Role and purview resolution from claims (E1, E9).
- Any real institutional identity provider.

## Acceptance criteria

- [ ] Item 1 is settled — implemented, or recorded in SPEC with what E1 builds
      against instead. It is settled **before** E1's login work starts, not after.
- [ ] Item 2's limits are still accurate against the gate as it then stands, and
      the ADR is corrected if the swept set has changed.
- [ ] `MOCK_IDP_TOOL_REDIRECT_URI` is correct for however E0-18 drives the browser,
      and whatever makes it correct is recorded rather than discovered.
- [ ] Item 4 is affirmed or reversed in ADR 0062 or in the provider's own record.

## Definition of done

**Tests apply** to item 1 if it is implemented — the refusal must arrive as a
redirect carrying `error` and the `state` that was sent, and a test must fail if
it reverts to a page.

**Docs apply** to all four items.

**AI evals do not apply.**

**Accessibility does not apply** — a test harness, not a product surface.

**Security review applies and matters for item 1.** An error redirect carries
attacker-influenced values to a validated URI; the `state` echo is what makes it
safe, and the exactness rule E0-16 established is what makes the echo trustworthy.

## What E0-16's review did close

Two HIGH and seven smaller findings across two passes, all closed in E0-16's own
pull request:

- **HIGH** — every parameter stripped before the shape check, so PKCE bound an
  unbounded set of strings rather than one, and `state` and `nonce` were silently
  repaired. `base64.encodebytes()` appends exactly the newline that triggered it.
- **HIGH** — the two-hat person deletable from the seed with all 49 tests green,
  and with her removed a session leaking every assignment also stayed green.
- **MED** — `scope.split()` splitting on tab, newline and U+00A0, which meant the
  unknown-scope refusal added one round earlier could never fire.
- **MED** — the duplicate-parameter rule applied per source, so a parameter sent
  once in the query and once in the body was not refused, and `README.md` stated
  the closed property in words measurement contradicted.
- **MED** — unknown scopes accepted, and `email`/`profile` claims issued on an
  `openid`-only grant.
- **MED** — `roles_claim` missing from ADR 0058's contract, so E1 would hard-code
  the claim URI.
- **MED** — the assistant dean seeded outside criterion 6's enumeration.
- **LOW** — a bare `#` reading as falsy and registering; a registered query
  already carrying `code` or `state`; an absent `grant_type` answered
  `unsupported_grant_type` where §5.2 assigns `invalid_request`.
- **LOW** — the token endpoint's refusal asserted as any 4xx rather than §5.2's
  400.

ADR 0062 came out of the round rather than out of the ticket: five of the six
defects were one shape — a value re-derived downstream of where it was parsed —
and every fix had been local.
