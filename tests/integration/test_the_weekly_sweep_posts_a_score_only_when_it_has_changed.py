"""The recompute posts on a difference and on nothing else — ticket E3-06, criteria 1, 2 and 3.

SPEC §3.4, the sentence this module is the whole of:

> Re-posted whenever a recomputation changes the value, ordinarily after each
> week closes; fully automatic, no instructor action or override. … the
> recompute posts a value only when it differs from the last one sent. A section
> with no elapsed weeks has no score posted yet — an absent score, never a
> posted zero.

**Why a difference and not a schedule.** A posted score is not final when its
week closes: E2-08's asynchronous reclassification can flip a comment that fell
to §3.3's fail-open floor from substantive to `insufficient` weeks after the
window shut, which lowers the numerator of a score already sitting in somebody's
gradebook. ADR 0124 makes `grade_sync` append-only for exactly that case, and
this module is where the three consequences are asserted: the first post, the
run that changes nothing, and the re-post that supersedes without erasing.

**Where the evidence comes from, and it is three places on purpose.**

  - **The wire** (`ServiceWire`) records every request as it left the sweep.
    Criterion 2 says in as many words that the second run is "asserted against
    the call log, not against the gradebook, because an idempotent post and an
    absent post look the same in a gradebook" — so the no-HTTP assertions are
    made here and repeated against `ags_call`, which is the row an operator
    reads (SPEC §6.1). Two witnesses, because a sweep that made the call and
    logged nothing and a sweep that made no call are different defects.
  - **`GET /mock/posted-scores`** is what the platform received, verbatim (ADR
    0047), and it is the only surface that can say what was *sent*: a conformant
    AGS `Result` carries no timestamp and no comment, so the fields these
    criteria are about cannot come back through the protocol at all.
  - **`grade_sync`** is Pulse's own account of what it told a platform about a
    student's standing, and criterion 3 is a claim about the rows.

**Every planted row is planted by this module, never by a first run of the thing
under test.** `docs/MISTAKES.md` entry 31 is named in this ticket's own traps
list, and it is the reason the idempotence case does not begin by sweeping once:
a sweep that wrote a row saying it had posted, and then declined to post because
of the row it had just written, is idempotent against itself and against nothing
else.

**Every "latest row" case plants a second, older row for the same pair, inserted
last.** ADR 0124: "Every reader must ask for the latest row and not for 'the'
row", which is `docs/MISTAKES.md` entry 3 wearing a green tick. A reader that
answers with the last row written, the highest key, or an unordered first row is
wrong on these fixtures and right on any fixture built the obvious way.

**Which failure a red here is.** Before E3-06 lands every criterion test is
expected red on `pytest.fail` naming `app.services.grading` as a module that
exposes no `post_scores_for_all_sections`. That guard is a plain call in a test
body, never in a fixture (`docs/MISTAKES.md` entry 44), so an unbuilt tree reads
as FAILED naming the deliverable rather than as a wall of setup errors.

**The controls come first and they must be green today. A red in that section
means these tests are broken, not the code.**
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`; `ags_sections` and `ags_contract` from
# `tests/fixtures/ags_client.py`. All are reached as fixtures rather than
# imported, for the reason every module in this suite gives: an import of a
# fixtures module by name depends on where pytest put `tests/` on `sys.path`,
# and an import error is not a red.

# Instants for the rows this module plants. **They are this module's own and
# nothing reads them back as an answer** — what a planted row's `created_at`
# decides is only which of two rows is newer, which is the question ADR 0124
# makes every reader answer.
#
# **They sit in the real past, and dispute E3-06-01 is why.** `grade_sync.
# created_at` defaults to `now()`, and ADR 0109 keeps that class of instant —
# when a row was written — on real time rather than on the development
# override. So a row the sweep appends carries the machine's own clock, and a
# planted row dated inside this section's Fall 2026 calendar sorts *after*
# anything a real clock can produce: the criterion-3 test below then reads the
# planted row as the newer of the two, and the only implementation that could
# satisfy it is one that stamps the comparison key from a clock a demo can
# rewind. Any instant before real time serves, and only their relative order is
# used. Mondays at 02:20 — the beat's own slot — are kept from the original
# constants, and now say what they were meant to say: the sweep wrote this row
# on a Monday a few weeks ago.
AN_EARLIER_WRITE = datetime(2026, 8, 3, 2, 20, tzinfo=UTC)
A_LATER_WRITE = datetime(2026, 8, 10, 2, 20, tzinfo=UTC)
A_LATEST_WRITE = datetime(2026, 8, 17, 2, 20, tzinfo=UTC)

# The timestamp a planted row says it sent, kept apart from the `created_at`
# values above so a reader that confused the two is visible.
A_SENT_INSTANT = datetime(2026, 10, 6, 2, 19, 58, 500000, tzinfo=UTC)


def a_gradebook_with_answers(
    gradebooks: Any,
    sweep_contract: Any,
    *,
    students: int = 2,
    through: int = 1,
) -> tuple[Any, list[Any]]:
    """One section with a stored line item, `students` enrolled, every week answered fully.

    The clock is deliberately **not** moved here: which side of a window's close
    a run stands on is the whole subject of criterion 1, and a fixture that
    chose it would be answering that criterion (`docs/MISTAKES.md` entry 30).
    """
    book = gradebooks()
    people = sweep_contract.students(book, students)
    for student in people:
        sweep_contract.answered_fully(book.world, student, through=through)
    book.world.rows.commit()
    return book, people


def swept(book: Any, sweep_contract: Any, window_settings: Any) -> Any:
    """Run the sweep over everything, requiring it not to raise, and answer its dict."""
    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )
    assert raised is None, (
        f"The sweep raised {raised!r}. E3-06's work order (D1) has a section that fails "
        "unexpectedly logged and stepped over so the walk continues — an escape out of the entry "
        "point stops every remaining section in the institution, and the Celery task above it "
        "turns that into a task failure an operator has to read a traceback to understand."
    )
    return answered


def outcome_of(row: dict[str, Any], sweep_contract: Any) -> str:
    """One `grade_sync` row's outcome, as a plain string whichever way the enum comes back."""
    value = row[sweep_contract.outcome_column]
    return str(getattr(value, "value", value))


