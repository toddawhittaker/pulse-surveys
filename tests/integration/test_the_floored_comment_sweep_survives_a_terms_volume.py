"""E2-16 criterion 3 — the sweep's anti-join, and what it must go on selecting.

> The sweep's two legs contain no `NOT IN` anti-join; a plan-shape or
> statement-count test pins the rewrite, and the new index exists.

The epic-boundary data-model review measured `app/services/validity.py`'s
re-classification sweep at a term's volume. Both legs — the judged one and the
floored one — are `NOT IN` anti-joins, which the planner runs as a hashed subplan
until the hash outgrows the 4MB default `work_mem` and then rescans
`classification` once per outer row: **72 seconds at ~300k rows**, 46 with a
supporting index, 166ms with the anti-join written in a shape the planner can
always run. The sweep is enqueued per floored submission
(`app/api/student.py`) and again on a beat (`app/jobs/schedules.py`), so it fires
hardest during a provider outage — exactly when floored rows accumulate.

**The shape is read off the wire, not off the source.** What matters is the SQL
the server was sent, which is where a `NOT IN` costs what it costs; a statement
compiled in a test would be a different object from the one the sweep executes,
and a service that built its query somewhere this module did not look would pass.
`tests/fixtures/statements.py` records every statement any engine sends while the
sweep runs, and the sweep runs in this process through the wrapper E2-08 put in
`app/jobs/tasks.py`.

**The rewrite has to keep selecting the same rows, and that is the other test
here.** A shape assertion on its own is satisfied by a leg that selects nothing —
which would be a sweep that never re-runs anything, invisible in production until
a term's floored comments were never judged. So the equivalence half seeds the
three shapes a `classification` row comes in — a floored verdict naming a
comment, a model's verdict naming a comment, and a bounce naming none — and
requires the sweep to pick up exactly the first. That test is **green today** and
is here to stay green across the rewrite: it is the regression guard, not the
red.

**The index this criterion also asks for is asserted next door**, in
`tests/integration/test_the_sweep_and_week_axis_indexes.py`, against the migrated
catalog. Two tests of one rule would be `docs/MISTAKES.md` entry 19's shape, and
an index is a fact about the database rather than about a call.

**The three submissions are made by three students of one section.** SPEC §8
allows one response per student per section per week, so three comments in three
states need three students; `SubmitWorld.another_student` is what E2-08 left for
it. The mock provider's behaviour is selected by a marker inside each comment,
read from the mock's own served rules (`GET /mock/rules`) rather than copied.
"""

from typing import Any

