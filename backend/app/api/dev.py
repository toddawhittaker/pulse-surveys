"""The developer test console: the development-only `GET /dev` page.

The console is a convenience for a developer, and nothing a deployment serves. It
lists the web-login people the mock identity provider knows and offers each as a
one-click "sign in as this person" link, plus one launcher link per registered
LTI platform, so both of SPEC §2's entry doors can be walked without typing URLs.

**The launcher links come from `lti_platform`** (E1-05). They used to come from
the origin of a process-wide setting, which rendered one link whatever the
database held — including when it held no registration at all, which sent a
developer to a port answering nothing. With nothing registered the page now says
so and how to fix it.

**It is a become-any-user surface, so it is gated exactly the way `/docs` is** —
served only when `ENVIRONMENT` is exactly `development` (ADR 0074), the same value
`app.main` keys the schema and its documentation on. Outside development the
handler answers `404`, indistinguishable from a route that was never registered:
a page enumerating every identity anyone can sign in as is the single worst thing
this feature could hand a production browser. The production refusal is asserted
without a network in `tests/unit/test_dev_console_exposure.py`; the
development-serves direction, with a real roster behind it, in
`tests/integration/test_dev_console.py`.

**A new module, and §13 does not name it** — its `api/` list is the screen
routers plus `deps.py`, and a developer test console is neither a screen nor LTI.
It is a thin router here, and the page it builds lives beside it: a handful of
f-strings, the way `mock-idp/app/pages.py` builds its three pages, because no
template engine is in this project's locked dependency closure.

**Every interpolated value goes through `html.escape` with `quote=True`.** The
subjects and labels come from the mock provider's roster, which is trusted, but
they are escaped anyway — a page that escapes only the values it distrusts is one
audit away from a hole. Nothing a caller or a roster supplies is ever written into
the `<style>` block, which carries no interpolation at all.
"""

from html import escape
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import LOGIN_PATH
from app.config import Settings, is_development
from app.db import get_session
from app.models.lti import LtiPlatform

router = APIRouter(tags=["dev"])

DEV_CONSOLE_PATH = "/dev"

# Where the console reads the roster from. The mock provider publishes its
# registration and its seed together (ADR 0058) under this path on the issuer's
# host, and the fetch goes through `app.state.http` — the one client every
# server-side call the tool makes already shares.
MOCK_REGISTRATION_PATH = "/mock/registration"

# How long the console waits for the roster. The page is a development
# convenience, so a slow mock should make it say so rather than hang.
ROSTER_TIMEOUT_SECONDS = 5.0

NOT_FOUND = 404

CONSOLE_TITLE = "Pulse Surveys — developer test console"