def bodies_for(book: Any, subject: str, sweep_contract: Any) -> list[dict[str, Any]]:
    """Every score body the platform recorded for one student, in arrival order."""
    return [
        sweep_contract.body(entry)
        for entry in book.posted()
        if str(entry.get(sweep_contract.user_member)) == subject
    ]


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_section_this_module_builds_is_a_gradebook_and_a_term_of_answers_at_once(
    gradebooks: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """A control: the world these criteria are measured over really is both halves.

    Every test below rests on one section being two things at the same time — a
    gradebook the AGS client can reach, and a section the participation formula
    can score. Those come from two fixtures that were built for different
    tickets and seed on different connections, and `SweptWorld` is the join. If
    the join were broken the criteria would fail for that reason and the failure
    would name E3-06, which is the wrong ticket.

    Four things are required, and each fails differently. The section stores a
    line item the platform serves, so there is somewhere to post. The line
    item's container holds it, so the stored address is real. The formula
    answers a score for each enrolled student, so there is something to post.
    And the platform has recorded no score yet, so every "the platform holds X"
    assertion below is about a delivery this module caused.

    Green today. Nothing here calls anything E3-06 adds.
    """
    book, people = a_gradebook_with_answers(gradebooks, sweep_contract)
    book.world.elapsed_through(committed_clock_overrides, 1)

    assert book.line_item_url, (
        "The section carries no stored line item, so there is no address for a score to be posted "
        "to and every posting assertion below would be about a section the sweep must skip."
    )
    listed = [
        item.get("id")
        for page in book.platform.line_item_pages(book.context.launches[0])
        for item in page
    ]
    assert book.line_item_url in listed, (
        f"The section points at {book.line_item_url!r} and the platform's container holds "
        f"{listed}. A stored id the platform does not serve is a score posted to nothing, and this "
        "module's readback would be reading an address nobody writes to."
    )
    answers = book.world.scores(settings=window_settings)
    assert len(answers) == len(people), (
        f"`participation_scores` answered {len(answers)} entries for {len(people)} enrolled "
        "students. E3-03 answers one entry per enrolled student with at least one elapsed enrolled "
        "week; with fewer, the sweep has nothing to post for somebody and 'a score per student' "
        "below would be satisfied by a formula that skipped them."
    )
    assert not book.posted(), (
        f"The platform has already recorded {book.posted()} against this line item before anything "
        "posted. Then 'the platform holds the value the sweep sent' is satisfied by a delivery this "
        "module did not make."
    )


def test_the_wire_this_module_reads_records_what_the_sweep_sends_and_refuses_a_stranger(
    gradebooks: Any, sweep_contract: Any
) -> None:
    """A control: the call log criterion 2 rests on can see a call and can refuse one.

    Criterion 2's assertion is that a list is **empty**, and an empty list is
    what a broken recorder produces as readily as a sweep that made no call
    (`docs/MISTAKES.md` entry 3). So the same wire is driven here against the
    section's own gradebook container, where it must record a request and get a
    status back, and against a host nothing mounted, where it must refuse — the
    thing that stands between "the sweep dialled somewhere it should not" and a
    silent pass.

    Green today. The wire is E1-11's and the container is E0-15's.
    """
    book = gradebooks()
    session = book.wire.session()

    answered = session.get(book.section.container or "")
    assert answered.status_code in (200, 401, 403), (
        f"The wire answered {answered.status_code} for the section's own container address "
        f"{book.section.container!r}. A status means the request reached the platform — which "
        "credential it needs is E3-04's business — and anything else means the host is not "
        "mounted, so the sweep could never reach this gradebook through this transport."
    )
    assert book.wire.calls, (
        "The wire recorded no call after one was made over it. Every 'no HTTP happened' assertion "
        "below would then be true of a recorder that records nothing."
    )
    with pytest.raises(Exception, match="no application is mounted"):
        session.get("http://a-platform-nobody-registered.invalid/lineitems/1/scores")


# ---------------------------------------------------------------------------
# Criterion 1 — the first closed window posts, and an unclosed one posts nothing.
# ---------------------------------------------------------------------------


def test_a_section_whose_first_window_has_closed_gets_one_post_for_each_enrolled_student(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """Criterion 1, first half.

    > A section whose first window has closed gets a score posted for each
    > enrolled student.

    Two students, both fully answered for course week 1, and the clock a minute
    past that window's close. Afterwards each student has exactly one
    `grade_sync` row marked posted, and the platform's own log holds one score
    for each of their subjects — asserted per student rather than as a count,
    because "two posts happened" is equally true of a sweep that posted one
    student's score twice.

    **The mutations this kills**: the sweep absent altogether, which is the
    state at HEAD; a sweep that walks sections and not students, so one post
    lands for the section and one student is silently ungraded; and a sweep that
    posts and records nothing, which leaves the next run unable to tell a
    changed value from an unchanged one and re-posts every student for ever.

    **The near miss it must not fire on** is the unclosed-window half below, at
    the same door with the same students: a sweep written as "post whatever the
    formula answers" passes this test and fails that one.

    **The returned dict is asserted too**, because the task above the service
    returns it and E11's job dashboard is the reader: a sweep that posted
    correctly and reported nothing leaves an operator with no way to see it ran.
    """
    book, people = a_gradebook_with_answers(gradebooks, sweep_contract)
    book.world.elapsed_through(committed_clock_overrides, 1)
    expected = {
        student.subject: sweep_contract.computed(book.world, student, settings=window_settings)
        for student in people
    }

    answered = swept(book, sweep_contract, window_settings)

    for student in people:
        rows = grade_sync_rows.for_pair(book.id, student.user_id)
        assert len(rows) == 1, (
            f"There are {len(rows)} `grade_sync` rows for {student.subject!r} after one sweep of a "
            f"section whose first window has closed: {rows}. SPEC §3.4 posts a score for each "
            "enrolled student once the first week is over, and ADR 0124 makes every attempt a row "
            "— none means nothing was posted or nothing was recorded, and more than one means the "
            "sweep posted twice in a single walk."
        )
        assert outcome_of(rows[0], sweep_contract) == grade_sync_rows.outcomes()["posted"], (
            f"The row for {student.subject!r} carries outcome "
            f"{outcome_of(rows[0], sweep_contract)!r}. A failed attempt recorded as a post is a "
            "gradebook Pulse believes it has written to."
        )
        assert rows[0][sweep_contract.score_text_column] == expected[student.subject].percentage, (
            f"The row for {student.subject!r} records "
            f"{rows[0][sweep_contract.score_text_column]!r} and `participation_scores` computed "
            f"{expected[student.subject].percentage!r}. ADR 0124 stores 'the exact string, not a "
            "number to be re-rendered', because ADR 0052's retry identity is byte equality of a "
            "body the platform already accepted — a row that disagrees with what was computed "
            "cannot reconstruct the delivery it claims to describe."
        )
        recorded = bodies_for(book, student.subject, sweep_contract)
        assert len(recorded) == 1, (
            f"The platform recorded {len(recorded)} scores for {student.subject!r}: {recorded}. "
            "Zero is a student this sweep left ungraded while grading their classmate; two is a "
            "single walk delivering the same score twice, which ADR 0052 makes the platform accept "
            "silently when the timestamps agree."
        )
    assert answered == {sweep_contract.posted_key: len(people), sweep_contract.failed_key: 0}, (
        f"The sweep answered {answered!r} after posting for {len(people)} students with nothing "
        f"failing. E3-06's work order (D1) settles the shape: "
        f'`{{"{sweep_contract.posted_key}": p, "{sweep_contract.failed_key}": f}}` with integer '
        "counts, returned by the task so E11's job dashboard has something true to render."
    )


def test_a_section_whose_first_window_has_not_closed_gets_no_post_at_all_and_not_a_zero(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """Criterion 1, second half, and both directions of the boundary in one run.

    > A section whose first window has not closed gets no post at all, not a
    > posted zero.

    SPEC §3.4: "an absent score, never a posted zero, because a zero in a
    gradebook is a statement about a student and only absence is true before the
    first week closes." A student who sees a zero in week one has been told
    something false about themselves by a tool that has no information yet.

    **Both sides of the line, a minute apart.** The clock stands a minute before
    course week 1's window closes and the sweep is required to touch nothing at
    all — no HTTP on the wire, no `ags_call` row, no `grade_sync` row, and
    nothing in the platform's score log. Then it is moved a minute past the same
    close and the same sweep is required to post. An offset clock cannot stand
    exactly on an instant (ADR 0109), so the pair sits a minute either side; a
    minute is four orders of magnitude inside the week it has to be
    distinguished from.

    **The mutations this kills**: a sweep that posts `participation_scores`'
    answer for every enrolled student without asking whether any week has
    elapsed — which posts a zero, because a student with no elapsed weeks has
    completed none of no items; and a sweep whose elapsed test reads the wrong
    side of the comparison, which the second half catches by refusing to post
    after the window has shut.

    **The refusal is asserted as an absence of calls, and the absence is proved
    to be a real one by the accepting half in the same test** — without it, this
    would be equally satisfied by a sweep that does nothing ever, which is the
    state at HEAD.
    """
    book, people = a_gradebook_with_answers(gradebooks, sweep_contract)
    book.world.not_yet_closed(committed_clock_overrides, 1)
    book.wire.calls.clear()

    before = swept(book, sweep_contract, window_settings)

    assert not book.wire.calls, (
        f"The sweep made {[f'{call.method} {call.url}' for call in book.wire.calls]} for a section "
        "whose first window has not closed. There is nothing to post yet, so there is nothing to "
        "authorise and nothing to ask the platform — a call made here is this tool reaching into a "
        "gradebook about a week that is still open."
    )
    assert not grade_sync_rows.all_rows(), (
        f"`grade_sync` holds {grade_sync_rows.all_rows()} after a sweep that had nothing to post. "
        "A row here says Pulse told the platform something, and before the first window closes "
        "there is nothing true to tell it."
    )
    assert not book.posted(), (
        f"The platform recorded {book.posted()} before this section's first window closed. SPEC "
        "§3.4: an absent score, never a posted zero — a zero in a gradebook is a statement about a "
        "student, and this one would be false."
    )
    assert before == {
        sweep_contract.posted_key: 0,
        sweep_contract.failed_key: 0,
    }, f"The sweep answered {before!r} having posted nothing and failed nothing."

    book.world.elapsed_through(committed_clock_overrides, 1)
    book.wire.calls.clear()

    after = swept(book, sweep_contract, window_settings)

    assert after == {sweep_contract.posted_key: len(people), sweep_contract.failed_key: 0}, (
        f"With the same section a minute *past* its first window's close the sweep answered "
        f"{after!r} rather than one post per enrolled student. Without this half, the refusal above "
        "holds of a sweep that never posts anything at all — which is exactly the tree these tests "
        "were written against."
    )
    assert len(book.posted()) == len(people), (
        f"The platform recorded {book.posted()} after the window closed. The refusal above is only "
        "evidence if the same section, the same students and the same clock service produce a post "
        "on the other side of the boundary."
    )


# ---------------------------------------------------------------------------
# Criterion 2 — running it twice posts once, and the ledger is part of the test.
# ---------------------------------------------------------------------------


def test_a_sweep_that_finds_the_latest_row_already_carrying_the_computed_pair_makes_no_call(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """Criterion 2, and the ledger's place in the comparison.

    > Running the sweep twice in a row posts once. The second run reads
    > `grade_sync`, finds no difference, and makes no HTTP call — asserted
    > against the call log, not against the gradebook, because an idempotent post
    > and an absent post look the same in a gradebook.

    **The row the sweep compares against is planted by this test.**
    `docs/MISTAKES.md` entry 31, named in this ticket's own traps section: a
    second run tested only against a database the first run filled proves that
    the sweep agrees with itself. Here the row is written by the test, carrying
    exactly what `participation_scores` answers, and the sweep meets it as it
    would meet last week's.

    **Then the ledger alone is changed, and the sweep must post.** SPEC §3.4
    makes the per-week ledger part of what is delivered — "every posted score
    carries the ledger" — so a comparison over the percentage alone is a
    comparison over half the payload. A reclassification in one week of a
    student who was going to score the same percentage anyway, a question set
    that changed a week's denominator, a late add that moved which weeks count:
    each of those can leave the number equal and the arithmetic behind it
    different, and under a percentage-only comparison the platform would keep
    showing a ledger that no longer explains the grade it sits beside. That is
    ADR 0125's whole subject.

    **The mutations this kills**: the comparison flipped, `==` for `!=`, which
    posts exactly when it should not and is invisible to any test that only
    counts posts after one run; the comparison narrowed to the percentage,
    caught by the second half; and the comparison dropped altogether, which the
    first half catches as a call that should not have been made.

    **The pair is the whole instrument.** The refusing half alone is satisfied by
    a sweep that never posts; the accepting half alone by a sweep that always
    does. Both run against one section, one platform and one clock, with one
    value changed between them.
    """
    book, people = a_gradebook_with_answers(gradebooks, sweep_contract, students=1)
    student = people[0]
    book.world.elapsed_through(committed_clock_overrides, 1)
    expected = sweep_contract.computed(book.world, student, settings=window_settings)
    outcomes = grade_sync_rows.outcomes()
    grade_sync_rows.plant(
        section_id=book.id,
        user_id=student.user_id,
        score_text=expected.percentage,
        ledger_text=expected.ledger,
        outcome=outcomes["posted"],
        score_timestamp=A_SENT_INSTANT,
        created_at=AN_EARLIER_WRITE,
        response_code=200,
    )
    book.wire.calls.clear()

    swept(book, sweep_contract, window_settings)

    assert not book.wire.calls, (
        f"The sweep made {[f'{call.method} {call.url}' for call in book.wire.calls]} for a student "
        "whose latest `grade_sync` row already carries the score and ledger the formula computes. "
        "Criterion 2 asserts this against the call log rather than the gradebook, because a "
        "re-post of an identical body is invisible in a gradebook and is still a request this tool "
        "had no reason to make — thirty thousand of them every Monday morning, against every "
        "platform at once."
    )
    assert not grade_sync_rows.calls(), (
        f"`ags_call` holds {grade_sync_rows.calls()} after a sweep that should have made no HTTP "
        "call. §6.1 puts that log at the grain of one call the tool made, so a row here is a "
        "second witness that a call happened — and if the wire saw none and this did, the two "
        "disagree and the sweep is reaching the platform by some route this suite cannot see."
    )
    unchanged = grade_sync_rows.for_pair(book.id, student.user_id)
    assert len(unchanged) == 1, (
        f"There are {len(unchanged)} `grade_sync` rows for this student after a sweep that posted "
        f"nothing: {unchanged}. A row appended for a post that never happened is a false account "
        "of what Pulse sent, and the next sweep compares against it."
    )

    grade_sync_rows.plant(
        section_id=book.id,
        user_id=student.user_id,
        score_text=expected.percentage,
        ledger_text=sweep_contract.a_differing_ledger,
        outcome=outcomes["posted"],
        score_timestamp=A_SENT_INSTANT,
        created_at=A_LATER_WRITE,
        response_code=200,
    )
    book.wire.calls.clear()

    swept(book, sweep_contract, window_settings)

    posted = book.posted()
    assert len(posted) == 1, (
        f"The platform recorded {posted} after the latest `grade_sync` row was changed to carry the "
        f"same percentage ({expected.percentage!r}) and a different ledger. The comparison E3-06 "
        "makes is over the pair the delivery carries, not over the number alone: SPEC §3.4 puts "
        "the per-week arithmetic in the AGS comment and ADR 0125 makes that comment the only place "
        "anyone can see it, so a stale ledger beside a correct percentage is the one visible "
        "artefact of the reclassification the epic exists to handle."
    )
    assert sweep_contract.body(posted[-1]).get(sweep_contract.comment_member) == expected.ledger, (
        f"The platform holds the comment "
        f"{sweep_contract.body(posted[-1]).get(sweep_contract.comment_member)!r} and the formula "
        f"produced {expected.ledger!r}. The post that closed the difference has to carry the "
        "current ledger; one that re-sent the stale one changed nothing and will be made again "
        "next week."
    )


def test_the_sweep_compares_against_the_newest_row_and_not_the_last_one_written(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """ADR 0124's named failure mode, planted rather than described.

    > Every reader must ask for the latest row and not for "the" row … a query
    > that happens to return one row in a test fixture and the wrong row in a
    > term's worth of data.

    Two rows for one `(section_id, user_id)` pair. The one that **matches** what
    the formula computes is written first and carries the later `created_at`;
    the one that **differs** is written second and carries the earlier one. A
    reader whose "latest" means the last row inserted, the highest primary key,
    or an unordered `LIMIT 1` sees the differing row and posts; a reader that
    orders by `created_at` sees the matching one and does not.

    **Both directions, on one section.** A third row is then written, newer than
    both and differing, and the sweep must post — without which this test is
    satisfied by a sweep that never posts at all, which is the state at HEAD.

    **The mutation this kills**: `ORDER BY created_at DESC` dropped from the
    lookup, or replaced by the primary key. Primary keys here are
    server-generated random uuids (ADR 0016), so ordering by one is a coin toss
    per run and the failure would be a flake in somebody else's module rather
    than a red here.

    **The near miss it must survive**: ordering on `score_timestamp` instead of
    `created_at`. The two are deliberately given the *same* relative order in
    this fixture, because they have the same order in production too and this
    module is not the place that decides which one a reader keys on. What it
    does decide is that the older row does not win.
    """
    book, people = a_gradebook_with_answers(gradebooks, sweep_contract, students=1)
    student = people[0]
    book.world.elapsed_through(committed_clock_overrides, 1)
    expected = sweep_contract.computed(book.world, student, settings=window_settings)
    outcomes = grade_sync_rows.outcomes()

    grade_sync_rows.plant(
        section_id=book.id,
        user_id=student.user_id,
        score_text=expected.percentage,
        ledger_text=expected.ledger,
        outcome=outcomes["posted"],
        score_timestamp=A_SENT_INSTANT,
        created_at=A_LATER_WRITE,
        response_code=200,
    )
    grade_sync_rows.plant(
        section_id=book.id,
        user_id=student.user_id,
        score_text=sweep_contract.a_differing_score,
        ledger_text=sweep_contract.a_differing_ledger,
        outcome=outcomes["posted"],
        score_timestamp=A_SENT_INSTANT - timedelta(days=7),
        created_at=AN_EARLIER_WRITE,
        response_code=200,
    )
    book.wire.calls.clear()

    swept(book, sweep_contract, window_settings)

    assert not book.wire.calls, (
        f"The sweep made {[f'{call.method} {call.url}' for call in book.wire.calls]}. The newest "
        f"row for this pair carries {expected.percentage!r} — what the formula computes — and the "
        f"older one carries {sweep_contract.a_differing_score!r}. A call here means the older row "
        "was read as the current one, which against a term's worth of posts re-sends whatever a "
        "student's score happened to be in September."
    )

    grade_sync_rows.plant(
        section_id=book.id,
        user_id=student.user_id,
        score_text=sweep_contract.a_differing_score,
        ledger_text=sweep_contract.a_differing_ledger,
        outcome=outcomes["posted"],
        score_timestamp=A_SENT_INSTANT + timedelta(days=7),
        created_at=A_LATEST_WRITE,
        response_code=200,
    )
    book.wire.calls.clear()

    swept(book, sweep_contract, window_settings)

    assert len(book.posted()) == 1, (
        f"With the newest of three rows now differing from the computed value, the platform "
        f"recorded {book.posted()}. Without this half the refusal above holds of a sweep that "
        "never posts, and every 'the latest row won' claim in this module would be evidence about "
        "a sweep that reads no rows at all."
    )


# ---------------------------------------------------------------------------
# Criterion 3 — a reclassification lowers a posted score, and both rows survive.
# ---------------------------------------------------------------------------


def test_a_reclassification_that_lowers_a_posted_week_posts_again_and_leaves_both_rows(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """Criterion 3, which the ticket gives a test of its own and ADR 0124 exists for.

    > A reclassification that lowers an already-posted week's numerator causes
    > the next sweep to post the lower value, and `grade_sync` afterwards holds
    > **both** rows — the higher value that was sent first and the lower one that
    > superseded it, each with its own timestamp.

    The case the epic is built around. A comment accepted under §3.3's fail-open
    floor is classified later; the later verdict refuses it; the week's numerator
    drops; and a student who saw 92% sees 85% without having done anything. The
    behaviour is correct and the record of it is the whole point: the question
    asked when a grade is disputed is *what did we send, and when*, and only an
    append-only log can answer it.

    **The higher post is planted by this test, not produced by a first sweep**
    (`docs/MISTAKES.md` entry 31). The reclassification is then appended as a
    new `classification` row, which is how a verdict changes at all (ADR 0055,
    and `pulse_app` holds `SELECT, INSERT` on that table and nothing else).

    **The row count is the assertion, and that is deliberate.** A sweep that
    updated the existing row in place would leave the platform holding the right
    number and Pulse holding no record that the higher one was ever sent — and
    it would pass every other test in this module. It is *also* refused by the
    grant, since `pulse_app` has no `UPDATE` on `grade_sync`; asserting the two
    rows rather than the missing grant is what pins the layer, because a test
    satisfied by the database's refusal says nothing about what the sweep tried
    to do and would go green again the day the grant widened for some other
    reason.

    **Each row keeps its own timestamp**, which is what makes the two deliveries
    distinguishable: ADR 0052 has a platform accept an equal timestamp as a
    retry of the same delivery, so two rows sharing one would be one delivery
    recorded twice rather than a supersession.

    **This is the only test in the module that orders a planted row against a
    swept one**, and dispute E3-06-01 was decided on it. The planted row is
    dated in the real past so that the row the sweep appends — `created_at`
    defaults to `now()`, which ADR 0109 keeps on real time — is the newer of the
    two, which is what makes `rows[0]` the sweep's and `rows[-1]` this test's.
    The constants were first written inside the section's Fall 2026 calendar,
    which sorts *after* the machine's clock, and the assertions below then
    passed only against a sweep that stamped `created_at` from the development
    clock — a comparison key any demo's rewind could reorder.

    **The precondition is asserted before the sweep**: the reclassification is
    required to have actually lowered the computed value. Without that check a
    run where the new verdict changed nothing would report the sweep's silence
    as correct, when in fact nothing was ever different (`docs/MISTAKES.md`
    entry 3).
    """
    book, people = a_gradebook_with_answers(gradebooks, sweep_contract, students=1, through=0)
    student = people[0]
    week_one = book.world.answer_week(student, 1)
    book.world.answer_week(student, 2)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, 2)
    higher = sweep_contract.computed(book.world, student, settings=window_settings)
    outcomes = grade_sync_rows.outcomes()
    grade_sync_rows.plant(
        section_id=book.id,
        user_id=student.user_id,
        score_text=higher.percentage,
        ledger_text=higher.ledger,
        outcome=outcomes["posted"],
        score_timestamp=A_SENT_INSTANT,
        created_at=AN_EARLIER_WRITE,
        response_code=200,
    )

    comments = book.world.comment_positions()
    assert comments, (
        "The question set in force carries no comment item, so no reclassification can lower "
        "anything and this test cannot pose its case. SPEC §3.2's five-question set has two."
    )
    book.world.classify(
        week_one[comments[0]],
        sweep_contract.insufficient,
        classified_at=book.world.closes_at(1) + timedelta(days=3),
    )
    book.world.rows.commit()
    lower = sweep_contract.computed(book.world, student, settings=window_settings)

    assert lower.percentage != higher.percentage, (
        f"The reclassification left the computed percentage at {lower.percentage!r}. Criterion 3 is "
        "about a value that changed after it was posted, and with nothing changed the sweep's "
        "silence below would be correct for a reason that has nothing to do with this test."
    )
    book.wire.calls.clear()

    swept(book, sweep_contract, window_settings)

    rows = grade_sync_rows.for_pair(book.id, student.user_id)
    assert len(rows) == 2, (
        f"There are {len(rows)} `grade_sync` rows for this student after a lowered score was "
        f"re-posted: {rows}. ADR 0124 puts this table at the grain of one row per post precisely "
        "for this case — under a row updated in place the higher number, the one a student saw and "
        "an instructor may have acted on, is gone from Pulse entirely, and the answer to 'what did "
        "we send, and when' would have to be reconstructed from request bodies or not at all."
    )
    newest, oldest = rows[0], rows[-1]
    assert oldest[sweep_contract.score_text_column] == higher.percentage, (
        f"The older row now records {oldest[sweep_contract.score_text_column]!r} and it was written "
        f"carrying {higher.percentage!r}. A later post rewrote a row it does not own; the value a "
        "student was shown in a gradebook is now whatever the most recent recomputation produced."
    )
    assert oldest[sweep_contract.ledger_text_column] == higher.ledger, (
        f"The older row's ledger is now {oldest[sweep_contract.ledger_text_column]!r} rather than "
        f"the {higher.ledger!r} it was written with. The ledger is the arithmetic behind the number "
        "that was sent, and a rewritten one explains a grade nobody was ever shown."
    )
    assert newest[sweep_contract.score_text_column] == lower.percentage, (
        f"The newest row records {newest[sweep_contract.score_text_column]!r} and the recomputation "
        f"produced {lower.percentage!r}. §3.3: a later classification that refuses a floored "
        "comment lowers the §3.4 score for that week, including where the week's score has already "
        "been posted."
    )
    assert (
        newest[sweep_contract.score_timestamp_column]
        != oldest[sweep_contract.score_timestamp_column]
    ), (
        "Both rows carry the score timestamp "
        f"{newest[sweep_contract.score_timestamp_column]!r}. ADR 0052 makes an equal timestamp the "
        "mark of a **retry of the same delivery**, so two supersessions sharing one are two rows "
        "describing one post — and the platform, meeting the second, would treat the lower score "
        "as a repeat of the higher rather than as the correction it is."
    )
    posted = book.posted()
    assert posted, (
        "The platform recorded no score at all after the recomputation lowered the value. The row "
        "assertions above would then be about a sweep that writes its own account of posts it "
        "never made."
    )
    delivered = sweep_contract.body(posted[-1]).get(sweep_contract.given_member)
    assert float(delivered) == float(lower.percentage), (
        f"The last score the platform received is {delivered!r} and the lowered value is "
        f"{lower.percentage!r}. §3.4's adjustment is only real once the platform has it; a correct "
        "row beside an unchanged gradebook is Pulse telling itself a story.\n\n"
        "Compared as quantities rather than byte-for-byte on purpose: `scoreGiven` is an RFC 8259 "
        "number and the platform re-serialises it, so the bytes cannot survive the round trip. "
        "Byte identity is E3-04's criterion 3, asserted on the wire in "
        "`test_the_ags_client_is_a_conformant_service_client.py`; what this criterion is about is "
        "that the number changed."
    )
