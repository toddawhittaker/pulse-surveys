"""E2-08 — the controls on this ticket's own test machinery.

`tests/fixtures/submit.py` is new machinery, and four of E2-08's five criteria
are asserted through it. Everything below is a control on that machinery rather
than an assertion about the submit path, and every one of them is expected to be
**green on a tree where E2-08 has not been built at all**: they rest on E2-05's
schema, E2-06's window service, E1-08's session module and the operating system's
own refusal of a closed port.

**A red here means the tests are broken, not the code.** That is the whole
purpose of the module. Three of the assertions the other modules make are
satisfied by emptiness or by blindness and could not tell you so:

  - "a refused submission stored nothing" passes against a reader that cannot see
    what another connection committed;
  - "a submission into an open window was accepted" is about a window that has to
    be genuinely open at the moment the request is made;
  - "a session was refused" is about a session that would otherwise have been
    accepted.

`docs/MISTAKES.md` entry 3 is the rule and entry 20 is the near miss: a mutation
the fixture undoes reads as a test that cannot fail.

**One test here is not a control**, and it is fenced off below: the submit route
existing at all. It is expected red until the route lands, and it is here rather
than in the criteria modules so that "the deliverable is absent" is one legible
failure instead of thirty identical ones.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fixtures.submit import (
    COURSE_COMMENT_POSITION,
    COURSE_RATING_POSITION,
    INSTRUCTOR_COMMENT_POSITION,
    INSTRUCTOR_RATING_POSITION,
    LIKERT_BOUNDS,
    MAXIMUM_VALUE_COLUMN,
    MINIMUM_VALUE_COLUMN,
    PLATFORM_ISSUER,
    POSITION_COLUMN,
    REQUIRED_AT_MOST,
    REQUIRED_IF_AT_MOST_COLUMN,
    REQUIRED_IF_POSITION_COLUMN,
    SECTION_TABLE,
    STEP_COLUMN,
    USER_TABLE,
    WORKLOAD_BOUNDS,
    WORKLOAD_POSITION,
    SubmitWorld,
    closed_loopback_address,
    session_secret,
    shape_column,
    submit_route,
)
from fixtures.supervision import require_table
from fixtures.survey_windows import OPEN_WINDOW_FUNCTION, model_for
from sqlalchemy import insert

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


def test_the_seeded_window_is_open_according_to_the_window_service(
    submit_world: SubmitWorld,
    survey_window_service: Any,
    window_settings: Any,
    open_now: tuple[Any, Any],
) -> None:
    """`open_now` really is open, asked of the function the submit path asks.

    The ticket's Scope makes the submit route resolve "the section's open window
    (E2-06's one function)", so the question this control asks is the same
    question the path asks, of the same rows. A window that turned out to be
    closed — a naive instant coerced into the wrong zone, a term the section does
    not belong to, a `survey_window` row whose composite key silently pointed
    elsewhere — would make every accepted cell in the matrix module fail as though
    the route were refusing correct submissions.

    **A red here means the fixture is broken, not the submit path.**
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    section = world.rows.session.get(
        model_for(SECTION_TABLE), world.section[world.key_of(SECTION_TABLE)]
    )
    assert section is not None, "The seeded section could not be loaded through its mapped class."

    answered = getattr(survey_window_service, OPEN_WINDOW_FUNCTION)(
        world.rows.session, section, settings=window_settings
    )

    assert answered is not None, (
        f"`{OPEN_WINDOW_FUNCTION}` answered `None` for a section whose window runs "
        f"{world.window['opens_at']!r} to {world.window['closes_at']!r}, a day either side of "
        "now. Every accepted cell in `test_the_submit_path_answers_the_validity_matrix.py` needs "
        "this window open, and none of them could tell you it was not."
    )


def test_the_seeded_window_is_closed_once_the_fixture_closes_it(
    submit_world: SubmitWorld,
    survey_window_service: Any,
    window_settings: Any,
    open_now: tuple[Any, Any],
) -> None:
    """`close_the_window` really closes it, asked of the same function.

    The other direction, and the one the after-close resubmission test rests on:
    a `close_the_window` that wrote nothing — a wrong primary key, an update
    against the wrong table, a commit that never happened — would leave that test
    asserting a refusal that has to come from somewhere else.

    **A red here means the fixture is broken, not the submit path.**
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    world.close_the_window()
    section = world.rows.session.get(
        model_for(SECTION_TABLE), world.section[world.key_of(SECTION_TABLE)]
    )

    answered = getattr(survey_window_service, OPEN_WINDOW_FUNCTION)(
        world.rows.session, section, settings=window_settings
    )

    assert answered is None, (
        f"`{OPEN_WINDOW_FUNCTION}` still answers {answered!r} after the fixture moved the window "
        "into the past. `test_a_resubmission_after_the_window_closes_is_refused` would then be "
        "asserting a refusal that cannot be about the window."
    )


def test_the_seeded_question_set_is_spec_3_2s_five_questions(
    submit_world: SubmitWorld,
    open_now: tuple[Any, Any],
    metadata_tables: dict[str, Any],
) -> None:
    """The five questions carry §3.2's own numbers, not this fixture's convenience.

    Every value-validation test in this ticket is measured against these rows —
    ADR 0110 makes `question.minimum_value`, `maximum_value` and `step` "the only
    statement of the ranges in the system" — so a set seeded with a 0-to-100
    workload would make "3.25 is refused" and "6 is refused" assertions about
    bounds nobody chose. And a set whose five questions all came out the same
    shape (which is what the shared walker produces for an unnamed enum column)
    would make the happy path unsubmittable.

    **A red here means the fixture is broken, not the submit path.**
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    by_position = {row[POSITION_COLUMN]: row for row in world.questions.values()}

    assert sorted(by_position) == [1, 2, 3, 4, 5], (
        f"The seeded set holds questions at positions {sorted(by_position)}. SPEC §3.2 fixes five, "
        "numbered 1 to 5, and every submission body in this ticket names them by that number."
    )

    minimum, maximum, step = LIKERT_BOUNDS
    for position in (INSTRUCTOR_RATING_POSITION, COURSE_RATING_POSITION):
        row = by_position[position]
        assert (row[MINIMUM_VALUE_COLUMN], row[MAXIMUM_VALUE_COLUMN], row[STEP_COLUMN]) == (
            minimum,
            maximum,
            step,
        ), (
            f"Question {position} carries the range "
            f"{(row[MINIMUM_VALUE_COLUMN], row[MAXIMUM_VALUE_COLUMN], row[STEP_COLUMN])}; SPEC "
            f"§3.2 gives both Likert questions {minimum} to {maximum}."
        )

    workload_minimum, workload_maximum, workload_step = WORKLOAD_BOUNDS
    workload = by_position[WORKLOAD_POSITION]
    assert (
        workload[MINIMUM_VALUE_COLUMN],
        workload[MAXIMUM_VALUE_COLUMN],
        workload[STEP_COLUMN],
    ) == (workload_minimum, workload_maximum, workload_step), (
        "The workload question does not carry SPEC §3.2's 0-to-40 range in 0.5-hour steps, so "
        "the off-step and out-of-range tests are measured against bounds this fixture invented."
    )

    for comment_position, rating_position in (
        (INSTRUCTOR_COMMENT_POSITION, INSTRUCTOR_RATING_POSITION),
        (COURSE_COMMENT_POSITION, COURSE_RATING_POSITION),
    ):
        row = by_position[comment_position]
        assert (row[REQUIRED_IF_POSITION_COLUMN], row[REQUIRED_IF_AT_MOST_COLUMN]) == (
            rating_position,
            REQUIRED_AT_MOST,
        ), (
            f"Question {comment_position} carries the conditional rule "
            f"{(row[REQUIRED_IF_POSITION_COLUMN], row[REQUIRED_IF_AT_MOST_COLUMN])}; SPEC §3.2 "
            f'makes it "Required if Q{rating_position} ≤ {REQUIRED_AT_MOST}".'
        )

    found = shape_column(require_table(metadata_tables, "question"))
    if found is not None:
        name, _members = found
        shapes = {by_position[position][name] for position in (1, 2, 5)}
        assert len(shapes) == 3, (
            f"The rating, comment and workload questions carry {shapes} in `question.{name}` — "
            "fewer than three distinct values. The shared seeding walker fills an unnamed enum "
            "with the type's first member, so all five would be one shape and the happy path "
            "would be unsubmittable."
        )


def test_the_world_reader_sees_a_row_another_connection_committed(
    submit_world: SubmitWorld,
    open_now: tuple[Any, Any],
    migrated_engine: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """`rows_of` sees what the application wrote, and this is the control that says so.

    Every "nothing was stored" assertion in this ticket is `world.responses() ==
    []`, and a reader that could not see another connection's committed writes
    would satisfy all of them — against a route that stored everything. That is
    `docs/MISTAKES.md` entry 3 in its purest form: the assertion would pass for a
    reason unrelated to what it asserts, and no other test could tell.

    The probe is an `enrollment` row rather than a `response`, deliberately: it
    uses only schema that exists before E2-08, so this control is green on an
    untouched tree and a red here is about the reader rather than about a column
    the ticket has not added yet.

    **A red here means the fixture is broken, not the submit path.**
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    # Both rows the probe needs are seeded and committed on *this* fixture's own
    # connection first, so that the only thing the other connection contributes
    # is the row whose visibility is the subject.
    probe_student = world.another_student("e2-08-reader-probe")
    elsewhere = world.foreign_section()
    before = len(world.rows_of("enrollment"))

    table = require_table(metadata_tables, "enrollment")
    with migrated_engine.begin() as connection:
        connection.execute(
            insert(table).values(
                **{
                    world.link("enrollment", USER_TABLE): probe_student[world.key_of(USER_TABLE)],
                    world.link("enrollment", SECTION_TABLE): elsewhere[world.key_of(SECTION_TABLE)],
                    "started_on": datetime.now(UTC).date() - timedelta(days=1),
                    "ended_on": None,
                }
            )
        )

    after = len(world.rows_of("enrollment"))
    assert after > before, (
        f"The reader saw {before} enrollment rows before another connection committed one and "
        f"{after} afterwards. It is reading inside a snapshot that predates the write, so every "
        "'nothing was stored' assertion in this ticket would pass against a path that stored "
        "everything."
    )


# ---------------------------------------------------------------------------
# The student.
# ---------------------------------------------------------------------------


def test_the_minted_session_verifies_as_the_seeded_student(
    submit_world: SubmitWorld,
    signed_in_student: Any,
    open_submit_tool: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    configured_env: dict[str, str],
) -> None:
    """The token this suite mints is one the application's own verifier accepts.

    Read back through `verified_session` with the same secret the application was
    built from, because a token the application refuses makes every 401 test in
    this ticket pass for the wrong reason — including the one asserting that a
    *valid* student session is not refused.

    Three things are checked and each is a different way to be wrong: the token
    verifies at all (the secret matches), its role is `STUDENT` (so
    `require_student` is being given the case it must accept), and its `user_id`
    is the seeded student's (so the response the path writes belongs to the
    student this suite thinks it is).

    **A red here means the fixture is broken, not the submit path.**
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    student = signed_in_student(client, world)

    import app.services.session as session_module
    from app.services.authz import LandingRole

    claims = session_module.verified_session(student.token, session_secret(configured_env))

    assert claims is not None, (
        "`verified_session` answered `None` for the token this suite just minted, so every "
        "request it makes is an unauthenticated one and the 401 tests pass for the wrong reason. "
        "The secret comes from the same documented mapping the application was built from."
    )
    assert claims.role is LandingRole.STUDENT, (
        f"The minted session states role {claims.role!r}. `require_student` refuses anything that "
        "is not `STUDENT`, so a wrongly-roled token makes every accepted cell in this ticket "
        "unreachable."
    )
    # Compared as strings, because that is what a claim in a JWT is:
    # `issue_session` declares `user_id: str | None` and the seeded value is a
    # `uuid.UUID` out of the database (ADR 0016). Comparing the two raw is a
    # comparison between a `str` and a `UUID`, which is false for every pair
    # there is — and the coercion itself is `issue_student_session`'s, so this is
    # reading the same value back rather than repairing it here.
    assert claims.user_id == str(world.student[world.key_of(USER_TABLE)]), (
        f"The minted session carries `user_id` {claims.user_id!r} and the seeded student is "
        f"{str(world.student[world.key_of(USER_TABLE)])!r}. The submit path writes "
        "`response.user_id` from the session, so a mismatch files every response against "
        "somebody else."
    )
    assert claims.iss == PLATFORM_ISSUER, (
        f"The minted session states issuer {claims.iss!r} rather than the seeded registration's "
        f"{PLATFORM_ISSUER!r}. A path that resolves its student through the issuer and the "
        "subject rather than through `user_id` would find nobody."
    )


# ---------------------------------------------------------------------------
# The addresses.
# ---------------------------------------------------------------------------


def test_the_unreachable_address_refuses_a_connection() -> None:
    """A closed loopback port really refuses, and it refuses quickly.

    ADR 0056's unreachable row is asserted against this address, and an address
    that something happened to be listening on would turn that test into an
    assertion about whatever answered. The refusal has to be prompt as well as
    certain: the broker half of `docs/MISTAKES.md` entry 41's near miss measures
    a 2.5-second budget against a background of *instant* refusal, and a slow one
    would eat the margin the measurement depends on.

    **A red here means the fixture is broken, not the submit path.**
    """
    import socket

    host, port = closed_loopback_address().split(":")
    started = datetime.now(UTC)
    with pytest.raises(OSError), socket.create_connection((host, int(port)), timeout=2):
        pass
    elapsed = datetime.now(UTC) - started

    assert elapsed < timedelta(seconds=1), (
        f"The closed port took {elapsed} to refuse a connection. Both the unreachable-provider "
        "test and the broker-down budget measurement assume an immediate refusal; a slow one "
        "makes the second of them measure the network rather than the handler."
    )


# ---------------------------------------------------------------------------
# NOT a control. This one is expected red until the route lands, and it is here
# so that an absent deliverable is one legible failure rather than thirty.
# ---------------------------------------------------------------------------


def test_the_submit_route_is_the_one_post_route_the_student_api_defines(
    open_submit_tool: Any,
    mock_ai_endpoint: Any,
) -> None:
    """`app.api.student` defines exactly one `POST` route, registered on the application.

    E2-08's work order settles the module and settles no URL, so this is how every
    other test in this ticket addresses the route: it finds the one POST endpoint
    that module defines. Two things have to hold for that to work, and each is a
    different missing piece — the module exists and defines the route, and
    `app.main.create_app` registers its router "beside the others".

    **This is not a control and it will be red until the route lands.** It is
    written separately so that "E2-08 is not built" reads as one failure with a
    name rather than as every submission test failing on a 404.
    """
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    path = submit_route(client)

    assert path.startswith("/"), (
        f"The submit route's path is {path!r}, which is not an absolute path and cannot be "
        "requested."
    )
