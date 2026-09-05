"""The two readbacks of one gradebook agree — ticket E3-08, criterion 2.

E3-08's second acceptance criterion, in full: "The readback goes through the
platform's Result container as well as through the mock-only route, and the two
agree."

**Why the criterion exists.** Every assertion E3 makes about what reached a
gradebook is made through `GET /mock/posted-scores` (ADR 0047), because a
conformant AGS `Result` carries `userId`, `resultScore`, `resultMaximum` and
`scoreOf` and nothing else — no timestamp, no progress members, no record of what
was *sent* — so the mock-only route is the only surface that can answer questions
about the body. That makes it load-bearing for the whole epic and unverified by
anything: a mock whose inspection route recorded the request and whose AGS
implementation stored something else would leave every passback test in this
repository green over a gradebook that held a different number. The exit is where
the two surfaces are put beside each other.

**Which readback is which.** `GET /mock/posted-scores` is a log, in arrival
order, of the bodies the tool posted; the AGS Result container at
`…/line_items/{id}/results` is the platform's own statement of what a student's
result *is* now. They answer different questions, which is why "agree" has to
mean something precise: **the latest entry of the log, per student, is what the
Result container reports.** Two posts per student are driven here for exactly
that reason — a comparison made after a single post is satisfied by a platform
that files the first score it is ever sent and ignores the rest, which is a
gradebook that stops updating in week two.

**The token is why this is not in the browser spec.** `GET …/results` requires an
access token carrying `…/scope/result.readonly` (ADR 0134), and that token is
obtained with a `client_assertion` signed by the tool's private key. A host-side
Playwright process cannot mint one. `MockPlatform.results` goes through the
platform's own token endpoint, which is also what makes this a statement about
the AGS surface as a conformant tool reaches it rather than about a back door.

**The passback is driven through E3-07's `/dev` trigger**, on
`tests/integration/test_the_dev_trigger_runs_a_passback.py`'s machinery, so the
thing being read back twice is a real end-to-end post rather than a body this
module composed. Nothing here computes a percentage or a ledger: E3-03's
`participation_scores` is the only source of an expected value, and the two
premise guards that use it say so at their assertion (`docs/MISTAKES.md` entry
19).

**The environment.** `window_settings` states `ENVIRONMENT=development` and
`INSTITUTION_TIMEZONE=America/New_York` over `configured_env`'s documented values
(`docs/MISTAKES.md` entry 40), which is the chain every module built on
`gradebooks` rides.

**Which failure a red here is.** Every test in this module is expected **green**
on the tree E3-08 starts from: the sweep, the trigger, the mock's AGS
implementation and its inspection route all exist. `declared_passback_path` is a
plain call in the test body, so a tree without E3-07's constant reports a FAILED
naming the deliverable rather than an ERROR in a fixture (`docs/MISTAKES.md`
entry 44). A red anywhere else is a disagreement between the two surfaces, which
is a finding about the mock platform and about every E3 test that trusts one of
them.
"""

from typing import Any

