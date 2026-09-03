"""When the next survey opens, and which zone to read it in — ticket FIX-01, items 2 and 4.

FIX-01's fourth item: a closed section's placeholder "says when". The owner's
ruling of 2026-09-03, wording exact: *"When the next survey for this course opens
at 6:00PM EDT on Friday, September 4, it appears here."* The sentence is the
screen's; what this module is about is the two things the read answer has to
carry before any screen can write it — the next materialized window's opening
instant, and the zone that instant is to be read in.

**Three states, and each of the other two is what makes the middle one mean
something.** A section whose survey is open carries no next instant, a section
whose survey is closed with a window still ahead carries that window's
`opens_at`, and a section whose survey is closed with nothing ahead carries no
instant and keeps the sentence it has today. A module asserting only the middle
state would pass against a field that simply always names the next materialized
window — which is a page telling a student, inside an open window, when the
*following* one starts.

**The instants are transcribed, never computed.** Every expected moment here is
`WINDOWS_BY_TERM_WEEK`'s — the hand-written Fall 2026 calendar in
`tests/fixtures/survey_windows.py`, which
`tests/unit/test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py` controls
against SPEC §3.1's own rhythm. Nothing here re-derives a Friday, an offset or a
zone conversion, because an expectation derived by the same arithmetic as the
code under test agrees with an implementation that made the same mistake
(`docs/MISTAKES.md` entry 19).

**The fields are found by walking the answer.** The work order settles the two
member names — `next_window_opens_at` on the enrolled-section entry and
`institution_timezone` on the view — and settles nothing about where in the
document they sit, so they are looked for wherever they are, exactly as E2-09's
own week-number test looks for its pair.

**What is not here.** The §4.1 refusal pair is
`test_the_student_read_path_names_nothing_outside_the_enrollment.py`'s and is
unchanged by this ticket: the two new members are the same for every read of the
route, so the two parametrised reads stay byte-identical to the plain one. The
rendered sentence, its `6:00PM EDT` shape and the zone abbreviation the date
derives are `tests/e2e/student-survey-heading-and-next-window.spec.ts`'s.
"""

from datetime import datetime
from typing import Any

import pytest
from fixtures.clock import INSTITUTION_TIMEZONE_VARIABLE
from fixtures.student_read import (
    A_NON_DEFAULT_INSTITUTION_TIMEZONE,
    AFTER_THE_WINDOW,
    DEFAULT_INSTITUTION_TIMEZONE,
    INSIDE_THE_WINDOW,
    INSTITUTION_TIMEZONE_FIELD,
    NEXT_TERM_WEEK,
    NEXT_WINDOW_FIELD,
    NEXT_WINDOW_OPENS_AT,
    OTHER_NEXT_WINDOW_OPENS_AT,
    OTHER_SECTIONS_NEXT_TERM_WEEK,
    STUDENT_READ_PATH,
    WINDOW_CLOSES_AT,
    WINDOW_OPENS_AT,
    StudentReadDoor,
    around,
    decoded,
    instants_in,
    objects_carrying,
    response_surface,
)
from fixtures.survey_windows import WINDOW_OPENS_COLUMN

pytestmark = [pytest.mark.integration, pytest.mark.lti]


def sole_entry(body: Any, answered: Any) -> dict[str, Any]:
    """The one object in the answer that carries the next-window member.

    One, because this reader has exactly one live enrollment. Nought means the
    member is not on the wire at all, which is the state every test here is
    written red against and the message says so; more than one means an
    enrollment is being reported twice, which is a different defect and worth
    telling apart from a wrong instant.
    """
    entries = objects_carrying(body, NEXT_WINDOW_FIELD)
    assert len(entries) == 1, (
        f"{len(entries)} objects in the answer carry `{NEXT_WINDOW_FIELD}`, and this student has "
        f"one live enrollment. Body begins {answered.text[:400]!r}.\n\n"
        "FIX-01 item 4 puts the next materialized window's opening instant on the enrolled-section "
        f"entry under exactly that name, as `datetime | None` — so the member is *present* on "
        "every entry and is null when there is nothing ahead. Nought here is the member missing "
        "from the schema, which is what this ticket owes; two is one enrollment answered twice."
    )
    return entries[0]


