# 0140 — The CSRF sweep reads two currencies over a method-based inventory

## Context

E2 carried an entry into E3 saying that nothing structurally forces the next
mutating route onto the CSRF dependency: `require_student` and
`csrf_verified_student` sit beside each other in `backend/app/api/deps.py`, the
submit path reaches for the checked one, and nothing makes the next writing route
do the same. Its done-when asks for "a sweep over the built application's routes,
asserted in both directions so a stale exemption fails as loudly as an unguarded
route".

The ticket that builds the sweep settles three things and [SPEC](../SPEC.md) says
nothing about any of them: what counts as a mutating route, what the exemption
list may hold and what a new entry costs, and how the check is recognised on a
route. Each is contestable, so this record exists.

Two facts about this application shape all three. First, `include_router` on the
pinned `fastapi` 0.141.1 appends an `_IncludedRouter` wrapper carrying no `path`
and no `dependant`, so a walk over `application.routes` sees four documentation
paths and nothing this project serves (dispute E2-04-01, ruled 2026-09-01);
`tests/fixtures/routing.py::every_route` follows `original_router` and is what
the sweep walks. Second, `backend/app/api/dev.py` registers three routes by
appending route objects to `router.routes` rather than by a decorator, and an
appended route carries no dependency graph at all.

## Decision

**The inventory is every route of the built application whose `methods` is `None`
or holds anything outside `GET`, `HEAD` and `OPTIONS`.** By method and nothing
else — not by whether the route takes a body, not by anything a route declares
about itself — because those are properties an author chooses per route and this
inventory has to hold routes whose author never heard of it. `methods is None` is
the any-method registration `AnyMethodRoute` uses, which matches every verb and
is therefore in.

**The check is held in two currencies, and each has a control finding it on a
route that certainly holds it.**

1. `app.api.deps.csrf_verified_student` anywhere in the route's `dependant`
   graph, at any depth, matched as the **object** rather than by name. Three
   attachments reach that graph and all three are planted and found: a parameter
   default, the route decorator's `dependencies=`, and
   `APIRouter(dependencies=[...])`.
2. `isinstance(route, app.api.dev.DevControlRoute)`. An appended route offers
   nothing else to read, and a same-origin check written into a route class is a
   check a dependency-graph walk cannot see.

**A fourth attachment is refused rather than read.** Measured on `fastapi`
0.141.1 on 2026-09-05, when the sweep's own control planted it and came back
empty: a dependency passed as `include_router(..., dependencies=[...])` reaches
no route. `route.dependencies` is `[]`, the `dependant` graph holds only the
endpoint's own, and the list survives on the wrapper's private
`include_context.dependencies` and nowhere else. So the sweep fails loudly on any
reachable include carrying dependencies, names the paths under it and names the
keyword, and says where to attach it instead. The refusal runs on every walk
rather than in one test, so such an include reddens the sweep on the day it lands
rather than showing up as a set of routes that carry nothing. The two attribute
names are pinned as constants in `tests/fixtures/routing.py` and required to
exist: read through a `getattr` default, a FastAPI that renamed either would make
this check answer "no include-level dependencies" for every application forever
while every test around it stayed green.

**The exemption ledger is a mapping of path to one sentence, and an entry costs
that sentence plus both directions of assertion.** A sentence of at least sixty
characters saying why that route cannot hold the check — the number is arbitrary
and what it enforces is not, since a path added with `"dev"` beside it reads as a
ledger entry in a diff and is not one. The both directions:

- every exempt path must still be a mutating route this application serves, so a
  route renamed or deleted with the entry left behind is red rather than an
  excuse nobody can check;
- every exempt route must carry **neither** currency, so an exemption that has
  become unnecessary is red and **the ledger shrinks**. This is the direction
  that decays quietly: an entry left beside a route that has since grown the
  check keeps that route outside the sweep permanently, and the day somebody
  removes the check again nothing goes red.

Four entries ship: `/lti/login` and `/lti/launch`, which are the two legs of a
handshake with no session to bind a token to and a deliberately cross-site POST
respectively, and `/dev/clock` and `/dev/clock/clear`, which are appended routes
with no dependency graph posted by a page holding no session. E3-07's own
`/dev/passback` is **not** on it: it carries currency 2, because a development
route is refused outside development by the environment guard, which is a
different control answering a different question (ADR 0141).

**Three limits are disclosed rather than closed**, written down the way the
denial-module sweep's were. A state-changing `GET` escapes the inventory, and
what closes that is that a `GET` which writes is a defect of its own. A mutating
endpoint inside a `Mount` escapes it, because a `Mount` carries no `methods`;
today this application mounts one thing, the SPA's static files, which serves
`GET`. A `WebSocketRoute` escapes it for the same reason, and there are none.

## Alternatives rejected

**A hand-maintained inventory of writing routes.** It is how a new route joins a
system with nothing swept over it, which is `docs/MISTAKES.md` entry 2. The
built application's own route table cannot be forgotten to update.

**One currency — the dependency alone.** It would report the three appended
`/dev` routes as unguarded and force all three onto the ledger, which turns the
ticket's own trigger into a line of prose excusing itself. It is also
`docs/MISTAKES.md` entry 35 in its plainest form: a guard that enumerates the
ways a privilege can be held misses the way the design actually uses.

**Currency 2 as `type(route).__name__ == "DevControlRoute"`**, which a rename
breaks silently, or as `isinstance(route, AnyMethodRoute)`, which reports the
unchecked clock pair as guarded and would have nothing to say the day a third
unchecked any-method route is appended.

**Reading the include-level dependency off `include_context`.** It would mean
accumulating private state down through nested includes to decide what each route
inherited — a closed-set guard defeated one level out, built on two private names
with no stability promise, and silently wrong on the FastAPI that renames them.
Refusing the attachment costs one legal way of writing a dependency and buys a
guard that cannot go blind.

**A `GET`-inclusive inventory.** It would demand a CSRF check of every page this
project serves and would be red against every correct application, so it would be
deleted rather than fixed.

## Consequences

**A new mutating route is red on the day it lands unless it carries the check or
is argued for.** The three states are exhaustive and "it is a development route"
is not one of them. That is the carried E2 entry closed: the fix for a red here
is usually one import.

**An `include_router(..., dependencies=[...])` anywhere in this tree is now a
build error in the sweep, with a message naming where to move it.** That is a
real constraint on how this application composes dependencies, chosen with the
alternative named above.

**The ledger is a surface a reviewer reads.** Four sentences arguing that four
writing routes have no CSRF check is the thing to check in any diff that touches
it, and the both-direction assertions are what make it cheaper to delete an entry
than to keep one.

**The disclosed limits are open until somebody widens the rule deliberately.**
A `WebSocketRoute` or a mutating endpoint behind a `Mount` is outside this sweep
the day it arrives, and neither goes red — the sweep says so in its own docstring
rather than leaving a reader to discover it.
