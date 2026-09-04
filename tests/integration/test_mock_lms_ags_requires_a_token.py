"""The mock platform's grade services refuse a call that is not authorised — E3-04.

ADR 0099 recorded that the mock requires a client-credentials token on NRPS and
still does not on AGS, and recorded why: "no AGS client exists yet and a `401` there
would be refused by nothing but this repository's own E0-15 tests — `docs/
MISTAKES.md` entry 22 exactly". It named the owner in the same sentence — "Owner:
E3, which builds the first AGS client" — and E3-04 is the ticket that does both
halves at once, which is what makes the pairing structural instead of stated. This
module is the platform half.

**The contract, per route.** Every AGS route requires an `Authorization: Bearer
<token>` whose token this platform's own endpoint issued carrying a scope that route
accepts (ADR 0134):

  - `POST …/line_items`         — `…/scope/lineitem`
  - `GET …/line_items`          — `…/scope/lineitem` **or** `…/scope/lineitem.readonly`
  - `GET …/line_items/{id}`     — `…/scope/lineitem` **or** `…/scope/lineitem.readonly`
  - `POST …/scores`             — `…/scope/score`
  - `GET …/results`             — `…/scope/result.readonly`
  - `GET …/results/{user}`      — `…/scope/result.readonly`

A missing or malformed header is **401** with a bare `WWW-Authenticate: Bearer`
challenge naming no error code; a token this platform did not sign is **401**,
`invalid_token`; a token it issued for a scope the route does not accept is **403**,
`insufficient_scope`. Those statuses and those two strings are RFC 6750's, §3.1, and
§3 is what puts them inside the challenge — nothing here invents a vocabulary.

**The triple, per route, and the third of it is a control that must be green.**
Criterion 6 asks for all three on every route: the absent token refused, the wrong
scope refused, the right scope accepted. The accepting half is the one that says the
harness's credential arrives and parses at all — a module whose only evidence was
that its refusals went red would be reporting a platform that refuses everything
(`docs/MISTAKES.md` entry 35). **Those halves are green before this ticket lands and
green after it**, and a red in one of them means these tests are broken rather than
that the mock is.

**The superstring pair is the one that proves membership rather than substring**,
and it is the carried entry's own subject. `…/scope/lineitem.readonly` contains
`…/scope/lineitem` as a prefix, so a check written as `required in granted` over the
raw claim string — or as `granted.startswith(required)` — accepts a read-only token
on the route that creates line items. Both directions are asserted: the read-only
token refused there, and the writing token accepted there. Until this ticket there
was no second scope on one service to pose it with.

**The credential is judged before anything else about the request**, which the NRPS
route already does and ADR 0134 copies. Two groups assert the ordering rather than
the status: an unauthenticated call naming a context nothing seeds is answered 401
rather than 404, and an unauthenticated read carrying a page cursor below its own
bound is answered 401 rather than the framework's 422. That second one is ADR 0099's
own recorded consequence — "the AGS containers keep their `ge=1` page bound in the
signature… the day AGS starts requiring a token, those two signatures are part of
the work" — and it is the case a route signature makes easy to get wrong, because a
bound declared there is enforced before the handler runs at all.

**`GET /mock/posted-scores` stays tokenless, and that is a decision with a test.**
ADR 0047 puts the posted-score readback outside the AGS namespace as an inspection
surface no real platform serves, and ADR 0134 says out loud that the `/mock/` prefix
is outside this enforcement — so a reviewer can tell the decision from an oversight.
The test at the foot is what makes it a decision rather than a sentence: an
enforcement applied by path prefix, or applied to every route in the application,
takes that surface with it and every readback in the suite with it.

**What this module deliberately leaves to its neighbour.** `app.tokens::
authorised_token` is one door and `test_mock_lms_nrps_requires_a_token.py` asserts
its semantics in full — the four malformed credential shapes, the expired token, the
forged one, and what each challenge may say. Repeating all of that over six routes
would be thirty assertions about one function. What is asserted here is that the AGS
routes go **through** that door: one forged-token test, on one route, kills the
implementation that decodes a token and reads its `scope` without establishing who
signed it, and nothing else in this module can see that mutation. The boundary is
named rather than claimed away (`docs/MISTAKES.md` entry 14).

**No §4.1 invariant lives here**, for the reason the roster suite gives: the mock is
a platform, not a Pulse read path.
"""

import json
import re
import time
from typing import Any, NamedTuple
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fixtures.routing import every_route

pytestmark = pytest.mark.lti

# `mock_platform` and `key_the_tool_never_published` come from `tests/fixtures/` and
# are reached as fixtures rather than imported, for the reason every module in this
# suite gives: an import of a fixtures module by name depends on where pytest put
# `tests/` on `sys.path`, and an import error is not a red.

# The four scopes AGS 2.0 defines, and NRPS's, spelled as the specifications spell
# them. Transcribed rather than imported from `mock-lms/app/ags.py`, which is
# `docs/MISTAKES.md` entry 19: a module that reads its expectation out of the code
# under test holds two copies of one fact inside the blast radius of one change, and
# a scope renamed in both places would leave every assertion here green.
LINE_ITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
LINE_ITEM_READONLY_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
RESULT_READONLY_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"
SCORE_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"

# The media types AGS 2.0 fixes, sent on every call below — refused and accepted
# alike — so that the one thing differing between the halves of a pair is the
# credential.
LINE_ITEM_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitem+json"
LINE_ITEM_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitemcontainer+json"
RESULT_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.resultcontainer+json"
RESULT_MEDIA_TYPE = "application/vnd.ims.lis.v2.result+json"
SCORE_MEDIA_TYPE = "application/vnd.ims.lis.v1.score+json"

# RFC 6750's scheme, its two error codes, and the status each answers with.
BEARER_SCHEME = "Bearer"
INVALID_TOKEN = "invalid_token"  # noqa: S105 - an error code, not a credential
INSUFFICIENT_SCOPE = "insufficient_scope"
UNAUTHORIZED = 401
FORBIDDEN = 403

# One `parameter="value"` of an RFC 6750 §3 challenge. The quotes are the ABNF's
# rather than a convenience of this parser, and the parser is a parser rather than a
# substring search for the reason the NRPS module's copy gives at length: `"error"
# in header` answers yes to a challenge whose *description* mentions one.
CHALLENGE_PARAMETER = re.compile(r'(?P<name>[A-Za-z_-]+)\s*=\s*"(?P<value>[^"]*)"')

# The mock-only inspection route, spelled here as `tests/fixtures/lti_services.py`
# spells it and for the same reason its comment gives: a fixture that went looking
# for a route whose path carries "score" would find an AGS route, and the `/mock/`
# prefix is the one thing that rules that out. ADR 0047 fixes the path.
MOCK_POSTED_SCORES_PATH = "/mock/posted-scores"

# A context identifier nothing seeds, asserted absent from the seeded set before it
# is used so it cannot quietly become one of them.
A_CONTEXT_NOBODY_SEEDED = "a-context-nobody-seeded"
CONTEXT_NOT_FOUND_STATUS = 404

# The two paging parameters both AGS containers declare, and a value below the bound
# each carries in its route signature today. `page` is the cursor a walk moves by and
# `limit` is the page size a tool asks for; ADR 0099's consequence is that both
# bounds move out of the signature and behind the credential when AGS starts
# requiring one.
PAGE_PARAMETER = "page"
LIMIT_PARAMETER = "limit"
A_VALUE_BELOW_THE_BOUND = 0

# What an authenticated caller gets for a page that is not a page number. E0-28 item
# 2's code, which ADR 0099 already applied to the roster's cursor when its bound
# moved behind the credential: 400 says the platform read the request and will not
# serve it, and is deliberately not the 404 a page *past* the end answers with.
PAGE_REFUSAL_STATUS = 400

# The score this module posts, and the line item it posts against. §3.4's label and
# maximum, so nothing here invents a gradebook column; the values are the AGS suite's
# and are chosen to be ones no implementation arrives at by accident.
PULSE_LABEL = "Pulse Participation"
POSTED_MAXIMUM = 100
POSTED_SCORE = 61.5
POSTED_TIMESTAMP = "2026-03-02T14:05:09+00:00"

# A credential shape that is not a bearer token this platform issued. Deliberately
# not JWT-shaped: the JWT-shaped near miss is the forged-token test below.
A_TOKEN_NOBODY_ISSUED = "not-a-token-this-platform-ever-issued"  # noqa: S105 - a fake, by design

# The prefixes this platform serves without a credential, **by decision**. ADR 0047
# puts the posted-score readback outside the AGS namespace as an inspection surface no
# real platform serves, and ADR 0134 says out loud that the `/mock/` prefix is outside
# the enforcement so a reviewer can tell the decision from an oversight. This is that
# sentence as an allowlist, and the inventory guard at the foot of this module holds
# it to two properties: every entry is under `/mock/`, and nothing inside the AGS
# namespace is covered by it — so a new AGS route cannot be parked here.
TOKENLESS_BY_DECISION = ("/mock/",)

