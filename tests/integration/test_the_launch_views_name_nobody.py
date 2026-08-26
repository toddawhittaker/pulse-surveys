"""The launch door's two landing pages name nobody — SPEC §4.1, ticket E0-41.

`POST /lti/launch` is the only door a student can enter through, and until E0-41
it carried no `invariant`-marked test at all: the web door's landing pages had
three, this door had none, so the isolated §4.1 pass — the one CLAUDE.md says may
never be skipped — walked past the student page entirely.

**What is asserted, and against what.** SPEC §4: "Identity is never displayed to
instructors or any leadership role, in any view, including CSV exports", and
§4.1 item 1 keeps comparables, benchmarks and other sections away from students.
E0-18 rendered both of these as empty pages by design — no purview was computed
(ADR 0003), no roster synced, no report existed — and E1-08 removes the page
itself, answering a `302` and a session instead (see "Reconciled for E1-08"
below). Either way the honest reading for these two surfaces is: nothing this
door answers with names anybody but the person who launched, and none of it
carries a section code, a course number or a roster count. Each is asserted
against **what a browser actually received** — the rendered body while E0-18
stood, `response_surface` (headers, body and the session token's own decoded
claims) since E1-08 — exactly as `tests/integration/test_web_login_door.py`'s
three landing invariants are: what a browser received, not what a function
returned.

**Every value scanned for is live.** The people come from the launches the mock
platform signs and from the NRPS rosters it serves; the section codes and course
numbers come from the three places a section names itself to a tool (§2.2's
`{startLetter}{ordinal}{modality}` and §8's numbered prefix, read out of the
context claim, the resource link claim and the membership container). Nothing
here is transcribed from `mock-lms/app/seed.py`, so a reseeding cannot leave this
module quietly asserting about people and sections that are no longer there.

**The mutations these exist to kill**, and the near miss that decides whether a
green means anything:

  - a landing page gaining a seeded person's display name or address — the
    "signed in as" line somebody adds because it is friendly, or a roster the
    page fetches because the data is right there in the launch;
  - a landing page gaining the launched section's code or course number — the
    context header that reads `NURS 8100 · Q2FF`, which is the most natural
    thing in the world to put on a page rendered from a launch and is the one
    string §2.2 makes a section identifiable by;
  - a landing page gaining a roster count — "23 students enrolled", which is a
    figure about a section computed from data this door has no business reading;
  - **the near miss**: the assertion passing because the fixture provoked a
    refusal instead of a real launch. A 4xx names nobody either. So every test
    below lands first — `redirected_to_role` requires the `302` this door
    answers with on the happy path, to the right role's route, since E1-08
    (`lands_on`'s `200` + testid before it) — and then shows its scan finding
    the very strings it is about to report absent (`docs/MISTAKES.md` entry
    3).

**What is deliberately not asserted here.** The ticket's criterion also names a
"comparison figure". Nothing in E0 computes one: there is no comparison set, no
benchmark minimum and no report, and SPEC §4.1 item 7 says in as many words that
it is "asserted from **E4**, the epic that builds the reports carrying these
figures". A test written here could only assert that a number nobody computes is
absent, which is an assertion about emptiness dressed as a confidentiality check.
The roster count is the numeric half that *can* be posed today, because the
platform really does publish rosters this door could count, and it is posed
below. E4 owns the comparison figure.

**Why the launching person's own identifiers are excluded from the scan**, the
same decision `test_web_login_door.py::identifying_strings` makes: a page naming
who is signed in is legitimate and is a product decision E1 may take, while a
page naming *anybody else* has enumerated people — and there is nowhere in E0
that list could legitimately have come from. Asserting that a student's page
never says the student's own name would be this module inventing a rule no
record states, and it would go red against a perfectly correct greeting.

**Nothing is imported from `test_lti_launch_door.py`**, whose machinery this
module drives launches with. A test module importing its sibling depends on where
pytest put `tests/` on `sys.path`, and an import error is not a red — the same
reason `test_web_login_door.py` keeps its own copy of the platform's variable
names rather than reaching next door for them.

**Reconciled for E1-08, arbitrated by dispute E1-08-03.** E1-08 retires the
`200` + inline landing HTML this whole module was written against: a valid
launch now answers a `302` to `/app/<role>#session=<jwt>` (ADR 0089), with the
session and CSRF cookies set, and renders no page at all on the happy path.
That is not a weaker confidentiality surface — it is a smaller one, and this
module's invariants move with it rather than being dropped. `lands_on`
(`200` + testid) is replaced by `redirected_to_role` (`302` +
`/app/<role>#session=`); every scan that used to read `response.text` alone
now reads `response_surface` — the response's headers (`Location`
included, still in its raw encoded form, and every `Set-Cookie`), its body
(normally empty; scanned anyway), and the session token's own claims,
decoded (not verified — a confidentiality scan does not need the signature
checked to read what anyone intercepting the redirect already could) and
stringified. The `RenderedText` HTML reader and the CSS/SVG-shaped plants it
existed to see past are gone with the markup they read: there is no
stylesheet, no graphic and no rendered text left to confuse a scan, so a
direct regex match over the response surface is simpler and at least as
strict. What is unchanged is the shape of every test: land, scan for a
specific class of leak, and prove first that the scan can find what it is
about to report absent.
"""

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The mock platform's configuration surface, from `mock-lms/app/config.py`, set so
# that its launch form posts at *this* tool and its authorization endpoint accepts
# this tool's `redirect_uri`. Spelled as `tests/integration/test_lti_launch_door.py`
# spells them.
MOCK_LMS_TOOL_LOGIN_URL_VARIABLE = "MOCK_LMS_TOOL_LOGIN_URL"
MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE = "MOCK_LMS_TOOL_LAUNCH_URL"

