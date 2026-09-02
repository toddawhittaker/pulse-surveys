"""The developer test console: the development-only `GET /dev` page.

The console is a convenience for a developer, and nothing a deployment serves. It
lists the web-login people the mock identity provider knows and offers each as a
one-click "sign in as this person" link, plus one launcher link per registered
LTI platform, so both of SPEC §2's entry doors can be walked without typing URLs.
Below those it reports the sections a launch has discovered so far.

**The launcher links come from `lti_platform`** (E1-05). They used to come from
the origin of a process-wide setting, which rendered one link whatever the
database held — including when it held no registration at all, which sent a
developer to a port answering nothing. With nothing registered the page now says
so and how to fix it.

**It is a become-any-user surface, so it is gated exactly the way `/docs` is** —
served only when `ENVIRONMENT` is exactly `development` (ADR 0074), the same value
`app.main` keys the schema and its documentation on. Outside development the
handler answers `404`, indistinguishable from a route that was never registered:
a page enumerating every identity anyone can sign in as is the single worst thing
this feature could hand a production browser. The production refusal is asserted
without a network in `tests/unit/test_dev_console_exposure.py`; the
development-serves direction, with a real roster behind it, in
`tests/integration/test_dev_console.py`.

**A new module, and §13 does not name it** — its `api/` list is the screen
routers plus `deps.py`, and a developer test console is neither a screen nor LTI.
It is a thin router here, and the page it builds lives beside it: a handful of
f-strings, the way `mock-idp/app/pages.py` builds its three pages, because no
template engine is in this project's locked dependency closure.

**The sections table reports sections and never the people in them** (E1-15).
E1 ships no product screen that renders a section's derived calendar, and SPEC
§9.2's exit proof for "a synced section shows correct derived dates" is a browser
proof, so the console grew one row per `section`: the dates and length §2.2's
start letter derives, the modality, how many people are enrolled, whether a
roster address is stored, and — since E2-06 — whether that section's survey window
is open at the effective clock and until when (§3.1). **No identity column of any
kind** — not a subject, not
a name, not an address, and not the stored roster address itself, which is a
service endpoint carrying the platform's own context identifier. The enrolled
figure is a count and comes from `public.section_enrollment_count`, the view §4.1
invariant 4 puts every count behind. `tests/integration/
test_the_dev_console_names_nobody.py` is the durable assertion of that rule, over
a section a roster sync has really filled.

**It grows a clock control in E2-04**, and that is the one thing here that writes
anything. SPEC §3.1 makes every survey window a wall-clock time in the institution's
timezone, and E2 has to be drivable by hand, so the console shows the effective
clock and offers two `POST` routes — `/dev/clock` sets a pretend now and
`/dev/clock/clear` gives the real one back. Both carry the same in-handler gate this
page does, and both are stricter about the method probe: **every** method they do
not serve answers `404` here rather than the `405 Allow:` the console itself
discloses (ADR 0079, ADR 0087), because the row they write moves the clock every
scheduling and visibility read in the product goes through. "Every" is enforced by
matching the path for any method at all and refusing in the handler — see
`AnyMethodRoute` below, and the security round of 2026-09-01 that put it there
after a closed list of verbs let `TRACE` reach the router's `405`.
`app.services.clock` is what applies the row, and only where `is_development`; ADR
0109 carries the design and the list of clocks it deliberately does not touch.

**Every interpolated value goes through `html.escape` with `quote=True`.** The
subjects and labels come from the mock provider's roster, which is trusted, but
they are escaped anyway — a page that escapes only the values it distrusts is one
audit away from a hole. Nothing a caller or a roster supplies is ever written into
the `<style>` block, which carries no interpolation at all.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html import escape
from typing import Any
from urllib.parse import parse_qs, urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, insert, select, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.routing import Route

from app.api.auth import LOGIN_PATH
from app.config import Settings, is_development
from app.db import SessionLocal, get_session
from app.lti.registration import launcher_origins
from app.models.clock import ClockOverride
from app.models.org import Course, Prefix, Section
from app.services import clock
from app.services.survey_windows import open_windows_now

router = APIRouter(tags=["dev"])

DEV_CONSOLE_PATH = "/dev"

# E2-04's clock control: the two routes the section below posts to.
DEV_CLOCK_SET_PATH = "/dev/clock"
DEV_CLOCK_CLEAR_PATH = "/dev/clock/clear"

# Where the console reads the roster from. The mock provider publishes its
# registration and its seed together (ADR 0058) under this path on the issuer's
# host, and the fetch goes through `app.state.http` — the one client every
# server-side call the tool makes already shares.
MOCK_REGISTRATION_PATH = "/mock/registration"

# How long the console waits for the roster. The page is a development
# convenience, so a slow mock should make it say so rather than hang.
ROSTER_TIMEOUT_SECONDS = 5.0

NOT_FOUND = 404
BAD_REQUEST = 400

# The answer both clock controls give on success: 303, so the browser follows with
# a GET and a reload does not re-post the form.
SEE_OTHER = 303

# The one method either clock route serves. Every other method — standard, or a
# token nobody has thought of — is refused by the handler and not by the router,
# which is what `AnyMethodRoute` below exists to arrange. That is a stricter gate
# than the console's own measured `405` (ADR 0079, ADR 0087, and
# `tests/unit/test_dev_console_exposure.py` pins it there), deliberately: a page is
# a thing to read and a control is a thing to attack.
POST_METHOD = "POST"

CONSOLE_TITLE = "Pulse Surveys — developer test console"

# The sections table's `data-testid` vocabulary, spelled once. E1-15's browser
# specs address these and nothing else on the table, so a rename is one edit here
# and one in `tests/e2e/`.
#
# A row is keyed by what a person writes on a timetable — `dev-section-BIOL-215-R3WW`
# — rather than by the section's primary key, because a `uuid` is regenerated by
# every reseed and a spec cannot name one. Two sections could in principle share
# a prefix, a number and a code across two terms, and would then share a row key;
# the development stack seeds one term, and the alternative — hanging a term on
# the key — would make every spec spell a term it has nothing to say about.
SECTION_ROW_TESTID_PREFIX = "dev-section-"
SECTION_START_DATE_TESTID = "section-start-date"
SECTION_END_DATE_TESTID = "section-end-date"
SECTION_LENGTH_WEEKS_TESTID = "section-length-weeks"
SECTION_MODALITY_TESTID = "section-modality"
SECTION_ENROLLED_COUNT_TESTID = "section-enrolled-count"
SECTION_ROSTER_ADDRESS_TESTID = "section-roster-address-stored"
# E2-06's column: whether this section's survey window is open at the effective
# clock, and until when. `tests/e2e/window-scheduling.spec.ts` reads it.
SECTION_OPEN_WINDOW_TESTID = "section-open-window"

# The clock section's `data-testid` vocabulary (E2-04). Spelled once here, and in
# `tests/e2e/dev-clock.spec.ts` and the two Python suites that drive these routes;
# a rename is those four places.
CLOCK_EFFECTIVE_NOW_TESTID = "clock-effective-now"
CLOCK_OVERRIDE_STATE_TESTID = "clock-override-state"
CLOCK_PRETEND_NOW_TESTID = "clock-pretend-now"
CLOCK_SET_TESTID = "clock-set"
CLOCK_CLEAR_TESTID = "clock-clear"

# The form field `POST /dev/clock` reads: an HTML `datetime-local` value — a wall
# time with no offset, minute precision — read in the institution's timezone.
PRETEND_NOW_FIELD = "pretend_now"

# How the page writes an instant, and how the field is pre-filled. ISO 8601 in the
# institution's own timezone, offset included: SPEC §3.1 makes that zone the one
# every window is expressed in, so it is the zone a developer is thinking in, and
# the offset is what stops the reading being ambiguous on a page that also shows
# dates. Seconds are shown because the whole point of the section is that an
# overridden clock is still running.
PRETEND_NOW_INPUT_FORMAT = "%Y-%m-%dT%H:%M"

# What the state readout says. Two constants, because its whole job is to tell the
# two states apart at a glance — and because a browser spec compares the cleared
# reading against the one it took before it set anything.
NO_OVERRIDE_STATE = "The clock is real: no override is set."

# What the roster-address cell says. A yes or a no on
# `lms_context_memberships_url IS NOT NULL` (SPEC §7.3's never-synced state), and
# never the address: it carries the platform's own context identifier and is the
# target of a credentialled service call.
ADDRESS_STORED = "yes"
ADDRESS_NOT_STORED = "no"

# What the open-window cell says (E2-06). A section spends five days of every week
# with no open survey, so `closed` is the ordinary reading rather than an error
# state; the open reading carries the instant the window closes at, because "open"
# on its own cannot be told from a cell that says "open" whatever the clock is.
NO_OPEN_WINDOW = "closed"
OPEN_WINDOW_PREFIX = "open until"

# How many people each section holds, read from the view rather than counted off
# `public.enrollment`. SPEC §4.1 invariant 4 — "aggregate language counts
# sections, never instructors" — puts every count behind
# `public.section_enrollment_count`, whose own SQL says why: a count is the shape
# most likely to be extended with "…and their names", and this is the read path
# that cannot be.
#
# Spelled here rather than reached through `app.views_sql.queries`, which
# `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` keeps to the
# single importer that is the authorization chokepoint — this console asks a
# question with no actor and no purview in it, and importing that module would
# turn a one-importer rule into a two-importer one. Its helper takes a course in
# any case; the console lists every section there is.
_SECTION_ENROLLED_COUNTS = text(
    "SELECT section_id, enrolled_count FROM public.section_enrollment_count"
)


@dataclass(frozen=True, slots=True)
class ConsoleSection:
    """One row of the sections table: a section's calendar, a count, a yes/no, a window.

    Nothing on it names a person. The count is an integer and the roster address
    is reduced to whether there is one before it ever leaves the database.

    `open_window_closes_at` is E2-06's addition: the instant this section's open
    survey window closes at, already in the institution's timezone, or `None` when
    no window of the section is open at the effective clock.
    """

    prefix: str
    number: str
    code: str
    start_date: date
    end_date: date
    length_weeks: int
    modality: str
    enrolled_count: int
    roster_address_stored: bool
    open_window_closes_at: datetime | None

    @property
    def testid(self) -> str:
        """`dev-section-BIOL-215-R3WW` — the row key the browser specs address."""
        return f"{SECTION_ROW_TESTID_PREFIX}{self.prefix}-{self.number}-{self.code}"

    @property
    def open_window(self) -> str:
        """`closed`, or `open until` the instant the open window closes at (E2-06).

        The instant is written the way the clock section above writes one — ISO
        8601 in the institution's timezone, offset included, to the second — so
        the two readings on this page are in the same zone and comparable by eye,
        and so the daylight-saving offset a window closes on is visible rather
        than implied.
        """
        if self.open_window_closes_at is None:
            return NO_OPEN_WINDOW
        return f"{OPEN_WINDOW_PREFIX} {self.open_window_closes_at.isoformat(timespec='seconds')}"

    @property
    def label(self) -> str:
        """The section as a person writes it (SPEC §2.2, §8)."""
        return f"{self.prefix} {self.number} {self.code}"


# Static CSS, no interpolation: this is code, never a value a caller or a roster
# supplied, so it does not go through `escape` and nothing from a request is ever
# written into it. A cool teal accent, distinct from the mock IdP's violet and the
# mock platform's slate, so the three test surfaces are never mistaken for one
# another, and from Pulse's own palette (`design/tokens.css` is deliberately not
# referenced — this is a developer scaffold, not a product screen).
STYLE = """
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      padding: 2.5rem 1rem;
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      background: #f0faf9;
      color: #18181b;
    }
    .card {
      width: 100%;
      max-width: 640px;
      background: #ffffff;
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 8px 24px rgba(0, 0, 0, 0.06);
      padding: 2rem 2.25rem 2.25rem;
      height: fit-content;
    }
    h1 { font-size: 1.375rem; margin: 0 0 0.5rem; color: #0f766e; }
    h2 {
      font-size: 1rem;
      margin: 2rem 0 0.75rem;
      color: #0f766e;
      border-top: 1px solid #e5e7eb;
      padding-top: 1.25rem;
    }
    p { line-height: 1.5; color: #3f3f46; margin: 0.5rem 0 1rem; }
    .banner {
      display: flex;
      gap: 0.6rem;
      align-items: flex-start;
      background: #fff7ed;
      border: 1px solid #fdba74;
      color: #9a3412;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.875rem;
      line-height: 1.4;
      margin-bottom: 1.5rem;
    }
    .banner strong { font-weight: 600; }
    .note {
      background: #fef2f2;
      border: 1px solid #fca5a5;
      color: #991b1b;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.875rem;
      line-height: 1.4;
    }
    ul { list-style: none; margin: 0; padding: 0; }
    li { margin: 0.4rem 0; }
    a.action {
      display: inline-block;
      color: #0f766e;
      font-weight: 600;
      text-decoration: none;
      padding: 0.15rem 0;
    }
    a.action:hover { text-decoration: underline; }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.85em;
      background: rgba(0, 0, 0, 0.05);
      padding: 0.1em 0.35em;
      border-radius: 4px;
      color: #52525b;
    }
    form.clock { display: inline-flex; gap: 0.5rem; margin: 0 0.75rem 0.5rem 0; }
    form.clock input, form.clock button {
      font: inherit;
      padding: 0.35rem 0.6rem;
      border-radius: 6px;
      border: 1px solid #d4d4d8;
      background: #ffffff;
      color: inherit;
    }
    form.clock button { border-color: #0f766e; color: #0f766e; font-weight: 600; cursor: pointer; }
    .scroller { overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; font-size: 0.8125rem; }
    th, td { text-align: left; padding: 0.35rem 0.6rem; white-space: nowrap; }
    thead th { color: #52525b; border-bottom: 1px solid #e5e7eb; font-weight: 600; }
    tbody th { font-weight: 600; }
    tbody tr + tr th, tbody tr + tr td { border-top: 1px solid #f4f4f5; }
    @media (prefers-color-scheme: dark) {
      body { background: #0c1a19; color: #e4e4e7; }
      .card { background: #18181b; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4); }
      h1, h2 { color: #5eead4; }
      h2 { border-top-color: #3f3f46; }
      p { color: #a1a1aa; }
      a.action { color: #5eead4; }
      code { background: rgba(255, 255, 255, 0.08); color: #a1a1aa; }
      .banner { background: #451a03; border-color: #c2410c; color: #fed7aa; }
      .note { background: #450a0a; border-color: #b91c1c; color: #fecaca; }
      form.clock input, form.clock button { background: #27272a; border-color: #3f3f46; }
      form.clock button { border-color: #5eead4; color: #5eead4; }
      thead th { color: #a1a1aa; border-bottom-color: #3f3f46; }
      tbody tr + tr th, tbody tr + tr td { border-top-color: #27272a; }
    }
"""

# Static banner markup, no interpolation.
BANNER = """
    <div class="banner">
      <span>&#9888;&#65039;</span>
      <span>
        <strong>Development-only test console.</strong>
        It offers one-click sign-in as any web-login identity and a launch into the
        mock LMS. It is served only in development and never in a deployment.
      </span>
    </div>"""


def page(body: str) -> str:
    """The shell the console renders inside, so its markup has one shape."""
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{escape(CONSOLE_TITLE)}</title>
    <style>{STYLE}</style>
  </head>
  <body>
    <div class="card">
      {BANNER}
{body}
    </div>
  </body>
</html>
"""


def sign_in_link(subject: str, label: str) -> str:
    """A "sign in as this person" link to the web door, carrying `login_hint`.

    The subject rides as OIDC Core 1.0 §3.1.2.1's `login_hint`, which the tool
    forwards to the provider so its form pre-selects this person. `target="_blank"`
    so a click opens the flow in a new tab and the console stays put — a developer
    signs in, then comes back to pick the next identity.
    """
    href = f"{LOGIN_PATH}?{urlencode({'login_hint': subject})}"
    return (
        f'<li><a class="action" href="{escape(href, quote=True)}" target="_blank">'
        f"Sign in as {escape(label)}</a> "
        f"<code>{escape(subject)}</code></li>"
    )


def web_section(users: list[dict[str, Any]]) -> str:
    """The web-login roster, one sign-in link per person the provider publishes."""
    people = [user for user in users if user.get("web_login") and user.get("sub")]
    links = "\n          ".join(
        sign_in_link(str(user["sub"]), str(user.get("label") or user["sub"])) for user in people
    )
    return f"""    <h2>Web login</h2>
    <p>Sign in through the identity provider (SPEC §2) as any seeded person.</p>
    <ul>
          {links}
    </ul>"""


def unreachable_section() -> str:
    """What the web section becomes when the roster cannot be fetched."""
    return """    <h2>Web login</h2>
    <p class="note">
      The mock identity provider is unreachable, so the web-login roster could not
      be loaded. Bring it up and reload this page.
    </p>"""


def launcher_section(origins: list[str]) -> str:
    """One launcher link per registered platform origin, or an honest line saying none is.

    **The empty case is a case, not a blank space.** While the origin came from a
    process-wide setting there was always a link, including on a database that
    had never been seeded — which sent a developer to a port answering nothing
    and read as a broken stack. The console reads the registrations now, so the
    absence is visible, and the honest answer to it names what is missing and how
    to fix it.
    """
    if not origins:
        return """    <h2>LTI launch</h2>
    <p class="note">
      No LTI platform is registered, so there is nothing to launch from. Run
      <code>make seed</code> to register the mock LMS, then reload this page.
    </p>"""
    links = "\n          ".join(
        f'<li><a class="action" href="{escape(origin, quote=True)}" target="_blank">'
        f"Open the launcher at {escape(origin)}</a></li>"
        for origin in origins
    )
    return f"""    <h2>LTI launch</h2>
    <p>Launch as an instructor or a student from a registered platform (SPEC §2).</p>
    <ul>
          {links}
    </ul>"""


def roster_users(settings: Settings, http: httpx.Client) -> list[dict[str, Any]] | None:
    """The provider's published users, or `None` when the roster cannot be fetched.

    `None` is the console's fail-soft signal, not a raised error: a page that says
    "the mock is down" is better than one that answers `500` because a development
    dependency is not running. Every failure to obtain a well-formed list of user
    records collapses to it.
    """
    url = f"{settings.oidc_issuer.rstrip('/')}{MOCK_REGISTRATION_PATH}"
    try:
        answered = http.get(url, timeout=ROSTER_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        return None
    if answered.status_code != 200:
        return None
    try:
        document = answered.json()
    except ValueError:
        return None
    if not isinstance(document, dict):
        return None
    users = document.get("users")
    if not isinstance(users, list):
        return None
    return [user for user in users if isinstance(user, dict)]


def console_sections(session: Session, settings: Settings) -> list[ConsoleSection]:
    """Every section, with its derived calendar, how many people are in it, and its window.

    Three statements rather than one join, because the count comes from a view, the
    calendar comes from the base tables and the open window comes from a service,
    and joining a view into an ORM select would mean spelling the view's column
    list twice. The count defaults to zero for a section the view has no row for,
    which cannot happen — it is a `LEFT JOIN` over `section` — and is written
    anyway so that a section is never dropped from the page by a missing count.

    **The open window is asked for the whole page at once**, through
    `app.services.survey_windows.open_windows_now`, which reads the effective clock
    once and answers by section id. Per section it would mean handing that service
    a `Section` row, and the select below deliberately never loads one — the roster
    address is reduced to a boolean in the database so it is not selected onto this
    page's connection at all (ADR 0100).

    Ordered the way a person reads a timetable, so the table is stable between
    reloads and a spec polling it sees the same row in the same place.
    """
    counted: dict[UUID, int] = {
        row.section_id: row.enrolled_count for row in session.execute(_SECTION_ENROLLED_COUNTS)
    }
    zone = ZoneInfo(settings.institution_timezone)
    open_windows = open_windows_now(session, settings=settings)
    rows = session.execute(
        select(
            Section.id,
            Prefix.code,
            Course.lms_number,
            Section.lms_section_code,
            Section.start_date,
            Section.end_date,
            Section.length_weeks,
            Section.modality,
            # Reduced to a boolean **in the database**, so the address itself is
            # never selected onto this page's connection at all.
            Section.lms_context_memberships_url.is_not(None),
        )
        .join(Course, Course.id == Section.course_id)
        .join(Prefix, Prefix.id == Course.prefix_id)
        .order_by(Prefix.code, Course.lms_number, Section.lms_section_code)
    )
    return [
        ConsoleSection(
            prefix=prefix,
            number=number,
            code=code,
            start_date=start_date,
            end_date=end_date,
            length_weeks=length_weeks,
            # The member's name — `ONLINE`, `FACE_TO_FACE` — which is also its
            # value (`app.models.org.Modality`), so the page and the column say
            # the same word.
            modality=modality.name,
            enrolled_count=counted.get(section_id, 0),
            roster_address_stored=stored,
            open_window_closes_at=(
                None
                if section_id not in open_windows
                else open_windows[section_id].closes_at.astimezone(zone)
            ),
        )
        for (
            section_id,
            prefix,
            number,
            code,
            start_date,
            end_date,
            length_weeks,
            modality,
            stored,
        ) in rows
    ]


def section_row(section: ConsoleSection) -> str:
    """One `<tr>`: the section, its calendar, its count and whether it can be synced."""

    def cell(testid: str, value: str) -> str:
        return f'<td data-testid="{escape(testid, quote=True)}">{escape(value)}</td>'

    return (
        f'<tr data-testid="{escape(section.testid, quote=True)}">'
        f'<th scope="row">{escape(section.label)}</th>'
        f"{cell(SECTION_START_DATE_TESTID, section.start_date.isoformat())}"
        f"{cell(SECTION_END_DATE_TESTID, section.end_date.isoformat())}"
        f"{cell(SECTION_LENGTH_WEEKS_TESTID, str(section.length_weeks))}"
        f"{cell(SECTION_MODALITY_TESTID, section.modality)}"
        f"{cell(SECTION_ENROLLED_COUNT_TESTID, str(section.enrolled_count))}"
        f"{cell(
            SECTION_ROSTER_ADDRESS_TESTID,
            ADDRESS_STORED if section.roster_address_stored else ADDRESS_NOT_STORED,
        )}"
        f"{cell(SECTION_OPEN_WINDOW_TESTID, section.open_window)}"
        "</tr>"
    )


def sections_section(sections: list[ConsoleSection]) -> str:
    """The sections table, or an honest line saying nothing has been discovered yet.

    **The empty case is a case**, for the reason `launcher_section` gives about
    its own: a blank space reads as a broken page, and "no section exists yet" is
    a state SPEC §7.3 makes ordinary — a section is discovered by a staff launch
    and by nothing else, so a freshly migrated database has none.
    """
    if not sections:
        return """    <h2>Sections</h2>
    <p class="note">
      No section has been discovered yet. A section is created by a staff launch
      (SPEC §7.3), so launch as an instructor from the mock LMS and reload this
      page.
    </p>"""
    rows = "\n          ".join(section_row(section) for section in sections)
    return f"""    <h2>Sections</h2>
    <p>
      What each section's code derives to (SPEC §2.2), how many people the last
      roster sync enrolled, whether a roster address is stored to sync from
      (SPEC §7.3), and whether this week's survey window is open at the clock
      above (SPEC §3.1). Sections only — never the people in them.
    </p>
    <div class="scroller">
    <table>
      <thead>
        <tr>
          <th scope="col">Section</th>
          <th scope="col">Starts</th>
          <th scope="col">Ends</th>
          <th scope="col">Weeks</th>
          <th scope="col">Modality</th>
          <th scope="col">Enrolled</th>
          <th scope="col">Roster address</th>
          <th scope="col">Survey window</th>
        </tr>
      </thead>
      <tbody>
          {rows}
      </tbody>
    </table>
    </div>"""


def standing_override(session: Session) -> ClockOverride | None:
    """The `clock_override` row, or `None` if the clock is real.

    **Read here rather than through `app.services.clock`**, which answers what time
    it is and not whether somebody moved it. Those are two questions, and the second
    is this page's alone: the console exists to say that an overridden stack is not
    a live one, and no other reader in the product has any business asking. Adding a
    third function to the service for one page's readout would put a question with
    one caller in the module every scheduling read goes through.

    A direct read of a model in a router, which is what the sections table above
    already does for `section`, `course` and `prefix`. `clock_override` holds two
    timestamps and no person, so no view stands over it and none of SPEC §4.1's
    read-path rules reach it.
    """
    return session.scalars(select(ClockOverride)).first()


def clock_section(session: Session, settings: Settings) -> str:
    """The effective clock, whether an override stands, and the two controls (E2-04).

    **Beside the sections table on purpose.** That table shows derived dates, and a
    stack whose clock has been moved shows them against a day that is not today; the
    ticket's scope says to "show the effective clock beside it so an overridden stack
    is never mistaken for a live one".

    **Rendered in the institution's timezone, with the offset** — ISO 8601, e.g.
    `2026-09-04T18:30:00-04:00`. SPEC §3.1 puts every window at a wall-clock time in
    that zone, so it is the zone a developer setting one is thinking in, and the
    offset is what keeps the reading unambiguous beside a table of dates. Seconds
    are shown because the override is an offset and not a freeze: the point is
    visible only if the clock is seen running.

    **The field is pre-filled with the effective now** so that moving the clock by
    an hour is an edit rather than a full datetime typed from nothing. Minute
    precision, which is what an `<input type="datetime-local">` carries.
    """
    zone = ZoneInfo(settings.institution_timezone)
    effective = clock.now(session, settings=settings).astimezone(zone)
    override = standing_override(session)
    if override is None:
        state = NO_OVERRIDE_STATE
    else:
        state = (
            "An override is in force: set to "
            f"{override.pretend_now.astimezone(zone).isoformat(timespec='seconds')}, anchored at "
            f"{override.anchored_at.astimezone(zone).isoformat(timespec='seconds')}."
        )
    return f"""    <h2>Clock</h2>
    <p>
      What this stack thinks the time is (SPEC §3.1, in {escape(settings.institution_timezone)}).
      Setting a pretend now moves the clock for the tool and the worker alike, and it
      keeps running from there — an offset, never a freeze.
    </p>
    <p>Effective now:
      <code data-testid="{escape(CLOCK_EFFECTIVE_NOW_TESTID, quote=True)}"
        >{escape(effective.isoformat(timespec="seconds"))}</code></p>
    <p data-testid="{escape(CLOCK_OVERRIDE_STATE_TESTID, quote=True)}"
      >{escape(state)}</p>
    <form class="clock" method="post" action="{escape(DEV_CLOCK_SET_PATH, quote=True)}">
      <input
        data-testid="{escape(CLOCK_PRETEND_NOW_TESTID, quote=True)}"
        type="datetime-local"
        name="{escape(PRETEND_NOW_FIELD, quote=True)}"
        value="{escape(effective.strftime(PRETEND_NOW_INPUT_FORMAT), quote=True)}"
        required>
      <button data-testid="{escape(CLOCK_SET_TESTID, quote=True)}" type="submit"
        >Set the pretend now</button>
    </form>
    <form class="clock" method="post" action="{escape(DEV_CLOCK_CLEAR_PATH, quote=True)}">
      <button data-testid="{escape(CLOCK_CLEAR_TESTID, quote=True)}" type="submit"
        >Clear the override</button>
    </form>"""


@router.get(DEV_CONSOLE_PATH, summary="Development-only test console for both entry doors")
def dev_console(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    """Render the console, or `404` outside development.

    The gate is the whole safety of the feature (see the module docstring), and it
    is checked here so production is indistinguishable from a route that was never
    registered. Synchronous, and the blocking things it does — the roster fetch
    over the network, and two reads for the sections table — run in FastAPI's
    threadpool the way `app.api.auth.begin_web_login` does.

    **The session is taken before the gate rather than after**, because
    `Depends` resolves before the handler body runs either way. It costs a
    connection from the pool on a request a deployment answers `404` to, which is
    the same cost every other routed dependency has and is why the gate stays in
    the handler (ADR 0079) rather than moving anywhere clever.
    """
    settings: Settings = request.app.state.settings
    if not is_development(settings):
        raise HTTPException(status_code=NOT_FOUND)

    users = roster_users(settings, request.app.state.http)
    web = unreachable_section() if users is None else web_section(users)
    body = f"""    <h1>{escape(CONSOLE_TITLE)}</h1>
    <p>Walk either of Pulse's two entry doors (SPEC §2) without typing URLs.</p>
{web}
{launcher_section(launcher_origins(session))}
{clock_section(session, settings)}
{sections_section(console_sections(session, settings))}"""
    return HTMLResponse(page(body))


class AnyMethodRoute(Route):
    """A route that matches its path whatever method the request carries.

    **The security round of 2026-09-01 is why this class exists.** The two clock
    controls were registered as a `POST` plus a second registration naming the six
    other standard verbs, and a review drove a method outside that list. Starlette
    matches a route by path and then by method: a path it knows and a method no
    registration names is a *partial* match, and a partial match with no full one
    anywhere answers `405 Allow: POST` from the router, before any handler runs. So
    `TRACE` — a real method from RFC 9110 — and any arbitrary token got the router's
    answer, and the environment check never had a say. On a deployment that is one
    unauthenticated request telling a caller both that this build carries a clock
    control and that `ENVIRONMENT` is not `development`.

    Adding the missing tokens to the list is not the fix; the next token nobody
    thought of reopens it (`docs/MISTAKES.md` entry 35 — a guard that enumerates the
    forms a thing can take misses the form nobody listed). **The fix is to stop
    enumerating**: match the path for every method and let the handler decide, so
    what answers a method probe is the same 404 the environment check gives.

    `Route.matches` treats `self.methods` of `None` as no restriction at all — a
    full match for every method — but `Route.__init__` cannot be asked for that
    directly: given a function endpoint it reads `methods=None` as "the default",
    which is `["GET"]`. So the route is built naming the one method it really serves
    and the restriction is cleared in the line below, which is the whole of this
    class.

    A plain `starlette.routing.Route` rather than a FastAPI `APIRoute`, because
    `APIRouter.api_route` requires a method list and every route class FastAPI
    builds carries one. It costs the two paths their entry in the OpenAPI schema —
    `get_openapi` walks `APIRoute` instances only — which is no loss: `/docs` is
    served in development alone (ADR 0074) and the controls are two buttons on the
    page beside it, not an API anybody writes a client against. It also costs
    `Depends`, so the two handlers open their own session the way `app.main`'s
    framing middleware does.
    """

    def __init__(self, path: str, endpoint: Callable[..., Any]) -> None:
        super().__init__(path, endpoint, methods=[POST_METHOD], include_in_schema=False)
        # Not `methods=None` above: for a function endpoint that means "the
        # default", and the default is GET. Cleared here, where `matches` reads it.
        self.methods = None


async def set_the_dev_clock(request: Request) -> Response:
    """Replace the override row with the posted instant, or `404`.

    `404` in two cases, and they are one answer on purpose: outside development, and
    to any method that is not `POST`. A caller cannot tell which of those refused
    them, which is the point — see `AnyMethodRoute` above.

    The gate is the same in-handler comparison the console carries, for the same
    reason and one step more urgently: the row this writes moves the clock that
    decides which survey window is open, which term a launch lands in and which
    enrollments are live, and the console has no session and no CSRF token to put in
    front of it. Outside development this route does not exist, to any method.

    **The posted value is a wall time and the institution's zone is what supplies
    the offset.** An `<input type="datetime-local">` sends `2031-03-14T10:30` and
    nothing about a zone; SPEC §3.1 makes the institution's the zone every window is
    expressed in, so a developer typing `18:30` to reach a Friday evening means
    18:30 where the institution is. Reading it as UTC would put the stack four or
    five hours from where they aimed it — enough to be on the wrong side of a
    boundary and never enough to look obviously wrong.

    **The anchor is the real instant this ran at**, and it is what makes the
    override an offset rather than a freeze: `app.services.clock` adds the elapsed
    real time to the pretended instant on every read. Storing the pretended instant
    in both columns would give a clock running at the right rate from the wrong
    origin, which no single reading can tell from a correct one.

    **Asynchronous, because the body is read with `await`, and parsed by hand.**
    Both of FastAPI's routes to a form field — a `Form()` parameter and
    `request.form()` — need `python-multipart`, which is not in this project's
    locked dependency closure; a development scaffold is no reason to add one, and
    the body a browser sends here is `application/x-www-form-urlencoded`, which
    `urllib.parse.parse_qs` reads in a line. The blocking database work then goes to
    the threadpool, the way `app.main`'s framing middleware does its own.
    """
    settings: Settings = request.app.state.settings
    if not is_development(settings) or request.method != POST_METHOD:
        raise HTTPException(status_code=NOT_FOUND)

    posted = posted_field(await request.body(), PRETEND_NOW_FIELD)
    if not posted:
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail=(
                f"This control reads a `{PRETEND_NOW_FIELD}` field carrying an HTML "
                "`datetime-local` value, e.g. `2031-03-14T10:30`."
            ),
        )
    pretend_now = pretend_instant(posted, settings)
    await run_in_threadpool(replace_the_override, pretend_now)
    return RedirectResponse(DEV_CONSOLE_PATH, status_code=SEE_OTHER)


def clear_the_dev_clock(request: Request) -> Response:
    """Delete the override row, or `404`.

    The same two refusals as the setter above and in the same order — not
    development, or not `POST` — answered identically so a probe learns nothing.

    Deleting the row rather than writing a zero offset: a row holding a zero offset
    answers the same instants today and is a state nothing else in this product
    knows how to read.

    Synchronous, and that is enough: it reads no body, and Starlette runs a
    non-async endpoint in a worker thread, so the statement below is off the event
    loop without this function saying anything about threads.
    """
    settings: Settings = request.app.state.settings
    if not is_development(settings) or request.method != POST_METHOD:
        raise HTTPException(status_code=NOT_FOUND)

    with SessionLocal() as session:
        session.execute(delete(ClockOverride))
        session.commit()
    return RedirectResponse(DEV_CONSOLE_PATH, status_code=SEE_OTHER)


# The two controls, each matching its path for every method. Appended rather than
# decorated because `APIRouter.api_route` requires a method list, which is the thing
# that has to go — see `AnyMethodRoute`. One route per path, so there is no ordering
# between a route that serves `POST` and a route that refuses everything else, and
# no way to reintroduce the router's `405` by moving one of them.
router.routes.append(AnyMethodRoute(DEV_CLOCK_SET_PATH, set_the_dev_clock))
router.routes.append(AnyMethodRoute(DEV_CLOCK_CLEAR_PATH, clear_the_dev_clock))


def posted_field(body: bytes, name: str) -> str | None:
    """One field out of an `application/x-www-form-urlencoded` body, or `None`.

    The whole of this project's form parsing, and it is four lines because a
    `<form method="post">` with text inputs sends exactly that encoding.
    `python-multipart` — which both of FastAPI's form seams require — is not in the
    locked dependency closure, and this page is not the reason to widen it.

    Undecodable bytes are replaced rather than raised on: what follows judges the
    value and answers `400` about it, and a caller who sent something that is not a
    form should meet that answer rather than a 500 from the decoder. `parse_qs`
    drops a blank value, so an empty field arrives here as `None` and is refused by
    the caller like a missing one.
    """
    fields = parse_qs(body.decode("utf-8", errors="replace"))
    values = fields.get(name)
    return values[0] if values else None


def pretend_instant(posted: str, settings: Settings) -> datetime:
    """The posted wall time as an instant in the institution's timezone.

    `datetime.fromisoformat` reads what a browser sends for `datetime-local`
    (`2031-03-14T10:30`, and the seconds-bearing form some browsers send). A value
    that already carries an offset is refused rather than reinterpreted: no
    `datetime-local` control produces one, so it means the caller is not the form,
    and silently replacing an offset somebody stated would move the clock somewhere
    they did not ask for.
    """
    try:
        wall = datetime.fromisoformat(posted)
    except ValueError:
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail=(
                f"`{posted}` is not an HTML `datetime-local` value. This control reads a wall "
                "time such as `2031-03-14T10:30`, in the institution's timezone."
            ),
        ) from None
    if wall.utcoffset() is not None:
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail=(
                f"`{posted}` carries a UTC offset. An HTML `datetime-local` value is a wall time "
                "with none, and this control reads it in the institution's timezone (SPEC §3.1)."
            ),
        )
    return wall.replace(tzinfo=ZoneInfo(settings.institution_timezone))


def replace_the_override(pretend_now: datetime) -> None:
    """Make this the single override row, anchored at the real instant now.

    Delete then insert, rather than an upsert: the table holds at most one row by a
    unique index over `(true)`, so a second insert would be refused by that index
    rather than replacing anything. Both statements and the commit are one
    transaction, so a stack is never briefly running on a clock nobody set.

    **It opens its own session.** The route it serves is a plain
    `starlette.routing.Route` (see `AnyMethodRoute`), which has no `Depends`, so
    there is no request-scoped session to be handed — the same position
    `app.main.framing_ancestors` is in, and the same answer. The `with` block is
    what makes the closing unconditional, which is the whole of what
    `app.db.get_session` does for a routed handler.
    """
    with SessionLocal() as session:
        session.execute(delete(ClockOverride))
        session.execute(
            insert(ClockOverride).values(pretend_now=pretend_now, anchored_at=datetime.now(UTC))
        )
        session.commit()