# One `{name}` or `{name:converter}` in a Starlette path template. `:path` is the
# converter that spans slashes, which `RESULT_PATH` uses so an LTI `sub` containing
# one still routes; every other parameter is a single segment. Both are needed, and a
# pattern that treated them alike would match a result URL against the container's
# own template and report a route as covered by the wrong row.
TEMPLATE_PARAMETER = re.compile(r"\{[^}]*\}")

# The HTTP methods a route's declaration carries that are not a route: Starlette adds
# `HEAD` to every `GET` and `OPTIONS` to everything, and neither is a surface this
# platform implements.
DERIVED_METHODS = ("HEAD", "OPTIONS")


# ---------------------------------------------------------------------------
# The six routes, addressed the way a tool addresses them.
# ---------------------------------------------------------------------------


class Route(NamedTuple):
    """One AGS route, its URL on this platform, and what opens it.

    `accepts` is the whole set of scopes ADR 0134 lets through, not one of them:
    two routes take either the line-item scope or its read-only sibling, and a
    check that implemented "the required scope" as a single string would serve
    them both while passing every single-scope test written the obvious way.
    """

    key: str
    description: str
    method: str
    url: str
    accepts: tuple[str, ...]
    accepted_status: int
    accept_media_type: str
    body: dict[str, Any] | None = None
    content_type: str | None = None


class Gradebook(NamedTuple):
    """The six addressed routes, and the context they live in."""

    context_id: str
    routes: dict[str, Route]


def line_item_body() -> dict[str, Any]:
    """SPEC §3.4's line item, with a `resourceId` nothing else in this run uses."""
    return {
        "scoreMaximum": POSTED_MAXIMUM,
        "label": PULSE_LABEL,
        "resourceId": f"e3-04-{uuid4().hex[:12]}",
        "tag": "participation",
    }


def score_body(user_id: str) -> dict[str, Any]:
    """One conformant AGS score for `user_id`, out of the line item's own maximum."""
    return {
        "userId": user_id,
        "timestamp": POSTED_TIMESTAMP,
        "activityProgress": "Completed",
        "gradingProgress": "FullyGraded",
        "scoreGiven": POSTED_SCORE,
        "scoreMaximum": POSTED_MAXIMUM,
    }


def gradebook(platform: Any) -> Gradebook:
    """Create the line item and the result every route below is addressed at.

    **A plain function called from a test body, never a fixture**, and
    `docs/MISTAKES.md` entry 44 is why: the setup here goes through the very
    enforcement under test, so an implementation that refuses a call it should serve
    would turn every red in this module into a setup ERROR — which proves nothing
    about the assertion the test exists to make and reads to a hurried eye as "the
    suite is red". Called in the body, the same failure arrives as a FAILED naming
    the accepted call that did not work.

    Everything is reached through the launch's own AGS claim rather than through a
    path, the way every module in this suite reaches a service: E0-15 spells no URL,
    so naming one here would assert against an interface the ticket left open.
    """
    contexts = platform.seeded_contexts()
    assert contexts, (
        "The launch page offers no launches, so no context advertises a line-items URL and there "
        "is nothing here to authorise a call against. E0-14 seeds the launches and E0-15 the "
        "gradebook behind them."
    )
    context = contexts[0]
    subjects = sorted(context.subjects)
    assert subjects, (
        f"The launches into {context.context_id!r} carry no `sub`, so there is no user to post a "
        "score for and the two result routes below cannot be addressed at all."
    )
    container = platform.line_items_url(context.launches[0])

    created = platform.create_line_item(context.launches[0])
    identifier = platform.line_item_id(created)
    posted = platform.post_score(created, score_body(subjects[0]))
    assert posted.status_code == 200, (
        f"Posting a score with a token granted for {SCORE_SCOPE!r} answered {posted.status_code} "
        f"rather than 200, so this module cannot build the result its two read routes address. "
        f"Body begins {posted.text[:300]!r}."
    )
    result_url = posted.json().get("resultUrl")
    assert isinstance(result_url, str) and result_url, (
        f"The Score service answered {posted.text[:300]!r}, which carries no `resultUrl`. AGS "
        "returns it so a tool can read back the result it caused, and it is the URL the "
        "single-result route below is addressed at."
    )

    routes = {
        "create_line_item": Route(
            key="create_line_item",
            description="creating a line item",
            method="POST",
            url=container,
            accepts=(LINE_ITEM_SCOPE,),
            accepted_status=201,
            accept_media_type=LINE_ITEM_MEDIA_TYPE,
            body=line_item_body(),
            content_type=LINE_ITEM_MEDIA_TYPE,
        ),
        "list_line_items": Route(
            key="list_line_items",
            description="listing a context's line items",
            method="GET",
            url=container,
            accepts=(LINE_ITEM_SCOPE, LINE_ITEM_READONLY_SCOPE),
            accepted_status=200,
            accept_media_type=LINE_ITEM_CONTAINER_MEDIA_TYPE,
        ),
        "read_line_item": Route(
            key="read_line_item",
            description="reading one line item at its own id",
            method="GET",
            url=identifier,
            accepts=(LINE_ITEM_SCOPE, LINE_ITEM_READONLY_SCOPE),
            accepted_status=200,
            accept_media_type=LINE_ITEM_MEDIA_TYPE,
        ),
        "post_score": Route(
            key="post_score",
            description="posting a score to a line item",
            method="POST",
            url=platform.scores_url(created),
            accepts=(SCORE_SCOPE,),
            accepted_status=200,
            accept_media_type=SCORE_MEDIA_TYPE,
            body=score_body(subjects[0]),
            content_type=SCORE_MEDIA_TYPE,
        ),
        "read_results": Route(
            key="read_results",
            description="reading a line item's result container",
            method="GET",
            url=platform.results_url(created),
            accepts=(RESULT_READONLY_SCOPE,),
            accepted_status=200,
            accept_media_type=RESULT_CONTAINER_MEDIA_TYPE,
        ),
        "read_result": Route(
            key="read_result",
            description="reading one user's result at the URL the platform handed back",
            method="GET",
            url=result_url,
            accepts=(RESULT_READONLY_SCOPE,),
            accepted_status=200,
            accept_media_type=RESULT_MEDIA_TYPE,
        ),
    }
    return Gradebook(context_id=context.context_id, routes=routes)


EVERY_ROUTE = (
    "create_line_item",
    "list_line_items",
    "read_line_item",
    "post_score",
    "read_results",
    "read_result",
)

# The two containers whose route signatures carry a `ge=1` bound today, which is
# what ADR 0099's consequence says moves behind the credential.
PAGED_CONTAINERS = ("list_line_items", "read_results")


def send(platform: Any, route: Route, credential: str | None, url: str | None = None) -> Any:
    """Issue one raw call at `route`, carrying `credential` as its `Authorization`.

    Deliberately **not** `MockPlatform`'s AGS helpers: those attach a working token
    for the route's own scope, which is the whole of what these tests vary. Every
    other header — the media type asked for, the media type sent — is identical
    between a refused call and an accepted one, so the credential is the only
    difference a refusal could be about.
    """
    headers: dict[str, str] = {"accept": route.accept_media_type}
    if credential is not None:
        headers["authorization"] = credential
    target = platform.local(route.url if url is None else url)
    if route.method == "POST":
        headers["content-type"] = str(route.content_type)
        return platform.client.post(target, content=json.dumps(route.body or {}), headers=headers)
    return platform.client.get(target, headers=headers)


def template_pattern(template: str) -> re.Pattern[str]:
    """One Starlette path template as a pattern matching the URLs it routes.

    Everything outside a `{…}` is matched literally; a plain parameter matches one
    segment and a `:path` parameter matches across slashes, which is the distinction
    `RESULT_PATH` rests on. Anchored at both ends, because an unanchored pattern
    reports the container's template as matching every URL beneath it and the
    inventory below would then find every route covered by one row.
    """
    parts: list[str] = []
    last = 0
    for found in TEMPLATE_PARAMETER.finditer(template):
        parts.append(re.escape(template[last : found.start()]))
        parts.append(".+" if ":path" in found.group() else "[^/]+")
        last = found.end()
    parts.append(re.escape(template[last:]))
    return re.compile(f"^{''.join(parts)}$")


