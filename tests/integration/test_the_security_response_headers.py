"""The security headers every response carries, and who may frame the app — E1-04 item 2.

The governing "done when" is `docs/tickets/e1/deferred.md`, E1-04 item 2, carried
into `docs/tickets/e2/carried-from-e1.md` as "The application sends no security
response headers":

    the app factory attaches a deliberate header set to every response — a CSP,
    `X-Content-Type-Options: nosniff`, a `Referrer-Policy`, and a
    `frame-ancestors` directive naming who may frame the app — with a test
    pinning each header.

**Three kinds of response, not one, and that is the whole of "every response".** A
header set added by a router dependency, or by one route's own `Response` object,
passes any test that reads a single endpoint and ships an application whose SPA
and whose 404s carry nothing. So each header is asserted over an API response
(`/healthz`, JSON, from a router), the built SPA's entry document (a static mount,
which is not a router at all), and a path nothing routes (a 404 Starlette
produced, which no route handler ever saw). Only a middleware wrapping the whole
application answers all three.

**Why the framing directive is asserted on a document and not on the JSON.** Only
a document can be framed, and the work order leaves the implementer a choice it is
not this module's business to make: set `frame-ancestors` on every response, or
only on the document responses that can actually be framed. Both satisfy the
criterion, so the assertions here are made against the SPA entry document — which
is what an LMS iframe actually holds — and this module says nothing at all about
whether a JSON body also carries the directive. ADR 0102 records whichever the
implementer chose.

**The framing directive is proved against the registration table, never a
literal.** `frame-ancestors` must admit the platforms that legitimately frame a
launch, and the browser-facing origin a registration exposes is its
`authorization_endpoint` — the same column `launcher_origins` reads for the
developer console (E1-05). So every expectation below is computed from the rows
*this module registered*, with `origin_of` — the helper the console suite uses,
shared rather than copied (`docs/MISTAKES.md` entry 13). A policy naming an origin
this module did not register came from a constant or a fallback, which is exactly
the process-wide setting E1-05 deleted arriving back under another name.

**The policy is parsed, not searched.** A substring search over the header answers
a question that only looks the same (`docs/MISTAKES.md` entry 3). Two ways it goes
wrong, and both are live here: a policy may legitimately carry
`style-src 'unsafe-inline'` if the bundler injects an inline style, and a search
for `'unsafe-inline'` would call that an inline-script hole; and a policy with no
`script-src` at all falls back to `default-src`, so "no `'unsafe-inline'` in
`script-src`" is *vacuously true* of a policy that allows inline script through
`default-src`. `directives` and `sources_for` below implement the fallback and the
first-wins repeat rule, and `test_the_policy_parser_...` is their control, run
against the text it is claimed to catch and the text it is claimed to allow.

The harness is the door suites': `tool_doors` builds `app.main.create_app()`
against the container database with the settings a test chooses. No mock is
mounted — nothing here makes a server-side fetch, so a door that reached for one
would fail loudly rather than be quietly served.
"""

from pathlib import Path
from typing import Any

import pytest

from fixtures.lti_platform import origin_of

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# The header names, and the values the done-when and the work order settle.
# ---------------------------------------------------------------------------

CONTENT_SECURITY_POLICY = "Content-Security-Policy"
X_CONTENT_TYPE_OPTIONS = "X-Content-Type-Options"
REFERRER_POLICY = "Referrer-Policy"

# The only value `X-Content-Type-Options` has. Compared case-insensitively
# because the field value is an ASCII case-insensitive match per the fetch
# standard; what is being pinned is that it is *this* token and not another.
NOSNIFF = "nosniff"

DEFAULT_SOURCE_DIRECTIVE = "default-src"
SCRIPT_SOURCE_DIRECTIVE = "script-src"
FRAME_ANCESTORS_DIRECTIVE = "frame-ancestors"

SELF_SOURCE = "'self'"
INLINE_SCRIPT_SOURCE = "'unsafe-inline'"

# What `default-src` must be, from the work order's header set: `default-src
# 'self'`. Asserted as equality rather than membership — a `default-src` that
# also names something else is a decision with a reason, and the pull request
# that widens this line is where the reason goes.
EXPECTED_DEFAULT_SOURCES = [SELF_SOURCE]

# The referrer policies that count as deliberate. **The exact value is the
# implementer's, recorded in ADR 0102**, so this is a closed set rather than one
# string: every member keeps a full URL off a cross-origin request, which is the
# property the header is being set for. `strict-origin-when-cross-origin` is the
# work order's recommendation and the likeliest member.
#
# Widening this set is a one-line deliberate change, and the pull request that
# does it says which policy was chosen and why. Narrowing it to the single value
# ADR 0102 names would be stronger still, and is the right edit once that ADR
# exists.
DELIBERATE_REFERRER_POLICIES = (
    "no-referrer",
    "same-origin",
    "strict-origin",
    "strict-origin-when-cross-origin",
)

