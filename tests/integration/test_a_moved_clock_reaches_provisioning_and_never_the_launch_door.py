"""One launch, two clocks — E2-04 criteria 1 and 4, asserted against each other.

E2-04 draws a line through the codebase's readings of "now". On one side is
**scheduling and visibility**, which goes through `app.services.clock` and moves
when a developer moves it: which term a launch lands in, which enrollments are
live, which survey window is open. On the other is **protocol time**, which stays
real: nonce and state expiry, an `id_token`'s own `exp`, clock skew, session
expiry, audit timestamps. The ticket states the second side as its own criterion —
"Launch validation, session expiry, and audit timestamps still read real time —
pinned by a test that sets the override and watches a token's clock-skew check not
move" — and its security header says why: "a movable clock on nonce, state, or
token expiry checks would open the replay window E1 closed."

**The two tests below are mirror images of each other, and neither is worth much
alone.** The first shows a staff launch provisioning into the term that contains
the *overridden* day, which is criterion 1 for `app.services.provisioning`'s term
lookup. The second shows a launch **accepted** with the clock five years on — the
protocol side — while the *same request* records `no_term_for_launch_date`,
because the scheduling side moved. One request, two clocks, and the defect record
is what makes the acceptance mean something: without it, "the launch was accepted"
is exactly what an override that never applied looks like (`docs/MISTAKES.md`
entry 3).

**Why the launch door is the cheapest place to pin criterion 4.** The mock
platform mints its `id_token` on real time — `iat` now, `exp` minutes out. A tool
validating that token against a clock five years ahead sees a token that expired
half a decade ago and refuses the launch. Nothing has to be constructed for this:
the discriminator is already in every launch this suite drives, which is why it is
the cheapest protocol read to pin.

**The environment is named by each test** (`docs/MISTAKES.md` entry 40):
`launch_driver_in(DEVELOPMENT)` sets it through `tool_doors`, so it is true both
at import — for anything built out of `Settings` — and at call time. The override
only applies in development, so a test that let the variable default would be
proving nothing on the day `.env.example` changed.

`committed_clock_overrides` is listed before the door fixtures in every signature
here on purpose: fixtures are finalised in reverse of setup, so its
`DELETE FROM clock_override` runs after the tool's connections are closed.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fixtures.clock import DEVELOPMENT, PRETEND_NOW_COLUMN

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The pretended instant, and the term seeded around it. Five years out, so no
# tolerance could confuse it with real time and no seeded calendar could contain
# both days (`docs/MISTAKES.md` entry 30).
PRETEND_NOW = datetime(2031, 3, 14, 10, 30, tzinfo=UTC)

# A Monday, so the term begins where a term calendar begins, and eighteen weeks
# long — the length `tests/fixtures/provisioning.py` seeds and the reference model
# SPEC §2.2 gives for a fall or spring term.
PRETEND_TERM_STARTS_ON = date(2031, 3, 3)
TERM_WEEKS = 18

# The widest offset any IANA zone carries, either way. The term below is required
# to contain the pretended day whichever zone the institution is in, so that this
# module never has to name a zone at all: at ±14 hours the pretended instant is
# still eleven days inside an eighteen-week term.
WIDEST_ZONE_OFFSET = timedelta(hours=14)


def days_the_pretend_instant_could_fall_on() -> set[date]:
    """Every calendar date the overridden instant could be, in any institution zone.

    The service reads `settings.institution_timezone`, and this module deliberately
    does not care which zone that is — the seeded term is wide enough to contain
    all three candidates. Which zone `today` resolves in is asserted directly, on
    the service itself, in
    `tests/integration/test_the_clock_service_reads_a_development_override.py`.
    """
    return {
        (PRETEND_NOW - WIDEST_ZONE_OFFSET).date(),
        PRETEND_NOW.date(),
        (PRETEND_NOW + WIDEST_ZONE_OFFSET).date(),
    }


def test_a_staff_launch_provisions_into_the_term_containing_the_overridden_day(
    committed_clock_overrides: Any,
    launch_driver_in: Any,
    launch_ground: Any,
    provisioning_contract: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 1 for the provisioning call site: the launch day is the clock's day.

    `app.services.provisioning` looks up "the one term whose dates contain the day
    of the launch". Before E2-04 it computed that day with a direct
    `datetime.now(ZoneInfo(settings.institution_timezone)).date()`; E2-04 makes it
    `clock.today(...)`, so an overridden stack provisions into the term the
    developer moved to.

    **The arrangement is one term rather than two**, the sharper one E1-11 chose
    for the same question: the seeded term contains the *pretended* day and not the
    real one, so the two readings give different kinds of answer rather than two
    neighbouring rows. Read through the clock service, the launch finds its term
    and a section is written; read off the system clock, no term contains the day
    at all, E1-10 records `no_term_for_launch_date` and writes nothing. A section
    against a defect, not a row against a row.

    **The mutation this kills**: the direct `datetime.now(...)` in the term lookup,
    which is HEAD. **The near miss it must not pass on**: a term seeded so wide it
    contains both days, which is why the real day is asserted to be outside it
    before the launch is driven.
    """
    ground_start = PRETEND_TERM_STARTS_ON
    ground_end = ground_start + timedelta(days=TERM_WEEKS * 7 - 1)
    real_today = datetime.now(UTC).date()
    assert not ground_start <= real_today <= ground_end, (
        f"The term this test seeds runs {ground_start}..{ground_end} and today is {real_today}, "
        "which is inside it. Then a launch finds a term whichever clock it reads and this case "
        "cannot tell the two apart."
    )
    for candidate in days_the_pretend_instant_could_fall_on():
        assert ground_start <= candidate <= ground_end, (
            f"The overridden instant {PRETEND_NOW!r} could fall on {candidate} in some institution "
            f"timezone, and the seeded term runs {ground_start}..{ground_end}. The term has to "
            "contain the pretended day in every zone, or this case would depend on a zone it never "
            "named."
        )

    committed_clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))

    driver = launch_driver_in(DEVELOPMENT)
    offer = driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = driver.claims_of(offer)
    ground = launch_ground(provisioning_contract.label_of(claims), term_starts_on=ground_start)

    response, _ = driver.launch(offer)
    driver.accepted(response, "A staff launch on a stack whose clock has been moved to 2031")

    sections = provisioned_rows.sections()
    assert len(sections) == 1, (
        f"The launch wrote {len(sections)} sections: {[dict(row) for row in sections]}. Exactly "
        f"one term exists and it runs {ground_start}..{ground_end}, which contains the day the "
        f"overridden clock names and not today ({real_today}). A writer reading the clock service "
        "provisions one section here; a writer reading the system clock finds no term, writes "
        f"nothing, and records `{provisioning_contract.no_term_for_launch_date}`."
    )
    term_link = provisioned_rows.link("section", "term")
    assert sections[0][term_link] == ground.term_id, (
        f"The section was written into term {sections[0][term_link]!r} and the term containing the "
        f"overridden day is {ground.term_id!r}."
    )
    assert not [
        row
        for row in provisioned_rows.defects()
        if row.get("kind") == provisioning_contract.no_term_for_launch_date
    ], (
        f"The launch recorded `{provisioning_contract.no_term_for_launch_date}` while a term "
        "containing the overridden day was seeded. That is the term lookup reading a clock the "
        "development override does not reach."
    )


