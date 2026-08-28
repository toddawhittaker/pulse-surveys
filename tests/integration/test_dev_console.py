"""The developer test console `GET /dev`, served with a real roster behind it.

The console is a development-only page: it fetches the mock identity provider's
roster and lists the web-login people as one-click "sign in as this person"
links to `/auth/oidc/login?login_hint=<subject>`, each opening in a new tab, plus
a link to the mock LMS launcher. It exists so a developer can walk both entry
doors (SPEC §2) without typing URLs.

Everything here is asserted over HTTP against the application `app.main:create_app`
returns, with the mock provider served in process through `app.state.http` — the
same seam `tests/integration/test_web_login_door.py` drives, and for the same
reason: the console's roster fetch is a server-side call, so mounting the provider
by host lets the page render with a genuine roster and no live network.

**Two settled facts this module is built on.** The console fetches the roster
from `{oidc_issuer}/mock/registration` over `app.state.http`, so the fixture below
mounts the provider under the **`oidc_issuer` host** — the same host its token and
JWKS endpoints carry — and a fetch to that host resolves in process. And the
launcher links are derived from the *origins of the registered platforms'
authorization endpoints*, one link per distinct origin, so the launcher
assertions compute what they expect from the rows the test registered.

**That second fact changed in E1-05, and the change is the point.** The launcher
link used to come from the origin of a process-wide setting, which is one link
whatever is registered — including when nothing is. The endpoint is a column on
`lti_platform` now, so the console reads the registrations: a platform per
distinct origin, and, where no platform is registered at all, an honest line
saying so instead of a link to an address nobody configured. Both directions are
asserted below, because a console that renders a link built from nothing is worse
than one that renders none: it sends a developer to a port that answers nothing
and tells them the stack is broken.

The gate's production half — that `/dev` 404s outside development — is asserted
without a roster in `tests/unit/test_dev_console.py`. These two directions are a
pair, and the unit module names this one.
"""

from html.parser import HTMLParser
from typing import Any, NamedTuple
from urllib.parse import urlsplit

import pytest
from fixtures.lti_platform import origin_of

pytestmark = pytest.mark.integration

DEV_CONSOLE_PATH = "/dev"

ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEVELOPMENT = "development"

# The mock provider's redirect-URI setting, spelled as `test_web_login_door.py`
# spells it: it is compared exactly on the way in and again at the token endpoint,
# so this and the tool's callback have to be one address.
MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE = "MOCK_IDP_TOOL_REDIRECT_URI"

# A browser-facing OIDC authorization endpoint that no implementation could reach
# by accident, so the tool has to be reading it from configuration. Only used to
# fill the setting; the console does not send a browser here. `.invalid` is RFC
# 2606.
CONFIGURED_AUTHORIZATION_ENDPOINT = "http://identity-provider.invalid/dev-console-authorize"

# Two registered platforms' browser-facing authorization endpoints. The console
# renders one launcher link per distinct origin, so these are set to known
# addresses and the launcher assertions compute the expected origins from them.
# Distinct hosts and explicit ports, so each origin is a path-less, unambiguous
# thing to compare a launcher href against — and two of them, because one
# registration cannot tell a console that reads the table from a console that
# renders whatever it did before.
FIRST_PLATFORM_AUTHORIZATION_ENDPOINT = "http://lti-platform.invalid:9443/dev-console-authorize"
SECOND_PLATFORM_AUTHORIZATION_ENDPOINT = "http://other-platform.invalid:9444/dev-console-authorize"

# What those platforms are registered as. Nothing here is fetched and nothing is
# launched: the console reads the rows and renders links. `.invalid` is RFC 2606.
FIRST_PLATFORM_ISSUER = "http://lti-platform.invalid:9443"
SECOND_PLATFORM_ISSUER = "http://other-platform.invalid:9444"