def declared_routes(platform: Any) -> list[tuple[str, str]]:
    """Every `(method, path template)` the running mock platform declares.

    Read off the application rather than from a list in this file, which is the whole
    point of the guard that uses it: an inventory written by hand cannot see a route
    that was added after it was written. `every_route` is
    `tests/fixtures/routing.py`'s walk and it recurses into included routers — the
    mock registers with decorators today, and a walk that read `application.routes`
    directly would go blind the day it grows a router and report an empty namespace
    as a covered one.

    `HEAD` and `OPTIONS` are dropped: Starlette derives them, and neither is a
    surface this platform implements or a token could be required on.
    """
    found: set[tuple[str, str]] = set()
    for route in every_route(platform.application):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not isinstance(path, str) or not methods:
            continue
        for method in methods:
            if str(method).upper() not in DERIVED_METHODS:
                found.add((str(method).upper(), path))
    return sorted(found)


def ags_namespace(declared: list[tuple[str, str]], container_path: str) -> str:
    """The path template the line-item container is served at, found by what it routes.

    Derived rather than transcribed: the container's address comes from the launch's
    own AGS endpoint claim, and the template is whichever declaration routes it. Every
    other AGS route on this platform is addressed beneath that template — a line item
    is inside the container, and the Score and Result services are inside the line
    item — so it is also the prefix that names the namespace.

    Ambiguity stops rather than picks, the contract every discovery in this suite
    keeps: two templates routing one URL means this cannot say which one is the
    container, and choosing would be the test deciding.
    """
    matching = sorted(
        {path for _method, path in declared if template_pattern(path).match(container_path)}
    )
    assert len(matching) == 1, (
        f"{len(matching)} declared templates route the line-item container {container_path!r} "
        f"({matching}); this platform declares {sorted({path for _m, path in declared})}. The "
        "namespace below is derived from the one that does, so with none there is nothing to "
        "enumerate and with two there is no saying which."
    )
    return matching[0]


def challenge_parameters(challenge: str) -> dict[str, str]:
    """Every `name="value"` an RFC 6750 §3 challenge carries. See the control below."""
    return {
        found.group("name").lower(): found.group("value")
        for found in CHALLENGE_PARAMETER.finditer(challenge)
    }


def bearer_challenge(response: Any, subject: str, control: str) -> str:
    """The `WWW-Authenticate` header on a refusal, required to name `Bearer`.

    Asserted beside the status rather than the status alone, and it is what makes a
    refusal non-vacuous: a 401 with no challenge is indistinguishable to a client
    from a route that has gone wrong, RFC 7235 §3.1 requires the header on a 401 at
    all, and `Bearer` is what tells a tool *which* credential to go and get.
    """
    challenge = response.headers.get("www-authenticate")
    assert isinstance(challenge, str) and challenge.strip(), (
        f"{subject} was answered {response.status_code} with no `WWW-Authenticate` header. "
        f"{control} RFC 7235 §3.1 requires the header on a 401 and RFC 6750 §3 makes it the "
        "challenge that names the scheme, which is how a tool learns it needs a bearer token "
        "rather than that the gradebook has moved. A bare 401 is indistinguishable from a 404."
    )
    scheme = challenge.split(None, 1)[0]
    assert scheme.lower() == BEARER_SCHEME.lower(), (
        f"{subject} was challenged with {challenge!r}, whose scheme is {scheme!r} rather than "
        f"{BEARER_SCHEME!r}. {control} RFC 6750 §3 makes the challenge for a resource that takes "
        "an access token a `Bearer` challenge; any other scheme sends a conformant tool looking "
        "for a credential this platform does not issue."
    )
    return challenge


def accepted(platform: Any, route: Route, credential: str, subject: str) -> Any:
    """The authorised call every refusal is posed against, required to succeed.

    Without it a refusal could be the platform refusing every AGS call — which
    satisfies every refusal in this module and serves nothing (`docs/MISTAKES.md`
    entry 3) — and it is also criterion 6's own third of the triple.
    """
    response = send(platform, route, credential)
    assert response.status_code == route.accepted_status, (
        f"{subject} answered {response.status_code} rather than {route.accepted_status}, so the "
        "call this test poses its refusal against does not itself work and the refusal would say "
        f"nothing about what was refused. Body begins {response.text[:300]!r}."
    )
    return response


def refused(
    platform: Any,
    route: Route,
    credential: str | None,
    *,
    status: int,
    code: str | None,
    subject: str,
    control: str,
    url: str | None = None,
) -> None:
    """Assert one call is refused, with the status and the RFC 6750 code that say why.

    The code is asserted rather than the status alone wherever the contract states
    one. 401 and 403 are two different instructions to a client — go and get a
    credential, versus the credential you hold will never reach this — and a platform
    answering one code for every refusal tells a tool neither.

    **`code=None` asserts the challenge carries no `error` parameter at all**, which
    is RFC 6750 §3.1's own rule: nothing was presented for this route to have found
    fault with, and naming a code tells a caller who presented nothing what the route
    would have objected to. There is deliberately **no "do not check" mode**, for the
    reason the NRPS module's copy of this helper records: an implementation that
    stamps `error="invalid_token"` on every challenge survives a helper that can be
    asked to skip the check.
    """
    response = send(platform, route, credential, url=url)
    assert response.status_code == status, (
        f"{subject} answered {response.status_code} rather than {status}. {control} Body begins "
        f"{response.text[:300]!r}."
    )
    challenge = bearer_challenge(response, subject, control)
    parameters = challenge_parameters(challenge)
    if code is None:
        assert "error" not in parameters, (
            f"{subject} was challenged with {challenge!r}, which states `error` "
            f"{parameters.get('error')!r}. This request presented nothing this route reads as a "
            "bearer credential, so there is no token it has found fault with — RFC 6750 §3.1 says "
            "a request carrying no authentication SHOULD NOT be answered with an error code. A "
            "challenge that names one tells a caller who presented nothing what this route would "
            "have objected to, and it makes 'you sent no credential' indistinguishable from 'the "
            "one you sent is bad'."
        )
        return
    assert parameters.get("error") == code, (
        f"{subject} was challenged with {challenge!r}, whose `error` is "
        f"{parameters.get('error')!r} rather than {code!r}. {control} RFC 6750 §3.1 is the only "
        f"place these strings are defined and it is the parameter a client reads: {INVALID_TOKEN!r} "
        f"means 'get a new credential' and {INSUFFICIENT_SCOPE!r} means 'ask for a different "
        "scope', and a refusal that states neither leaves a tool retrying the thing that will not "
        "work."
    )


def advertised_scopes(platform: Any) -> list[str]:
    """Every scope this platform says a token may be requested for."""
    document = platform.discovery() or {}
    scopes = document.get("scopes_supported")
    assert isinstance(scopes, list) and all(isinstance(scope, str) for scope in scopes), (
        f"The discovery document's `scopes_supported` is {scopes!r} rather than a list of strings "
        f"(it carries {sorted(document)}). E1-06 puts the service scopes there, and without it "
        "this module cannot ask for a token carrying a scope a route does not accept."
    )
    return list(scopes)


def claims_of(token: str, subject: str) -> dict[str, Any]:
    """`token`'s claims, read without verifying anything.

    Used only by this module's controls, which ask what a token *says* rather than
    whether it is good: the platform is the only thing entitled to answer the second
    question, and a test that verified a token here would be checking the mock's
    arithmetic with a second copy of it.
    """
    import jwt

    try:
        return dict(
            jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
            )
        )
    except Exception as failure:
        pytest.fail(
            f"{subject} is not a JWT this suite can read ({type(failure).__name__}: {failure}). "
            "E1-06 mints an access token as a signed JWS so that a service can check one with "
            "nothing remembered, and the forged-token control below rests on being able to read "
            "what a token states."
        )


def forged_access_token(platform: Any, stranger: Any, scope: str) -> str:
    """An access token that says everything a granted one says, signed by nobody's key.

    Every value is read off the platform rather than transcribed — the issuer and
    audience out of its discovery document, the subject out of the client id its
    launch form publishes, the `kid` out of the key set it serves. The `kid` in
    particular is the platform's own, which is the near miss for an implementation
    that selects a key by the header's `kid` and then trusts the token because a key
    was found.

    **A second copy of the NRPS module's builder, and the duplication is deliberate.**
    The two modules share no import path — a test module that imported another test
    module by name would depend on where pytest put `tests/` on `sys.path` — and the
    twin control below is what keeps this copy honest about being a twin.
    """
    import uuid

    document = platform.discovery() or {}
    issuer = document.get("issuer")
    assert isinstance(issuer, str) and issuer, (
        f"The discovery document states no `issuer` (it carries {sorted(document)}), so a forged "
        "token cannot claim to have come from this platform and its refusal would be about a token "
        "that is wrong in two ways."
    )
    client_id = platform.require_offers()[0].parameters.get("client_id")
    assert isinstance(client_id, str) and client_id, (
        "The launch form publishes no `client_id`, so a forged token cannot name the subject a "
        "granted one names."
    )
    published = platform.published_keys()
    assert published, "The platform publishes no keys, so there is no `kid` to forge a header with."

    issued = int(time.time())
    return stranger.sign(
        {
            "iss": issuer,
            "sub": client_id,
            "aud": issuer,
            "jti": uuid.uuid4().hex,
            "iat": issued,
            "exp": issued + 3600,
            "scope": scope,
        },
        kid=str(published[0].get("kid") or ""),
    )