def instant_carried(entry: dict[str, Any], answered: Any) -> datetime:
    """The entry's next-window member as a moment, or a failure saying what it was.

    Parsed rather than string-compared, for the reason
    `fixtures.student_read.instants_in` gives: FIX-01 settles the member and
    settles no serialization for it, so `2026-11-27T23:00:00Z` and
    `2026-11-27T23:00:00+00:00` are one moment written two ways and a test
    comparing text would be pinning a choice the ticket leaves open.
    """
    value = entry[NEXT_WINDOW_FIELD]
    assert isinstance(value, str), (
        f"`{NEXT_WINDOW_FIELD}` came back as {value!r} ({type(value).__name__}). It carries an "
        f"instant, and the answer is JSON. Body begins {answered.text[:400]!r}."
    )
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, (
        f"`{NEXT_WINDOW_FIELD}` came back as {value!r}, which carries no offset. ADR 0019 stores "
        "every instant aware, and a naive one on the wire is a moment the browser will read in "
        "whatever zone it happens to be in — which is the whole defect this member exists to fix."
    )
    return parsed


def zones_carried(body: Any) -> list[str]:
    """Every `institution_timezone` anywhere in the answer, wherever it sits."""
    return [
        entry[INSTITUTION_TIMEZONE_FIELD]
        for entry in objects_carrying(body, INSTITUTION_TIMEZONE_FIELD)
    ]


# ---------------------------------------------------------------------------
# The three states the instant has to tell apart.
# ---------------------------------------------------------------------------


def test_a_section_whose_survey_is_open_names_no_next_window(
    student_read_door: StudentReadDoor,
) -> None:
    """Item 4, the first direction: an open week says nothing about the one after it.

    The clock is inside term week 13's window and a window over term week 15 is
    materialized as well, so there genuinely *is* a next window — and the answer
    must still carry `None`. A section with a survey open is not a section
    waiting for one, and the sentence this member feeds is the closed-state
    placeholder.

    **The mutations this kill.** The member filled from "the next materialized
    window for this section" with no regard for whether the survey is open, which
    is the shortest implementation and answers term week 15's instant here; and
    the member filled from the *open* window's own `opens_at`, which answers term
    week 13's. Both are named in the message, by the instant that came back.

    **The near miss it must survive**: the member being present and null. That is
    the pass, and it is why the assertion is on the value rather than on the
    member's absence — a schema that omitted the key when it is null would be a
    different, defensible choice, so the failure message names both readings.

    **The canary, first.** A next window is required to exist before the answer
    is asked to withhold it: without that row this test is green against an
    implementation that never looks for one (`docs/MISTAKES.md` entry 3).
    """
    world = student_read_door.world
    assert WINDOW_OPENS_AT <= INSIDE_THE_WINDOW <= WINDOW_CLOSES_AT, (
        f"{INSIDE_THE_WINDOW} is not inside the window this world seeds ({WINDOW_OPENS_AT} to "
        f"{WINDOW_CLOSES_AT}), so the read below is not the open case this test claims."
    )
    assert INSIDE_THE_WINDOW < NEXT_WINDOW_OPENS_AT, (
        f"Term week {NEXT_TERM_WEEK}'s window opens at {NEXT_WINDOW_OPENS_AT}, which is not after "
        f"the instant this test reads at ({INSIDE_THE_WINDOW}). It has to be ahead, or there is no "
        "next window for a wrong implementation to name and this test cannot fail."
    )

    ahead = world.seed_window_over(world.enrolled_section, NEXT_TERM_WEEK)
    assert ahead[WINDOW_OPENS_COLUMN] == NEXT_WINDOW_OPENS_AT, (
        f"The window this test seeded ahead of the reader opens at {ahead[WINDOW_OPENS_COLUMN]} "
        f"and term week {NEXT_TERM_WEEK} of Fall 2026 opens at {NEXT_WINDOW_OPENS_AT}. The row is "
        "the whole premise of the assertion below."
    )

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student inside an open "
        f"window. Body begins {answered.text[:300]!r}."
    )
    entry = sole_entry(decoded(answered, f"`GET {STUDENT_READ_PATH}`"), answered)

    assert entry[NEXT_WINDOW_FIELD] is None, (
        f"With the survey open, the answer carries {entry[NEXT_WINDOW_FIELD]!r} as "
        f"`{NEXT_WINDOW_FIELD}`.\n\n"
        f"The window on screen runs {WINDOW_OPENS_AT} to {WINDOW_CLOSES_AT} and the clock is at "
        f"{INSIDE_THE_WINDOW}; the next materialized window opens at {NEXT_WINDOW_OPENS_AT} and "
        f"the open one opened at {WINDOW_OPENS_AT}. A value equal to the first is the member being "
        "filled without asking whether the survey is open — which puts 'when the next survey opens' "
        "on a page that is offering this week's form. A value equal to the second is the open "
        "window's own instant served under this member's name."
    )


