# 0088 — A query parameter selects one wrong launch per mint

## Context

E1-07 gives the mock platform a way to mint a launch that is wrong in exactly
one named way — a bad signature, an `alg` the LTI 1.3 security framework does
not permit, a claim the registration would refuse — so that E1-08's tool-side
refusal tests have an invalid half of each guard to drive, not only the valid
half E0-14 built. `docs/MISTAKES.md` entry 28 is why this matters: a driver
that can only speak correctly leaves every one of those guards untestable on
its refusing side.

The ticket leaves the interface open in as many words: "a launch page
parameter or a dedicated endpoint — the builder's call." `docs/SPEC.md` does
not mention a wrong-launch mint at all, so this is silent on both halves ADR
practice asks for — the spec does not decide it, and a reasonable engineer
could build it three different ways. Three decisions ride together because one
implementation answers all three: the shape of the selector, how many defects
one mint may carry, and where `reused_nonce`'s replayed bytes come from.

## Decision

**1. One query parameter, `?defect=<name>`, on the existing authorization
endpoint (`/oidc/authorize`), read off the request's URL regardless of
`GET` or `POST`.** A request that omits it runs the exact two lines it ran
before this ticket — `key.compact_jws(id_token_claims(resolved, settings))`,
`state=resolved.state` — so the happy path stays byte-identical, which is
acceptance criterion 2. The parameter is read from `request.query_params`
rather than from the parsed form body, deliberately: it is this suite's own
instruction to the mock, not a value an OIDC authorization request carries,
and it must never collide with a real parameter name a tool might one day
send.

**2. Exactly one defect per mint, and the vocabulary is one tuple.**
`app.wrong_launches.ALL_SELECTORS` names every selector this platform answers
to — the fifteen wrong-launch names and the three near-miss/edge fixture
names, together, because both groups are asked for the same way. A name
outside that tuple is refused with a 400 that names it, through the same
`AuthorizationRequestError` every other malformed authorization request
raises. `WrongLaunchMinter.mint` dispatches on the name with one branch per
selector; nothing composes two defects into one mint, on the ticket's own
rule that a launch wrong two ways is two tests that cannot tell which guard
fired.

**3. `reused_nonce`'s replayed token is a mock-process-local cache, keyed by
`nonce`, held on one `WrongLaunchMinter` instance per running platform.** The
first request naming `reused_nonce` for a given `nonce` mints an ordinary
correctly-signed token and remembers it; every later request naming
`reused_nonce` with that same `nonce` is handed back the identical bytes —
same `iat`, same `exp`, same signature — rather than a fresh mint. That is
what makes it a replay of one signed artifact rather than a second launch
that happens to reuse a nonce *value*. The cache is created fresh in
`create_app`, alongside the issuer key and `GradeBook` (ADR 0049 already
makes per-app, in-memory, reset-on-restart state this mock's normal shape for
exactly this kind of thing), and it is never persisted.

**4. `foreign_signature`'s key is generated lazily, on first use, and cached
for the app's lifetime — not at startup, and not per request.** Generating an
RSA key costs 0.29–0.80 seconds (ADR 0035's own measurement); paying that at
`create_app` time for every platform this suite starts, whether or not a test
ever asks for `foreign_signature`, would roughly double the ten seconds ADR
0035 already prices in for a suite that starts about two dozen platforms.
Paying it once per request would make a test that mints this selector twice
pay it twice for no reason: nothing about the key needs to change between two
calls to the same platform.

## Alternatives rejected

**A dedicated endpoint per defect, or one dedicated endpoint parametrised by
body.** The authorization endpoint already runs every check a correct launch
must pass — `client_id`, `redirect_uri`, `state`, `nonce`, the seeded
enrollment — and a defect that is supposed to look like an otherwise-normal
launch (every claim-value and return-leg defect here) needs all of that to
run unchanged first. A second endpoint either duplicates `resolve_launch`
(two places that can drift, `docs/MISTAKES.md` entry 13's shape) or skips
those checks (a mint that never resembles what a tool actually receives from
this platform). Reusing the one flow a correct launch already travels avoids
both.

**Encoding the defect in a field the protocol already defines** — a magic
prefix on `state` or `login_hint`, say. Rejected because those are values a
real tool sends and a real platform echoes or resolves; overloading one with
a second meaning couples the selector to protocol semantics it has nothing to
do with, and a `tampered_state` mint could not use `state` as its own
selector without contradicting itself.

**A header, e.g. `X-Mock-Defect`.** Rejected on the consumer: E1-08's
Playwright specs (and any human clicking through the launch page) drive a
browser through links and form submissions, and a browser-driven test cannot
attach an arbitrary header to a navigation the way it can append a query
string to a URL. A query parameter is addressable from an `<a href>` or a
form's `action`; a header is not, from the surface E1-08 actually drives.

**Persisting `reused_nonce`'s cache** — a file, a table, anything that
survives a restart. Rejected as unearned: the mock's whole existence is
per-run (SPEC §9.1, ADR 0035), nothing else in it survives a restart either,
and a replay test needs the second call to arrive within the same process
the first one did — which every test in this suite already assumes of the
platform it started.

## Consequences

**The selector vocabulary is duplicated, not imported, everywhere it is
consumed.** `mock-lms/app` and `mock-idp/app` are both packages literally
named `app` (SPEC §13); `docs/adr/0039-the-two-app-packages-are-typechecked-
in-two-runs.md` records the same collision for mypy, and a test module that
imported `app.wrong_launches` by name would depend on which of the two
happened to be on `sys.path` first. `tests/integration/test_mock_lms_wrong_
launches.py` therefore copies the fifteen-plus-three strings as its own
constants, and E1-08's Playwright spec will have to do the same. A name
renamed in `app.wrong_launches` without a matching rename in every copy fails
loudly — the dispatcher's 400 names the value it did not recognise — rather
than silently, but it is still two (soon three) places to change together for
one rename, and nothing enforces that other than this record and the
practice of grepping for the old string.

**`WrongLaunchMinter` is the one piece of mutable, per-app state this ticket
adds**, and it is deliberately in the shape `app.ags.GradeBook` already
established rather than a new one: created once in `create_app`, closed over
by the route, gone when the process is. A platform started twice in one test
(`mock_platforms`, used for the two-platform criteria E0-14 and E1-06 both
carry) gets two independent minters, two independent replay caches, and two
independent lazily-generated foreign keys — the same isolation every other
per-app value in this file already has.

**A defect name travels in the request's query string**, which means it
reaches uvicorn's own access log the way `state`, `nonce` and `login_hint`
already do on a `GET` authorization request (`main.py`'s own documented
tradeoff). That is not a new exposure: a defect name is this ticket's own
vocabulary, invented here, and identifies nobody — it is the same shape of
non-concern the existing three values already are, not a new one this record
introduces.
