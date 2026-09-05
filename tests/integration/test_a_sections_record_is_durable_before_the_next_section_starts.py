"""What survives a run that did not finish cleanly — ticket E3-06, work order D15.

The sweep walks every section in the institution in one call. Until D15 it wrote
every row of that walk into one transaction and left the commit to the task above
it, which means the record of what reached a platform existed only in memory
until the last section was done. A worker killed in the middle — a deploy, an
OOM, a lost database connection on section two hundred — discarded the
`grade_sync` and `ags_call` rows of every section before it, while the scores
those rows describe were already sitting in gradebooks. Pulse would then believe
it had posted nothing, and the next run would post everything again: new
timestamps, new deliveries, and no account anywhere of the first ones.

**D15 settles the grain: the sweep commits after each section.** A section's rows
are durable before the next section starts, which is the same thing E3-05 settled
one layer up for `create_line_item` and for the same reason — the record of an
outbound call has to outlive the process that made it.

**The residue is named rather than hidden.** An unexpected failure inside a
section still rolls that section's own rows back, because its work is one
savepoint (D1) and a half-written section is not a record anybody can read. What
D15 buys is that the failure is contained to the section it happened in. Both
halves are asserted here, and the second is what keeps the first from being a
claim about a sweep that simply commits everything all the time.

**How durability is measured.** Every other reader in this suite ends the tests'
own transaction before it looks — `GradeSyncRows.for_pair` says so in its own
docstring — so a row the sweep wrote and never committed becomes durable *because
the test looked at it*, and the question this module asks would answer itself.
So the read here goes through `durable_for`, on a **second connection** from the
engine, and it happens before anything else touches the session. That ordering is
load-bearing: one call to `for_pair` first would commit the sweep's work and this
test would pass against the very shape it exists to refuse.

**And the fix's own new failure mode is here too.** Committing per section
creates a place a run can fail that did not exist before: the commit itself. It
happens after that section's savepoint has been released, so a handler written
for the *other* failure — roll the savepoint back, log, carry on — cannot run at
all, and what an operator gets is a traceback about a closed transaction and a
walk that stopped without saying where. A fix round has the defect density of the
work it fixes, so the second test here is about the shape D15 introduced rather
than the one it removed.

**Which failure a red here is.** Neither test can fail on a missing symbol; both
are about a sweep that exists. Against the sweep as it first shipped — one
transaction, committed by the task — the first fails on the assertion that the
posting section's row is visible on the second connection: the row is there in
the session and nowhere else yet. Against the sweep as the D15 round shipped it,
the second fails on `raised is None`, because `ResourceClosedError` comes out of
the handler and out of the sweep.
"""