# Where this platform's registration says to send a browser to begin the launch —
# a column since E1-05, a setting before it. `.invalid` is reserved by RFC 2606;
# the value is one no implementation could arrive at by accident, which is why
# the launch-door module chose it and why this one reuses the spelling rather
# than inventing a second.
CONFIGURED_AUTHORIZATION_ENDPOINT = "http://lti-platform.invalid/e0-18-configured-authorize"

# The LTI 1.3 claims this module reads, spelled as the specification spells them.
LTI_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
ROLES_CLAIM = LTI_CLAIM + "roles"
CONTEXT_CLAIM = LTI_CLAIM + "context"
RESOURCE_LINK_CLAIM = LTI_CLAIM + "resource_link"

# The two LIS v2 membership roles E0-18's landing rule dispatches on, and the two
# views it dispatches them to.
MEMBERSHIP_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTRUCTOR_ROLE_URI = f"{MEMBERSHIP_ROLE}Instructor"
LEARNER_ROLE_URI = f"{MEMBERSHIP_ROLE}Learner"

# E1-04's route group names — "student, instructor, leadership, care, admin"
# — used here only as the path segment `redirected_to_role` expects,
# `/app/<role>`. Replaces the `pulse-landing-*` testid constants E0-18's
# inline HTML carried; there is no testid left to carry one.
STUDENT_ROLE = "student"
INSTRUCTOR_ROLE = "instructor"

# The two ways this door answers, as the parameters of every test below. Both
# are asserted by every rule here rather than one each: an instructor response
# naming students and a student response naming classmates are the same
# defect, and a rule proved on one says nothing about the other.
LANDING_PAGES = (
    pytest.param(LEARNER_ROLE_URI, STUDENT_ROLE, id="student"),
    pytest.param(INSTRUCTOR_ROLE_URI, INSTRUCTOR_ROLE, id="instructor"),
)

# Where a person's name, address or subject rides — in a launch's claims (the
# standard OpenID Connect members LTI 1.3 carries) and in an NRPS member (NRPS 2.0
# spells the subject `user_id`). A member outside this set is not read: `roles`,
# `status` and the enrollment extension are about a membership rather than about a
# human, and scanning a landing page for the word `Learner` would report the
# student view's own testid as a leaked identity.
PERSON_MEMBERS = ("name", "given_name", "family_name", "middle_name", "email", "sub", "user_id")

# §2.2's section code as a whole token — `{startLetter}{ordinal}{modality}`, e.g.
# `R3WW`, `Q2FF`. Uppercase only, and that narrowing is deliberate rather than a
# claim that a lowercase code is illegal: a hexadecimal fragment of a UUID can
# spell `a1ff`, and a case-insensitive scan of a rendered page would find section
# codes that are not there. `tests/integration/test_mock_lms_seed_data.py` reads
# the platform's own strings with this same pattern and says the same thing about
# it; both are transcriptions of §2.2 rather than two copies of a choice.
SECTION_CODE = re.compile(r"^(?P<letter>[A-Z])(?P<ordinal>[0-9]{1,2})(?P<modality>WW|FF)$")

# A course number as it is written beside a prefix: `BIOL 215`, `ITEC 8100`.
# Searched inside a string because the space is part of how it is written, and
# transcribed from §8 the same way.
COURSE_NUMBER = re.compile(r"\b(?P<prefix>[A-Z]{2,4})[ -]?(?P<number>[0-9]{3,4})\b")