# ---------------------------------------------------------------------------
# Controls on this module's own machinery. **A red in this section means these
# tests are broken, not the mock platform**, and every refusal below is then
# reporting nothing.
# ---------------------------------------------------------------------------


def test_the_challenge_reader_finds_the_error_code_and_not_a_mention_of_it() -> None:
    """The parser every refusal here is read through, run against both texts.

    `docs/MISTAKES.md` entry 3: a pattern searched against text is a test passing for
    a reason unrelated to what it asserts, wearing a disguise — so it is run against
    the text it is claimed to catch *and* the text it is claimed to allow. A reader
    that answered `{}` for everything would make every code assertion in this module
    fail for a reason that is this file's; a reader that matched a substring would
    pass a challenge whose `error` says one thing and whose prose mentions another.

    The two bare-challenge rows are load-bearing rather than tidiness: the
    missing-credential half of every triple asserts that a challenge carries *no*
    `error`, and an absence found by a reader that cannot find a presence is not an
    absence (`docs/MISTAKES.md` entry 35).

    **A red here means these tests are broken, not the mock platform.**
    """
    found = challenge_parameters(
        'Bearer realm="pulse-mock-lms", error="invalid_token", '
        'error_description="the token expired at 1"'
    )
    assert found.get("error") == INVALID_TOKEN
    assert found.get("realm") == "pulse-mock-lms"
    assert found.get("error_description") == "the token expired at 1"

    described = challenge_parameters(
        f'Bearer error="{INSUFFICIENT_SCOPE}", '
        f'error_description="this is not an {INVALID_TOKEN}, the scope is wrong"'
    )
    assert described.get("error") == INSUFFICIENT_SCOPE, (
        "The reader took an error code out of the human-readable description rather than out of "
        "the `error` parameter, so a platform answering the right status with the wrong code would "
        "be read as correct."
    )

    assert challenge_parameters("Bearer") == {}
    assert challenge_parameters("") == {}


def test_the_line_item_read_only_scope_contains_the_line_item_scope_as_a_prefix() -> None:
    """The premise the superstring pair rests on, checked against the two strings.

    The carried entry's whole claim is that these two specification constants stand
    in a containment relation, so a scope check written as a substring test cannot
    tell them apart. If IMS ever spelled them so that one is not a prefix of the
    other, the pair below would still pass and would be proving nothing — it would be
    an ordinary wrong-scope test wearing the carried entry's name.

    **A red here means these tests are broken, not the mock platform** — or the
    constants at the top of this file have been mistyped, which is the same finding.
    """
    assert LINE_ITEM_READONLY_SCOPE.startswith(LINE_ITEM_SCOPE), (
        f"{LINE_ITEM_READONLY_SCOPE!r} does not begin with {LINE_ITEM_SCOPE!r}, so a check written "
        "as a substring or a prefix test would already tell the two apart and the superstring pair "
        "below would assert nothing about membership."
    )
    assert LINE_ITEM_READONLY_SCOPE != LINE_ITEM_SCOPE, (
        "The two scope constants are the same string, so no token can carry one without the other "
        "and neither half of the pair below is expressible."
    )


def test_the_six_routes_this_module_drives_are_six_different_addresses(
    mock_platform: Any,
) -> None:
    """The route table, checked before any triple is believed of it.

    Every test below is parametrised over `EVERY_ROUTE` and reads its URL out of
    `gradebook`. Two entries resolving to one address — a `results_url` that came
    back as the line item's own id, a `scores_url` that concatenated instead of
    inserting — would silently turn six routes into four, and every refusal would
    still be green because a refusal is a refusal wherever it lands
    (`docs/MISTAKES.md` entry 3).

    The method is part of the identity: `POST …/line_items` and `GET …/line_items`
    are one URL and two routes, which is exactly why the pair is `(method, url)`.

    **A red here means these tests are broken, not the mock platform.**
    """
    routes = gradebook(mock_platform).routes
    assert sorted(routes) == sorted(EVERY_ROUTE), (
        f"`gradebook` addressed {sorted(routes)} and this module parametrises over "
        f"{sorted(EVERY_ROUTE)}. Criterion 6 is 'all three, per route', so a route missing from "
        "the table is a route with no enforcement test at all."
    )
    addressed = [(route.method, route.url) for route in routes.values()]
    assert len(set(addressed)) == len(addressed), (
        f"The route table addresses {addressed}, which carries a duplicate: two entries reach one "
        "endpoint, so one of the six routes is untested and its triple is being answered by "
        "another route's enforcement."
    )


def test_the_platform_grants_a_token_for_every_scope_this_module_presents(
    mock_platform: Any,
) -> None:
    """The credential machinery every accepted half rests on, exercised once.

    `MockPlatform.ags_token` is new. If it handed back a string it invented, or one
    obtained some way the platform does not sanction, every accepted call in this
    module would fail and every refusal would pass — a module reporting a conformant
    platform having proved nothing (`docs/MISTAKES.md` entry 35).

    Two things say each grant is real, and the second cannot be faked from this side:
    the response carries RFC 6749 §5.1's `token_type` and the scope that was asked
    for, **and** the platform fetched the tool's key set while verifying the
    assertion. A helper that minted a token locally would fetch nothing.

    **A red here means these tests are broken, not the mock platform.**
    """
    for scope in (LINE_ITEM_SCOPE, LINE_ITEM_READONLY_SCOPE, RESULT_READONLY_SCOPE, SCORE_SCOPE):
        before = len(mock_platform.tool_key_set.requested)
        granted = mock_platform.service_token_grant(scope)

        token = granted.get("access_token")
        assert isinstance(token, str) and token, (
            f"The grant for {scope!r} answered {granted!r}, which carries no `access_token`, so "
            "every accepted call presenting it is about an empty credential."
        )
        assert str(granted.get("token_type", "")).lower() == BEARER_SCHEME.lower(), (
            f"The grant for {scope!r} states `token_type` {granted.get('token_type')!r} rather "
            f"than {BEARER_SCHEME!r}, so this suite presents the token under a scheme the platform "
            "did not issue it for."
        )
        assert scope in str(granted.get("scope", "")).split(), (
            f"A token was asked for {scope!r} and granted with `scope` {granted.get('scope')!r}, "
            "so the credential the accepted halves present is not the one they say it is."
        )
        assert len(mock_platform.tool_key_set.requested) > before, (
            f"The platform granted a token for {scope!r} without fetching the tool's key set, so "
            "either it verified nothing — which `test_mock_lms_client_credentials_grant.py` "
            "diagnoses — or this helper never went through the platform's endpoint and the "
            "credential it returns is its own invention."
        )


def test_the_forged_token_this_module_builds_is_a_twin_of_a_granted_one(
    mock_platform: Any,
    key_the_tool_never_published: Any,
) -> None:
    """The forged credential, checked against a real one before a refusal rests on it.

    The forged-token test below claims the platform refuses a token *because of who
    signed it*. That claim is worth something only if the forgery is otherwise
    indistinguishable: a token that also named the wrong issuer, carried the wrong
    scope, or had already expired would be refused by a platform checking any one of
    those, and the test would read that as a signature check
    (`docs/MISTAKES.md` entry 3).

    **A red here means these tests are broken, not the mock platform.**
    """
    granted = str(mock_platform.service_token_grant(SCORE_SCOPE)["access_token"])
    forged = forged_access_token(mock_platform, key_the_tool_never_published, SCORE_SCOPE)

    real_claims = claims_of(granted, "The token the platform granted")
    forged_claims = claims_of(forged, "The token this module forged")

    assert set(forged_claims) >= set(real_claims) - {"jti"}, (
        f"The forged token states {sorted(forged_claims)} and a granted one states "
        f"{sorted(real_claims)}. A claim the platform puts in and this forgery leaves out is a "
        "second thing the refusal could be about."
    )
    for claim in ("iss", "aud", "sub", "scope"):
        assert forged_claims.get(claim) == real_claims.get(claim), (
            f"The forged token states `{claim}` {forged_claims.get(claim)!r} and a granted one "
            f"states {real_claims.get(claim)!r}. The forgery has to agree with a real token about "
            "everything except who signed it."
        )
    assert float(forged_claims.get("exp", 0)) > time.time(), (
        f"The forged token expired at {forged_claims.get('exp')!r} and it is now "
        f"{int(time.time())}, so a platform refusing it would be refusing an expired token and the "
        "signature would never be reached."
    )
    assert granted.rsplit(".", 1)[-1] != forged.rsplit(".", 1)[-1], (
        "The forged token and the granted one carry the same signature, so the two keys this "
        "module uses are one key and the refusal that rests on them is about nothing."
    )


