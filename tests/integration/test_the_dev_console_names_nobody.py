"""The developer console's sections table reports sections, never the people in them.

E1-15 adds a sections table to `GET /dev` because E1 ships no product surface
that renders a section's derived dates and §9.2's exit proof is a browser proof.
That makes it a **new read path over roster-derived rows**, and its contract is
that it carries no identity column of any kind: one row per `section`, with the
derived calendar, an enrolled *count*, and a yes/no on whether a roster address
is stored — never the address, never a member, never an address to mail one.

**Why this module exists rather than a note in a pull request.** The rule was
written into E1-15's build item and asserted nowhere; behaviour shipped with
nothing asserting it is `docs/MISTAKES.md` entry 2, and a console is exactly the
surface where "just this once, to make debugging easier" adds a column. The
browser spec `tests/e2e/exit-synced-section-dates.spec.ts` carries a light
version of the same guard over one section on the composed stack; this is the
durable one, over rows a test owns and members it can name.

**The canary, and why the test is worthless without it.** "This page names
nobody" is trivially true of a page that renders nothing, of a console with no
sections table, and of a section nobody is enrolled in — three states that look
identical to a scan (`docs/MISTAKES.md` entry 3). So the order below is fixed:
the roster is synced first, the identity strings the tool actually stored are
read out of the database and required non-empty, the sections table is required
present, and only then is it searched. Every string searched for is one this
tool demonstrably holds about a member of a section on that page.

**Placed beside `test_dev_console.py` rather than inside it.** That module builds
its application with the mock identity provider mounted and no platform, no
section and no sync; this one needs a registered platform, a section carrying a
roster address, and the sync run against it — `tests/fixtures/roster_sync.py`'s
whole chain. Two fixture shapes, so two modules, and this one names the other.

The console's production half — that `/dev` 404s outside development — is
asserted in `tests/unit/test_dev_console_exposure.py` and is not reopened here.
"""

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

DEV_CONSOLE_PATH = "/dev"

ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEVELOPMENT = "development"

# The mock provider's redirect-URI setting, spelled as `test_dev_console.py` and
# `test_web_login_door.py` spell it.
MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE = "MOCK_IDP_TOOL_REDIRECT_URI"

# A browser-facing OIDC authorization endpoint nothing here sends a browser to;
# it only fills the setting. `.invalid` is RFC 2606.
CONFIGURED_AUTHORIZATION_ENDPOINT = "http://identity-provider.invalid/dev-console-authorize"

# How E1-15 keys a row of the sections table:
# `dev-section-{COURSE_PREFIX}-{COURSE_NUMBER}-{lms_section_code}`. The prefix is
# what identifies the table region, and using it means this module needs no
# table-level testid invented for it and no copy of how a section's own row is
# spelled — which is a value the seeded containment chain generates.
SECTION_ROW_TESTID_PREFIX = "dev-section-"

# Two literals that are identity by construction wherever they appear on this
# page. `@` is how an address gets onto a page at all, and the mock roster
# exposes one per member (ADR 0050); `mock-lms-user-` is the stem of every
# subject that platform signs, and SPEC §4 keys every response to a subject.
#
# They are asserted **as well as** the planted values below, not instead: the
# planted set proves this reader can find what is there, and these two catch a
# member from some other seed, or from some other platform, that the planted set
# would not name.
ADDRESS_MARK = "@"
SUBJECT_STEM = "mock-lms-user-"

# The shortest stored string this module will search the page for. A `user` row
# carries short values that are not identity in any useful sense — a status, a
# single-character flag — and a one-character needle is found in half the markup
# a correct page contains, which would make this red against every
# implementation. Eight is comfortably shorter than a subject or an address and
# comfortably longer than anything that collides by accident.
SHORTEST_TELLING_VALUE = 8

# HTML elements that never carry an end tag, so the row reader's depth counter
# does not go looking for one.
VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

# How much of the page is printed around a suspected leak, so that a failure can
# be told apart from this module reading a value out of markup that means
# something else.
CONTEXT_CHARACTERS = 80