# Letter groups that are not a course prefix, so a term written in capitals —
# `FALL 2026` — is not read as course number 2026. Copied from
# `test_mock_lms_seed_data.py`, which needs the same guard against the same seed;
# if it ever suppresses a real prefix that is a defect in both copies.
NOT_A_COURSE_PREFIX = frozenset({"AY", "FA", "FALL", "SP", "SPR", "SU", "SUM", "TERM", "WI", "WIN"})

# How a roster member's role is recognised whichever vocabulary spelled it: NRPS
# 2.0's own example uses short names, a launch's roles claim uses LIS URIs, and
# both arrive at the same word once the fragment or last path segment is taken.
LEARNER_ROLE_NAMES = ("learner", "student")

# The smallest roster count this module will look for on a page. A section with
# one member — or none — is counted by a digit that appears in half the strings a
# page can legitimately contain, so a `1` in the body would be reported as a
# leaked roster size and the test would be red against every correct
# implementation. Two is the smallest count that says something about a section
# and is worth the false-positive risk; the guard below fails loudly if no seeded
# roster reaches it, rather than scanning for nothing.
SMALLEST_TELLABLE_COUNT = 2

# How much of the body is printed around a suspected leak. A failure here is
# either a real leak or this module reading a number out of markup that means
# something else, and the two are told apart by seeing the text it sat in.
CONTEXT_CHARACTERS = 60

# The elements-and-attributes reader that used to live here — `RAW_ELEMENTS`,
# `GRAPHIC_ELEMENT`, `SPOKEN_INSIDE_A_GRAPHIC`, `DOCUMENT_BOUNDARIES`,
# `READABLE_ATTRIBUTES` and the `RenderedText` `HTMLParser` subclass below
# them — existed to read past a stylesheet and a decorative SVG that E0-18's
# inline landing page carried, so that a hex colour or a spacing token was
# never mistaken for a roster count. **Removed by E1-08's reconciliation**:
# there is no markup left to misread. A valid launch now answers a `302`
# with no rendered body at all, so the surface a leak could ride on is
# headers, an empty body, and the session token's own claims — plain text
# and structured data, never CSS or an SVG. `response_surface` below reads
# all three directly; a regex over it needs no reader in front of it.

# A number a reader would read as a number. The lookarounds are what tell `23` in
# "23 students" from the `4` in `--space-4`, the `6` in `#F6F8F4` and the `5` in
# `1.5` — a word boundary alone does not, because `-` and `#` are non-word
# characters and `\b4\b` matches happily inside `--space-4`. Adjacent letters,
# digits, hyphens, dots and hashes all disqualify a run; a number in prose is
# surrounded by spaces or punctuation that is none of those.
STANDALONE_NUMBER = re.compile(r"(?<![\w#.-])(\d+)(?![\w.-])")


@pytest.fixture
def platform(mock_platforms: Any, door_contract: Any) -> Any:
    """The mock platform, pointed at this tool's own login and launch URLs."""
    return mock_platforms(
        {
            MOCK_LMS_TOOL_LOGIN_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_login}"
            ),
            MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_launch}"
            ),
        }
    )


@pytest.fixture
def jwks_url(platform: Any) -> str:
    """Where the platform publishes the key set a launch verifies against."""
    document = platform.discovery() or {}
    advertised = document.get("jwks_uri")
    assert isinstance(advertised, str) and advertised, (
        "The mock platform's discovery document advertises no `jwks_uri` (it carries "
        f"{sorted(document)}). That URL is what `lti_platform.jwks_url` holds, so without it there "
        "is no registration to make and no launch to land."
    )
    return advertised


@pytest.fixture
def tool(
    tool_doors: Any, door_contract: Any, platform: Any, jwks_url: str, register_platform: Any
) -> Any:
    """The application, registered for this platform and able to reach it in process."""
    register_platform(platform.require_offers()[0], jwks_url, CONFIGURED_AUTHORIZATION_ENDPOINT)
    return tool_doors(
        {door_contract.settings["public_base_url"]: door_contract.public_base_url},
        {urlsplit(jwks_url).hostname: platform},
    )


def strings_in(node: Any) -> list[str]:
    """Every string anywhere inside a decoded JSON value."""
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [found for value in node.values() for found in strings_in(value)]
    if isinstance(node, list):
        return [found for item in node for found in strings_in(item)]
    return []


def query_of(url: str) -> dict[str, str]:
    """The query parameters of a URL, as a mapping."""
    return dict(parse_qsl(urlsplit(url).query))


