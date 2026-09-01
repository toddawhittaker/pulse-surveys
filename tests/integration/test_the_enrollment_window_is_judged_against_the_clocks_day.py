"""Whether a person is enrolled *today* is asked of the clock service — E2-04, criterion 1.

`app.services.authz` decides who may see what from the assignment model, and for a
student that decision is one enrollment window against one day: `started_on <=
today AND (ended_on IS NULL OR ended_on >= today)` (E1-13 criterion 5, ADR 0020's
inclusive end, ADR 0028's rule that enrollment is the whole of a student's
access). Before E2-04 that day came from a direct
`datetime.now(ZoneInfo(settings.institution_timezone)).date()` inside the service;
E2-04 makes it `clock.today(...)`, which is the third of the three call sites the
ticket names.

**Why this is the criterion and not a mechanism.** E2 exists to make the weekly
cycle drivable by hand, and the first thing a developer has to be able to do is
*be* a student in a week that is not this one — open next week's survey, watch a
window close, see what a person who dropped in week three sees. Every one of those
begins with the tool agreeing that this person is enrolled on the day the clock
says it is.

**The pair is the whole test.** One window, seeded five years out; with the
override standing the student lands on the student view, and with no override the
same window lands them nowhere. Neither half means anything alone: the first is
satisfied by a resolver that ignores the window entirely, and the second by a
resolver that never lands anybody. Together they say the window was judged against
the clock's day and not the server's.

**The environment is named by each test** (`docs/MISTAKES.md` entry 40) through
`launch_driver_in(DEVELOPMENT)`, which sets it via `tool_doors` so it is true both
at import and at call time. `committed_clock_overrides` is first in each signature
so its teardown runs after the tool's connections close.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fixtures.clock import DEVELOPMENT

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The pretended instant and the window seeded around it. Five years out, so no
# window this test could seed contains both it and today (`docs/MISTAKES.md`
# entry 30).
PRETEND_NOW = datetime(2031, 3, 14, 10, 30, tzinfo=UTC)

# A week either side of the overridden day, which comfortably covers whichever of
# the three candidate dates the institution's zone makes of that instant — the
# zone `today` resolves in is asserted directly on the service in
# `tests/integration/test_the_clock_service_reads_a_development_override.py` and is
# not this module's question.
WINDOW_MARGIN = timedelta(days=7)

# Where a landing lands. E1-08's interface ruling, unchanged since: a landing is a
# redirect whose `Location` is `/app/<route>#session=<token>`.
LANDING_PREFIX = "/app/"
SESSION_FRAGMENT = "#session="
STUDENT_ROUTE = "student"

# The claim a launch carries its subject in.
SUBJECT_CLAIM = "sub"


def student_landing_prefix() -> str:
    """The exact `Location` prefix a student's landing carries."""
    return f"{LANDING_PREFIX}{STUDENT_ROUTE}{SESSION_FRAGMENT}"


def drive_a_student_launch_over(
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
    *,
    started_on: date,
    ended_on: date | None,
) -> Any:
    """One launch by a subject whose only claim on a view is one enrollment window.

    The `tests/integration/test_landing_resolves_from_assignments.py` arrangement,
    which is where E1-13's criterion 5 pinned the window's own edges: the launching
    subject holds no `person` row and no assignment, so enrollment is the only
    thing that can land them anywhere (ADR 0028). The window is always the
    caller's, because which side of the boundary the clock falls on is the whole
    question (`docs/MISTAKES.md` entry 30).
    """
    driver = launch_driver_in(DEVELOPMENT)
    offer = driver.offer_for_role(provisioning_contract.learner_role_urn)
    claims = driver.claims_of(offer)

    subject = claims.get(SUBJECT_CLAIM)
    assert isinstance(subject, str) and subject, (
        f"The launch this platform signs carries `{SUBJECT_CLAIM}` {subject!r}, so there is no "
        "subject to seed a `user` row for and the launch would resolve nobody."
    )

    launch_ground(provisioning_contract.label_of(claims))

    platform_id = driver.registration.platform_row[web_identity.key_of("lti_platform")]
    user_id = web_identity.user(platform_id=platform_id, subject=subject)
    section_id = committed_rows.graph.scope("section")
    committed_rows.commit()
    enrol.enrol(user_id=user_id, section_id=section_id, started_on=started_on, ended_on=ended_on)

    response, _ = driver.launch(offer)
    return response


