"""The launch door's two landing pages name nobody — SPEC §4.1, ticket E0-41.

`POST /lti/launch` is the only door a student can enter through, and until E0-41
it carried no `invariant`-marked test at all: the web door's landing pages had
three, this door had none, so the isolated §4.1 pass — the one CLAUDE.md says may
never be skipped — walked past the student page entirely.

**What is asserted, and against what.** SPEC §4: "Identity is never displayed to
instructors or any leadership role, in any view, including CSV exports", and
§4.1 item 1 keeps comparables, benchmarks and other sections away from students.
E0-18 renders both of these pages empty by design — no purview is computed in E0
(ADR 0003), no roster is synced, no report exists — so the honest reading of that
for these two surfaces is: the page names nobody but the person who launched, and
it carries no section code, no course number and no roster count. Each is
asserted against the **rendered body**, exactly as
`tests/integration/test_web_login_door.py`'s three landing invariants are: what a
browser received, not what a function returned.

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
  - **the near miss**: the assertion passing because the fixture rendered an
    error page instead of the landing page. A 4xx body names nobody either. So
    every test below lands first — `lands_on` requires this page's own testid
    present *and* the other four absent — and then shows its scan finding the
    very strings it is about to report absent (`docs/MISTAKES.md` entry 3).

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
"""

import re
from html.parser import HTMLParser
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

# Where the tool is told to send a browser to begin the launch. `.invalid` is
# reserved by RFC 2606; the value is one no implementation could arrive at by
# accident, which is why the launch-door module chose it and why this one reuses
# the spelling rather than inventing a second.
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
STUDENT_VIEW = "pulse-landing-student"
INSTRUCTOR_VIEW = "pulse-landing-instructor"