def redirect_target(response: Any, purpose: str) -> str:
    """The `Location` of a redirect, or a failure saying what came back instead."""
    assert response.status_code in (302, 303, 307), (
        f"The tool answered {response.status_code} rather than a redirect when {purpose}. Body "
        f"begins {response.text[:300]!r}. E0-18: '`POST /lti/login` … answers a 302 to the "
        "platform's authorization endpoint'."
    )
    location = response.headers.get("location")
    assert location, f"The tool answered {response.status_code} with no `Location` when {purpose}."
    return location


def offer_for_role(platform: Any, role_uri: str) -> Any:
    """The launch the platform offers whose **signed** roles claim carries `role_uri`.

    Found by minting rather than by naming a seeded user, so this module holds no
    copy of the mock's identifiers. The signed claim is the ground truth because
    E0-18's landing rule reads the verified token — the offer's own parameters
    carry no roles at all and could not answer this.
    """
    seen: list[tuple[str | None, Any]] = []
    for offer in platform.require_offers():
        roles = platform.mint(offer).claims.get(ROLES_CLAIM) or []
        seen.append((offer.parameters.get("login_hint"), roles))
        if role_uri in roles:
            return offer
    pytest.fail(
        f"No launch the mock platform offers carries the role {role_uri!r}. What it offers: "
        f"{seen}. Both landing pages need a launch to reach them, and E0-14's criterion 7 is that "
        "the platform provides a student launch and an instructor launch."
    )


def landed(
    tool: Any, contract: Any, platform: Any, offer: Any, decode: Any
) -> tuple[Any, dict[str, Any]]:
    """One whole launch, and the claims the platform signed for it.

    Every part is the real one — the platform's launch form posted at `/lti/login`,
    the tool's own authorization request answered at the platform, the signed
    `id_token` delivered to `/lti/launch`. The claims come back beside the response
    because they are how the launching person's own identifiers are known, and
    those are the one set of strings a landing page may legitimately carry.
    """
    started = tool.post(contract.lti_login, data=dict(offer.parameters))
    parameters = query_of(redirect_target(started, "a registered platform began a launch"))
    path = platform.endpoint(
        "authorization_endpoint", ("auth",), "answers the tool with a signed `id_token`"
    )
    answered = (
        platform.client.post(path, data=parameters)
        if path in platform.paths("POST")
        else platform.client.get(path, params=parameters)
    )
    id_token, state, _ = platform.read_authorization_response(answered, path)
    body = {"id_token": id_token}
    if state is not None:
        body["state"] = state
    return tool.post(contract.lti_launch, data=body), dict(decode(id_token))


def redirected_to_role(response: Any, role: str) -> str:
    """The launch redirected to `/app/<role>#session=<token>`, and the token itself.

    **This is the positive control every scan below rests on**, the same
    discipline `lands_on` enforced before E1-08 retired the page it checked:
    a 4xx refusal, a 500, or a redirect to the wrong role all fail here
    rather than silently passing a scan that looked at nothing the ticket is
    about (`docs/MISTAKES.md` entry 3). This module's own copy of
    `test_lti_launch_door.py::redirected_to_role` — not imported, for the
    reason this module's own docstring gives about its sibling.
    """
    assert response.status_code in (302, 303, 307), (
        f"The launch was answered {response.status_code} rather than a redirect, so what follows "
        f"would be asserted about a refusal page rather than about the session this door issues. "
        f"Body begins {response.text[:400]!r}."
    )
    location = response.headers.get("location") or ""
    prefix = f"/app/{role}#session="
    assert location.startswith(prefix), (
        f"The launch redirected to `{location}`, which does not start with `{prefix}`. E1-08's "
        "interface ruling: a 302 whose `Location` is `/app/<segment>#session=<token>`, and "
        "'Learner → student, Instructor → instructor' is unchanged from E0-18's own dispatch."
    )
    token = location[len(prefix) :]
    assert token, f"The redirect `{location}` carries `session=` with an empty token."
    return token


# The `SessionClaims` fields E1-08's interface ruling names — `door`, `role`,
# `sub`, `iss`, `jti`, `iat`, `exp` — and nothing else. **Not asserted as an
# exact set below**: a benign field arriving later should not turn this test
# red for a reason unrelated to what it guards. Asserted instead as an
# *absence* of the key names an actual leak would add — `docs/MISTAKES.md`
# entry 2's own preference for the forbidden state over the permitted one,
# because it keeps working when a legitimate new opaque field arrives.
FORBIDDEN_SESSION_CLAIM_KEYS = frozenset(
    {
        "name",
        "given_name",
        "family_name",
        "middle_name",
        "email",
        "section",
        "section_code",
        "course",
        "course_number",
        "roster",
        "roster_count",
        "enrollment",
        "enrollment_count",
        "members",
    }
)


