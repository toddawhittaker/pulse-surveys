# E0-30 — Review debt from E0-16 (Batch F: mock IdP error redirects)

**ID:** E0-30
**Branch:** `e0/review-debt-e0-16`
**Depends on:** E0-16; item 3 is settled by E0-18, so build this after it

## Status — what is left here

**All four items are in `mock-idp/` or in the one Compose line that points at
it, so this ticket is already the batch.** Re-verified against the epic branch
on 2026-08-21; file and line references below are current.

**Item 1 is decided as of 2026-08-18: implement the redirects.** Items 2 and 4
are records that ride with it. Item 3 is settled by E0-18 — this ticket
records the answer rather than choosing one.

**Of the four remaining E0 batches, this one goes first.** E1's login error
branch cannot be tested until this provider sends error redirects, and E1 is
the next epic.

## Context

What E0-16's two review passes found and could not close in place. What could
be closed in E0-16's own pull request was, and it is indexed at the bottom.

Read first: [ADR 0058](../../adr/0058-the-mock-provider-publishes-its-registration-and-its-seed.md),
[ADR 0062](../../adr/0062-a-request-is-parsed-once-at-the-edge.md), RFC 6749
§4.1.2.1 and §3.1, SPEC §9.2 and §2.1, and `docs/MISTAKES.md` entries 2, 3, 13
and 29.

## Scope

### 1. RFC 6749 §4.1.2.1 error redirects are not implemented — and E1 needs them

Every refusal this provider makes after `client_id` and `redirect_uri` have
validated is a **400 page**. §4.1.2.1 requires the error to be added to the
redirection URI's query once the redirect target is known good, carrying
`error`, `error_description` and the `state` that was sent.

**Why it is E1's problem rather than a conformance footnote.** E1's
`/auth/oidc/callback` has an error branch — parse `error`, match the returned
`state`, consume the pending login — that this mock makes **unreachable**, so
E1 ships it untested or does not ship it. And the case that will actually
occur in use is the user cancelling, which is `access_denied` arriving by
redirect. The sharpest instance of the current state: the scope refusal's own
message cites "§4.1.2.1 `invalid_scope`" while being delivered by the one
mechanism §4.1.2.1 says not to use.

**The design, concretely.** The split point exists in
`app/flow.py::Flows.begin` immediately after the `redirect_uri` check (the
first two refusals in `begin`, and only those, stay pages — you must never
redirect to an address you have not validated).

- `AuthorizationRequestError` (`flow.py:167`) gains an `error` member — the
  §4.1.2.1 code — beside its prose, which becomes `error_description`. Every
  raise site names its code; the handler stops guessing.
- Codes, per raise site in `begin`: `response_type` →
  `unsupported_response_type`; the three scope refusals (grammar, missing
  `openid`, unknown scope) → `invalid_scope`; a missing `state`, `nonce` or
  `code_challenge` (`required`) → `invalid_request`; a malformed challenge or
  wrong `code_challenge_method` → `invalid_request` (RFC 7636 §4.4.1 assigns
  exactly that, with the reason in `error_description`).
- The two refusals in `sign_in` (`flow.py:502`) — unknown subject, and the
  wrong-door person §2 refuses — become `access_denied` redirects. A refused
  login still spends the pending request; that rule does not change.
- The duplicate-parameter check in `app/main.py::authorize` (line 205)
  currently runs before any validation and answers a page. Reorder: a
  duplicated `client_id` or `redirect_uri` stays a page (neither can be
  trusted); any other duplicated parameter, once those two have validated, is
  an `invalid_request` redirect. This is a second place the page-vs-redirect
  line is drawn, so it gets its own tests.
- `state` is echoed exactly as it arrived. Error parameters are *added to*
  the registered URI's query, not substituted for it — a registered URI may
  legitimately carry its own query (only one already holding `code` or `state`
  is refused at registration), so use `&` where a query exists. If the refusal
  is that `state` itself is missing, the redirect carries no `state`
  parameter, per the RFC's "if present".

