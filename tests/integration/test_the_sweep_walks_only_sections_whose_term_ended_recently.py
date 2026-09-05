"""How far back a weekly run reaches — ticket E3-06, the bound the ticket sends it to settle.

The ticket's "Decisions this ticket settles" opens with it:

> **The beat slot and cadence**, and how the sweep bounds its own work so a
> weekly run does not walk every section of every past term.

Work order D7 settles the bound: a section is swept while `term.end_date +
TERM_SWEEP_GRACE_DAYS >= clock.today`, with `TERM_SWEEP_GRACE_DAYS = 14`.
Fourteen days is two more sweeps after a term ends — the final week's post plus
one corrective pass for a reclassification that lands late — and the reason it
stops there rather than never is not tidiness. SPEC §4 deletes raw responses at
the end of the retention period and keeps only aggregates; a sweep still walking
a term whose comments have been purged would recompute every student's score
against data that is no longer there and post the result. Stopping well before
that is what keeps a finished term's grades from being quietly rewritten
downwards years later.

**Both sides of the line, one day apart, on one section.** The refusing side runs
first, so that the accepting side is what proves the refusal was a refusal and
not a sweep that does nothing; and they are a single day apart, because a day is
the whole width of a rule expressed in dates.

**A note on what is *not* asserted here.** Nothing in this module says a term
inside the bound is walked *because* of its term — a section with no line item
is skipped for a different reason, and that is criterion 8's module. What this
asserts is only the pair: the same fully-posted-ready section, on two days,
answering differently.

**Which failure a red here is.** Before E3-06 lands this is expected red on
`pytest.fail` naming `app.services.grading` as a module that exposes no
`post_scores_for_all_sections`, from a plain call in the test body
(`docs/MISTAKES.md` entry 44). The grace-days constant has a test of its own in
`tests/unit/test_the_participation_sweep_is_scheduled_weekly_and_run_by_a_task.py`,
which is where the *value* 14 is pinned; here it is used to compute two dates.
"""

from datetime import timedelta
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` and
# `clock_service` from `tests/fixtures/clock.py`.

A_DAY = timedelta(days=1)


def test_a_section_is_swept_on_the_last_day_of_the_grace_window_and_not_on_the_day_after(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
    clock_service: Any,
) -> None:
    """D7's bound, from both sides, on a section that is ready to post either way.

    One section, one enrolled student, every week answered. The clock is stood
    first on `term.end_date + 15` — one day outside — where the sweep must make
    no HTTP call at all and write no row; and then on `term.end_date + 14`,
    where the same sweep must post.

    **The order is deliberate.** The refusing half runs first because a posted
    score changes what the accepting half would find: with the grace day tested
    first, the second run would meet a `grade_sync` row carrying the current
    value and correctly decline to post, and the test would read that silence as
    a bound that is too tight. Run this way round, each half sees the state the
    other one leaves rather than the state it needs.

    **The mutations this kills:**

      - the bound left out, so a Monday-morning run walks every section of every
        past term — an hour of work that grows without limit, against platforms
        that have long since archived the courses, and eventually against terms
        whose comments SPEC §4 has already purged.
      - the comparison flipped, `<=` for `>=`, which sweeps exactly the terms it
        should skip; the refusing half is what sees it.
      - the grace applied to the wrong end — `term.start_date`, or the
        *section's* own `end_date`. A six-week cohort finishing in early
        November sits well inside its term, so a bound measured from the
        section's end would stop posting for it six weeks early while every
        full-term section beside it kept going.
      - an off-by-one on the boundary itself, which one-day-apart halves catch
        and a pair of dates a month apart never could.

    **The control runs first**: the clock service is required to actually read
    the day this test computed, so a run where the override did not take reports
    that rather than reporting a bound that is not there.
    """
    book = gradebooks()
    (student,) = sweep_contract.students(book, 1)
    sweep_contract.answered_fully(book.world, student, through=1)
    book.world.rows.commit()

    last_day = book.term_end_date + timedelta(days=sweep_contract.grace_days_value)
    book.world.clock_at(committed_clock_overrides, last_day + A_DAY)

    effective = clock_service.today(book.session, settings=window_settings)
    assert effective == last_day + A_DAY, (
        f"The clock service reads today as {effective!r} and this test moved the override to "
        f"{last_day + A_DAY!r}. Both halves below are dates measured against the term's own "
        f"`end_date` ({book.term_end_date!r}), so with the clock somewhere else neither half is "
        "the day it claims to be."
    )
    book.wire.calls.clear()

    outside, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r} on a term outside the bound."
    assert not book.wire.calls, (
        f"The sweep made {[f'{call.method} {call.url}' for call in book.wire.calls]} for a section "
        f"whose term ended {book.term_end_date!r}, more than "
        f"{sweep_contract.grace_days_value} days ago. D7 stops the walk there: two sweeps after a "
        "term ends cover the last week's post and one corrective pass, and a run that keeps going "
        "eventually recomputes a finished term against comments SPEC §4's retention has deleted "
        "and posts the answer."
    )
    assert not grade_sync_rows.all_rows(), (
        f"`grade_sync` holds {grade_sync_rows.all_rows()} after a sweep that should have walked "
        "past this section. A row here is Pulse writing about a term it has stopped following."
    )
    assert outside == {
        sweep_contract.posted_key: 0,
        sweep_contract.failed_key: 0,
    }, f"The sweep answered {outside!r} for a section outside its own bound."

    book.world.clock_at(committed_clock_overrides, last_day)
    book.wire.calls.clear()

    inside, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r} on the last day of the grace window."
    assert inside == {sweep_contract.posted_key: 1, sweep_contract.failed_key: 0}, (
        f"On {last_day!r} — exactly `term.end_date + {sweep_contract.grace_days_value}` — the "
        f"sweep answered {inside!r}. D7 makes that day the last one inside the bound, so a section "
        "with a student to post for is posted for; without this half the refusal above holds of a "
        "sweep that walks nothing at all, which is the tree these tests were written against."
    )
    assert len(book.posted()) == 1, (
        f"The platform recorded {book.posted()} on the last day inside the bound. The refusal a "
        "day later is only evidence if the same section, the same student and the same clock "
        "service produce a post on the other side of the line."
    )