def session_claims_of(response: Any, role: str, decode: Any) -> dict[str, Any]:
    """The session token's own decoded claims, off the fragment `redirected_to_role` reads.

    Decoded, not verified: this module holds no copy of `SESSION_SECRET`, and
    a confidentiality scan does not need the signature checked to read what
    anyone intercepting the redirect could already read unverified. `decode`
    is `claims_in_token`, the same bare-JWS splitter the launch's own
    `id_token` claims are read with below.
    """
    return dict(decode(redirected_to_role(response, role)))


def response_surface(response: Any, session_claims: dict[str, Any]) -> str:
    """Everything a browser, a proxy log, or a script reading this response could see.

    E1-08 renders no page on the happy path, so there is no markup left for a
    reader to parse around: what a leak could ride on is the response's
    headers (`Location` included, still in its raw encoded form, and every
    `Set-Cookie`), its body (normally empty on a redirect; scanned anyway),
    and the session token's own claims — decoded and stringified, so a leak
    *inside* the token counts as well as one beside it.
    """
    header_text = " ".join(f"{name}: {value}" for name, value in response.headers.items())
    return " ".join([header_text, response.text, json.dumps(session_claims, default=str)])


def numbers_in(surface: str) -> set[str]:
    """Every number a reader would read as a number, out of a response surface."""
    return {match.group(1) for match in STANDALONE_NUMBER.finditer(surface)}


def own_identifiers(claims: dict[str, Any]) -> set[str]:
    """Every string identifying the person whose launch this is, out of their own token."""
    return {
        str(value)
        for member, value in claims.items()
        if member in PERSON_MEMBERS and isinstance(value, str) and value
    }


def other_peoples_identifiers(platform: Any, mine: set[str]) -> list[str]:
    """Every seeded person's name, address and subject, apart from one person's own.

    Two live sources, because a page could have got a name from either: the claims
    of every launch the platform signs, and the members of every NRPS roster it
    serves. Neither is transcribed.

    A value that is a *substring* of one of the caller's own identifiers is
    dropped. Subjects seeded as `…-1` and `…-10` are the case: with the caller's
    own `…-10` legitimately on the page, `…-1` is found inside it and would be
    reported as a leaked third party, which is a red nobody could act on.
    """
    found: list[str] = []
    for context in platform.seeded_contexts():
        for launch in context.launches:
            found += [
                str(value)
                for member, value in launch.claims.items()
                if member in PERSON_MEMBERS and isinstance(value, str) and value
            ]
        for page in platform.membership_pages(context.memberships_url):
            for member in page.members:
                found += [
                    value
                    for name, value in member.items()
                    if name in PERSON_MEMBERS and isinstance(value, str) and value
                ]
    return sorted(
        {value for value in found if value not in mine and not any(value in own for own in mine)}
    )


def published_about_sections(platform: Any) -> list[str]:
    """Every string the platform publishes about a seeded section.

    The three places a section names itself to a tool: the launch's context claim,
    its resource link claim, and the `context` object on the membership container.
    Nothing wider is read, so a section code cannot be found inside an opaque
    identifier that happens to look like one.
    """
    found: list[str] = []
    for context in platform.seeded_contexts():
        launch = context.launches[0]
        for claim in (CONTEXT_CLAIM, RESOURCE_LINK_CLAIM):
            found += strings_in(launch.claims.get(claim))
        page = platform.membership_page(context.memberships_url)
        found += strings_in(page.document.get("context"))
    return found


def section_identifiers(platform: Any) -> tuple[set[str], set[str]]:
    """The §2.2 section codes and the §8 course numbers the platform publishes."""
    codes: set[str] = set()
    numbers: set[str] = set()
    for value in published_about_sections(platform):
        codes |= {token for token in re.split(r"[^A-Za-z0-9]+", value) if SECTION_CODE.match(token)}
        numbers |= {
            match.group("number")
            for match in COURSE_NUMBER.finditer(value)
            if match.group("prefix") not in NOT_A_COURSE_PREFIX
        }
    return codes, numbers


def role_names(member: dict[str, Any]) -> set[str]:
    """A roster member's roles as bare lower-case words, whichever vocabulary spelled them."""
    roles = member.get("roles")
    if not isinstance(roles, list):
        return set()
    return {
        str(role).replace("#", "/").rstrip("/").rsplit("/", maxsplit=1)[-1].lower()
        for role in roles
        if isinstance(role, str) and role
    }


