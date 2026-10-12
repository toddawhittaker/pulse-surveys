"""The named-set series route answers from the session's own scope — E9-05.

> 11. **The route takes no purview.** The series route resolves the scope from
>    the session through `leadership_scope`; a request carrying another
>    person's id is answered from the session's own scope. A non-leadership
>    session gets ADR 0196's 403.

E9-05's interface settles the route: `GET /leadership/comparison-sets/{set_id}/
series?term_id=<uuid>`, depending on `leadership_scope`, answering
`NamedSetSeries` with `Cache-Control: no-store`, and refusing by this table —
401 `NOT_LEADERSHIP` with no session, 403 ADR 0196's sentence for another role,
404 `SET_UNAVAILABLE` for an unknown set, 404 `TERM_UNAVAILABLE` for an unknown
term, and FastAPI's 422 for a malformed or missing `term_id`. The 401 and the
403 are also driven for this route by
`test_the_named_set_routes_admit_leadership_and_refuse_everybody_else.py`,
which now lists it.

**The world** is E6-05's lead-review world (`tests/fixtures/lead_review.py`): lead
A leads the report world's course, whose sections are a six-week section
starting 2026-09-28 (`F1WW`) and a twelve-week one; sibling lead B leads a course
with one eight-week section. One named set is planted over A's course, declaring
six weeks at that course's level. So A's answer carries one cohort, starting
2026-09-28, and B's carries none: cohorts come from the reader's purview (the
interface), and B's purview runs no six-week section. That difference is what
makes "answered from A's scope" observable over HTTP.

Every request rides the built application, as `pulse_app` (`docs/MISTAKES.md`
entries 46 and 47).

**Which failure a red is, before E9-05 lands:** the application serves no such
path, so each admitted request answers 404 and FAILS on its status; the 404
refusal tests FAIL on the sentence (or, for the term, on the missing
`app.copy.leadership_rollup`).
"""

from datetime import date
from importlib import import_module
from typing import Any
from uuid import uuid4

import pytest
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    member_of,
    membership_table,
)
from fixtures.lead_review import LeadReviewWorld
from fixtures.leadership_gate import NOT_YOUR_ROLE_STATUS, not_your_role_sentence
from fixtures.named_sets import (
    CACHE_CONTROL_HEADER,
    NO_STORE,
    SET_UNAVAILABLE,
    detail_of,
    refusal_sentence,
    series_path,
)
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import SEEDED_COHORTS, TERM_TABLE
from sqlalchemy import select

pytestmark = pytest.mark.integration

COURSE_TABLE = "course"
SIX_WEEKS = 6
THE_SIX_WEEK_START = SEEDED_COHORTS["F"][2]

ROLLUP_COPY_MODULE = "app.copy.leadership_rollup"
TERM_UNAVAILABLE_TEXT = "There is no term here."

# The members the interface names for the payload, and nothing beside them
# (`docs/MISTAKES.md` entry 22: a member that arrives without a decision).
SERIES_MEMBERS = frozenset({"cohorts"})
COHORT_MEMBERS = frozenset({"section_start_date", "weeks"})
WEEK_MEMBERS = frozenset(
    {
        "course_week",
        "term_week",
        "instructor_mean",
        "course_mean",
        "workload_mean",
        "workload_median",
    }
)
FIGURE_MEMBERS = frozenset({"suppressed", "reason", "figure"})
FIGURE_WEEK_MEMBERS = ("instructor_mean", "course_mean", "workload_mean", "workload_median")


def a_set_over_the_own_course(review: LeadReviewWorld) -> tuple[Any, Any]:
    """A six-week named set over lead A's course, at that course's own level; (set, term) keys."""
    world = review.world
    tables = world.tables
    courses = require_table(tables, COURSE_TABLE)
    course_key = single_primary_key(courses)
    statement = select(courses).where(courses.c[course_key] == review.own_course)
    own = dict(review.session.execute(statement).mappings().one())
    stored = world.seed(
        COMPARISON_SET_TABLE, {}, **{LENGTH_COLUMN: SIX_WEEKS, LEVEL_COLUMN: own["level"]}
    )
    member_of(world.seed, membership_table(tables), stored, own)
    review.rows.commit()
    set_key = stored[single_primary_key(require_table(tables, COMPARISON_SET_TABLE))]
    term = world.calendar.term[single_primary_key(require_table(tables, TERM_TABLE))]
    return set_key, term


def asked(review: LeadReviewWorld, token: Any, set_id: Any, query: str) -> Any:
    return review.ask("GET", f"{series_path(set_id)}?{query}", token=token)


