"""What a running application actually serves — one walk, for the two suites that ask.

**The library behaviour this exists to survive: `fastapi` 0.141.1's
`_IncludedRouter`.** On the pinned FastAPI, `app.include_router(...)` no longer
copies the router's routes onto the application. It appends a single
`fastapi.routing._IncludedRouter` — a `starlette.routing.BaseRoute` carrying
`handle`, `matches`, `effective_candidates` and `url_path_for`, and **no `path`
attribute at all**. So the obvious walk, `{route.path for route in
application.routes if hasattr(route, "path")}`, sees only what the factory
registered directly. Against `app.main.create_app()` that is four paths —
`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, `/redoc`, which FastAPI adds
itself — while `/healthz`, every `/lti/*` and `/auth/*` path and the whole `/dev`
console are invisible, because all of them arrive through `include_router`.

That is measured, not read: `docs/disputes/E2-04-01.md` carries the printed route
list from this branch, and the ruling of 2026-09-01 adopts the flattening below.
`_IncludedRouter` keeps the router it wrapped on `original_router`, so the
members it hides are one recursion away.

**Why the flattening does not lose the property the control needs.** The caller
this was written for asserts that an application *carries* a route, and its whole
value is that it fails on an application whose routers were never registered. It
still does. This walk adds nothing of its own: it reports the paths reachable
from `application.routes`, and a factory that skipped its `include_router` calls
appends no `_IncludedRouter` to recurse into, so the walk finds only FastAPI's
four documentation paths and every assertion about `/dev` or `/dev/clock` fails
exactly as before. Widening what can be *seen* is not widening what is *there* —
the near miss is an application missing its routers, and a missing router is
missing from this walk too.

**One walk and not two** (`docs/MISTAKES.md` entry 13). `tests/fixtures/
lti_platform.py`'s `declared_paths` asks the same question of the same kind of
object for the two mock services. It is unaffected today only because both mocks
register their routes with decorators on the application object rather than
through `include_router` — so it would go blind in precisely this way the day
either mock grows a router, and report an empty walk as a clean one. The E2-04-01
ruling requires the two to route through one helper in the same change rather
than leaving that as a warning, so `declared_paths` filters what `every_route`
below hands it.

No fixtures live here, so this module is not in `tests/conftest.py`'s
`pytest_plugins`: it is imported by name, the way `fixtures.lti_platform`'s
`origin_of` and `split_jws` are.
"""

from typing import Any

# The attribute `fastapi.routing._IncludedRouter` keeps the wrapped router on.
# Named rather than inlined because it is the whole of what makes the recursion
# possible, and because a FastAPI that renames it should fail at a constant a
# reader can find rather than inside a `getattr` default.
INCLUDED_ROUTER_ATTRIBUTE = "original_router"


def every_route(application: Any) -> list[Any]:
    """Every route object reachable from `application`, through included routers too.

    Breadth is not preserved and does not matter: both callers reduce the result
    to a set or a sorted set. What matters is that a route registered through
    `include_router` is in the list at all — see this module's docstring for the
    library behaviour that makes that a question.

    An object that is not an `_IncludedRouter` simply has no `original_router`
    and contributes only itself, so a plain `starlette.routing.Route`, a `Mount`
    and a `WebSocketRoute` all pass through unchanged.
    """
    found: list[Any] = []
    pending = list(application.routes)
    while pending:
        route = pending.pop()
        found.append(route)
        included = getattr(route, INCLUDED_ROUTER_ATTRIBUTE, None)
        if included is not None:
            pending.extend(included.routes)
    return found


def registered_paths(application: Any) -> set[str]:
    """Every path `application` has a route for, at any depth of inclusion.

    Verified against `app.main.create_app()` on this branch in
    `docs/disputes/E2-04-01.md`: it answers the thirteen paths the tool serves,
    `/dev`, `/dev/clock` and `/dev/clock/clear` among them.
    """
    return {
        path
        for path in (getattr(route, "path", None) for route in every_route(application))
        if isinstance(path, str)
    }