# ---------------------------------------------------------------------------
# Criterion 6, third of the triple — the right scope is accepted. **These must be
# green before this ticket lands and green after it.**
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route_key", EVERY_ROUTE)
def test_every_ags_route_accepts_a_token_granted_for_a_scope_it_takes(
    mock_platform: Any, route_key: str
) -> None:
    """Criterion 6's accepted half, over **every** scope the route takes.

    **Green before this ticket and green after it**, which is what makes it the
    control: it says the harness's credential reaches the route and parses there, so
    that the two refusals beside it are statements about the credential rather than
    about a platform that refuses everything (`docs/MISTAKES.md` entry 35). **A red
    here means these tests are broken, not the mock.**

    **The mutation this kills is not "no enforcement".** It is the any-of rule
    implemented as one required scope: two routes take the line-item scope *or* its
    read-only sibling, and a check comparing against a single string serves a tool
    holding the other one a 403. Every scope in `accepts` is presented in turn, so
    the narrower implementation is red on one row and green on the rest — which is
    also why this is a loop rather than one call with the first scope.

    The response body is asserted to be the document the route serves, not only the
    status: an enforcement that answered 200 with an empty body would satisfy a
    status check while having broken the route it guards.
    """
    routes = gradebook(mock_platform).routes
    route = routes[route_key]
    for scope in route.accepts:
        response = accepted(
            mock_platform,
            route,
            f"{BEARER_SCHEME} {mock_platform.ags_token(scope)}",
            f"A call {route.description} presenting a token granted for {scope!r}",
        )
        assert response.content, (
            f"A call {route.description} with a token granted for {scope!r} answered "
            f"{response.status_code} with an empty body. The status alone is satisfied by an "
            "enforcement that lets the request through and leaves nothing for the handler to "
            "serve, which is a working credential check on a broken route."
        )


# ---------------------------------------------------------------------------
# Criterion 6, first of the triple — an absent or unreadable credential is 401
# with a bare `Bearer` challenge.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route_key", EVERY_ROUTE)
def test_every_ags_route_refuses_a_call_carrying_no_authorization_header(
    mock_platform: Any, route_key: str
) -> None:
    """Criterion 6's first line, and the state of every one of these routes at HEAD.

    **The mutation this kills:** no enforcement at all, which is what the mock does
    today — `mock-lms/app/main.py`'s Advantage comment says so in as many words, and
    ADR 0099 records the argument that kept it that way until an AGS client existed.
    Anything that can reach these URLs writes a gradebook column and posts a grade
    into it.

    **The near misses it is written around.** A 404 would also stop the call and
    would tell a tool the gradebook is not there, sending its author looking for the
    URL rather than for a credential; a 403 would tell it the credential it does not
    have would not have helped. Both are excluded by asserting the status and the
    `WWW-Authenticate` challenge together.

    **The challenge is required to name no error code**, which is RFC 6750 §3.1's own
    rule — nothing was presented for this route to find fault with — and it kills a
    second mutation: an implementation that stamps `error="invalid_token"` on every
    challenge, which tells a caller who presented nothing what the route would have
    objected to.

    The authorised call comes first and is the same one the control above makes, so a
    platform that refuses everything cannot satisfy this test.
    """
    routes = gradebook(mock_platform).routes
    route = routes[route_key]
    accepted(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(route.accepts[0])}",
        f"A call {route.description} presenting a token granted for {route.accepts[0]!r}",
    )

    refused(
        mock_platform,
        route,
        None,
        status=UNAUTHORIZED,
        code=None,
        subject=f"A call {route.description} carrying no `Authorization` header at all",
        control=(
            f"The identical call presenting a token granted for {route.accepts[0]!r} was answered "
            f"{route.accepted_status} a moment ago,"
        ),
    )


@pytest.mark.parametrize("route_key", EVERY_ROUTE)
def test_every_ags_route_refuses_a_credential_that_is_not_a_bearer_token(
    mock_platform: Any, route_key: str
) -> None:
    """The malformed half of the same line, over the shapes a fail-open check accepts.

    **The mutations these kill, one per shape**, and they are the four
    `app.tokens::presented_credential` names:

      - `Basic …` with junk: an enforcement written as `"authorization" in
        request.headers`, which is the cheapest thing that passes the test above and
        authorises anybody who sends any header at all.
      - a granted token under `Basic`: the near miss, and the reason that shape is
        here. A check that takes the last whitespace-separated word of the header
        reads a perfectly good token out of a scheme this platform issues nothing
        for, and every other case in this module stays green.
      - `Bearer` with nothing after it: a check that splits on a space without asking
        whether anything followed, which then looks a token up by the empty string.
      - the bare token with no scheme: a check treating the whole header value as the
        credential, which accepts a client that forgot the scheme and would accept
        the same value dressed as anything else.

    Each carries **no** error code, per RFC 6750 §3.1: a credential this route cannot
    read as a bearer token is one it has found no fault with, because it never got as
    far as looking.
    """
    routes = gradebook(mock_platform).routes
    route = routes[route_key]
    token = mock_platform.ags_token(route.accepts[0])
    accepted(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {token}",
        f"A call {route.description} presenting that token under the `Bearer` scheme",
    )

    for credential, description in (
        ("Basic cHVsc2U6bm90LWEtdG9rZW4=", "a `Basic` credential"),
        (f"Basic {token}", "a granted token presented under the `Basic` scheme"),
        (f"{BEARER_SCHEME} ", "a `Bearer` scheme with no credential after it"),
        (token, "a granted token with no scheme in front of it"),
    ):
        refused(
            mock_platform,
            route,
            credential,
            status=UNAUTHORIZED,
            code=None,
            subject=f"A call {route.description} carrying {description}",
            control=(
                "The identical call presenting the same token as `Bearer <token>` was answered "
                f"{route.accepted_status} a moment ago,"
            ),
        )


def test_an_ags_route_refuses_a_token_this_platform_did_not_sign(
    mock_platform: Any,
    key_the_tool_never_published: Any,
) -> None:
    """The AGS routes go through the same door NRPS does, and this is what says so.

    **The mutation this kills:** an enforcement that decodes the presented token and
    reads its `scope` claim without establishing that this platform issued it. That
    is the cheapest implementation which passes every other test in this module — the
    header is well formed, the token is a readable JWT, the scope is right — and it
    authorises anybody who can write a JSON object. E1-06's argument for a *signed*
    access token was exactly this: a service can check one with nothing remembered,
    and the whole of that rests on the signature being verified.

    It also kills the narrower version that selects a key by the header's `kid` and
    trusts the token because a key was found: the forgery carries the platform's own
    published `kid`, and its signature is a real RS256 signature by a real key rather
    than a corrupted one — a mangled signature is refused by a verifier that does no
    key selection at all, and this test would read that as verification working.

    **One route, deliberately.** `app.tokens::authorised_token` is one door and
    `test_mock_lms_nrps_requires_a_token.py` asserts its semantics in full; what is
    open here is whether the AGS routes go through it, and a token nobody signed
    answers that on any one of them. The score post is the route chosen because it is
    the one that writes a grade.
    """
    routes = gradebook(mock_platform).routes
    route = routes["post_score"]
    accepted(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(SCORE_SCOPE)}",
        "A score post presenting a token this platform signed",
    )

    forged = forged_access_token(mock_platform, key_the_tool_never_published, SCORE_SCOPE)
    refused(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {forged}",
        status=UNAUTHORIZED,
        code=INVALID_TOKEN,
        subject=(
            "A score post presenting a token that states everything a granted one states, carries "
            "the platform's own `kid`, and is signed by a key the platform does not have"
        ),
        control=(
            "The identical post presenting a token this platform actually signed was answered 200 "
            "a moment ago,"
        ),
    )

    refused(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {A_TOKEN_NOBODY_ISSUED}",
        status=UNAUTHORIZED,
        code=INVALID_TOKEN,
        subject=f"A score post presenting the string {A_TOKEN_NOBODY_ISSUED!r} as a bearer token",
        control=(
            "The identical post presenting a token this platform granted was answered 200 a moment "
            "ago,"
        ),
    )


