"""The `/dev` clock control, driven over HTTP against a real database — E2-04.

The serving half of criterion 2: "In development, setting the pretend now from
`/dev` changes what the backend and the worker both answer; clearing it returns
them to real time." The backend half is here; the worker half is
`tests/integration/test_the_dev_clock_reaches_the_worker.py`, and the browser half
is `tests/e2e/dev-clock.spec.ts`.

**The refusal direction is `tests/unit/test_dev_clock_control_exposure.py`**, and
the two are a pair that only means something together: a control that only ever
refuses cannot be told from one that never worked, which is the observation ADR
0079's consequences section makes about the console these routes sit on.

**The console is built with the mock identity provider mounted**, exactly as
`tests/integration/test_dev_console.py` builds it, because `GET /dev` fetches the
provider's roster over `app.state.http` before it renders anything. That fixture
is deliberately a second copy rather than a shared one: the module next door is
this suite's proven-green baseline for the console, and moving its fixture out
would put a diff on the baseline inside the pull request that is trying to use it
as one — the reason `tests/e2e/support/doors.ts` gives for leaving the six
existing specs alone. If a third console suite arrives, that is the moment the
builder moves into `tests/fixtures/` (`docs/MISTAKES.md` entry 13).

**What is pinned and what is left to the implementer.** The testids, the form
field name, the redirect and the row are E2-04's work order and are asserted
exactly. The *wording* of the two readouts is not: a readout is asserted to be
non-empty, to carry the pretended year while an override stands, and to stop
carrying it once it is cleared. A year is in every rendering of an instant that
anybody would put on a page, and it is five years away from real time here, so
this discriminates without making an improvement to the copy a test change.
"""

from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from fixtures.clock import ANCHORED_AT_COLUMN, DEVELOPMENT, PRETEND_NOW_COLUMN

pytestmark = pytest.mark.integration

ENVIRONMENT_VARIABLE = "ENVIRONMENT"
INSTITUTION_TIMEZONE_VARIABLE = "INSTITUTION_TIMEZONE"

DEV_CONSOLE_PATH = "/dev"
DEV_CLOCK_SET_PATH = "/dev/clock"
DEV_CLOCK_CLEAR_PATH = "/dev/clock/clear"

# The form field and the five testids, spelled by E2-04's work order. A deliberate
# rename is these six lines, here and in `tests/e2e/dev-clock.spec.ts`.
PRETEND_NOW_FIELD = "pretend_now"
EFFECTIVE_NOW_TESTID = "clock-effective-now"
OVERRIDE_STATE_TESTID = "clock-override-state"
PRETEND_NOW_INPUT_TESTID = "clock-pretend-now"
SET_BUTTON_TESTID = "clock-set"
CLEAR_BUTTON_TESTID = "clock-clear"

# What a browser sends from an `<input type="datetime-local">`: a local wall time
# with no offset, minute precision. The work order settles both the shape and the
# reading — it is interpreted in `settings.institution_timezone`.
POSTED_PRETEND_NOW = "2031-03-14T10:30"
POSTED_YEAR = "2031"

# Two zones at the far ends of the offset range, so that the same posted wall time
# is two instants fourteen hours and one minute apart depending on which one the
# handler reads it in. Neither observes daylight saving, so the offsets are the
# whole of the arithmetic.
CANDIDATE_TIMEZONES = ("Pacific/Kiritimati", "Pacific/Niue")

# The mock provider's redirect-URI setting, spelled as the console suite next door
# spells it: it is compared exactly on the way in and again at the token endpoint.
MOCK_IDP_TOOL_REDIRECT_URI_VARIABLE = "MOCK_IDP_TOOL_REDIRECT_URI"

# A browser-facing authorization endpoint nothing here reaches; only used to fill
# the setting. `.invalid` is RFC 2606.
CONFIGURED_AUTHORIZATION_ENDPOINT = "http://identity-provider.invalid/dev-clock-authorize"

# HTML elements that carry no end tag, so a reader that pushed them onto a stack
# would never pop them and would attribute the rest of the page to whatever was
# open. `input` is the one that matters here — the pretend-now field is one.
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


