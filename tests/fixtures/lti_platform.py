"""The mock LTI 1.3 platform's names, and the JWS, HTML and URL helpers.

Where the mock platform lives, what its package is called, and the pieces both
mocks read a response with: a compact JSON Web Signature split and verified, the
forms on an HTML page, and the URL arithmetic a service client does. They are
here rather than beside either driver because both mocks ask the same questions
of them (`docs/MISTAKES.md` entry 13); `fixtures/lti_services.py` holds the
platform driver itself and `fixtures/mock_idp.py` the provider's.
"""

import base64
import hashlib
import hmac
import itertools
import json
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any, NamedTuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest

from fixtures.repo import REPO_ROOT

# ---------------------------------------------------------------------------
# E0-14 — the mock LTI 1.3 platform, driven the way a tool drives one.
# ---------------------------------------------------------------------------

# SPEC §13 spells the directory and the package inside it: `mock-lms/` holding a
# `Dockerfile` and an `app/`. Nothing else about the module layout is written
# down, so the application object is discovered rather than imported by name.
MOCK_LMS_DIR = REPO_ROOT / "mock-lms"
MOCK_LMS_SERVICE = "mock-lms"

# The package name **both** mocks use, because SPEC §13 gives each of them an
# `app/` beside a Dockerfile. It is the whole reason `MockPackageFinder` below
# exists, and it is one constant rather than one per mock so that the collision
# is described once.
MOCK_PACKAGE = "app"

# Where the ASGI application might sit inside that package, most likely first.
# `backend/` puts its own in `app.main`, so a mock written beside it probably
# does too; the rest are here so that a different arrangement is found rather
# than reported as a missing deliverable.
MOCK_LMS_MODULES = ("app.main", "app", "app.platform", "app.server", "app.api")

# Names a zero-argument application factory might carry, if the mock exposes one
# instead of a module-level instance. `backend/app/main.py` uses `create_app`,
# and `uvicorn --factory` is what makes that legal, so the mock may well too.
APPLICATION_FACTORY_NAMES = ("create_app", "get_app", "make_app", "build_app")

# How many launches a page offering several users, contexts or roles is walked
# for. **This suite's choice**, and a bound rather than a rule: the seeded data
# is meant to be small (E0-15: "this seed data belongs to the mock platform and
# stays small"), and a page offering more combinations than this is still walked,
# just not exhaustively. Raise it if a seed grows and a test starts missing a
# shape it names.
MAX_LAUNCH_VARIANTS = 32

# The parameters a tool sends to a platform's authorization endpoint for a plain
# resource-link launch. These are the OIDC and LTI 1.3 required values, not this
# suite's preferences: `id_token` with `form_post` and `prompt=none` is what the
# LTI 1.3 security framework specifies, and a platform that answered anything
# else would not be strict LTI 1.3 core (SPEC §7.3).
AUTHORIZATION_REQUEST_CONSTANTS = {
    "scope": "openid",
    "response_type": "id_token",
    "response_mode": "form_post",
    "prompt": "none",
}