def test_a_launch_is_accepted_with_the_clock_five_years_on(
    committed_clock_overrides: Any,
    launch_driver_in: Any,
    launch_ground: Any,
    provisioning_contract: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 4: the door's own clock does not move, in the same request that proves one did.

    The mock platform signs its `id_token` on real time, so the launch this test
    drives carries an `iat` of now and an `exp` minutes out. A tool that validated
    it against the overridden clock would be judging a token issued five years ago
    against an expiry five years past, and would refuse the launch — which is
    exactly the failure mode the ticket's security header names in reverse: "a
    movable clock on nonce, state, or token expiry checks would open the replay
    window E1 closed", and the same movable clock closes the door on every honest
    launch.

    **The term seeded here contains today**, not the overridden day, and that
    inverts the test next door. So the launch must be *accepted* — the protocol
    side reading real time — and must record `no_term_for_launch_date` — the
    scheduling side reading the moved one. Two clocks, one request, and the second
    assertion is what makes the first mean anything: an override that never applied
    would leave the launch accepted for reasons that have nothing to do with this
    ticket, and no assertion about acceptance alone can tell those apart
    (`docs/MISTAKES.md` entry 3).

    **The mutations this kills**: routing `app.lti.launch`'s expiry, skew or nonce
    checks through the clock service — the tidy-up somebody does when a sweep for
    `datetime.now` turns up the launch door; and the override applying in a
    process-wide way that reaches every reader of the current time rather than the
    named scheduling ones.

    E2-04's ADR carries the explicit list of clocks this service does not touch —
    launch validation, session expiry, audit timestamps, `func.now()` column
    defaults, the NRPS debounce and call log, and Celery beat's own firing
    schedule. This is the one of them with a door in front of it, which is why it
    is the one with a test.
    """
    committed_clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))
    standing = committed_clock_overrides.rows()
    assert len(standing) == 1 and standing[0][PRETEND_NOW_COLUMN] == PRETEND_NOW, (
        f"`clock_override` holds {standing} rather than the single row this test committed. The "
        "whole question below is what a launch does while an override stands, and no row is not "
        "that question."
    )

    driver = launch_driver_in(DEVELOPMENT)
    offer = driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = driver.claims_of(offer)
    launch_ground(provisioning_contract.label_of(claims))

    response, _ = driver.launch(offer)
    driver.accepted(
        response,
        "A staff launch signed on real time, arriving at a tool whose development clock is five "
        "years ahead",
    )

    moved = [
        row
        for row in provisioned_rows.defects()
        if row.get("kind") == provisioning_contract.no_term_for_launch_date
    ]
    assert moved, (
        "The launch above was accepted, and nothing shows the clock was moved while it happened. "
        f"The seeded term contains today and not {PRETEND_NOW.date()}, so a term lookup reading "
        f"the overridden clock records `{provisioning_contract.no_term_for_launch_date}` — and "
        "that record is this test's canary. Without it, an accepted launch is what an override "
        "that never applied looks like, and criterion 4 would be attested by a test that never "
        f"moved a clock. Defects recorded: {[dict(row) for row in provisioned_rows.defects()]}."
    )
    assert not provisioned_rows.sections(), (
        f"The launch provisioned {[dict(row) for row in provisioned_rows.sections()]} while the "
        "only seeded term contains today rather than the overridden day. A section written here "
        "means the term lookup found a term for a day no term covers, which contradicts the "
        "defect record beside it."
    )
