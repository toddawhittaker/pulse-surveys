"""E2-08 criterion 3 — the race, with the constraint seen refusing.

> A second submission racing the first cannot produce two responses for one
> (student, section, week) — the constraint is seen refusing, not cited
> (MISTAKES entry 9).

`docs/MISTAKES.md` entry 9's rule is the whole design of this module: "Before
citing a guard, execute it against the case you claim it stops and the case you
claim it allows. A guard that has never been run is a comment." E2-05 built
`uq_response_user_id_section_id_week_id` and asserts it with two `INSERT`s; what
is unexecuted until here is the *submit path* meeting it — the branch where a
request has decided there is no response yet, has classified a comment, and then
finds that another transaction wrote one while it was doing so.

**The provocation is deterministic, and the version before it was not.** This
module used to run two whole submissions in parallel and rely on the classifier's
budget to keep both inside the handler until each had passed its lookup. The
security fix round reordered the gating so classification runs *before* the
insert, which collapsed the window the two requests raced in from seconds to
microseconds: at 94809dc the test failed about three runs in ten, and the failure
was not a defect. When the second thread's lookup landed after the first thread's
commit it was an ordinary in-window resubmission answering 200 — one row, nothing
wrong, and the constraint simply never asked anything. The overlap guard compared
whole-request times and could not see that, so it reported the deliverable
failing.

**So the window is held open by a transaction rather than by a stopwatch.** This
test opens a database transaction of its own, inserts the response row for the
student's (section, week) and does **not** commit. The HTTP submission that
follows cannot see that row — it is uncommitted — so it takes the branch this
test is about: it looks, finds nothing, classifies, and inserts. The insert
blocks on the unique index, waiting for the holding transaction to end. Only once
the submission is *observably blocked* does this test commit, at which point the
index refuses the blocked insert and the handler has to turn that into a 409.

Nothing about that is timing-dependent. The point at which the commit happens is
decided by watching Postgres report an ungranted lock, not by sleeping; a run
where the submission never blocks fails saying so rather than passing.

**The barrier and the overlap guard are gone**, with the device they served. Both
existed to make two whole requests overlap and to notice when they had not, and
neither proves anything about a race that is now provoked rather than hoped for.
"""

import threading
import time
from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.submit import (
    RESPONSE_TABLE,
    SECTION_TABLE,
    SUBSTANTIVE_COMMENT,
    USER_TABLE,
    SubmitWorld,
    a_valid_submission,
    copy_texts,
)
from fixtures.supervision import require_table, seed_row
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

# How long to wait for the HTTP submission to reach its insert and block on the
# unique index. Generous, because the request classifies a comment against the
# mock before it inserts and a container start can be slow; bounded, because a
# submission that never blocks is a test that cannot pose its question and has to
# say so rather than wait for CI's own timeout.
BLOCKED_DEADLINE_SECONDS = 30.0
BLOCKED_POLL_SECONDS = 0.05

# How long to wait for the blocked request to finish once the holding transaction
# has committed. It is unblocked by then, so this only bounds a hang: a deadlock,
# a lock timeout on the application's own connection, or a handler that swallowed
# the violation and never answered.
ANSWER_DEADLINE_SECONDS = 30.0

# Postgres reports a transaction waiting on another transaction's uncommitted row
# as an ungranted lock. Asked of this test's own connection, which is idle inside
# the holding transaction and can see the whole cluster's locks.
UNGRANTED_LOCKS = "SELECT count(*) FROM pg_locks WHERE NOT granted"

# The instant the competing row carries in both its submission timestamps. Named
# and equal rather than left to the shared seeding walker, because E2-05 checks
# that `last_submitted_at` does not precede `first_submitted_at` and dispute
# E2-05-01 records the walker filling one of the pair from a constant chosen for
# `survey_window` — a row refused inside its own fixture, for a reason no
# assertion here is about. Aware, because ADR 0019 refuses anything else.
COMPETING_SUBMITTED_AT = datetime(2026, 8, 23, 22, 30, tzinfo=UTC)

# The column both `section` and `response` carry their term on, spelled as E0-06
# spelled it on `section` and E2-16 spells it on `response`. One name, because the
# seeded row below reads it off a section and writes it onto a response, and the
# whole point of the column is that those two are the same value.
TERM_COLUMN = "term_id"