class ElementsByTestid(HTMLParser):
    """Every `data-testid` on a page, with its attributes and its own text.

    A parser rather than a regular expression, for the reason
    `tests/integration/test_dev_console.py` gives about its anchor reader: the
    properties under test are about which text sits inside which element, and a
    pattern over markup answers a question that only looks the same
    (`docs/MISTAKES.md` entry 3). Its control is the first test below.

    Text is attributed to **every** open element carrying a testid, so a readout
    nested inside a labelled container is found under both names rather than under
    neither.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []
        self.text: dict[str, str] = {}
        self.attributes: dict[str, dict[str, str]] = {}

    def _record(self, attrs: list[tuple[str, str | None]]) -> str | None:
        values = {name.lower(): (value or "") for name, value in attrs}
        testid = values.get("data-testid")
        if testid is not None:
            self.attributes[testid] = values
            self.text.setdefault(testid, "")
        return testid

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        testid = self._record(attrs)
        if tag.lower() not in VOID_ELEMENTS:
            self.stack.append((tag.lower(), testid))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(attrs)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == name:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        for _, testid in self.stack:
            if testid is not None:
                self.text[testid] += data


def read_testids(markup: str) -> ElementsByTestid:
    """Parse `markup` and hand back the reader holding what it found.

    **Named `read_testids` and not `testids_in`**, and the class above is
    `ElementsByTestid` and not `TestidReader`, because pytest collects on a bare
    `test` prefix for functions and a `Test` prefix for classes. A helper called
    `testids_in(markup)` is collected as a test and errors with "fixture 'markup'
    not found" — a red that says nothing about the console and stops the module
    before any real assertion runs.
    """
    reader = ElementsByTestid()
    reader.feed(markup)
    reader.close()
    return reader


def text_of(reader: ElementsByTestid, testid: str) -> str:
    """The whitespace-collapsed text of one testid, or a failure saying it is absent."""
    assert testid in reader.attributes, (
        f"The console carries no element with `data-testid={testid!r}` (it carries "
        f"{sorted(reader.attributes)}). E2-04's work order settles that name."
    )
    return " ".join(reader.text.get(testid, "").split())


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
def dev_console(
    tool_doors: Any,
    door_contract: Any,
    provider: Any,
    committed_clock_overrides: Any,
) -> Any:
    """Build the tool in development with the provider mounted, so `/dev` renders.

    The same arrangement as `tests/integration/test_dev_console.py`'s fixture of
    the same name: the OIDC endpoints come out of the provider's own discovery
    document, and the provider is mounted under the host those endpoints name, so
    the console's roster fetch resolves in process.

    **`committed_clock_overrides` is depended on rather than used**, for the
    teardown order `tests/fixtures/authz_data.py`'s `care_connections` depends on
    it for: fixtures are finalised in reverse of setup, so naming it here makes its
    `DELETE FROM clock_override` run *after* this tool's connections are closed.

    **The institution timezone is an override the caller passes**, never a default
    set here: which zone a posted wall time is read in is exactly what one test
    below is about (`docs/MISTAKES.md` entry 30).
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
        host = urlsplit(endpoint("issuer")).hostname
        return tool_doors(values, {host: provider})

    return build


def console_page(client: Any) -> ElementsByTestid:
    """`GET /dev` in development, parsed, with the answer checked first."""
    response = client.get(DEV_CONSOLE_PATH)
    assert response.status_code == 200, (
        f"`GET {DEV_CONSOLE_PATH}` answered {response.status_code} with `{ENVIRONMENT_VARIABLE}` "
        f"set to {DEVELOPMENT!r}. The console is served in development and nowhere else; a 404 "
        f"here is the gate closed on the direction it must stay open. Body begins "
        f"{response.text[:300]!r}."
    )
    return read_testids(response.text)


def redirected_to_the_console(response: Any, what: str) -> None:
    """A control route answered `303` and sent the browser back to `/dev`."""
    assert response.status_code == 303, (
        f"{what} answered {response.status_code}. E2-04's work order settles both control routes at "
        "a 303 back to the console, which is what stops a browser reload from re-posting the form. "
        f"Body begins {response.text[:300]!r}."
    )
    location = response.headers.get("location") or ""
    assert location.rstrip("/").endswith(DEV_CONSOLE_PATH), (
        f"{what} redirected to {location!r}, which does not lead back to {DEV_CONSOLE_PATH}. The "
        "control is a section of the console and a developer who used it is looking at the console "
        "again afterwards."
    )


# ---------------------------------------------------------------------------
# The control on the testid reader, before anything is believed of it.
# ---------------------------------------------------------------------------


