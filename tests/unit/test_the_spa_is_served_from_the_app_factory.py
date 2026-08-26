"""The built SPA is served by the app factory, and its absence changes nothing — E1-04.

E1-04 acceptance criterion 1: "`docker compose up` serves the built SPA through
the `api` service exactly as §13 describes (static serve from the app factory),
and each of the five routes renders its empty landing." SPEC §13 puts it in the
one-line comment beside the module: `main.py` is "FastAPI app factory, router
mount, SPA static serve".

This module asserts the seam rather than the stack. What a browser sees is
`tests/e2e/landing-views.spec.ts`, which needs a real build and a running Compose
stack; what is asserted here is the property that spec cannot isolate — that the
factory mounts a built directory at `/app`, that a path under `/app` matching no
file answers `index.html` so the client router can route it, and that with no
build present the application boots and the API is untouched.

**The two halves are a pair on purpose.** "The SPA is served" and "the app works
without one" are the two sides of one line, and only one of them is a criterion.
The second is what makes the whole test suite runnable on a checkout that has
never run `npm run build`, and it is also the honest statement of what the
tolerance costs: with no dist, `/app` is a 404 rather than an error at startup.
A mount that raised on a missing directory would fail every test in this
repository, and one that silently served nothing anywhere would pass half of them.

**The environment variable is settled by the ticket's contract, not chosen here.**
`FRONTEND_DIST` names the built directory and defaults to the repository's
`frontend/dist`. The absent case is posed by pointing that variable at a directory
that does not exist rather than by relying on `frontend/dist` being unbuilt: a
developer who has run the build once would otherwise turn the 404 half of this
module green-for-the-wrong-reason on their machine and red on nobody's
(`docs/MISTAKES.md` entry 3).

**The `index.html` and the asset carry markers.** Serving *some* HTML at `/app/`
is not the criterion; serving the built entry point is. A marker string proves it
was that file, and the asset case is what tells a real static mount apart from a
catch-all that answers `index.html` to everything under `/app` — which would pass
every fallback assertion here and ship a page whose scripts all return HTML.

The harness is `tests/unit/test_healthz.py`'s: `create_app()` through Starlette's
`TestClient`, with `configured_env` laying down the documented configuration. No
database is involved, which is why this sits in `tests/unit/` beside the other
modules that drive the factory in process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# The ticket's settled contract: where the built SPA is found, and where it is
# served. Named here in one place, so a deliberate rename is two lines.
FRONTEND_DIST_VARIABLE = "FRONTEND_DIST"
MOUNT = "/app"

# The five routes SPEC §14.3's E1 exit needs a person to land on, spelled as the
# ticket spells them. The client router owns them; the server's only job is to
# hand `index.html` to each so the router can run.
ROLE_ROUTES = (
    f"{MOUNT}/student",
    f"{MOUNT}/instructor",
    f"{MOUNT}/leadership",
    f"{MOUNT}/care",
    f"{MOUNT}/admin",
)

# A path under the mount that names no route and no file. The rule is about paths
# that match no file, so this must be answered the same way a role route is —
# what the client router then renders is the client router's business.
UNROUTED_PATH = f"{MOUNT}/not-a-route-at-all"

# Markers no implementation would produce by accident. The first proves the HTML
# that came back is the built entry document rather than a server-rendered page or
# an error body; the second proves an asset request reached the asset.
INDEX_MARKER = "pulse-spa-index-4f2a91"
ASSET_MARKER = "pulse-asset-1b7e44"

INDEX_HTML = (
    "<!doctype html>\n"
    '<html lang="en">\n'
    f"  <head><title>{INDEX_MARKER}</title></head>\n"
    '  <body>\n    <div id="root"></div>\n'
    '    <script type="module" src="/app/assets/entry.js"></script>\n'
    "  </body>\n"
    "</html>\n"
)

ASSET_PATH = "assets/entry.js"
ASSET_BODY = f'export const marker = "{ASSET_MARKER}";\n'

HEALTHZ_PATH = "/healthz"


def built_dist(root: Path) -> Path:
    """A directory shaped like a Vite build output, with an entry document and one asset."""
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / ASSET_PATH).write_text(ASSET_BODY, encoding="utf-8")
    return dist


def client_over(dist: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A `TestClient` on an application built with `FRONTEND_DIST` pointed at `dist`.

    The variable is set before anything is imported and the factory is called
    after, and the client is used inside a `with` block by the caller so the
    lifespan runs — the same shape `tests/unit/test_healthz.py` uses, for the same
    reason: this is the callable `uvicorn app.main:create_app --factory` resolves.

    **The ordering matters and is one of the two ways this could be a broken test
    rather than a red one.** If the mount is decided at import time rather than
    inside the factory, the first case to run fixes it for the whole module and the
    two dist-absent tests would fail for a reason that is nothing to do with what
    they assert. Setting the variable first makes the first import right; if the
    later cases still disagree, the mount is being decided at import and `create_app()`
    is not the seam SPEC §13 describes — which is a finding rather than a repair
    to make here.
    """
    monkeypatch.setenv(FRONTEND_DIST_VARIABLE, str(dist))

    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