def test_a_closed_section_with_a_window_still_ahead_names_when_it_opens(
    student_read_door: StudentReadDoor,
) -> None:
    """Item 4, the second direction: the placeholder gets the instant it needs.

    The clock is past term week 13's close and a window over term week 15 is
    materialized, so the answer must carry that window's `opens_at` — the fact
    the ruled sentence is built out of, and the fact the system already held and
    was withholding.

    **The mutations this kills.** The member left null whenever the survey is
    closed, which is today's behaviour written into the schema and is the state
    this test is red against. The *closing* instant served in the opening
    instant's place, which reads perfectly well and is two days out. And the
    window's own `opens_at` taken from the week that just closed rather than the
    week ahead — term week 13's instant, which is in the past and would render a
    date that has already gone.

    **The near miss it must survive**: any ISO-8601 spelling of the right moment,
    because the ticket settles the member and not its serialization.

    **The canary, first.** The seeded row is required to carry the instant this
    test expects, and the clock is required to be past the close and before the
    opening — so a green is about the read path and not about a world that
    happened to line up differently.
    """
    world = student_read_door.world
    assert WINDOW_CLOSES_AT < AFTER_THE_WINDOW < NEXT_WINDOW_OPENS_AT, (
        f"{AFTER_THE_WINDOW} does not sit between term week 13's close ({WINDOW_CLOSES_AT}) and "
        f"term week {NEXT_TERM_WEEK}'s open ({NEXT_WINDOW_OPENS_AT}), so this read is not the "
        "closed-with-a-window-ahead case it claims to be."
    )

    ahead = world.seed_window_over(world.enrolled_section, NEXT_TERM_WEEK)
    assert ahead[WINDOW_OPENS_COLUMN] == NEXT_WINDOW_OPENS_AT, (
        f"The seeded next window opens at {ahead[WINDOW_OPENS_COLUMN]} and term week "
        f"{NEXT_TERM_WEEK} of Fall 2026 opens at {NEXT_WINDOW_OPENS_AT}."
    )
    student_read_door.pretend(AFTER_THE_WINDOW)

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student whose window has "
        f"closed. Body begins {answered.text[:300]!r}. A student whose week has closed is still "
        "enrolled: the answer says there is nothing open, it does not refuse."
    )
    entry = sole_entry(decoded(answered, f"`GET {STUDENT_READ_PATH}`"), answered)

    assert entry[NEXT_WINDOW_FIELD] is not None, (
        f"With the survey closed and term week {NEXT_TERM_WEEK}'s window materialized and still "
        f"ahead, the answer carries no `{NEXT_WINDOW_FIELD}`.\n\n"
        "FIX-01 item 4: 'the read answer gains the next window's opening instant for sections "
        "whose survey is not open'. The system already holds this row — the placeholder withholds "
        "a date it has, which is the defect the owner's ruling of 2026-09-03 names."
    )
    assert instant_carried(entry, answered) == NEXT_WINDOW_OPENS_AT, (
        f"The answer names {entry[NEXT_WINDOW_FIELD]!r} as the next opening; term week "
        f"{NEXT_TERM_WEEK}'s window opens at {NEXT_WINDOW_OPENS_AT}.\n\n"
        f"{WINDOW_CLOSES_AT} would be the week that just closed, served as though it were ahead. "
        f"{WINDOW_OPENS_AT} would be that week's own opening, which is in the past. Anything an "
        "hour out is one zone conversion per window rather than one per instant (E2-06's own "
        "daylight-saving case)."
    )


def test_a_closed_section_with_nothing_ahead_names_no_instant(
    student_read_door: StudentReadDoor,
) -> None:
    """Item 4's stated exception: 'a section with no future window keeps the current sentence'.

    The clock is past term week 13's close and this world materializes nothing
    after it, so there is no opening instant to name and the member is null. That
    null is what the screen falls back to the undated sentence on.

    **The mutation this kills**: a member filled from the section's *last*
    window, or from any window at all, when there is none ahead — which renders a
    sentence promising a survey on a date that has already passed. A member
    filled from the term's calendar rather than from the materialized rows fails
    here too: ADR 0111 makes the answer exactly the set of `survey_window` rows,
    and term week 14 onward exists in the calendar and not in this table.

    **The near miss it must survive** is the sibling above, which seeds a window
    ahead and requires it to be named. The two are the pair: this one is only
    meaningful because the other proves the member is capable of carrying
    something.

    **The canary, first**: the clock really is past the close, and no window
    beyond term week 13 has been seeded for this section.
    """
    assert WINDOW_CLOSES_AT < AFTER_THE_WINDOW, (
        f"{AFTER_THE_WINDOW} is not after the window closes at {WINDOW_CLOSES_AT}, so this is not "
        "the closed case."
    )
    student_read_door.pretend(AFTER_THE_WINDOW)

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code}. Body begins "
        f"{answered.text[:300]!r}."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")
    entry = sole_entry(body, answered)

    assert entry[NEXT_WINDOW_FIELD] is None, (
        f"This section's only materialized window closed at {WINDOW_CLOSES_AT} and nothing was "
        f"seeded after it, yet the answer carries {entry[NEXT_WINDOW_FIELD]!r} as "
        f"`{NEXT_WINDOW_FIELD}`. The instants the answer holds are {sorted(instants_in(body))}.\n\n"
        "FIX-01 item 4 keeps the undated sentence for a section with no future window. A value "
        "here is a window read out of the term calendar rather than out of the materialized rows "
        "(ADR 0111), or the closed window's own instants served as though they were ahead — either "
        "way the screen would name a date that has gone."
    )