# The DigestInfo prefix PKCS#1 v1.5 puts in front of a SHA-256 digest, from
# RFC 8017 appendix B.1. Nineteen bytes, and the whole of what makes an RS256
# verification a verification rather than a decode.
SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def base64url_decode(value: str) -> bytes:
    """Decode one base64url segment, supplying the padding JWS omits."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class JsonWebSignature(NamedTuple):
    """A compact JWS, split into the parts a verification needs.

    `signing_input` is the exact bytes that were signed — the encoded header and
    payload with the dot between them — and it is kept rather than recomputed so
    that a caller checking a *tampered* token compares against what the tamper
    produced.
    """

    header: dict[str, Any]
    claims: dict[str, Any]
    signing_input: bytes
    signature: bytes


def split_jws(token: str) -> JsonWebSignature:
    """Split a compact JWS, failing with the token in hand if it is not one."""
    parts = token.split(".")
    if len(parts) != 3:
        pytest.fail(
            f"The mock platform issued a value with {len(parts)} dot-separated segments rather "
            "than the three a compact JSON Web Signature has, so it is not a signed `id_token`. "
            f"It begins {token[:64]!r}."
        )
    encoded_header, encoded_claims, encoded_signature = parts
    try:
        header = json.loads(base64url_decode(encoded_header))
        claims = json.loads(base64url_decode(encoded_claims))
    except ValueError as failure:
        # `json.JSONDecodeError` and `binascii.Error` are both `ValueError`
        # subclasses, so this one clause covers a segment that is not base64url
        # and a segment that decodes to something that is not JSON.
        pytest.fail(f"The `id_token`'s header or payload is not base64url-encoded JSON: {failure}")
    return JsonWebSignature(
        header=header,
        claims=claims,
        signing_input=f"{encoded_header}.{encoded_claims}".encode("ascii"),
        signature=base64url_decode(encoded_signature),
    )


def verify_rs256(signing_input: bytes, signature: bytes, key: Mapping[str, Any]) -> bool:
    """Whether `signature` is an RS256 signature over `signing_input` under `key`.

    Written out of `pow` and `hashlib` rather than taken from a library, because
    nothing in this project's locked dependency set verifies a JWS and adding one
    to satisfy a test would decide, from the test side, which JOSE library the
    mock signs with. RSA *verification* is public-exponent modular
    exponentiation and a padding comparison, so the whole of it is below.

    The comparison is against the full PKCS#1 v1.5 encoded message, padding
    included, which is what makes this a real check: a verifier that compared
    only the trailing digest would accept a signature with forged padding, and a
    verifier that only decoded the token would accept anything at all. The tests
    that hand this a wrong key and a tampered payload are what prove it says no.
    """
    if key.get("kty") != "RSA":
        return False
    try:
        modulus = int.from_bytes(base64url_decode(str(key["n"])), "big")
        exponent = int.from_bytes(base64url_decode(str(key["e"])), "big")
    except (KeyError, ValueError, TypeError):
        return False
    if modulus <= 0 or exponent <= 0:
        return False

    width = (modulus.bit_length() + 7) // 8
    if len(signature) != width:
        return False
    numeric = int.from_bytes(signature, "big")
    if numeric >= modulus:
        return False

    encoded = pow(numeric, exponent, modulus).to_bytes(width, "big")
    digest_info = SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(signing_input).digest()
    if width < len(digest_info) + 11:
        return False
    expected = b"\x00\x01" + b"\xff" * (width - len(digest_info) - 3) + b"\x00" + digest_info
    return hmac.compare_digest(encoded, expected)


def verifying_key(signature: JsonWebSignature, key_set: Mapping[str, Any]) -> dict[str, Any] | None:
    """The key in `key_set` that verifies `signature`, or `None` if none does.

    Every key is tried, not just the one the header's `kid` names. That is
    deliberate: whether the header selects the right key and whether the key set
    contains a key that works are two different claims, and one test asserts each.
    Trying only the named key would fold them together, so a mock that published
    the right key under the wrong `kid` would fail both tests with one cause.
    """
    keys = key_set.get("keys")
    if not isinstance(keys, list):
        return None
    for key in keys:
        if isinstance(key, dict) and verify_rs256(
            signature.signing_input, signature.signature, key
        ):
            return key
    return None


class FormReader(HTMLParser):
    """Every form on an HTML page, with the fields it would submit.

    A parser rather than a regular expression, because what is being read is the
    launch page's contract with a browser — a form's action, its method, and the
    named values it carries — and a pattern over markup answers a different
    question that happens to look the same (`docs/MISTAKES.md` entry 3).

    `<select>` options are collected separately from fixed fields, because a
    launch page offering a choice of seeded users is one form with several
    outcomes, and the tests about "an arbitrary seeded user" need each outcome.

    **E0-16 widened what counts as a choice, and added `controls` and `labels`.**
    A login form offering six seeded identities is the same shape as a launch page
    offering several users, and it can legitimately be written three ways: a
    `<select>`, a set of same-named radio buttons, or a set of same-named submit
    buttons. All three are now read as choices, so the provider can be driven
    whichever the implementer picked — none of the launch pages has a radio or a
    named button, so nothing E0-14 or E0-15 asserts changes. `controls` and
    `labels` answer a different question again: whether a Playwright test could
    address the form without a brittle selector, which needs each control's
    attributes rather than the value it would submit.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.open_select: str | None = None
        self.open_option: str | None = None
        self.option_text: str = ""

    def current(self) -> dict[str, Any] | None:
        return self.forms[-1] if self.forms else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}
        if tag == "form":
            self.forms.append(
                {
                    "action": attributes.get("action", ""),
                    "method": (attributes.get("method") or "get").lower(),
                    "fields": {},
                    "choices": {},
                    "controls": [],
                    "labels": [],
                }
            )
            return
        form = self.current()
        if form is None:
            return
        if tag == "label":
            form["labels"].append(attributes.get("for", ""))
            return
        if tag in {"input", "textarea", "select", "button"}:
            form["controls"].append({"tag": tag, **attributes})
        if tag in {"input", "textarea"}:
            name = attributes.get("name")
            kind = attributes.get("type", "text").lower()
            if not name:
                return
            if kind in {"radio", "checkbox"}:
                # One of several values under one name: a choice, not a fixed
                # field. Recording it as a field would keep only the last one and
                # silently shrink the set of identities a login form offers.
                form["choices"].setdefault(name, []).append(attributes.get("value", "on"))
            else:
                form["fields"][name] = attributes.get("value", "")
        elif tag == "button":
            name = attributes.get("name")
            kind = (attributes.get("type") or "submit").lower()
            if name and kind == "submit":
                form["choices"].setdefault(name, []).append(attributes.get("value", ""))
        elif tag == "select":
            self.open_select = attributes.get("name") or None
            if self.open_select:
                form["choices"].setdefault(self.open_select, [])
        elif tag == "option" and self.open_select:
            # Closed here as well as on `</option>`, because HTML permits the
            # end tag to be omitted and a page that omits it would otherwise
            # lose every option but the last — which would silently shrink the
            # set of seeded launches the tests walk.
            self.close_option()
            self.open_option = attributes.get("value")
            self.option_text = ""

    def handle_data(self, data: str) -> None:
        if self.open_option is None and self.open_select:
            self.option_text += data

    def close_option(self) -> None:
        form = self.current()
        if form is None or not self.open_select:
            return
        value = self.open_option if self.open_option is not None else self.option_text.strip()
        if value:
            form["choices"][self.open_select].append(value)
        self.open_option = None
        self.option_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            self.close_option()
        elif tag == "select":
            self.close_option()
            self.open_select = None


