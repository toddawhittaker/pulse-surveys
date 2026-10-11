"""Draft and check answer only the instructor's own section, for a published week — done-when 6.

> Draft and check refuse a section the instructor does not teach and a week not
> yet published, with one refusal that names nothing of the section, and run no
> model call. The gate runs at dispatch: no CSRF token is refused over HTTP beside
> the same request with it.

Work-order decision 2 makes the refusal the report's own: "a section the reader
does not teach, or a week not yet published for it, gets the report's existing 404
sentence (byte-identical)". So each refusal here is compared with the report
route's answer to the same section-week at the same clock — the sentence is never
transcribed (`docs/MISTAKES.md` entry 19), and a refusal that differed from the
report's would tell a prober something the report does not.

**"Run no model call" is measured on the wire**: the scripted provider counts the
completion requests it receives. Every test that asserts zero also drives the
admitted request in the same world and requires the count to rise, so the
counter is shown to be counting (`docs/MISTAKES.md` entry 3).

**CSRF over HTTP, against the built application** (`docs/MISTAKES.md` entry 47):
the session rides the cookie, the carrier `csrf_verified_instructor` exists for;
a Bearer request is exempt by design (ADR 0089) and would prove nothing.

**Which failure a red is.** Before E7-04: a FAILED naming the missing route.
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.report_api import (
    FULL_WEEK,
    REPORT_OPENS_BY_TERM_WEEK,
    TERM_WEEK_OF_COURSE_WEEK,
    a_section_that_does_not_exist,
    once_the_report_has_opened,
)
from fixtures.response_draft import (
    A_PLAIN_DRAFT,
    CHECK,
    DRAFT,
    NOT_FOUND_STATUS,
    SHOWN_THEME_A,
    SHOWN_THEME_A_COUNT,
    DraftDoor,
    check_answer,
    draft_answer,
)
from fixtures.submit import CSRF_REFUSED_STATUS

pytestmark = pytest.mark.integration

TASKS = (DRAFT, CHECK)

# Far over any bound a draft could be given: E7-01 sets the response text bound
# and the work order puts the check's draft under the same one ("if 01 has not
# merged, define `RESPONSE_TEXT_MAX = 4000`"). The exact number is 01's; this is
# deliberately a hundred times the fallback, so the test holds whichever lands.
A_DRAFT_FAR_OVER_ANY_BOUND = "x" * 400_000


def script_a_usable_answer(door: DraftDoor, task: str) -> None:
    if task == DRAFT:
        door.provider.script(draft_answer(A_PLAIN_DRAFT))
    else:
        door.provider.script(check_answer([(SHOWN_THEME_A, SHOWN_THEME_A_COUNT)]))


def ask(door: DraftDoor, task: str, **kwargs: Any) -> Any:
    return door.ask(task, draft=A_PLAIN_DRAFT if task == CHECK else None, **kwargs)


def assert_the_counter_counts(door: DraftDoor, task: str) -> None:
    """The admitted request, in the same world: it reaches the model."""
    script_a_usable_answer(door, task)
    before = len(door.provider.completions)
    answered = ask(door, task)
    assert answered.status_code == 200, (
        f"The {task} for the instructor's own published week answered {answered.status_code}, so "
        f"this world is not the one the refusal is measured against. Body {answered.text[:300]!r}."
    )
    assert len(door.provider.completions) > before, (
        f"The admitted {task} made no completion request either, so 'no model call' below is a "
        "counter that does not count."
    )


@pytest.mark.parametrize("task", TASKS)
def test_a_section_the_instructor_does_not_teach_gets_the_reports_404_and_no_model_call(
    draft_door: DraftDoor, task: str
) -> None:
    """The untaught section: the report's 404, byte for byte, naming nothing, asking nobody.

    **The mutations this kills:** the route resolving the section without the
    teaching scope (it answers 200, or 502 from a model call); a refusal worded
    apart from the report's (a 403, or "you do not teach this section", which
    confirms the section exists); the gather or the model reached before the scope
    check. **The near miss:** the taught section, asked afterwards, answers 200.
    """
    door = draft_door
    door.build_the_week()
    script_a_usable_answer(door, task)
    untaught = door.rows.untaught_section_id
    before = len(door.provider.completions)

    answered = ask(door, task, section_id=untaught)
    report = door.report(section_id=untaught)

    assert report.status_code == NOT_FOUND_STATUS, (
        f"The report itself answers {report.status_code} for the untaught section; decision 2 "
        "borrows its 404, so this premise is what the comparison rests on."
    )
    assert answered.status_code == NOT_FOUND_STATUS, (
        f"The {task} answered {answered.status_code} for a section the instructor does not teach. "
        f"Body {answered.text[:300]!r}."
    )
    assert answered.content == report.content, (
        f"The {task}'s refusal {answered.text[:300]!r} is not the report's {report.text[:300]!r}. "
        "Decision 2: 'the report's existing 404 sentence (byte-identical)'."
    )
    assert str(untaught) not in answered.text, "The refusal names the section's key."
    assert len(door.provider.completions) == before, (
        f"The {task} for an untaught section made {len(door.provider.completions) - before} model "
        "call(s). Done-when 6: refused 'and run no model call'."
    )
    assert_the_counter_counts(door, task)


@pytest.mark.parametrize("task", TASKS)
def test_a_section_that_does_not_exist_gets_the_same_refusal_as_one_not_taught(
    draft_door: DraftDoor, task: str
) -> None:
    """ "One refusal": a key nothing holds and a section somebody else teaches read alike.

    **The mutation this kills:** a distinct answer for an unknown key (a 422, a
    different sentence), which turns the route into an existence oracle for
    section keys.
    """
    door = draft_door
    door.build_the_week()
    script_a_usable_answer(door, task)
    before = len(door.provider.completions)
    untaught = ask(door, task, section_id=door.rows.untaught_section_id)
    missing = ask(door, task, section_id=a_section_that_does_not_exist())
    assert (missing.status_code, missing.content) == (untaught.status_code, untaught.content), (
        f"A section that does not exist answers {missing.status_code} {missing.text[:200]!r}; one "
        f"the instructor does not teach answers {untaught.status_code} {untaught.text[:200]!r}."
    )
    assert len(door.provider.completions) == before, "A refused request reached the model."


@pytest.mark.parametrize("task", TASKS)
def test_a_week_not_yet_published_gets_the_reports_404_and_opens_with_the_report(
    draft_door: DraftDoor, task: str
) -> None:
    """An hour before course week 1's report opens: the report's 404. An hour after: 200.

    The clock stands after the week's window has closed and before Monday 06:00
    (ADR 0184), which is the one interval where "closed" and "published" differ —
    the near miss of gating on the window's close rather than on publication.

    **The mutations this kills:** the publication check absent (200 before the
    report opens); a check keyed on the window's close (also 200 here); a refusal
    worded apart from the report's. **The twin:** the same request an hour after
    the opening, answered 200 with a model call.
    """
    door = draft_door
    door.build_the_week()
    opens = REPORT_OPENS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[FULL_WEEK]]
    door.door.pretend(opens - timedelta(hours=1))
    script_a_usable_answer(door, task)
    before = len(door.provider.completions)

    answered = ask(door, task)
    report = door.report()
    assert report.status_code == NOT_FOUND_STATUS, (
        f"The report answers {report.status_code} for course week 1 an hour before it opens; the "
        "comparison below rests on its 404."
    )
    assert (answered.status_code, answered.content) == (report.status_code, report.content), (
        f"The {task} for a week not yet published answered {answered.status_code} "
        f"{answered.text[:300]!r}; the report answers {report.text[:300]!r}."
    )
    assert (
        len(door.provider.completions) == before
    ), f"The {task} for an unpublished week reached the model."

    door.door.pretend(once_the_report_has_opened(FULL_WEEK))
    assert_the_counter_counts(door, task)


@pytest.mark.parametrize("task", TASKS)
def test_a_cookie_borne_request_without_its_csrf_token_is_refused_beside_one_with_it(
    draft_door: DraftDoor, task: str
) -> None:
    """The gate at dispatch, over HTTP: no token refused and no model call; the bound token admitted.

    **The mutation this kills:** the route declared behind the plain instructor
    dependency rather than `csrf_verified_instructor`, or the check gutted — a
    cookie-borne cross-site POST then spends a model call and returns a draft.
    **The near miss:** the same request carrying the session's own token, answered
    200, so the refusal is the token's absence and not the cookie carrier itself.
    """
    door = draft_door
    door.build_the_week()
    script_a_usable_answer(door, task)
    draft = A_PLAIN_DRAFT if task == CHECK else None
    before = len(door.provider.completions)

    refused = door.ask_as_a_browser(task, draft=draft, csrf_token=None)
    assert refused.status_code == CSRF_REFUSED_STATUS, (
        f"A cookie-borne {task} with no CSRF token answered {refused.status_code}; ADR 0114's "
        f"refusal is {CSRF_REFUSED_STATUS}. Body {refused.text[:300]!r}."
    )
    assert len(door.provider.completions) == before, "The tokenless request reached the model."

    admitted = door.ask_as_a_browser(task, draft=draft)
    assert admitted.status_code == 200, (
        f"The same {task} carrying the session's own CSRF token answered {admitted.status_code}. "
        f"Body {admitted.text[:300]!r}."
    )
    assert len(door.provider.completions) > before, "The admitted request made no model call."


def test_a_check_of_a_draft_far_over_any_bound_is_refused_before_the_model(
    draft_door: DraftDoor,
) -> None:
    """Work-order decision 1: the check's draft is bounded, and the bound is met at the edge.

    The bound's value is E7-01's and is not pinned here; a draft a hundred times
    the fallback is over any value it could take. **The mutation this kills:** an
    unbounded `draft` field, which sends whatever arrives to the provider at the
    instructor's cost. **The near miss:** every other check in this suite, sent a
    short draft and answered.
    """
    door = draft_door
    door.build_the_week()
    script_a_usable_answer(door, CHECK)
    before = len(door.provider.completions)
    answered = door.check(A_DRAFT_FAR_OVER_ANY_BOUND)
    assert 400 <= answered.status_code < 500, (
        f"A check of a {len(A_DRAFT_FAR_OVER_ANY_BOUND)}-character draft answered "
        f"{answered.status_code}."
    )
    assert len(door.provider.completions) == before, "The oversized draft reached the model."
    assert_the_counter_counts(door, CHECK)