# ---------------------------------------------------------------------------
# Criterion 6, second of the triple — a good credential for the wrong thing is
# 403, `insufficient_scope`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route_key", EVERY_ROUTE)
def test_every_ags_route_refuses_a_token_granted_for_a_scope_it_does_not_accept(
    mock_platform: Any, route_key: str
) -> None:
    """Criterion 6's second line, over every other scope this platform advertises.

    **The mutations this kills.** An enforcement that establishes the token is one
    this platform issued and never reads what it was issued *for*: the token endpoint
    grants every advertised scope to the same client on request, so a score route
    behind a scope-blind check is a gradebook any roster token writes to. And,
    narrower, an enforcement that requires the token to carry *some* scope, which
    every row here satisfies.

    **Every advertised scope the route does not accept is asked, rather than a chosen
    couple** (`docs/MISTAKES.md` entry 15): the platform's own `scopes_supported` is
    the set, so a scope added to that list later is covered the day it is added
    rather than being the one case a hand-written parametrisation missed. The
    membership scope is among them, which is the cross-service half — a roster token
    must not open a gradebook.

    403 rather than 401, per RFC 6750 §3.1, and the difference is the whole point of
    stating a code: the credential is good and will never reach this, so a client
    retrying with a fresh token of the same scope would loop forever.
    """
    routes = gradebook(mock_platform).routes
    route = routes[route_key]
    advertised = advertised_scopes(mock_platform)
    for scope in route.accepts:
        assert scope in advertised, (
            f"The platform advertises {advertised!r} and not {scope!r}, so no token can be "
            "requested for this route at all and its accepted half is unreachable. E1-06 adds the "
            "service scopes; `test_mock_lms_client_credentials_grant.py` diagnoses their absence."
        )
    others = [scope for scope in advertised if scope not in route.accepts]
    assert others, (
        f"The platform advertises only {advertised!r}, and this route accepts all of them, so "
        "there is no scope a token can be granted for that fails to open it and this test cannot "
        "pose its question."
    )

    accepted(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(route.accepts[0])}",
        f"A call {route.description} presenting a token granted for {route.accepts[0]!r}",
    )

    for scope in others:
        refused(
            mock_platform,
            route,
            f"{BEARER_SCHEME} {mock_platform.ags_token(scope)}",
            status=FORBIDDEN,
            code=INSUFFICIENT_SCOPE,
            subject=f"A call {route.description} presenting a token granted for {scope!r}",
            control=(
                f"The identical call presenting a token granted for {route.accepts[0]!r} was "
                f"answered {route.accepted_status} a moment ago, so the platform does serve this "
                "route,"
            ),
        )


@pytest.mark.parametrize("route_key", EVERY_ROUTE)
def test_every_ags_route_accepts_a_token_carrying_its_scope_beside_another(
    mock_platform: Any, route_key: str
) -> None:
    """The accepted half the wrong-scope test cannot pose, and the mutation it kills.

    **The mutation:** a scope check written as equality against the whole `scope`
    claim — `granted == required` — rather than membership of the space-delimited
    list RFC 6749 §3.3 defines. It passes every other test in this module: a
    single-scope token is accepted and every wrong-scope token is refused. What it
    breaks is a real client, because `pylti1p3` asks its token endpoint for whichever
    scopes the launch's service claims advertise, and this launch's AGS claim
    advertises four — so a tool that will list line items and post grades holds one
    token carrying both.

    The grant is asserted to have carried both scopes before the call is believed: a
    platform that quietly dropped one would make this an assertion about a
    single-scope token, which the test above already makes.

    **Green before this ticket and after it**, like the other accepted halves.
    """
    routes = gradebook(mock_platform).routes
    route = routes[route_key]
    wanted = route.accepts[0]
    advertised = advertised_scopes(mock_platform)
    others = [scope for scope in advertised if scope not in route.accepts]
    assert others, (
        f"The platform advertises only {advertised!r} and this route accepts all of them, so no "
        "token can carry its scope *beside* another and the equality mutation is not expressible."
    )
    beside = others[0]

    granted = mock_platform.service_token_grant(f"{beside} {wanted}")
    carried = str(granted.get("scope", "")).split()
    assert {beside, wanted} <= set(carried), (
        f"A token was asked for {beside!r} and {wanted!r} together and granted with `scope` "
        f"{granted.get('scope')!r}. A platform that dropped one leaves this test presenting a "
        "single-scope token, which says nothing about how a route reads a list."
    )

    accepted(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {granted['access_token']}",
        f"A call {route.description} presenting a token granted for {beside!r} and {wanted!r}",
    )


# ---------------------------------------------------------------------------
# Criterion 7 — the superstring pair. The carried entry's own proof, and it
# becomes available for the first time in this ticket.
# ---------------------------------------------------------------------------


def test_a_line_item_read_only_token_is_refused_where_the_line_item_scope_is_required(
    mock_platform: Any,
) -> None:
    """The carried entry's refused half: the granted string *contains* the required one.

    `…/scope/lineitem.readonly` has `…/scope/lineitem` as a prefix, so this is the one
    refusal in the repository that a substring check cannot answer correctly. The
    mutations it kills, and each passes every other test in this module:

      - `required_scope in claims["scope"]` — the whole claim searched as a string,
        which finds `lineitem` inside `lineitem.readonly`;
      - `any(granted.startswith(required) for granted in scopes)` — the same error
        one level in, over the split list;
      - `granted.split(required)` or any other prefix arithmetic on the scope URIs.

    Each of those hands a tool holding only the *read-only* line-item scope the
    ability to create a gradebook column. The rule the platform has to implement is
    membership of the space-delimited list RFC 6749 §3.3 defines, and membership is
    the only thing that gets this row and its pair both right.

    **The pair is the test below**, where the same route is asked with the writing
    scope and must accept — without it, "the read-only token is refused" is satisfied
    by a route that refuses every token, and the whole pair says nothing about which
    string was compared.

    The containment premise is checked by
    `test_the_line_item_read_only_scope_contains_the_line_item_scope_as_a_prefix`, so
    a mistyped constant is a red naming the constant rather than an ordinary
    wrong-scope test wearing this name.
    """
    routes = gradebook(mock_platform).routes
    route = routes["create_line_item"]
    assert route.accepts == (LINE_ITEM_SCOPE,), (
        f"The create route is recorded as accepting {route.accepts!r}. ADR 0134 gives it the "
        f"writing scope alone — if it accepted {LINE_ITEM_READONLY_SCOPE!r} too, a read-only "
        "credential creating a gradebook column would be the platform's own rule and this pair "
        "would be asserting against the table rather than against the check."
    )

    accepted(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(LINE_ITEM_SCOPE)}",
        f"Creating a line item with a token granted for {LINE_ITEM_SCOPE!r}",
    )

    refused(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(LINE_ITEM_READONLY_SCOPE)}",
        status=FORBIDDEN,
        code=INSUFFICIENT_SCOPE,
        subject=(
            f"Creating a line item with a token granted only for {LINE_ITEM_READONLY_SCOPE!r}, "
            f"which contains {LINE_ITEM_SCOPE!r} as a prefix"
        ),
        control=(
            "The identical request presenting the writing scope was answered 201 a moment ago, so "
            "the route creates line items and this refusal is about the scope,"
        ),
    )


def test_a_line_item_token_creates_a_line_item_the_container_then_lists(
    mock_platform: Any,
) -> None:
    """The carried entry's accepted half, asserted past the status code.

    The pair to the refusal above. A route that refused every credential satisfies
    that one completely, so this is the half that says the writing scope *works* —
    and it says it by looking at the gradebook rather than at a 201: the created line
    item is required to appear in the container afterwards, because an enforcement
    that let the request through and left the handler unable to store anything would
    answer 201 and create nothing.

    **The mutation this kills:** the scope check made strict enough to satisfy the
    refusal above by refusing everything — the safest-looking repair, and the one
    that turns off grade passback entirely.

    The container is read with the read-only scope, which is the same credential the
    refusal above was refused with: so this test also says that token is not simply
    broken, and the two rows together say the platform tells the *scopes* apart
    rather than the tokens.
    """
    routes = gradebook(mock_platform).routes
    route = routes["create_line_item"]

    response = accepted(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(LINE_ITEM_SCOPE)}",
        f"Creating a line item with a token granted for {LINE_ITEM_SCOPE!r}",
    )
    created = response.json()
    resource_id = (route.body or {}).get("resourceId")
    assert isinstance(created, dict) and created.get("id"), (
        f"Creating a line item answered {created!r}, which carries no `id`. AGS makes the `id` the "
        "platform's own URL for the line item, and without it there is nothing to look for below."
    )

    listed = mock_platform.ags_get(
        route.url,
        accept=LINE_ITEM_CONTAINER_MEDIA_TYPE,
        scope=LINE_ITEM_READONLY_SCOPE,
    )
    assert listed.status_code == 200, (
        f"Listing the container with a token granted for {LINE_ITEM_READONLY_SCOPE!r} answered "
        f"{listed.status_code}. That is the credential the refusal above was refused with, so a "
        "refusal here would mean the token itself is bad and the pair would be about the token "
        f"rather than about the scope. Body begins {listed.text[:300]!r}."
    )
    served = {str(item.get("resourceId")) for item in mock_platform.line_items_of(listed)}
    assert str(resource_id) in served, (
        f"A line item carrying `resourceId` {resource_id!r} was created with the writing scope and "
        f"the container lists {sorted(served)}. A 201 that stores nothing is what an enforcement "
        "strict enough to refuse everything looks like from the status code alone."
    )


