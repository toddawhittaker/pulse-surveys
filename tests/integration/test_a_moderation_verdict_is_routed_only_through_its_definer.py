"""A moderation verdict and its route land together, through one door — E6-01.

The work order's decisions 2, 3 and 9, and the ticket's criteria 4, 5 and 6:

  - **One writer.** `public.route_moderation_verdict(answer_id, verdict,
    prompt_version, model_id) RETURNS uuid` writes the `MODERATION`
    classification row and its route in one statement's transaction — a
    `FLAGGED_COLLAPSED` row in `moderation_state` for harmful or privacy, a
    `threat_case` row for threat or self-harm (unique per answer: a second
    Care-class verdict leaves the open case alone, with no error), nothing more
    for clear or nonsense. Owned by the NOLOGIN role `pulse_moderation_definer`;
    `pulse_app` holds `EXECUTE` on it.
  - **Verdict and route land together** (criterion 5): a call whose route fails
    leaves neither the verdict nor the route; and `pulse_app` cannot insert into
    `moderation_state` or `threat_case` directly — asserted on the connection
    production uses (`docs/MISTAKES.md` entry 46).
  - **The verdict check is per task** (criterion 6): a `MODERATION` row with a
    validity verdict, and a validity row with a moderation verdict, are both
    refused by the database.
  - **One test walks the whole of it as `pulse_app`** — the definer, the view and
    a later `clear` that publishes nothing — because a suite that drives these
    through the migrating engine has not tested a grant at all (entry 46).

**Every call through the door here is made on `application_session`**, which is a
real `pulse_app` login on the application engine (`tests/fixtures/authz_data.py`),
except where a test has to stand a failing route up first: that one runs in
`db_session`'s transaction as `pulse_app` by `SET ROLE`, so the trigger it plants
is rolled back with it. Rows are seeded and read back on the bootstrap connection,
the only one that can see `threat_case` at all.

**Every refusal is a refused statement with its SQLSTATE**, never an empty
result, and every refusal sits beside an accepted control on the same connection
(`docs/MISTAKES.md` entries 3 and 35).

**How a red reads before E6-01 lands.** Each test calls
`require_routing_function` (or `require_definer_role`, `require_threat_case`) as
its first statement, so a missing deliverable is a FAILED naming it
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.care_subject import plant_a_comment_answer
from fixtures.moderation import (
    CARE_CLASS,
    CLEAR,
    EVERY_VERDICT,
    FLAGGED_COLLAPSED,
    FLAGGING,
    HARMFUL,
    MODERATION_DEFINER_ROLE,
    MODERATION_TASK,
    ROUTE_VERDICT,
    ROUTING_ARGUMENT_TYPES,
    ROUTING_CALL,
    ROUTING_FUNCTION,
    SEED_MODEL_ID_NAME,
    SEED_PROMPT_VERSION_NAME,
    SEED_PROVENANCE,
    SELF_HARM,
    SUBSTANTIVE,
    THREAT,
    UNMODERATED,
    VALIDITY_TASK,
    moderation_states,
    moderation_verdicts,
    named_in_moderation,
    plant_verdict,
    require_definer_role,
    require_routing_function,
    require_threat_case,
    threat_cases,
)
from fixtures.report_comments import CommentWorld, comment_view_rows
from fixtures.report_views import INSTRUCTOR_STREAM
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

APPLICATION_ROLE = "pulse_app"
CARE_ROLE = "pulse_care"
INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
CURRENT_ROLE = "SELECT current_user"

# The provenance a test hands the door, so that "the row carries what the caller
# named" is a measurement rather than two copies of the seed constant.
A_PROMPT_VERSION = "e6-01-routing-test-prompt-v1"
A_MODEL_ID = "e6-01-routing-test-model"

# A row of `classification` written directly, for the per-task check. Every column
# the table carries except its generated key
# (`tests/integration/test_identity_column_marker.py` records them).
CLASSIFICATION_INSERT = (
    "INSERT INTO public.classification "
    "(answer_id, task, verdict, prompt_version, model_id, classified_at) VALUES "
    "(CAST(:answer AS uuid), CAST(:task AS text), CAST(:verdict AS text), "
    "CAST(:prompt_version AS text), CAST(:model_id AS text), now())"
)

# The definer's own catalog entry.
THE_FUNCTION = """
    SELECT p.prosecdef AS security_definer,
           r.rolname AS owner,
           r.rolsuper AS owner_is_superuser,
           r.rolcanlogin AS owner_can_log_in,
           coalesce(p.proconfig, ARRAY[]::text[]) AS settings,
           format_type(p.prorettype, NULL) AS returns,
           array(
               SELECT format_type(a.argtype, NULL)
               FROM unnest(p.proargtypes::oid[]) WITH ORDINALITY AS a(argtype, idx)
               ORDER BY a.idx
           ) AS argument_types
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    JOIN pg_roles r ON r.oid = p.proowner
    WHERE n.nspname = 'public' AND p.proname = :name