# Named so the failure message can say what a wrong value would have cost.
# `unsafe-url` sends the full URL — path and query — to every origin; the default
# a browser applies with no header at all, `no-referrer-when-downgrade` or
# `strict-origin-when-cross-origin` depending on the browser, is not a decision
# this application made. A header carrying one of these is the header set
# without the deliberation the criterion asks for.
LEAKY_REFERRER_POLICIES = ("unsafe-url", "no-referrer-when-downgrade")

# ---------------------------------------------------------------------------
# The application under test: what is served, and where from.
# ---------------------------------------------------------------------------

ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEVELOPMENT = "development"

# The not-development value, spelled as `tests/unit/test_docs_exposure.py` spells
# it. `tool_doors` already configures an identity provider that is not the mock,
# so a deployment's environment is safe to ask for here (E0-39).
DEPLOYMENT = "production"

# Where the built SPA is found (ADR 0086). An environment variable rather than a
# §6.3 setting, which is that ADR's decision, so it is passed through the same
# route as every other value this suite sets.
FRONTEND_DIST_VARIABLE = "FRONTEND_DIST"

HEALTHZ_PATH = "/healthz"
SPA_MOUNT_ROOT = "/app/"
SPA_LANDING_PATH = "/app/student"
UNROUTED_PATH = "/no-such-path-at-all"

# The four paths, in three kinds, that the header set has to cover — and the
# status each must answer, so that "every response carries the header" cannot
# pass over four identical error pages.
EXPECTED_STATUS = {
    HEALTHZ_PATH: 200,
    SPA_MOUNT_ROOT: 200,
    SPA_LANDING_PATH: 200,
    UNROUTED_PATH: 404,
}
EVERY_PATH = tuple(EXPECTED_STATUS)

# The paths that answer the built entry document — the only responses a browser
# can frame, and the ones the framing assertions read.
DOCUMENT_PATHS = (SPA_MOUNT_ROOT, SPA_LANDING_PATH)

# A marker no implementation would produce by accident, proving the HTML that came
# back is the built entry document this module laid down rather than a refusal
# page or an error body.
SPA_MARKER = "pulse-headers-spa-3c81ef"
SPA_INDEX_HTML = (
    "<!doctype html>\n"
    '<html lang="en">\n'
    f"  <head><title>{SPA_MARKER}</title></head>\n"
    '  <body><div id="root"></div></body>\n'
    "</html>\n"
)

# ---------------------------------------------------------------------------
# The registrations the framing policy is derived from.
# ---------------------------------------------------------------------------

# Two platforms' browser-facing authorization endpoints, and a third that is
# registered nowhere. Distinct hosts *and* explicit ports, so each origin is an
# unambiguous thing to compare a `frame-ancestors` source against and a policy
# that dropped the port fails visibly. `.invalid` is RFC 2606: none of these can
# resolve if one escapes a fixture, and nothing here is ever fetched.
#
# `https` rather than `http`, unlike the developer console suite's rows. Most of
# this module builds the application with a deployment's `ENVIRONMENT`, and
# ADR 0081's registration address rules refuse cleartext off this machine there.
# Nothing judges an address on a read path today, so an `http` row would work —
# but a test that would start failing the day a read path did judge one is
# failing for a reason that is not its subject (`docs/MISTAKES.md` entry 22), and
# the scheme is not what any of these assertions is about.
FIRST_PLATFORM_AUTHORIZATION_ENDPOINT = "https://framing-platform-one.invalid:9543/authorize"
SECOND_PLATFORM_AUTHORIZATION_ENDPOINT = "https://framing-platform-two.invalid:9544/authorize"
UNREGISTERED_AUTHORIZATION_ENDPOINT = "https://framing-platform-nowhere.invalid:9545/authorize"

FIRST_PLATFORM_ORIGIN = origin_of(FIRST_PLATFORM_AUTHORIZATION_ENDPOINT)
SECOND_PLATFORM_ORIGIN = origin_of(SECOND_PLATFORM_AUTHORIZATION_ENDPOINT)
UNREGISTERED_ORIGIN = origin_of(UNREGISTERED_AUTHORIZATION_ENDPOINT)

FIRST_PLATFORM_ISSUER = "https://framing-platform-one.invalid:9543"
SECOND_PLATFORM_ISSUER = "https://framing-platform-two.invalid:9544"


# ---------------------------------------------------------------------------
# Reading a Content-Security-Policy.
# ---------------------------------------------------------------------------