# The two seeded subjects the ticket names by hand: the dean, and the person who
# holds Care here and teaches by the other door. Both must appear on the console,
# so a roster that lost either — or a page rendering none — fails by name.
DEAN_SUBJECT = "mock-idp-user-dean"
TWO_HAT_SUBJECT = "mock-idp-user-care-who-teaches"

# What a link that opens in a new tab carries (HTML `target` attribute).
NEW_TAB = "_blank"

# How the console may say that no platform is registered, with nothing in
# `lti_platform`. **A set of phrases rather than a sentence**: the exact wording
# is the implementer's, and pinning it would make an improvement to the copy a
# test change — but a page that says *none* of these has reported the situation
# by rendering nothing, which is the failure the test using this is about. Each
# phrase is one only an honest line would contain; none of them appears in a
# roster listing by accident.
NO_PLATFORM_PHRASES = (
    "no platform",
    "no lti platform",
    "not registered",
    "run the seed",
    "make seed",
)


class Anchor(NamedTuple):
    """One `<a>`: where it points and whether it opens in a new tab."""

    href: str
    target: str


class AnchorReader(HTMLParser):
    """Every `<a>` on a page, as an `href`/`target` pair.

    A parser rather than a regular expression because the property under test —
    "the sign-in links open in a new tab" — is about which attributes sit on which
    tag, and a pattern over markup answers a question that only looks the same
    (`docs/MISTAKES.md` entry 3). Its own control test is below.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[Anchor] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        values = {name.lower(): (value or "") for name, value in attrs}
        self.anchors.append(Anchor(href=values.get("href", ""), target=values.get("target", "")))


def anchors_in(markup: str) -> list[Anchor]:
    """Parse `markup` and hand back every anchor it declares."""
    reader = AnchorReader()
    reader.feed(markup)
    reader.close()
    return reader.anchors


# A launcher link is the origin of a registered platform's authorization endpoint
# (`http://host:port`, no path), so that is what a launcher href is compared
# against. `origin_of` lives in `tests/fixtures/lti_platform.py` beside the other
# URL arithmetic, because the framing policy in
# `test_the_security_response_headers.py` asks the same question of the same
# column (`docs/MISTAKES.md` entry 13). Each origin is still computed from the
# value *this* module registered, so the two cannot become different strings.
FIRST_LAUNCHER_ORIGIN = origin_of(FIRST_PLATFORM_AUTHORIZATION_ENDPOINT)
SECOND_LAUNCHER_ORIGIN = origin_of(SECOND_PLATFORM_AUTHORIZATION_ENDPOINT)


def launcher_anchors(anchors: list[Anchor], origin: str) -> list[Anchor]:
    """The anchors pointing at one platform's launcher: its origin, or under it."""
    return [anchor for anchor in anchors if anchor.href.startswith(origin)]


def every_launcher_anchor(anchors: list[Anchor]) -> list[Anchor]:
    """The anchors pointing at either registered platform's launcher."""
    return [
        anchor
        for anchor in anchors
        if anchor.href.startswith((FIRST_LAUNCHER_ORIGIN, SECOND_LAUNCHER_ORIGIN))
    ]


def serves_html(response: Any) -> str:
    """The body of a `200 text/html` response, or a failure saying what came instead."""
    assert response.status_code == 200, (
        f"`GET {DEV_CONSOLE_PATH}` answered {response.status_code} with `{ENVIRONMENT_VARIABLE}` set "
        f"to {DEVELOPMENT!r}. The console is served in development and nowhere else; a 404 here is "
        f"the gate closed on the direction it must stay open. Body begins {response.text[:300]!r}."
    )
    content_type = response.headers.get("content-type", "")
    assert "html" in content_type.lower(), (
        f"`GET {DEV_CONSOLE_PATH}` answered 200 with content type {content_type!r} rather than HTML. "
        "The console is a page a developer opens in a browser."
    )
    return response.text