# Static CSS, no interpolation: this is code, never a value a caller or a roster
# supplied, so it does not go through `escape` and nothing from a request is ever
# written into it. A cool teal accent, distinct from the mock IdP's violet and the
# mock platform's slate, so the three test surfaces are never mistaken for one
# another, and from Pulse's own palette (`design/tokens.css` is deliberately not
# referenced — this is a developer scaffold, not a product screen).
STYLE = """
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      padding: 2.5rem 1rem;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: #f0faf9;
      color: #18181b;
    }
    .card {
      width: 100%;
      max-width: 640px;
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 8px 24px rgba(0, 0, 0, 0.06);
      padding: 2rem 2.25rem 2.25rem;
      height: fit-content;
    }
    h1 { font-size: 1.375rem; margin: 0 0 0.5rem; color: #0f766e; }
    h2 {
      font-size: 1rem;
      margin: 2rem 0 0.75rem;
      color: #0f766e;
      border-top: 1px solid #e5e7eb;
      padding-top: 1.25rem;
    }
    p { line-height: 1.5; color: #3f3f46; margin: 0.5rem 0 1rem; }
    .banner {
      display: flex;
      gap: 0.6rem;
      align-items: flex-start;
      background: #fff7ed;
      border: 1px solid #fdba74;
      color: #9a3412;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.875rem;
      line-height: 1.4;
      margin-bottom: 1.5rem;
    }
    .banner strong { font-weight: 600; }
    .note {
      background: #fef2f2;
      border: 1px solid #fca5a5;
      color: #991b1b;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.875rem;
      line-height: 1.4;
    }
    ul { list-style: none; margin: 0; padding: 0; }
    li { margin: 0.4rem 0; }
    a.action {
      display: inline-block;
      color: #0f766e;
      font-weight: 600;
      text-decoration: none;
      padding: 0.15rem 0;
    }
    a.action:hover { text-decoration: underline; }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.85em;
      background: rgba(0, 0, 0, 0.05);
      padding: 0.1em 0.35em;
      border-radius: 4px;
      color: #52525b;
    }
    @media (prefers-color-scheme: dark) {
      body { background: #0c1a19; color: #e4e4e7; }
      .card { background: #18181b; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4); }
      h1, h2 { color: #5eead4; }
      h2 { border-top-color: #3f3f46; }
      p { color: #a1a1aa; }
      a.action { color: #5eead4; }
      code { background: rgba(255, 255, 255, 0.08); color: #a1a1aa; }
      .banner { background: #451a03; border-color: #c2410c; color: #fed7aa; }
      .note { background: #450a0a; border-color: #b91c1c; color: #fecaca; }
    }
"""

# Static banner markup, no interpolation.
BANNER = """
    <div class="banner">
      <span>&#9888;&#65039;</span>
      <span>
        <strong>Development-only test console.</strong>
        It offers one-click sign-in as any web-login identity and a launch into the
        mock LMS. It is served only in development and never in a deployment.
      </span>
    </div>"""


def page(body: str) -> str:
    """The shell the console renders inside, so its markup has one shape."""
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{escape(CONSOLE_TITLE)}</title>
    <style>{STYLE}</style>
  </head>
  <body>
    <div class="card">
      {BANNER}
{body}
    </div>
  </body>