# ---------------------------------------------------------------------------
# The credential is judged **before anything else about the request**, so an
# unauthenticated caller learns nothing about what the route would have served.
# ---------------------------------------------------------------------------


def url_for_an_unseeded_context(url: str, seeded: str) -> str:
    """`url` with its context identifier replaced by one nothing seeds.

    Derived from the address the platform published rather than assembled from a
    path this file knows, the way every URL in this module is. Both guards are
    load-bearing: an identifier that appears nowhere in its own URL, or more than
    once, means this substitution is not the thing it looks like — and a URL that
    came back unchanged would leave the test asking about a context that *is*
    seeded, which answers 200 and says nothing.
    """
    assert seeded != A_CONTEXT_NOBODY_SEEDED, (
        f"The platform seeds a context called {A_CONTEXT_NOBODY_SEEDED!r}, so the call below "
        "addresses one that exists and the 404 this test poses its refusal against never happens."
    )
    assert url.count(seeded) == 1, (
        f"The URL {url!r} carries the context identifier {seeded!r} {url.count(seeded)} times "
        "rather than once, so swapping it either changes nothing or changes more than the context. "
        "This module addresses an unseeded context by substitution rather than by assembling a "
        "path, because E0-15 spells no URL."
    )
    return url.replace(seeded, A_CONTEXT_NOBODY_SEEDED)


@pytest.mark.parametrize("route_key", ("create_line_item", "list_line_items", "read_results"))
def test_an_unauthorised_ags_call_is_refused_before_the_context_is_looked_up(
    mock_platform: Any, route_key: str
) -> None:
    """The credential is judged before the request is resolved, and the pair says so.

    ADR 0134 copies the NRPS route's ordering: the check runs before the query
    parameters and before the context lookup, so an unauthenticated caller learns
    neither which sections exist nor which filters the container understands.

    **The mutation this kills: enforcement placed below the context lookup.** The
    routes still refuse every unauthenticated call to a *seeded* context, so every
    other test in this module stays green; what changes is that a call naming a
    context nothing seeds is answered 404 before the credential is looked at. A 404
    and a 401 are two different sentences to a stranger — one is an answer about the
    platform's contents and the other about the caller — and sweeping identifiers
    against a route that distinguishes them is how a caller enumerates what exists.
    These routes are scoped to a context, so the identifier is the thing worth
    enumerating.

    **Both halves, because the 401 alone proves nothing.** A route answering 401 to
    everything satisfies the unauthenticated half completely and would hide a real
    404 from a tool addressing the wrong course. So the authenticated counterpart is
    asserted beside it: with a token, the same unseeded context still answers 404.

    Three routes rather than one, and each reaches the lookup by a different path —
    the container's own handler, the same handler on `GET`, and `require_line_item`,
    which resolves the section before the line item precisely so that a wrong course
    and an unknown column are two different messages.
    """
    book = gradebook(mock_platform)
    route = book.routes[route_key]
    unseeded = url_for_an_unseeded_context(route.url, book.context_id)

    authorised = send(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(route.accepts[0])}",
        url=unseeded,
    )
    assert authorised.status_code == CONTEXT_NOT_FOUND_STATUS, (
        f"A call {route.description} with a granted token, naming the unseeded context "
        f"{A_CONTEXT_NOBODY_SEEDED!r}, answered {authorised.status_code} rather than "
        f"{CONTEXT_NOT_FOUND_STATUS} — so there is no context lookup for the credential check to "
        "come before and this test cannot show the ordering. If this answered 401 or 403 the token "
        "is what failed, and the control tests at the head of this module diagnose that; if it "
        "answered 2xx the platform served a gradebook for a section nobody seeded, which is a "
        f"finding of its own. Body begins {authorised.text[:300]!r}."
    )

    refused(
        mock_platform,
        route,
        None,
        status=UNAUTHORIZED,
        code=None,
        subject=(
            f"A call {route.description} carrying no credential and naming the unseeded context "
            f"{A_CONTEXT_NOBODY_SEEDED!r}"
        ),
        control=(
            f"The identical call presenting a granted token was answered "
            f"{CONTEXT_NOT_FOUND_STATUS} a moment ago, so the lookup is there and the credential "
            "was judged before it,"
        ),
        url=unseeded,
    )


@pytest.mark.parametrize("parameter", (PAGE_PARAMETER, LIMIT_PARAMETER))
@pytest.mark.parametrize("route_key", PAGED_CONTAINERS)
def test_an_unauthorised_read_is_refused_before_a_paging_bound_is_checked(
    mock_platform: Any, route_key: str, parameter: str
) -> None:
    """ADR 0099's recorded consequence, arriving in the ticket that ADR named.

    That record kept the `ge=1` bounds in the AGS route signatures and said exactly
    why the roster's had to move: "a constraint on a route parameter is enforced by
    the framework before the handler is entered at all — so `?page=0` answered `422`,
    naming the parameter and the bound it broke, to a caller who had presented
    nothing". It then named the day this becomes true of AGS: "the day AGS starts
    requiring a token — E3's, per the deferral — those two signatures are part of the
    work, and this consequence is the note saying so."

    **The mutation this kills: the bound left in the signature**, on either
    container and either parameter. It is one word, it reads as tidier than a check
    inside the handler, and every other test in this module stays green — the routes
    still refuse an unauthenticated call to a plain URL, and only a caller who adds
    `?page=0` learns that this container pages, what its cursor is called, and where
    it starts.

    Both parameters, because they are two declarations and a repair can reach one.
    Both containers, because they are two route signatures with the same pair in
    each, which is `docs/MISTAKES.md` entry 13's shape exactly.

    **The authenticated half asserts only that the credential is not what refuses**,
    which is all the ordering claim needs here and is deliberately not a status. What
    an authenticated `?limit=0` should answer is not settled by any record — a
    container is free to clamp it — and pinning one would be this test deciding it.
    The page half of that question *is* settled and has its own test below.
    """
    book = gradebook(mock_platform)
    route = book.routes[route_key]
    bounded = mock_platform.with_query(route.url, {parameter: A_VALUE_BELOW_THE_BOUND})

    authorised = send(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(route.accepts[0])}",
        url=bounded,
    )
    assert authorised.status_code not in (UNAUTHORIZED, FORBIDDEN), (
        f"A call {route.description} with a granted token and `{parameter}="
        f"{A_VALUE_BELOW_THE_BOUND}` answered {authorised.status_code}, which is a refusal of the "
        "credential rather than of the parameter — so the 401 below would be the same answer this "
        "call got and would say nothing about which check came first. The control tests at the "
        f"head of this module diagnose a token that does not work. Body begins "
        f"{authorised.text[:300]!r}."
    )

    refused(
        mock_platform,
        route,
        None,
        status=UNAUTHORIZED,
        code=None,
        subject=(
            f"A call {route.description} carrying no credential and `{parameter}="
            f"{A_VALUE_BELOW_THE_BOUND}`, below the bound that parameter's signature declares"
        ),
        control=(
            f"The identical call presenting a granted token was answered "
            f"{authorised.status_code} a moment ago, so the parameter reaches the handler and the "
            "credential was judged before whatever judges it,"
        ),
        url=bounded,
    )


@pytest.mark.parametrize("route_key", PAGED_CONTAINERS)
def test_an_authorised_read_of_a_page_below_the_bound_is_refused_by_the_judged_path(
    mock_platform: Any, route_key: str
) -> None:
    """The other side of the move: the bound still exists, one layer in.

    Moving a constraint off a route signature is two changes and only one of them is
    visible to the test above — the framework stops answering first, and something
    inside the handler has to start. **The mutation this kills: the bound deleted
    rather than moved.** An unauthenticated `?page=0` is then 401 exactly as the pair
    above requires, and an authenticated one is served page one of the container as
    though the cursor had never been sent, so a tool walking with a broken cursor
    reads the same page forever and never learns why.

    **400, and the code is not this test's invention.** It is E0-28 item 2's for a
    parameter this container will not serve on, and ADR 0099 already applied it to
    the roster's cursor when that bound moved behind the credential: "a value that is
    not a page number is refused **400** … and deliberately not the `404` that a page
    *past* the end of a roster answers with — that one is a client following a header
    into nowhere, and page zero is a cursor no collection could have." Two containers
    answering one cursor two ways is `docs/MISTAKES.md` entry 13.

    The refusal is required to name the parameter, so it is a sentence a tool's
    author acts on rather than a bare code, and so this test can attribute the
    refusal to the cursor rather than to something else about the request.
    """
    book = gradebook(mock_platform)
    route = book.routes[route_key]
    bounded = mock_platform.with_query(route.url, {PAGE_PARAMETER: A_VALUE_BELOW_THE_BOUND})

    served = accepted(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(route.accepts[0])}",
        f"A call {route.description} with a granted token and no paging parameters",
    )
    assert served.status_code == route.accepted_status, served.text[:300]

    answered = send(
        mock_platform,
        route,
        f"{BEARER_SCHEME} {mock_platform.ags_token(route.accepts[0])}",
        url=bounded,
    )
    assert answered.status_code == PAGE_REFUSAL_STATUS, (
        f"A call {route.description} with a granted token and `{PAGE_PARAMETER}="
        f"{A_VALUE_BELOW_THE_BOUND}` answered {answered.status_code} rather than "
        f"{PAGE_REFUSAL_STATUS}. A 2xx means the bound was deleted along with the signature and "
        "the container served page one to a cursor no collection could have; a 422 means the "
        "bound is still in the signature, where the framework answers before the credential — "
        "which is what the pair beside this one refuses. Body begins "
        f"{answered.text[:300]!r}."
    )
    assert PAGE_PARAMETER in answered.text.lower(), (
        f"The refusal of `{PAGE_PARAMETER}={A_VALUE_BELOW_THE_BOUND}` does not name "
        f"`{PAGE_PARAMETER}` — the body is {answered.text[:300]!r}. E0-28 item 2 asks a parameter "
        "refusal to say which parameter it objects to, and a refusal that names none is one this "
        "test cannot attribute to the cursor rather than to something else about the request."
    )