@pytest.fixture
def provider(mock_idps: Any, door_contract: Any) -> Any:
    """The mock provider, registered to return to this tool's own callback."""
    return mock_idps(
        {
            MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.oidc_callback}"
            )
        }
    )


@pytest.fixture
def two_registered_platforms(register_platform_row: Any) -> None:
    """Two platform registrations, each with its own authorization endpoint.

    Written straight into `lti_platform` rather than by starting two mock
    platforms, because the console never resolves a launch: it reads the
    registered endpoints and renders a link per distinct origin. Starting two
    platforms to give it two rows would be paying for a launch nobody makes.

    Requested by the tests that assert what the launcher links are, and
    deliberately **not** by `dev_console` itself, so that the no-registration
    case below is a case rather than a fixture that has to be undone.
    """
    register_platform_row(
        issuer=FIRST_PLATFORM_ISSUER,
        authorization_endpoint=FIRST_PLATFORM_AUTHORIZATION_ENDPOINT,
        jwks_url=f"{FIRST_PLATFORM_ISSUER}/.well-known/jwks.json",
    )
    register_platform_row(
        issuer=SECOND_PLATFORM_ISSUER,
        authorization_endpoint=SECOND_PLATFORM_AUTHORIZATION_ENDPOINT,
        jwks_url=f"{SECOND_PLATFORM_ISSUER}/.well-known/jwks.json",
    )


@pytest.fixture
def dev_console(tool_doors: Any, door_contract: Any, provider: Any) -> Any:
    """Build the tool with the mock provider mounted, so `/dev` can fetch a roster.

    The OIDC endpoints come out of the provider's own discovery document, the way a
    client learns them, and the provider is mounted under the host those endpoints
    name — so a console fetching its roster from the configured provider reaches the
    in-process mock, and one fetching from anywhere else fails loudly.

    **No platform is registered here.** Which registrations exist is what the
    launcher half of this module is about, so it belongs to the tests rather than
    to the fixture they share (`docs/MISTAKES.md` entry 30).
    """
    document = provider.discovery()
    registration = provider.registration()
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
        # The console fetches its roster from `{oidc_issuer}/mock/registration`, so
        # the provider is mounted under the issuer's host and that fetch resolves
        # in process. The mock's issuer, token and JWKS endpoints share one host,
        # so this is also where a stray token or key-set fetch would land.
        host = urlsplit(endpoint("issuer")).hostname
        return tool_doors(values, {host: provider})

    return build


def web_login_subjects(provider: Any) -> list[str]:
    """Every subject the provider publishes as a web-login identity (ADR 0058)."""
    return [
        str(user["sub"])
        for user in provider.published_users()
        if user.get("web_login") and user.get("sub")
    ]


# ---------------------------------------------------------------------------
# The control for the anchor parser, run before anything is believed of it.
# ---------------------------------------------------------------------------


def test_the_anchor_reader_reads_href_and_new_tab_target() -> None:
    """The control on every link assertion below (`docs/MISTAKES.md` entry 3).

    The new-tab tests report that some links carry `target="_blank"` and others do
    not; a reader that saw the attribute on nothing, or on everything, would make
    both reports meaningless. So it is shown here reading a link that opens in a new
    tab and one that does not, and picking the `href` off each.
    """
    markup = (
        '<a href="/auth/oidc/login?login_hint=x" target="_blank">in</a>'
        '<a href="/somewhere">same</a>'
    )

    anchors = anchors_in(markup)

    assert anchors == [
        Anchor(href="/auth/oidc/login?login_hint=x", target=NEW_TAB),
        Anchor(href="/somewhere", target=""),
    ], (
        f"The anchor reader parsed {anchors} from a page with one new-tab link and one plain one. "
        "Every link assertion below is made with it, so it is wrong here before it is wrong about "
        "the console."
    )


# ---------------------------------------------------------------------------
# What the console serves, in development, with a real roster behind it.
# ---------------------------------------------------------------------------