"""

# A trigger function that refuses every row, stood up on a route table for the one
# test that needs the route to fail after the verdict is written. Created inside
# `db_session`'s transaction and rolled back with it; the name is this ticket's so
# nothing else in the schema can collide with it.
A_FAILING_ROUTE = "e6_01_a_route_that_fails"
STAND_UP_A_FAILING_ROUTE = f"""
    CREATE FUNCTION public.{A_FAILING_ROUTE}() RETURNS trigger LANGUAGE plpgsql AS $body$
    BEGIN
        RAISE EXCEPTION 'e6-01: the route was made to fail after the verdict';
    END
    $body$
"""


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def attempted(session: Any, statement: str, parameters: dict[str, Any] | None = None) -> Any:
    """Run `statement` in a savepoint that is **always** rolled back; answer its error or `None`."""
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters or {})
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


def kept_if_accepted(session: Any, statement: str, parameters: dict[str, Any]) -> Any:
    """Run `statement` in a savepoint kept on success and undone on failure; answer the error."""
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters)
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.commit()
    return None


def route(session: Any, answer_id: Any, verdict: str) -> Any:
    """Call the door on `session` and commit; answer the error it raised, or `None`.

    The function's return value is deliberately not handed back: every test here
    asserts the rows a call left, never what it answered (`docs/MISTAKES.md`
    entry 49).
    """
    try:
        session.execute(
            text(ROUTING_CALL),
            {
                "answer_id": str(answer_id),
                "verdict": verdict,
                "prompt_version": A_PROMPT_VERSION,
                "model_id": A_MODEL_ID,
            },
        )
    except DatabaseError as failure:
        session.rollback()
        return failure
    session.commit()
    return None


def require_the_application_role(session: Any) -> None:
    """The session really is `pulse_app`, or every assertion below measures somebody else."""
    current = session.execute(text(CURRENT_ROLE)).scalar_one()
    assert current == APPLICATION_ROLE, (
        f"`application_session` connects as {current!r}, not `{APPLICATION_ROLE}`. Every claim "
        "this module makes is about the role production runs as (`docs/MISTAKES.md` entry 46), "
        "and a superuser passes every one of them."
    )


def fresh(committed_rows: Any) -> Any:
    """The bootstrap session, with its snapshot ended so it sees what other connections committed."""
    committed_rows.session.rollback()
    return committed_rows.session


class acting_as:  # noqa: N801 — a context manager used as a statement, not a type
    """`SET ROLE` for the block on a bootstrap session, and back again."""

    def __init__(self, session: Any, role: str) -> None:
        self.session = session
        self.role = role

    def __enter__(self) -> "acting_as":
        self.session.execute(text(f'SET ROLE "{self.role}"'))
        current = self.session.execute(text(CURRENT_ROLE)).scalar_one()
        assert current == self.role, f"`SET ROLE {self.role}` left `current_user` as {current!r}."
        return self

    def __exit__(self, *exception: Any) -> None:
        self.session.execute(text("RESET ROLE"))


# ---------------------------------------------------------------------------
# What each verdict routes to — on the application connection.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", EVERY_VERDICT)
def test_each_verdict_lands_with_exactly_its_own_route_through_the_application_connection(
    verdict: str, application_session: Any, committed_rows: Any
) -> None:
    """Decision 2, one case per verdict, called as `pulse_app`.

    One comment with no verdict, one call through the door on the connection
    production uses, then the rows:

      - **the verdict**: exactly one `MODERATION` classification row for the
        answer, carrying the verdict token and the prompt version and model id the
        caller named (SPEC §7.4: every classification stores both);
      - **the route**: one `FLAGGED_COLLAPSED` `moderation_state` row for harmful
        and privacy and none otherwise; one `threat_case` row naming that
        classification for threat and self-harm and none otherwise.

    **A case per verdict**, because a door that routed five of six correctly passes
    every test that plants one of the five, and the failure should name the sixth.

    **The mutations this kills:** a verdict written with no route; a route for the
    wrong class (a case for harmful, a flag for threat — the second shows a
    self-harm disclosure to an instructor as a collapsed chip); `nonsense` routed as
    a flag; a provenance pair dropped or replaced with a constant; and a door
    `pulse_app` may not execute (refused for privilege on every case).
    """
    require_routing_function(committed_rows.session)
    require_threat_case(committed_rows.tables)
    require_the_application_role(application_session)
    planted = plant_a_comment_answer(committed_rows, verdict=UNMODERATED)

    failure = route(application_session, planted.answer_id, verdict)
    assert failure is None, (
        f"Routing a {verdict!r} verdict on `{APPLICATION_ROLE}` was refused: {failure} (SQLSTATE "
        f"{sqlstate(failure)}). E6-01's work order gives `{APPLICATION_ROLE}` `EXECUTE` on "
        f"`public.{ROUTING_FUNCTION}`; every fixture, seed and sweep writes verdicts through it."
    )

    session = fresh(committed_rows)
    verdicts = moderation_verdicts(session, planted.answer_id)
    assert [(row["verdict"], row["prompt_version"], row["model_id"]) for row in verdicts] == [
        (verdict, A_PROMPT_VERSION, A_MODEL_ID)
    ], (
        f"After one call routing {verdict!r}, the answer carries the moderation verdicts "
        f"{[(row['verdict'], row['prompt_version'], row['model_id']) for row in verdicts]}. One "
        "call writes one `MODERATION` row, with the verdict and the provenance the caller named."
    )

    states = [row["state"] for row in moderation_states(session, planted.answer_id)]
    expected_states = [FLAGGED_COLLAPSED] if verdict in FLAGGING else []
    assert states == expected_states, (
        f"A {verdict!r} verdict left the moderation states {states}; decision 2 says "
        f"{expected_states}. A flag is what puts a harmful or privacy comment in front of a "
        "reviewer; a flag on any other verdict hides a comment nobody needs to review, or shows a "
        "Care-class one to an instructor as a chip."
    )

    cases = threat_cases(session, planted.answer_id)
    if verdict in CARE_CLASS:
        assert [row["classification_id"] for row in cases] == [verdicts[0]["id"]], (
            f"A {verdict!r} verdict left the cases {cases}; decision 2 opens exactly one, naming "
            f"the classification that routed it ({verdicts[0]['id']}). Without it the comment is "
            "hidden from every instructor and read by nobody (SPEC §6.2, ruling 5)."
        )
    else:
        assert cases == [], f"A {verdict!r} verdict opened a Care case: {cases}."


def test_a_second_care_class_verdict_leaves_the_open_case_alone(
    application_session: Any, committed_rows: Any
) -> None:
    """Decision 2: `threat_case` is unique per answer, and a second Care-class verdict is no error.

    `threat` is routed, then `self_harm` on the same comment, both as `pulse_app`.
    The second call succeeds, both verdicts are stored, and there is still exactly
    one case — naming the first verdict, because the case was opened by it and the
    second leaves it alone.

    **The mutations this kills:** a second case for one comment (E10's queue would
    show one student twice); the second call refused by the unique index (a re-run
    of moderation would fail every time on any comment already routed to Care, and
    — since nothing commits a verdict without its route — the second verdict would
    be lost with it); and the case re-pointed at the newer verdict.
    """
    require_routing_function(committed_rows.session)
    require_threat_case(committed_rows.tables)
    planted = plant_a_comment_answer(committed_rows, verdict=UNMODERATED)

    first = route(application_session, planted.answer_id, THREAT)
    assert first is None, f"The first Care-class verdict was refused: {first}."
    second = route(application_session, planted.answer_id, SELF_HARM)
    assert second is None, (
        f"A second Care-class verdict on a comment that already has a case was refused: {second} "
        f"(SQLSTATE {sqlstate(second)}). Decision 2: the existing case is left alone, with no error."
    )

    session = fresh(committed_rows)
    verdicts = moderation_verdicts(session, planted.answer_id)
    assert sorted(row["verdict"] for row in verdicts) == sorted([THREAT, SELF_HARM]), (
        f"The comment holds {sorted(row['verdict'] for row in verdicts)} after two calls; both "
        "verdicts are kept (`classification` is append-only)."
    )
    threat_row = next(row for row in verdicts if row["verdict"] == THREAT)
    cases = threat_cases(session, planted.answer_id)
    assert [row["classification_id"] for row in cases] == [threat_row["id"]], (
        f"The comment has the cases {cases}. Exactly one, opened by the first verdict "
        f"({threat_row['id']}) and left alone by the second."
    )


@pytest.mark.parametrize("verdict", [HARMFUL, THREAT], ids=["flag-route", "care-route"])
def test_a_call_whose_route_fails_leaves_neither_the_verdict_nor_the_route(
    verdict: str, db_session: Any, seed_rows: Any
) -> None:
    """Criterion 5: "A definer call that fails after the verdict is written leaves neither."

    The route table this verdict writes to is made to refuse every insert, by a
    trigger this test stands up inside its own transaction. Then the door is called
    as `pulse_app`. Whatever order the body writes in, the route's insert fails;
    because the verdict and the route are one call, the verdict must go with it.

    **Asserted on the rows, not on the call's answer.** A body that swallowed the
    route's failure in an `EXCEPTION` block would answer success — the call is
    then *kept*, and the verdict row it left is what fails this test.

    **The mutations this kills:** an `EXCEPTION WHEN OTHERS` around the route
    insert (a threat verdict with no case: hidden from everyone, read by no one);
    a route insert written `ON CONFLICT DO NOTHING` against the wrong conflict
    target, which also answers success; and a verdict written by a separate call
    before the route.

    **The pair** is `test_each_verdict_lands_with_exactly_its_own_route_...`, where
    nothing is planted and both halves land.
    """
    require_routing_function(db_session)
    route_table = "moderation_state" if verdict in FLAGGING else "threat_case"
    answer = seed_rows("answer", {}, comment_text="e6-01 a comment whose route will fail")

    db_session.execute(text(STAND_UP_A_FAILING_ROUTE))
    db_session.execute(
        text(
            f"CREATE TRIGGER {A_FAILING_ROUTE} BEFORE INSERT ON public.{route_table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{A_FAILING_ROUTE}()"
        )
    )

    with acting_as(db_session, APPLICATION_ROLE):
        kept_if_accepted(
            db_session,
            ROUTING_CALL,
            {
                "answer_id": str(answer["id"]),
                "verdict": verdict,
                "prompt_version": A_PROMPT_VERSION,
                "model_id": A_MODEL_ID,
            },
        )

    left = moderation_verdicts(db_session, answer["id"])
    assert left == [], (
        f"The route for a {verdict!r} verdict could not be written (`{route_table}` refused every "
        f"insert) and the verdict was kept anyway: {left}. Criterion 5: verdict and route land "
        "together. A threat verdict with no case is a student at risk hidden from every instructor "
        "and read by nobody."
    )
    assert moderation_states(db_session, answer["id"]) == []
    assert threat_cases(db_session, answer["id"]) == []


def test_the_application_connection_is_refused_a_direct_write_to_either_route_table(
    application_session: Any, committed_rows: Any
) -> None:
    """Criterion 5's second half, on the connection production uses (entry 46).

    `pulse_app` may write a route only by calling the door. So on its own login:

      - `INSERT`, `UPDATE` and `DELETE` on `moderation_state` are refused with 42501;
      - `INSERT` on `threat_case` is refused with 42501 — and so is a bare
        `SELECT`, because the application connection holds no privilege on it at
        all (`RUNTIME_BASE_TABLE_PRIVILEGES` in `test_identity_grants.py`);
      - **the controls**: the same connection reads `moderation_state` and inserts a
        `COMMENT_VALIDITY` classification row, both of which it certainly may
        (`docs/MISTAKES.md` entry 35) — so the refusals are about the two tables,
        not about a connection that can do nothing.

    Every statement runs in a savepoint that is rolled back whatever happens.

    **The mutations this kills:** `GRANT INSERT ON moderation_state` or `ON
    threat_case` to `pulse_app` (a route written with no verdict, or a case nobody's
    verdict opened); `GRANT SELECT ON threat_case` (an instructor's connection able
    to count Care cases).
    """
    require_threat_case(committed_rows.tables)
    require_the_application_role(application_session)
    planted = plant_a_comment_answer(committed_rows, verdict=UNMODERATED)
    answer = {"answer": str(planted.answer_id)}

    readable = attempted(application_session, "SELECT count(*) FROM public.moderation_state")
    assert readable is None, (
        f"`{APPLICATION_ROLE}` could not read `moderation_state` ({readable}); E4-06 granted it "
        "`SELECT` and the read path needs it. Until this control holds, the refusals below may be a "
        "connection that can do nothing."
    )
    appended = attempted(
        application_session,
        CLASSIFICATION_INSERT,
        {
            **answer,
            "task": VALIDITY_TASK,
            "verdict": SUBSTANTIVE,
            "prompt_version": A_PROMPT_VERSION,
            "model_id": A_MODEL_ID,
        },
    )
    assert appended is None, (
        f"`{APPLICATION_ROLE}` could not append a validity verdict ({appended}); the submit path "
        "does that on this connection."
    )

    statements = {
        "insert into moderation_state": (
            "INSERT INTO public.moderation_state (answer_id, state) "
            "VALUES (CAST(:answer AS uuid), 'FLAGGED_COLLAPSED')"
        ),
        "update moderation_state": (
            "UPDATE public.moderation_state SET state = 'FLAGGED_COLLAPSED'"
        ),
        "delete from moderation_state": "DELETE FROM public.moderation_state",
        "insert into threat_case": (
            "INSERT INTO public.threat_case (answer_id, classification_id, opened_at) "
            "VALUES (CAST(:answer AS uuid), CAST(:classification AS uuid), now())"
        ),
        "select from threat_case": "SELECT count(*) FROM public.threat_case",
    }
    parameters = {**answer, "classification": str(uuid4())}
    answered = {
        name: attempted(application_session, statement, parameters)
        for name, statement in statements.items()
    }
    not_refused = {
        name: (failure, sqlstate(failure))
        for name, failure in answered.items()
        if failure is None or sqlstate(failure) != INSUFFICIENT_PRIVILEGE
    }
    assert not not_refused, (
        f"On `{APPLICATION_ROLE}`, these were not refused with {INSUFFICIENT_PRIVILEGE}: "
        f"{not_refused}. The routing definer is the only writer of both tables (E6-01 work order, "
        "decision 2), and `threat_case` is read by nobody until E10's Care queue."
    )


# ---------------------------------------------------------------------------
# The per-task verdict check.
# ---------------------------------------------------------------------------


def test_the_verdict_check_is_per_task_in_both_directions(db_session: Any, seed_rows: Any) -> None:
    """Criterion 6: each task takes only its own vocabulary, refused by the database.

    Four inserts of one answer's classification, each the only difference from its
    pair:

      - `MODERATION` with `clear` — accepted; `MODERATION` with `substantive` —
        refused with 23514. Both written as `pulse_moderation_definer`, the one role
        the trigger lets write a moderation row, so the trigger is not what decides
        either and only the check can refuse the second.
      - `COMMENT_VALIDITY` with `substantive` — accepted; `COMMENT_VALIDITY` with
        `threat` — refused with 23514.

    `nonsense` is in both vocabularies (SPEC §3.3 and §7.4) and is deliberately not
    a crossing case: refusing it either way would be a defect.

    **The mutations this kill:** one `CHECK` over the union of the two
    vocabularies (both crossings accepted); a `CHECK` that ignores the task; and the
    moderation tokens added to the validity check rather than to their own.
    """
    require_definer_role(db_session)
    answer = seed_rows("answer", {}, comment_text="e6-01 a comment the per-task check is about")

    def row(task: str, verdict: str) -> dict[str, Any]:
        return {
            "answer": str(answer["id"]),
            "task": task,
            "verdict": verdict,
            "prompt_version": A_PROMPT_VERSION,
            "model_id": A_MODEL_ID,
        }

    insert = CLASSIFICATION_INSERT
    with acting_as(db_session, MODERATION_DEFINER_ROLE):
        moderation_accepted = attempted(db_session, insert, row(MODERATION_TASK, CLEAR))
        moderation_crossing = attempted(db_session, insert, row(MODERATION_TASK, SUBSTANTIVE))
    validity_accepted = attempted(db_session, insert, row(VALIDITY_TASK, SUBSTANTIVE))
    validity_crossing = attempted(db_session, insert, row(VALIDITY_TASK, THREAT))

    assert moderation_accepted is None, (
        f"A `MODERATION` row with {CLEAR!r}, written by the door's owner, was refused: "
        f"{moderation_accepted} (SQLSTATE {sqlstate(moderation_accepted)}). Until it is accepted, "
        "the refusal of its crossing pair cannot be attributed to the verdict check."
    )
    assert (
        validity_accepted is None
    ), f"A `COMMENT_VALIDITY` row with {SUBSTANTIVE!r} was refused: {validity_accepted}."
    assert sqlstate(moderation_crossing) == CHECK_VIOLATION, (
        f"A `MODERATION` row carrying the validity verdict {SUBSTANTIVE!r} was answered "
        f"{moderation_crossing!r} (SQLSTATE {sqlstate(moderation_crossing)}), not refused by a check "
        f"({CHECK_VIOLATION}). The verdict check is per task (E6-01 criterion 6), built from the "
        "enums the way the validity check is."
    )
    assert sqlstate(validity_crossing) == CHECK_VIOLATION, (
        f"A `COMMENT_VALIDITY` row carrying the moderation verdict {THREAT!r} was answered "
        f"{validity_crossing!r} (SQLSTATE {sqlstate(validity_crossing)}), not refused by a check "
        f"({CHECK_VIOLATION}). A validity row that says `threat` routes nothing and counts toward "
        "nobody's credit — the database is where that is refused."
    )


# ---------------------------------------------------------------------------
# The door itself: its owner, its shape, and who may open it.
# ---------------------------------------------------------------------------


def test_the_door_is_a_definer_owned_by_its_own_nologin_role(committed_rows: Any) -> None:
    """Decision 2's shape, from the catalog: the `teaching_grant_end_v001.sql` pattern (ADR 0043).

    `SECURITY DEFINER`; owned by `pulse_moderation_definer`, which is neither a
    superuser nor able to log in; `search_path` pinned, so a caller cannot shadow a
    relation the body names (`docs/MISTAKES.md` entry 17); one function of the name
    (an overload is a second way in); `(uuid, text, text, text)` in and `uuid` out.

    **The mutations this kill:** `SECURITY INVOKER` (the caller would then need the
    route grants `pulse_app` must not hold); the function owned by the migration
    superuser or by another door's owner; no `search_path`; a changed signature.
    """
    require_routing_function(committed_rows.session)
    found = (
        committed_rows.session.execute(text(THE_FUNCTION), {"name": ROUTING_FUNCTION})
        .mappings()
        .all()
    )
    assert len(found) == 1, (
        f"`public` declares {len(found)} functions called `{ROUTING_FUNCTION}`; an overload is a "
        "second way in."
    )
    function = found[0]
    assert function["security_definer"], f"`{ROUTING_FUNCTION}` is not `SECURITY DEFINER`."
    assert function["owner"] == MODERATION_DEFINER_ROLE, (
        f"`{ROUTING_FUNCTION}` is owned by {function['owner']!r}, not `{MODERATION_DEFINER_ROLE}` "
        "(work order decision 2)."
    )
    assert not function["owner_is_superuser"] and not function["owner_can_log_in"], (
        f"The owner {function['owner']!r} is a superuser or can log in; a definer's owner exists "
        "for nothing but its door."
    )
    assert any(
        setting.startswith("search_path=") for setting in function["settings"]
    ), f"`{ROUTING_FUNCTION}` pins no `search_path` (its settings are {list(function['settings'])})."
    assert list(function["argument_types"]) == ROUTING_ARGUMENT_TYPES, (
        f"`{ROUTING_FUNCTION}` takes {list(function['argument_types'])}; the work order settles "
        "`(answer_id uuid, verdict text, prompt_version text, model_id text)`."
    )
    assert function["returns"] == "uuid", (
        f"`{ROUTING_FUNCTION}` returns {function['returns']}; the work order settles the new "
        "classification's id."
    )


def test_the_care_role_may_not_route_a_verdict(
    committed_rows: Any, application_session: Any
) -> None:
    """The door is `pulse_app`'s: `pulse_care` is refused it, with the control beside it.

    Postgres grants `EXECUTE` on a new function to `PUBLIC` unless the migration
    revokes it, and `PUBLIC` includes the Care role. Asserted as a refused call with
    SQLSTATE 42501, every argument a typed NULL so that a missing function (42883)
    cannot stand in for the refusal. **The control:** the same call on `pulse_app`
    is not refused for privilege.

    **The mutation this kills:** the migration's `REVOKE ALL … FROM PUBLIC` left out.
    """
    require_routing_function(committed_rows.session)
    nulls = {"answer_id": None, "verdict": None, "prompt_version": None, "model_id": None}

    allowed = attempted(application_session, ROUTING_CALL, nulls)
    assert allowed is None or sqlstate(allowed) != INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}` was refused `EXECUTE` on the routing definer ({allowed}), so the Care "
        "refusal below would be satisfied by a door nobody may open."
    )

    session = fresh(committed_rows)
    session.execute(text(f'SET ROLE "{CARE_ROLE}"'))
    try:
        assert session.execute(text(CURRENT_ROLE)).scalar_one() == CARE_ROLE
        refusal = attempted(session, ROUTING_CALL, nulls)
    finally:
        session.rollback()
        session.execute(text("RESET ROLE"))
    assert refusal is not None and sqlstate(refusal) == INSUFFICIENT_PRIVILEGE, (
        f"`{CARE_ROLE}` called the routing definer and was answered {refusal!r} (SQLSTATE "
        f"{sqlstate(refusal)}). `REVOKE ALL ON FUNCTION … FROM PUBLIC` is the line whose absence "
        "produces this."
    )


# ---------------------------------------------------------------------------
# The seed provenance every fixture plants under.
# ---------------------------------------------------------------------------


def test_a_planted_verdict_carries_the_seed_provenance_the_work_order_names(
    db_session: Any, seed_rows: Any
) -> None:
    """Decision 4: fixtures and seeds plant through `route_verdict`, under a provenance that says "seed".

    `app.services.moderation` exposes `route_verdict`, `SEED_PROMPT_VERSION` and
    `SEED_MODEL_ID`, and both constants are `"seed"` — a prompt version a real
    prompt never has, so a seeded verdict can never be mistaken for a model's in an
    eval or a drift panel (SPEC §6.1, §7.4). One verdict is planted the way every
    world in this suite plants one, and the row it left is read back.

    **The mutations this kill:** a constant set to a real prompt version (a seeded
    verdict indistinguishable from a model's); `route_verdict` ignoring the
    provenance it is handed and stamping a constant of its own; and `route_verdict`
    writing the row itself rather than through the definer, which the trigger
    refuses (the bootstrap session used here is not the door's owner).
    """
    assert named_in_moderation(SEED_PROMPT_VERSION_NAME) == SEED_PROVENANCE, (
        f"`{SEED_PROMPT_VERSION_NAME}` is {named_in_moderation(SEED_PROMPT_VERSION_NAME)!r}; the work "
        f"order (decision 4) settles {SEED_PROVENANCE!r}."
    )
    assert named_in_moderation(SEED_MODEL_ID_NAME) == SEED_PROVENANCE, (
        f"`{SEED_MODEL_ID_NAME}` is {named_in_moderation(SEED_MODEL_ID_NAME)!r}; the work order "
        f"(decision 4) settles {SEED_PROVENANCE!r}."
    )
    assert callable(named_in_moderation(ROUTE_VERDICT))

    answer = seed_rows("answer", {}, comment_text="e6-01 a comment a fixture plants a verdict on")
    plant_verdict(db_session, answer["id"], CLEAR)

    rows = moderation_verdicts(db_session, answer["id"])
    assert [(row["verdict"], row["prompt_version"], row["model_id"]) for row in rows] == [
        (CLEAR, SEED_PROVENANCE, SEED_PROVENANCE)
    ], (
        f"A verdict planted through `{ROUTE_VERDICT}` under the seed provenance left "
        f"{[(row['verdict'], row['prompt_version'], row['model_id']) for row in rows]}."
    )


# ---------------------------------------------------------------------------
# The whole of it, as `pulse_app`: the definer, the trigger's sibling, and the view.
# ---------------------------------------------------------------------------


def test_the_view_shows_a_comment_once_its_verdict_lands_and_never_after_a_care_class_one(
    application_session: Any, committed_rows: Any, committed_comment_world: CommentWorld
) -> None:
    """Entry 46, end to end: `report_comment` v004 read on `pulse_app`, verdicts routed on `pulse_app`.

    Three comments in one closed week, committed. One holds a `clear` verdict
    planted by the world (the control: the view is readable on this connection and
    returns verdicted comments). Two hold none. On `pulse_app`'s own login:

      1. the view returns the control and neither of the other two — a comment with
         no verdict is not in the view (v004's first condition);
      2. `clear` is routed for one and `threat` for the other, through the door, on
         the same connection; the view now returns the control and the `clear` one,
         and not the `threat` one (v004's second condition);
      3. a later `clear` is routed for the `threat` one; the view still does not
         return it — "never when any of its verdicts, ever, is threat or self-harm".

    The view is a database object read on the production connection, so what it
    returns there is what every reader built on it can return
    (`docs/MISTAKES.md` entry 46 — the migrating engine passes every grant).

    **The mutations this kills:** v004's verdict condition left out (step 1); its
    Care-class condition left out (step 2); the Care-class condition written over
    the latest verdict (step 3); and `pulse_app` lacking `EXECUTE` on the door or
    `SELECT` on the view (every step).
    """
    require_routing_function(committed_rows.session)
    require_the_application_role(application_session)
    world = committed_comment_world
    world.build()
    week = 7
    world.close_week(week)
    control = "e6-01 the control comment, verdicted by the world"
    later_clear = "e6-01 a comment whose clear verdict lands later"
    later_threat = "e6-01 a comment whose threat verdict lands later"
    world.submit(term_week=week, comments={INSTRUCTOR_STREAM: control})
    _, to_clear = world.submit(
        term_week=week,
        comments={INSTRUCTOR_STREAM: later_clear},
        moderation={INSTRUCTOR_STREAM: UNMODERATED},
    )
    _, to_threat = world.submit(
        term_week=week,
        comments={INSTRUCTOR_STREAM: later_threat},
        moderation={INSTRUCTOR_STREAM: UNMODERATED},
    )
    committed_rows.commit()
    section_id = world.section_id()

    def shown() -> set[str]:
        application_session.rollback()
        return {
            str(row["comment_text"])
            for row in comment_view_rows(application_session, section_id=section_id)
        }

    before = shown()
    assert control in before, (
        f"The view, read on `{APPLICATION_ROLE}`, does not return the comment the world verdicted "
        f"`clear` (it returned {sorted(before)}). Until it does, every absence below is a view that "
        "returns nothing on this connection."
    )
    assert later_clear not in before and later_threat not in before, (
        f"The view returns a comment that holds no moderation verdict: {sorted(before)}. v004 shows "
        "a comment only once it holds one (E6-01 criterion 1)."
    )

    answer_key = world.key_of("answer")
    cleared = route(application_session, to_clear[INSTRUCTOR_STREAM][answer_key], CLEAR)
    threatened = route(application_session, to_threat[INSTRUCTOR_STREAM][answer_key], THREAT)
    assert (
        cleared is None and threatened is None
    ), f"Routing on `{APPLICATION_ROLE}` was refused: clear {cleared}, threat {threatened}."
    after = shown()
    assert later_clear in after, (
        f"A `clear` verdict landed through the door and the view still does not return the comment "
        f"(it returned {sorted(after)})."
    )
    assert later_threat not in after, (
        "The view returns a comment holding a `threat` verdict: SPEC §6.2 suppresses it from all "
        "instructor and leadership views, and every one of them reads this view."
    )

    relabelled = route(application_session, to_threat[INSTRUCTOR_STREAM][answer_key], CLEAR)
    assert relabelled is None, f"A later `clear` on the threat comment was refused: {relabelled}."
    finally_shown = shown()
    assert later_clear in finally_shown, "The `clear` comment left the view after a later call."
    assert later_threat not in finally_shown, (
        "A later `clear` verdict put a comment that once held `threat` back into the view. E6-01: "
        "never when any of its verdicts, ever, is threat or self-harm."
    )