def roster_counts(platform: Any) -> set[int]:
    """Every figure a page could print if it counted a seeded roster.

    Both the whole membership and the learners in it, because "23 students" and
    "25 people" are the same disclosure written two ways and an implementation
    could reasonably compute either.
    """
    counts: set[int] = set()
    for context in platform.seeded_contexts():
        members = [
            member
            for page in platform.membership_pages(context.memberships_url)
            for member in page.members
        ]
        counts.add(len(members))
        counts.add(len([m for m in members if role_names(m) & set(LEARNER_ROLE_NAMES)]))
    return {count for count in counts if count >= SMALLEST_TELLABLE_COUNT}


def around(body: str, needle: str) -> str:
    """The text a suspected leak sits in, so a failure can be acted on in one read."""
    at = body.find(needle)
    if at < 0:  # pragma: no cover - only reached if the caller found it another way
        return ""
    return body[max(0, at - CONTEXT_CHARACTERS) : at + len(needle) + CONTEXT_CHARACTERS]


@pytest.mark.invariant
@pytest.mark.parametrize(("role_uri", "role"), LANDING_PAGES)
def test_a_launch_landing_page_names_nobody_but_the_person_who_launched(
    tool: Any,
    door_contract: Any,
    platform: Any,
    claims_in_token: Any,
    role_uri: str,
    role: str,
) -> None:
    """SPEC §4 over the two ways a launch answers.

    "Identity is never displayed to instructors or any leadership role, in any
    view" — and **E1-08 renders no view at all** on this door's happy path: a
    valid launch now answers a `302` carrying a session in the URL fragment,
    never an HTML page (ADR 0089). That narrows what could possibly leak to
    the response's headers, its (normally empty) body, and the session
    token's own claims — `response_surface` reads all three — and a page
    carrying a seeded person's name, address or subject would still have
    obtained it from a read nothing sanctions; on the student side it would
    be a classmate.

    **Reconciled for E1-08 by dispute E1-08-03**, preserving this test's
    original intent against the new response shape: `lands_on` (`200` +
    testid) is replaced by `redirected_to_role` (`302` +
    `/app/<role>#session=`), and the scan reads `response_surface` in place
    of `response.text` alone. The session token's claim *keys* are checked
    too, against `FORBIDDEN_SESSION_CLAIM_KEYS`, which nothing before this
    ticket needed because there was no session token to carry a key at all.

    **The mutation this kills:** a session claim, a cookie, or (were a page
    ever rendered again) a body gaining a seeded person's display name — a
    "signed in as" value built from the launch's `name` claim would be
    excluded here as the caller's own, so what this catches is the version
    that reaches past the caller: a roster claim added to the session token
    because the launch carried the NRPS service URL, or a cookie built from a
    membership fetch.

    **The two guards that keep a green meaningful.** The launch has to reach
    the new redirect shape for this role, so a refusal fails rather than
    passes; and the scan is shown finding the very strings it reports absent,
    so a search that has gone blind says so instead of reporting a clean
    response (`docs/MISTAKES.md` entry 3).
    """
    response, claims = landed(
        tool, door_contract, platform, offer_for_role(platform, role_uri), claims_in_token
    )
    session_claims = session_claims_of(response, role, claims_in_token)

    forbidden_keys = sorted(FORBIDDEN_SESSION_CLAIM_KEYS & set(session_claims))
    assert not forbidden_keys, (
        f"The session token carries {forbidden_keys} (it carries {sorted(session_claims)}). "
        "E1-08's interface ruling gives the session an opaque `sub`, `iss`, `role`, `door` and "
        "`jti` — never a name, a section or a roster."
    )

    mine = own_identifiers(claims)
    others = other_peoples_identifiers(platform, mine)
    assert others, (
        "No seeded launch and no seeded roster publishes a name, an address or a subject other "
        f"than the launching person's own ({sorted(mine)}), so this test has nothing to look for "
        "and would pass against a response naming the whole institution."
    )
    canary = " ".join(others)
    assert all(value in canary for value in others), (
        "The scan below cannot find these strings in a sample built out of them, so its silence "
        "about the response means nothing."
    )

    surface = response_surface(response, session_claims)
    leaked = sorted({value for value in others if value in surface})
    assert not leaked, (
        f"This `{role}` launch's response carries {leaked}, which identify seeded people other "
        f"than the one who launched. First occurrence: {around(surface, leaked[0])!r}. SPEC §4 "
        "keeps identity out of every view, and E1-08 renders no view at all on this door's happy "
        "path — a response that names somebody got that name from somewhere §4.1 does not "
        "sanction, whether in a header, a cookie, or the session token itself."
    )