def test_the_testid_reader_finds_a_readout_a_void_input_and_their_attributes() -> None:
    """The control on every console assertion below (`docs/MISTAKES.md` entry 3).

    Every test in this module reports what one testid's text says, and two of them
    report that a testid's text *stops* saying something. A reader that found no
    testids would make the first kind fail for the wrong reason and the second kind
    pass for no reason at all — the second is the dangerous half.

    Three properties are shown, and each is a way this reader could be quietly
    wrong:

      - it picks the text out of the element carrying the testid, and not the text
        of the whole page;
      - it does not attribute a later sibling's text to an earlier readout, which
        is what a naive depth counter does the moment it meets `<input>`: that tag
        has no end tag, so a counter that pushed it would never pop and would
        swallow the rest of the document;
      - it reads attributes off the element, which is how the form field's `name`
        is checked below.

    Needs no implementation and is green now. If it is red, nothing else in this
    module means what it says.
    """
    markup = (
        '<section data-testid="clock-effective-now">2031-03-14 10:30 UTC</section>'
        '<span data-testid="clock-override-state">override active</span>'
        '<form><input data-testid="clock-pretend-now" name="pretend_now" '
        'type="datetime-local" value="">'
        '<button data-testid="clock-set">set</button></form>'
    )

    reader = read_testids(markup)

    assert text_of(reader, EFFECTIVE_NOW_TESTID) == "2031-03-14 10:30 UTC", (
        f"The reader read {text_of(reader, EFFECTIVE_NOW_TESTID)!r} out of the effective-now "
        "element. Every readout assertion below is made with it."
    )
    assert (
        text_of(reader, OVERRIDE_STATE_TESTID) == "override active"
    ), f"The reader read {text_of(reader, OVERRIDE_STATE_TESTID)!r} out of the state element."
    assert text_of(reader, PRETEND_NOW_INPUT_TESTID) == "", (
        f"The reader attributed {text_of(reader, PRETEND_NOW_INPUT_TESTID)!r} to a void `<input>`. "
        "An `<input>` has no end tag, so a reader that pushed it onto its stack would go on "
        "attributing every later element's text to it — including the submit button's — and a "
        "test asserting that a readout no longer names a year would then be reading the wrong "
        "element entirely."
    )
    assert reader.attributes[PRETEND_NOW_INPUT_TESTID].get("name") == PRETEND_NOW_FIELD, (
        f"The reader read the input's attributes as {reader.attributes[PRETEND_NOW_INPUT_TESTID]}. "
        "The `name` is what the form posts under and what the route reads, and it is checked below."
    )


# ---------------------------------------------------------------------------
# What the console shows, and what the two routes do.
# ---------------------------------------------------------------------------


def test_the_console_carries_the_clock_readouts_and_both_controls_in_development(
    dev_console: Any,
) -> None:
    """The console shows the effective clock beside the section table, and offers both controls.

    E2-04's scope: "`/dev` grows the control: set the pretend now, see the
    effective now, clear it… show the effective clock beside it so an overridden
    stack is never mistaken for a live one." All five names are E2-04's work
    order's.

    **The mutations this kills**: a console that grew the two POST routes and no
    way to reach them, which is a control a developer cannot use; and a form whose
    field is named something other than `pretend_now`, which posts a body the route
    does not read and fails as a validation error nobody can see from the browser.

    **Why the effective-now readout is required non-empty**: an element rendered
    with nothing in it satisfies "the console shows the effective clock" while
    showing nothing, and it is exactly what a readout wired to a value the handler
    forgot to pass looks like (`docs/MISTAKES.md` entry 3).

    The wording of neither readout is pinned. What is pinned is that they exist,
    that they say something, and — in the tests below — that what they say changes
    with the row.
    """
    reader = console_page(dev_console())

    for testid in (
        EFFECTIVE_NOW_TESTID,
        OVERRIDE_STATE_TESTID,
        PRETEND_NOW_INPUT_TESTID,
        SET_BUTTON_TESTID,
        CLEAR_BUTTON_TESTID,
    ):
        assert testid in reader.attributes, (
            f"The console carries no `data-testid={testid!r}`; it carries "
            f"{sorted(reader.attributes)}. E2-04 settles these five names, and "
            "`tests/e2e/dev-clock.spec.ts` drives the page by them."
        )

    assert text_of(reader, EFFECTIVE_NOW_TESTID), (
        "The console's effective-now readout is empty. The point of showing it is that an "
        "overridden stack is never mistaken for a live one, and a blank space says neither."
    )
    assert text_of(reader, OVERRIDE_STATE_TESTID), (
        "The console's override-state readout is empty, so the page does not say whether an "
        "override is active — which is half of what the section is for."
    )
    assert reader.attributes[PRETEND_NOW_INPUT_TESTID].get("name") == PRETEND_NOW_FIELD, (
        f"The pretend-now input posts under "
        f"{reader.attributes[PRETEND_NOW_INPUT_TESTID].get('name')!r}; `POST "
        f"{DEV_CLOCK_SET_PATH}` reads `{PRETEND_NOW_FIELD}`. A form that posts a field the route "
        "does not read is a control that answers 422 to every use."
    )