def forms_in(markup: str) -> list[dict[str, Any]]:
    """Parse `markup` and hand back every form it declares."""
    reader = FormReader()
    reader.feed(markup)
    reader.close()
    return reader.forms


def form_submissions(form: Mapping[str, Any]) -> list[dict[str, str]]:
    """Every set of values `form` could submit, one per combination of choices."""
    choices = form.get("choices") or {}
    names = sorted(name for name, options in choices.items() if options)
    if not names:
        return [dict(form.get("fields") or {})]
    submissions: list[dict[str, str]] = []
    for combination in itertools.islice(
        itertools.product(*(choices[name] for name in names)), MAX_LAUNCH_VARIANTS
    ):
        values = dict(form.get("fields") or {})
        values.update(dict(zip(names, combination, strict=True)))
        submissions.append(values)
    return submissions


class LaunchOffer(NamedTuple):
    """One launch the platform's launch page offers a browser.

    `posts_to` is the form's action — the tool's third-party login-initiation
    URL — and `parameters` is what the form would send it. Those parameters are
    the OIDC third-party-initiated login request, so they are also where a test
    learns the seeded registration's issuer, client ID and deployment ID without
    any endpoint being invented to publish them.
    """

    page: str
    posts_to: str
    method: str
    parameters: dict[str, str]