def test_the_mount_root_serves_the_built_entry_document(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 1, at its simplest: a built SPA is reachable at `/app/`.

    The application is the only thing serving the built application — SPEC §13
    gives the factory the static serve, so there is no separate web server in the
    Compose stack to fall back on. If this is a 404 the five landing views are
    unreachable however well they are built, and E1's exit ("a student, an
    instructor and a Dean each land on the right (empty) view") cannot be
    demonstrated.

    The marker is what makes this an assertion about the *built* document rather
    than about some HTML: E0-18's server-rendered landing pages are still in this
    application and also answer 200 with HTML.

    **The mutation this kills:** mount nothing, or mount the dist somewhere other
    than `/app`. **The near miss that must stay green:** any static-file
    implementation at all — Starlette's `StaticFiles`, a `FileResponse` route, a
    router mounted by the factory — since this reads what came back.
    """
    with client_over(built_dist(tmp_path), monkeypatch) as client:
        response = client.get(f"{MOUNT}/")

    assert response.status_code == 200, (
        f"`GET {MOUNT}/` answered {response.status_code} with a built SPA in place at the "
        f"directory `{FRONTEND_DIST_VARIABLE}` names.\n"
        f"  body: {response.text[:300]!r}\n"
        "\n"
        "SPEC §13 gives `backend/app/main.py` the SPA static serve, and nothing else in the "
        "Compose stack serves the built application."
    )
    assert INDEX_MARKER in response.text, (
        f"`GET {MOUNT}/` answered 200 with something that is not the built entry document.\n"
        f"  body: {response.text[:300]!r}\n"
        "\n"
        "The marker is in the `index.html` this test wrote into the dist directory. HTML that "
        "does not carry it came from somewhere else — E0-18's server-rendered landings answer 200 "
        "with HTML too, and so does an error page."
    )


def test_a_path_under_the_mount_that_matches_no_file_answers_the_entry_document(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The client-routing rule: every route under `/app` is served by `index.html`.

    A single-page application's routes exist in the browser. `/app/student` is not
    a file in the build output, so a plain static mount answers 404 and the five
    landing views are reachable only by navigating from `/app/` — which is not how
    a person arrives, and not how the doors will hand over once E1-08/E1-09 land
    the redirects.

    The five role routes are asserted together with a path that names no route at
    all, because the rule is about paths matching no *file* rather than about a
    list of five: a mount that special-cased the five would be a second copy of
    the route table, in the server, drifting from the router the moment E2 adds a
    route.

    **The mutation this kills:** `StaticFiles` with no fallback, which answers
    `index.html` at `/app/` and 404 at `/app/student` — the shape this arrives in,
    because it is what the obvious one-line mount does. **The near miss that must
    stay green:** any spelling of the fallback, and any status the client router
    later chooses to render for an unknown route, since that is decided in the
    browser and not here.
    """
    with client_over(built_dist(tmp_path), monkeypatch) as client:
        answers = {path: client.get(path) for path in (*ROLE_ROUTES, UNROUTED_PATH)}

    wrong = {
        path: response
        for path, response in answers.items()
        if response.status_code != 200 or INDEX_MARKER not in response.text
    }

    assert not wrong, "\n".join(
        [
            "These paths under the mount did not answer the built entry document:",
            *(
                f"  {path} -> {response.status_code} {response.text[:120]!r}"
                for path, response in sorted(wrong.items())
            ),
            "",
            "A single-page application routes in the browser: none of these is a file in the "
            "build output, and every one of them has to be answered with `index.html` so the "
            "client router can read the path and render the view. E1-04's contract with "
            "E1-08/E1-09/E1-13 is that the backend decides the landing role and redirects to one "
            "of these paths, and the frontend renders whatever route it is handed.",
            "",
            "The unrouted path is in this list on purpose. The rule is 'a GET under the mount "
            "matching no file answers index.html', not 'these five paths are special' — a server "
            "that knows the five is a second copy of the route table that E2 will silently "
            "outgrow.",
        ]
    )


def test_a_built_asset_is_served_as_itself(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other side of the fallback, and the case that makes it mean something.

    A mount that answered `index.html` to everything under `/app` passes every
    assertion in the test above and ships an application whose scripts and
    stylesheets all return HTML — a blank page in the browser and a console full
    of syntax errors, with the server reporting 200 throughout.

    So the fallback has to be a fallback: a request that *does* match a file gets
    that file, byte for byte.

    **The mutation this kills:** answer `index.html` unconditionally under the
    mount. **The near miss that must stay green:** whatever the implementation
    does about caching headers, ETags or content types, none of which this reads.
    """
    with client_over(built_dist(tmp_path), monkeypatch) as client:
        response = client.get(f"{MOUNT}/{ASSET_PATH}")

    assert response.status_code == 200, (
        f"`GET {MOUNT}/{ASSET_PATH}` answered {response.status_code}, and that file is in the "
        "build output this test laid down."
    )
    assert response.text == ASSET_BODY, (
        f"`GET {MOUNT}/{ASSET_PATH}` did not answer the file itself.\n"
        f"  expected: {ASSET_BODY!r}\n"
        f"  answered: {response.text[:300]!r}\n"
        "\n"
        "If this is the entry document, the mount answers `index.html` to everything under "
        f"`{MOUNT}` — which passes the client-routing test above completely and serves a page "
        "whose every script returns HTML."
    )


def test_with_no_build_present_the_application_boots_and_the_mount_is_a_404(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other side of the line: no dist, no mount, and no startup failure.

    Most of this repository's tests, `make migrate`, `make seed` and every backend
    developer's checkout run against a tree that has never produced a build —
    `frontend/dist` is gitignored and is written by `npm run build`. A factory that
    raised on a missing directory would take all of that down; one that mounted
    something anyway would serve a 200 over an empty tree, which is the shape ADR
    0083 rejected for the bundle-budget gate in the sentence "a gate turned on and
    made meaningless".

    So the tolerance is stated as behaviour and pinned in both directions: the
    application builds, and `/app` answers 404 rather than a blank 200.

    **The mutation this kills:** mount the directory unconditionally, which raises
    at startup — or answer 200 with an empty body, which reads as a working
    application serving a blank page. **The near miss that must stay green:** any
    404 body or handler, since what is asserted is the status.
    """
    absent = tmp_path / "never-built" / "dist"
    assert not absent.exists(), "The absent-dist case was posed with a directory that exists."

    with client_over(absent, monkeypatch) as client:
        answers = {path: client.get(path) for path in (f"{MOUNT}/", *ROLE_ROUTES)}

    served = {
        path: response.status_code
        for path, response in answers.items()
        if response.status_code != 404
    }

    assert not served, "\n".join(
        [
            "With no built SPA, these paths did not answer 404:",
            *(f"  {path} -> {status}" for path, status in sorted(served.items())),
            "",
            f"`{FRONTEND_DIST_VARIABLE}` pointed at a directory that does not exist, which is "
            "every checkout that has not run the production build — `frontend/dist` is "
            "gitignored. The application has to come up regardless, because the backend suite, "
            "the migrations and the seed all run on such a tree.",
            "",
            "A 200 here is the worse failure of the two: it says the application is serving a "
            "frontend when it is serving nothing.",
        ]
    )


def test_the_api_answers_the_same_with_a_build_and_without_one(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Mounting the SPA changes no API route, in either direction.

    The mount sits under one prefix and the API does not live there, but a mount
    at the wrong place — at `/`, or a catch-all registered before the routers —
    swallows everything, and the symptom is an application that serves a beautiful
    blank page and no API at all. `/healthz` is the cheapest witness this
    repository has: E0-01 built it and every gate in the Compose stack waits on it.

    Both directions are asserted in one test because the property is a comparison:
    the answer with a build present must be the answer without one.

    **The mutation this kills:** mount the static files at `/` instead of `/app`,
    or register the SPA fallback ahead of the API routers so that it answers
    first. **The near miss that must stay green:** anything at all happening under
    `/app`, which the tests above are about.
    """
    with client_over(built_dist(tmp_path), monkeypatch) as client:
        with_build = client.get(HEALTHZ_PATH)

    absent = tmp_path / "never-built" / "dist"
    with client_over(absent, monkeypatch) as client:
        without_build = client.get(HEALTHZ_PATH)

    assert with_build.status_code == 200 and without_build.status_code == 200, (
        f"`GET {HEALTHZ_PATH}` answered {with_build.status_code} with a build present and "
        f"{without_build.status_code} without one. E0-01's acceptance criterion 1 is that it "
        "answers 200 with a JSON body naming the environment, and `docker compose` waits on it "
        "for every service in the stack.\n"
        "\n"
        "A static mount that reaches the API's paths is the usual cause: mounted at `/` rather "
        "than under a prefix, or a fallback registered before the routers."
    )
    assert with_build.json() == without_build.json(), (
        "`/healthz` answers differently depending on whether a frontend build is present.\n"
        f"  with a build:    {with_build.json()}\n"
        f"  without a build: {without_build.json()}\n"
        "\n"
        "The SPA serve is a mount, not a feature the API reports on. If the health body is to "
        "carry the frontend's state that is a decision for the ticket that wants it — and it "
        "would have to be read against SPEC §4.1 and the `/healthz` disclosure question E1 "
        "carries."
    )