# ---------------------------------------------------------------------------
# Whose window it is.
# ---------------------------------------------------------------------------


def test_the_next_window_named_is_the_readers_own_sections_and_no_other(
    student_read_door: StudentReadDoor,
) -> None:
    """Item 4, scoped: 'the reader's own section's window and nothing else's'.

    Two sections are closed at this instant and both have a window ahead. The one
    the reader is enrolled in opens in term week 15; the one they are **not**
    enrolled in opens in term week 14, a week *earlier*. So the earliest window
    in the database is not the reader's, and a read that asked "which window
    opens next" without saying whose section it is asking about answers the
    wrong one.

    **The order of the pair is the whole test.** Were the reader's window the
    earlier of the two, a query ordered by `opens_at` with no section predicate
    would return exactly what the correct query returns and the mutation would
    survive with the suite green — the shape `docs/MISTAKES.md` entry 3 is about,
    and the shape E2-09's own mutation battery measured on this world's
    enrollment predicate.

    **The mutations this kills.** A next-window lookup with no `section_id`
    predicate. One joined to the course, or to the term, or to the week rather
    than to the section — the two sections here are siblings under one course of
    one term, so all three reach the other's row. And one scoped to the section
    but ordered descending, which returns the *last* window rather than the next.

    **The near miss it must survive**: the correct answer, which names term week
    15's instant and nothing else. It is asserted first, before the denial,
    because an answer carrying no instant at all does not name the other
    section's window either (`docs/MISTAKES.md` entry 3).
    """
    world = student_read_door.world
    assert OTHER_NEXT_WINDOW_OPENS_AT < NEXT_WINDOW_OPENS_AT, (
        f"The other section's next window ({OTHER_NEXT_WINDOW_OPENS_AT}) is not earlier than this "
        f"reader's ({NEXT_WINDOW_OPENS_AT}). It has to be earlier, or a lookup that ignores the "
        "section returns the reader's own window anyway and this test passes against the mutation "
        "it exists to kill."
    )
    assert AFTER_THE_WINDOW < OTHER_NEXT_WINDOW_OPENS_AT, (
        f"{OTHER_NEXT_WINDOW_OPENS_AT} is not ahead of the instant this test reads at "
        f"({AFTER_THE_WINDOW}), so it is not a window an unscoped 'next' query would reach."
    )

    mine = world.seed_window_over(world.enrolled_section, NEXT_TERM_WEEK)
    theirs = world.seed_window_over(world.other_section, OTHER_SECTIONS_NEXT_TERM_WEEK)
    assert (mine[WINDOW_OPENS_COLUMN], theirs[WINDOW_OPENS_COLUMN]) == (
        NEXT_WINDOW_OPENS_AT,
        OTHER_NEXT_WINDOW_OPENS_AT,
    ), (
        f"The two seeded windows open at {mine[WINDOW_OPENS_COLUMN]} and "
        f"{theirs[WINDOW_OPENS_COLUMN]}; term weeks {NEXT_TERM_WEEK} and "
        f"{OTHER_SECTIONS_NEXT_TERM_WEEK} of Fall 2026 open at {NEXT_WINDOW_OPENS_AT} and "
        f"{OTHER_NEXT_WINDOW_OPENS_AT}."
    )
    student_read_door.pretend(AFTER_THE_WINDOW)

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code}. Body begins "
        f"{answered.text[:300]!r}."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")
    entry = sole_entry(body, answered)

    assert entry[NEXT_WINDOW_FIELD] is not None, (
        f"The answer carries no `{NEXT_WINDOW_FIELD}` at all, so the denial below would be a "
        f"statement about an empty member. Body begins {answered.text[:400]!r}."
    )
    assert instant_carried(entry, answered) == NEXT_WINDOW_OPENS_AT, (
        f"The answer names {entry[NEXT_WINDOW_FIELD]!r} as this reader's next opening. Their own "
        f"section's next window opens at {NEXT_WINDOW_OPENS_AT}; the section they are not enrolled "
        f"in opens at {OTHER_NEXT_WINDOW_OPENS_AT}, a week earlier.\n\n"
        "The earlier instant here is a lookup with no section predicate, or one joined to the "
        "course, the term or the week — the two sections are siblings under one course of one "
        "term, so every one of those reaches the other's row."
    )

    surface = response_surface(answered)
    leaked = sorted(
        spelling
        for spelling in (
            OTHER_NEXT_WINDOW_OPENS_AT.isoformat(),
            OTHER_NEXT_WINDOW_OPENS_AT.isoformat().replace("+00:00", "Z"),
        )
        if spelling in surface
    )
    assert not leaked and OTHER_NEXT_WINDOW_OPENS_AT not in instants_in(body), (
        f"The answer names {OTHER_NEXT_WINDOW_OPENS_AT}, which is when a survey opens for a "
        "section this student is not enrolled in. It carries the instants "
        f"{sorted(instants_in(body))}"
        + (f", and the text sits in {around(surface, leaked[0])!r}" if leaked else "")
        + ".\n\nSPEC §4.1 item 1: a student is never shown another section, in any surface. A "
        "window instant is a fact about somebody else's course calendar, and it reaches the page "
        "the moment a 'when does the next one open' lookup stops naming a section."
    )