class SignedLaunch(NamedTuple):
    """The result of driving one launch to the point the tool would receive it."""

    offer: LaunchOffer
    authorization_request: dict[str, str]
    id_token: str
    state: str | None
    posted_to: str | None
    signature: JsonWebSignature

    @property
    def claims(self) -> dict[str, Any]:
        return self.signature.claims

    @property
    def header(self) -> dict[str, Any]:
        return self.signature.header


def local_target(url: str) -> str:
    """`url` as an in-process test client can request it: its path and query.

    A mock advertises itself with absolute URLs built from whatever public base
    it is configured with, and that host is one a `TestClient` neither can nor
    should resolve — what is under test is the mock's own routing. Both mocks ask
    this question, so it is answered once (`docs/MISTAKES.md` entry 13).
    """
    split = urlsplit(url)
    target = split.path or "/"
    return f"{target}?{split.query}" if split.query else target


def origin_of(url: str) -> str:
    """The scheme-and-authority of `url`, with the path stripped — its origin.

    Two suites ask this of the same column. The developer console links to the
    origin of a registered platform's `authorization_endpoint`, and the framing
    policy admits that same origin as a `frame-ancestors` source — so it is
    answered once rather than once per module (`docs/MISTAKES.md` entry 13).

    Always applied to a value the *test* registered, never to anything the
    application computed, so the expectation and the thing under test cannot
    become one string (`docs/MISTAKES.md` entry 19).
    """
    split = urlsplit(url)
    return f"{split.scheme}://{split.netloc}"


def url_with_query(url: str, query: Mapping[str, Any]) -> str:
    """`url` with `query` appended to whatever it already carries.

    Both mocks ask this — the platform to filter a line-item container, the
    provider to send a parameter in the query as well as in the body — so it is
    answered once (`docs/MISTAKES.md` entry 13). Appends rather than replaces: a
    name already in the URL and the same name added here is a URL carrying it
    twice, which for the provider is the whole question.
    """
    if not query:
        return url
    split = urlsplit(url)
    merged = parse_qsl(split.query) + [(name, str(value)) for name, value in query.items()]
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(merged), split.fragment))


def path_appended(url: str, segment: str) -> str:
    """`url` with `segment` added to its path, **before** any query it carries.

    **The hazard this exists for is Moodle's.** AGS 2.0 derives the Score and
    Result services from a line item's own `id` by appending `/scores` or
    `/results` to it, and every worked example in the specification shows an id
    that is a bare path — so `id + "/scores"` is right, forever, against a
    platform whose ids carry no query. Moodle's line item ids carry one:
    `…/lineitems/3/lineitem?type_id=1`, and the segment belongs *before* it.
    Concatenation there produces `…/lineitem?type_id=1/scores`, which is a
    request to the line item itself carrying a nonsense query — a URL that is
    well-formed, that some platform will answer with something, and that posts
    no score anywhere.

    This is the client E0-28 item 3 says a test must model, so it lives in one
    place and both service URLs are built from it (`docs/MISTAKES.md` entry 13:
    a hazard written down and worked around in only one of the two places facing
    it is not worked around). It is correct for a bare id too — that is what
    lets it land before the platform mints a querified one, without a single
    existing assertion moving.
    """
    split = urlsplit(url)
    path = f"{split.path.rstrip('/')}/{segment.strip('/')}"
    return urlunsplit((split.scheme, split.netloc, path, split.query, split.fragment))


def declared_paths(application: Any, method: str = "GET") -> list[str]:
    """Every path `application` declares that answers `method` and takes no parameter.

    No path parameter, so a caller can fetch every one of them without inventing
    a value — which is what makes "walk what this service serves" safe to do at
    all. Shared by both mocks for the reason `local_target` above is.
    """
    found: list[str] = []
    for route in application.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if isinstance(path, str) and "{" not in path and method in methods:
            found.append(path)
    return sorted(set(found))