import logging
from typing import Any
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`; `migrated_engine` from `tests/fixtures/database.py`.

# How many course weeks have elapsed when the sweep runs. One: the smallest world
# in which both sections have a score to post at all.
ELAPSED_WEEKS = 1

# What the poisoned transport raises. A `RuntimeError` carrying a string of this
# module's own, so that a failure arriving anywhere in this test can be told from
# the one the test planted — and deliberately **not** an error type E3-04 defines,
# because the case D15 is about is the *unexpected* one: a `MemoryError`, a
# connection reset, a bug in a helper. An error the client knows how to describe
# is an ordinary failed post and is asserted in
# `test_a_failed_post_is_recorded_and_retried_with_the_bytes_it_sent.py`.
THE_UNEXPECTED_FAILURE = "e3-06-unexpected-failure-inside-one-section"

# The subject the failing section's student carries. **This module's own rather
# than one of that section's launch subjects**, and the reason is a collision the
# test cannot otherwise avoid: the two sections are two launch contexts of one
# registered platform, a platform is free to seed the same person in both, and
# `user` is unique on `(lti_platform_id, lms_user_id)` — so a student built from
# the second context's subjects can be a row that already exists. It costs
# nothing here: this student's post is the one the poison stops, so no platform
# is ever asked to recognise them.
A_STUDENT_THIS_MODULE_INVENTED = "e3-06-durability-student"

# What the failing commit raises. A `RuntimeError` carrying a string of this
# module's own, because the *class* is immaterial and the *moment* is everything:
# what the second test poses is a `session.commit()` that fails after the
# section's savepoint has already been released, which is what a lost connection,
# a deadlock victim or an idle-transaction terminate produces in production.
THE_LOST_CONNECTION = "e3-06-commit-lost-the-connection"

# Which call to the driving session's `commit` fails. The first is this module's
# own control commit, which proves the hook is installed and passes through
# unharmed; then one per section, and the middle section of three is the one that
# fails — so the walk has a section before it and a section after it.
THE_FAILING_COMMIT = 3


class OnePoisonedSection:
    """The suite's own wire, with any call naming one section's Score service raising.

    A wrapper rather than a substitute: every other call — the token grant, the
    other section's post, anything the client does that this module has not
    thought about — goes through to the real transport untouched, so the section
    that is *not* poisoned behaves exactly as it does in every other module here.

    **Which section fails is decided by the URL and never by an ordinal**, because
    the order the sweep walks sections in is not something E3-06 settles. Poisoned
    by address, the same two assertions hold whichever section the walk reaches
    first, which is what stops this test from quietly depending on an ordering
    nobody promised.

    `raised` counts what it did, and the test asserts on it. Without that a sweep
    that never reached the poisoned section at all — because it walked one
    section, or none — would satisfy every "nothing was written for it" assertion
    below perfectly (`docs/MISTAKES.md` entry 3).
    """

    def __init__(self, inner: Any, poisoned: str) -> None:
        self.inner = inner
        self.poisoned = poisoned
        self.raised = 0

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self.inner, name)
        if not callable(attribute):
            return attribute

        def guarded(*arguments: Any, **keywords: Any) -> Any:
            spoken = (*arguments, *keywords.values())
            if any(self.poisoned in str(value) for value in spoken):
                self.raised += 1
                raise RuntimeError(THE_UNEXPECTED_FAILURE)
            return attribute(*arguments, **keywords)

        return guarded


def a_section_that_posts(gradebooks: Any, sweep_contract: Any) -> Any:
    """The section that must succeed: a stored line item and one of the platform's own students."""
    book = gradebooks()
    (student,) = sweep_contract.students(book, 1)
    sweep_contract.answered_fully(book.world, student, through=ELAPSED_WEEKS)
    book.world.rows.commit()
    return book


def a_second_section_on_the_same_platform(gradebooks: Any, beside: Any, sweep_contract: Any) -> Any:
    """The section that must fail: built beside the first, never a second registration.

    `gradebooks.beside` seeds it on the platform the first section registered —
    same platform row, same deployment, same wire host — under a launch context of
    its own, so it has its own AGS container and its own line item and the poison
    can tell the two apart by address. A second `gradebooks()` call would register
    the mock a second time, which `uq_lti_platform_issuer_client_id` refuses.

    Its student is this module's invented subject for the reason the constant
    gives.
    """
    book = gradebooks.beside(beside)
    student = book.world.student(f"{A_STUDENT_THIS_MODULE_INVENTED}-{uuid4().hex[:8]}")
    sweep_contract.answered_fully(book.world, student, through=ELAPSED_WEEKS)
    book.world.rows.commit()
    return book


class ACommitThatFailsOnce:
    """The driving session's `commit`, raising on one call and passing every other through.

    **The moment is the whole point.** D15 gives each section a savepoint and
    then commits, so a `session.commit()` that fails is a failure arriving after
    that savepoint has already been *released* — which is the state the shipped
    handler's `savepoint.rollback()` cannot be called in. Nothing else in this
    suite can reach that state: the poison above raises from the transport, while
    the savepoint is still open and rolling it back is exactly right.

    It counts, and both numbers are asserted. `calls` is what says the hook is on
    the object the sweep actually commits through — a seam installed on some other
    session would never be called at all — and `raised` is what says the failure
    this test is about actually happened, rather than a walk that committed once
    and stopped.
    """

    def __init__(self, inner: Any, *, failing_call: int) -> None:
        self.inner = inner
        self.failing_call = failing_call
        self.calls = 0
        self.raised = 0

    def __call__(self) -> Any:
        self.calls += 1
        if self.calls == self.failing_call:
            self.raised += 1
            raise RuntimeError(THE_LOST_CONNECTION)
        return self.inner()


def logged_by(caplog: Any, prefix: str) -> list[Any]:
    """Every captured record written by `prefix` or by a child of it.

    A copy of `records_from` in
    `tests/integration/test_the_sweep_never_logs_a_score_a_ledger_or_an_lms_user_id.py`
    rather than an import of it: a test module that imports a sibling test module
    depends on where pytest put `tests/` on `sys.path`, and an import error is not
    a red.
    """
    return [
        record
        for record in caplog.records
        if record.name == prefix or record.name.startswith(f"{prefix}.")
    ]


def test_a_successful_sections_rows_are_durable_though_another_section_failed_unexpectedly(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    migrated_engine: Any,
) -> None:
    """D15's commit grain, measured as the only thing it can be measured as: durability.

    Two sections in one run. One posts. The other raises a `RuntimeError` out of
    its transport mid-post — an unexpected failure, not a refusal the client has
    a name for — and the sweep logs it and steps over (D1). Then, **with the test
    committing nothing at all**, a second connection is asked what is in the two
    passback tables: the posting section's row and call are there, and the
    failing section's are not.

    **The mutation this kills**: the per-section commit reverted to one commit at
    the end of the run — which is how the sweep first shipped, is the shape every
    other test in these modules is indifferent to, and loses the record of every
    section already posted when a worker dies mid-walk. The scores stay in the
    gradebooks; only Pulse's account of them is gone, and the next run re-posts
    them all as new deliveries because `grade_sync` no longer says otherwise.

    **The two halves, and the second is the accepted residue.** A section that
    fails unexpectedly rolls back — D1 puts its work in a savepoint, and a
    half-written section is worse than none. Asserting it here keeps the first
    half honest: without it, "A's rows are durable" is equally true of a sweep
    that committed everything the moment it was written, including the rows of
    the section that then blew up.

    **Two sections of one institution, not two institutions.** The second is
    built with `gradebooks.beside`, on the platform the first registered and under
    a launch context of its own: the mock registers under one issuer and one
    client id, so a second `gradebooks()` call is refused by
    `uq_lti_platform_issuer_client_id` before this test says anything, and
    `roster_platforms` mounts platforms by host, so a second one would replace the
    first on the wire. Their containment chains are separate, which is what lets
    both carry the same cohort's section code.

    **The controls, and they run before the assertions they qualify.**

      - The two sections are distinct rows with distinct Score service addresses,
        because the poison picks its victim by address; and their week-1 close is
        the same instant, because one clock is moved for both.
      - The poison is required to have fired. A sweep that walked one section, or
        walked neither, satisfies "nothing was written for the failing section"
        without the failure ever happening.
      - The posting section is required to have actually reached the platform,
        read from the platform's own record. A run that posted nothing has
        nothing to be durable, and every assertion below would be about an empty
        table.

    **Why the durable read comes first in the body.** `for_pair`, `all_rows` and
    `calls` all commit this suite's session before they read — deliberately, for
    the task-driven tests — so calling any of them here would make the sweep's
    work durable and this test would pass against the shape it refuses. The
    second-connection read happens first, and nothing else in this test reads the
    database at all.
    """
    posting = a_section_that_posts(gradebooks, sweep_contract)
    failing = a_second_section_on_the_same_platform(gradebooks, posting, sweep_contract)
    posting.world.elapsed_through(committed_clock_overrides, ELAPSED_WEEKS)
    assert posting.id != failing.id and posting.scores_url() != failing.scores_url(), (
        f"The two sections are {posting.id} at {posting.scores_url()!r} and {failing.id} at "
        f"{failing.scores_url()!r}. The poison below picks its victim by address, so two sections "
        "sharing one Score service address would make it kill both — and the durable half of this "
        "test would fail for a reason that has nothing to do with when the sweep commits."
    )
    assert failing.world.closes_at(ELAPSED_WEEKS) == posting.world.closes_at(ELAPSED_WEEKS), (
        f"Course week {ELAPSED_WEEKS} closes at {posting.world.closes_at(ELAPSED_WEEKS)!r} for one "
        f"section and {failing.world.closes_at(ELAPSED_WEEKS)!r} for the other. One clock is moved "
        "for both below, so two calendars would leave one of them with no elapsed week and nothing "
        "to post — which reads as a sweep that skipped a section."
    )
    poison = OnePoisonedSection(posting.wire.session(), failing.scores_url())
    posting.wire.calls.clear()

    _answered, raised = sweep_contract.run(posting.session, settings=window_settings, http=poison)

    assert raised is None, (
        f"The sweep raised {raised!r}. D1 has a section that fails unexpectedly logged and stepped "
        "over so the walk continues, and this test poisons one section's transport precisely to "
        "produce that case — an escape here means one bad section still stops every section after "
        "it, and D15's commit grain cannot be measured because the run never finished."
    )
    assert poison.raised, (
        f"The poisoned transport was never asked about {failing.scores_url()!r}, so no section "
        "failed and this run is an ordinary two-section sweep wearing this test's name. Either the "
        "walk never reached that section — a bound, a missing line item, an enrollment — or the "
        "sweep posts through some transport other than the one it was handed."
    )
    assert posting.posted(), (
        "The platform recorded no score for the section that was meant to post, so there is no "
        "delivery for a `grade_sync` row to be the record of. Every assertion below would then be "
        "about an empty table rather than about when rows become durable."
    )

    durable = grade_sync_rows.durable_for(migrated_engine, posting.id)
    left_behind = grade_sync_rows.durable_for(migrated_engine, failing.id)

    assert len(durable[sweep_contract.grade_sync_table]) == 1, (
        f"A second connection sees {durable[sweep_contract.grade_sync_table]} in "
        f"`{sweep_contract.grade_sync_table}` for the section that posted, and this test has "
        "committed nothing. D15 commits after each section, so by the time the walk moved on this "
        "row was durable. Under one commit at the end of the run it exists only inside the sweep's "
        "own transaction — and a worker that dies before that commit leaves the score in the "
        "gradebook and no record anywhere that Pulse put it there."
    )
    assert durable[sweep_contract.ags_call_table], (
        f"A second connection sees no `{sweep_contract.ags_call_table}` row for the section that "
        "posted. SPEC §6.1 puts that table at the grain of one call the tool made, and it is what "
        "an operator reads to find out what happened; a call log that is only durable if the whole "
        "institution's walk finishes is not a log of what happened."
    )
    assert not left_behind[sweep_contract.grade_sync_table], (
        f"A second connection sees {left_behind[sweep_contract.grade_sync_table]} in "
        f"`{sweep_contract.grade_sync_table}` for the section whose transport raised. D1 puts each "
        "section's work in a savepoint, so an unexpected failure takes that section's rows with "
        "it — the accepted residue, and the reason it is asserted is that a row here would mean "
        "the failure was recorded as an outcome rather than stepped over.\n\n"
        "If the row present here is a `FAILED` one carrying a status, the `RuntimeError` this test "
        "raises was absorbed into a post outcome instead of escaping to the section's savepoint. "
        "That is this test's seam being wrong rather than the sweep: the case D15 is about is the "
        "failure the client has no name for, and the poison would need to be raised somewhere the "
        "post's own error handling does not reach."
    )


def test_a_section_whose_commit_fails_is_stepped_over_and_the_rest_of_the_walk_still_lands(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    ags_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    migrated_engine: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The failure D15's own fix made reachable: a commit that fails after its savepoint is gone.

    Three sections. The middle one's `session.commit()` raises once — a lost
    connection, a deadlock victim, an idle-transaction terminate, any of which
    reaches the caller as an exception out of that call and none of which this
    suite could produce before D15, because before D15 there was no per-section
    commit to fail. The sweep must log it, step over it, and go on: the section
    after it posts and its rows are durable.

    **The mutation this kills is the shipped handler's own line**: an unguarded
    `savepoint.rollback()` in the `except` that wraps a section's work. By the
    time `session.commit()` is called the savepoint has been *released* — a
    committed savepoint is not a thing that can be rolled back — so the handler's
    first statement raises `ResourceClosedError` from inside the handler. The log
    line never runs, the session is never rolled back, the `continue` never
    happens, and every remaining section of the institution is abandoned in
    silence, in a run that reports a traceback about a closed transaction rather
    than about the section that failed. A handler that guards that call, or a
    structure that does not hold a savepoint at that point, greens this test.

    **Why the existing test above cannot see it.** Its poison raises from the
    transport, while the section's savepoint is still open — where rolling it back
    is exactly the right thing. The whole defect lives in the window between
    `savepoint.commit()` and the end of `session.commit()`, and only a failure
    from the commit itself lands there.

    **The seam is a wrapper on the driving session's `commit`, and its own
    correctness is a control.** It counts every call and passes each through
    untouched except one. Before the sweep runs, this test commits through it
    once itself and requires that call to have been seen and to have raised
    nothing — which is what says the hook is installed on the object the sweep
    commits through and that a pass-through commit still works. Then the sweep's
    calls are the section commits, and the failure lands on the middle one.

    **Which section fails is discovered, not assumed.** The order the sweep walks
    sections in is not something E3-06 settles, so this asserts the *shape* of the
    outcome — exactly one of three sections left no durable rows, and the other
    two left one each — and takes the section that failed to be the one with none.
    That is the same claim, and it is one an ordering cannot make false.

    **The log assertion is an id and nothing else.** Criterion 7's rules hold
    everywhere in this ticket: the section is named because an operator has to
    know which gradebook stopped updating, and the score, the ledger and the
    student are not, which
    `test_the_sweep_never_logs_a_score_a_ledger_or_an_lms_user_id.py` is what
    polices.
    """
    first = a_section_that_posts(gradebooks, sweep_contract)
    second = a_second_section_on_the_same_platform(gradebooks, first, sweep_contract)
    third = a_second_section_on_the_same_platform(gradebooks, second, sweep_contract)
    walked = (first, second, third)
    first.world.elapsed_through(committed_clock_overrides, ELAPSED_WEEKS)

    assert len({book.id for book in walked}) == len(walked), (
        f"The three sections are {[book.id for book in walked]}, and they are not three rows. "
        "Every assertion below counts sections by their id, so two names for one section would "
        "make 'exactly one failed' unreadable."
    )
    closes = {book.world.closes_at(ELAPSED_WEEKS) for book in walked}
    assert len(closes) == 1, (
        f"The three sections close course week {ELAPSED_WEEKS} at {sorted(closes)}. One clock is "
        "moved for all three below, so more than one calendar leaves some of them with no elapsed "
        "week and nothing to post — which reads here as a walk that skipped a section."
    )

    seam = ACommitThatFailsOnce(first.session.commit, failing_call=THE_FAILING_COMMIT)
    monkeypatch.setattr(first.session, "commit", seam)
    first.session.commit()

    assert seam.calls == 1 and seam.raised == 0, (
        f"The seam recorded {seam.calls} call(s) and {seam.raised} failure(s) after this test "
        "committed through it once. It is installed on the session the sweep is handed, and a "
        "pass-through commit has to reach the real one and return — without that, every count "
        "below is about a hook that is not where the sweep commits."
    )
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=sweep_contract.grading_logger)

    _answered, raised = sweep_contract.run(
        first.session, settings=window_settings, http=first.wire.session()
    )

    assert raised is None, (
        f"The sweep raised {raised!r} when one section's commit failed. That is the defect this "
        "test exists for: the section's savepoint was already released by the time the commit was "
        "attempted, so the handler's `savepoint.rollback()` raises `ResourceClosedError` from "
        "inside the `except` — the log line, the session rollback and the `continue` are all "
        "skipped, and every section after this one is abandoned without a word. D1's promise is "
        "that a section that fails is logged and stepped over, and it has to hold for the commit "
        "as well as for the post."
    )
    assert seam.raised == 1, (
        f"The seam was called {seam.calls} time(s) and raised {seam.raised} time(s). It fails on "
        f"call {THE_FAILING_COMMIT} — this test's own control commit, then one per section — so "
        "zero failures means the sweep committed fewer times than there are sections and D15's "
        "per-section commit is not in force, which is a different red from this one."
    )

    durable = {book.id: grade_sync_rows.durable_for(migrated_engine, book.id) for book in walked}
    absent = [book for book in walked if not durable[book.id][sweep_contract.grade_sync_table]]
    landed = [book for book in walked if durable[book.id][sweep_contract.grade_sync_table]]

    assert len(absent) == 1, (
        f"{len(absent)} of {len(walked)} sections left no durable row in "
        f"`{sweep_contract.grade_sync_table}`: {[book.id for book in absent]}. Exactly one commit "
        "failed, so exactly one section should have nothing.\n\n"
        "Two or more means the walk stopped at the failure rather than stepping over it. None "
        "means the failed section's rows reached the database anyway — which happens when the "
        "handler does not roll the session back, since the next section's commit then carries the "
        "failed section's uncommitted work along with its own."
    )
    survived = {book.id: durable[book.id][sweep_contract.grade_sync_table] for book in landed}
    assert all(len(rows) == 1 for rows in survived.values()), (
        f"The sections that survived left {survived}. One row each: one student, one post, one "
        "record of it — and durable without this test committing anything, which is what says the "
        "walk carried on and committed after the failure rather than at the end of a run that "
        "never finished."
    )
    assert all(durable[book.id][sweep_contract.ags_call_table] for book in landed), (
        f"A second connection sees no `{sweep_contract.ags_call_table}` row for one of the sections "
        "that posted. §6.1's call log is what an operator reads to find out what happened, and it "
        "becomes durable with the section it belongs to."
    )
    assert not durable[absent[0].id][sweep_contract.ags_call_table], (
        f"A second connection sees {durable[absent[0].id][sweep_contract.ags_call_table]} in "
        f"`{sweep_contract.ags_call_table}` for the section whose commit failed. Its work was "
        "rolled back with the failed transaction, so the call log has to go with it: a call row "
        "without the `grade_sync` row beside it says a post was made that Pulse has no record of "
        "sending."
    )

    text = ags_contract.logged_text(logged_by(caplog, sweep_contract.grading_logger))
    assert str(absent[0].id) in text, (
        f"Nothing written under `{sweep_contract.grading_logger}` names section {absent[0].id}, "
        "whose commit failed and whose gradebook has therefore not been updated. D1 has a failing "
        "section logged and stepped over, and the log line is the whole of 'stepped over' that "
        "anybody can see — without it a section stops updating in silence and §6.1's console has "
        f"nothing to show. What was logged:\n{text}"
    )