# ---------------------------------------------------------------------------
# What stays open, and why it is a decision. ADR 0134 says so out loud so that a
# reviewer can tell the decision from an oversight; this is the test that makes
# it one.
# ---------------------------------------------------------------------------


def test_the_mock_only_posted_score_readback_still_answers_without_a_credential(
    mock_platform: Any,
) -> None:
    """The `/mock/` prefix is outside this enforcement, by decision (ADR 0047, ADR 0134).

    `GET /mock/posted-scores` is not an AGS route. ADR 0047 puts it outside the AGS
    namespace precisely so that nothing can mistake it for part of the protocol — "a
    tool that learned this route would have learned something no real platform
    serves" — and it is the surface E3 proves its own passback against, because a
    conformant `Result` cannot carry what was sent.

    **The mutation this kills: enforcement applied to the application rather than to
    the routes** — a dependency on the app, a middleware over every path, or a check
    added to `json_object`. Every refusal in this module stays green under all three,
    and what breaks is every readback in the AGS suite and the byte-exact carriage
    assertion E3-04's client tests rest on, which would go red naming the score
    rather than the credential.

    Both halves are here, and the second is what makes this a statement about the
    prefix rather than about one path: the readback answers with no header at all,
    **and** it carries the score the AGS routes have just recorded — so a route that
    answered 200 with nothing would not satisfy it.

    **Green before this ticket and green after it.** A red here means the enforcement
    reached further than ADR 0134 says it does.
    """
    book = gradebook(mock_platform)
    assert book.routes, "The gradebook was built with no routes, so nothing has been posted."

    response = mock_platform.client.get(mock_platform.local(MOCK_POSTED_SCORES_PATH))
    assert response.status_code == 200, (
        f"`GET {MOCK_POSTED_SCORES_PATH}` carrying no credential answered "
        f"{response.status_code}. ADR 0047 makes this a mock-only inspection route outside the AGS "
        "namespace and ADR 0134 leaves it outside the enforcement; a refusal here is enforcement "
        "applied to the application rather than to the AGS routes, and it takes every readback in "
        f"the suite with it. Body begins {response.text[:300]!r}."
    )
    document = response.json()
    recorded = document.get("scores") if isinstance(document, dict) else None
    assert isinstance(recorded, list) and recorded, (
        f"`{MOCK_POSTED_SCORES_PATH}` answered {document!r} after a score was accepted through the "
        "Score service. A 200 with nothing in it satisfies the status assertion above while "
        "carrying none of what this surface exists to carry, so both halves are asserted."
    )


def test_every_ags_route_the_platform_declares_is_one_this_module_drives(
    mock_platform: Any,
) -> None:
    """The inventory, read off the running application rather than out of this file.

    The security round's LOW, and it is `docs/MISTAKES.md` entry 35's shape one level
    up from the triples: `EVERY_ROUTE` is a hand-written tuple over a hand-written
    route table, so **a seventh AGS route registered without a credential is covered
    by nothing here and this module stays entirely green**. Criterion 6 says "every
    AGS route", and a list that cannot grow with the platform cannot say "every".

    So the namespace is derived. The container's address comes from the launch's own
    AGS endpoint claim, `ags_namespace` finds the template that routes it, and every
    declaration beneath that template is required to be one of the six this module
    addresses — matched by `(method, template)` against the concrete URLs the triples
    actually drive, so a route this file *names* but never calls does not count as
    covered.

    **The mutation this kills: a new AGS route registered without `authorised_token`.**
    Add `GET …/line_items/{id}/history` to the mock and every other test in this file
    passes; this one names the method and the path that nothing drives.

    **The near miss it is written around: the new route added to the allowlist
    instead.** `TOKENLESS_BY_DECISION` is the `/mock/` prefix decision written down
    (ADR 0047, ADR 0134), and it is held to two properties so it cannot become a place
    to put an inconvenient route — every entry is under `/mock/`, and nothing inside
    the AGS namespace matches any entry. A route parked there fails both.

    **The allowlist is required to cover something**, which is the same entry-35 rule
    the triples keep: an allowlist that matched no route this platform serves would be
    a decision about nothing, and its two properties would hold vacuously.

    **A red here is not necessarily a defect in the mock.** It is either a route that
    has to be driven — the six triples take a seventh row and `Route` takes a seventh
    entry — or a deliberate exception, which is an ADR 0134 amendment and a line in
    `TOKENLESS_BY_DECISION`, never a widening of this walk.

    **Predicted green today**, over the six routes ADR 0134 maps. Its worth is the
    mutation it names rather than the colour it starts at.
    """
    book = gradebook(mock_platform)
    declared = declared_routes(mock_platform)
    assert declared, (
        "The walk found no declared route on the mock platform at all, so this guard would report "
        "an empty namespace as a covered one. `tests/fixtures/routing.py` explains the shape a "
        "blind walk takes; a red here is that walk rather than the platform."
    )

    container_path = urlsplit(mock_platform.local(book.routes["list_line_items"].url)).path
    prefix = ags_namespace(declared, container_path)
    namespace = [(method, path) for method, path in declared if path.startswith(prefix)]
    assert len(namespace) >= len(EVERY_ROUTE), (
        f"The AGS namespace {prefix!r} declares {namespace}, which is fewer routes than the "
        f"{len(EVERY_ROUTE)} this module drives. Either the walk is not seeing what the platform "
        "serves or a route this module addresses has been removed, and both are findings rather "
        "than a shrinking inventory."
    )

    addressed = [
        (route.method.upper(), urlsplit(mock_platform.local(route.url)).path)
        for route in book.routes.values()
    ]
    uncovered = [
        (method, path)
        for method, path in namespace
        if not any(
            driven_method == method and template_pattern(path).match(driven_path)
            for driven_method, driven_path in addressed
        )
    ]
    assert not uncovered, (
        f"The mock declares {uncovered} under the AGS namespace {prefix!r}, and no test in this "
        f"module calls them — this module drives {sorted(EVERY_ROUTE)}, addressed at {addressed}. "
        "Criterion 6 is 'all three, per route': an AGS route nothing here drives has no absent-token "
        "test, no wrong-scope test and no accepted control, so it can be serving a gradebook to "
        "anyone who can reach the URL with this whole file green. Add it to `Route`/`EVERY_ROUTE` "
        f"with its accepted scopes, or — if it is deliberately open — amend ADR 0134 and name it in "
        "`TOKENLESS_BY_DECISION`."
    )

    for allowed in TOKENLESS_BY_DECISION:
        assert allowed.startswith("/mock/"), (
            f"`TOKENLESS_BY_DECISION` carries {allowed!r}. ADR 0134's decision is about the "
            "`/mock/` prefix — an inspection surface no real platform serves — and an entry outside "
            "it is a protocol route excused from the enforcement by an edit to a test file."
        )
        assert not [path for _method, path in namespace if path.startswith(allowed)], (
            f"A route inside the AGS namespace {prefix!r} is covered by the tokenless entry "
            f"{allowed!r}. That is the near miss this guard exists for: a new AGS route parked on "
            "the allowlist rather than given its triple."
        )
    covered = [path for _method, path in declared if path.startswith(TOKENLESS_BY_DECISION)]
    assert covered, (
        f"`TOKENLESS_BY_DECISION` ({list(TOKENLESS_BY_DECISION)}) matches no route this platform "
        f"declares; it declares {sorted({path for _m, path in declared})}. An allowlist that covers "
        "nothing is a decision about nothing, and both properties asserted above would hold "
        "vacuously (`docs/MISTAKES.md` entry 35)."
    )
