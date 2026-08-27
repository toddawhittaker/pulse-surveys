"""Launch-time provisioning takes its configuration from `Settings` — E1-11, decision D13.

Two items E1-10 deferred, closed together because they are one change: the writer
is handed the configuration the door already holds, and then reads both of the
things it was reading out of the process for itself.

**Item 5 — the environment.** "`app.services.provisioning._environment()` reads
`os.environ` while every other reader of the same rules reads `Settings`… a process
whose `ENVIRONMENT` lives only in a `.env` file that `Settings` loads and
`os.environ` does not see would judge a development stack by a deployment's rules,
and refuse the mock platform's own cleartext roster address on a developer's
machine." **Done when** "`provision_from_launch` takes the environment from
`Settings` … and a test drives a launch under a `.env`-only development
configuration and asserts the mock's address is stored."

**Item 2 — the day.** "The launch day is UTC's day, not the institution's… A launch
in the hours either side of a term boundary can be read into the neighbouring
calendar day and land in the neighbouring term." **Done when** "the launch moment
reaches the writer … and a test drives a launch at an hour that falls on different
dates in UTC and in the institution's zone, asserting the term the institution's
calendar names."

**Both tests state the environment they run under, in their own bodies** — which is
the point of the first of them, and `docs/MISTAKES.md` entry 40's rule for all of
them. The first asserts that `ENVIRONMENT` is *absent* from `os.environ` at the
moment of the launch, because a test of a `.env`-only configuration that ran with
the variable set would pass against exactly the code it exists to fail.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

ENVIRONMENT_VARIABLE = "ENVIRONMENT"
INSTITUTION_TIMEZONE_VARIABLE = "INSTITUTION_TIMEZONE"

# `app.config`'s own name for the one environment where the registration-address
# rules are switched off, quoted rather than transcribed: `.env.example` says
# "Anything other than `development` is a deployment", so the value matters and the
# spelling is the application's.
DEVELOPMENT = "development"

# Two zones at the far ends of the offset range, so that at **every** instant at
# least one of them is on a different calendar date from UTC. Kiritimati is UTC+14
# and is a day ahead whenever it is 10:00 or later in UTC; Niue is UTC-11 and is a
# day behind whenever it is before 11:00. Between them they cover the clock, which
# is what makes this test runnable at any hour rather than only overnight.
CANDIDATE_ZONES = ("Pacific/Kiritimati", "Pacific/Niue")

# How long the one seeded term runs. Long enough to hold a section derived from a
# twelve-week start-letter row (ADR 0021 refuses one that runs past its term) and
# short enough that its *edge* is the thing under test.
TERM_WEEKS = 18


def a_zone_whose_date_differs_from_utc() -> tuple[Any, Any, Any]:
    """A zone where today is not UTC's today, with both dates.

    Answers the zone, the institution's date and UTC's, so the test can seed a term
    around one and assert the other is outside it. A failure here is a failure of
    arithmetic rather than of the code under test, so it says so.
    """
    today = datetime.now(UTC).date()
    for name in CANDIDATE_ZONES:
        zone = ZoneInfo(name)
        local = datetime.now(zone).date()
        if local != today:
            return zone, local, today
    pytest.fail(
        f"Neither {list(CANDIDATE_ZONES)} is on a different calendar date from UTC right now "
        f"({today}), which cannot happen: one is UTC+14 and the other UTC-11, so between them they "
        "differ from UTC at every instant. Either a zone has been renamed in the tzdata this "
        "container carries, or this arithmetic is wrong — and until it is fixed, the test below "
        "cannot pose its question at all."
    )


def test_a_launch_under_a_dotenv_only_development_configuration_stores_the_mocks_address(
    monkeypatch: pytest.MonkeyPatch,
    launch_driver_in: Any,
    launch_ground: Any,
    provisioning_contract: Any,
    provisioned_rows: Any,
    tmp_path: Path,
) -> None:
    """Deferred E1-10 item 5's done-when, driven the way a developer's machine is configured.

    `Settings` loads `.env`; `os.environ` does not. That difference is invisible
    until something reads the variable directly, and E1-10's round-3 review found
    `provision_from_launch` doing exactly that: "a process whose `ENVIRONMENT` lives
    only in a `.env` file … would judge a development stack by a deployment's
    rules, and refuse the mock platform's own cleartext roster address on a
    developer's machine".

    **So the configuration here is the one that tells the two apart**: a `.env` in
    the working directory naming the development environment, and no `ENVIRONMENT`
    in the process at all. `os.environ` is asserted not to carry it, because a test
    of a `.env`-only configuration that ran with the variable set would pass
    against the very code it exists to fail (`docs/MISTAKES.md` entry 40 — the
    suite that ran under an environment nobody chose).

    **The mutation this kills**: `_environment()` reading `os.environ`, which is
    HEAD. Under it, `is_a_deployment("")` is true, the registration-address rules
    are in force, the mock's cleartext `http://mock-lms:8000/…` address is refused,
    and the section is provisioned with a null address and a
    `roster_address_refused` defect — which is E1-11's never-synced state arriving
    as a configuration accident rather than as a platform's choice.

    **Both halves are asserted**, because the address being stored and no defect
    being recorded are two facts and only one of them is visible in the row: a
    writer that stored the address *and* recorded the refusal would be inconsistent
    in a way an operator reading §6.1's console would have to unpick.
    """
    (tmp_path / ".env").write_text(f"{ENVIRONMENT_VARIABLE}={DEVELOPMENT}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(ENVIRONMENT_VARIABLE, raising=False)

    import os

    assert ENVIRONMENT_VARIABLE not in os.environ, (
        f"`{ENVIRONMENT_VARIABLE}` is still in `os.environ` ({os.environ.get(ENVIRONMENT_VARIABLE)!r}), "
        "so a writer reading the process environment directly would find the same answer "
        "`Settings` finds and this test would pass against the defect it is about."
    )
    assert (Path.cwd() / ".env").is_file(), (
        "There is no `.env` in the working directory, so `Settings` has nowhere to read the "
        "environment from either and this launch would run as a deployment for a reason that is "
        "not the one under test."
    )

    driver = launch_driver_in()
    offer = driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    advertised = provisioning_contract.memberships_url_in(claims)
    launch_ground(label)

    response, _ = driver.launch(offer)
    driver.landed(response, "A staff launch under a `.env`-only development configuration")

    assert provisioned_rows.addresses() == [advertised], (
        f"The launch advertised the roster address {advertised!r} and the sections carry "
        f"{provisioned_rows.addresses()}. SPEC §7.3 makes that stored address the whole of the "
        "scheduled job's discovery — 'it has no way of its own to learn that a section exists' — "
        "so a section provisioned without one is never synced at all. Under a `.env`-only "
        "development configuration the address rules are switched off, and a writer that read "
        "`os.environ` rather than `Settings` sees no environment, treats an unset value as a "
        "deployment, and refuses the mock's own cleartext address."
    )
    refused = [
        row
        for row in provisioned_rows.defects()
        if row.get("kind") == provisioning_contract.roster_address_refused
    ]
    assert not refused, (
        f"The launch recorded {[dict(row) for row in refused]}. That defect is E1-10's record of "
        "an address the registration rules refused, and under the development environment those "
        "rules do not apply — so its presence is the environment being read from somewhere that "
        "cannot see this configuration."
    )


def test_a_launch_lands_in_the_term_the_institutions_calendar_names(
    monkeypatch: pytest.MonkeyPatch,
    launch_driver_in: Any,
    launch_ground: Any,
    provisioning_contract: Any,
    provisioned_rows: Any,
) -> None:
    """Deferred E1-10 item 2's done-when: the launch day is the institution's day.

    "A launch in the hours either side of a term boundary can be read into the
    neighbouring calendar day and land in the neighbouring term."

    **One term rather than two, and it is the sharper arrangement.** The seeded
    term contains the institution's date and not UTC's, so the two readings give
    *different kinds* of answer rather than two neighbouring terms: read in the
    institution's zone, the launch finds its term and a section is written; read in
    UTC, no term contains the day at all, E1-10 records `no_term_for_launch_date`
    and writes no section. A test that seeded two adjacent terms would be
    distinguishing two rows; this distinguishes a section from a defect.

    **The zone is chosen at run time from two that bracket the clock**, so this test
    poses its question at every hour rather than only in the few where a
    conveniently-picked zone happens to differ. The two dates are asserted to differ
    before anything is seeded, because a test whose two candidate days were the same
    day would be satisfied by either reading (`docs/MISTAKES.md` entry 3).

    **`INSTITUTION_TIMEZONE` is set before the door is built**, not after: the
    application reads it into `Settings`, and `tool_doors` imports `app.main` fresh
    per call, so a value set afterwards would reach nothing. SPEC §8 makes the
    institution timezone "a deployment-level setting (§6.3)", which is precisely why
    it belongs in the configuration the door hands the writer rather than in the
    writer's own call to `datetime.now(UTC)`.

    **The mutation this kills**: `datetime.now(UTC).date()` in the term lookup,
    which is HEAD.
    """
    zone, institution_day, utc_day = a_zone_whose_date_differs_from_utc()
    assert institution_day != utc_day, (
        f"The institution's date and UTC's are both {utc_day}, so both readings of 'the launch day' "
        "give the same answer and this test cannot tell them apart."
    )
    monkeypatch.setenv(INSTITUTION_TIMEZONE_VARIABLE, str(zone))

    driver = launch_driver_in()
    offer = driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)

    # The term begins on the institution's own date when that date is ahead of
    # UTC's, and ends on it when it is behind — either way exactly one of the two
    # candidate days falls inside it, which is the whole arrangement.
    if institution_day > utc_day:
        starts_on = institution_day
    else:
        starts_on = institution_day - timedelta(days=TERM_WEEKS * 7 - 1)
    ground = launch_ground(label, term_starts_on=starts_on)
    ends_on = starts_on + timedelta(days=TERM_WEEKS * 7 - 1)
    assert starts_on <= institution_day <= ends_on and not starts_on <= utc_day <= ends_on, (
        f"The seeded term runs {starts_on}..{ends_on}; the institution's date is "
        f"{institution_day} and UTC's is {utc_day}. It has to contain exactly one of them, or a "
        "launch would find a term either way and this test would pass whichever clock the writer "
        "read."
    )

    response, _ = driver.launch(offer)
    driver.landed(response, "A staff launch on a day the two zones disagree about")

    sections = provisioned_rows.sections()
    assert len(sections) == 1, (
        f"The launch wrote {len(sections)} sections: {[dict(row) for row in sections]}. Exactly "
        f"one term exists and it contains {institution_day}, the institution's own date — so a "
        "writer reading the institution's calendar provisions one section here. A writer reading "
        f"UTC's date ({utc_day}) finds no term at all, writes nothing, and records "
        f"`{provisioning_contract.no_term_for_launch_date}`, which is what the defects below say."
    )
    term_link = provisioned_rows.link("section", "term")
    assert sections[0][term_link] == ground.term_id, (
        f"The section was written into term {sections[0][term_link]!r} and the term whose calendar "
        f"contains the institution's own date is {ground.term_id!r}. SPEC §8 makes the institution "
        "timezone a deployment-level setting for exactly this reason: a section's term is a fact "
        "about the institution's calendar, not about the server's clock."
    )
    assert not [
        row
        for row in provisioned_rows.defects()
        if row.get("kind") == provisioning_contract.no_term_for_launch_date
    ], (
        "The launch recorded `no_term_for_launch_date` and a term containing the institution's "
        "own date is seeded. That is the writer reading UTC's day: the two are different dates "
        "right now, and only one of them is in any term."
    )
