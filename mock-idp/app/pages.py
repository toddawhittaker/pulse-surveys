"""The three HTML pages, and the JSON document that publishes what they show.

Written as f-strings rather than through a template engine, because no template
engine is in this project's locked dependency closure and adding one for three
pages would be a second lockfile question — the same reasoning
`docs/adr/0035-the-mock-platform-signs-with-standard-library-rsa.md` applies to
the larger case, and the same choice `mock-lms/app/pages.py` made for two pages.
Three is the bound: a fourth would be the moment to reconsider.

**Every interpolated value goes through `html.escape` with `quote=True`.** That
is not decoration. This service reflects values a caller supplied — a refusal
naming the `client_id` that failed, a `redirect_uri` that is not registered — so a
provider that did not escape them would reflect whatever the caller wrote into
its own page. A cross-site scripting hole in a login page is exactly the shortcut
E0-16's definition of done says must not become a habit. `escape` is applied at
every interpolation site rather than to the values on the way in, so a value that
reaches a new page later cannot arrive already trusted.

**The login form is built to be driven by a browser test without brittle
selectors**, which E0-16's scope asks for and E0-18 has to deliver against: one
labelled control, one submit button, and a `data-testid` on each, so
`get_by_label` and `get_by_test_id` both resolve. What it is *not* is a design
surface — E0-16's definition of done says accessibility does not apply, because
this is a test harness. The markup is plain and labelled because that costs
nothing; it has not been audited against WCAG 2.2 AA and this file does not
pretend it has.

**No page and no document carries a password**, because there is no password:
this provider signs in whichever seeded identity the form posts
(`docs/adr/0060-the-mock-provider-authenticates-a-seeded-subject.md`).
"""

from html import escape
from typing import Any

from app.config import (
    AUTHORIZATION_PATH,
    DISCOVERY_PATH,
    LOGIN_PATH,
    MOCK_REGISTRATION_PATH,
    ProviderSettings,
)
from app.flow import CODE_CHALLENGE_METHOD, ROLES_CLAIM, PendingAuthorization
from app.seed import MockPerson, SeededDirectory

INDEX_TITLE = "Mock IdP — OpenID Connect for web login"
LOGIN_TITLE = "Mock IdP — sign in"
REFUSAL_TITLE = "Mock IdP — request refused"

# The `data-testid` values E0-18's Playwright specs address the form by. Named
# here rather than written into the markup inline, because they are an interface
# to another ticket: a rename is a change to what E0-18 clicks, and it should be
# visible as one.
IDENTITY_CONTROL_TESTID = "mock-idp-identity"
SUBMIT_CONTROL_TESTID = "mock-idp-submit"

# The form field the login page posts the chosen identity under. It is the value
# that becomes the `sub` claim, and it is named for that.
IDENTITY_FIELD = "sub"

# The field carrying which authorization request this login answers. Opaque, and
# the only thing the form round-trips: everything else about the request stayed
# on the server when it was checked (see `app.flow.PendingAuthorization`).
REQUEST_FIELD = "request"