def directives(policy: str) -> dict[str, list[str]]:
    """`policy` as a mapping from directive name to its source list.

    Two details of CSP that a `in`-test over the raw string gets wrong, and both
    are implemented here rather than described:

    * **A repeated directive is ignored after the first.** A policy reading
      `script-src 'self'; script-src 'unsafe-inline'` allows no inline script at
      all, because the user agent keeps the first occurrence and drops the rest.
      `setdefault` below models that, so a test never reports a hole a browser
      would not have.
    * **Names are ASCII case-insensitive**, as are the keyword sources, so
      everything is lowered. Host sources are lowered too, which is safe: a host
      is case-insensitive and every origin this module compares against is
      written in lower case.
    """
    parsed: dict[str, list[str]] = {}
    for clause in policy.split(";"):
        tokens = clause.split()
        if not tokens:
            continue
        parsed.setdefault(tokens[0].lower(), [token.lower() for token in tokens[1:]])
    return parsed


def sources_for(parsed: dict[str, list[str]], directive: str) -> list[str]:
    """The sources that actually govern `directive`, following the `default-src` fallback.

    This is the half a careless CSP silently drops. `script-src` absent does not
    mean "no inline script is allowed"; it means `default-src` decides, so a
    policy of `default-src 'self' 'unsafe-inline'` allows inline script while
    carrying no `script-src` for a test to find. Every question about a **fetch**
    directive below is asked of this rather than of `parsed` directly.

    `frame-ancestors` is deliberately *not* read through here — it is a
    navigation directive and falls back to nothing, so `framing_sources` reads it
    directly and fails when it is absent. Routing it through this fallback would
    have made a policy carrying no framing directive at all indistinguishable
    from `frame-ancestors 'self'`, and the empty-table test would have passed
    against an application that sets no framing policy whatsoever.
    """
    if directive in parsed:
        return parsed[directive]
    return parsed.get(DEFAULT_SOURCE_DIRECTIVE, [])


def admits_any_origin(sources: list[str]) -> list[str]:
    """The sources in `sources` that admit origins nobody enumerated.

    A bare `*`, a wildcard host such as `*.invalid`, and a scheme-only source such
    as `https:` each admit an origin no row registers, which is the failure the
    unregistered-origin test is about — and none of them would be caught by
    checking that a particular origin string is absent.
    """
    return [
        source
        for source in sources
        if source == "*" or source.startswith("*.") or (source.endswith(":") and "//" not in source)
    ]


def policy_of(response: Any, path: str) -> dict[str, list[str]]:
    """The parsed `Content-Security-Policy` of `response`, or a failure naming what came.

    The **enforcing** header, never `Content-Security-Policy-Report-Only`: a
    report-only policy enforces nothing, so an application carrying only that one
    has the appearance of the criterion and none of its effect.
    """
    header = response.headers.get(CONTENT_SECURITY_POLICY)
    assert header, (
        f"`GET {path}` answered {response.status_code} carrying no `{CONTENT_SECURITY_POLICY}`. "
        f"Headers: {sorted(response.headers)}.\n"
        "\n"
        "E1-04 item 2's done-when: the app factory attaches a deliberate header set to every "
        "response, a CSP among them. If a `Content-Security-Policy-Report-Only` is present "
        "instead, that reports violations and prevents none of them."
    )
    parsed = directives(header)
    assert parsed, (
        f"`GET {path}` carried a `{CONTENT_SECURITY_POLICY}` of {header!r}, which parses to no "
        "directives at all. An empty policy restricts nothing, so every assertion made about it "
        "below would pass on emptiness (`docs/MISTAKES.md` entry 3)."
    )
    return parsed


def framing_sources(response: Any, path: str) -> list[str]:
    """The `frame-ancestors` sources of `response`'s policy, or a failure if it has none.

    Read directly rather than through `sources_for`, because `frame-ancestors` is
    a navigation directive with no `default-src` fallback. A policy that omits it
    names nobody who may frame the app — and read through the fallback it would
    have answered `['self']` against a `default-src 'self'`, which is exactly
    what the empty-table test expects. That would have been a test passing for a
    reason unrelated to what it asserts (`docs/MISTAKES.md` entry 3).
    """
    parsed = policy_of(response, path)
    assert FRAME_ANCESTORS_DIRECTIVE in parsed, (
        f"`GET {path}` carried a policy with no `{FRAME_ANCESTORS_DIRECTIVE}` directive; it "
        f"carries {sorted(parsed)}.\n"
        "\n"
        "E1-04 item 2's done-when names it specifically: 'a `frame-ancestors` directive naming "
        "who may frame the app'. It has no `default-src` fallback, so a policy without it says "
        "nothing about framing at all."
    )
    return parsed[FRAME_ANCESTORS_DIRECTIVE]


# ---------------------------------------------------------------------------
# The control for the policy parser, run before anything is believed of it.
# ---------------------------------------------------------------------------