Reviewer's estimate from the round: about 40 lines plus tests. The refusal
volume has grown since (unknown scope, malformed challenge, duplicate
parameter were added by E0-16's own fix rounds), so expect somewhat more.

**Done when** every post-validation refusal arrives at the registered
redirect URI carrying `error`, `error_description` and the echoed `state`; a
test per code fails if that refusal reverts to a page; and the two
pre-validation refusals provably remain pages (the near-miss: an *unregistered*
`redirect_uri` plus an invalid scope must yield a page, never a redirect to
the unregistered address — that mutation is the whole point of the ordering).

### 2. The ADR 0062 gate's three limits

`tests/unit/test_the_provider_judges_the_value_that_arrived.py` sweeps every
`strip`, `lower`, `upper`, `casefold`, `split` and `unquote` under
`mock-idp/app/` by AST against four permitted shapes. ADR 0062 states what it
covers and what it does not: the swept set is six names because six were
measured against this tree (`rstrip`, `lstrip`, `replace` are not swept); it
is syntactic, not dataflow; it reads the source, not the running application.

Item 1's implementation edits exactly the files this gate sweeps. **Done
when**, after item 1 lands, the ADR's three stated limits are still true of
the gate as it then stands, and the ADR is corrected if the swept set had to
change. This is a re-verification, not new machinery.

### 3. `MOCK_IDP_TOOL_REDIRECT_URI` — settled by E0-18, recorded here

E0-18 drives the browser from the host, so the variable is repointed to
`http://localhost:8000/auth/oidc/callback` in `docker-compose.override.yml`
(dev and CI wiring, absent from deployments); the base-file default stays the
container-facing address. E0-18 makes the change; **done when** this file and
the comment beside the variable in `mock-idp/app/config.py` (line 188) both
state the settled answer instead of anticipating one.

### 4. A strictness choice to affirm rather than fix

`openid␠␠email` — an empty token between two valid ones — is **refused**,
because an empty token is not RFC 6749 Appendix A.4's `1*NQCHAR`. Some real
servers tolerate it. The reasoning for keeping it strict: a client that
satisfies this provider satisfies every real one; the reverse leniency is the
whole subject of E0-28. **Done when** the affirmation is recorded — a short
addition to ADR 0062's consequences or to the provider's module docstring, so
the next person meeting a refused double space finds a decision, not a bug.

## Out of scope

- Tool-side OIDC login, session handling, and the unified session model
  (E0-18 builds the walking skeleton; E1 builds the rest — this ticket touches
  only the provider).
- Any leniency toggle. The provider stays strict; item 1 changes the
  *transport* of a refusal, never its verdict. A request refused today is
  refused after this ticket, with the same reasoning in `error_description`.
- Role and purview resolution from claims (E1, E9). Any real institutional
  identity provider.

## Acceptance criteria

- [ ] Every post-validation refusal in `begin` and `sign_in` arrives as a
      redirect to the registered URI with `error`, `error_description` and the
      echoed `state`; one test per error code, each failing if the refusal
      reverts to a page.
- [ ] An unregistered `redirect_uri`, an unknown `client_id`, and a duplicated
      `client_id`/`redirect_uri` still produce pages — asserted, not assumed,
      with the unregistered-URI-plus-other-defect near-miss in the battery.
- [ ] A duplicated non-critical parameter redirects with `invalid_request`.
- [ ] The user-cancel shape E1 will meet — `access_denied` with the echoed
      `state` — is producible from the login form and tested.
- [ ] ADR 0062's stated limits are re-verified against the post-change gate;
      the ADR is amended if the swept set changed.
- [ ] Item 3's settled value is recorded here and in `config.py`'s comment.
- [ ] Item 4's affirmation is in the record.
- [ ] The redirect behaviour is verified by mutation, including the ordering
      near-miss above.

## Definition of done

**Tests apply** — item 1 is tests-first throughout. **Docs apply** to all four
items. **AI evals do not apply. Accessibility does not apply** — a test
harness, not a product surface. **Security review applies and matters for
item 1:** an error redirect carries attacker-influenced values to a validated
URI; the exact-match registration rule is what makes the redirect safe, and
the exact `state` echo is what makes it useful. The one HIGH-shaped mutation
to try is the ordering one — a refusal that redirects before `redirect_uri`
validates is an open redirector, and the suite must catch it.

## What E0-16's review did close

Two HIGH and seven smaller findings across two passes, all closed in E0-16's
own pull request:

- **HIGH** — every parameter stripped before the shape check, so PKCE bound an
  unbounded set of strings rather than one, and `state` and `nonce` were
  silently repaired. `base64.encodebytes()` appends exactly the newline that
  triggered it.
- **HIGH** — the two-hat person deletable from the seed with all 49 tests
  green, and with her removed a session leaking every assignment also stayed
  green.
- **MED** — `scope.split()` splitting on tab, newline and U+00A0, which meant
  the unknown-scope refusal added one round earlier could never fire.
- **MED** — the duplicate-parameter rule applied per source, so a parameter
  sent once in the query and once in the body was not refused, and `README.md`
  stated the closed property in words measurement contradicted.
- **MED** — unknown scopes accepted, and `email`/`profile` claims issued on an
  `openid`-only grant.
- **MED** — `roles_claim` missing from ADR 0058's contract, so E1 would
  hard-code the claim URI.
- **MED** — the assistant dean seeded outside criterion 6's enumeration.
- **LOW** — a bare `#` reading as falsy and registering; a registered query
  already carrying `code` or `state`; an absent `grant_type` answered
  `unsupported_grant_type` where §5.2 assigns `invalid_request`.
- **LOW** — the token endpoint's refusal asserted as any 4xx rather than
  §5.2's 400.

ADR 0062 came out of the round rather than out of the ticket: five of the six
defects were one shape — a value re-derived downstream of where it was parsed —
and every fix had been local.
