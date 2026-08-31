# 0102 — The framing policy is read from the registration table, per document

## Context

E1-04 item 2's done-when gives the app factory a deliberate header set on every
response: a Content-Security-Policy, `X-Content-Type-Options: nosniff`, a
`Referrer-Policy`, and "a `frame-ancestors` directive naming who may frame the
app". SPEC §7.3 and §7.6 make the constraint concrete: Pulse renders inside an
LMS iframe, so the framing policy has to admit the platforms that legitimately
frame a launch and nothing else.

Who may frame the app is not a fixed list. The browser-facing origin a platform
launches from is its `authorization_endpoint`, a column of `lti_platform` that
E1-05 made a property of each registration rather than of the process — and
`launcher_origins` already derives the distinct `scheme://host[:port]` origins of
that column for the developer console. A platform can be registered while the
process runs, so any set computed once at startup is wrong the moment a
registration is added.

Two things the spec leaves open, and a reasonable engineer might decide either
differently: how the middleware reads the registration table (a FastAPI
middleware runs outside the request-scoped session a route is handed), and which
responses carry the framing directive. `Referrer-Policy` has no single value the
spec names either.

## Decision

**One derivation of one column.** `launcher_origins` moves from `app.api.dev`
(the developer-console router) to `app.lti.registration`, the platform-config
module SPEC §13 names, and both the console and the middleware import it. A
security control importing a helper from a dev-console router is a layering
smell, and a second copy of the origin derivation is `docs/MISTAKES.md` entry 13
exactly. `dev.py` keeps importing the moved function.

**The static headers go on every response; `frame-ancestors` goes only on
documents.** A middleware registered last in `create_app()` wraps the whole
application, so the API, the SPA mount and a 404 no route handled all carry
`nosniff`, the `Referrer-Policy` and the base CSP (`default-src 'self';
script-src 'self'`) — none of which touches the database. Only a document can be
framed, so `frame-ancestors 'self'` plus the registered origins is added only to
`text/html` responses, read per request through `launcher_origins`. The read is
synchronous SQLAlchemy, so it runs in a worker thread rather than on the event
loop.

**The read is per request, not cached.** The table holds a handful of rows behind
a unique index, so the read is cheap, and correctness — the policy tracks a
platform registered after the process started — beats a cache that would then owe
an invalidation story on every registration write.

**Serving a document does not depend on a reachable database.** The single-page
application is a static shell that then calls the API; a read that cannot reach
`lti_platform` degrades to `frame-ancestors 'self'` alone — the app's own frame,
and never wider. That is fail-closed (a stricter policy, not a laxer one: the LMS
iframe simply does not load until the database is back), and it is what lets the
factory's own unit tests serve the SPA mount and `/docs` with no database. An
empty table is a normal read and answers `'self'` the same way; only an error is
caught, and the integration suite asserts the real origin set against a real
database, so a *wrong* read is caught loudly rather than degraded.

**`Referrer-Policy: strict-origin-when-cross-origin`.** It keeps the full URL —
path and query — off every cross-origin request while still sending the origin.
Inside an LMS iframe that URL identifies a section and a person's place in it, so
`unsafe-url` and the browser's own no-header default are both rejected.

**The emitter admits only syntactically valid origins and drops a malformed
one.** `launcher_origins` builds each source as `scheme://host[:port]` from a
stored `authorization_endpoint`, and `urlsplit` strips neither a space nor a `;`
nor a `,` nor a `*` from the host. The registration chokepoint (ADR 0081) does
not reject those characters on `authorization_endpoint` either — it is
browser-facing, not resolve-judged — so a stored `https://lms.edu *` would emit
`frame-ancestors 'self' https://lms.edu *`, whose bare trailing `*` lets any
origin frame the app, and a stored `https://lms.edu;script-src *` would graft a
second CSP directive onto the header. So `launcher_origins` matches each
candidate origin against a compiled pattern — `http`/`https`, a hostname or IPv4
or bracketed IPv6 host, an optional numeric port, and no whitespace, `;`, `,`,
`*`, quote or other CSP-breaking character — and drops any origin that does not
match. This is fail-closed for that platform: a malformed endpoint contributes no
framing source (and no developer-console link), so its iframe simply is not
permitted rather than every origin's being permitted. The fix sits in
`launcher_origins` itself, at the root of the derivation, so both consumers
benefit and the header is robust however the column was written.

**The CSP needs no `'unsafe-inline'` anywhere.** A real `npm run build` (Vite 8)
emits the entry document with an external module script
(`/app/assets/index-*.js`) and an external stylesheet (`/app/assets/index-*.css`)
and injects neither inline. So `script-src 'self'` refuses inline script with
nothing to bless, and the same-origin stylesheet is covered by `default-src
'self'` with no `style-src` of its own.

## Alternatives rejected

- **A static, env-configured origin list.** It drifts from the registrations it
  is meant to mirror — it is the process-wide setting E1-05 deleted, arriving
  back under another name — and it cannot express the empty-table case or a
  platform registered after boot.
- **`frame-ancestors` on every response, including JSON.** It would put a
  database read on every `/healthz` liveness probe and every JSON body a browser
  never frames, for a directive only a document can use.
- **Computing the origin set once in `create_app()`, or memoising it for the
  process.** A hardcoded list built at run time: right on the day it is written
  and wrong the moment a registration is added. Caching with a real invalidation
  story is permitted; a cache with none is what the after-registration test
  fails.
- **Failing the response when the registration read fails.** It would make
  serving the static SPA shell — and `/docs` — depend on a reachable database,
  worse availability than the outage already is, and it would take down the
  factory's DB-less unit tests over the mount rather than over the database.

## Consequences

- **`launcher_origins` now lives in `app.lti.registration`.** The console and the
  framing policy read one derivation; a rename or a change to how an origin is
  computed happens in one place.
- **The SPA entry document and `/docs` now carry a `frame-ancestors` derived from
  the database when one is reachable.** In the factory's DB-less unit tests they
  carry `'self'` alone through the degrade path, so those tests still assert only
  what they are about — that the mount and the docs route are served.
- **`Referrer-Policy` is pinned to one value.** The header test admits a closed
  set of deliberate policies; narrowing it to `strict-origin-when-cross-origin`
  alone is the right edit now that this ADR names it.
- **The e2e canary is what proves the browser actually frames.** This module says
  only what the header contains; `tests/e2e/cookieless-launch.spec.ts` is the
  proof that a real LMS iframe loads under the enforced policy, and it is the
  check for any runtime inline style the built stylesheet does not cover.
- **The source-side validation is owed to E11.** The emitter now drops a
  malformed origin, so the header is robust whatever the column holds — but the
  registration chokepoint still stores an `authorization_endpoint` carrying a
  space, a `;`, a `,` or a `*` verbatim, because it judges the address for SSRF,
  not for CSP syntax. E11 takes the endpoint from an untrusted party through
  dynamic registration, so it owes a write-time rejection of a CSP-breaking
  `authorization_endpoint` at the chokepoint. Recorded in
  `docs/tickets/e1/deferred.md` and `docs/tickets/e2/carried-from-e1.md`.