# The two pages this door serves, as the parameters of every test below. Both
# pages are asserted by every rule here rather than one each: an instructor page
# listing students and a student page listing classmates are the same defect, and
# a rule proved on one page says nothing about the other.
LANDING_PAGES = (
    pytest.param(LEARNER_ROLE_URI, STUDENT_VIEW, id="student"),
    pytest.param(INSTRUCTOR_ROLE_URI, INSTRUCTOR_VIEW, id="instructor"),
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

# Elements whose contents a browser never renders as words. **This is the repair
# E0-41's verification round forced**: the first version of the roster-count test
# scanned `response.text` whole and reported 4, 5, 6 and 7 as leaked roster sizes,
# every one of them out of the inline stylesheet and the decorative SVG in
# `landing.py`'s page template — hex colours (`#F6F8F4`, `#5B7269`), spacing
# tokens (`--space-4`), a `line-height: 1.5`, a `stroke-width="2.5"`. No count was
# rendered anywhere. `HTMLParser` treats their contents as raw text, so no tag
# inside them is parsed either.
RAW_ELEMENTS = frozenset({"style", "script"})

# The graphic, whose drawing instructions are numbers and whose text is text.
GRAPHIC_ELEMENT = "svg"

# What is read or spoken from inside a graphic. `<text>` and `<tspan>` are drawn;
# `<title>` and `<desc>` are the SVG accessibility pair a screen reader announces;
# `<foreignObject>` holds ordinary HTML rendered inside the graphic (spelled in
# lower case because `HTMLParser` folds tag names). A count in any of them is a
# count on the page, and a reader that stopped at the `<svg>` boundary would be
# the mutation the planted control below exists to catch.
SPOKEN_INSIDE_A_GRAPHIC = frozenset({"text", "tspan", "title", "desc", "foreignobject"})

# Where a graphic certainly ends, whatever the markup says. An unclosed `<svg>`
# would otherwise swallow every text node after it — measured by the security pass
# over this reader — so the document's own closing tags reset the state: a graphic
# cannot outlive the body it is drawn in.
DOCUMENT_BOUNDARIES = frozenset({"body", "html"})

# Attributes a screen reader speaks. SPEC §4.1 item 1 names aria labels in the
# same breath as charts, text and tooltips. **Collected from every element,
# including the ones whose contents are skipped**: `<svg aria-label="18 students
# in your section">` is the standard accessible-chart pattern, so an attribute
# scan that stopped where the text scan stops would miss the first shape §4.1
# item 1 names — which is what it did until the security pass ran it.
READABLE_ATTRIBUTES = ("aria-label", "aria-description", "aria-valuetext", "title", "alt")

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
    register_platform(platform.require_offers()[0], jwks_url)
    return tool_doors(
        {
            door_contract.settings["public_base_url"]: door_contract.public_base_url,
            door_contract.settings["lti_authorization_endpoint"]: CONFIGURED_AUTHORIZATION_ENDPOINT,
        },
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


def views_in(response: Any, contract: Any) -> list[str]:
    """Which of the five landing testids the body carries."""
    return [testid for testid in contract.landing_testids if testid in response.text]


def lands_on(response: Any, contract: Any, expected: str) -> None:
    """The response is the landing page for `expected`, and for nothing else.

    **This is the positive control every scan below rests on.** A 4xx refusal page,
    a 500, an empty body and a page that was never reached all name nobody and
    carry no section code, so a scan run over one of them reports a clean page
    while having looked at nothing the ticket is about (`docs/MISTAKES.md` entry
    3). Requiring the other four testids absent as well as this one present is the
    same discipline the two door modules use: a page carrying several is right
    about none of them.
    """
    assert response.status_code == 200, (
        f"The launch was answered {response.status_code} rather than 200, so what follows would be "
        f"asserted about a refusal page rather than about a landing page. Body begins "
        f"{response.text[:400]!r}."
    )
    found = views_in(response, contract)
    assert found == [expected], (
        f"The landing page carries {found or 'no landing testid at all'}, and this launch lands on "
        f"`{expected}` (E0-18: 'Learner → student empty view, Instructor → instructor empty view'). "
        "Every other view's testid has to be absent as well as this one present."
    )


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


class RenderedText(HTMLParser):
    """What a reader reads: text nodes, plus the attributes a screen reader speaks.

    A landing page is markup, and most of the characters in it are instructions to
    a browser rather than words to a person. Counting digits across all of them
    reports a stylesheet's spacing scale as a roster size, which is exactly what
    the first version of the test below did. So the numbers are counted over what
    a browser would show and what a screen reader would say, and nothing else.

    **Four decisions, each of which could have made this blind. The third and the
    fourth are repairs from E0-42's security pass, which ran this reader over the
    shapes below and watched it miss them.**

      - `style` and `script` contents are dropped. Neither can put a word on the
        page, and both are full of numbers. `HTMLParser` treats their contents as
        raw text, so no tag inside them is parsed either.
      - `svg` contents are dropped **except** `<text>`, `<tspan>`, `<title>`,
        `<desc>` and `<foreignObject>`, which are drawn, announced, or ordinary
        HTML laid out inside the graphic. A count rendered in any of them is a
        count on the page.
      - **Readable attributes are collected from every element, skipped ones
        included.** An `aria-label` is spoken whatever it is attached to, and
        `<svg aria-label="18 students in your section">` is *the* accessible-chart
        pattern — so is `<g aria-label="…">` on a group inside one. The first
        version collected attributes only after the skip check, which made the one
        shape §4.1 item 1 names first invisible while the docstring claimed to
        cover it.
      - **A graphic cannot outlive the document.** `</body>` and `</html>` reset
        every state, because an unclosed `<svg>` otherwise swallows every text
        node to the end of the input. What an unclosed graphic still costs is the
        text between it and the end of the body: that text is genuinely
        unreachable to a parser that cannot know where the author meant the
        graphic to stop, and it is a bounded loss rather than the whole page. The
        planted control appends its content after `</html>`, so the reader is
        proved alive even on a page whose graphic never closes.

    Nesting is counted rather than name-matched, so a `<title>` inside a
    `<foreignObject>` inside an `<svg>` resolves in the right order.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raw = 0
        self.graphic = 0
        self.spoken = 0
        self.readable: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Before any skip decision: an attribute is spoken wherever it sits.
        self.readable += [value for name, value in attrs if name in READABLE_ATTRIBUTES and value]
        if tag in RAW_ELEMENTS:
            self.raw += 1
        elif tag == GRAPHIC_ELEMENT:
            self.graphic += 1
        elif self.graphic and tag in SPOKEN_INSIDE_A_GRAPHIC:
            self.spoken += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in DOCUMENT_BOUNDARIES:
            self.raw = self.graphic = self.spoken = 0
        elif tag in RAW_ELEMENTS:
            self.raw = max(0, self.raw - 1)
        elif tag == GRAPHIC_ELEMENT:
            self.graphic = max(0, self.graphic - 1)
            if not self.graphic:
                self.spoken = 0
        elif self.graphic and tag in SPOKEN_INSIDE_A_GRAPHIC:
            self.spoken = max(0, self.spoken - 1)

    def handle_data(self, data: str) -> None:
        if not self.raw and (not self.graphic or self.spoken):
            self.readable.append(data)


def readable_text(body: str) -> str:
    """Everything in `body` a person would read or hear, joined by spaces.

    Joined rather than concatenated so two fragments cannot spell a number
    neither of them contains.
    """
    reader = RenderedText()
    reader.feed(body)
    reader.close()
    return " ".join(reader.readable)


def numbers_read_from(body: str) -> set[str]:
    """Every number a reader would read as a number, out of a rendered page."""
    return {match.group(1) for match in STANDALONE_NUMBER.finditer(readable_text(body))}


def around(body: str, needle: str) -> str:
    """The text a suspected leak sits in, so a failure can be acted on in one read."""
    at = body.find(needle)
    if at < 0:  # pragma: no cover - only reached if the caller found it another way
        return ""
    return body[max(0, at - CONTEXT_CHARACTERS) : at + len(needle) + CONTEXT_CHARACTERS]


@pytest.mark.invariant
@pytest.mark.parametrize(("role_uri", "view"), LANDING_PAGES)
def test_a_launch_landing_page_names_nobody_but_the_person_who_launched(
    tool: Any,
    door_contract: Any,
    platform: Any,
    claims_in_token: Any,
    role_uri: str,
    view: str,
) -> None:
    """SPEC §4 over the two pages a launch can reach.

    "Identity is never displayed to instructors or any leadership role, in any
    view" — and E0-18 renders both of these pages empty *by design*, because
    nothing in E0 computes a purview (ADR 0003) or syncs a roster. So a page
    carrying a seeded person's name, address or subject obtained it from a read
    nothing sanctions, and on the student page it would be a classmate.

    **The mutation this kills:** a landing page gaining a seeded person's display
    name — a "signed in as" line built from the launch's `name` claim would be
    excluded here as the caller's own, so what this catches is the version that
    reaches past the caller: a roster fetched over NRPS because the launch carries
    the service URL, or a template that lists the section's members.

    **The two guards that keep a green meaningful.** The launch has to land on
    this page's own testid, so a refusal page fails rather than passes; and the
    scan is shown finding the very strings it reports absent, so a search that has
    gone blind says so instead of reporting a clean page (`docs/MISTAKES.md`
    entry 3).
    """
    response, claims = landed(
        tool, door_contract, platform, offer_for_role(platform, role_uri), claims_in_token
    )
    lands_on(response, door_contract, view)

    mine = own_identifiers(claims)
    others = other_peoples_identifiers(platform, mine)
    assert others, (
        "No seeded launch and no seeded roster publishes a name, an address or a subject other "
        f"than the launching person's own ({sorted(mine)}), so this test has nothing to look for "
        "and would pass against a page listing the whole institution."
    )
    canary = " ".join(others)
    assert all(value in canary for value in others), (
        "The scan below cannot find these strings in a sample built out of them, so its silence "
        "about the landing page means nothing."
    )

    leaked = sorted({value for value in others if value in response.text})
    assert not leaked, (
        f"The `{view}` landing page carries {leaked}, which identify seeded people other than the "
        f"one who launched. First occurrence: {around(response.text, leaked[0])!r}. SPEC §4 keeps "
        "identity out of every view, and E0-18 renders this page empty by design — no purview is "
        "computed in E0 and no roster is synced, so a page that names somebody got that name from "
        "somewhere §4.1 does not sanction."
    )


@pytest.mark.invariant
@pytest.mark.parametrize(("role_uri", "view"), LANDING_PAGES)
def test_a_launch_landing_page_carries_no_section_code_or_course_number(
    tool: Any,
    door_contract: Any,
    platform: Any,
    claims_in_token: Any,
    role_uri: str,
    view: str,
) -> None:
    """The section half of the criterion: neither page identifies a section.

    §2.2 makes `{startLetter}{ordinal}{modality}` the string a section is known by
    and §8 makes the prefixed number the course; between them they are how a page
    says *which* class this is. E0-18's landing pages show a heading and nothing
    else, and E0 has no section-scoped read path at all — so a code or a number on
    either page came out of the launch claims and was rendered, which is the first
    step of the page that eventually shows one section's figures beside another's
    (§4.1 item 1).

    **The mutation this kills:** a landing page gaining the launched section's
    code — the context header reading `NURS 8100 · Q2FF` that anybody would add to
    a page rendered from a launch that carries exactly those strings.

    **The near miss it must survive:** the page still lands, so an error page
    cannot pass this by carrying nothing; and the codes and numbers are read out
    of what the platform publishes, so a scan looking for strings the seed no
    longer uses fails on the guard rather than reporting a clean page.

    **The course-number half reads rendered text**, through the same
    `RenderedText` reader the roster-count test uses. It was never red, and it was
    the same defect one seed change away: counting every digit run in the whole
    body collects the stylesheet's palette and spacing scale, so a seeded course
    number that happened to equal a hex fragment would have been reported as a
    leak — which is precisely how the roster-count test failed its first run.
    Closing the class in one round beats meeting it again in another test. The
    reader is proved here rather than by borrowing that test's proof: a real
    course number is planted into this page's content and the scan has to find it.

    **The section-code half still reads the whole body, deliberately.** A code is
    `{startLetter}{ordinal}{modality}` — uppercase, ending `WW` or `FF` — which is
    not a shape a spacing scale or a palette produces, and a code sitting in a
    `data-` attribute or a comment is a leak worth catching even though no reader
    would speak it. The residual is named rather than implied: an uppercase hex
    colour can spell one (`#A1FF…`), and if that ever happens the failure prints
    the surrounding text, which makes it one read to tell a palette from a section.
    """
    response, _ = landed(
        tool, door_contract, platform, offer_for_role(platform, role_uri), claims_in_token
    )
    lands_on(response, door_contract, view)

    codes, numbers = section_identifiers(platform)
    assert codes, (
        "No string the platform publishes about a seeded section matches §2.2's "
        "`{startLetter}{ordinal}{modality}` shape, so this test is scanning for a section code "
        "that does not exist. E0-15 criterion 5 seeds codes that reach a tool, and "
        "`tests/integration/test_mock_lms_seed_data.py` is where their absence is diagnosed."
    )
    assert numbers, (
        "No string the platform publishes about a seeded section carries anything shaped like a "
        "§8 course number, so the course-number half of this test would pass against a page "
        "printing one. E0-15: 'Every seeded course needs a title and a number in SPEC §8's bands'."
    )
    # A prefix chosen for the sample rather than taken from the seed: what the
    # course-number pattern has to be shown finding is a number written the way a
    # course number is written, and borrowing a real prefix would make this sample
    # a copy of the thing it checks (`docs/MISTAKES.md` entry 19).
    sample = " ".join(sorted(codes)) + " " + " ".join(f"XYZ {number}" for number in sorted(numbers))
    assert all(code in sample for code in codes), (
        "The code scan cannot find these codes in a sample built out of them, so its silence about "
        "the landing page means nothing."
    )
    assert {match.group("number") for match in COURSE_NUMBER.finditer(sample)} >= numbers, (
        "The course-number pattern cannot find these numbers in a sample written the way a course "
        "number is written, so its silence about the landing page means nothing."
    )
    # And the reader, on the page under test. The two assertions above prove the
    # *patterns* are not blind; this proves that what the patterns are given —
    # `RenderedText`'s idea of what the page says — still contains a course number
    # when the page carries one. A reader narrowed one element too far reports a
    # clean page exactly as confidently as a correct one does.
    planted = sorted(numbers)[0]
    assert planted in numbers_read_from(response.text + f"<p>XYZ {planted}</p>"), (
        f"The scan cannot find the course number {planted} planted into this page's rendered "
        "content, so its silence about the real page says nothing (`docs/MISTAKES.md` entry 3). "
        "`RenderedText` drops `style` and `script` contents and a graphic's drawing instructions — "
        "keeping the text it draws or announces, and keeping readable attributes wherever they sit "
        "— and `STANDALONE_NUMBER` rejects a digit run touching a letter, digit, hyphen, dot or "
        "hash; if either has gone one step too far, this is where it shows."
    )

    body = response.text
    found_codes = sorted({code for code in codes if code in body})
    found_numbers = sorted(numbers & numbers_read_from(body))
    first = (found_codes or found_numbers or [""])[0]
    assert not found_codes and not found_numbers, (
        f"The `{view}` landing page carries section code(s) {found_codes} and course number(s) "
        f"{found_numbers}, which the platform publishes about its seeded sections. First "
        f"occurrence: {around(body, first)!r}.\n"
        "E0-18 renders this page "
        "empty; a page that says which section this is has begun rendering the launch's context "
        "claim, and §2.2's code is the whole identity of a section.\n"
        "The course numbers are read out of the rendered text, so a digit from the stylesheet "
        "cannot reach them; a code is searched for in the whole body, so one in a `data-` "
        "attribute is caught too. If what is reported is not a section after all — an uppercase "
        "hex colour can spell a code — the surrounding text printed here is what says so, and the "
        "defect is then in this test rather than in the door."
    )


@pytest.mark.invariant
@pytest.mark.parametrize(("role_uri", "view"), LANDING_PAGES)
def test_a_launch_landing_page_carries_no_roster_count(
    tool: Any,
    door_contract: Any,
    platform: Any,
    claims_in_token: Any,
    role_uri: str,
    view: str,
) -> None:
    """The numeric half: neither page reports how many people are in the section.

    A roster count is a figure computed about a section from data this door has no
    business reading — E0 syncs no roster, and §7.3's NRPS sync is E1's. On the
    student page it is also a fact about classmates. It is asserted rather than
    assumed because the launch carries the names-and-role service URL, so the
    count is one fetch away from any template that wants to look busy.

    **The mutation this kills:** a landing page gaining "N students enrolled",
    whether shown or only spoken through an aria label (§4.1 item 1 names those
    beside charts and text).

    **The near miss, and it is now the more interesting half.** The first version
    of this test counted digits across `response.text` whole and went red on both
    pages, reporting 4, 5, 6 and 7 as leaked roster sizes — every one of them out
    of the inline stylesheet and the decorative SVG: `#F6F8F4`, `--space-4`,
    `line-height: 1.5`, `stroke-width="2.5"`. No count was rendered anywhere. So
    the scan now reads only what a browser would show and a screen reader would
    say, and **the narrowing is itself a way to blind this test**: a reader that
    dropped attributes, or stopped at the `<svg>` boundary, or a number pattern
    that rejected too much, would report a clean page just as confidently as the
    old one reported a dirty one. That is the mutation the control below exists
    for — it plants a real roster size into this very page four ways and requires
    the narrowed scan to find all four. A word boundary alone would not have been
    the fix either: `\\b4\\b` matches inside `--space-4`.

    **Two of those four plants are E0-42's security pass**, which ran the reader
    over the accessible-chart pattern and watched it miss: `<svg aria-label="18
    students in your section">` and a `<g aria-label="…">` inside the graphic were
    both invisible, because attributes were collected only after the skip check.
    The control went green over that hole, which is the whole reason a control
    plants the shapes an implementer would actually write rather than the shape
    the test's author had in mind.

    SPEC §4.1 item 7's comparison figures are **not** asserted here and this is
    the ticket's own boundary: nothing in E0 computes one, and the spec assigns
    that assertion to E4.
    """
    response, _ = landed(
        tool, door_contract, platform, offer_for_role(platform, role_uri), claims_in_token
    )
    lands_on(response, door_contract, view)

    counts = roster_counts(platform)
    assert counts, (
        f"No seeded roster has {SMALLEST_TELLABLE_COUNT} or more members, or more than that many "
        "learners, so there is no roster count this test could recognise on a page. E0-15 seeds "
        "rosters and `tests/integration/test_mock_lms_nrps_roster.py` is where their size is "
        "asserted."
    )

    # The control, run against the page under test rather than against a sample of
    # this file's own making: a real roster size is planted four ways and the
    # narrowed scan has to find every one. The last two are the shapes E0-42's
    # security pass caught this reader missing — a count on a chart is written as
    # an `aria-label` on the `<svg>` itself or on a `<g>` inside it far more often
    # than it is written as a paragraph — and the control was green over that hole
    # until they were added. A reader that skips too much is the failure this
    # catches, and it is the failure a scan reporting "no numbers" cannot be told
    # from.
    planted = sorted(counts)[0]
    plants = (
        ("rendered content", f"<p>{planted} students enrolled</p>"),
        ("an aria label", f'<span aria-label="{planted} learners">roster</span>'),
        ("an aria label on the graphic itself", f'<svg aria-label="{planted} students"></svg>'),
        (
            "an aria label inside the graphic",
            f'<svg><g aria-label="{planted} learners"></g></svg>',
        ),
    )
    unseen = [
        shape
        for shape, plant in plants
        if str(planted) not in numbers_read_from(response.text + plant)
    ]
    assert not unseen, (
        f"The scan cannot find {planted} planted into this page as {unseen}, so its silence about "
        "the real page says nothing (`docs/MISTAKES.md` entry 3). This reader drops `style` and "
        "`script` contents and a graphic's drawing instructions — keeping `<text>`, `<tspan>`, "
        "`<title>`, `<desc>` and `<foreignObject>` — and keeps the attributes a screen reader "
        "speaks **wherever they sit, the graphic included**. If the narrowing has gone one element "
        "too far, or `STANDALONE_NUMBER` now rejects a number in prose, this is where it shows, "
        f"and what the reader made of the first planted page was "
        f"{readable_text(response.text + plants[0][1])[:400]!r}."
    )

    read = numbers_read_from(response.text)
    reported = sorted(count for count in counts if str(count) in read)
    sat_in = around(readable_text(response.text), str(reported[0])) if reported else ""
    assert not reported, (
        f"The `{view}` landing page shows or speaks {reported}, which is the size of a seeded "
        f"roster (or the number of learners in one). Where it sits in the rendered text: "
        f"{sat_in!r}. "
        "E0 syncs no roster — §7.3's names-and-role sync is E1's — so a count on this page was "
        "fetched from the platform at render time, and on the student page it is a fact about "
        "classmates.\n"
        "The scan reads text nodes, text drawn or announced inside a graphic, and the attributes a "
        "screen reader speaks wherever they sit — so a number from the stylesheet cannot reach it, "
        "and an `aria-label` on a chart can. If this number is still not a roster count — a year, "
        "a version — the rendered text printed above is what says so, and the defect is then in "
        "this test rather than in the door."
    )