class Submission:
    """One HTTP submission made on a thread, with whatever it answered."""

    def __init__(self, student: Any, answers: Any) -> None:
        self.student = student
        self.answers = answers
        self.response: Any = None
        self.failure: BaseException | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        try:
            self.response = self.student.submit(self.answers)
        except BaseException as raised:
            self.failure = raised

    def start(self) -> None:
        self.thread.start()

    def answered(self, timeout: float) -> Any:
        """What the submission answered, or a failure naming why there is nothing."""
        self.thread.join(timeout)
        if self.thread.is_alive():
            pytest.fail(
                f"The submission was still running {timeout} seconds after the holding "
                "transaction committed, so it is not waiting on that transaction any more. "
                "Either the application's connection carries a `lock_timeout` and gave up, or "
                "the handler caught the unique violation and never answered. The thread is a "
                "daemon and will not hold the run open, but nothing here can say what it is "
                "doing."
            )
        if self.failure is not None:
            raise self.failure
        return self.response


def wait_until_blocked(session: Session, deadline: float) -> bool:
    """Poll until Postgres reports an ungranted lock, or the deadline passes.

    This is what replaces a sleep. The submission's insert waits on the
    uncommitted row's transaction, which Postgres reports as a lock it has not
    granted; watching for that is watching for the exact state this test needs
    before it commits, rather than guessing how long the classifier takes.
    """
    ends_at = time.monotonic() + deadline
    while time.monotonic() < ends_at:
        if int(session.execute(text(UNGRANTED_LOCKS)).scalar_one()) >= 1:
            return True
        time.sleep(BLOCKED_POLL_SECONDS)
    return False