def test_the_policy_parser_follows_the_default_source_fallback_and_the_repeat_rule() -> None:
    """The control on every policy assertion below (`docs/MISTAKES.md` entry 3).

    Run against the text this module claims it catches **and** the text it claims
    it allows, because a parser that saw `'unsafe-inline'` everywhere and one that
    saw it nowhere would each make the inline-script test meaningless in a way
    reading the code would not show.

    Four cases, one per way the naive substring test is wrong:

    1. an explicit `script-src` is read as itself;
    2. with no `script-src`, `default-src` governs — so a policy that allows
       inline script through `default-src` is caught rather than passed;
    3. `style-src 'unsafe-inline'` beside `script-src 'self'` is **allowed**,
       which is the outcome the work order's first verification step permits if
       the bundler injects an inline style;
    4. a repeated directive keeps the first occurrence, the way a user agent
       does, so a policy that cannot allow inline script is not reported as
       though it could.
    """
    explicit = sources_for(directives("default-src 'self'; script-src 'self'"), "script-src")
    assert explicit == ["'self'"], f"An explicit `script-src` parsed to {explicit}."

    inherited = sources_for(directives("default-src 'self' 'unsafe-inline'"), "script-src")
    assert inherited == ["'self'", INLINE_SCRIPT_SOURCE], (
        f"With no `script-src`, the sources governing script parsed to {inherited}. CSP falls back "
        "to `default-src`, so this policy allows inline script and the parser has to say so — "
        "otherwise the inline-script test passes vacuously against exactly this."
    )

    styles = sources_for(
        directives("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"),
        "script-src",
    )
    assert INLINE_SCRIPT_SOURCE not in styles, (
        f"An inline *style* allowance was read into the script sources: {styles}. A policy may "
        "legitimately carry `style-src 'unsafe-inline'`, and a parser that called that an "
        "inline-script hole would fail a correct implementation."
    )

    repeated = sources_for(
        directives("script-src 'self'; script-src 'unsafe-inline'"), "script-src"
    )
    assert repeated == ["'self'"], (
        f"A repeated `script-src` parsed to {repeated}. A user agent keeps the first occurrence "
        "and ignores the rest, so this policy allows no inline script and the parser must not "
        "report one."
    )


def test_the_wildcard_reader_finds_a_wildcard_and_leaves_an_origin_alone() -> None:
    """The control on `admits_any_origin` (`docs/MISTAKES.md` entry 3).

    The unregistered-origin test reports that a policy names no wildcard. A reader
    that found none in anything would make that report meaningless, so it is shown
    here finding each of the three shapes and leaving `'self'` and a real origin
    alone.
    """
    found = admits_any_origin(
        ["*", "*.invalid", "https:", SELF_SOURCE, FIRST_PLATFORM_ORIGIN, "'none'"]
    )

    assert found == ["*", "*.invalid", "https:"], (
        f"The wildcard reader found {found}. It has to see a bare `*`, a wildcard host and a "
        "scheme-only source — each admits an origin no row registers — and it must leave "
        f"`{SELF_SOURCE}` and a concrete origin alone, or the test using it never passes."
    )


# ---------------------------------------------------------------------------
# The application, and the three kinds of response the header set has to cover.
# ---------------------------------------------------------------------------


def built_spa(root: Path) -> Path:
    """A directory shaped like a build output, holding just the entry document.

    Deliberately its own rather than shared with
    `tests/unit/test_the_spa_is_served_from_the_app_factory.py`: that module's
    dist carries an asset because its subject is the mount's fallback behaviour,
    and this one needs only a document to read headers off. Sharing would tie a
    headers test to the shape of a mount test's fixture, which is two things that
    merely look alike.

    Pointed at explicitly rather than relying on `frontend/dist`, for the reason
    that module gives: a developer who has run the build once would otherwise be
    testing against a different document from CI's.
    """
    dist = root / "headers-spa-dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(SPA_INDEX_HTML, encoding="utf-8")
    return dist


@pytest.fixture
def serve(tool_doors: Any, door_contract: Any, tmp_path: Path) -> Any:
    """Build the tool with a built SPA behind it, and hand back its client.

    A factory rather than one instance, because the environment is one of the
    things asserted about: the header set is not a deployment's privilege, and the
    only way to say so is to build the application twice.

    No mock is mounted. Nothing fetched here makes a server-side call, so a door
    that reached for one fails loudly rather than being quietly served
    (`tests/fixtures/doors.py`'s `routed_through`).
    """
    dist = built_spa(tmp_path)

    def build(*, environment: str = DEPLOYMENT) -> Any:
        return tool_doors(
            {
                door_contract.settings["public_base_url"]: door_contract.public_base_url,
                FRONTEND_DIST_VARIABLE: str(dist),
                ENVIRONMENT_VARIABLE: environment,
            }
        )

    return build


