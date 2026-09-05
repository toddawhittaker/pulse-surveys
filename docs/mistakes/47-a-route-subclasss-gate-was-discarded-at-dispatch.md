# 47. A route subclass's gate was discarded at dispatch while the class stayed visible

## What happened

E3-07 adds `POST /dev/passback`, a development control that runs SPEC §3.4's
participation sweep and posts real grades to a real LMS. Its work order settles a
route class, `DevControlRoute(AnyMethodRoute)`, whose wrapper refuses anything
that is not a `POST` in development with a bare `404` and then refuses any
`Origin` that is not this application's own with a `403`. The work order's own
words are "its constructor wraps the endpoint".

The first build wrapped something else. `starlette.routing.Route.__init__` turns
an endpoint into an ASGI application on `self.app`, and wrapping *that* looked
strictly better: it inherits Starlette's own handling of synchronous and
asynchronous endpoints for free, rather than reimplementing the branch.

```python
def __init__(self, path: str, endpoint: Callable[..., Any]) -> None:
    super().__init__(path, endpoint)
    self.app = refuse_unless_this_page_asked(self.app)   # inert
```

It ran clean through `ruff`, `mypy` and the whole unit suite, and every gate did
nothing. `POST /dev/passback` answered `303` on an application built with
`ENVIRONMENT=production`, and answered `303` to a cross-site `Origin` in
development. Eight of the ticket's tests were red on it.

## The root cause

`fastapi/routing.py::_IncludedRouter._build_effective_context`, on the pinned
`fastapi` 0.141.1. `include_router` does not serve the route objects a router
holds. For a plain `starlette.routing.Route` it builds a **fresh** `Route` out of
four values read off the original — `endpoint`, `list(methods or [])`, `name` and
`include_in_schema` — and serves that. Nothing else survives: not the subclass,
not any attribute a subclass set, and not `self.app`.

The original object stays in `router.routes` for anything that walks them, which
is the half that makes this dangerous rather than merely wrong. The CSRF sweep the
same ticket builds reads `isinstance(route, DevControlRoute)` off that walk. It
found the class, reported the route guarded, and was **green over a route whose
gate could not run**. Two independent readings of the same application disagreed:
the router said the check was there and the dispatcher had never heard of it.

The deeper cause is the assumption that a framework serves the object you handed
it. Everything about `router.routes` invites it — the list is public, the objects
are the ones appended, and the route class is exactly what a reader inspects to
answer "what does this route do".

## The consequence

Twenty minutes, because the tests existed first: the exposure suite drives every
method against a deployment build and the integration suite drives a cross-site
`Origin` against a real gradebook, and both fail loudly on an inert gate.

What it would have cost without them is the whole point of writing it down. The
shipped state would have been a development route that posts participation grades
to a live LMS, reachable unauthenticated from any page a developer's browser
happened to be showing and from any deployment that ran with the router included
— while the ticket's own security sweep, the route class's docstring and the ADR
beside it all said the check was in place. A guard that is present by inspection
and absent at runtime is worse than no guard, because it ends the review.

## The rule

**On this FastAPI, a route's behaviour must live in its endpoint. Anything a
route subclass puts anywhere else is discarded at dispatch.** `include_router`
rebuilds a plain `Route` from the endpoint, the methods, the name and
`include_in_schema`; a subclass survives only in `router.routes`, where
introspection reads it. So a route class is a marker a sweep can read and a place
to wrap an endpoint, and it is not a place to put an ASGI middleware, a matcher,
or state a handler is meant to see.

**And when a structural guard and a behavioural test can disagree about the same
route, write the behavioural one and believe it.** The sweep that reads the route
table is worth having — it is what forces the next mutating route onto a check —
but it answers "is the class there", never "does the gate run". Every gate this
project adds to a route needs at least one test that drives the built application
over HTTP and reads the status, in both directions; without it the structural
guard is a green that means nothing.
