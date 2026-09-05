"""A section with no line item and one with no gradebook address — ticket E3-06, criterion 8.

> The suite runs the sweep against a section with no line item and against a
> section with no AGS address, and neither raises.

Both states are ordinary rather than exceptional, which is why the criterion
exists. A section acquires its "Pulse Participation" line item on the first staff
launch (SPEC §3.4, E3-05), so every section is in the first state between the day
it is provisioned and the day an instructor first opens the tool — and a Monday
sweep runs across all of them. The second state is SPEC §7.3's never-synced
shape: a platform that advertised no AGS endpoint claim, or a launch that carried
none, leaves the column NULL for ever and no amount of retrying will change it.

**What the first one does instead of posting** is work order D8, which is ADR
0135's named window: the section gets `request_line_item_creation` — the bounded
publish E3-05 already built, which never raises and enqueues nothing it should
not — and no posting this run. That is the backstop for a section whose launch
happened before E3-05 shipped, or whose creation task failed, and it costs one
publish rather than a second schedule.

**Neither test asserts a raise, and both assert an absence.** An absence is the
weakest kind of evidence (`docs/MISTAKES.md` entry 3), so each is paired with
something the same run must positively do: the first requires the creation
trigger to have been asked for, and the second requires that the wire — the same
wire that carries every post in this suite — recorded nothing at all while the
section that could not be addressed was walked past.

**Which failure a red here is.** Before E3-06 lands both tests are expected red
on `pytest.fail` naming `app.services.grading` as a module that exposes no
`post_scores_for_all_sections`, from a plain call in the test body
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`.

TRIGGER_IS_OWED = (
    "E3-05's work order (D3) ships `request_line_item_creation(session, section_id)` in "
    "`app.services.grading`: the bounded publish the launch door calls, which enqueues nothing for "
    "a section with no container address or with a line-item id already stored and which never "
    "raises. E3-06's work order (D8) reuses it as the sweep's line-item backstop rather than "
    "adding a second schedule."
)


class ARecordedTrigger:
    """A stand-in for E3-05's bounded publish that records its calls and answers `False`.

    Two jobs, and the second is what keeps the test from proving nothing. It
    stops the real trigger publishing to a broker this process does not have —
    which under `.env.example`'s default address is a name that does not resolve
    here — and it **counts its calls**, because a sweep that reached the trigger
    by another route would leave the real one running, the real one never
    raises, and the test would be green having pinned nothing
    (`docs/MISTAKES.md` entry 3).

    Substituted on `app.services.grading` itself, which D8 makes the module the
    sweep calls it from. A `from … import request_line_item_creation` elsewhere
    would bind the original and this substitution would silently do nothing —
    worth naming rather than discovering, and it is the first thing to look at
    if this test fails with no calls recorded.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *arguments: Any, **keywords: Any) -> bool:
        self.calls.append((arguments, keywords))
        return False