def test_the_dev_console_serves_the_web_login_roster_in_development(
    dev_console: Any, door_contract: Any, provider: Any, two_registered_platforms: None
) -> None:
    """**Dies if the gate closes on development, or if the page lists no people.**

    The two mutations this kills are the paired opposite of the unit module's: a
    gate written so `/dev` 404s in development takes the console away from every
    developer, and a page that renders the shell but no roster is the feature
    without the thing it is for. So the page must be served, and it must name the
    web-login people — the dean and the two-hat person by name, since the ticket
    calls them out — each as a sign-in link carrying `login_hint`, plus a link to
    the mock LMS launcher.

    The roster is asserted to actually hold those two subjects first, so that "their
    identifiers appear on the page" cannot pass because the roster was empty and the
    page said nothing (`docs/MISTAKES.md` entry 3).
    """
    body = serves_html(dev_console().get(DEV_CONSOLE_PATH))

    subjects = web_login_subjects(provider)
    for named in (DEAN_SUBJECT, TWO_HAT_SUBJECT):
        assert named in subjects, (
            f"The provider's roster does not publish {named!r} as a web-login identity (it "
            f"publishes {subjects}), so the assertion that it appears on the console would be about "
            "an empty roster rather than about the page."
        )
        assert named in body, (
            f"The console does not name {named!r}. The page lists the web-login people fetched from "
            f"the mock provider's roster, and this is one the ticket names by hand. Body begins "
            f"{body[:400]!r}."
        )

    assert f"login_hint={DEAN_SUBJECT}" in body, (
        f"The console carries no sign-in link with `login_hint={DEAN_SUBJECT}`. Each person is "
        "offered as a one-click link to `/auth/oidc/login` carrying their subject as the "
        f"`login_hint`. Body begins {body[:400]!r}."
    )
    assert door_contract.oidc_login in body, (
        f"The console names no `{door_contract.oidc_login}` link at all, so its sign-in links do "
        "not point at the web door they are for."
    )

    anchors = anchors_in(body)
    assert every_launcher_anchor(anchors), (
        "The console carries no link to a registered platform's launcher, at either of the "
        f"origins {FIRST_LAUNCHER_ORIGIN!r} and {SECOND_LAUNCHER_ORIGIN!r}. The ticket has the "
        "console offer both entry doors, and since E1-05 a launcher URL is the origin of a "
        f"registered platform's `authorization_endpoint`. Anchors on the page: {anchors}."
    )


def test_the_dev_console_offers_a_launcher_for_each_registered_platform(
    dev_console: Any, two_registered_platforms: None
) -> None:
    """The console reads the registrations, and one platform cannot show that it does.

    Two platforms are registered with authorization endpoints at two different
    origins, so the console has to offer two launchers. A console that renders
    one link — from a setting, from a constant, or from whichever row it read
    first — is exactly what E1-05 deletes, and it is indistinguishable from a
    correct one against a stack with a single registration, which is what every
    development database has held until now.

    **The mutations this kills:** a launcher origin read from anywhere that is
    not the registrations; and a console that reads them and renders only the
    first.

    Each origin is required *present* rather than the count being asserted, so a
    console that legitimately grows a second kind of link is not broken by this.
    """
    anchors = anchors_in(dev_console().get(DEV_CONSOLE_PATH).text)

    for origin in (FIRST_LAUNCHER_ORIGIN, SECOND_LAUNCHER_ORIGIN):
        assert launcher_anchors(anchors, origin), (
            f"The console offers no launcher at {origin!r}. Two platforms are registered here, "
            f"with endpoints at {FIRST_LAUNCHER_ORIGIN} and {SECOND_LAUNCHER_ORIGIN}, and the "
            "console renders one link per distinct registered origin. Anchors on the page: "
            f"{anchors}."
        )