@pytest.mark.invariant
@pytest.mark.parametrize(("role_uri", "role"), LANDING_PAGES)
def test_a_launch_landing_page_carries_no_section_code_or_course_number(
    tool: Any,
    door_contract: Any,
    platform: Any,
    claims_in_token: Any,
    role_uri: str,
    role: str,
) -> None:
    """The section half of the criterion: neither response identifies a section.

    §2.2 makes `{startLetter}{ordinal}{modality}` the string a section is known by
    and §8 makes the prefixed number the course; between them they are how a
    response says *which* class this is. **E1-08 renders no view at all** on
    this door's happy path, and E0 (and E1-08) has no section-scoped read path
    either — so a code or a number anywhere in the response came out of the
    launch claims and leaked somewhere it should not have, which is the first
    step of the page that eventually shows one section's figures beside
    another's (§4.1 item 1).

    **Reconciled for E1-08 by dispute E1-08-03.** `lands_on` is replaced by
    `redirected_to_role`, and both halves now scan `response_surface` — the
    response's headers, its body, and the session token's own decoded claims
    — rather than `response.text` alone. **The `RenderedText` reader this
    test used to lean on is gone**, and so are the CSS/SVG plants it existed
    to see past: there is no stylesheet and no graphic left in a `302` with
    an empty body, so a direct `STANDALONE_NUMBER` match over the surface is
    simpler and at least as strict as the reader was — the class of false
    positive the reader guarded against (a hex colour, a spacing token) no
    longer has anywhere to hide in.

    **The mutation this kills:** the launched section's code or course number
    reaching a header, a cookie, or the session token — `NURS 8100 · Q2FF`
    riding along in whatever this door still adds to a response once the
    inline landing page is gone.

    **The near miss it must survive:** the launch still has to reach the new
    redirect shape, so a refusal response cannot pass this by carrying
    nothing; and the codes and numbers are read out of what the platform
    publishes, so a scan looking for strings the seed no longer uses fails on
    the guard rather than reporting a clean response.
    """
    response, _ = landed(
        tool, door_contract, platform, offer_for_role(platform, role_uri), claims_in_token
    )
    session_claims = session_claims_of(response, role, claims_in_token)

    codes, numbers = section_identifiers(platform)
    assert codes, (
        "No string the platform publishes about a seeded section matches §2.2's "
        "`{startLetter}{ordinal}{modality}` shape, so this test is scanning for a section code "
        "that does not exist. E0-15 criterion 5 seeds codes that reach a tool, and "
        "`tests/integration/test_mock_lms_seed_data.py` is where their absence is diagnosed."
    )
    assert numbers, (
        "No string the platform publishes about a seeded section carries anything shaped like a "
        "§8 course number, so the course-number half of this test would pass against a response "
        "carrying one. E0-15: 'Every seeded course needs a title and a number in SPEC §8's bands'."
    )
    # A prefix chosen for the sample rather than taken from the seed: what the
    # course-number pattern has to be shown finding is a number written the way a
    # course number is written, and borrowing a real prefix would make this sample
    # a copy of the thing it checks (`docs/MISTAKES.md` entry 19).
    sample = " ".join(sorted(codes)) + " " + " ".join(f"XYZ {number}" for number in sorted(numbers))
    assert all(code in sample for code in codes), (
        "The code scan cannot find these codes in a sample built out of them, so its silence about "
        "the response means nothing."
    )
    assert {match.group("number") for match in COURSE_NUMBER.finditer(sample)} >= numbers, (
        "The course-number pattern cannot find these numbers in a sample written the way a course "
        "number is written, so its silence about the response means nothing."
    )

    surface = response_surface(response, session_claims)
    # The reader's replacement, proved on the surface under test rather than
    # assumed: a real course number is planted into it and the plain scan has
    # to find it, the same discipline `RenderedText` was proved with — a scan
    # narrowed one step too far reports a clean response exactly as
    # confidently as a correct one does.
    planted = sorted(numbers)[0]
    assert planted in numbers_in(surface + f" XYZ {planted}"), (
        f"The scan cannot find the course number {planted} planted into this response's surface, "
        "so its silence about the real response says nothing (`docs/MISTAKES.md` entry 3). "
        "`STANDALONE_NUMBER` rejects a digit run touching a letter, digit, hyphen, dot or hash; if "
        "it has gone one step too far, this is where it shows."
    )

    found_codes = sorted({code for code in codes if code in surface})
    found_numbers = sorted(numbers & numbers_in(surface))
    first = (found_codes or found_numbers or [""])[0]
    assert not found_codes and not found_numbers, (
        f"This `{role}` launch's response carries section code(s) {found_codes} and course "
        f"number(s) {found_numbers}, which the platform publishes about its seeded sections. "
        f"First occurrence: {around(surface, first)!r}.\n"
        "E1-08 renders no view at all on the happy path; a response that says which section this "
        "is has begun leaking the launch's context claim into a header, a cookie, or the session "
        "token itself, and §2.2's code is the whole identity of a section.\n"
        "If what is reported is not a section after all — an uppercase hex fragment can spell a "
        "code, and a large enough number can coincide with a course number's shape — the "
        "surrounding text printed here is what says so, and the defect is then in this test "
        "rather than in the door."
    )