import pytest
from fixtures.dev_console import (
    ORIGIN_HEADER,
    declared_passback_path,
    redirected_to_the_console,
    same_origin_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `sweep_contract` come from `tests/fixtures/grade_sweep.py`;
# `window_settings` from `tests/fixtures/survey_windows.py`;
# `committed_clock_overrides` from `tests/fixtures/clock.py`; `line_item_contract`
# from `tests/fixtures/line_item_creation.py`; `dev_console_tool` from
# `tests/fixtures/dev_console.py`. All are reached as fixtures rather than
# imported, for the reason every module in this suite gives: an import of a
# fixtures module by name depends on where pytest put `tests/` on `sys.path`, and
# an import error is not a red.

# The AGS 2.0 `Result` members, transcribed from the specification rather than
# imported from `mock-lms/app/ags.py` — a module that read its expectation out of
# the code under test holds two copies of one fact inside the blast radius of one
# change (`docs/MISTAKES.md` entry 19). `tests/fixtures/lti_services.py::results`
# and `tests/integration/test_mock_lms_ags_line_items_and_scores.py` spell them
# the same way.
RESULT_USER_MEMBER = "userId"
RESULT_SCORE_MEMBER = "resultScore"
RESULT_MAXIMUM_MEMBER = "resultMaximum"

# The two moments the clock stands at, as course weeks of this section's own
# calendar. Two rather than one because the agreement has to be about the
# *latest* post: see the module docstring.
FIRST_MOMENT = 1
SECOND_MOMENT = 2

# How many students the section carries. Three, so that the two surfaces cannot
# agree by reporting one number for everybody — a Result container that answered
# the same result whatever `userId` it was asked about would pass a
# single-student comparison completely.
STUDENTS = 3

# What each of the three answers, and the arithmetic that follows from it. The
# section carries a five-question set (`gradebooks`' default) and the three are
# day-one members of it (`sweep_contract.students`), so a week is five items and
# an elapsed week the student did not answer is 0 of 5.
#
#   - `steady` answers course week 1 in full and nothing after it:
#       one elapsed week   → 5 of 5   → 5/5 x 100 = 100.0
#       two elapsed weeks  → 5 of 10  → 5/10 x 100 = 50.0
#   - `partial` answers course week 1 without one optional comment:
#       one elapsed week   → 4 of 5   → 4/5 x 100 = 80.0
#       two elapsed weeks  → 4 of 10  → 4/10 x 100 = 40.0
#   - `silent` answers nothing:
#       one elapsed week   → 0 of 5   → 0.0
#       two elapsed weeks  → 0 of 10  → 0.0
#
# Three distinct values at each moment, and the first two students' values move
# between the moments — which is what makes "the container holds the latest"
# checkable. `silent`'s value does not move and their ledger does (one line
# becomes two), so they re-post as well (ADR 0137's pair comparison); they are
# here for the cross-student distinctness rather than for the change.
STEADY_AT_THE_FIRST_MOMENT = "100.0"
STEADY_AT_THE_SECOND_MOMENT = "50.0"

# How many entries the log must hold per student after two passbacks: one each.
POSTS_PER_STUDENT = 2


def answered_without_one_comment(world: Any) -> list[int]:
    """Every question position but the first comment — a week answered four items of five.

    SPEC §3.3 as amended: a blank optional comment does not affect the response's
    validity and does cost its item in §3.4's score. Which positions those are is
    read off the question set this world planted, never spelled here: the set is
    versioned precisely so its shape can change (§3.2), and a literal list would
    be wrong the first time it does.
    """
    comments = world.comment_positions()
    assert comments, (
        "The question set in force carries no comment position, so there is no optional item to "
        "leave blank and the `partial` student below would answer exactly what `steady` does — "
        "which collapses two of this module's three distinct values into one."
    )
    return [position for position in world.positions if position != comments[0]]


def a_gradebook_with_three_different_scores(
    gradebooks: Any, sweep_contract: Any
) -> tuple[Any, Any, Any, Any]:
    """One section, one line item, and three students whose scores differ from each other."""
    book = gradebooks()
    steady, partial, silent = sweep_contract.students(book, STUDENTS)
    book.world.answer_week(steady, FIRST_MOMENT)
    book.world.answer_week(
        partial, FIRST_MOMENT, positions=answered_without_one_comment(book.world)
    )
    book.world.rows.commit()
    return book, steady, partial, silent


def pull_the_trigger(client: Any, declared: str) -> None:
    """One same-origin POST to E3-07's `/dev` passback trigger, required to have run.

    The redirect is asserted rather than assumed for the reason
    `test_the_dev_trigger_runs_a_passback.py` gives: a trigger that answered
    something else did not run the sweep, and every assertion below would then be
    about a gradebook nothing wrote to.
    """
    answered = client.post(declared, headers={ORIGIN_HEADER: same_origin_of(client)})
    redirected_to_the_console(answered, f"`POST {declared}` with a same-origin `{ORIGIN_HEADER}`")


def logged_for(book: Any, subject: str, sweep_contract: Any) -> list[dict[str, Any]]:
    """Every score body `GET /mock/posted-scores` holds for one student, in arrival order."""
    return [
        sweep_contract.body(entry)
        for entry in book.posted()
        if str(entry.get(sweep_contract.user_member)) == subject
    ]


def results_by_user(book: Any) -> dict[str, dict[str, Any]]:
    """The AGS Result container for this line item, keyed by `userId`.

    A dict rather than a list, and a failure rather than a silent overwrite if two
    results name one user: AGS makes a Result the platform's statement about one
    user, so two of them for one `userId` is a container this comparison cannot
    read at all and is a different finding from a disagreement.
    """
    found: dict[str, dict[str, Any]] = {}
    for result in book.platform.results(book.line_item):
        user = str(result.get(RESULT_USER_MEMBER))
        if user in found:
            pytest.fail(
                f"The Result container holds more than one result for {user!r}: {found[user]!r} "
                f"and {result!r}. AGS makes a `Result` the platform's statement about one user "
                "against one line item, so a second one means the container is a log of posts "
                "wearing the Result media type — and 'the two surfaces agree' is then a question "
                "about which of two results was picked."
            )
        found[user] = dict(result)
    return found


def test_the_result_container_reports_the_latest_entry_of_the_mock_only_log_for_every_student(
    gradebooks: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    line_item_contract: Any,
    dev_console_tool: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 2: one gradebook, read through both surfaces, compared per student.

    Two passbacks a week apart, three students whose scores differ from each other
    and two of whom differ from themselves between the two runs. Afterwards the
    log holds two bodies per student and the Result container holds one result per
    student, and the criterion is that the second of each pair is what the
    container reports.

    **The mutations this kills:**

      1. *The mock records the request in its inspection log and stores something
         else against the line item* — a rescale, a clamp, a value read out of the
         wrong member of the body. Every passback test in E3 reads the log, so
         this defect is invisible to all of them and would be a gradebook holding
         a number Pulse never sent.
      2. *The Result container reports the first post rather than the current
         result*, which is a gradebook that stops updating after week one. Killed
         by the two moments and by nothing else: after a single post the two
         surfaces agree whichever one the container files.
      3. *Either surface answers one student's result for another*, or answers one
         number for everybody. Killed by the three distinct values — a container
         keyed on the line item rather than on `(line item, user)` reports the last
         score anybody was given, and with one student that is the right answer.
      4. *The container reports a stale maximum*, which rescales the whole column
         silently. The maximum is compared beside the score for that reason.

    **The near misses that must stay green:** any number of entries in the log
    beyond two per student, which a sweep is entitled to write if a value changed
    more often than this test made it change; the `comment` member, which AGS
    makes optional on a `Result` and which is deliberately not compared here —
    what the *ledger* is, is E3-03's, and whether the platform stored it verbatim
    is `test_the_dev_trigger_runs_a_passback.py`'s, read off the log where ADR
    0047 puts it; and any ordering of the container's own results.

    **The three premise guards come first**, and none of them is ceremony: an
    empty log makes "the container matches the log" true for nothing, three equal
    scores make mutation 3 unreachable, and a `steady` student whose value did not
    move makes mutation 2 unreachable.
    """
    declared = declared_passback_path()
    book, steady, partial, silent = a_gradebook_with_three_different_scores(
        gradebooks, sweep_contract
    )
    everybody = (steady, partial, silent)

    client = dev_console_tool()
    line_item_contract.reaching_the_platform(monkeypatch, book.wire)

    # --- the first moment ---------------------------------------------------
    book.world.elapsed_through(committed_clock_overrides, FIRST_MOMENT)
    first = {
        student.subject: sweep_contract.computed(book.world, student, settings=window_settings)
        for student in everybody
    }
    assert first[steady.subject].percentage == STEADY_AT_THE_FIRST_MOMENT, (
        f"With one course week elapsed, `participation_scores` makes the fully answered student "
        f"{first[steady.subject].percentage!r} and this module's own arithmetic makes them "
        f"{STEADY_AT_THE_FIRST_MOMENT!r} — five items of five is 5/5 x 100. This is a premise "
        "guard on the world this test built, not a second implementation of the formula: with the "
        "world different from the one described above, the distinctness and change guards below "
        "are checking something else."
    )
    pull_the_trigger(client, declared)

    # --- the second moment --------------------------------------------------
    book.world.elapsed_through(committed_clock_overrides, SECOND_MOMENT)
    latest = {
        student.subject: sweep_contract.computed(book.world, student, settings=window_settings)
        for student in everybody
    }
    assert latest[steady.subject].percentage == STEADY_AT_THE_SECOND_MOMENT, (
        f"With two course weeks elapsed, `participation_scores` makes the same student "
        f"{latest[steady.subject].percentage!r} and this module's arithmetic makes them "
        f"{STEADY_AT_THE_SECOND_MOMENT!r} — the same five completed items over a denominator that "
        "has grown to ten, which is 5/10 x 100. The whole point of the second run is that this "
        "value moved."
    )
    pull_the_trigger(client, declared)

    # --- the premises, before either surface is believed --------------------
    spread = {student.subject: latest[student.subject].percentage for student in everybody}
    assert len(set(spread.values())) == STUDENTS, (
        f"The three students' scores at the second moment are {spread}, which is not three "
        "different values. With two of them equal, a container that answered one student's result "
        "for another would agree with the log anyway, and mutation 3 is unreachable."
    )
    for student in (steady, partial):
        assert first[student.subject].percentage != latest[student.subject].percentage, (
            f"{student.subject!r} scored {first[student.subject].percentage!r} at both moments, so "
            "there is no difference between the first post and the last one and a container that "
            "filed only the first would look correct. `silent` is legitimately unchanged; these "
            "two are the ones this test needs to move."
        )

    log = {
        student.subject: logged_for(book, student.subject, sweep_contract) for student in everybody
    }
    for subject, bodies in log.items():
        assert len(bodies) == POSTS_PER_STUDENT, (
            f"`GET /mock/posted-scores` holds {len(bodies)} entries for {subject!r} after two "
            f"passbacks over a section whose scores changed between them: {bodies}. Zero means "
            "nothing reached the platform at all and every comparison below is between two empty "
            "answers; one means the second sweep found nothing to say, which makes 'the latest "
            "entry' the only entry and mutation 2 unreachable."
        )

    # --- the criterion ------------------------------------------------------
    container = results_by_user(book)
    assert set(container) >= {student.subject for student in everybody}, (
        f"The AGS Result container reports results for {sorted(container)} and this section's "
        f"three students are {sorted(student.subject for student in everybody)}. A student the "
        "platform posted a score for and reports no result for is the two surfaces disagreeing in "
        "the way a comparison over shared keys alone cannot see."
    )

    for student in everybody:
        last = log[student.subject][-1]
        result = container[student.subject]
        assert result.get(RESULT_SCORE_MEMBER) == last.get(sweep_contract.given_member), (
            f"For {student.subject!r} the AGS Result container reports `{RESULT_SCORE_MEMBER}` "
            f"{result.get(RESULT_SCORE_MEMBER)!r} and the last body `GET /mock/posted-scores` "
            f"recorded carries `{sweep_contract.given_member}` "
            f"{last.get(sweep_contract.given_member)!r}. The whole log for this student is "
            f"{log[student.subject]}.\n\n"
            "Two findings look like this and the log tells them apart. If the container's value "
            "matches the *first* entry, the platform files a student's first score and ignores "
            "every later one — a gradebook that stops updating in week two, which no E3 test could "
            "see because they all read the log. If it matches neither, the inspection route and "
            "the AGS implementation are recording different things, and every assertion this epic "
            "makes about what reached a gradebook is an assertion about a log rather than about a "
            "grade."
        )
        assert result.get(RESULT_MAXIMUM_MEMBER) == last.get(sweep_contract.maximum_member), (
            f"For {student.subject!r} the container reports `{RESULT_MAXIMUM_MEMBER}` "
            f"{result.get(RESULT_MAXIMUM_MEMBER)!r} and the last posted body sent "
            f"`{sweep_contract.maximum_member}` {last.get(sweep_contract.maximum_member)!r}. AGS "
            "lets a platform rescale a score to the line item's maximum, so a maximum that "
            "disagrees rescales the whole column while the score itself still reads as a match at "
            "one of the two numbers."
        )