def every_response(client: Any) -> dict[str, Any]:
    """`GET` each of the four paths, having first proved each answers what it should.

    **This guard is not ceremony** (`docs/MISTAKES.md` entry 3). "Every response
    carries the header" is satisfied by four identical 500s, by four 404s from an
    application whose routers never mounted, and by an `/app/` that answers some
    other HTML — and each of those would turn every assertion in this module into
    a statement about an application that is not the one under test.

    Redirects are followed, because what is asserted is what a browser ends up
    holding.
    """
    answers = {path: client.get(path, follow_redirects=True) for path in EVERY_PATH}

    wrong = {
        path: response.status_code
        for path, response in answers.items()
        if response.status_code != EXPECTED_STATUS[path]
    }
    assert not wrong, "\n".join(
        [
            "These paths did not answer the status this module is built on:",
            *(
                f"  {path} -> {status} (expected {EXPECTED_STATUS[path]})"
                for path, status in sorted(wrong.items())
            ),
            "",
            f"`{HEALTHZ_PATH}` is E0-01's and every Compose gate waits on it; the two `/app` paths "
            "are the built SPA this test laid down under `FRONTEND_DIST` (ADR 0086); "
            f"`{UNROUTED_PATH}` names no route and must be a 404 nothing handled.",
            "",
            "A failure here is this module's own setup rather than the header set — suspect the "
            "fixture first (`docs/MISTAKES.md` entry 13).",
        ]
    )

    for path in DOCUMENT_PATHS:
        assert SPA_MARKER in answers[path].text, (
            f"`GET {path}` answered 200 with something that is not the entry document this test "
            f"wrote into the dist directory (it carries no {SPA_MARKER!r}). Body begins "
            f"{answers[path].text[:300]!r}. The framing assertions read this response, so they "
            "would otherwise be about a page nobody serves."
        )

    return answers


@pytest.fixture
def responses(serve: Any) -> dict[str, Any]:
    """The four responses, from an application built with a deployment's environment."""
    return every_response(serve())


# ---------------------------------------------------------------------------
# One test per header, over an API response, a document and an unrouted 404.
# ---------------------------------------------------------------------------


def test_every_response_carries_x_content_type_options_nosniff(
    responses: dict[str, Any],
) -> None:
    """The done-when's `X-Content-Type-Options: nosniff`, on all three kinds of response.

    **The mutation this kills:** the header omitted, or set to any other value.
    Without it a browser may sniff a response body and execute as script something
    served as data — which is the whole reason the header is in the criterion's
    list beside the CSP rather than behind it.

    **The near miss that must stay green:** any casing of the token, which is an
    ASCII case-insensitive match, and any ordering or spelling of the other
    headers, none of which this reads.
    """
    wrong = {
        path: response.headers.get(X_CONTENT_TYPE_OPTIONS)
        for path, response in responses.items()
        if (response.headers.get(X_CONTENT_TYPE_OPTIONS) or "").strip().lower() != NOSNIFF
    }

    assert not wrong, "\n".join(
        [
            f"These responses did not carry `{X_CONTENT_TYPE_OPTIONS}: {NOSNIFF}`:",
            *(f"  {path} -> {value!r}" for path, value in sorted(wrong.items())),
            "",
            "E1-04 item 2's done-when names this header in the set the app factory attaches to "
            "every response. The paths are three kinds of response: an API route, a static "
            "mount, and a path no route handled. A header set added by a router dependency "
            "reaches the first and neither of the others, which is why all three kinds are "
            "here.",
        ]
    )


def test_every_response_carries_a_content_security_policy_whose_default_source_is_self(
    responses: dict[str, Any],
) -> None:
    """The done-when's CSP, present on all three kinds of response, defaulting to `'self'`.

    `default-src 'self'` is the work order's header set verbatim: everything the
    page may load comes from this origin unless a narrower directive says
    otherwise.

    **The mutation this kills:** no CSP at all; a CSP on the API and not on the
    SPA; a `default-src` widened to `*` or to a scheme, which is the shape a
    hardening header takes when it is added to stop a scanner complaining rather
    than to restrict anything.

    **The near miss that must stay green:** every other directive the policy
    carries. A CSP legitimately grows `img-src`, `connect-src`, `style-src` and
    more as E2 puts real content in the SPA, and none of that is read here.
    """
    wrong: dict[str, list[str] | None] = {}
    for path, response in responses.items():
        sources = policy_of(response, path).get(DEFAULT_SOURCE_DIRECTIVE)
        if sources != EXPECTED_DEFAULT_SOURCES:
            wrong[path] = sources

    assert not wrong, "\n".join(
        [
            f"These responses' policies do not read `{DEFAULT_SOURCE_DIRECTIVE} {SELF_SOURCE}`:",
            *(f"  {path} -> {sources}" for path, sources in sorted(wrong.items())),
            "",
            "`default-src 'self'` is the floor the rest of the policy narrows from, and a `None` "
            "here means the policy has no `default-src` at all — so every fetch directive it "
            "omits is unrestricted.",
        ]
    )