@pytest.mark.invariant
@pytest.mark.parametrize(("role_uri", "role"), LANDING_PAGES)
def test_a_launch_landing_page_carries_no_roster_count(
    tool: Any,
    door_contract: Any,
    platform: Any,
    claims_in_token: Any,
    role_uri: str,
    role: str,
) -> None:
    """The numeric half: nothing in the response reports how many people are in the section.

    A roster count is a figure computed about a section from data this door has no
    business reading — E1's NRPS sync is E1-11's, not this ticket's. On the
    student side it is also a fact about classmates. It is asserted rather than
    assumed because the launch carries the names-and-role service URL, so the
    count is one fetch away from any code that wants to look busy.

    **Reconciled for E1-08 by dispute E1-08-03.** `lands_on` is replaced by
    `redirected_to_role`, and the scan reads `response_surface` in place of
    `response.text`. **The four-shape plant control is now one shape**, and
    that is a real simplification rather than a quiet weakening: the other
    three existed to prove `RenderedText` could see a count written as an
    `aria-label`, on a graphic, or inside one — shapes that only exist inside
    rendered markup, and E1-08 renders none. A `302` with an empty body has
    exactly one place left for a number to ride: the surface
    `response_surface` already reads (headers, body, decoded session
    claims), so one plant proves the plain scan finds a number there.

    **The mutation this kills:** the launched section's member count reaching
    a header, a cookie, or the session token — "N students enrolled" riding
    along in whatever this door still adds to a response once the inline
    landing page and its aria-labelled chart are gone.

    SPEC §4.1 item 7's comparison figures are **not** asserted here and this is
    the ticket's own boundary: nothing in E1-08 computes one, and the spec
    assigns that assertion to E4.
    """
    response, _ = landed(
        tool, door_contract, platform, offer_for_role(platform, role_uri), claims_in_token
    )
    session_claims = session_claims_of(response, role, claims_in_token)

    counts = roster_counts(platform)
    assert counts, (
        f"No seeded roster has {SMALLEST_TELLABLE_COUNT} or more members, or more than that many "
        "learners, so there is no roster count this test could recognise on a response. E0-15 "
        "seeds rosters and `tests/integration/test_mock_lms_nrps_roster.py` is where their size "
        "is asserted."
    )

    surface = response_surface(response, session_claims)
    # The control, run against the surface under test rather than against a
    # sample of this file's own making: a real roster size is planted and the
    # scan has to find it. A word boundary alone would not be enough —
    # `\b4\b` matches inside a token like `--space-4` — which is why
    # `STANDALONE_NUMBER`'s own lookarounds are proved here too.
    planted = sorted(counts)[0]
    plant = f" {planted} students enrolled"
    assert str(planted) in numbers_in(surface + plant), (
        f"The scan cannot find {planted} planted into this response's surface, so its silence "
        "about the real response says nothing (`docs/MISTAKES.md` entry 3). If "
        "`STANDALONE_NUMBER` now rejects a number in prose, this is where it shows."
    )

    reported = sorted(count for count in counts if str(count) in numbers_in(surface))
    sat_in = around(surface, str(reported[0])) if reported else ""
    assert not reported, (
        f"This `{role}` launch's response carries {reported}, which is the size of a seeded "
        f"roster (or the number of learners in one). Where it sits: {sat_in!r}. E0/E1-08 sync no "
        "roster — §7.3's names-and-role sync is E1-11's — so a count anywhere in this response "
        "(a header, a cookie, or the session token) was fetched from the platform at issue time, "
        "and on the student side it is a fact about classmates.\n"
        "If this number is not a roster count after all — a year, a version, part of an "
        "encoded token that happened to spell a standalone run — the text printed above is what "
        "says so, and the defect is then in this test rather than in the door."
    )