import pytest
from fixtures.statements import anti_joins, statements_recorded
from fixtures.submit import (
    ANSWER_ID_COLUMN,
    ANSWER_TABLE,
    CLASSIFICATION_TABLE,
    RESPONSE_TABLE,
    SUBSTANTIVE_COMMENT,
    USER_TABLE,
    SubmitWorld,
    a_valid_submission,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration

# The mock's selector for a provider that says it cannot serve now. ADR 0056 puts
# HTTP 503 inside SPEC §3.3's fail-open floor, so a comment carrying this marker
# is accepted and stored with a floored classification — the row the sweep exists
# to come back to.
UNAVAILABLE_SELECTOR = "503"

# The mock's selector for a verdict of `insufficient`, which §3.3 bounces before
# anything is stored. Its classification row names no comment, and by the
# 2026-09-03 ruling it never will: nothing is stored on a bounce, so there is no
# `answer` row for the verdict to point at.
INSUFFICIENT_SELECTOR = "insufficient"

# The subjects the two extra students are seeded under. Distinct from E2-08's own
# `e2-08-student` so that a failure names which submission it is about.
JUDGED_SUBJECT = "e2-16-judged-student"
BOUNCED_SUBJECT = "e2-16-bounced-student"

# A statement whose shape is exactly what the criterion refuses, run against real
# tables so that the recorder and the detector are proved on the thing they are
# asked about rather than on a string. See the control below.
A_REAL_ANTI_JOIN = text(
    "SELECT count(*) FROM public.classification "
    "WHERE answer_id NOT IN (SELECT id FROM public.answer)"
)


def marked(mock_ai: Any, selector: str) -> str:
    """A floor-eligible comment carrying the mock's own marker for `selector`."""
    return f"{SUBSTANTIVE_COMMENT} {mock_ai.marker_for(selector)}"


def accepted(answered: Any, what: str) -> None:
    """Stop unless the route answered success, printing what it said instead."""
    assert 200 <= answered.status_code < 300, (
        f"{what} answered {answered.status_code} rather than success. Every assertion below is "
        f"about the row that submission stored. Body begins {answered.text[:400]!r}."
    )


def comment_answer_of(world: SubmitWorld, response: dict[str, Any]) -> dict[str, Any]:
    """The one `answer` row of a response that holds a comment."""
    comments = [row for row in world.answers_of(response) if row["comment_text"] is not None]
    assert len(comments) == 1, (
        f"The stored response holds {len(comments)} comment answers: {comments}. Every submission "
        "here answers exactly one comment, so a classification would otherwise be attributed to a "
        "row nothing in this module chose."
    )
    return comments[0]


def response_of(world: SubmitWorld, student: Any) -> dict[str, Any]:
    """The one stored response belonging to one seeded student row."""
    user_column = world.link(RESPONSE_TABLE, USER_TABLE)
    key = world.key_of(USER_TABLE)
    mine = [row for row in world.responses() if row[user_column] == student[key]]
    assert len(mine) == 1, (
        f"{len(mine)} responses belong to the student {student[key]}: {mine}. Each student here "
        "submits once, so a different number means this module is reading somebody else's row."
    )
    return mine[0]


class ThreeShapes:
    """One section, three students, and the three shapes a classification comes in."""

    def __init__(self, world: SubmitWorld, floored: Any, judged: Any) -> None:
        self.world = world
        self.floored_answer = floored
        self.judged_answer = judged

    def classifications_of(self, answer: dict[str, Any]) -> list[dict[str, Any]]:
        return self.world.classifications_of(answer)

    def bounce_rows(self) -> list[dict[str, Any]]:
        """Every classification naming no comment — the bounce shape."""
        return [
            row for row in self.world.rows_of(CLASSIFICATION_TABLE) if row[ANSWER_ID_COLUMN] is None
        ]


def three_shapes(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> ThreeShapes:
    """Seed and submit until the database holds one row of each shape the sweep sorts.

    A floored verdict naming a comment (the provider answered 503, §3.3's
    fail-open accepted the submission), a model's verdict naming a comment (the
    provider judged it), and a bounce naming none. Their assertions live in the
    tests; what this refuses to do is proceed on a submission that did not land
    the way the shape requires, so a red names the submission rather than the
    sweep.
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)

    judged_row = world.another_student(JUDGED_SUBJECT)
    floored_student = signed_in_student(client, world)
    judged_student = signed_in_student(client, world, judged_row)
    bounced_student = signed_in_student(client, world, world.another_student(BOUNCED_SUBJECT))

    accepted(
        floored_student.submit(a_valid_submission(comment=marked(mock_ai, UNAVAILABLE_SELECTOR))),
        "The submission whose comment the provider answered 503 for",
    )
    accepted(
        judged_student.submit(a_valid_submission(comment=SUBSTANTIVE_COMMENT)),
        "The submission whose comment the provider judged",
    )
    bounced = bounced_student.submit(
        a_valid_submission(comment=marked(mock_ai, INSUFFICIENT_SELECTOR))
    )
    assert bounced.status_code == 422, (
        f"The submission carrying the mock's `{INSUFFICIENT_SELECTOR}` marker was answered "
        f"{bounced.status_code} rather than 422. §3.3 bounces a comment the classifier will not "
        "call substantive, and this module needs the classification row that bounce leaves — the "
        f"one naming no comment. Body begins {bounced.text[:300]!r}."
    )

    floored_answer = comment_answer_of(world, response_of(world, world.student))
    judged_answer = comment_answer_of(world, response_of(world, judged_row))
    shapes = ThreeShapes(world, floored_answer, judged_answer)

    assert len(shapes.classifications_of(floored_answer)) == 1, (
        "The floored submission left "
        f"{len(shapes.classifications_of(floored_answer))} classification rows rather than one, so "
        "counting what the sweep adds to it would mean nothing."
    )
    assert len(shapes.classifications_of(judged_answer)) == 1, (
        "The judged submission left "
        f"{len(shapes.classifications_of(judged_answer))} classification rows rather than one."
    )
    assert len(shapes.bounce_rows()) == 1, (
        f"The bounce left {len(shapes.bounce_rows())} classification rows naming no comment rather "
        "than one. That row is the third shape the sweep has to sort, and without exactly one here "
        "the count after the sweep says nothing."
    )
    assert world.rows_of(ANSWER_TABLE), (
        "No `answer` rows were stored at all, so neither of the two answers this module follows "
        "exists and every count below would be about an empty table."
    )
    return shapes


def run_the_sweep(import_app_module: Any, reclassify: Any) -> list[Any]:
    """Run the re-classification once in this process, recording every statement it sent."""
    tasks = import_app_module("app.jobs.tasks")
    assert tasks is not None, (
        "There is no `app.jobs.tasks` module, so there is no sweep to run. E2-08's work order puts "
        "the async re-classification there as a thin wrapper over `app/services/validity.py`."
    )
    with statements_recorded() as recorded:
        reclassify(tasks)
    return recorded


def test_the_statement_recorder_sees_the_anti_join_shape_when_one_is_sent(
    migrated_engine: Any,
) -> None:
    """The control on this module's instrument. **A red here means the test is broken.**

    The assertion below this is an *absence*: no statement the sweep sent carried
    a `NOT IN`. An absence passes for free against a recorder that saw nothing and
    against a detector that matches nothing — a listener registered on the wrong
    event, a pattern with a typo — and neither failure is visible in a green
    (`docs/MISTAKES.md` entry 3, and entry 35's rule that a guard must be made to
    *find* the thing on a subject that certainly has it).

    So exactly the shape the criterion refuses is sent, over the real tables, and
    both halves have to see it: the recorder has to record the statement, and the
    detector has to flag it.
    """
    with statements_recorded() as recorded, migrated_engine.connect() as connection:
        connection.execute(A_REAL_ANTI_JOIN)

    assert recorded, (
        "The recorder saw no statements at all while a query ran on the migrated engine. It "
        "listens for `before_cursor_execute` on the `Engine` class, so nothing at all means it is "
        "listening in the wrong place — and every absence this module asserts would pass for that "
        "reason rather than for the one it claims."
    )
    flagged = anti_joins(recorded)
    assert len(flagged) == 1, (
        f"The detector flagged {len(flagged)} of the {len(recorded)} recorded statements as "
        "carrying a `NOT IN`, and exactly one was sent: "
        f"{[statement.sql for statement in recorded]}. A detector that cannot see this one cannot "
        "see the sweep's."
    )


def test_the_sweep_sends_no_not_in_anti_join(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    import_app_module: Any,
    reclassify: Any,
) -> None:
    """Criterion 3's first half, read off the statements the sweep actually sent.

    **The mutation this must kill, and it is the state of the code today:** both
    legs of the sweep written as `NOT IN` anti-joins. Measured at a term's volume:
    72 seconds, the planner rescanning `classification` once per outer row after
    the subplan's hash outgrows `work_mem`, on a job the API enqueues on every
    floored submission.

    **The near miss it must survive:** the same anti-join with the inner set
    fetched into Python and sent back as `NOT IN (:p1, :p2, …)`. That reads as a
    rewrite, passes any test looking for the word `SELECT` inside the parentheses,
    and is the same unbounded set moved from the planner into the request. The
    detector stops at `NOT IN` for that reason.

    **The canary** is asserted first: the sweep has to have sent a statement
    naming `classification`. An absence assertion over a call that queried nothing
    — a sweep that returned early, an entry point that did not run — is satisfied
    by any implementation at all.
    """
    three_shapes(
        open_submit_tool, submit_world, signed_in_student, mock_ai, mock_ai_endpoint, open_now
    )

    recorded = run_the_sweep(import_app_module, reclassify)

    read_the_table = [
        statement for statement in recorded if CLASSIFICATION_TABLE in statement.sql.lower()
    ]
    assert read_the_table, (
        f"The sweep sent {len(recorded)} statements and none of them names `{CLASSIFICATION_TABLE}`"
        f": {[statement.sql for statement in recorded]}. The floored rows it exists to find are in "
        "that table, so a run that never names it did not sweep — and 'no `NOT IN` was sent' would "
        "then be true of a sweep that does nothing at all."
    )
    flagged = anti_joins(recorded)
    assert not flagged, (
        f"{len(flagged)} of the statements the sweep sent carry a `NOT IN`:\n"
        + "\n".join(statement.sql for statement in flagged)
        + "\n\nE2-16 criterion 3: the sweep's two legs contain no `NOT IN` anti-join. Postgres "
        "runs one as a hashed subplan and abandons the hash past `work_mem`, rescanning "
        "`classification` once per outer row — 72 seconds measured at ~300k rows against 166ms for "
        "`NOT EXISTS` or a `LEFT JOIN … IS NULL`, which the planner can always run. The job is "
        "enqueued per floored submission and on a beat, so it runs hardest during the provider "
        "outage that produced the rows."
    )


def test_the_sweep_re_runs_the_floored_verdict_and_leaves_the_other_two_alone(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    import_app_module: Any,
    reclassify: Any,
) -> None:
    """Criterion 3's other half: the rewrite selects exactly the rows the old shape did.

    **Green today, and that is the point.** This is the equivalence guard the
    shape assertion needs: a leg rewritten to `NOT EXISTS` with the correlation
    condition dropped, or with the two legs' filters swapped, selects a different
    set — everything or nothing — and every shape assertion goes on passing. The
    three shapes are asserted together because the failure that matters is a
    *change in the set*, and one row cannot show it:

      - the **floored** verdict, naming a stored comment and unresolved, is what
        the sweep exists to come back to. It gains a row.
      - the **judged** verdict, naming a stored comment, is resolved. It gains
        none — a sweep that re-judged it would pay for a model call per stored
        comment per run, and §7.4's audit trail would carry a classification
        nothing asked for.
      - the **bounce**, naming no comment, is invisible to both legs by design
        (they filter `answer_id IS NOT NULL`) and stays that way. A rewrite that
        picked it up has nothing to classify: the comment was never stored.

    The provider is still answering 503 when the sweep runs — the selector is
    inside the stored comment, so it cannot be otherwise — so the row the floored
    answer gains is a second floor rather than a model's verdict. That is what
    append-only means (ADR 0055) and it is not what this test is about; the
    subject is which rows were *selected*.
    """
    shapes = three_shapes(
        open_submit_tool, submit_world, signed_in_student, mock_ai, mock_ai_endpoint, open_now
    )
    floored_before = shapes.classifications_of(shapes.floored_answer)
    judged_before = shapes.classifications_of(shapes.judged_answer)
    bounces_before = shapes.bounce_rows()

    run_the_sweep(import_app_module, reclassify)

    floored_after = shapes.classifications_of(shapes.floored_answer)
    judged_after = shapes.classifications_of(shapes.judged_answer)
    bounces_after = shapes.bounce_rows()

    assert len(floored_after) > len(floored_before), (
        f"The floored comment still has {len(floored_after)} classification rows after the sweep. "
        "It names a stored answer and no verdict resolves it, which is exactly the set the sweep "
        "selects; a leg that no longer finds it means a floored submission is never judged, and "
        "§3.3's promise that the submission is 'then classified async' is a sentence with nothing "
        "behind it."
    )
    assert len(judged_after) == len(judged_before), (
        f"The already-judged comment went from {len(judged_before)} classification rows to "
        f"{len(judged_after)}. A model has answered about that comment, so the anti-join's whole "
        "job is to exclude it: re-judging every resolved comment on every sweep is a model call "
        "per stored comment per run, and the sweep runs on a beat."
    )
    assert len(bounces_after) == len(bounces_before), (
        f"The classification rows naming no comment went from {len(bounces_before)} to "
        f"{len(bounces_after)}. A bounce stores nothing as submitted, so there is no comment for "
        "the sweep to re-classify; both legs filter on `answer_id IS NOT NULL` and a rewrite that "
        "stopped doing so would be re-running verdicts about text this system deliberately does "
        "not keep."
    )