# Static CSS, no interpolation. This is code, not a value a caller supplied, so
# it never goes through `escape` and it never sits next to a value that does —
# nothing from a request is ever written into this string. The indigo/violet
# accent is this service's own: the mock LTI platform is a cooler slate/blue, so
# the two are never mistaken for one another, and neither is Pulse's own palette
# (`design/tokens.css` is deliberately not referenced here — this stands in for
# an institution's identity provider, not for Pulse).
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
      background: #f5f0fc;
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
    h1 { font-size: 1.375rem; margin: 0 0 0.5rem; color: #6d28d9; }
    h2 {
      font-size: 1rem;
      margin: 2rem 0 0.75rem;
      color: #6d28d9;
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
    label { display: block; font-weight: 600; font-size: 0.875rem; margin-bottom: 0.35rem; color: #27272a; }
    form p { margin: 0 0 1rem; }
    select {
      width: 100%;
      padding: 0.55rem 0.65rem;
      border: 1px solid #d4d4d8;
      border-radius: 8px;
      font-size: 0.9375rem;
      background: #ffffff;
      color: #18181b;
    }
    select:focus { outline: 2px solid #7c3aed; outline-offset: 1px; border-color: #7c3aed; }
    button[type="submit"] {
      appearance: none;
      border: none;
      background: #7c3aed;
      color: #ffffff;
      font-size: 0.9375rem;
      font-weight: 600;
      padding: 0.65rem 1.25rem;
      border-radius: 8px;
      cursor: pointer;
    }
    button[type="submit"]:hover { background: #6d28d9; }
    dl {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 0.4rem 1rem;
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 1rem;
      font-size: 0.875rem;
    }
    dt { color: #52525b; font-weight: 600; }
    dd { margin: 0; }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.85em;
      background: rgba(0, 0, 0, 0.05);
      padding: 0.1em 0.35em;
      border-radius: 4px;
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; margin-top: 0.5rem; }
    th, td { text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid #e5e7eb; }
    th { color: #52525b; font-weight: 600; background: #f8fafc; }
    a { color: #7c3aed; }
    @media (prefers-color-scheme: dark) {
      body { background: #1e1b29; color: #e4e4e7; }
      .card { background: #18181b; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4); }
      h1, h2 { color: #a78bfa; }
      h2 { border-top-color: #3f3f46; }
      p { color: #a1a1aa; }
      label { color: #d4d4d8; }
      select { background: #27272a; border-color: #3f3f46; color: #f4f4f5; }
      dl { background: #27272a; border-color: #3f3f46; }
      dt { color: #a1a1aa; }
      code { background: rgba(255, 255, 255, 0.08); }
      th { background: #27272a; }
      th, td { border-color: #3f3f46; }
      a { color: #a78bfa; }
      .banner { background: #451a03; border-color: #c2410c; color: #fed7aa; }
    }
"""

# Static banner markup, no interpolation: it names what the service is and
# nothing a caller supplied.
BANNER = """
    <div class="banner">
      <span>&#9888;&#65039;</span>
      <span>
        <strong>Development-only mock identity provider.</strong>
        It signs in as any seeded identity with no password and no authentication.
        Never point a real deployment at this service.
      </span>
    </div>"""


def hidden(name: str, value: str) -> str:
    """One hidden form field, both halves escaped."""
    return (
        f'<input type="hidden" name="{escape(name, quote=True)}" '
        f'value="{escape(value, quote=True)}">'
    )


def option(value: str, label: str) -> str:
    """One `<select>` option. The value is the wire value; the label is for a human."""
    return f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'


def page(title: str, body: str) -> str:
    """The shell every page below shares, so three pages are one document shape."""
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{escape(title)}</title>
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


def person_row(subject: MockPerson) -> str:
    """One seeded person, as a row of the table both HTML pages show."""
    roles = ", ".join(role.value for role in subject.web_login_roles) or "—"
    other = ", ".join(role.value for role in subject.launch_only_roles) or "—"
    return (
        "<tr>"
        f"<td><code>{escape(subject.subject)}</code></td>"
        f"<td>{escape(subject.label)}</td>"
        f"<td><code>{escape(roles)}</code></td>"
        f"<td><code>{escape(other)}</code></td>"
        "</tr>"
    )


def person_table(directory: SeededDirectory) -> str:
    """Everybody this provider knows, and which door each assignment opens."""
    rows = "\n        ".join(person_row(subject) for subject in directory.people)
    return f"""<table>
      <thead>
        <tr>
          <th>Subject</th><th>Who they are</th>
          <th>Roles a session states</th><th>Roles that use the other door</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>"""


def index_page(settings: ProviderSettings, directory: SeededDirectory) -> str:
    """The page a developer lands on: what this is, who it knows, how to configure it.

    It carries **no form**, deliberately. A "start a login" button here could not
    do PKCE — the verifier belongs to the client and has to be minted by whatever
    will redeem the code — so a demo flow driven from this page would have to be
    one without PKCE, which is the single most important thing this provider
    exists to make E1 do. A login begins at the client.
    """
    registration = "\n      ".join(
        f"<dt>{escape(term)}</dt><dd><code>{escape(str(value))}</code></dd>"
        for term, value in client_registration(settings).items()
    )
    return page(
        INDEX_TITLE,
        f"""    <h1>{escape(INDEX_TITLE)}</h1>
    <p>
      A development-only OpenID Connect provider, standing in for the
      institution's identity provider so that Pulse's second entry door
      (SPEC §2) can be exercised without one. It authenticates nobody: it signs
      a session for whichever seeded identity a login form posts.
    </p>
    <p>
      A login starts at the client, not here. Send an authorization request to
      <code>{escape(AUTHORIZATION_PATH)}</code> with a PKCE challenge; the
      endpoints are published at
      <a href="{escape(DISCOVERY_PATH, quote=True)}"><code>{escape(DISCOVERY_PATH)}</code></a>
      and the registration below is also served as JSON at
      <a href="{escape(MOCK_REGISTRATION_PATH, quote=True)}">
        <code>{escape(MOCK_REGISTRATION_PATH)}</code></a>.
    </p>

    <h2>Registration</h2>
    <dl>
      {registration}
    </dl>

    <h2>Who it can sign in</h2>
    <p>
      Web login is for every role except instructor and student, who enter by
      LTI launch (SPEC §2). The last person holds one assignment of each kind:
      she signs in here for Care work and launches from the mock LMS to teach,
      and this door will only ever act under the Care half.
    </p>
    {person_table(directory)}""",
    )


def login_page(
    settings: ProviderSettings,
    pending: PendingAuthorization,
    directory: SeededDirectory,
) -> str:
    """The form that asks who is signing in, and posts the answer.

    One control and one button. The control offers the seeded people this door is
    open to — computed from their assignments, so a person the form offers is a
    person the login handler will accept, and the two cannot drift.

    The authorization request is **not** in this form beyond its opaque
    identifier. Everything else about it was checked when it arrived and stayed
    on the server; a hidden `redirect_uri` here would be a value the browser gets
    to choose after the check that validated it.
    """
    people = directory.web_login_people()
    choices = "\n          ".join(
        option(subject.subject, f"{subject.label} — {subject.subject}") for subject in people
    )
    return page(
        LOGIN_TITLE,
        f"""    <h1>{escape(LOGIN_TITLE)}</h1>
    <p>
      <code>{escape(settings.client_id)}</code> is asking who you are. Pick a
      seeded identity; there is no password, and there is nothing else this
      provider knows about any of them.
    </p>

    <form method="post" action="{escape(LOGIN_PATH, quote=True)}">
      {hidden(REQUEST_FIELD, pending.request_id)}
      <p>
        <label for="{escape(IDENTITY_FIELD, quote=True)}">Sign in as</label>
        <select id="{escape(IDENTITY_FIELD, quote=True)}"
                name="{escape(IDENTITY_FIELD, quote=True)}"
                data-testid="{escape(IDENTITY_CONTROL_TESTID, quote=True)}">
          {choices}
        </select>
      </p>
      <p>
        <button type="submit"
                data-testid="{escape(SUBMIT_CONTROL_TESTID, quote=True)}">Sign in</button>
      </p>
    </form>

    <h2>Who it can sign in</h2>
    {person_table(directory)}""",
    )


def refusal_page(detail: str) -> str:
    """What a refused request answers with: the reason, and nothing to submit.

    No form, and no link back to anything the caller named. A refusal that
    offered a way onward would be offering it to whoever built the request that
    was just refused.
    """
    return page(
        REFUSAL_TITLE,
        f"""    <h1>{escape(REFUSAL_TITLE)}</h1>
    <p>{escape(detail)}</p>
    <p>
      Nothing was issued. See
      <a href="{escape(MOCK_REGISTRATION_PATH, quote=True)}">
        <code>{escape(MOCK_REGISTRATION_PATH)}</code></a>
      for the registered client and the seeded identities.
    </p>""",
    )


def client_registration(settings: ProviderSettings) -> dict[str, str]:
    """What a client needs to talk to this provider, keyed as a client configures it.

    Protocol spellings — `client_id`, `redirect_uri`, `jwks_uri` — rather than
    column names, and that is where this differs from the mock platform's
    registration document (ADR 0036), deliberately: there the audience fills in
    `lti_platform`'s columns by hand, and here there is no such table. The
    audience is whoever configures an OIDC client library, so the keys are the
    names those libraries use.

    `token_endpoint_auth_method` and `code_challenge_method` are in here because
    they are the two things a client gets wrong silently: it looks for a secret
    that was never issued, or it starts a flow without a challenge and is refused
    at the token endpoint with a message about the challenge it never sent.
    """
    return {
        "issuer": settings.issuer,
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "openid_configuration": settings.discovery_url,
        "authorization_endpoint": settings.authorization_url,
        "token_endpoint": settings.token_url,
        "jwks_uri": settings.jwks_url,
        "token_endpoint_auth_method": "none",
        "code_challenge_method": CODE_CHALLENGE_METHOD,
        "roles_claim": ROLES_CLAIM,
    }


def seeded_identity(subject: MockPerson) -> dict[str, Any]:
    """One seeded person, as the document publishes them.

    `roles` is what a session for this person states; `launch_only_roles` is what
    they hold that this door will not act under, and it is the half that cannot
    be discovered by signing in — which is exactly why it is published. E0-18 has
    to find the person holding both, and reading the source is not a way for a
    test to find anything.
    """
    return {
        "sub": subject.subject,
        "label": subject.label,
        "email": subject.email,
        "roles": [role.value for role in subject.web_login_roles],
        "launch_only_roles": [role.value for role in subject.launch_only_roles],
        "assignments": [
            {"role": assignment.role.value, "scope": assignment.scope}
            for assignment in subject.assignments
        ],
        "web_login": subject.may_use_web_login,
        "lms_user_id": subject.lms_user_id,
    }


def registration_document(settings: ProviderSettings, directory: SeededDirectory) -> dict[str, Any]:
    """The registration and the seed, in one fetch.

    Two audiences, one source: a developer reads the index page, and E1's login
    work, E0-18's browser specs and anything else that has to drive this provider
    without a browser read this. Both are built from the same functions, so they
    cannot disagree — the reasoning ADR 0036 gives for the platform, applied to
    the door E1 has yet to build.

    It is served under `/mock/` because no real provider serves it: an
    institutional IdP issues a `client_id` through a registration process and
    never lists the people it can sign in. A client that learned this route would
    have learned something it cannot rely on anywhere else
    (`docs/adr/0058-the-mock-provider-publishes-its-registration-and-its-seed.md`).
    """
    return {
        **client_registration(settings),
        "users": [seeded_identity(subject) for subject in directory.people],
    }