def test_a_window_around_the_overridden_day_lands_the_student(
    committed_clock_overrides: Any,
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
) -> None:
    """Criterion 1 for the authz call site: the live-enrollment check reads the clock's day.

    The window seeded here contains the overridden day and nothing near today. A
    resolver asking the clock service what today is finds this person enrolled and
    lands them on the student view; a resolver asking the system clock finds a
    window that has not opened yet and lands them nowhere.

    **The mutation this kills**: `datetime.now(...)` inside `app.services.authz`'s
    live-assignment date check, which is HEAD. Under it every hand-driven week is
    unreachable — a developer can move the clock to a week and the tool goes on
    refusing them the section they moved it for.

    **The near miss it must not pass on**: a resolver that stopped reading the
    window at all, which lands this person whichever clock it reads. That is what
    the paired test below rules out, by seeding the same window with no override
    standing and requiring no landing.

    The window's own edges are E1-13's subject and are pinned in
    `tests/integration/test_landing_resolves_from_assignments.py`; this case sits a
    week clear of both of them, so an off-by-one on the boundary cannot be what
    decides it.
    """
    overridden_day = PRETEND_NOW.date()
    real_today = datetime.now(UTC).date()
    started_on = overridden_day - WINDOW_MARGIN
    ended_on = overridden_day + WINDOW_MARGIN
    assert not started_on <= real_today <= ended_on, (
        f"The window this test seeds runs {started_on}..{ended_on} and today is {real_today}, "
        "which is inside it. Then the student lands whichever clock the resolver reads and this "
        "case proves nothing."
    )

    committed_clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))

    response = drive_a_student_launch_over(
        launch_driver_in,
        provisioning_contract,
        launch_ground,
        web_identity,
        enrol,
        committed_rows,
        started_on=started_on,
        ended_on=ended_on,
    )

    location = response.headers.get("location") or ""
    assert location.startswith(student_landing_prefix()), (
        f"The launch answered {response.status_code} with `Location: {location!r}`, and a student's "
        f"landing is `{student_landing_prefix()}<token>`. The clock is overridden to "
        f"{PRETEND_NOW!r} and this person's enrollment runs {started_on}..{ended_on}, which "
        f"contains that day and not today ({real_today}). A resolver reading the system clock sees "
        "a window that has not opened yet and lands them on the calm no-access page instead — "
        "which is the whole of what makes a hand-driven week unreachable."
    )


def test_the_same_window_lands_nobody_with_no_override_standing(
    committed_clock_overrides: Any,
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    web_identity: Any,
    enrol: Any,
    committed_rows: Any,
) -> None:
    """The pair: without the override the window is five years from opening, and nobody lands.

    Identical to the test above in every respect but one — no row in
    `clock_override` — so the difference in the answer is attributable to the
    override and to nothing else.

    **What this rules out**: a resolver that ignores the enrollment window
    entirely, which would land this person in both cases and make the test above a
    statement about nothing (`docs/MISTAKES.md` entry 3); and an override applied
    unconditionally, which would move the clock even with no row and make the two
    cases indistinguishable.

    **The forbidden state is asserted, not the absence of the permitted one**
    (`docs/MISTAKES.md` entry 2). Two things must be true: the browser was not sent
    to the student view, and no session token left the door at all. A door that
    stopped sending the student route while still handing over a session would
    satisfy a route-only check and would have admitted somebody whose enrollment
    starts in 2031.

    The table is read back and required empty first, because "no override" is a
    premise this test has to establish rather than assume — a row left behind by a
    neighbour would make this the same case as the one above wearing the opposite
    name.
    """
    assert committed_clock_overrides.rows() == [], (
        f"`clock_override` already holds {committed_clock_overrides.rows()} before this test began. "
        "This case is the no-override half of a pair, and a row left standing would make it the "
        "other half."
    )

    overridden_day = PRETEND_NOW.date()
    started_on = overridden_day - WINDOW_MARGIN
    ended_on = overridden_day + WINDOW_MARGIN

    response = drive_a_student_launch_over(
        launch_driver_in,
        provisioning_contract,
        launch_ground,
        web_identity,
        enrol,
        committed_rows,
        started_on=started_on,
        ended_on=ended_on,
    )

    location = response.headers.get("location") or ""
    assert not location.startswith(student_landing_prefix()), (
        f"The launch answered `Location: {location!r}` with no override standing and an enrollment "
        f"running {started_on}..{ended_on} — a window that does not open for five years. Landing "
        "this person on the student view means the window was not read at all, which would make "
        "the paired test above true of a resolver that never asked what day it was."
    )
    assert SESSION_FRAGMENT not in location, (
        f"The launch answered `Location: {location!r}`, which carries a session token, for a "
        "person whose only claim on any view is an enrollment that has not started. Where the rows "
        "entitle somebody to nothing, nothing is what the door hands over."
    )