def test_every_response_carries_a_deliberate_referrer_policy(
    responses: dict[str, Any],
) -> None:
    """The done-when's `Referrer-Policy`, present and deliberate on every response.

    **The exact value is the implementer's and belongs in ADR 0102.** What the
    criterion asks is that there *is* one and that it was chosen, so this asserts
    membership of `DELIBERATE_REFERRER_POLICIES` — every member of which keeps a
    full URL off a cross-origin request — rather than one string. Narrowing this
    to the single value ADR 0102 names is the right edit once that ADR exists.

    **The mutation this kills:** the header omitted, so the browser's own default
    applies and nobody decided anything; or set to `unsafe-url`, which sends the
    path and query of the page a person is on to every origin it talks to. Inside
    an LMS iframe that URL identifies a section and a person's place in it.

    **The near miss that must stay green:** any of the four deliberate values, in
    any casing.
    """
    wrong = {
        path: response.headers.get(REFERRER_POLICY)
        for path, response in responses.items()
        if (response.headers.get(REFERRER_POLICY) or "").strip().lower()
        not in DELIBERATE_REFERRER_POLICIES
    }

    assert not wrong, "\n".join(
        [
            f"These responses carry no deliberate `{REFERRER_POLICY}`:",
            *(f"  {path} -> {value!r}" for path, value in sorted(wrong.items())),
            "",
            f"Deliberate means one of {list(DELIBERATE_REFERRER_POLICIES)}; the work order "
            "recommends `strict-origin-when-cross-origin` and ADR 0102 records the choice. A "
            "`None` means no decision was made and the browser's default stands. One of "
            f"{list(LEAKY_REFERRER_POLICIES)} is a decision to leak the URL a person is on.",
            "",
            "If ADR 0102 settles on a deliberate policy that is not in this list, that is a "
            "dispute rather than a test to edit around: `DELIBERATE_REFERRER_POLICIES` is one "
            "line, and the pull request that widens it says which policy was chosen and why.",
        ]
    )


def test_the_content_security_policy_refuses_inline_script(
    responses: dict[str, Any],
) -> None:
    """The half of a CSP that is silently dropped: no `'unsafe-inline'` governs script.

    A policy carrying `script-src 'unsafe-inline'` is a Content-Security-Policy
    header that stops nothing a cross-site scripting payload does, and it is the
    line an implementer adds when a bundle will not load. The work order settles
    this direction: the CSP admits what the built bundle legitimately loads, and
    if the bundler injects an inline *style* the answer is `style-src
    'unsafe-inline'` — styles only, never script — or a build configured to stop
    injecting it.

    **The mutation this kills:** `'unsafe-inline'` in `script-src`; and the one
    that hides, `'unsafe-inline'` in `default-src` with no `script-src` present at
    all, where the policy allows inline script and the word `script-src` never
    appears. `sources_for` follows the fallback, so both die here.

    **The near miss that must stay green:** `style-src 'unsafe-inline'`, and a
    `script-src` naming a nonce or a hash, neither of which allows arbitrary
    inline script.
    """
    offenders: dict[str, list[str]] = {}
    for path, response in responses.items():
        sources = sources_for(policy_of(response, path), SCRIPT_SOURCE_DIRECTIVE)
        assert sources, (
            f"`GET {path}` carried a policy with neither `{SCRIPT_SOURCE_DIRECTIVE}` nor "
            f"`{DEFAULT_SOURCE_DIRECTIVE}`, so nothing governs script at all and 'no "
            f"{INLINE_SCRIPT_SOURCE} in the script sources' is true of an empty list "
            "(`docs/MISTAKES.md` entry 3)."
        )
        if INLINE_SCRIPT_SOURCE in sources:
            offenders[path] = sources

    assert not offenders, "\n".join(
        [
            "These responses' policies allow inline script:",
            *(f"  {path} -> {sources}" for path, sources in sorted(offenders.items())),
            "",
            "The sources shown are the ones that actually govern script — "
            f"`{SCRIPT_SOURCE_DIRECTIVE}` where the policy has one, and "
            f"`{DEFAULT_SOURCE_DIRECTIVE}` where it does not, which is where this hides. A CSP "
            "that allows inline script refuses nothing a cross-site scripting payload does.",
        ]
    )


