"""The `/dev` console, built with a roster behind it, and the page reader its suites use.

**Why this file exists, and it is `docs/MISTAKES.md` entry 13.** Four modules
already build the same thing by hand — `tests/integration/test_dev_console.py`,
`test_the_dev_console_sets_and_clears_the_clock.py`,
`test_the_dev_console_names_nobody.py` and, in a variant of its own,
`test_web_login_door.py`. Each one starts the mock identity provider, points the
tool's five `oidc_*` settings at that provider's own discovery document, and
mounts it under the issuer's host so that `GET /dev`'s server-side roster fetch
resolves in process. The clock module's docstring says in as many words that "if
a third console suite arrives, that is the moment the builder moves into
`tests/fixtures/`"; the third and fourth arrived and the builder did not move.
E3-07 needs a fifth, so the shared home is written here and the fifth caller uses
it. **The four existing copies are not migrated in this ticket** — that is a
mechanical change to four green modules and it belongs with somebody who can run
them — so this file is the home, not yet the only copy.

The fixtures are named `dev_console_provider` and `dev_console_tool` rather than
`provider` and `dev_console`, deliberately: three of those four modules define
module-level fixtures under the shorter names, and a plugin fixture that shares a
name with them would be shadowed in some modules and not others, which is a
worse state than two copies.

**What a caller gets.** `dev_console_tool()` is a `TestClient` on
`app.main.create_app()`, its lifespan entered, its `app.state.http` routed at the
in-process provider, and its environment `tool_doors`' — `configured_env`'s
documented values over the container's database coordinates
(`docs/MISTAKES.md` entry 40). `ENVIRONMENT` defaults to `development` and any
keyword is one more environment variable, so a caller states what it runs under.

**`ConsolePage` is a parser, not a pattern.** The properties its callers assert
are about which attribute sits on which element and which form encloses which
button, and a regular expression over markup answers a question that only looks
the same (`docs/MISTAKES.md` entry 3). It ships with a control test at the top of
`tests/integration/test_the_dev_trigger_runs_a_passback.py`, which is the module
that reads a console page with it; a red there means the reader is broken rather
than the console.
"""

import importlib
from collections.abc import Callable
from html.parser import HTMLParser
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import pytest

from fixtures.line_item_creation import named_in

ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEVELOPMENT = "development"

DEV_CONSOLE_PATH = "/dev"

# The mock provider's redirect-URI setting, spelled as every console module
# spells it: it is compared exactly on the way in and again at the token
# endpoint, so this and the tool's callback have to be one address.
MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE = "MOCK_IDP_TOOL_REDIRECT_URI"

# A browser-facing OIDC authorization endpoint no implementation could reach by
# accident, so a tool that renders it has to have read it from configuration.
# Only used to fill the setting; the console sends no browser here. `.invalid` is
# RFC 2606.
CONFIGURED_AUTHORIZATION_ENDPOINT = "http://identity-provider.invalid/dev-console-authorize"

# ---------------------------------------------------------------------------
# The names E3-07's work order settles (D2 and D4), spelled once for the three
# modules that read them: the CSRF sweep, the trigger's exposure tests and the
# integration module that drives it. Three transcriptions of one settled path is
# `docs/MISTAKES.md` entry 13, and the guards below are functions rather than
# fixtures so that a tree where the trigger is unbuilt produces a FAILED naming
# the deliverable rather than an ERROR in somebody's setup (entry 44).
# ---------------------------------------------------------------------------

DEV_MODULE = "app.api.dev"

# D2: the trigger's path, its constant's name in that module, and the
# `data-testid` the console's button carries.
DEV_PASSBACK_PATH = "/dev/passback"
PASSBACK_PATH_NAME = "DEV_PASSBACK_PATH"
PASSBACK_RUN_TESTID = "passback-run"

# E3-08's roster-sync trigger: the second `DevControlRoute`, on the same footing.
# SPEC §7.3 pulls a roster on the hour and on a staff launch debounced by five
# *real* minutes, so a developer standing the clock in October cannot make the tool
# re-read a roster inside an afternoon; this control runs the walk now.
#
# Named here for the same reason the passback path is — one value addressed by the
# console's own form, the CSRF sweep and the exposure suite — and pinned by
# `declared_roster_sync_path` below, so a rename is a named failure rather than a
# suite quietly probing a path nobody registered. The testid is the one
# `tests/e2e/exit-grade-passback.spec.ts` already drives.
DEV_ROSTER_SYNC_PATH = "/dev/roster-sync"
ROSTER_SYNC_PATH_NAME = "DEV_ROSTER_SYNC_PATH"
ROSTER_SYNC_RUN_TESTID = "roster-sync-run"