def test_the_dev_console_says_no_platform_is_registered_when_none_is(dev_console: Any) -> None:
    """With nothing registered, the console says so instead of linking to nowhere.

    This is the case the deleted setting could not express: a process-wide
    address is a launcher link whatever the database holds, including when it
    holds nothing, so a developer who has not run the seed got a link to a port
    that answers nothing and read the stack as broken. Reading the registrations
    makes the empty case *visible*, and the honest answer to it is a line naming
    what is missing and how to fix it.

    **The mutations this kills:** a launcher link built from a hardcoded fallback
    when the query comes back empty — which is the deleted setting arriving back
    as a constant — and a console that renders nothing at all where a platform
    should be, leaving a developer to work out from an absence that the seed has
    not run.

    **What is pinned and what is not.** That a launcher link is absent is the
    hard half, and it is asserted exactly. That the page *says something* is
    asserted against the set of phrases below rather than against a sentence: any
    one of them means the page reported the situation, and none of them turns up
    by accident in a roster listing, so this fails against silence without making
    an improvement to the wording a test change. If a wording arrives that says
    the same thing in none of these words, `NO_PLATFORM_PHRASES` is one line to
    widen deliberately — and the pull request that widens it says what the page
    now says.
    """
    body = serves_html(dev_console().get(DEV_CONSOLE_PATH))
    anchors = anchors_in(body)

    assert not every_launcher_anchor(anchors), (
        "The console offers a launcher link with no platform registered: "
        f"{every_launcher_anchor(anchors)}. Those origins belong to registrations this test did "
        "not make, so the address came from a constant or a fallback — which is the process-wide "
        "setting E1-05 deletes, arriving back under another name."
    )

    lowered = body.lower()
    assert any(phrase in lowered for phrase in NO_PLATFORM_PHRASES), (
        f"The console says none of {list(NO_PLATFORM_PHRASES)} with `lti_platform` empty, so it "
        "reported the absence by rendering nothing. The developer whose database has not been "
        "seeded is exactly the reader of this page, and a blank space where a launcher used to be "
        f"tells them the stack is broken. Body begins {body[:400]!r}."
    )


def test_the_dev_console_links_open_in_a_new_tab(
    dev_console: Any, two_registered_platforms: None
) -> None:
    """**Dies if a sign-in link or the launcher link replaces the console's own window.**

    Opening in a new tab is part of the contract: a developer clicks a person,
    signs in on the tab that opens, and comes back to the console still on the
    original tab to pick the next one. A link without `target="_blank"` navigates
    the console away, which is the window-replacement defect the ticket names.

    Both kinds are checked, and each carries its own premise guard so that "they all
    open in a new tab" cannot pass because there were none of that kind to check.
    """
    body = dev_console().get(DEV_CONSOLE_PATH).text
    anchors = anchors_in(body)

    sign_in = [anchor for anchor in anchors if "login_hint=" in anchor.href]
    assert sign_in, (
        f"The console carries no sign-in link (no anchor whose `href` holds `login_hint=`). Anchors "
        f"on the page: {anchors}."
    )
    stuck_signin = [anchor for anchor in sign_in if anchor.target != NEW_TAB]
    assert not stuck_signin, (
        f'These sign-in links do not open in a new tab: {stuck_signin}. Without `target="{NEW_TAB}"`'
        " a click navigates the console away, and the developer loses the menu they were working "
        "through."
    )

    launcher = every_launcher_anchor(anchors)
    assert launcher, (
        "The console carries no launcher link at either registered origin "
        f"({FIRST_LAUNCHER_ORIGIN!r}, {SECOND_LAUNCHER_ORIGIN!r}), so the new-tab property cannot "
        f"be asserted of it. Anchors on the page: {anchors}."
    )
    stuck_launcher = [anchor for anchor in launcher if anchor.target != NEW_TAB]
    assert not stuck_launcher, (
        f"These launcher links do not open in a new tab: {stuck_launcher}. They replace the "
        "console's window like any other link that omits the target."
    )
