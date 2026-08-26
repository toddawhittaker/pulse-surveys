"""E0-15 — the LTI Advantage services, reached the way a tool reaches them.

E0-14's `mock_platform` and `mock_platforms` are here, with the driver they hand
back. Its definition of done asks for "a reusable fixture that mints a signed
launch — E1's launch-validation tests depend on it, so its interface matters", so
the fixture is the ticket's own deliverable rather than a convenience, and it is
shared for the reason every other shared thing is: E1 will import it, and a
second copy would drift. Like `SectionCodeService`, it discovers the mock
platform rather than naming its parts — what it discovers and what it refuses to
decide is written on the class.

E0-15 extends that class rather than adding another, because its subject is the
same platform: the LTI Advantage services it now serves are reached through the
claims a launch carries, which is how a tool reaches them and which means no URL
is hardcoded here either. `link_relations_in` and `instant_of` sit beside
`signed_launch` and exist so that a test module can exercise the paging-header
parser and the timestamp comparison without importing this file by name.
"""

import importlib
import json
import re
import secrets
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urljoin, urlsplit
from uuid import uuid4

import pytest

from fixtures.app_imports import import_mock_lms_application, mock_package_resolved
from fixtures.lti_platform import (
    AUTHORIZATION_REQUEST_CONSTANTS,
    MOCK_LMS_DIR,
    MOCK_LMS_SERVICE,
    MOCK_PACKAGE,
    JsonWebSignature,
    LaunchOffer,
    SignedLaunch,
    declared_paths,
    form_submissions,
    forms_in,
    local_target,
    path_appended,
    split_jws,
    url_with_query,
    verifying_key,
)
from fixtures.repo import REPO_ROOT

# ---------------------------------------------------------------------------
# E0-15 — the LTI Advantage services, reached the way a tool reaches them.
# ---------------------------------------------------------------------------

# The two service claims, **spelled as the IMS specifications spell them and not
# this suite's choice in any part**. In LTI Advantage a platform advertises its
# services inside the launch it has just signed: the NRPS claim carries the
# context memberships URL, and the AGS endpoint claim carries the line-items URL
# together with the scopes a token may be requested for. Reading them out of the
# token is how a real tool finds these services, which is why nothing below
# hardcodes a path — and a mock that serves them at fixed paths while putting no
# claim in the token has built something `pylti1p3` (SPEC §7.1) cannot find.
NRPS_CLAIM = "https://purl.imsglobal.org/spec/lti-nrps/claim/namesroleservice"
AGS_CLAIM = "https://purl.imsglobal.org/spec/lti-ags/claim/endpoint"

# The context claim, from the same specification. `tests/integration/
# test_mock_lms_launch.py` spells it too, and both are transcriptions of one
# published constant rather than two copies of a decision: a launch spelling it
# differently fails there first, by name.
CONTEXT_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/context"

# E1-08. The query parameter `mock-lms/app/wrong_launches.py` reads off an
# authorization request to select one of E1-07's deliberately wrong (or
# near-miss) mints by name. **This module's own copy of the string**, not an
# import of `app.wrong_launches.DEFECT_QUERY_PARAM`: both mocks declare a
# package named `app` (SPEC §13), and importing either by name from a module
# outside its own package is the collision `docs/adr/0039-the-two-app-
# packages-are-typechecked-in-two-runs.md` describes — the same reason
# `tests/integration/test_mock_lms_wrong_launches.py` keeps its own copy
# rather than importing the mock's.
DEFECT_QUERY_PARAM = "defect"

# The media types the Advantage services exchange, from NRPS 2.0 and AGS 2.0.
# Sent rather than assumed, because sending them is what a tool does. All four
# end in `+json`, which is also what lets a FastAPI endpoint declaring a JSON
# body parse them — FastAPI reads any `application/…+json` subtype as JSON — so
# using the specification's media type cannot fail a mock that expected plain
# `application/json`, while the reverse could.
NRPS_MEDIA_TYPE = "application/vnd.ims.lti-nrps.v2.membershipcontainer+json"
LINE_ITEM_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitem+json"
LINE_ITEM_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitemcontainer+json"
RESULT_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.resultcontainer+json"
SCORE_MEDIA_TYPE = "application/vnd.ims.lis.v1.score+json"

# Where a test reads back what the tool posted. **E0-15's spelling, not this
# suite's** (ADR 0047): a mock-only route outside the AGS namespace, answering
# `{"scores": [{"lineItem": …, "score": {…}}]}` in arrival order. It is named
# here rather than discovered, and the `/mock/` prefix is the reason — a fixture
# that went looking for a route whose path carries "score" would accept an AGS
# route serving the same thing, which is the one arrangement the prefix exists to
# rule out. A tool that learned this route would have learned something no real
# platform serves.
MOCK_POSTED_SCORES_PATH = "/mock/posted-scores"

# The two AGS scopes SPEC §3.4 needs: one line item per section, and a score
# posted to it. Specification constants, not preferences.
AGS_LINE_ITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
AGS_SCORE_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"

# How many pages of one paged container are walked before the walk is called
# broken. **This suite's choice**, and a bound rather than a rule: E0-15 keeps
# its seed small ("this seed data belongs to the mock platform and stays
# small"), so a container running past this is a `Link` header that never says
# stop rather than a large collection. Raise it if a seed grows.
MAX_PAGES_WALKED = 25

# One `<url>; rel="next"` entry of an RFC 8288 `Link` header. The parameter tail
# stops at a comma so that two entries in one header are read as two, which is
# the shape a platform sends when it offers `next` and `last` together.
LINK_HEADER_ENTRY = re.compile(r"<(?P<url>[^>]*)>(?P<parameters>(?:\s*;[^,;]*)*)")


