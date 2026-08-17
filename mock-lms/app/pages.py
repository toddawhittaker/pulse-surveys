"""The two HTML pages: the launch page, and the auto-posting authorization form.

Written as f-strings rather than through a template engine, because no template
engine is in this project's locked dependency closure and adding one for two
pages would be a second lockfile question (see
`docs/adr/0035-the-mock-platform-signs-with-standard-library-rsa.md` for the same
reasoning applied to the larger case). Two pages is the bound: a third would be
the moment to reconsider.

**Every interpolated value goes through `html.escape` with `quote=True`.** That
is not decoration. The `state` a tool sends is a value this platform hands back
inside an attribute, so a platform that did not escape it would reflect whatever
the caller wrote into the tool's own page — and a mock with a cross-site
scripting hole in the launch path is exactly the kind of shortcut E0-14's
security review says must not become a habit. `escape` is applied at every
interpolation site rather than to the values on the way in, so a value that
reaches a new page later cannot arrive already trusted.

**No accessibility work is claimed here.** E0-14's definition of done says
accessibility does not apply, because the mock is a test harness rather than a
product surface. The markup is plain and labelled because that costs nothing; it
has not been audited against WCAG 2.2 AA and this file does not pretend it has.
"""

from html import escape

from app.config import PlatformSettings
from app.seed import SeededPlatform

LAUNCH_PAGE_TITLE = "Mock LMS — LTI 1.3 launch"


def hidden(name: str, value: str) -> str:
    """One hidden form field, both halves escaped."""
    return f'<input type="hidden" name="{escape(name, quote=True)}" value="{escape(value, quote=True)}">'


def option(value: str, label: str) -> str:
    """One `<select>` option. The value is the wire value; the label is for a human."""
    return f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'


def launch_page(settings: PlatformSettings, platform: SeededPlatform) -> str:
    """The page a browser clicks through, and the page a test reads the form off.

    The form **is** the OIDC third-party-initiated login request: `iss`,
    `login_hint` and `target_link_uri` are what make it one, and `client_id` and
    `lti_deployment_id` are the optional two that let a tool resolve the
    registration without a lookup. It posts, because that is what a platform
    does; a `GET` would put the whole initiation request in a query string and
    still look like a working launch from a browser.

    The registration block sits **outside** the form on purpose. Anything inside
    it is a field that gets submitted, and a value that is documentation should
    not become a parameter because it was convenient to put it there.

    The user selector offers `launch_users()` rather than every seeded person,
    and E0-15 is what made the two differ: its roster holds students who take one
    section. The page's two selectors are chosen independently, so an option that
    is only a launch in some sections is an option that produces a `400` — which
    reads, from a browser, as a broken platform rather than as a dead choice.
    """
    users = "\n          ".join(
        option(user.user_id, user.label) for user in platform.launch_users()
    )
    placements = "\n          ".join(
        option(
            placement.resource_link_id,
            f"{placement.context.label} — {placement.title}",
        )
        for placement in platform.placements
    )
    registration = "\n      ".join(
        f"<dt>{escape(term)}</dt><dd><code>{escape(value)}</code></dd>"
        for term, value in registration_values(settings).items()
    )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{escape(LAUNCH_PAGE_TITLE)}</title>
  </head>
  <body>
    <h1>{escape(LAUNCH_PAGE_TITLE)}</h1>
    <p>
      A development-only LTI 1.3 platform. Pick a user and a placement, and this
      posts a third-party-initiated login request to the tool.
    </p>

    <form method="post" action="{escape(settings.tool_login_url, quote=True)}">
      {hidden("iss", settings.issuer)}
      {hidden("client_id", settings.client_id)}
      {hidden("lti_deployment_id", settings.deployment_id)}
      {hidden("target_link_uri", settings.tool_launch_url)}

      <p>
        <label for="login_hint">Launch as</label>
        <select id="login_hint" name="login_hint">
          {users}
        </select>
      </p>
      <p>
        <label for="lti_message_hint">Placement</label>
        <select id="lti_message_hint" name="lti_message_hint">
          {placements}
        </select>
      </p>
      <p><button type="submit">Launch</button></p>
    </form>

    <h2>Registration</h2>
    <p>
      Paste these into <code>lti_platform</code> and <code>lti_deployment</code>,
      or fetch the same values as JSON from
      <a href="/registration"><code>/registration</code></a>.
    </p>
    <dl>
      {registration}
    </dl>
  </body>
</html>
"""


def registration_values(settings: PlatformSettings) -> dict[str, str]:
    """The registration, keyed by the column each value goes in.

    Keyed by column name rather than by protocol term — `jwks_url`, not
    `jwks_uri` — because the audience is someone filling in `lti_platform` and
    `lti_deployment` from E0-08, and "one step" should mean the names match. The
    two endpoint URLs are the pair E0-08's own module docstring says arrive with
    the code that calls them; they are published here because a registration form
    will want them the moment E1 exists.

    One function, two audiences: this builds both the JSON at `/registration` and
    the block on the launch page, so a human and a script cannot be told
    different things. See
    `docs/adr/0036-the-mock-platform-publishes-its-registration-as-a-document.md`.
    """
    return {
        "issuer": settings.issuer,
        "client_id": settings.client_id,
        "deployment_id": settings.deployment_id,
        "jwks_url": settings.jwks_url,
        "authorization_endpoint": settings.authorization_url,
        "openid_configuration": settings.discovery_url,
    }


def authorization_response_page(id_token: str, state: str, redirect_uri: str) -> str:
    """The `form_post` response: the launch, on its way to the tool.

    This is what the LTI 1.3 security framework specifies — a self-submitting
    form rather than a redirect — and it is why the `id_token` never appears in a
    URL, a browser history or a proxy log.

    The `<noscript>` button is not politeness. Without it the page is a dead end
    for anything that does not run scripts, and "the launch silently stopped
    here" is a bad half-hour for whoever meets it first.
    """
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Signing you in…</title>
  </head>
  <body onload="document.forms[0].submit()">
    <form method="post" action="{escape(redirect_uri, quote=True)}">
      {hidden("id_token", id_token)}
      {hidden("state", state)}
      <noscript><button type="submit">Continue to the tool</button></noscript>
    </form>
  </body>
</html>
"""