def start_dates_in(answered: Any, what: str) -> list[str]:
    assert answered.status_code == 200, (
        f"{what} answered {answered.status_code}; body begins {answered.text[:400]!r}. E9-05's "
        "interface: `GET /leadership/comparison-sets/{set_id}/series?term_id=…` answers a "
        "leadership session 200 with `{cohorts: [...]}`."
    )
    body = answered.json()
    return [str(cohort.get("section_start_date")) for cohort in body.get("cohorts", [])]


@pytest.mark.invariant
def test_a_request_carrying_another_persons_ids_is_answered_from_the_sessions_own_scope(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A, sending lead B's person id (and B's course as a scope id), is answered A's series.

    **The control:** B's own session is answered B's series, which holds no
    cohort, while A's holds hers — so A's answer is not a constant, and an
    answer resolved from B's id would be visibly B's.

    **The mutations this kills:** the route (or `leadership_scope`) taking a
    `person_id` or `scope_id` query parameter that decides whose purview is
    read; the route resolving a scope itself from anything but the dependency.
    """
    review = lead_review
    lead_a, lead_b = review.lead, review.sibling_lead
    assert lead_a is not None and lead_b is not None, "The lead review world has no two leads."
    set_id, term = a_set_over_the_own_course(review)

    plain = start_dates_in(asked(review, lead_a.token, set_id, f"term_id={term}"), "A's request")
    carrying = start_dates_in(
        asked(
            review,
            lead_a.token,
            set_id,
            f"term_id={term}&person_id={lead_b.person_id}&scope_id={review.sibling_course}",
        ),
        "A's request carrying B's ids",
    )
    theirs = start_dates_in(asked(review, lead_b.token, set_id, f"term_id={term}"), "B's request")

    assert plain == [THE_SIX_WEEK_START.isoformat()], (
        f"Lead A's series lists cohorts {plain}; her purview holds one six-week section, starting "
        f"{THE_SIX_WEEK_START}, and the interface takes cohorts from the purview."
    )
    assert theirs != plain, (
        f"Lead B's series lists the same cohorts as A's ({theirs}), so this route does not show "
        "whose scope it read and the comparison below means nothing."
    )
    assert carrying == plain, (
        f"Lead A's request carrying B's person id was answered with cohorts {carrying}, not her "
        f"own {plain}. E9-05: 'a request carrying another person's id is answered from the "
        "session's own scope' (E9-01 done-when 10)."
    )


@pytest.mark.invariant
def test_an_instructor_session_gets_the_gates_403_from_the_series_route(
    lead_review: LeadReviewWorld,
) -> None:
    """A real instructor session: ADR 0196's 403 with the gate's own sentence.

    **The control:** lead A's session is answered 200 by the same request, so
    the 403 is the gate refusing a role and not a route that refuses everybody.
    """
    review = lead_review
    set_id, term = a_set_over_the_own_course(review)
    assert review.lead is not None

    admitted = asked(review, review.lead.token, set_id, f"term_id={term}")
    refused = asked(review, review.instructor_token, set_id, f"term_id={term}")

    assert admitted.status_code == 200, (
        f"The control failed: lead A's session answered {admitted.status_code}; body begins "
        f"{admitted.text[:400]!r}."
    )
    sentence = not_your_role_sentence(refused, "The series route, asked by an instructor session")
    assert (refused.status_code, detail_of(refused)) == (NOT_YOUR_ROLE_STATUS, sentence), (
        f"The series route answered an instructor session {refused.status_code} "
        f"{detail_of(refused)!r}; ADR 0196's gate answers {NOT_YOUR_ROLE_STATUS} {sentence!r}."
    )


def test_the_series_payload_carries_exactly_the_members_the_interface_names(
    lead_review: LeadReviewWorld,
) -> None:
    """`{cohorts: [{section_start_date, weeks: [{course_week, term_week, four figures}]}]}`.

    Each figure is `{suppressed, reason, figure}` (E4-07's `ComparisonFigure` on
    the wire). No member is called `comparison`, which keeps E4-07's discovery
    rule intact. The answer carries `Cache-Control: no-store`.

    **The mutations this kills:** a count, a section list or a set size added
    beside a figure (the disclosure E5-05's walk exists for); a bare number in
    place of a sealed figure; the cache header dropped.
    """
    review = lead_review
    set_id, term = a_set_over_the_own_course(review)
    assert review.lead is not None

    answered = asked(review, review.lead.token, set_id, f"term_id={term}")
    start_dates_in(answered, "A's request")
    body = answered.json()

    assert answered.headers.get(CACHE_CONTROL_HEADER) == NO_STORE, (
        f"The series route answered `{CACHE_CONTROL_HEADER}: "
        f"{answered.headers.get(CACHE_CONTROL_HEADER)!r}`; every leadership answer is `no-store`."
    )
    assert set(body) == SERIES_MEMBERS, f"The series body carries {sorted(body)}."
    cohorts = body["cohorts"]
    assert cohorts, "The series carries no cohort, so the shape below was checked over nothing."
    weeks = [week for cohort in cohorts for week in cohort["weeks"]]
    assert weeks, "A's cohort carries no week; the report world publishes its six."
    for cohort in cohorts:
        assert set(cohort) == COHORT_MEMBERS, f"A cohort carries {sorted(cohort)}."
        date.fromisoformat(str(cohort["section_start_date"]))
    for week in weeks:
        assert set(week) == WEEK_MEMBERS, f"A week carries {sorted(week)}."
        for name in FIGURE_WEEK_MEMBERS:
            figure = week[name]
            assert isinstance(figure, dict) and set(figure) == FIGURE_MEMBERS, (
                f"`{name}` at course week {week['course_week']} is {figure!r}, not a sealed "
                f"figure carrying exactly {sorted(FIGURE_MEMBERS)}."
            )


def test_an_unknown_set_is_refused_with_the_set_unavailable_sentence(
    lead_review: LeadReviewWorld,
) -> None:
    """404 and `SET_UNAVAILABLE`, beside the same request for a real set answered 200."""
    review = lead_review
    set_id, term = a_set_over_the_own_course(review)
    assert review.lead is not None

    known = asked(review, review.lead.token, set_id, f"term_id={term}")
    unknown = asked(review, review.lead.token, uuid4(), f"term_id={term}")

    expected = refusal_sentence(SET_UNAVAILABLE)
    assert known.status_code == 200, f"The control failed: a real set answered {known.status_code}."
    assert (unknown.status_code, detail_of(unknown)) == (404, expected), (
        f"An unknown set answered {unknown.status_code} {unknown.text[:400]!r}; the interface "
        "reuses E5-06's `SET_UNAVAILABLE` 404."
    )


def test_an_unknown_term_is_refused_with_the_term_unavailable_sentence(
    lead_review: LeadReviewWorld,
) -> None:
    """404 and `leadership_rollup.term_unavailable`'s text, served from the copy registry.

    The sentence is the interface's, transcribed here as the route's own pin; the
    registry entry is required to hold it, so a route serving a literal of its
    own is red as well as a reworded entry.
    """
    review = lead_review
    set_id, _term = a_set_over_the_own_course(review)
    assert review.lead is not None

    answered = asked(review, review.lead.token, set_id, f"term_id={uuid4()}")

    try:
        rollup = import_module(ROLLUP_COPY_MODULE)
    except ModuleNotFoundError:
        pytest.fail(
            f"`{ROLLUP_COPY_MODULE}` does not exist. E9-05 adds it with `TERM_UNAVAILABLE`, the "
            "series route's refusal for an unknown term (README decision 15)."
        )
    entry = getattr(rollup, "TERM_UNAVAILABLE", None)
    assert getattr(entry, "text", None) == TERM_UNAVAILABLE_TEXT, (
        f"`{ROLLUP_COPY_MODULE}.TERM_UNAVAILABLE` is {entry!r}; E9-05's interface settles "
        f"`CopyEntry(key='leadership_rollup.term_unavailable', text={TERM_UNAVAILABLE_TEXT!r})`."
    )
    assert (answered.status_code, detail_of(answered)) == (
        404,
        TERM_UNAVAILABLE_TEXT,
    ), f"An unknown term answered {answered.status_code} {answered.text[:400]!r}."


@pytest.mark.parametrize("query", ("", "term_id=not-a-uuid"), ids=("missing", "malformed"))
def test_a_missing_or_malformed_term_is_refused_by_the_framework(
    lead_review: LeadReviewWorld, query: str
) -> None:
    """FastAPI's own 422 for a `term_id` that is absent or is not a uuid."""
    review = lead_review
    set_id, _term = a_set_over_the_own_course(review)
    assert review.lead is not None

    answered = asked(review, review.lead.token, set_id, query)

    assert answered.status_code == 422, (
        f"A request with the term {'missing' if not query else 'malformed'} answered "
        f"{answered.status_code} {answered.text[:400]!r}; `term_id` is a required uuid."
    )