def link_relations(header: str | None) -> dict[str, str]:
    """Every `rel` an RFC 8288 `Link` header declares, mapped to its URL.

    A parser rather than a substring search, for the reason `FormReader` above
    is a parser: what is being read is the platform's contract with a paging
    client, and `"next" in header` answers a different question that happens to
    look the same (`docs/MISTAKES.md` entry 3). A header carrying
    `rel="first next"` declares both relations on one URL, which is legal and
    which a substring search gets right for the wrong reason.

    The first URL declared for a relation wins, so a repeated `rel="next"` is
    read the way a client reads it rather than silently taking the last.
    """
    relations: dict[str, str] = {}
    if not header:
        return relations
    for entry in LINK_HEADER_ENTRY.finditer(header):
        url = entry.group("url").strip()
        for parameter in entry.group("parameters").split(";"):
            name, _, value = parameter.partition("=")
            if name.strip().lower() != "rel":
                continue
            for relation in value.strip().strip('"').split():
                relations.setdefault(relation.lower(), url)
    return relations


def instant(value: Any) -> datetime | None:
    """`value` as a moment in time, or `None` if it is not one.

    Timestamps are compared as instants rather than as strings, because
    `2026-09-14T18:30:00+00:00` and `2026-09-14T18:30:00Z` are one moment
    written two ways and a service that normalises between them has lost
    nothing. What the comparison is for is the near miss — a score recorder that
    stored the value it was sent and stamped its own clock over the timestamp —
    and that survives normalisation.

    A date with no time is accepted, at midnight: NRPS carries enrollment
    windows (SPEC §3.4, §7.3) and a window's edges are days.
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        # RFC 3339 §5.6 notes that `Z` may be written in lower case, and
        # `datetime.fromisoformat` does not accept the lower-case form — so a
        # conformant timestamp would read as "not a moment" and a test about
        # enrollment windows would report that the roster carries no dates.
        # Rewritten by position rather than by `replace`, which would also
        # rewrite a `Z` that was not the designator.
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class MembershipPage(NamedTuple):
    """One page of an NRPS membership container, with the header that pages it.

    `link_header` is kept raw as well as parsed, because the criterion is about
    the header — "a roster larger than one page returns `Link` headers" — and a
    failure that can print what was actually sent is worth more than one that
    can only say a relation was missing.
    """

    url: str
    status_code: int
    document: dict[str, Any]
    link_header: str | None
    relations: dict[str, str]
    members: list[dict[str, Any]]
    next_url: str | None


class ResultPage(NamedTuple):
    """One page of an AGS Result container, with the header that pages it.

    The twin of `MembershipPage` above, and it exists for the same reason: E0-28
    item 4 makes the results container page like the roster, so a test asks it
    the same questions — which relations the page advertises, and what the page
    itself carries. Keeping the raw header beside the parsed relations is what
    lets a failure print what the platform actually sent.
    """

    url: str
    status_code: int
    results: list[dict[str, Any]]
    link_header: str | None
    relations: dict[str, str]


class SeededContext(NamedTuple):
    """One seeded section, and every launch the platform offers into it.

    `subjects` is the independent ground truth the paging tests need. Each is a
    user this platform will sign a launch for in this context, learned by
    driving the launch rather than by reading the roster, so a roster that has
    lost one has lost a member that demonstrably exists. It is a **lower bound**
    on the membership rather than the whole of it — the launch page offers a
    handful of users and a roster is bigger than that — and the test that leans
    on it says so.
    """

    context_id: str
    memberships_url: str
    launches: list[SignedLaunch]

    @property
    def subjects(self) -> set[str]:
        return {
            str(launch.claims["sub"])
            for launch in self.launches
            if isinstance(launch.claims.get("sub"), str)
        }


class MockPlatform:
    """E0-14's platform, driven the way a tool drives one rather than by name.

    **Nothing about the mock's URLs is written down**, so nothing here is
    hardcoded that the protocol can supply instead:

      - The launch page is found by *what it serves*: the page carrying a form
        with the OIDC third-party-initiated login parameters. That is the
        definition of a launch page rather than a guess at a path.
      - The registration values a test compares claims against — issuer, client
        ID, deployment ID, target link URI — are read out of that form, because
        those are exactly the parameters the initiation request carries.
      - The authorization endpoint and the key set are taken from the platform's
        OIDC discovery document when it serves one, and otherwise from the one
        route whose path names them.

    Two paths are all this leaves to a fragment match, and each fails with a
    message saying so. **What this does not do is decide anything**: where E0-14
    leaves a name open, a test fails naming the gap rather than passing against
    an interface the ticket never asked for.
    """

    def __init__(
        self, values: Mapping[str, str] | None = None, tool_key_set: Any | None = None
    ) -> None:
        from fastapi.testclient import TestClient

        self.values = dict(values or {})
        self.application = import_mock_lms_application(self.values)
        self.client = TestClient(self.application, follow_redirects=False)
        # Entered so the application's lifespan runs: a platform that generates
        # its issuer key on startup has not generated one until it does.
        self.client.__enter__()
        # E1-06. The platform verifies a tool-signed `client_assertion` against the
        # tool's published key set, which it fetches — and neither the tool's
        # address nor any other resolves in an in-process test. So every
        # server-side fetch this platform makes goes through one client, the way
        # `tests/fixtures/doors.py` routes the tool's own; see
        # `tests/fixtures/client_credentials.py` for what that pins and what it
        # deliberately leaves to the implementer. Installed **after** the lifespan
        # has run, for the reason `tool_doors` gives: it then holds this test's
        # client whether the mock builds one in its factory or at startup.
        if tool_key_set is not None:
            self.application.state.http = tool_key_set.client

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    # -- what the application serves ----------------------------------------

    def paths(self, method: str = "GET") -> list[str]:
        """Every declared path that answers `method` and takes no path parameter."""
        return declared_paths(self.application, method)

    def path_named_after(self, fragments: tuple[str, ...], purpose: str) -> str:
        """The one route whose path carries one of `fragments`.

        Ambiguity stops rather than picks, the way `callable_named_after` does
        above: two candidates mean this cannot tell which one the ticket is
        about, and choosing would be the test deciding.
        """
        declared = sorted(set(self.paths("GET")) | set(self.paths("POST")))
        for fragment in fragments:
            matches = [path for path in declared if fragment in path.lower()]
            if len(matches) > 1:
                pytest.fail(
                    f"The mock platform declares more than one route whose path carries "
                    f"{fragment!r} ({matches}), so this cannot tell which one {purpose}. E0-14 "
                    "spells no URL, so naming one here would pin an interface the ticket leaves "
                    "open — say in the pull request which it is, and `MockPlatform` in "
                    "tests/fixtures/lti_services.py is the one place that changes."
                )
            if matches:
                return matches[0]
        pytest.fail(
            f"The mock platform declares no route whose path carries any of {list(fragments)} — "
            f"it declares {declared}. This is the endpoint that {purpose}, which E0-14's scope "
            "requires; if it is there under a path none of these fragments reaches, that is a "
            "defect in `MockPlatform` in tests/fixtures/lti_services.py rather than in the mock."
        )

    def discovery(self) -> dict[str, Any] | None:
        """The platform's OIDC discovery document, if it serves one."""
        for path in self.paths("GET"):
            if "openid-configuration" not in path:
                continue
            response = self.client.get(path)
            if response.status_code == 200:
                document = response.json()
                if isinstance(document, dict):
                    return document
        return None

    def endpoint(self, discovered: str, fragments: tuple[str, ...], purpose: str) -> str:
        """An endpoint path, from the discovery document if there is one."""
        document = self.discovery()
        if document:
            advertised = document.get(discovered)
            if isinstance(advertised, str) and advertised:
                return urlsplit(advertised).path or advertised
        return self.path_named_after(fragments, purpose)

    def jwks(self) -> dict[str, Any]:
        """The published key set, as JSON."""
        path = self.endpoint("jwks_uri", ("jwks", "keys"), "serves the platform's public keys")
        response = self.client.get(path)
        assert response.status_code == 200, (
            f"The JWKS endpoint `{path}` answered {response.status_code} rather than 200. E0-14's "
            "second acceptance criterion is that it serves a key that verifies an issued "
            "`id_token`, and a key set nobody can fetch verifies nothing."
        )
        document = response.json()
        assert isinstance(document, dict), (
            f"The JWKS endpoint `{path}` served {document!r}, which is not a JWK Set. RFC 7517 "
            "makes a key set a JSON object with a `keys` member."
        )
        return document

    def published_keys(self) -> list[dict[str, Any]]:
        keys = self.jwks().get("keys")
        return [key for key in keys if isinstance(key, dict)] if isinstance(keys, list) else []

    def verifies(self, token: Any) -> dict[str, Any] | None:
        """The published key that verifies `token`, or `None` if none does.

        Takes a compact JWS string or an already-split one, so a test that has
        tampered with a token can hand over the string it produced rather than
        rebuilding the split. Verification is the arithmetic in `verify_rs256`
        above; this only supplies the key set.
        """
        signature = token if isinstance(token, JsonWebSignature) else split_jws(str(token))
        return verifying_key(signature, self.jwks())

    # -- launches ------------------------------------------------------------

    def offers(self) -> list[LaunchOffer]:
        """Every launch the platform's launch page offers.

        Found by serving rather than by path: a launch page is the page carrying
        a form whose fields are an OIDC third-party-initiated login request, and
        `target_link_uri` plus `login_hint` are the two that request must carry.
        Only `GET` routes with no path parameter are fetched, so nothing here can
        have a side effect.
        """
        offers: list[LaunchOffer] = []
        for path in self.paths("GET"):
            response = self.client.get(path)
            if response.status_code != 200:
                continue
            if "html" not in response.headers.get("content-type", "").lower():
                continue
            for form in forms_in(response.text):
                names = set(form["fields"]) | set(form["choices"])
                if not {"target_link_uri", "login_hint"} <= names:
                    continue
                for parameters in form_submissions(form):
                    offers.append(
                        LaunchOffer(
                            page=path,
                            posts_to=urljoin(f"http://testserver{path}", form["action"]),
                            method=form["method"],
                            parameters=parameters,
                        )
                    )
        return offers

    def require_offers(self) -> list[LaunchOffer]:
        offers = self.offers()
        assert offers, (
            "The mock platform serves no page carrying a form with `target_link_uri` and "
            f"`login_hint` fields. Pages fetched: {self.paths('GET')}. E0-14's scope asks for "
            "'a launch page that posts the form to the tool, so a browser-driven test can click "
            "through a realistic launch', and those two fields are what make that form an OIDC "
            "third-party-initiated login request rather than an arbitrary form."
        )
        return offers

    def mint(
        self,
        offer: LaunchOffer | None = None,
        *,
        state: str | None = None,
        nonce: str | None = None,
        defect: str | None = None,
    ) -> SignedLaunch:
        """Drive one launch to the point a tool would receive the `id_token`.

        This is E0-14's seventh criterion — "a test can obtain a signed launch
        for an arbitrary seeded user and role without a browser" — and it is done
        by *being* the tool: taking the platform's initiation request, answering
        it with an authorization request the way a tool would, and reading the
        `id_token` out of what comes back. Nothing is called that a real tool
        would not call, so a launch minted here and a launch a browser produces
        are the same launch.

        `defect`, added for E1-08, selects one of E1-07's deliberately wrong (or
        near-miss) launches by name — `?defect=foreign_signature` and the rest
        of `mock-lms/app/wrong_launches.py::ALL_SELECTORS`. `None`, the default,
        takes the exact code path this method took before E1-07 existed: that
        ticket's own module docstring promises its addition is additive, and
        this keyword is what keeps that promise here too. A caller that wants a
        defective launch to still be judged against a real tool's own `state`/
        `nonce` — the shape a door test needs, since pylti1p3's login step
        stores what it issued — passes them through the `state`/`nonce`
        keywords above rather than letting this method invent fresh ones.
        """
        chosen = offer or self.require_offers()[0]
        request = dict(AUTHORIZATION_REQUEST_CONSTANTS)
        request["state"] = state if state is not None else secrets.token_urlsafe(24)
        request["nonce"] = nonce if nonce is not None else secrets.token_urlsafe(24)
        request["redirect_uri"] = chosen.parameters.get("target_link_uri", "")
        for name in ("login_hint", "lti_message_hint", "client_id", "lti_deployment_id"):
            value = chosen.parameters.get(name)
            if value:
                request[name] = value

        path = self.endpoint(
            "authorization_endpoint",
            ("auth",),
            "receives the tool's authorization request and answers with a signed `id_token`",
        )
        query = {} if defect is None else {DEFECT_QUERY_PARAM: defect}
        # POST where the route accepts it, GET otherwise. Which of the two a
        # tool uses is the tool's choice under OIDC, so the endpoint's own
        # declaration decides rather than this file.
        if path in self.paths("POST"):
            response = self.client.post(path, data=request, params=query)
        else:
            response = self.client.get(path, params={**request, **query})

        id_token, returned_state, posted_to = self.read_authorization_response(response, path)
        return SignedLaunch(
            offer=chosen,
            authorization_request=request,
            id_token=id_token,
            state=returned_state,
            posted_to=posted_to,
            signature=split_jws(id_token),
        )

    def read_authorization_response(
        self, response: Any, path: str
    ) -> tuple[str, str | None, str | None]:
        """Pull the `id_token` and the returned `state` out of what the platform sent.

        Both shapes are accepted — the `form_post` auto-submitting form the LTI
        security framework specifies, and a redirect carrying the values in its
        query or fragment — because which one the mock uses is not something
        E0-14 decides, and refusing the second would fail a platform that is
        merely making a different legal choice.
        """
        if response.status_code == 200:
            for form in forms_in(response.text):
                fields = form["fields"]
                if "id_token" in fields:
                    return fields["id_token"], fields.get("state"), form["action"]
        location = response.headers.get("location")
        if location:
            split = urlsplit(location)
            for blob in (split.query, split.fragment):
                pairs = parse_qs(blob)
                if "id_token" in pairs:
                    returned = pairs.get("state") or [None]
                    return pairs["id_token"][0], returned[0], location
        pytest.fail(
            f"The authorization endpoint `{path}` answered {response.status_code} with no "
            "`id_token` in a form and none in a redirect, so no launch was produced. Body begins "
            f"{response.text[:300]!r}. E0-14 issues 'a signed `id_token` carrying the LTI 1.3 "
            "core claims'; the LTI 1.3 security framework returns it by `form_post` to the "
            "tool's redirect URI."
        )

    # -- the LTI Advantage services (E0-15) ----------------------------------

    def local(self, url: str) -> str:
        """`url` as this in-process client can request it: its path and query.

        The services advertise themselves with absolute URLs built from whatever
        public base the mock is configured with, and that host is one this
        client neither can nor should resolve — what is under test is the
        platform's own routing. That the advertised URL *is* absolute is
        asserted by a test rather than assumed here, because a relative one is a
        URL no real tool could follow.
        """
        return local_target(url)

    @staticmethod
    def refuse_an_unspecified_token_flow(response: Any, url: str) -> None:
        """Turn a 401 or a 403 into a named gap rather than a puzzling red.

        Real LTI Advantage services sit behind an OAuth 2.0 client-credentials
        grant against the platform's token endpoint. E0-15 does not mention one
        and E0-14 built none, so this suite drives the services unauthenticated.

        **E1-06 builds the token endpoint and deliberately does not make NRPS or
        AGS require a token**, which is a ruling of that ticket rather than an
        omission: enforcement pairs with E1-11's client, and a mock that started
        refusing unauthenticated reads would turn every E0-15 test red for a
        reason none of them is about (`docs/MISTAKES.md` entry 22). So this stays
        exactly as it was, and a 401 here is still a gap to be settled in a
        ticket rather than guessed at in this file.
        """
        if response.status_code in (401, 403):
            pytest.fail(
                f"The platform answered {response.status_code} for `{url}`, so it requires an "
                "access token for its Advantage services. E0-15 specifies no grant, E0-14 built "
                "none, and E1-06 builds the token endpoint while ruling that these services do "
                "not yet require a token — enforcement arrives with E1-11's client. So this suite "
                "calls NRPS and AGS unauthenticated; what a tool should present is a question for "
                "that ticket rather than something to guess at in tests/fixtures/lti_services.py."
            )

    def service_get(self, url: str, accept: str | None = None) -> Any:
        """GET one Advantage URL the platform advertised."""
        response = self.client.get(self.local(url), headers={"accept": accept} if accept else None)
        self.refuse_an_unspecified_token_flow(response, url)
        return response

    def service_post(
        self,
        url: str,
        payload: Mapping[str, Any],
        content_type: str,
        accept: str | None = None,
    ) -> Any:
        """POST one JSON document to an Advantage URL, under the media type AGS fixes.

        The body is serialised here rather than handed to httpx's `json=`
        keyword, because that keyword would set `application/json` and overwrite
        the media type the specification requires the request to carry.
        """
        headers = {"content-type": content_type}
        if accept:
            headers["accept"] = accept
        response = self.client.post(self.local(url), content=json.dumps(payload), headers=headers)
        self.refuse_an_unspecified_token_flow(response, url)
        return response

    def service_claim(self, launch: SignedLaunch, claim: str, member: str, purpose: str) -> str:
        """One member of one service claim, or a failure naming what is missing.

        The failure is worth more than the value: a launch that carries no
        service claim is a platform whose services a conformant tool cannot
        discover at all, whatever it serves and wherever.
        """
        advertised = launch.claims.get(claim)
        if not isinstance(advertised, dict):
            pytest.fail(
                f"The `id_token` carries no `{claim}` claim (it carries "
                f"{sorted(launch.claims)}). That claim is how a platform tells a tool where "
                f"{purpose}; without it a tool has nothing to call, whatever the mock serves and "
                "at whatever path."
            )
        value = advertised.get(member)
        if not isinstance(value, str) or not value:
            pytest.fail(
                f"The `{claim}` claim carries no `{member}` (it carries {sorted(advertised)}). "
                f"That member is the URL {purpose}."
            )
        return value

    def memberships_url(self, launch: SignedLaunch) -> str:
        """Where this launch's context roster lives, per the NRPS claim."""
        return self.service_claim(
            launch,
            NRPS_CLAIM,
            "context_memberships_url",
            "the roster for the launched context is served",
        )

    def line_items_url(self, launch: SignedLaunch) -> str:
        """Where this launch's line items live, per the AGS endpoint claim."""
        return self.service_claim(
            launch,
            AGS_CLAIM,
            "lineitems",
            "the context's line items are listed and created",
        )

    def ags_scopes(self, launch: SignedLaunch) -> list[str]:
        """The scopes the AGS endpoint claim says a token may be requested for."""
        advertised = launch.claims.get(AGS_CLAIM)
        if not isinstance(advertised, dict):
            return []
        scopes = advertised.get("scope")
        if not isinstance(scopes, list):
            return []
        return [scope for scope in scopes if isinstance(scope, str)]

    def membership_page(self, url: str) -> MembershipPage:
        """Fetch one page of a membership container and read its paging header."""
        response = self.service_get(url, accept=NRPS_MEDIA_TYPE)
        assert response.status_code == 200, (
            f"The membership service answered {response.status_code} for `{url}` rather than 200. "
            "E0-15's first criterion is a roster whose members carry role and enrollment status, "
            f"and a roster nobody can fetch carries nothing. Body begins {response.text[:200]!r}."
        )
        return self.membership_page_of(url, response)

    def membership_page_of(self, url: str, response: Any) -> MembershipPage:
        """Read one already-fetched membership page, header and all.

        Split from the fetch so that the walk in `link_walk` above and a caller
        asking for a single page build a page the same way, from one place.
        """
        document = response.json()
        assert isinstance(document, dict), (
            f"The membership service served {document!r} for `{url}`, which is not an NRPS "
            "membership container. NRPS 2.0 makes the container a JSON object with `id`, "
            "`context` and `members` members; a bare array is the shape `pylti1p3` cannot read."
        )
        members = document.get("members")
        header = response.headers.get("link")
        relations = link_relations(header)
        following = relations.get("next")
        return MembershipPage(
            url=url,
            status_code=response.status_code,
            document=document,
            link_header=header,
            relations=relations,
            members=[member for member in members if isinstance(member, dict)]
            if isinstance(members, list)
            else [],
            next_url=urljoin(url, following) if following else None,
        )

    def link_walk(self, url: str, accept: str, subject: str) -> list[tuple[str, Any]]:
        """Fetch `url` and every page its `Link` header advertises, in order.

        One walk for both paged containers E0-15 serves — the roster and the
        line-item container, which the ticket pages "the same way NRPS does" —
        so that the guards below exist once rather than twice
        (`docs/MISTAKES.md` entry 13). What differs between the two callers is
        what a page *carries*, and that stays with the caller.

        Two ways of not terminating are failures rather than hangs, and neither
        is hypothetical: a `next` URL that points at the page that served it, and
        a header that advertises a next page forever. Both leave a real tool
        looping, so both are named where they happen rather than left to a
        pytest timeout that says only that something hung.
        """
        walked: list[tuple[str, Any]] = []
        visited: set[str] = set()
        following: str | None = url
        while following is not None:
            if following in visited:
                pytest.fail(
                    f"The {subject} walk arrived back at `{following}` after {len(walked)} pages, "
                    "so the `Link` header advertises a next page that is the page that served "
                    "it. A client following this header never finishes."
                )
            visited.add(following)
            response = self.service_get(following, accept=accept)
            assert response.status_code == 200, (
                f"Page {len(walked) + 1} of the {subject} at `{following}` answered "
                f"{response.status_code} rather than 200, so the `Link` header that pointed here "
                f"points at nothing. Body begins {response.text[:200]!r}."
            )
            walked.append((following, response))
            if len(walked) > MAX_PAGES_WALKED:
                pytest.fail(
                    f"The {subject} at `{url}` ran past {MAX_PAGES_WALKED} pages without reaching "
                    "one that advertises no next relation. E0-15 keeps the seed small, so this is "
                    "a header that never says stop rather than a large collection — and a tool "
                    "paging on it does not stop either."
                )
            relations = link_relations(response.headers.get("link"))
            advertised = relations.get("next")
            following = urljoin(following, advertised) if advertised else None
        return walked

    def membership_pages(self, url: str) -> list[MembershipPage]:
        """Walk a roster from its first page to its last. Exactly what a sync does."""
        return [
            self.membership_page_of(page_url, response)
            for page_url, response in self.link_walk(url, NRPS_MEDIA_TYPE, "roster")
        ]

    def seeded_contexts(self) -> list[SeededContext]:
        """Every context the launch page offers a launch into, with those launches.

        Grouped by the context claim's `id`, so that a page offering four users
        in two sections answers two contexts rather than four. The memberships
        URL is taken from the first launch into each context, which is the URL
        that context's own roster lives at.
        """
        grouped: dict[str, list[SignedLaunch]] = {}
        for offer in self.require_offers():
            launch = self.mint(offer)
            context = launch.claims.get(CONTEXT_CLAIM)
            identifier = context.get("id") if isinstance(context, dict) else None
            if not isinstance(identifier, str) or not identifier:
                pytest.fail(
                    f"A launch from `{offer.page}` carries no context `id` (its context claim is "
                    f"{context!r}). E0-14's own suite asserts that claim, so this is that failure "
                    "arriving here first; without it a roster cannot be attributed to a section."
                )
            grouped.setdefault(identifier, []).append(launch)
        return [
            SeededContext(
                context_id=identifier,
                memberships_url=self.memberships_url(launches[0]),
                launches=launches,
            )
            for identifier, launches in sorted(grouped.items())
        ]

    def create_line_item(
        self,
        launch: SignedLaunch,
        *,
        omitting: Sequence[str] = (),
        **overrides: Any,
    ) -> dict[str, Any]:
        """Create one line item and hand back what the platform stored.

        The default body is SPEC §3.4's: one line item per section labelled
        "Pulse Participation", scored out of 100. `resourceId` is drawn fresh per
        call so that a test asking whether *its* line item appears in a listing
        is not answered by a seeded one.

        `omitting` sends a body with those keys **absent**, which `overrides`
        cannot express: `tag=None` posts `{"tag": null}`, and a null member and a
        missing member are two different bodies that a filter is entitled to
        treat differently — the missing one is the case a fail-open filter
        matches. It is a keyword rather than a sentinel value so that the call
        site reads as what it does, and a name that was not there to omit is a
        failure rather than a silent no-op, because a misspelling would
        otherwise leave a test quietly asserting nothing about the body it meant
        to send.
        """
        payload: dict[str, Any] = {
            "scoreMaximum": 100,
            "label": "Pulse Participation",
            "resourceId": f"e0-15-{uuid4().hex[:12]}",
            "tag": "participation",
        }
        payload.update(overrides)
        return self.created_line_item(launch, payload, omitting)

    def post_line_item(
        self,
        launch: SignedLaunch,
        payload: Mapping[str, Any],
    ) -> Any:
        """POST one line-item body and hand back the response, asserting nothing.

        `create_line_item` requires success, which is right for the callers that
        need a line item to work with and wrong for the ones asking what the
        container *refuses*. Those need the raw answer, and they need it without
        knowing the media type AGS fixes for the request.
        """
        return self.service_post(
            self.line_items_url(launch),
            payload,
            LINE_ITEM_MEDIA_TYPE,
            accept=LINE_ITEM_MEDIA_TYPE,
        )

    def created_line_item(
        self,
        launch: SignedLaunch,
        payload: dict[str, Any],
        omitting: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Post `payload`, require it created, and hand back what was stored."""
        for name in omitting:
            if name not in payload:
                pytest.fail(
                    f"`create_line_item(omitting={list(omitting)})` was asked to leave out "
                    f"`{name}`, which this body does not carry — it carries {sorted(payload)}. "
                    "A key that is already absent cannot be omitted, and a misspelling here "
                    "would post the very member the caller meant to leave out."
                )
            payload.pop(name)
        response = self.post_line_item(launch, payload)
        assert response.status_code in (200, 201), (
            f"Creating a line item answered {response.status_code} rather than 200 or 201. E0-15 "
            "criterion 3: line-item creation returns an identifier that score posting accepts. "
            f"Body begins {response.text[:200]!r}."
        )
        created = response.json()
        assert isinstance(created, dict), (
            f"Creating a line item answered {created!r}, which is not an AGS line item. AGS 2.0 "
            "makes it a JSON object whose `id` is the line item's own URL."
        )
        return created

    def with_query(self, url: str, query: Mapping[str, Any]) -> str:
        """`url` with `query` appended to whatever it already carries."""
        return url_with_query(url, query)

    def line_item_container(self, url: str) -> list[dict[str, Any]]:
        """One page of an AGS line-item container, as a list.

        AGS 2.0 serves an array; a mock that wraps it in an object is read here
        rather than failed, because which of the two E0-15 meant is not
        something this file decides — what every caller needs is the line items.
        """
        response = self.service_get(url, accept=LINE_ITEM_CONTAINER_MEDIA_TYPE)
        assert response.status_code == 200, (
            f"Listing line items at `{url}` answered {response.status_code} rather than 200. "
            "E0-15's scope: 'Assignment and Grade Services 2.0 stubs: line-item creation and "
            f"listing'. Body begins {response.text[:200]!r}."
        )
        return self.line_items_of(response)

    def line_items_of(self, response: Any) -> list[dict[str, Any]]:
        """Read the line items out of an already-fetched container page."""
        listed = response.json()
        if isinstance(listed, dict):
            listed = listed.get("lineItems") or listed.get("line_items") or listed.get("items")
        assert isinstance(listed, list), (
            f"Listing line items answered {response.json()!r}, which is not a line item "
            "container. AGS 2.0 serves an array of line items."
        )
        return [item for item in listed if isinstance(item, dict)]

    def line_items(self, launch: SignedLaunch, **query: Any) -> list[dict[str, Any]]:
        """The line items the platform lists for this launch's context, one page.

        `query` is passed to the container as it stands, so a test asking for
        `resource_id=…` is asking the platform the question AGS 2.0 defines
        rather than filtering the answer itself — which is the only way to tell a
        platform that honours the filter from one that accepts it and ignores it.
        """
        return self.line_item_container(self.with_query(self.line_items_url(launch), query))

    def line_item_pages(self, launch: SignedLaunch, **query: Any) -> list[list[dict[str, Any]]]:
        """Every page of the line-item container, walked by `Link` as the roster is."""
        return [
            self.line_items_of(response)
            for _, response in self.link_walk(
                self.with_query(self.line_items_url(launch), query),
                LINE_ITEM_CONTAINER_MEDIA_TYPE,
                "line item container",
            )
        ]

    def scores_url(self, line_item: Mapping[str, Any]) -> str:
        """Where AGS puts one line item's Score service.

        `{lineitem}/scores` is the specification's own construction rather than
        this file's guess: AGS 2.0 defines the Score service as the line item URL
        with `/scores` appended, which is why criterion 3 can speak of an
        identifier "that score posting accepts" without naming a second URL.

        The *appending* is `path_appended`'s, not a concatenation, because a line
        item id may carry a query and the segment goes before it. See that
        function for the platform this is true of and what concatenation does
        there; E0-28 item 3 makes this helper the client a test models.
        """
        return path_appended(self.line_item_id(line_item), "scores")

    def results_url(self, line_item: Mapping[str, Any]) -> str:
        """Where AGS puts one line item's Result container. Same insertion rule."""
        return path_appended(self.line_item_id(line_item), "results")

    def post_score(self, line_item: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
        """POST one score against a line item, to the URL AGS derives from its `id`."""
        return self.service_post(self.scores_url(line_item), payload, SCORE_MEDIA_TYPE)

    def line_item_id(self, line_item: Mapping[str, Any]) -> str:
        """A line item's own URL, or a failure saying it has none."""
        identifier = line_item.get("id")
        if not isinstance(identifier, str) or not identifier:
            pytest.fail(
                f"The line item {line_item!r} carries no `id`, so there is no URL to address it "
                "by. E0-15 criterion 3: 'AGS line-item creation returns an identifier that score "
                "posting accepts.'"
            )
        return identifier

    def posted_scores(self) -> list[dict[str, Any]]:
        """Every score the platform has been sent, in the order it received them.

        E0-15 settles this surface rather than leaving it to be discovered:
        `GET /mock/posted-scores`, outside the AGS namespace, answering
        `{"scores": [{"lineItem": …, "score": {…}}]}` in arrival order (ADR
        0047). So the shape is asserted here rather than normalised — an earlier
        version of this helper accepted four shapes because the ticket named
        none, and every one of the three it no longer accepts is now a mock that
        does not do what the ticket says.
        """
        response = self.service_get(MOCK_POSTED_SCORES_PATH)
        assert response.status_code == 200, (
            f"`GET {MOCK_POSTED_SCORES_PATH}` answered {response.status_code} rather than 200. "
            "E0-15 criterion 4 reads a posted score back from exactly this route, outside the AGS "
            f"namespace. Body begins {response.text[:200]!r}."
        )
        document = response.json()
        assert isinstance(document, dict), (
            f"`{MOCK_POSTED_SCORES_PATH}` served {document!r}. E0-15 spells the body "
            '`{"scores": [{"lineItem": …, "score": {…}}]}`.'
        )
        entries = document.get("scores")
        assert isinstance(entries, list), (
            f"`{MOCK_POSTED_SCORES_PATH}` served an object carrying {sorted(document)} rather "
            "than a `scores` array. A bare array, or the scores under another key, is a shape "
            "E0-15 does not describe and a test cannot read as arrival order."
        )
        return [entry for entry in entries if isinstance(entry, dict)]

    def posted_scores_for(self, line_item: Mapping[str, Any]) -> list[dict[str, Any]]:
        """The scores posted to one line item, in the order they arrived."""
        identifier = self.line_item_id(line_item)
        return [entry for entry in self.posted_scores() if entry.get("lineItem") == identifier]

    def results(self, line_item: Mapping[str, Any], **query: Any) -> list[dict[str, Any]]:
        """The conformant AGS Result container for one line item, **one page of it**.

        The other half of E0-15's readback, and the one E3 is built against. AGS
        2.0 puts the Result service at the line item URL with `/results`
        appended, and a `Result` carries `userId`, `resultScore`,
        `resultMaximum` and `scoreOf` — no timestamp, no progress. That absence
        is a criterion of its own, which is why this is reached separately from
        `posted_scores` rather than folded into it.

        One page, said in the summary line rather than in a footnote, because
        E0-28 item 4 makes this container page: every caller here posts a handful
        of scores and reads them off the first page, and a caller that posts more
        than a page's worth wants `result_pages` below. A test comparing "the
        container before" with "the container after" through this method is
        comparing two page-sized windows, which is `docs/MISTAKES.md` entry 3
        with a bound instead of a zero.
        """
        return self.result_page(self.with_query(self.results_url(line_item), query)).results

    def result_page(self, url: str) -> ResultPage:
        """Fetch one page of a result container and read its paging header."""
        response = self.service_get(url, accept=RESULT_CONTAINER_MEDIA_TYPE)
        assert response.status_code == 200, (
            f"The AGS Result service answered {response.status_code} for `{url}`. E0-15: 'The "
            "conformant AGS Results endpoint answers for the same line item.' Body begins "
            f"{response.text[:200]!r}."
        )
        return self.result_page_of(url, response)

    def result_page_of(self, url: str, response: Any) -> ResultPage:
        """Read one already-fetched result page, header and all.

        Split from the fetch for the reason `membership_page_of` is: the walk and
        a caller asking for a single page build a page from one place.
        """
        listed = response.json()
        if isinstance(listed, dict):
            listed = listed.get("results")
        assert isinstance(listed, list), (
            f"The AGS Result service served {response.json()!r} for `{url}`, which is not a "
            "result container. AGS 2.0 serves an array of results."
        )
        header = response.headers.get("link")
        return ResultPage(
            url=url,
            status_code=response.status_code,
            results=[result for result in listed if isinstance(result, dict)],
            link_header=header,
            relations=link_relations(header),
        )

    def result_pages(self, line_item: Mapping[str, Any], **query: Any) -> list[ResultPage]:
        """Every page of one line item's result container, walked by `Link`.

        The same walk the roster and the line-item container use, which is E0-28
        item 4's own requirement — "a test walks it the way the roster walk does"
        — and the reason it is the same `link_walk` rather than a second one is
        that the two ways of not terminating are already named there.
        """
        return [
            self.result_page_of(page_url, response)
            for page_url, response in self.link_walk(
                self.with_query(self.results_url(line_item), query),
                RESULT_CONTAINER_MEDIA_TYPE,
                "result container",
            )
        ]


@pytest.fixture
def repo_root() -> Path:
    """The repository root, for the tests that sweep the whole tree."""
    return REPO_ROOT


@pytest.fixture
def mock_lms_dir() -> Path:
    """Where the mock platform must live (SPEC §13). Asserted by the test, not here."""
    return MOCK_LMS_DIR


@pytest.fixture
def mock_lms_service() -> str:
    """The Compose service name SPEC §7.2 gives the mock platform."""
    return MOCK_LMS_SERVICE


@pytest.fixture
def mock_lms_config() -> Iterator[Any]:
    """The mock platform's `app.config` module, with `mock-lms/`'s `app` resolving.

    The twin of `mock_idp_settings` further down, and it exists for the same kind
    of reason: some of the platform's identity is **not** in the Compose file, so
    a test comparing the seeded registration against Compose literals has nothing
    to hold that part against. `JWKS_PATH` is the one that matters — the platform
    composes its key-set URL from its own issuer, so `docker-compose.yml` never
    carries it and a drift guard whose inventory is that file structurally cannot
    see it.

    The resolution is held open for the body rather than just for the import, the
    way `mock_package_resolved` explains.
    """
    if not MOCK_LMS_DIR.is_dir():
        pytest.fail(
            f"{MOCK_LMS_DIR} does not exist, so there is no configuration module to import. "
            "SPEC §13 puts the in-repo LTI 1.3 platform at `mock-lms/`, and E0-14 is the ticket "
            "that writes it."
        )
    with mock_package_resolved(MOCK_LMS_DIR):
        yield importlib.import_module(f"{MOCK_PACKAGE}.config")


class MockLmsPaths(NamedTuple):
    """The mock platform's own route paths, as strings, with nothing held open."""

    jwks: str
    authorization: str


@pytest.fixture
def mock_lms_paths() -> MockLmsPaths:
    """The two paths a registration is built from, read out and the resolution closed.

    **Why this exists beside `mock_lms_config` rather than instead of it.** That
    fixture holds `mock_package_resolved(MOCK_LMS_DIR)` open for the whole test
    body, deliberately and correctly — a class taken out of a mock and used after
    the resolution closed would re-resolve its lazy imports against this
    repository's own `app`, which is a different program. The cost is stated in
    `tests/fixtures/app_imports.py`'s docstring and is absolute: while the mock's
    `app` is resolved, **this repository's `app` is not importable**, so nothing
    that imports it may run in that window.

    An in-process `alembic upgrade head` is exactly such a thing — the first line
    of `backend/migrations/env.py` is `from app.models import Base` — so a test
    that requests `mock_lms_config` and then builds a database dies in
    `ModuleNotFoundError` before its first assertion, and no change on the
    implementation side of the wall can help it. That was measured and ruled on
    in `docs/disputes/E1-05-02.md`.

    So this reads the *values* out while the resolution is briefly open and lets
    it close before the caller's body runs — the shape
    `tests/fixtures/doors.py::seed_constant` already uses, for the reason its own
    docstring gives. Both are plain strings, so nothing is lost by copying them
    out. A test that needs the live module and never migrates anything can go on
    asking for `mock_lms_config`.

    The two paths are the ones a `lti_platform` registration is composed from:
    the key set the launch signature is verified against, and the authorization
    endpoint a browser is sent to. Both are validated here rather than in the
    caller, because "absolute path" is a property of the mock's configuration and
    not an assertion any one test owns.
    """
    if not MOCK_LMS_DIR.is_dir():
        pytest.fail(
            f"{MOCK_LMS_DIR} does not exist, so there is no configuration module to read the "
            "platform's own paths out of. SPEC §13 puts the in-repo LTI 1.3 platform at "
            "`mock-lms/`, and E0-14 is the ticket that writes it."
        )
    with mock_package_resolved(MOCK_LMS_DIR):
        configuration = importlib.import_module(f"{MOCK_PACKAGE}.config")
        found = {
            name: getattr(configuration, name, None) for name in ("JWKS_PATH", "AUTHORIZATION_PATH")
        }

    wrong = {
        name: value
        for name, value in found.items()
        if not isinstance(value, str) or not value.startswith("/")
    }
    if wrong:
        pytest.fail(
            f"`mock-lms/app/config.py` defines no absolute {sorted(wrong)} (found {wrong}). That "
            "module declares the platform's routes and builds the URLs its discovery document "
            "advertises, and a registration composed from a missing path would be checked against "
            "an absence."
        )
    return MockLmsPaths(
        jwks=str(found["JWKS_PATH"]), authorization=str(found["AUTHORIZATION_PATH"])
    )


@pytest.fixture
def mock_platforms() -> Iterator[Callable[..., MockPlatform]]:
    """Start one or more independent mock platforms, and shut them all down after.

    A factory rather than a single instance because two of E0-14's criteria are
    about *two* platforms: issuer keys generated per run means a second start
    generates a second key, and a key set that verifies its own launches has to
    refuse someone else's. Neither is observable from one instance.
    """
    started: list[MockPlatform] = []

    def start(
        values: Mapping[str, str] | None = None, tool_key_set: Any | None = None
    ) -> MockPlatform:
        platform = MockPlatform(values, tool_key_set)
        started.append(platform)
        return platform

    try:
        yield start
    finally:
        for platform in reversed(started):
            platform.close()


@pytest.fixture
def mock_platform(mock_platforms: Callable[..., MockPlatform]) -> MockPlatform:
    """One mock platform, started fresh for this test. See `MockPlatform` above."""
    return mock_platforms()


@pytest.fixture
def signed_launch(mock_platform: MockPlatform) -> SignedLaunch:
    """One signed launch off the first seeded offer.

    E0-14's definition of done names this: "a reusable fixture that mints a
    signed launch — E1's launch-validation tests depend on it, so its interface
    matters". `mock_platform.mint(...)` is the interface; this fixture is the
    common case of it.
    """
    return mock_platform.mint()


@pytest.fixture
def link_relations_in() -> Callable[[str | None], dict[str, str]]:
    """Hand `link_relations` to a test that checks the parser itself.

    The walk in `MockPlatform.membership_pages` reads paging headers with this
    same function, so the control test and the thing it controls cannot end up
    disagreeing about what a `Link` header says — which is the whole value of
    the control (`docs/MISTAKES.md` entry 3: run the pattern against the text
    you claim it catches *and* against the text you claim it allows).
    """
    return link_relations


@pytest.fixture
def path_appended_to() -> Callable[[str, str], str]:
    """Hand `path_appended` to the control test that checks the insertion itself.

    `MockPlatform.scores_url` and `MockPlatform.results_url` build every AGS
    service URL with this same function, so the control and the thing it controls
    cannot disagree about where a path segment goes — which is the whole value of
    a control (`docs/MISTAKES.md` entry 3).
    """
    return path_appended


@pytest.fixture
def instant_of() -> Callable[[Any], datetime | None]:
    """Hand `instant` to a test that has to compare two spellings of one moment.

    The seeded rosters ask it: an enrollment window's `start` and `end` are
    moments, and whether one member enrolled after another is a question about
    instants rather than about strings.

    **The AGS round trip deliberately does not**, and the asymmetry is worth
    knowing before someone tidies it away. E0-15 records a posted score "the
    posted body, verbatim" (ADR 0047), so there the spelling *is* the fact: a
    recorder that re-renders `+00:00` as `Z` has stopped carrying what the tool
    sent, and comparing instants would call that agreement.
    """
    return instant