def test_a_section_with_a_gradebook_and_no_line_item_asks_for_one_and_posts_nothing(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 8's first half, and D8's backstop.

    The section is fully ready to post — a container address the platform
    serves, a student with a closed window and a full set of answers — and
    carries no `ags_line_item_url`. So the only thing standing between it and a
    post is the missing line item, which is what makes this a statement about
    that column rather than about a section nothing would have posted for
    anyway.

    Three things are required, and none implies the others. Nothing raised, which
    is the criterion's own word. Nothing was posted and no `grade_sync` row was
    written, because a score posted to an address the section does not hold goes
    somewhere nobody chose. And the creation trigger was asked for exactly once
    for this section, which is D8: a section stuck without a line item is asked
    for one on every sweep until it has one, rather than being skipped for ever
    and waiting for a staff launch that may never come again.

    **The mutations this kills**: a sweep that dereferences a NULL line-item
    column and raises, taking every section after it in the walk with it — the
    plainest reading of criterion 8; a sweep that walks past the section
    silently, which leaves ADR 0135's window open with nothing to close it; and
    a sweep that asks for a line item and posts anyway against whatever
    `find_or_create` answers, which is the reconciliation this ticket puts out of
    scope.

    **The substitution is asserted to have taken** before its call count is
    believed, and the count is one rather than merely non-zero: a trigger asked
    once per student rather than once per section is a publish per person per
    week.
    """
    book = gradebooks(line_item=False)
    (student,) = sweep_contract.students(book, 1)
    sweep_contract.answered_fully(book.world, student, through=1)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, 1)

    grading = sweep_contract.grading()
    sweep_contract.named_in(grading, sweep_contract.request_line_item_creation, TRIGGER_IS_OWED)
    trigger = ARecordedTrigger()
    monkeypatch.setattr(grading, sweep_contract.request_line_item_creation, trigger)
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, (
        f"The sweep raised {raised!r} on a section carrying a gradebook address and no line item. "
        "Criterion 8: 'The suite runs the sweep against a section with no line item … and neither "
        "raises.' Every section is in this state between the day it is provisioned and the day an "
        "instructor first opens the tool, so a raise here stops the Monday walk at the first new "
        "course of the term."
    )
    assert len(trigger.calls) == 1, (
        f"The creation trigger was called {len(trigger.calls)} times: {trigger.calls}. D8 has a "
        "section inside the bound with a container address and no stored line item ask for one — "
        "ADR 0135's named window, closed by reusing the launch trigger's own bounded publish. Zero "
        "calls means the section is skipped for ever unless a staff launch happens to arrive; more "
        "than one means the ask is per student rather than per section, which is a publish per "
        "person per week.\n\n"
        "If this reads zero and the sweep otherwise works, the substitution may not have taken: D8 "
        f"has the sweep call `{sweep_contract.request_line_item_creation}` on its own module, and "
        "a `from … import` of it elsewhere would bind the original."
    )
    assert not grade_sync_rows.all_rows(), (
        f"`grade_sync` holds {grade_sync_rows.all_rows()} for a section with nowhere to post. A "
        "row here claims a delivery to an address this section does not have."
    )
    assert answered == {sweep_contract.posted_key: 0, sweep_contract.failed_key: 0}, (
        f"The sweep answered {answered!r} for a section it could not post to. D8 gives this "
        "section a creation request and no posting this run, so neither counter moves: a failure "
        "counted here would put a section that is merely new into E11's list of sections whose "
        "posts are failing."
    )


def test_a_section_with_no_gradebook_address_is_walked_past_without_a_raise_or_a_call(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """Criterion 8's second half: SPEC §7.3's never-synced shape.

    A section whose `lms_ags_line_items_url` is NULL has no gradebook this tool
    can reach — the platform advertised no AGS endpoint claim, or the launch
    carried none — and no retry will produce one. The sweep must walk past it,
    and it must not reach the network on its behalf: there is no address to
    dial, so any call made here is a call made to somewhere this section never
    named.

    **The absence is paired with the wire's own liveness.** The same wire that
    carries every post in this suite is required to have recorded nothing, and
    the section is otherwise fully ready to post — a student, a closed window,
    a complete set of answers — so the emptiness is a decision about this column
    rather than a world in which nothing was ever going to happen.

    **The mutations this kills**: a NULL container read straight into a URL
    join, which either raises or produces an address like `None/lineitems` and
    dials it; and a sweep that treats a missing container the way it treats a
    missing line item, asking for a creation that E3-05's trigger will decline
    anyway — harmless, and still a publish per section per week for every
    section in the institution that will never have a gradebook.
    """
    book = gradebooks(container=False, line_item=False)
    (student,) = sweep_contract.students(book, 1)
    sweep_contract.answered_fully(book.world, student, through=1)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, 1)

    assert book.section.container is None, (
        f"The section carries {book.section.container!r} in "
        f"`{sweep_contract.container_column}`, and this test needs it NULL — that is the whole "
        "state it is about, and with an address stored it is posing the ordinary case."
    )
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, (
        f"The sweep raised {raised!r} on a section with no AGS address at all. Criterion 8: "
        "'…and against a section with no AGS address, and neither raises.' SPEC §7.3 makes that a "
        "shape a conformant platform is allowed to leave behind, so a raise here is one platform's "
        "configuration stopping every section in the institution."
    )
    assert not book.wire.calls, (
        f"The sweep made {[f'{call.method} {call.url}' for call in book.wire.calls]} for a section "
        "that names no gradebook. There is no address to dial, so every one of these went "
        "somewhere this section never advertised — which for a NULL joined into a URL is whatever "
        "host the string happens to parse as."
    )
    assert (
        not grade_sync_rows.all_rows()
    ), f"`grade_sync` holds {grade_sync_rows.all_rows()} for a section with no gradebook."
    assert answered == {
        sweep_contract.posted_key: 0,
        sweep_contract.failed_key: 0,
    }, f"The sweep answered {answered!r} for a section it never touched."