def test_the_headers_do_not_depend_on_the_environment(serve: Any) -> None:
    """The header set is not a deployment's privilege — asserted, because it must not be.

    Two reasons this is a criterion rather than a nicety. The done-when says the
    factory attaches the set to **every** response and names no environment. And
    the batch owes a verification step that "the full e2e suite passes against the
    enforced headers", with `tests/e2e/cookieless-launch.spec.ts` as the canary —
    which proves nothing at all if the middleware is switched off in the
    environment the e2e stack runs in.

    **The mutation this kills:** the middleware gated on `is_a_deployment(...)` or
    on `ENVIRONMENT != "development"`. That is a plausible implementation — it
    keeps a developer's stack from arguing with a CSP — and it leaves the whole
    development stack unprotected while every other test in this module stays
    green.

    Presence only: which value each header carries is settled by the three tests
    above, and repeating it here would say the same thing twice.
    """
    named = (CONTENT_SECURITY_POLICY, X_CONTENT_TYPE_OPTIONS, REFERRER_POLICY)

    missing: dict[tuple[str, str], list[str]] = {}
    for environment in (DEVELOPMENT, DEPLOYMENT):
        for path, response in every_response(serve(environment=environment)).items():
            absent = [header for header in named if not response.headers.get(header)]
            if absent:
                missing[(environment, path)] = absent

    assert not missing, "\n".join(
        [
            "These responses are missing headers the done-when puts on every response:",
            *(
                f"  ENVIRONMENT={environment!r} {path} -> missing {absent}"
                for (environment, path), absent in sorted(missing.items())
            ),
            "",
            "Both environments are here because the header set is the app factory's and the "
            "done-when names no environment — and because the e2e suite, which is the batch's "
            "proof that the framing policy admits the LMS iframe, runs against the development "
            "stack. Headers only a deployment sends are headers no browser test ever exercises.",
        ]
    )


# ---------------------------------------------------------------------------
# `frame-ancestors` — derived from the registration table, never from a literal.
# ---------------------------------------------------------------------------