def test_a_submission_that_meets_an_uncommitted_response_is_refused_as_a_duplicate(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
    migrated_engine: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """The unique constraint refuses the submit path's insert, and the handler answers 409.

    **The constraint is seen refusing.** The submission's lookup runs while a
    competing response row exists and is invisible to it, so the handler takes the
    insert branch and meets `uq_response_user_id_section_id_week_id` head on. That
    is the branch E2-05's schema tests cannot reach — they insert twice
    themselves — and it is the one E2-08's work order calls "the backstop, not the
    mechanism".

    **Both halves of the handler's answer are asserted**, because they fail
    differently: an unhandled `IntegrityError` is a 500 with a stack trace where a
    student is standing, and a violation caught and swallowed is a submission
    silently lost. The registry's duplicate copy is asserted with them, because a
    409 carrying no sentence is a refusal a student cannot act on.

    **Three controls run before the assertion and none is ceremony.** Nothing is
    blocked in the cluster when the test starts, so an ungranted lock later is
    this submission and not the weather. The competing row is read back on the
    holding connection, so "it was inserted" is a fact rather than an assumption.
    And it is read for on a *different* connection and found absent, which is the
    premise the whole device rests on: if the submission could see the row it
    would take the resubmission branch and this would be a test of something else.

    **The mutation it kills** is unchanged from the version this replaces: the
    handler's `IntegrityError` translation dropped, so the violation escapes as a
    500. It also kills the check-then-insert written with no constraint behind it,
    which under two writers stores two rows for one week — two votes in every §5
    aggregate while §3.4's participation denominator stays at one.
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    client = open_submit_tool(ai_base_url=mock_ai_endpoint.base_url)
    student = signed_in_student(client, world)
    submission = Submission(
        student,
        a_valid_submission(comment=f"{SUBSTANTIVE_COMMENT} {mock_ai.marker_for('substantive')}"),
    )

    response_table = require_table(metadata_tables, RESPONSE_TABLE)
    student_id = world.student[world.key_of(USER_TABLE)]
    section_id = world.section[world.key_of(SECTION_TABLE)]
    week_id = world.week[world.key_of("week")]
    keyed = (
        (response_table.c["user_id"] == student_id)
        & (response_table.c["section_id"] == section_id)
        & (response_table.c["week_id"] == week_id)
    )

    holding = Session(bind=migrated_engine)
    committed = False
    try:
        assert int(holding.execute(text(UNGRANTED_LOCKS)).scalar_one()) == 0, (
            "Something in this cluster is already waiting on a lock before this test has done "
            "anything. The commit below is triggered by an ungranted lock appearing, so a lock "
            "that is already there would release the holding transaction before the submission "
            "had blocked on it — and the submission would then be an ordinary resubmission."
        )

        # The term is named beside the section and the week, and E2-16 is why
        # (`docs/disputes/E2-16-02.md`). That ticket gave `response` the
        # term-agreement rule `survey_window` has had since E2-05 — a `term_id`
        # held by composite foreign keys into `section (id, term_id)` and
        # `week (id, term_id)` — and this call names its section and its week
        # explicitly while handing the seeding walker an empty chain. Left to
        # fill `term_id` itself the walker builds a fresh section in a fresh term
        # and takes that term, and the composite key then refuses this row: the
        # competing response would never exist, the submission would meet nothing,
        # and the 409 this test is about would never be provoked. It comes off
        # `world.section`, which is the section `world.week` shares a term with.
        seed_row(
            holding,
            metadata_tables,
            RESPONSE_TABLE,
            {},
            user_id=student_id,
            section_id=section_id,
            week_id=week_id,
            term_id=world.section[TERM_COLUMN],
            first_submitted_at=COMPETING_SUBMITTED_AT,
            last_submitted_at=COMPETING_SUBMITTED_AT,
        )
        holding.flush()

        held = holding.execute(select(response_table).where(keyed)).all()
        assert len(held) == 1, (
            f"The holding transaction sees {len(held)} response rows for this (student, section, "
            "week) after inserting one. It has to hold exactly the row the submission will "
            "collide with, or there is nothing for the unique index to refuse."
        )
        assert world.responses() == [], (
            f"Another connection can already see {world.responses()}, so the row this test is "
            "holding is not uncommitted. The submission's own lookup would find it, take the "
            "resubmission branch, and never reach the insert this test is about — which is "
            "exactly the way the previous version of this test went wrong."
        )

        submission.start()
        blocked = wait_until_blocked(holding, BLOCKED_DEADLINE_SECONDS)

        holding.commit()
        committed = True

        assert blocked, (
            f"No ungranted lock appeared within {BLOCKED_DEADLINE_SECONDS} seconds, so the "
            "submission never reached its insert and never blocked on the row this test was "
            "holding. It could not pose its question — which is a defect in this test's "
            "provocation rather than a guard that held. The likeliest causes are the submit path "
            "refusing the request before it inserts (read the answer below), and the route "
            "inserting on a connection outside this cluster."
        )
    finally:
        if not committed:
            holding.rollback()
        holding.close()

    answered = submission.answered(ANSWER_DEADLINE_SECONDS)

    assert answered.status_code < 500, (
        f"The submission answered {answered.status_code}: {answered.text[:300]!r}. The unique "
        "constraint refusing is a condition this path expects and answers for — E2-08's work "
        "order makes the handler 'turn it into the 409 duplicate refusal' — and an unhandled "
        "`IntegrityError` is a stack trace where a student is standing."
    )
    assert answered.status_code == submit_contract.conflict, (
        f"The submission answered {answered.status_code} rather than {submit_contract.conflict}. "
        "Its insert was refused by `uq_response_user_id_section_id_week_id`, which is the "
        f"backstop E2-05 built for exactly this. Body begins {answered.text[:400]!r}."
    )

    published = sorted(
        key for key, value in copy_texts().items() if value and value in answered.text
    )
    assert len(published) == 1, (
        f"The duplicate refusal served {answered.text[:300]!r}, and {len(published)} of the copy "
        f"registry's strings appear in it ({published}). Criterion 4 covers this refusal as much "
        "as any other: it is a sentence a student reads, and E2-11's inventory reads the registry."
    )

    stored = [
        row
        for row in world.responses()
        if (row["user_id"], row["section_id"], row["week_id"]) == (student_id, section_id, week_id)
    ]
    assert len(stored) == 1, (
        f"There are {len(stored)} responses for one (student, section, week): {stored}. SPEC §8 "
        "makes that triple unique, and two rows are two votes in every §5 aggregate while §3.4's "
        "participation denominator stays at one week."
    )