# D2 again: what a cross-site `Origin` is answered with, inside development and
# after the environment gate has let the request through.
CROSS_SITE_REFUSED = 403

# What a `/dev` control answers when it did run: a See Other back to the console,
# E2-04's shape, which D3 reuses so a browser reload cannot re-run a passback.
SEE_OTHER = 303

# The header a browser sends with a form post, and the two values that are not
# this application's own origin. `.invalid` is RFC 2606, so the first can never
# be an address anything resolves; the second is the literal string a browser
# sends from a sandboxed iframe or an opaque origin, and it is a mismatch rather
# than an absence — which is the distinction D4 draws, and the one a check
# written as "if origin and origin != ours" gets wrong in the safe direction and
# a check written as `origin in (None, "null")` gets wrong in the other.
ORIGIN_HEADER = "Origin"
CROSS_SITE_ORIGIN = "http://cross-site.invalid"
OPAQUE_ORIGIN = "null"

# D4: the route class that carries the origin check, and the class it extends —
# named separately because telling the two apart is a property the CSRF sweep
# asserts.
DEV_CONTROL_ROUTE = "DevControlRoute"
ANY_METHOD_ROUTE = "AnyMethodRoute"

DEV_CONTROL_ROUTE_IS_OWED = (
    f"E3-07's work order (D4) adds `{DEV_CONTROL_ROUTE}({ANY_METHOD_ROUTE})` to `{DEV_MODULE}`: a "
    "route class whose constructor wraps the endpoint and refuses, in this order, anything that "
    "is not a POST in development (a bare 404, indistinguishable from an unregistered path) and "
    "then any request carrying an `Origin` header that is not this application's own origin (403). "
    "It is the CSRF sweep's second currency, because a route appended to `router.routes` — which "
    "is what the two clock controls are — carries no dependency graph for the first currency to be "
    "found in."
)

PASSBACK_PATH_IS_OWED = (
    f"E3-07's work order (D2) puts `{PASSBACK_PATH_NAME} = {DEV_PASSBACK_PATH!r}` in `{DEV_MODULE}` "
    "beside `DEV_CONSOLE_PATH`, and registers the trigger there. The constant is named rather than "
    "the string being written into the route, so the console's own form and every test that drives "
    "it address one value."
)


