# 0134 — The mock's AGS routes each name the scopes that open them, and `/mock/` stays open

Supersedes in part [ADR 0099](0099-the-mock-enforces-a-token-on-nrps-and-not-on-ags.md),
whose decision that AGS does not enforce ends here. Everything that record says
about NRPS, about the RFC 6750 vocabulary and about why enforcement waits for a
client still stands.

## Context

ADR 0099 left the mock platform's AGS surface answering without a credential and
named the condition for closing it: "enforcement pairs with the first conformant
client, because a service refusing before one exists would be refusing this
repository's own tests". E3-04 builds that client, so the condition is met, and
the two halves ship together — which is what makes the pairing structural rather
than a promise, after the same promise was made once before about E1-11 and not
kept.

What is left open is the mapping. RFC 6750 fixes the statuses and the two error
codes; AGS 2.0 defines four scopes and says what each is *for*, and does not say
which route each opens, because that is a property of a platform. This mock's
whole job is to be built against, so its answer becomes the shape E3's client is
written to — and a shape looser than a real platform's is one this repository
would ship a client against and discover in the field.

Two of the four scopes are the interesting case. `…/scope/lineitem` and
`…/scope/lineitem.readonly` are a writing scope and its read-only sibling, so a
route that only reads is opened by either — which means a route accepts a **set**
of scopes and not one. It is also the pair that makes the carried entry's
question answerable for the first time: the read-only string contains the writing
string as a prefix, so any check written as a substring or a prefix test hands a
read-only credential the ability to create a gradebook column, and until both
existed on one service nothing in this repository could tell those two
implementations apart.

## Decision

**Every AGS route requires an `Authorization: Bearer <token>` this platform's own
token endpoint issued, carrying one of the scopes below.**

| Route | Accepted scopes |
|---|---|
| `POST …/line_items` | `…/scope/lineitem` |
| `GET …/line_items` | `…/scope/lineitem` **or** `…/scope/lineitem.readonly` |
| `GET …/line_items/{id}` | `…/scope/lineitem` **or** `…/scope/lineitem.readonly` |
| `POST …/scores` | `…/scope/score` |
| `GET …/results` | `…/scope/result.readonly` |
| `GET …/results/{userId}` | `…/scope/result.readonly` |

The statuses and codes are ADR 0099's, unchanged: a missing or unreadable
credential is 401 with a bare `WWW-Authenticate: Bearer` and no error code (RFC
6750 §3.1 — nothing was presented to find fault with); a token this platform did
not sign, or one that has expired, is 401 with `error="invalid_token"`; a token
it issued for a scope the route does not take is 403 with
`error="insufficient_scope"` and a `scope` parameter listing every scope that
would have opened the route, space-delimited.

**The check is membership of RFC 6749 §3.3's space-delimited list, never a
substring or a prefix test**, and `app.tokens::authorised_token` is the one place
it happens. Where a route accepts several scopes, any one of them passes.

**The credential is judged before anything else about the request** — before the
query parameters and before the context or line-item lookup — so an
unauthenticated caller learns that it needs a credential and learns nothing about
which sections this platform seeds, which filters a container implements, or
where its cursor starts. That is the roster route's own order, copied.

**So both containers' `ge=1` page bounds move out of the route signatures**,
which is ADR 0099's own recorded consequence arriving. A constraint declared on a
route parameter is enforced by the framework before the handler runs at all, so
`?page=0` answered 422 — naming the parameter, its bound, and the fact that the
container pages — to a caller who had presented nothing. `page` and `limit` are
unbounded strings now, judged by `app.paging::page_number` behind the credential,
and a value that is not a whole number from one upwards is refused **400** naming
the parameter. 400 is E0-28 item 2's code for a parameter a container will not
serve on, and is deliberately not the 404 that a page *past* the end answers with.

**The `/mock/` prefix stays open, by decision.** `GET /mock/posted-scores` and
`GET /mock/defects` are inspection surfaces no real platform serves (ADR 0047),
so there is no protocol credential to ask for and nothing a conformant tool could
present. Saying so here is the point: a reviewer reading the enforcement can tell
a decision from an oversight, and a test asserts it, so an enforcement applied to
the application rather than to the routes is caught.

## Alternatives rejected

**One scope per route, with the line-item reads requiring the writing scope.**
Simpler to implement — a single string per route — and it makes the read-only
scope unusable, so a tool that holds only `…/scope/lineitem.readonly` is refused
a read AGS 2.0 grants it. It would also have hidden the superstring question
entirely, since no route would ever be reached with the read-only scope.

**One scope per route, with the line-item reads requiring the read-only scope.**
The mirror error, and worse: a token granted the writing scope alone could not
list the container it is about to write to, so the client's own find-or-create
would need both scopes on every run — which is the union this repository's client
deliberately does not ask for.

**Enforce with a FastAPI dependency on the application, or middleware over every
path.** Less code and it cannot be forgotten on a new route. It also takes the
`/mock/` prefix with it, which removes the only surface that can say what a tool
*sent* (ADR 0047) — a conformant `Result` carries no timestamp and no progress
members — and with it the evidence E3-04's byte-exact carriage criterion rests
on. Per-route is more code and it is the code that makes the exception a decision
instead of an accident.

**Leave the page bounds in the signatures.** One word each, and it reads as
tidier than a check inside the handler. It is the exception that makes the
ordering claim unusable: a claim with one exception is a claim nobody can rely
on, and the leak is small but real — that this container pages, what its cursor
is called, and where it starts, to a caller who presented nothing.

**Delete the page bounds rather than moving them.** An unauthenticated `?page=0`
is then 401 exactly as required, and an authenticated one is served page one as
though the cursor had never been sent — so a tool walking with a broken cursor
reads the same page for ever and never learns why.

## Consequences

- Every test that drove a mock AGS route without a credential goes red at once.
  The repair is at the fixture layer — `MockPlatform` grows a per-scope token and
  every AGS helper attaches the right one — and it rode the tests-first commit,
  which is `docs/MISTAKES.md` entry 22 budgeted for rather than met by surprise.
- `authorised_token` now takes one scope or several. The roster's call is
  unchanged and still passes a single string.
- The two AGS containers answer 400 rather than 422 for a page or a limit that is
  not a whole number, and 400 rather than 422 for one below the bound. The roster
  already answered 400 for the same thing, so the platform now says one thing
  everywhere.
- `page_number` is asked about `limit` as well as `page`. The grammar is the same
  — a run of at most nine ASCII digits, one or more — so the reuse is exact, and
  `page_size` still clamps an over-large value rather than refusing it.
- The carried entry about the mock's scope check being only provably a membership
  check is discharged: `…/scope/lineitem.readonly` is an advertised superstring of
  `…/scope/lineitem`, and both halves of the pair are asserted on the route that
  creates a gradebook column.
- Every AGS call costs an RSA verification. The handlers are synchronous, so
  FastAPI runs them off the event loop, and this is a development stack.