</html>
"""


def sign_in_link(subject: str, label: str) -> str:
    """A "sign in as this person" link to the web door, carrying `login_hint`.

    The subject rides as OIDC Core 1.0 §3.1.2.1's `login_hint`, which the tool
    forwards to the provider so its form pre-selects this person. `target="_blank"`
    so a click opens the flow in a new tab and the console stays put — a developer
    signs in, then comes back to pick the next identity.
    """
    href = f"{LOGIN_PATH}?{urlencode({'login_hint': subject})}"
    return (
        f'<li><a class="action" href="{escape(href, quote=True)}" target="_blank">'
        f"Sign in as {escape(label)}</a> "
        f"<code>{escape(subject)}</code></li>"
    )


def web_section(users: list[dict[str, Any]]) -> str:
    """The web-login roster, one sign-in link per person the provider publishes."""
    people = [user for user in users if user.get("web_login") and user.get("sub")]
    links = "\n          ".join(
        sign_in_link(str(user["sub"]), str(user.get("label") or user["sub"])) for user in people
    )
    return f"""    <h2>Web login</h2>
    <p>Sign in through the identity provider (SPEC §2) as any seeded person.</p>
    <ul>
          {links}
    </ul>"""


def unreachable_section() -> str:
    """What the web section becomes when the roster cannot be fetched."""
    return """    <h2>Web login</h2>
    <p class="note">
      The mock identity provider is unreachable, so the web-login roster could not
      be loaded. Bring it up and reload this page.
    </p>"""


def launcher_section(origins: list[str]) -> str:
    """One launcher link per registered platform origin, or an honest line saying none is.

    **The empty case is a case, not a blank space.** While the origin came from a
    process-wide setting there was always a link, including on a database that
    had never been seeded — which sent a developer to a port answering nothing
    and read as a broken stack. The console reads the registrations now, so the
    absence is visible, and the honest answer to it names what is missing and how
    to fix it.
    """
    if not origins:
        return """    <h2>LTI launch</h2>
    <p class="note">
      No LTI platform is registered, so there is nothing to launch from. Run
      <code>make seed</code> to register the mock LMS, then reload this page.
    </p>"""
    links = "\n          ".join(
        f'<li><a class="action" href="{escape(origin, quote=True)}" target="_blank">'
        f"Open the launcher at {escape(origin)}</a></li>"
        for origin in origins
    )
    return f"""    <h2>LTI launch</h2>
    <p>Launch as an instructor or a student from a registered platform (SPEC §2).</p>
    <ul>
          {links}
    </ul>"""


def roster_users(settings: Settings, http: httpx.Client) -> list[dict[str, Any]] | None:
    """The provider's published users, or `None` when the roster cannot be fetched.

    `None` is the console's fail-soft signal, not a raised error: a page that says
    "the mock is down" is better than one that answers `500` because a development
    dependency is not running. Every failure to obtain a well-formed list of user
    records collapses to it.
    """
    url = f"{settings.oidc_issuer.rstrip('/')}{MOCK_REGISTRATION_PATH}"
    try:
        answered = http.get(url, timeout=ROSTER_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        return None
    if answered.status_code != 200:
        return None
    try:
        document = answered.json()
    except ValueError:
        return None
    if not isinstance(document, dict):
        return None
    users = document.get("users")
    if not isinstance(users, list):
        return None
    return [user for user in users if isinstance(user, dict)]


def launcher_origins(session: Session) -> list[str]:
    """The distinct origins of every registered platform's authorization endpoint.

    The console links to the origin — `scheme://host[:port]`, path stripped — so
    a developer reaches the platform's launcher page rather than its
    authorization route itself.

    **Read from `lti_platform` and from nowhere else** (E1-05). This used to be
    the origin of one process-wide setting, which is one link whatever the
    database holds — the same address for every registration, and a link even
    when there is no registration at all. A registration with no authorization
    endpoint states none, so it offers no launcher; that is the same NULL the
    launch door refuses rather than defaults.

    Distinct, in the order the issuers sort, because two registrations of one
    platform — a pilot beside production, which is why `lti_platform` is unique
    on the pair — share one launcher page and two identical links would be a
    duplicate rather than a choice.
    """
    endpoints = session.execute(
        select(LtiPlatform.authorization_endpoint)
        .where(LtiPlatform.authorization_endpoint.is_not(None))
        .order_by(LtiPlatform.issuer)
    ).scalars()

    origins: list[str] = []
    for endpoint in endpoints:
        split = urlsplit(str(endpoint))
        origin = f"{split.scheme}://{split.netloc}"
        if origin not in origins:
            origins.append(origin)
    return origins


@router.get(DEV_CONSOLE_PATH, summary="Development-only test console for both entry doors")
def dev_console(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """Render the console, or `404` outside development.

    The gate is the whole safety of the feature (see the module docstring), and it
    is checked here so production is indistinguishable from a route that was never
    registered. Synchronous, and the one blocking thing it does — the roster fetch
    — runs in FastAPI's threadpool the way `app.api.auth.begin_web_login` does.

    **The session is taken before the gate rather than after**, because
    `Depends` resolves before the handler body runs either way. It costs a
    connection from the pool on a request a deployment answers `404` to, which is
    the same cost every other routed dependency has and is why the gate stays in
    the handler (ADR 0079) rather than moving anywhere clever.
    """
    settings: Settings = request.app.state.settings
    if not is_development(settings):
        raise HTTPException(status_code=NOT_FOUND)

    users = roster_users(settings, request.app.state.http)
    web = unreachable_section() if users is None else web_section(users)
    body = f"""    <h1>{escape(CONSOLE_TITLE)}</h1>
    <p>Walk either of Pulse's two entry doors (SPEC §2) without typing URLs.</p>
{web}
{launcher_section(launcher_origins(session))}"""
    return HTMLResponse(page(body))