def dev_api_module() -> ModuleType:
    """`app.api.dev`, imported where a test can fail on it rather than error.

    An `ImportError` from *inside* a module that exists is re-raised untouched: a
    module that was never written and one that imports something absent are
    different failures with different fixes.
    """
    try:
        return importlib.import_module(DEV_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        absent = missing.name
        if absent is not None and not (absent == DEV_MODULE or DEV_MODULE.startswith(f"{absent}.")):
            raise
        pytest.fail(
            f"`{DEV_MODULE}` does not exist. E0-18 ships the development console there and E2-04 "
            f"the clock controls beside it. {DEV_CONTROL_ROUTE_IS_OWED}"
        )


def dev_control_route_class() -> Any:
    """`app.api.dev.DevControlRoute`, or a failure naming the deliverable that owes it."""
    return named_in(dev_api_module(), DEV_CONTROL_ROUTE, DEV_CONTROL_ROUTE_IS_OWED)


def any_method_route_class() -> Any:
    """`app.api.dev.AnyMethodRoute` — `DevControlRoute`'s parent, and its near miss."""
    return named_in(
        dev_api_module(),
        ANY_METHOD_ROUTE,
        "E2-04 ships it: the route registration that matches every method so the handler's "
        "environment check is what refuses, rather than the router's method matcher "
        "(`tests/unit/test_dev_clock_control_exposure.py` is where that is asserted). E3-07's "
        f"`{DEV_CONTROL_ROUTE}` extends it, so a sweep over route classes has to tell them apart.",
    )


def declared_passback_path() -> str:
    """`app.api.dev.DEV_PASSBACK_PATH`, required to be the value D2 settles."""
    declared = named_in(dev_api_module(), PASSBACK_PATH_NAME, PASSBACK_PATH_IS_OWED)
    assert declared == DEV_PASSBACK_PATH, (
        f"`{DEV_MODULE}.{PASSBACK_PATH_NAME}` is {declared!r} and E3-07's work order (D2) settles "
        f"{DEV_PASSBACK_PATH!r}. The console's form, the CSRF sweep and both trigger suites address "
        "that one value, and a rename is a deliberate change in all of them."
    )
    return str(declared)


ROSTER_SYNC_PATH_IS_OWED = (
    f"E3-08's work order puts `{ROSTER_SYNC_PATH_NAME} = {DEV_ROSTER_SYNC_PATH!r}` in "
    f"`{DEV_MODULE}` beside `{PASSBACK_PATH_NAME}`, and registers the roster-sync trigger there "
    "on the same `DevControlRoute` footing: development-only, POST-only, same-origin-checked, "
    "redirecting back to the console. The constant is named rather than the string being written "
    "into the route, so the console's own form and every test that drives it address one value."
)


def declared_roster_sync_path() -> str:
    """`app.api.dev.DEV_ROSTER_SYNC_PATH`, required to be the value E3-08 settles."""
    declared = named_in(dev_api_module(), ROSTER_SYNC_PATH_NAME, ROSTER_SYNC_PATH_IS_OWED)
    assert declared == DEV_ROSTER_SYNC_PATH, (
        f"`{DEV_MODULE}.{ROSTER_SYNC_PATH_NAME}` is {declared!r} and E3-08's work order settles "
        f"{DEV_ROSTER_SYNC_PATH!r}. The console's form and the exposure suite address that one "
        "value, and a rename is a deliberate change in both."
    )
    return str(declared)


# The two `DevControlRoute` paths, keyed by the id a parametrised test reports
# under. **Resolvers rather than strings**, so the lookup that can `pytest.fail` on
# an absent constant happens in the test body and a tree missing either control
# reds as a FAILED naming it rather than erroring at collection
# (`docs/MISTAKES.md` entry 44).
#
# It is a mapping rather than a list because the gate this pair guards is
# per-route: E3-07's own security round found a route subclass's gate discarded at
# dispatch (`docs/MISTAKES.md` entry 47), and a second control registered the same
# way inherits that hazard whole. A suite that walked only the first would go on
# saying the class is sound while the new door swung open.
DEV_CONTROL_PATHS: dict[str, Callable[[], str]] = {
    "passback": declared_passback_path,
    "roster-sync": declared_roster_sync_path,
}

# The router the `/dev` controls are appended to, by the name `app.api.dev` gives
# it. Needed because the reconciliation below cannot walk the *application*: on the
# pinned FastAPI `include_router` rebuilds a plain route from the endpoint and the
# methods, so the `DevControlRoute` instances survive only in the router's own list
# (`docs/MISTAKES.md` entry 47, which is the incident that established this).
DEV_ROUTER_NAME = "router"

DEV_ROUTER_IS_OWED = (
    f"`{DEV_MODULE}` defines no `{DEV_ROUTER_NAME}`. E0-18 ships the development console on an "
    "`APIRouter` there and every `/dev` control is appended to it; without the router there is "
    "nothing holding the route objects a `DevControlRoute` sweep reads."
)


def registered_dev_control_paths() -> set[str]:
    """The path of every `DevControlRoute` the dev router actually holds.

    **Walked on the router rather than on the application, and entry 47 is why.**
    `include_router` does not serve the route objects a router holds: for a plain
    route it rebuilds one from the endpoint, the methods, the name and
    `include_in_schema` alone. So a sweep over `application.routes` finds no
    subclass at all, and one that reported "no controls" would make the
    reconciliation below vacuous in the direction that matters.

    **`isinstance` against `DevControlRoute` and not its parent.** `AnyMethodRoute`
    is what the two clock controls are; `DevControlRoute` extends it and adds the
    origin check. Matching the parent would drag the clock controls into an
    inventory they are not part of, and telling the two apart is a property the
    CSRF sweep already asserts in its own module.
    """
    router = named_in(dev_api_module(), DEV_ROUTER_NAME, DEV_ROUTER_IS_OWED)
    control = dev_control_route_class()
    found: set[str] = set()
    for route in getattr(router, "routes", ()) or ():
        path = getattr(route, "path", None)
        if isinstance(route, control) and isinstance(path, str):
            found.add(path)
    return found


# ---------------------------------------------------------------------------
# Probing a route with every method, standard or not. Moved here by E3-07 from
# `tests/unit/test_dev_clock_control_exposure.py`, which discovered the split and
# whose docstring carries the incident; the trigger's own exposure suite asks the
# identical question of a route registered the identical way, and two inventories
# of "every method" is `docs/MISTAKES.md` entry 13 — a widening applied to one
# and not the other, on a guard whose whole point is that enumerating is what
# fails. Both callers today are `/dev`-surface exposure suites; a third from
# outside that surface is the moment this moves again.
# ---------------------------------------------------------------------------

# **The standard seven are what a closed enumeration can hold.** They are what a
# method-listing route registration names, and a sweep over them alone reports a
# clean surface while the gap stands open one token out.
STANDARD_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")

# **These two are outside every enumeration, and that is their whole job.**
# `TRACE` is a real method defined by RFC 9110 that nothing in this tree
# registers; `FOO` is an arbitrary token, syntactically a valid method and
# certain never to appear in anybody's list. A route set that answers the seven
# above by naming them answers these with the router's own `405`, naming the one
# method it does register. Both are sent because they fail for the same reason
# and a reader should not have to take the general case on the strength of the
# specific one: `TRACE` shows the gap is reachable with a *standardised* verb,
# and `FOO` shows no amount of widening the list closes it.
NON_STANDARD_METHODS = ("TRACE", "FOO")

# The whole walk. `httpx` — which `starlette.testclient.TestClient` is built on —
# puts the method token on the wire verbatim and validates it against no list, so
# every one of these is sent by the ordinary client and no ASGI-level driving is
# needed. If a later pin changes that, the fallback is to call the ASGI
# application directly with a scope carrying the token, and the reason to do so
# belongs in a comment rather than in a skip.
PROBED_METHODS = STANDARD_METHODS + NON_STANDARD_METHODS


class ConsolePage(HTMLParser):
    """Every `data-testid` on a page, every `<form>`, and which form each testid sits in.

    Three readings, because the console's controls are asserted as controls: a
    button exists, the form around it posts to the route the button is for, and
    the two are the same control rather than two unrelated pieces of markup that
    happen to be on one page.

      - `testids` maps a `data-testid` to the attributes of the element carrying
        it;
      - `forms` is every `<form>`'s attributes, in document order;
      - `form_of(testid)` is the attributes of the innermost `<form>` open when
        that element started, or `None` for an element outside every form.

    Text is deliberately not collected. No caller asserts what a control *says* —
    the wording is the implementer's — and a reading nothing uses is a reading
    nobody would notice going wrong.

    **Only `<form>` is stacked, which is what keeps the void-element defect out of
    this reader.** `<input>`, `<img>` and the rest carry no end tag, so a reader
    that pushed every tag would never pop them and would go on attributing the
    document to whatever was open — the defect
    `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`'s own
    reader was written around. A `<form>` is not a void element and cannot be one,
    so the stack here is safe by construction rather than by an exclusion list;
    the control test asserts it against an `<input>` all the same.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.testids: dict[str, dict[str, str]] = {}
        self.forms: list[dict[str, str]] = []
        self._open_forms: list[dict[str, str]] = []
        self._enclosing: dict[str, dict[str, str] | None] = {}

    def _record(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): (value or "") for name, value in attrs}
        if tag == "form":
            self.forms.append(values)
            self._open_forms.append(values)
        testid = values.get("data-testid")
        if testid is not None:
            self.testids[testid] = values
            self._enclosing[testid] = self._open_forms[-1] if self._open_forms else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(tag.lower(), attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # A self-closing tag opens nothing, so a `<form ... />` written that way
        # must not stay on the stack. Recorded first, then closed.
        self._record(tag.lower(), attrs)
        if tag.lower() == "form" and self._open_forms:
            self._open_forms.pop()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._open_forms:
            self._open_forms.pop()

    def form_of(self, testid: str) -> dict[str, str] | None:
        """The attributes of the form enclosing one testid, or `None` if it is in no form."""
        return self._enclosing.get(testid)


def read_console(markup: str) -> ConsolePage:
    """Parse `markup` and hand back the reader holding what it found.

    Named `read_console` and not `console_in`, for the reason the clock suite's
    own reader gives: pytest collects a bare `test` prefix, and a helper called
    `testids_in(markup)` is collected as a test that errors with "fixture
    'markup' not found" before any real assertion runs.
    """
    reader = ConsolePage()
    reader.feed(markup)
    reader.close()
    return reader


def redirected_to_the_console(response: Any, what: str) -> None:
    """One `/dev` control answered `303` and sent the browser back to the console.

    E2-04 settles the answer shape for a control on this page and E3-07's work
    order (D3) reuses it by name: a 303 back to `/dev`, which is what stops a
    browser reload from re-posting the form. Held here rather than in a test
    module because two suites now assert it of two controls;
    `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py` keeps a
    copy of its own, which this file's docstring explains.
    """
    assert response.status_code == SEE_OTHER, (
        f"{what} answered {response.status_code}. A `/dev` control answers {SEE_OTHER} back to the "
        "console, which is what stops a browser reload from running it a second time. Body begins "
        f"{response.text[:300]!r}."
    )
    location = response.headers.get("location") or ""
    assert location.rstrip("/").endswith(DEV_CONSOLE_PATH), (
        f"{what} redirected to {location!r}, which does not lead back to {DEV_CONSOLE_PATH}. The "
        "control is a section of the console and a developer who used it is looking at the console "
        "again afterwards."
    )


def same_origin_of(client: Any) -> str:
    """The `scheme://host` a request from `client` arrives carrying.

    What a browser puts in `Origin` for a same-site form post, and what a
    same-origin check on the server compares against
    `f"{request.url.scheme}://{request.url.netloc}"`. Derived from the client
    rather than written out as `http://testserver`, so a suite that moves its
    base URL does not silently start asserting a cross-site refusal against a
    header it believes is same-origin.
    """
    parts = urlsplit(str(client.base_url))
    return f"{parts.scheme}://{parts.netloc}"


@pytest.fixture
def dev_console_provider(mock_idps: Any, door_contract: Any) -> Any:
    """The mock identity provider, registered to return to this tool's own callback."""
    return mock_idps(
        {
            MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.oidc_callback}"
            )
        }
    )