def test_frame_ancestors_admits_self_and_every_registered_platforms_origin(
    register_platform_row: Any, serve: Any
) -> None:
    """The framing policy is `'self'` plus the origins the registrations name.

    Two platforms are registered, at two different origins, before the
    application is built. `frame-ancestors` must then admit exactly `'self'` and
    both of them: `'self'` because the app frames its own documents, and each
    registered origin because a launch from that platform arrives inside its
    iframe.

    **Two registrations rather than one, and that is the point.** With a single
    platform registered, a policy read from the table and a policy holding one
    hardcoded address are the same string, which is the distinction E1-05 exists
    to make and the reason the developer console's own test registers two.

    **The mutations this kills:** a static origin list from configuration or from
    source; a policy that reads the table and names only the first row it found;
    a directive that drops the port, which produces an origin no browser matches
    and an iframe that silently fails to load.

    **The near miss that must stay green:** the order the sources appear in, and
    anything else in the policy, neither of which this reads.

    The expected set is computed from the endpoints registered by *this test*, so
    a policy that agrees with it agrees with the table (`docs/MISTAKES.md` entry
    19).
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
    expected = {SELF_SOURCE, FIRST_PLATFORM_ORIGIN, SECOND_PLATFORM_ORIGIN}

    documents = every_response(serve())

    wrong: dict[str, list[str]] = {}
    for path in DOCUMENT_PATHS:
        sources = set(framing_sources(documents[path], path))
        if sources != expected:
            wrong[path] = sorted(sources)

    assert not wrong, "\n".join(
        [
            f"These documents' `{FRAME_ANCESTORS_DIRECTIVE}` is not the registered set:",
            *(f"  {path} -> {sources}" for path, sources in sorted(wrong.items())),
            "",
            f"Expected exactly {sorted(expected)} — `{SELF_SOURCE}` plus the origin of each "
            "registered platform's `authorization_endpoint`, which is the same column "
            "`launcher_origins` reads for the developer console (E1-05).",
            "",
            "A set holding only one of the two origins is a policy that read the table and "
            "stopped at the first row. A set holding neither is a policy that is not reading the "
            "table at all. A set holding something this test did not register came from a "
            "constant or a fallback.",
        ]
    )


def test_frame_ancestors_does_not_admit_an_origin_no_row_registers(
    register_platform_row: Any, serve: Any
) -> None:
    """A platform nobody registered may not frame the app, by name or by wildcard.

    One platform is registered. The second origin — a well-formed address of
    exactly the same shape, registered nowhere — must not be admitted, and the
    policy must not admit it *sideways* either: a `*`, a wildcard host, or a
    scheme-only source lets in every origin while naming none of them, and would
    pass any test that only checked a particular string was absent.

    **The registered origin is asserted present first**, so "the unregistered one
    is absent" cannot pass because the directive is empty, or missing, or admits
    nothing at all (`docs/MISTAKES.md` entry 3).

    **The mutations this kills:** `frame-ancestors *`, which is how the directive
    arrives when someone finds the iframe broken and reaches for the value that
    makes it work; and a directive built from something other than the
    registrations, which would have no reason to exclude any particular address.
    """
    register_platform_row(
        issuer=FIRST_PLATFORM_ISSUER,
        authorization_endpoint=FIRST_PLATFORM_AUTHORIZATION_ENDPOINT,
        jwks_url=f"{FIRST_PLATFORM_ISSUER}/.well-known/jwks.json",
    )

    documents = every_response(serve())
    sources = framing_sources(documents[SPA_MOUNT_ROOT], SPA_MOUNT_ROOT)

    assert FIRST_PLATFORM_ORIGIN in sources, (
        f"The framing policy does not admit {FIRST_PLATFORM_ORIGIN!r}, the origin of the one "
        f"platform this test registered; it admits {sources}. The rest of this test is about what "
        "the policy leaves out, and would pass over a policy that leaves out everything."
    )

    assert UNREGISTERED_ORIGIN not in sources, (
        f"The framing policy admits {UNREGISTERED_ORIGIN!r}, which no `lti_platform` row "
        f"registers; it admits {sources}. The directive is a property of the registration table, "
        "so an address nobody registered can only have come from a constant or a fallback — the "
        "process-wide setting E1-05 deleted, arriving back under another name."
    )

    wildcards = admits_any_origin(sources)
    assert not wildcards, (
        f"The framing policy admits {wildcards} — sources that let any origin frame the app "
        f"without naming one. The whole directive reads {sources}. That is the value the "
        "directive takes when an iframe will not load and somebody reaches for the setting that "
        f"makes it work; `{UNREGISTERED_ORIGIN}` is admitted by every one of them."
    )


def test_frame_ancestors_is_only_self_when_no_platform_is_registered(serve: Any) -> None:
    """With `lti_platform` empty, the directive is `'self'` and nothing else.

    This is the case a hardcoded list cannot express. A policy built from an
    address in configuration or in source names that address whatever the table
    holds, including when it holds nothing — and it is indistinguishable from a
    correct one against a stack with a single registration, which is what every
    development database has held.

    **The mutations this kills:** a fallback origin used when the query comes back
    empty; and `frame-ancestors *` or a scheme-only source as the empty-table
    answer, which admits every origin at exactly the moment none is registered.

    **The near miss that must stay green:** whatever the rest of the policy says,
    which this does not read. Nothing can launch with no platform registered, so
    `'self'` alone is the honest answer and not a degradation.
    """
    documents = every_response(serve())

    wrong: dict[str, list[str]] = {}
    for path in DOCUMENT_PATHS:
        sources = set(framing_sources(documents[path], path))
        if sources != {SELF_SOURCE}:
            wrong[path] = sorted(sources)

    assert not wrong, "\n".join(
        [
            f"With no platform registered, these documents' `{FRAME_ANCESTORS_DIRECTIVE}` is not "
            f"`{SELF_SOURCE}` alone:",
            *(f"  {path} -> {sources}" for path, sources in sorted(wrong.items())),
            "",
            "Nothing beyond the tool itself may frame it when no registration says otherwise. An "
            "origin here belongs to a registration this test did not make, so the address came "
            "from a constant or a fallback; a wildcard here admits everything precisely when "
            "nothing is registered.",
        ]
    )


def test_frame_ancestors_admits_a_platform_registered_after_the_application_started(
    register_platform_row: Any, serve: Any
) -> None:
    """The policy tracks the table, rather than a set computed once at startup.

    The application is built with nothing registered, its policy read, a platform
    registered, and its policy read again from the same running application. The
    new origin has to appear.

    **The mutation this kills:** the origin set computed in `create_app()` or
    memoised for the life of the process. That is a static list by another route
    — it is right on the day it is written and wrong the moment a registration is
    added — and every other framing test in this module passes against it, because
    they all register before they build. This is the one that does not.

    **The near miss that must stay green:** any caching with an invalidation
    story, since what is asserted is that the answer changed, not how often the
    table is read.

    The first read is the control: without it, "the origin appears after
    registering" would pass against a policy that named it all along
    (`docs/MISTAKES.md` entry 3).
    """
    client = serve()

    before = framing_sources(every_response(client)[SPA_MOUNT_ROOT], SPA_MOUNT_ROOT)
    assert FIRST_PLATFORM_ORIGIN not in before, (
        f"The framing policy already admits {FIRST_PLATFORM_ORIGIN!r} before anything registered "
        f"it; it admits {before}. That address is in no row, so the policy is not derived from "
        "the table and the rest of this test would pass without the registration doing anything."
    )

    register_platform_row(
        issuer=FIRST_PLATFORM_ISSUER,
        authorization_endpoint=FIRST_PLATFORM_AUTHORIZATION_ENDPOINT,
        jwks_url=f"{FIRST_PLATFORM_ISSUER}/.well-known/jwks.json",
    )

    after = framing_sources(every_response(client)[SPA_MOUNT_ROOT], SPA_MOUNT_ROOT)

    assert FIRST_PLATFORM_ORIGIN in after, (
        "A platform registered while the application was running may not frame it: the policy "
        f"read {before} before the registration and {after} after it, and "
        f"{FIRST_PLATFORM_ORIGIN!r} is the origin of the `authorization_endpoint` that was just "
        "written.\n"
        "\n"
        "The directive is a property of the registration table (E1-05's column, the same one "
        "`launcher_origins` reads). A set computed once in the app factory is a hardcoded list "
        "that happened to be built at run time: correct on the day it was written, and wrong for "
        "every registration made afterwards. Caching is allowed; a cache with no invalidation is "
        "what this fails."
    )
