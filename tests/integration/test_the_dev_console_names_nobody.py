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
the roster is synced first, the values that would constitute a leak are read out
of the database and required non-empty, the sections table is required present,
and only then is it searched. Every string searched for is one this tool
demonstrably holds about a member of a section on that page.

**What "a leak" means here is three sets, and two of them are the live ones.**
The subjects and addresses the sync stored on `user` and `user_identity` are
unreachable by this page today — `pulse_app` is granted no `SELECT` on either —
so they are defence in depth against a future grant. What *is* reachable is the
member keys on `public.section_roster`, because that view is granted
deliberately, and the roster address on the `section` row itself. Those two are
what a console-only mutation can actually render, and each carries its own
canary.

Both were added after the fact, one round apart, and the pattern is the lesson:
the first version searched the unreachable half alone; a battery mutation
rendering each section's `user_id` walked through it, because a `user_id` is a
UUID and matched neither the string-valued set nor the literal shapes; and a
security review then found the roster address sitting in the same blind spot,
one value over. The rule that would have caught both at once is to start from
what the page's own connection is granted, and only then ask what of it is
forbidden here — rather than from the values that felt like identity.

**Placed beside `test_dev_console.py` rather than inside it.** That module builds
its application with the mock identity provider mounted and no platform, no
section and no sync; this one needs a registered platform, a section carrying a
roster address, and the sync run against it — `tests/fixtures/roster_sync.py`'s
whole chain. Two fixture shapes, so two modules, and this one names the other.

The console's production half — that `/dev` 404s outside development — is
asserted in `tests/unit/test_dev_console_exposure.py` and is not reopened here.

**The `invariant` marker moved from the denial test to the module**, in E1's
re-review fixes, and the whole module joined the isolated §4.1 pass with it. It
was not wrong before: the denial below carried `@pytest.mark.invariant` and ran
in that pass exactly as it does now. What was wrong is what the *next* denial
test in this module would have inherited, which is nothing —
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
demands the module-level form for that reason and names this module as one of the
four it found. So the two readers above it are now invariant tests too. That is
the cost and it is small: they are the instrument this file's denial is measured
with, and a module whose reader can be skipped while its denial cannot is a
module whose denial is measured by nothing. `tests/unit/test_no_service_reads_an_
identity_table_directly.py` marks its own control the same way.
"""

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import pytest
from sqlalchemy import text

# `invariant` joins the list rather than replacing it, and it sits here rather
# than on the one denial test below. See the module docstring on why the marker
# moved; the rule is
# `tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.
pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]

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

# Three literals that are identity by construction wherever they appear on this
# page. `@` is how an email address gets onto a page at all, and the mock roster
# exposes one per member (ADR 0050); `mock-lms-user-` is the stem of every
# subject that platform signs, and SPEC §4 keys every response to a subject; and
# `://` is how a service address gets onto a page, which for this table means the
# roster address a launch stored on the section. The third is `SERVICE_ADDRESS_
# MARK` and is declared further down, beside the read that collects the stored
# addresses; it is asserted here for the same reason as the other two.
#
# They are asserted **as well as** the planted values below, not instead: the
# planted set proves this reader can find what is there, and these three catch a
# member from some other seed, from some other platform, or an address spelled in
# a way the exact-string set cannot match — HTML-escaped, re-cased, or built up
# from parts — that the planted set would not name.
ADDRESS_MARK = "@"
SUBJECT_STEM = "mock-lms-user-"

# The shortest stored string this module will search the page for. A `user` row
# carries short values that are not identity in any useful sense — a status, a
# single-character flag — and a one-character needle is found in half the markup
# a correct page contains, which would make this red against every
# implementation. Eight is comfortably shorter than a subject or an address and
# comfortably longer than anything that collides by accident.
#
# The member keys added below clear it without needing an exemption: a UUID is 36
# characters written out and 32 with the hyphens stripped.
SHORTEST_TELLING_VALUE = 8

# The read view the console's own connection can reach a member through, and the
# column on it that names one. **`pulse_app` is granted `SELECT` on this view and
# on `user_id` deliberately** — `tests/integration/test_identity_grants.py`'s
# `SANCTIONED_VIEW_COLUMNS` records the sentence that admits it, because the
# Pulse-internal key "is what makes a de-identified response addressable" for
# instructor-scoped code. Sanctioned there is not sanctioned here: E1-15's
# contract for the sections table is a calendar, a count and a yes/no, and a
# stable per-person key on a developer console is an identity column whether or
# not it resolves to a name by itself.
#
# This is the reachable surface, so it is the one a console-only mutation can
# render, and it is what the battery proved this sweep was blind to.
ROSTER_VIEW = "section_roster"
ROSTER_MEMBER_KEY = "user_id"

# The table the console reads a section off, and what marks a stored service
# address on one of its rows. The roster address —
# `section.lms_context_memberships_url` — is the second value E1-15's contract
# forbids this table outright: it is where a launch said this section's roster
# lives, it carries the platform's own context identifier, and it is the target
# a bearer token is spent against. ADR 0100 is the record.
#
# Found by the `://` rather than by column name, so the sweep does not hold a
# copy of the schema's spelling and picks up any *other* address a later column
# might store. The section this test synced carries one by construction, which is
# what makes the canary below exact rather than hopeful.
SECTION_TABLE = "section"
SERVICE_ADDRESS_MARK = "://"

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

    **This half is defence in depth and not the live half, which is worth saying
    so nobody later reads it as dead code.** The battery established that
    `pulse_app` holds no `SELECT` on `user` or `user_identity` at all, so no
    mutation confined to the console can put a subject or an address on the page
    — the connection cannot read them. It stays because the grant is what makes
    that true, and a grant is one migration away from changing; the day one
    arrives, this set is already searching for what it would expose.

    The half that *is* live is `member_keys_the_console_can_reach` below.
    """
    found: set[str] = set()
    for row in list(roster_rows.users()) + list(roster_rows.identities()):
        for value in dict(row).values():
            if isinstance(value, str) and len(value) >= SHORTEST_TELLING_VALUE:
                found.add(value)
    return found