@pytest.fixture
def dev_console_tool(
    tool_doors: Any,
    door_contract: Any,
    dev_console_provider: Any,
    committed_clock_overrides: Any,
) -> Callable[..., Any]:
    """Build the tool with the provider mounted, so `GET /dev` renders a real roster.

    The OIDC endpoints come out of the provider's own discovery document, the way
    a client learns them, and the provider is mounted under the host those
    endpoints name — so a console fetching its roster from the configured
    provider reaches the in-process mock, and one fetching from anywhere else
    fails loudly rather than being quietly served.

    **No platform is registered here**, and no clock is set. Which registrations
    exist and where the clock stands are what the calling suites are about, so
    both belong to the tests rather than to the fixture they share
    (`docs/MISTAKES.md` entry 30).

    **`committed_clock_overrides` is depended on rather than used**, for the
    teardown order `tests/integration/test_the_dev_console_sets_and_clears_the
    _clock.py` depends on it for: fixtures are finalised in reverse of setup, so
    naming it here makes its `DELETE FROM clock_override` run *after* this tool's
    connections are closed. A row that outlives its test moves the clock for
    every test that follows it on the same worker.
    """
    document = dev_console_provider.discovery()
    registration = dev_console_provider.registration()
    names = door_contract.settings

    def endpoint(member: str) -> str:
        value = document.get(member)
        assert isinstance(value, str) and value, (
            f"The provider's discovery document advertises no `{member}` (it carries "
            f"{sorted(document)}), so the tool cannot be configured to reach it."
        )
        return value

    def build(*, environment: str = DEVELOPMENT, **overrides: str) -> Any:
        values = {
            names["public_base_url"]: door_contract.public_base_url,
            names["oidc_issuer"]: endpoint("issuer"),
            names["oidc_authorization_endpoint"]: CONFIGURED_AUTHORIZATION_ENDPOINT,
            names["oidc_token_endpoint"]: endpoint("token_endpoint"),
            names["oidc_jwks_url"]: endpoint("jwks_uri"),
            names["oidc_client_id"]: registration["client_id"],
            ENVIRONMENT_VARIABLE: environment,
        }
        values.update(overrides)
        host = urlsplit(endpoint("issuer")).hostname
        return tool_doors(values, {host: dev_console_provider})

    return build
