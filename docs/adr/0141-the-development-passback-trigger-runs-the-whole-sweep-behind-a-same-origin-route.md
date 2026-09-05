# 0141 — The development passback trigger runs the whole sweep behind a same-origin route

## Context

SPEC §3.4 makes the participation passback fully automatic: recomputed and
re-posted when a value changes, ordinarily after each week closes, with no
instructor action and no override. E3-06 put that sweep on the weekly beat,
`crontab(day_of_week="mon", hour="2", minute="20")`, which fires on **real**
time.

The formula does not. Every week it counts, every enrollment it treats as live
and every term it holds inside its bound come off `app.services.clock`, which
[ADR 0109](0109-the-dev-clock-is-a-database-offset-not-a-freeze.md) makes an
offset a developer can move from the `/dev` console. So a developer who sets the
pretend now past a survey window's close sees nothing happen until Monday morning
comes round for real, and the epic's behaviour is not drivable in a browser at
all. E2-04 and E2-13 hit the same gap with survey windows and answered it the
same way, with a `/dev` control.

That control is a mutating route, and E3-07 also builds the sweep that requires
every mutating route to carry a CSRF check (ADR 0140). SPEC settles none of what
follows: §3.4 forbids a production-facing trigger and says nothing about a
development one.

## Decision

**`POST /dev/passback` runs the whole sweep and takes no arguments.** No section
parameter and no student parameter: it calls
`app.services.grading.post_scores_for_all_sections` over every eligible section,
which is the weekly beat's own behaviour.

**It is synchronous and in the request.** The handler opens a session, hands the
blocking work to the threadpool, and answers `303` back to the console — the
answer shape both clock controls give, so a browser reload cannot run a second
passback. **It does not commit.** The service commits after each section, because
a score sitting in somebody else's gradebook is not undone by this process dying
and the rows recording it have to be as durable as the thing they describe;
`app.jobs.tasks.post_participation_scores` is the other caller and makes the same
argument at length.

**It is registered as a new `DevControlRoute`, not as an exemption.** The class
extends `AnyMethodRoute` — the any-method registration that keeps the router's
`405` out of the answer table — and adds a same-origin check. Two gates, and
**their order is the security property**:

1. Not development, or not a `POST`: a bare `404`, indistinguishable from a path
   nobody registered.
2. An `Origin` header that is not `f"{request.url.scheme}://{request.url.netloc}"`:
   `403` with a constant sentence carrying nothing the caller sent. The literal
   `null` a browser sends from a sandboxed iframe or an opaque origin is a value
   that is not this application's own, so it is refused like any other mismatch.
   An **absent** `Origin` is allowed: every current browser sends the header on a
   cross-site POST, so a request arriving without one is a caller that cannot be
   made to send it on somebody else's behalf — `curl`, a script, a Makefile
   target.

The `404` gates come first so a cross-site probe outside development learns
nothing. A `403` there would tell an unauthenticated caller both that this build
ships a passback trigger and that its same-origin check is running. Hoisting the
origin check reads as tightening, since it refuses more requests sooner, and it
is a disclosure.

**The gates wrap the endpoint, and that is measured rather than stylistic.** The
first build wrapped the ASGI application `Route.__init__` builds, and every gate
was inert: `POST /dev/passback` answered `303` on a production build.
`fastapi/routing.py::_IncludedRouter._build_effective_context` on the pinned
0.141.1 does not serve the route objects a router holds — for a plain
`starlette.routing.Route` it builds a **fresh** `Route` from that route's
`endpoint`, `list(methods or [])`, `name` and `include_in_schema`, and serves
that. The subclass and anything it put on `self.app` are discarded at dispatch
while the original object stays in `router.routes` for anything that walks them,
which is why the CSRF sweep reported the route guarded over a gate that never
ran. The endpoint is the only part of a route that survives, so it is where
behaviour belongs.

**The two clock controls stay plain `AnyMethodRoute` and are the sweep's declared
exemption.** They are not retrofitted onto the new class.

## Alternatives rejected

**A per-section or per-student trigger.** It reads as more careful and is not:
it adds a query surface a caller can steer at a control that writes to somebody
else's gradebook, it makes the console carry a section picker nothing else on the
page needs, and the sweep is already per-section transactional, so a narrower run
protects nothing a whole one does not. What a developer is checking is the beat's
behaviour, and the beat takes no arguments.

**Enqueuing the work the way E3-05 enqueues line-item creation.** The browser's
answer would then say nothing about whether anything happened — the developer
reloads the gradebook and cannot tell a working trigger from a broken one — and
the scripted proof would depend on a worker being up. A sweep over a development
stack's handful of sections is a second's work in the request.

**Exempting `/dev/passback` in ADR 0140's ledger because it is a development
route.** This is the ticket's own named trap, and it is wrong for a plain reason:
the environment guard and the CSRF check answer different questions. A
developer's browser, on a page some other site served, can be made to POST to a
development stack that is running, and this route posts real participation grades
to a real LMS. Writing the sweep and the route in one ticket is exactly the
circumstance in which the excuse would look reasonable.

**Putting the origin check in `backend/app/api/deps.py`.** That module is the home
of this project's routed dependencies and of the session chain; this check reads
no session, is attached to routes that have no dependency graph to hang a
`Depends` on, and belongs beside `AnyMethodRoute` in the module whose registration
shape it extends.

**Refusing a request with no `Origin` header.** The shape a reviewer asks for, and
it locks every non-browser caller out of the one control this ticket adds while
defending against nothing: a script cannot be tricked into posting on a
developer's behalf, which is the whole thing a same-origin check is for.

**Retrofitting the check onto `/dev/clock` and `/dev/clock/clear`.** It would be
a strict improvement to those two routes and it deletes the ledger's only worked
example — the exemption whose sentence a reader can check against a route that
really is in that position, and the pair ADR 0140's both-direction assertions are
proven against. It is a change worth making in a ticket that is about those
routes, with the ledger's machinery re-proven on whatever is left.

**Any production-facing trigger.** SPEC §3.4 forbids it outright.

## Consequences

**The epic is drivable by hand.** Move the pretend now past a window's close,
click the button, open the mock's gradebook.

**Two known hazards become reachable by hand for the first time**, and the
console's own copy names them because the alternative is somebody debugging the
passback rather than the clock they moved. A clock rewound behind where a roster
sync has already reached can wedge that sync, and a passback run under a rewound
clock can be refused with `409` because the score it sends carries a timestamp
older than the one the platform holds (ADR 0138). Neither is E3-07's to fix; both
are carried entries with owners.

**`DevControlRoute` is the registration a future mutating `/dev` control uses**,
and a plain `AnyMethodRoute` in that position is red in ADR 0140's sweep on the
day it lands unless somebody argues for it in the ledger.

**The clock pair keeps its accepted residual risk**: a cross-site page can move a
developer's clock. It is named in the ledger's sentence rather than left
implicit, and it is now the one `/dev` control that writes without an origin
check.

**The trigger's answer table is stricter than the console's.** `GET /dev` answers
`405` outside development by measurement and accepted disclosure (ADR 0079, ADR
0087); this route answers `404` to every method in every environment but a
same-origin `POST` in development. A page is a thing to read and a control is a
thing to attack.