def stored_roster_addresses(roster_rows: Any) -> set[str]:
    """Every service address stored on a `section` row.

    **The second survivor of the same shape as the first**, and the review that
    found it called it that: the sweep already searched for what the console
    cannot reach and for member keys, and left out the one *other* forbidden
    value its connection can read. This module's own docstring listed "prints the
    stored roster address" among the mutations it kills, and that sentence was
    false — a record asserting something nothing enforced (`docs/MISTAKES.md`
    entry 1 meeting entry 2).

    Read off the rows rather than taken from the fixture object, because what
    matters is that the value is reachable *in the database* the console queries.
    The fixture's own copy is used in the test as the canary that this read found
    the right thing.
    """
    found: set[str] = set()
    for row in roster_rows.all_of(SECTION_TABLE):
        for value in dict(row).values():
            if isinstance(value, str) and SERVICE_ADDRESS_MARK in value:
                found.add(value)
    return found


def member_keys_the_console_can_reach(committed: Any, section_id: Any) -> tuple[set[str], set[str]]:
    """Every member key reachable through `section_roster`, and this section's own.

    **The half the battery found missing.** A mutation that rendered each
    section's member `user_id` into a cell — from the one view the console's
    connection is granted — survived this module untouched, and two decisions of
    mine let it: `stored_identity_strings` keeps only `str` values, and a
    `user_id` is a `uuid.UUID`, so it was in neither the planted set nor the two
    literals. The rule the docstring states ("names no member") and the contract
    the ticket writes ("no user ids") both forbid it, and nothing asserted it.

    Both forms are returned. `str(...)` is the hyphenated spelling anything
    rendering a UUID produces by default, and the hyphen-stripped one is the near
    miss — `uuid.hex`, or a template that tidies it — which would otherwise walk
    straight through a search for the first.

    Two sets rather than one, because they answer two questions. Every key on the
    view is the search set: the console lists every section, so a key belonging
    to some other test's section is as much a leak as one belonging to this
    test's. This section's own keys are the canary: the sync above demonstrably
    wrote them, so a page searched for them is a page searched for values that
    certainly exist behind it.

    **`committed` is the `CommittedRows` the `committed_rows` fixture yields**,
    not the `RosterRows` beside it, and the difference is one this function got
    wrong once: `RosterRows` keeps its `CommittedRows` as `self.rows` and exposes
    no `session` of its own, so a `roster_rows.session` here raised
    `AttributeError` before any assertion ran — a broken test rather than a red
    one. `CommittedRows.__init__` is where `session` is defined
    (`tests/fixtures/authz_data.py`), and the test already holds that object,
    which is what it passes.
    """
    # Rollback first, so this read sees what another connection committed. That
    # is `RosterRows.all_of`'s own arrangement, made through the same
    # `CommittedRows`, and it is the fixture's intent rather than this module's
    # invention.
    committed.session.rollback()
    # Column and view names are the two constants above; the statement is written
    # out rather than interpolated so nothing here composes SQL from a name.
    statement = text("SELECT section_id, user_id FROM public.section_roster")
    found = committed.session.execute(statement).all()

    def spellings(value: Any) -> set[str]:
        written = str(value)
        return {written, written.replace("-", "")}

    reachable = {spelling for _, member in found for spelling in spellings(member)}
    this_section = {
        spelling
        for section, member in found
        if section == section_id
        for spelling in spellings(member)
    }
    return reachable, this_section


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
# The invariant: a synced section, on the console, naming nobody. Marked at the
# top of the module rather than here — see the module docstring.
# ---------------------------------------------------------------------------


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
    developer console and the reason this rule needed writing down. A column
    added later that holds "who last synced this" and turns out to be a member.
    And two this file listed before it could kill: a cell holding each member's
    `user_id`, and a cell printing the stored roster address, which carries the
    platform's own context identifier and is a service credential's target.

    **And one the exact-string set cannot kill on its own**, which is why the
    literals are asserted beside it: an address that reaches the region in some
    other spelling — HTML-escaped, re-cased, or assembled from parts — matches no
    stored string and would walk through the planted set untouched. `@` and `://`
    are what it cannot lose on the way, so the two of them are the backstop and
    neither is a repeat of the search above.

    **Both of those were claims before they were assertions**, found one round
    apart and by different readers — the battery for the first, the security
    review for the second, which named it the identical survivor pattern one
    value over. The docstring you are reading listed each among the mutations
    this test kills while the planted set contained neither. That is
    `docs/MISTAKES.md` entry 2 arriving through entry 1: a record that described
    a guarantee, and a reader — me — who wrote the description from the contract
    rather than from what the set actually held. Both are in the set now, each
    with its own canary below.

    **The mutation that survived, and what it changed here.** The Loop B battery
    rendered `section_roster.user_id` into a cell and this test passed. Two
    decisions of mine let it through: the planted set was built from `str` values
    only, and a `user_id` is a `uuid.UUID`; and the two literals it also searches
    for, an `@` and the launch-subject stem, are shapes a UUID does not have. So
    the sweep was searching diligently for the two things the console's own
    connection **cannot** reach and not for the one thing it can. That is
    `docs/MISTAKES.md` entry 3 in the plainest form: a green that measured the
    wrong surface.

    The battery's other finding runs the other way and is in the code's favour:
    `pulse_app` holds no `SELECT` on `user` or `user_identity`, so no
    console-only mutation can put a subject or an address on the page at all.
    Those stay in the planted set as defence in depth against a future grant —
    `stored_identity_strings` says so — and `section_roster` is the live half.

    **A member key is an identity column even though it names nobody**, and the
    grant on that view is not a licence for this page. `carried-from-e0.md`'s
    sweep entry is the record: a stable per-person key resolves a de-identified
    response to a person in one join, which is why the reveal's composition
    treats it as the thing to guard. `section_roster.user_id` is sanctioned for
    instructor-scoped code, by name, in
    `tests/integration/test_identity_grants.py`; E1-15's contract for this table
    is a calendar, a count and a yes/no, and nothing on it is a person.

    **What makes it non-vacuous, in order.** The sync runs first, so the section
    on the page has real members behind it; each of the three sets is read out of
    the database and carries its own guard — the stored strings must be
    non-empty, this section's member keys must be non-empty, and this section's
    roster address must be among the addresses found on the `section` rows — so
    the page is searched for values it demonstrably could have printed; and the
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

    stored = stored_identity_strings(roster_rows)
    assert stored, (
        "The sync wrote no `user` or `user_identity` row carrying a string this test could "
        "look for, so there is nothing the console could have leaked. The section is "
        f"{synced_section.id} and its roster address is {synced_section.address!r}; if the "
        "sync did not run, every assertion below passes over a page about a section nobody "
        "is in."
    )

    reachable, this_section = member_keys_the_console_can_reach(committed_rows, synced_section.id)
    assert this_section, (
        f"`public.{ROSTER_VIEW}` reports no {ROSTER_MEMBER_KEY} for section "
        f"{synced_section.id}, so the live half of this sweep is searching for nothing. That "
        "view is the one surface the console's own connection is granted a member through, "
        "which makes it the only thing a console-only mutation can render — the sync above "
        "wrote the enrollments behind it, so an empty answer here means the sync did not "
        "reach this section rather than that the console is clean."
    )

    addresses = stored_roster_addresses(roster_rows)
    assert synced_section.address in addresses, (
        f"The roster address this test's section was seeded with ({synced_section.address!r}) is "
        f"not among the addresses readable off the `{SECTION_TABLE}` rows ({sorted(addresses)}). "
        "That address is the second value E1-15's contract forbids this table, and the whole of "
        "what makes searching for it meaningful is that the console's own connection can read it "
        "from the database — so an empty or wrong answer here means this half of the sweep is "
        "looking for something that is not there to be leaked."
    )

    # Three sets, searched as one. The member keys and the addresses clear
    # `SHORTEST_TELLING_VALUE` on their own — a UUID is 36 characters, 32 without
    # hyphens, and a URL is longer than either — so no exemption is needed.
    planted = stored | reachable | addresses

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
        f"The console's sections table carries {len(leaked)} value(s) that name a member of a "
        f"section: {leaked[:5]}. The first sits in {around(region, leaked[0])!r}.\n\n"
        "If it is a service address, that is the roster address a launch stored on the section: "
        "it carries the platform's own context identifier and is where a bearer token gets spent, "
        "and the table reports whether one is stored as a yes or a no and never the value.\n\n"
        f"If it is a `{ROSTER_MEMBER_KEY}` from `public.{ROSTER_VIEW}`, read this before "
        "reaching for the grant: that view hands the key to instructor-scoped code by design and "
        "is sanctioned by name in `tests/integration/test_identity_grants.py`, so the repair is "
        "not a grant change — it is that a stable per-person key does not belong on this page. It "
        "resolves a de-identified response to a person in one join, which is what "
        "`carried-from-e0.md`'s sweep entry records, and it is an identity column even though it "
        "names nobody by itself.\n\n"
        "E1-15's contract for this table is one row per section with its derived calendar, an "
        "enrolled count and a yes/no on the roster address — no identity column of any kind. "
        "SPEC §4 keys every response to a subject and §4.1 separates an address from it; a "
        "development console is not an exemption from either."
    )
    assert ADDRESS_MARK not in region, (
        f"The console's sections table carries an {ADDRESS_MARK!r}, which is how an email address "
        f"gets onto a page: {around(region, ADDRESS_MARK)!r}. The mock roster exposes an address "
        "per member (ADR 0050) and the sync stores it; the table reports the section."
    )
    assert SERVICE_ADDRESS_MARK not in region, (
        f"The console's sections table carries a {SERVICE_ADDRESS_MARK!r}, which is how a service "
        f"address gets onto a page: {around(region, SERVICE_ADDRESS_MARK)!r}. The roster address a "
        "launch stored on the section is the one this table forbids — it carries the platform's "
        "own context identifier and is where a bearer token gets spent (ADR 0100) — and the table "
        "reports whether one is stored as a yes or a no, never the value. This backstops the "
        "exact-string set above rather than repeating it: an address that reached the page "
        "HTML-escaped, re-cased, or assembled from parts matches no stored string and still "
        "carries its scheme separator."
    )
    assert SUBJECT_STEM not in region, (
        f"The console's sections table names a launch subject: {around(region, SUBJECT_STEM)!r}. "
        "A subject is what SPEC §4 keys every response to, and a table that prints one has put an "
        "identity on a read path that carries a calendar and a count."
    )