def test_posting_a_pretend_now_writes_the_override_and_moves_the_consoles_own_clock(
    dev_console: Any, committed_clock_overrides: Any
) -> None:
    """Criterion 2, the setting half, over HTTP: the row is written and the page moves.

    **The mutations this kills**: a handler that answers 200 and writes nothing; one
    that writes the pretended instant and no anchor, which leaves the service unable
    to add elapsed time and turns the offset into a freeze; and a console whose
    readout is computed from the real clock rather than from the service, which is
    how an overridden stack ends up looking live.

    **Both the row and the readout are asserted, and neither would do alone.** The
    row alone says nothing about whether anything reads it; the readout alone would
    be satisfied by a console that echoed back whatever was posted without storing
    it, which no other process could then see.

    The anchor is required to be near real time rather than near the pretended
    instant: it is the *real* moment the override was set, and a handler that
    stored the pretended instant in both columns produces a clock that is correct
    at the instant it is set and then runs at the right rate from the wrong place —
    a defect no single reading of `now` can distinguish.
    """
    client = dev_console()

    posted = client.post(DEV_CLOCK_SET_PATH, data={PRETEND_NOW_FIELD: POSTED_PRETEND_NOW})
    redirected_to_the_console(posted, f"`POST {DEV_CLOCK_SET_PATH}`")

    written = committed_clock_overrides.rows()
    assert len(written) == 1, (
        f"`POST {DEV_CLOCK_SET_PATH}` left {len(written)} rows in `clock_override`: {written}. The "
        "control sets or replaces the single row, and the table holds at most one by a unique "
        "index over `(true)`."
    )
    stored_pretend = written[0][PRETEND_NOW_COLUMN]
    assert stored_pretend.year == int(POSTED_YEAR), (
        f"The posted pretend now {POSTED_PRETEND_NOW!r} was stored as {stored_pretend!r}. The "
        "handler reads an HTML `datetime-local` value and stores the instant it names; a year "
        "other than the posted one means the value was not parsed at all."
    )
    anchored = written[0][ANCHORED_AT_COLUMN]
    assert abs((anchored - datetime.now(UTC)).total_seconds()) < 300, (
        f"The row's `{ANCHORED_AT_COLUMN}` is {anchored!r} and real time is about "
        f"{datetime.now(UTC)!r}. The anchor is the *real* instant the override was set at — it is "
        "what the service measures elapsed time from — so a handler that stored the pretended "
        "instant there produces a clock running at the right rate from the wrong origin."
    )

    shown = text_of(console_page(client), EFFECTIVE_NOW_TESTID)
    assert POSTED_YEAR in shown, (
        f"The console's effective-now readout says {shown!r} with the clock overridden to "
        f"{POSTED_PRETEND_NOW!r}. Any rendering of an instant in {POSTED_YEAR} carries that year, "
        "and real time is five years away from it, so a readout without it is the console showing "
        "the real clock beside an override it is ignoring — the exact confusion the section exists "
        "to prevent."
    )


def test_clearing_the_override_returns_the_console_to_real_time(
    dev_console: Any, committed_clock_overrides: Any
) -> None:
    """Criterion 2, the clearing half, over HTTP: the row goes and the page comes back.

    Set through the control, read, clear through the control, read again — one
    test, because the claim is about the transition and a second test would have to
    assert against a state the first one produced.

    **The mutations this kill**: a clear route that answers 303 and deletes
    nothing; one that deletes the row but leaves a console rendering a cached
    effective now; and a "clear" implemented as writing a zero offset, which is a
    row nothing else in this product knows how to read — so the table is required
    empty as well.

    The moved reading is taken first and required to be moved, because "the console
    shows real time" is satisfied perfectly by an override that never applied
    (`docs/MISTAKES.md` entry 3).
    """
    client = dev_console()

    client.post(DEV_CLOCK_SET_PATH, data={PRETEND_NOW_FIELD: POSTED_PRETEND_NOW})
    moved = text_of(console_page(client), EFFECTIVE_NOW_TESTID)
    assert POSTED_YEAR in moved, (
        f"The console's effective-now readout says {moved!r} after the override was set to "
        f"{POSTED_PRETEND_NOW!r}. The clock never moved, so the assertion that clearing brings it "
        "back would be about a clock that never left."
    )
    state_while_set = text_of(console_page(client), OVERRIDE_STATE_TESTID)

    cleared = client.post(DEV_CLOCK_CLEAR_PATH)
    redirected_to_the_console(cleared, f"`POST {DEV_CLOCK_CLEAR_PATH}`")

    assert committed_clock_overrides.rows() == [], (
        f"`POST {DEV_CLOCK_CLEAR_PATH}` left {committed_clock_overrides.rows()} in "
        "`clock_override`. Clearing removes the row; a row holding a zero offset answers the same "
        "instants today and is a state the service is not written for."
    )

    reader = console_page(client)
    restored = text_of(reader, EFFECTIVE_NOW_TESTID)
    assert POSTED_YEAR not in restored, (
        f"The console's effective-now readout still says {restored!r} after the override was "
        f"cleared, and {POSTED_YEAR} is five years from real time. The offset outlived the row it "
        "came from, which on a running stack means clearing the clock appears to do nothing until "
        "the process restarts."
    )
    assert text_of(reader, OVERRIDE_STATE_TESTID) != state_while_set, (
        f"The console's override-state readout says {text_of(reader, OVERRIDE_STATE_TESTID)!r} "
        f"both while an override stood and after it was cleared. Its whole job is to tell those "
        "two states apart, so that an overridden stack is never mistaken for a live one."
    )