# ---------------------------------------------------------------------------
# The zone the instant is to be read in.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("zone", (DEFAULT_INSTITUTION_TIMEZONE, A_NON_DEFAULT_INSTITUTION_TIMEZONE))
def test_the_answer_names_the_institution_timezone_the_deployment_is_configured_with(
    student_read_door_in: Any, zone: str
) -> None:
    """Item 4's other half: the instant is rendered "in `INSTITUTION_TIMEZONE`".

    SPEC §3.1 puts every window at a wall-clock time in the institution's zone,
    and the ruled sentence names that wall-clock time with an abbreviation
    derived from the date. The browser cannot derive either without being told
    which zone, so the read answer carries it. It is deployment configuration and
    not person data — the same string for every reader of the deployment.

    **Two zones, and that is the whole design of this test.** Asserted only under
    the documented default, a member hard-coded to `America/New_York` passes
    perfectly; asserted under a zone this repository configures nowhere, it does
    not. The pair is what tells a member that *follows the setting* from a
    constant that happens to agree with it (`docs/MISTAKES.md` entry 3), and each
    case states the value it runs under rather than inheriting one (entry 40).

    **The mutations this kill.** The zone written as a literal in the schema or
    the service. The zone read from the process's own `TZ` rather than from
    `Settings`, which answers whatever the container was started with and would be
    UTC in CI under both cases. And the member absent, which is the state this
    test is first red against.

    **The near miss it must survive**: the answer carrying the zone in more than
    one place — a per-section copy as well as a view-level one is a shape the
    ticket does not forbid — so every occurrence is required to be this zone
    rather than exactly one occurrence being required.
    """
    door = student_read_door_in(**{INSTITUTION_TIMEZONE_VARIABLE: zone})

    answered = door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} with "
        f"{INSTITUTION_TIMEZONE_VARIABLE}={zone}. Body begins {answered.text[:300]!r}."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")

    carried = zones_carried(body)
    assert carried, (
        f"Nothing in the answer carries `{INSTITUTION_TIMEZONE_FIELD}`. Body begins "
        f"{answered.text[:400]!r}.\n\n"
        "FIX-01 item 4 renders the next window's opening instant 'in `INSTITUTION_TIMEZONE` with "
        "the zone abbreviation derived from the date'. A browser handed an instant and no zone "
        "renders it in the reader's own, so a student travelling — or one whose laptop is set to "
        "UTC — is told a survey opens at an hour nobody's institution keeps."
    )
    wrong = sorted({value for value in carried if value != zone})
    assert not wrong, (
        f"The answer carries {carried} as `{INSTITUTION_TIMEZONE_FIELD}` and this deployment is "
        f"configured with {INSTITUTION_TIMEZONE_VARIABLE}={zone}.\n\n"
        f"{DEFAULT_INSTITUTION_TIMEZONE!r} under the non-default case is the zone written as a "
        "literal rather than read from `Settings` — which is the mutation this parametrisation "
        "exists to kill, and which the default case alone cannot see. `UTC` is the process's own "
        "zone being reported instead of the institution's."
    )