class SectionRowReader(HTMLParser):
    """Every section row on the console, as the whole text and attributes of each.

    Attributes are collected as well as text because an identity can ride one —
    a `title` holding a member's name, an `href` carrying a subject — and a
    reader that only saw text would report a clean page. Its own control test is
    below, per `docs/MISTAKES.md` entry 3: a reader that found nothing anywhere
    would make every assertion in this module pass.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[str] = []
        self._depth = 0
        self._collected: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): (value or "") for name, value in attrs}
        inside = self._depth > 0
        testid = values.get("data-testid", "")
        if not inside and not testid.startswith(SECTION_ROW_TESTID_PREFIX):
            return
        if not inside:
            self._collected = []
        self._collected.extend(values.values())
        if tag not in VOID_ELEMENTS:
            self._depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._depth > 0:
            self._collected.extend((value or "") for _, value in attrs)

    def handle_endtag(self, tag: str) -> None:
        if self._depth == 0 or tag in VOID_ELEMENTS:
            return
        self._depth -= 1
        if self._depth == 0:
            self.rows.append(" ".join(self._collected))

    def handle_data(self, data: str) -> None:
        if self._depth > 0:
            self._collected.append(data)


def section_rows_in(markup: str) -> list[str]:
    """Parse `markup` and hand back the text and attributes of every section row."""
    reader = SectionRowReader()
    reader.feed(markup)
    reader.close()
    return reader.rows


def around(body: str, needle: str) -> str:
    """The markup either side of a found value, so a failure can be judged."""
    at = body.find(needle)
    if at < 0:
        return ""
    return body[max(0, at - CONTEXT_CHARACTERS) : at + len(needle) + CONTEXT_CHARACTERS]


def stored_identity_strings(roster_rows: Any) -> set[str]:
    """Every telling string the tool stored about the people this sync ingested.

    Read out of the `user` and `user_identity` rows rather than composed from
    the mock's seed, so what is searched for is what this tool actually holds —
    the subject it keys a member by, and the address §4's separation puts on the
    other side of the wall. Column names are not spelled anywhere here: every
    string value of every row is taken, and the short ones are dropped for the
    reason `SHORTEST_TELLING_VALUE` gives.
    """
    found: set[str] = set()
    for row in list(roster_rows.users()) + list(roster_rows.identities()):
        for value in dict(row).values():
            if isinstance(value, str) and len(value) >= SHORTEST_TELLING_VALUE:
                found.add(value)
    return found


@pytest.fixture
def provider(mock_idps: Any, door_contract: Any) -> Any:
    """The mock identity provider, registered to return to this tool's own callback.

    The console fetches its web-login roster from the provider, so one is mounted
    for the same reason `test_dev_console.py` mounts one: without it the page
    renders an honest line about a provider it cannot reach, and this module
    would be asserting about a page in a degraded state rather than the one a
    developer sees.
    """
    return mock_idps(
        {
            MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.oidc_callback}"
            )
        }
    )


@pytest.fixture
def dev_console(tool_doors: Any, door_contract: Any, provider: Any) -> Any:
    """The application serving `/dev` in development, with the provider reachable.

    Built exactly as `test_dev_console.py` builds its own — the OIDC endpoints
    come out of the provider's discovery document, the way a client learns them,
    and the provider is mounted under the host those endpoints name. It reads the
    same database the sync below writes to, which is the whole point: the rows
    this module plants are the rows the page renders.
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

    values = {
        names["public_base_url"]: door_contract.public_base_url,
        names["oidc_issuer"]: endpoint("issuer"),
        names["oidc_authorization_endpoint"]: CONFIGURED_AUTHORIZATION_ENDPOINT,
        names["oidc_token_endpoint"]: endpoint("token_endpoint"),
        names["oidc_jwks_url"]: endpoint("jwks_uri"),
        names["oidc_client_id"]: registration["client_id"],
        ENVIRONMENT_VARIABLE: DEVELOPMENT,
    }
    host = urlsplit(endpoint("issuer")).hostname
    return tool_doors(values, {host: provider})


# ---------------------------------------------------------------------------
# The control on the reader, run before anything is believed of it.
# ---------------------------------------------------------------------------