@pytest.mark.parametrize("zone", CANDIDATE_TIMEZONES)
def test_the_posted_pretend_now_is_read_in_the_institution_timezone(
    zone: str, dev_console: Any, committed_clock_overrides: Any
) -> None:
    """A `datetime-local` value carries no offset, and the institution's zone is what supplies it.

    E2-04's work order settles the reading: the form field is an HTML
    `datetime-local` value — a wall time with no offset — "interpreted in the
    institution timezone, converted to aware before storage". SPEC §3.1 makes that
    the zone every window is expressed in, so a developer typing `18:30` to reach a
    Friday-evening window means 18:30 where the institution is.

    **The mutations this kills**: reading the posted value as UTC, which is the
    shortest thing that runs and puts the stack four or five hours from where the
    developer aimed it — enough to be on the wrong side of a window boundary and
    never enough to look obviously wrong; and reading it in the *server's* local
    zone, which is UTC in every container this project ships and therefore
    indistinguishable from the first mutation until somebody runs it on a laptop.

    **Two zones, because one cannot tell a correct handler from a hardcoded one.**
    The same posted wall time is two instants fourteen hours and one minute apart
    in Kiritimati (UTC+14) and Niue (UTC-11), and the expectation is computed from
    the zone this case configured. Neither zone observes daylight saving, so the
    offsets are the whole of the arithmetic and no tzdata edition can move them.

    ADR 0019 is the other half of the sentence: the stored value must be aware, or
    the column refuses it at bind. That is asserted here rather than assumed,
    because a handler that stored a naive value would raise inside the POST and the
    test would fail on the redirect instead of saying what was wrong.
    """
    client = dev_console(**{INSTITUTION_TIMEZONE_VARIABLE: zone})

    posted = client.post(DEV_CLOCK_SET_PATH, data={PRETEND_NOW_FIELD: POSTED_PRETEND_NOW})
    redirected_to_the_console(posted, f"`POST {DEV_CLOCK_SET_PATH}` with the zone {zone}")

    written = committed_clock_overrides.rows()
    assert (
        len(written) == 1
    ), f"`POST {DEV_CLOCK_SET_PATH}` left {len(written)} rows in `clock_override`: {written}."
    stored = written[0][PRETEND_NOW_COLUMN]
    assert stored.utcoffset() is not None, (
        f"The stored `{PRETEND_NOW_COLUMN}` is {stored!r}, which carries no offset. ADR 0019's "
        "`AwareDateTime` refuses a naive datetime at bind precisely so that a wall time with no "
        "zone cannot become a row; the handler converts to aware before storage."
    )

    expected = datetime.fromisoformat(POSTED_PRETEND_NOW).replace(tzinfo=ZoneInfo(zone))
    as_utc = datetime.fromisoformat(POSTED_PRETEND_NOW).replace(tzinfo=UTC)
    assert expected != as_utc, (
        f"Reading {POSTED_PRETEND_NOW!r} in {zone} and reading it in UTC name the same instant, so "
        "this case cannot tell the two apart. Both candidate zones are offset from UTC by hours."
    )
    assert stored == expected, (
        f"`POST {DEV_CLOCK_SET_PATH}` stored {stored!r} for the posted wall time "
        f"{POSTED_PRETEND_NOW!r} with `{INSTITUTION_TIMEZONE_VARIABLE}` set to {zone!r}; that wall "
        f"time in that zone is {expected!r}, and read as UTC it would be {as_utc!r}. A "
        "`datetime-local` value carries no offset, and SPEC §3.1 makes the institution's zone the "
        "one that supplies it."
    )