def test_the_section_row_reader_reads_a_rows_text_and_attributes_and_no_other_row() -> None:
    """The control on the scan below (`docs/MISTAKES.md` entry 3).

    Every assertion in this module reports that a section row does *not* contain
    something. A reader that collected nothing would report that about every page
    ever served, including one printing a class list — so it is shown here
    finding text inside a row, finding an attribute value inside a row, and
    **not** collecting a value that sits outside one.

    The last of those is the half that matters: the console lists the web-login
    people by subject elsewhere on the page, by design, so a reader whose region
    leaked into the rest of the document would be red against every correct
    console.
    """
    markup = (
        '<a href="/auth/oidc/login?login_hint=mock-idp-user-dean">sign in</a>'
        "<table><tbody>"
        '<tr data-testid="dev-section-BIOL-215-R3WW">'
        '<td data-testid="section-start-date">2026-09-07</td>'
        '<td data-testid="section-enrolled-count">12</td>'
        "</tr>"
        '<tr data-testid="dev-section-MATH-140-E1FF"><td>2026-08-17</td></tr>'
        "</tbody></table>"
        "<p>somebody@example.invalid</p>"
    )

    rows = section_rows_in(markup)

    assert (
        len(rows) == 2
    ), f"The reader found {len(rows)} section rows in a page carrying two: {rows}."
    assert "2026-09-07" in rows[0], (
        f"The reader collected no cell text from a section row ({rows[0]!r}), so every assertion "
        "below would be about an empty string."
    )
    assert "section-enrolled-count" in rows[0], (
        f"The reader collected no attribute values from a section row ({rows[0]!r}). An identity "
        "can ride an attribute, and a reader blind to them reports a clean page."
    )
    joined = " ".join(rows)
    assert "mock-idp-user-dean" not in joined and "somebody@example.invalid" not in joined, (
        f"The reader collected content from outside the section rows: {rows}. The console lists "
        "the web-login people by subject by design, so a region that leaks is red against every "
        "correct page."
    )


# ---------------------------------------------------------------------------
# The invariant: a synced section, on the console, naming nobody.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_the_dev_consoles_sections_table_names_no_member_of_a_synced_section(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    roster_rows: Any,
    dev_console: Any,
) -> None:
    """SPEC §4: the console reports a section's calendar and a count, and no person.

    **The mutations this kills.** A sections table that renders the roster
    alongside the count, which is the single most useful thing to add to a
    developer console and the reason this rule needed writing down. A table that
    prints the stored roster address, which carries the platform's own context
    identifier and is a service credential's target. A column added later that
    holds "who last synced this" and turns out to be a member.

    **What makes it non-vacuous, in order.** The sync runs first, so the section
    on the page has real members behind it; the strings the tool stored about
    those members are read out of the database and required non-empty, so the
    page is searched for values it demonstrably could have printed; and the
    sections table is required present before it is searched, so an absent table
    fails saying so rather than passing because there was nothing to find.
    """
    roster_sync.call(
        roster_sync.sync_one_section,
        session=committed_rows.session,
        section_id=synced_section.id,
        http=service_wire.session(),
    )
    committed_rows.commit()

    planted = stored_identity_strings(roster_rows)
    assert planted, (
        "The sync wrote no `user` or `user_identity` row carrying a string this test could "
        "look for, so there is nothing the console could have leaked. The section is "
        f"{synced_section.id} and its roster address is {synced_section.address!r}; if the "
        "sync did not run, every assertion below passes over a page about a section nobody "
        "is in."
    )

    answered = dev_console.get(DEV_CONSOLE_PATH)
    assert answered.status_code == 200, (
        f"`GET {DEV_CONSOLE_PATH}` answered {answered.status_code} with `{ENVIRONMENT_VARIABLE}` "
        f"set to {DEVELOPMENT!r}. Body begins {answered.text[:300]!r}."
    )
    body = answered.text

    rows = section_rows_in(body)
    assert rows, (
        f"The console renders no element whose `data-testid` begins `{SECTION_ROW_TESTID_PREFIX}`, "
        "so it has **no sections table** — the surface E1-15 adds so the exit proof can read a "
        "section's derived dates in a browser. This test is about what that table must not carry, "
        f"and there is nothing to read. Body begins {body[:300]!r}."
    )

    region = " ".join(rows)

    leaked = sorted(value for value in planted if value in region)
    assert not leaked, (
        f"The console's sections table carries {len(leaked)} value(s) the tool stored about the "
        f"people in that section: {leaked[:5]}. The first sits in "
        f"{around(region, leaked[0])!r}. E1-15's contract for this table is one row per section "
        "with its derived calendar, an enrolled count and a yes/no on the roster address — no "
        "identity column of any kind. SPEC §4 keys every response to a subject and §4.1 separates "
        "an address from it; a development console is not an exemption from either."
    )
    assert ADDRESS_MARK not in region, (
        f"The console's sections table carries an {ADDRESS_MARK!r}, which is how an email address "
        f"gets onto a page: {around(region, ADDRESS_MARK)!r}. The mock roster exposes an address "
        "per member (ADR 0050) and the sync stores it; the table reports the section."
    )
    assert SUBJECT_STEM not in region, (
        f"The console's sections table names a launch subject: {around(region, SUBJECT_STEM)!r}. "
        "A subject is what SPEC §4 keys every response to, and a table that prints one has put an "
        "identity on a read path that carries a calendar and a count."
    )
