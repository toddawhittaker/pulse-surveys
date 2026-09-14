"""SPEC §4.1 item 1 over the class E5 adds — ticket E5-11, criteria 2 and 3.

Item 1 reads: "Students never see comparables, benchmarks, university averages,
or other sections — in charts, text, tooltips, exports, or aria labels", and §5.4
repeats it for this surface: "Students **never** see comparison-set or university
lines". It has been asserted since E2 for *other sections*
(`test_the_student_read_path_names_nothing_outside_the_enrollment.py`). E5 gives
it a second class to refuse: benchmark figures now exist, are computed, and are
served — to instructors — so the student-side exclusion has to be proven against
a world where there is something to leak.

**The inventory is the running application's, not a list** (`docs/MISTAKES.md`
entry 53). Every route whose dependency graph contains `app.api.deps.
require_student` is swept, through `tests/fixtures/routing.py::
student_visible_routes` — the same derivation the E2-09 module uses, lifted into
the fixtures module by this ticket so the two sweeps share one filter and one
planted-route control. A student route registered tomorrow is inside this sweep
the day it lands, and a student route this module cannot drive **fails** here
rather than being skipped.

**The rule is a stem, not a name.** A key is refused when its lowercase spelling
*contains* `benchmark`, `compar`, `university` or `cohort`, at any depth of the
decoded body, inside lists as well as objects. An enumeration of the member names
E5-05 serves today would be defeated by the first member called something else —
`course_benchmark_v2` is the shape entry 53 records — so the sweep is over the
class and the enumeration is only the vocabulary its controls are built from. The
stem is `compar` rather than `comparison` because item 1's own first word is
"comparables": a member called `comparable_sections` is the thing the rule
forbids, and the longer stem would walk past it.

**One world, both readers.** The instructor of `tests/fixtures/report_api.py`'s
taught section stands at the door; `tests/fixtures/report_benchmarks.py` plants
the comparison population around that section; and the student is signed in at
the *same* door through `student_session_in`, enrolled in that same taught
section. So what is asserted is the ticket's own sentence: while the instructor
is served three lines over this population, the student enrolled in the hero
section is served none of them, from one application and one database at one
moment. (`tests/fixtures/student_read.py`'s door cannot be used here — it builds a
second world, whose question set collides with this one's on
`uq_question_set_version`.)

**Every negative here stands beside a positive.** The instructor's report must
*hit* the sweep and name both `benchmark` and `workload_benchmark`; without that,
an empty benchmark world satisfies every assertion in this file
(`docs/MISTAKES.md` entry 3), which is the ticket's "vacuous exclusion" trap. And
before any absence is reported, the student's own read is required to be a 200
naming the section she is enrolled in — a refusal carries no benchmark key
either.

**Values as well as key names.** A figure can travel without its member name, so
one comparison statistic is read *off the instructor's own response* — never
computed here — and searched for in the student's payload, in the spellings that
were shown to hit on the instructor's. The statistic is required to be a value
nothing in a student payload could equal for another reason before it is searched
for, because a needle that collides with a legitimate number would be a red
nobody can act on, and one that collides by luck is entry 3 wearing a decimal
point.

**Sequence, not one payload** (`docs/MISTAKES.md` entry 51). A student meets this
surface repeatedly, and what one view withholds a pair of views can still hand
over. The last test drives the three payloads a student meets in one week — the
read before submitting, the submit's own answer, the read after — and requires
each to be clean *and* the second read to differ from the first, so the sweep is
run over a sequence that actually moved rather than three copies of one answer.

**The marker sits at module level**, in the list form, as the E2-09 module's
does: this file's name matches the `carries_nothing` denial shape, and
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
refuses such a module marked per test.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fixtures.report_api import ReportDoor, StudentInTheReportWorld
from fixtures.report_benchmarks import (
    BENCHMARK_MEMBER,
    COMPARISON_POPULATION,
    HERO_WORKLOAD_HOURS,
    MEAN_FIELD,
    WEEK_CLEAR,
    WORKLOAD_BENCHMARK_MEMBER,
    numbers_of,
    workload_figures,
)
from fixtures.routing import every_route, paths_of, student_visible_routes
from fixtures.student_read import (
    STUDENT_READ_PATH,
    around,
    decoded,
    response_surface,
    scalars_in,
)
from fixtures.submit import WORKLOAD_POSITION, a_valid_submission, submit_route
from test_the_submit_path_answers_the_validity_matrix import a_student_in_an_open_window, accepted

pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]

# The stems a student-visible key may not contain. Lowercased substrings, so a
# member spelled some new way is caught by the class rather than missed by a list
# (`docs/MISTAKES.md` entry 53). `compar` covers both of SPEC §4.1 item 1's own
# words, "comparables" and the `comparison` member E5-05 serves; `cohort` is here
# because the comparison population is a cohort of sections and naming it is
# naming it.
BENCHMARK_STEMS = ("benchmark", "compar", "university", "cohort")

# Keys that share a prefix with a stem and are not one. The sweep must spare every
# one of them: a sweep that refused these would be red against correct payloads
# everywhere it was pointed, and would be deleted rather than fixed.
# `compatible_version` is the near miss for `compar` — five letters shared and the
# sixth different, and a plausible member for a payload to carry about itself
# rather than a word invented to be spared.
NEAR_MISS_KEYS = ("compatible_version", "universe_label", "bench_seat", "cohesive_rating")

# Keys a future payload could grow that no enumeration of today's member names
# would catch. The sweep must find each of them. `comparable_sections` is here
# because it is item 1's own vocabulary and the reason the stem is `compar`.
FUTURE_SPELLINGS = (
    "course_benchmark_v2",
    "Comparison",
    "comparable_sections",
    "UNIVERSITY_MEAN",
    "cohortSize",
)

# What a planted benchmark member carries, in the wire shape
# `tests/fixtures/report_benchmarks.py` documents.
PLANTED_FIGURE: dict[str, Any] = {"suppressed": False, "reason": None, "figure": 4.2}

# The week the comparison figures are read at: the one planted at both configured
# minimums exactly, so nothing here is read off a suppressed member.
REPORTED_WEEK = WEEK_CLEAR

# The hours the sequence test's submission reports. Distinct from every value that
# world plants, so "the second read differs from the first" is a difference this
# module can point at rather than infer.
SUBMITTED_HOURS = 2.5


def keys_in(node: Any, path: str = "$") -> list[tuple[str, str]]:
    """Every dict key at every depth of a decoded JSON document, with where it sits.

    Lists are descended as well as objects, which is the whole of why this is a
    walk rather than a look at the top level: E5-05's own payload puts its figures
    under `streams.<stream>.benchmark.<population>.points[n].mean`, four levels
    down and through a list, and a member added to a student payload would arrive
    the same way. The path travels with the key so a failure says *where*, not
    only *what*.

    A key that is not a string is reported as its `str()`: a JSON document has
    only string keys, and a dict this walk is handed from somewhere else should
    not be able to hide a key by not being one.
    """
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append((f"{path}.{key}", str(key)))
            found.extend(keys_in(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(keys_in(item, f"{path}[{index}]"))
    return found


def benchmark_shaped(node: Any) -> list[tuple[str, str]]:
    """Every key in a decoded body whose name carries one of the stems.

    Matched as a lowercased substring rather than by equality: `workload_benchmark`
    and a future `course_benchmark_v2` both carry `benchmark`, and the sweep is
    over what the class of names has in common.
    """
    return sorted(
        (where, key)
        for where, key in keys_in(node)
        if any(stem in key.lower() for stem in BENCHMARK_STEMS)
    )


def spellings_of(number: float) -> list[str]:
    """The ways one statistic plausibly reaches a JSON body as text.

    A `Decimal` serialises as a string and a `float` as a number, and a number is
    written without trailing zeros while a fixed-scale column keeps them. A search
    for one spelling that reported a clean body is a search gone blind
    (`docs/MISTAKES.md` entry 3), so every spelling is carried and the ones that
    actually hit on the instructor's answer are the ones the student's is searched
    for.
    """
    return [str(number), f"{number:.1f}", f"{number:.2f}"]


def numbers_carried_by(body: Any) -> list[float]:
    """Every scalar in a decoded body that reads as a number, in either currency."""
    found: list[float] = []
    for scalar in scalars_in(body):
        if isinstance(scalar, bool) or scalar is None:
            continue
        try:
            found.append(float(scalar))
        except (TypeError, ValueError):
            continue
    return found


def the_student_reads_her_own_sections(student: StudentInTheReportWorld) -> tuple[Any, Any]:
    """One student read, required to be an answer about her before anything is denied.

    The readable-something control, in the one place all three tests need it: a
    refusal, a 500 or an answer about nobody carries no benchmark key either, and
    an absence reported over one of those means nothing (`docs/MISTAKES.md` entry
    3). Answers the decoded body and the response it came in.
    """
    answered = student.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student enrolled in this "
        f"world's taught section. Body begins {answered.text[:300]!r}. Every absence this module "
        "reports would be explained just as well by a door that answers nobody."
    )
    surface = response_surface(answered)
    assert str(student.taught_section_id) in surface, (
        f"The student's answer does not name the section she is enrolled in "
        f"({student.taught_section_id}) — the section whose comparison figures the instructor is "
        f"being served in this same world. Body begins {answered.text[:300]!r}. An answer that "
        "names no section withholds a benchmark because it withholds everything."
    )
    return decoded(answered, f"`GET {STUDENT_READ_PATH}`"), answered


# ---------------------------------------------------------------------------
# The controls on the instrument, run before any payload is judged with it.
# ---------------------------------------------------------------------------


def test_the_key_walker_finds_a_benchmark_key_planted_deep_inside_a_list() -> None:
    """The sweep finds what it is looking for, three levels down and through a list.

    `docs/MISTAKES.md` entry 3: a search that has gone blind reports every body as
    clean, and the report is indistinguishable from a pass. So the walk is
    required to *find* a planted key on a document of this test's own making,
    under the same nesting a real payload uses — an object, inside a list, inside
    an object — and to say where it found it.

    **The mutations this kills:** a walk that looks only at the top level; a walk
    that descends objects and steps over lists, which is where every point in a
    series lives; a match written as equality against today's member names, which
    the future spellings below defeat one rename later.

    **A red here means these tests are broken, not the code.**
    """
    document = {
        "sections": [
            {
                "section_code": "R7FF",
                "open_survey": {
                    "questions": [{"id": 1, "position": 1}],
                    "workload_benchmark": {"comparison": PLANTED_FIGURE},
                },
            }
        ],
        "institution_timezone": "America/New_York",
    }

    found = benchmark_shaped(document)
    where = {key: place for place, key in found}

    assert WORKLOAD_BENCHMARK_MEMBER in where, (
        f"The walk did not find `{WORKLOAD_BENCHMARK_MEMBER}`, planted three levels down inside a "
        f"list. It found {found}. A sweep that cannot see a member in the position a real payload "
        "would put one in reports every student payload as clean, and every absence assertion in "
        "this module would be silence dressed as a pass."
    )
    assert "sections[0]" in where[WORKLOAD_BENCHMARK_MEMBER], (
        f"The walk found `{WORKLOAD_BENCHMARK_MEMBER}` at {where[WORKLOAD_BENCHMARK_MEMBER]!r}, "
        "which does not name the list entry it sits under. The path is what a failure message "
        "hands a reader, and a walk that loses it has found the key by accident."
    )
    assert COMPARISON_POPULATION in where, (
        f"The walk did not find the nested `{COMPARISON_POPULATION}` under the planted member; it "
        f"found {found}. Every depth is swept, not only the depth the member starts at."
    )

    for spelling in FUTURE_SPELLINGS:
        assert benchmark_shaped({spelling: PLANTED_FIGURE}), (
            f"The sweep spared a key called `{spelling}`. It is a member name nobody has written "
            "yet and the whole reason the rule is a stem rather than a list of the names E5-05 "
            "serves today: an enumeration is defeated by the first member spelled differently "
            "(`docs/MISTAKES.md` entry 53), and matching has to be case-insensitive and by "
            "substring for that to hold. `comparable_sections` is the one to look at first — it is "
            "SPEC §4.1 item 1's own opening word, and the stem is `compar` for it."
        )


def test_the_key_walker_spares_the_keys_that_only_look_like_the_stems() -> None:
    """The other direction: a near miss is not a hit.

    The pair to the control above, and neither is evidence without the other
    (`docs/MISTAKES.md` entry 2). A sweep that reported every key would be red
    against every correct payload, would tell nobody anything, and would be
    deleted rather than fixed — so the keys that share a prefix with a stem and
    are not one are required to pass through untouched.

    **The mutation this kills:** a stem shortened until it matches ordinary words
    — `compa`, `uni`, `co` — which is the repair somebody reaches for the first
    time this sweep misses something. `compatible_version` is the one that pins
    it: it shares five letters with `comparison` and differs at the sixth, which
    is exactly where the stem stops.

    **A red here means these tests are broken, not the code.**
    """
    document = {key: index for index, key in enumerate(NEAR_MISS_KEYS)}

    found = benchmark_shaped(document)

    assert not found, (
        f"The sweep refused {found} on a document carrying only near misses ({list(NEAR_MISS_KEYS)})"
        ". None of them contains `benchmark`, `compar`, `university` or `cohort`: "
        "`compatible_version` is not a comparable, `universe_label` is not a university, and a "
        "sweep that cannot tell them apart reddens correct payloads."
    )


def test_the_instructor_report_in_the_same_world_carries_what_the_student_must_not(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    student_session_in: Callable[..., StudentInTheReportWorld],
) -> None:
    """Criterion 3, and the readable-something control beside it.

    Two things are established here and nothing is denied, which is why it runs
    first: the benchmark population this module's absences are measured against is
    really there and really served — the instructor's report hits the sweep and
    names both `benchmark` and `workload_benchmark` — and the student enrolled in
    that same taught section answers a 200 naming it, through the same tool at the
    same moment. Without the first, an empty world satisfies every test below
    (`docs/MISTAKES.md` entry 3, and the ticket's "vacuous exclusion" trap);
    without the second, every absence below is equally well explained by a door
    that refuses everybody.

    **The mutations this kills:** a benchmark population that is planted and never
    reaches the payload, which would make the sweeps below true of a report with
    nothing in it; and a student session that cannot read at all in this world.

    **A red here means these tests are broken, not the code** — it is the
    instrument, not the read paths.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())

    body, answered = report_door.payload(course_week=REPORTED_WEEK)
    hit = benchmark_shaped(body)
    named = {key for _where, key in hit}

    assert BENCHMARK_MEMBER in named, (
        f"The instructor's report for course week {REPORTED_WEEK} carries no key containing "
        f"`{BENCHMARK_MEMBER}`; the keys the sweep did match are {hit}. SPEC §5.1 puts three lines "
        "on each panel — this section, the comparison set and university-wide — and E5-05 serves "
        "them under the stream's `benchmark` member. If they are not there, this world has nothing "
        "for a student payload to leak and every assertion in this module is vacuous."
    )
    assert WORKLOAD_BENCHMARK_MEMBER in named, (
        f"The instructor's report carries no `{WORKLOAD_BENCHMARK_MEMBER}`; the sweep matched "
        f"{hit}. §5.1's workload mean and median against the comparison and university figures are "
        "the other half of what a student may not see, and the sweep has to be shown finding them "
        f"on the payload that does carry them. Body begins {answered.text[:300]!r}."
    )

    student = student_session_in(report_door)
    the_student_reads_her_own_sections(student)


# ---------------------------------------------------------------------------
# SPEC §4.1 item 1, criterion 2: no student route carries a benchmark key.
# ---------------------------------------------------------------------------


def test_no_student_visible_route_carries_a_benchmark_shaped_key_at_any_depth(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    student_session_in: Callable[..., StudentInTheReportWorld],
    require_student_dependency: Any,
) -> None:
    """Criterion 2: every student-visible route, swept generically, in the planted world.

    The inventory comes from the application's own route table and the sweep is
    over key *names* at every depth, so what has to be defeated by a future
    benchmark member is a rule about a class of names rather than a list somebody
    keeps (`docs/MISTAKES.md` entry 53). The benchmark population is planted
    first and the instructor's own answer is read as the canary, in this test's
    own body: a world where the figures do not exist satisfies this assertion
    perfectly.

    **The mutations this kills:** a student read path joined to the benchmark
    views — the comparison figures computed for the report served through the
    student's own answer, under any member name; and a payload model that grew a
    benchmark member which the service quietly fills. The student here is enrolled
    in the hero section itself, so a join from her enrolment to that section's
    benchmark reaches a populated figure rather than an empty one.

    **The near misses it must survive:** a payload carrying `compatible_version`
    or any other near miss, spared by the control above; and a refusal, which is
    refused here — every route swept has to answer 200 and name her own section
    first.

    **A route this sweep cannot drive fails rather than being skipped.** A GET
    taking a path parameter, or a route answering some other method, is a route
    §4.1 item 1 is unasserted over unless something drives it: the submit path is
    driven by the sequence test at the end of this module and is named here as
    covered, and anything else is a red asking for a driver in the same change
    that added the route.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())
    instructor_body, _answered = report_door.payload(course_week=REPORTED_WEEK)
    assert benchmark_shaped(instructor_body), (
        "The instructor's report for course week "
        f"{REPORTED_WEEK} carries no benchmark-shaped key at all, so this world has nothing for a "
        "student payload to carry and the sweep below judged an empty question. "
        "`test_the_instructor_report_in_the_same_world_carries_what_the_student_must_not` is where "
        "that is diagnosed."
    )

    student = student_session_in(report_door)
    application = report_door.application
    routes = student_visible_routes(application, require_student_dependency)
    assert routes, (
        "The running application serves no route whose dependency graph contains "
        "`require_student`, so this sweep judged nothing and its silence means nothing. The paths "
        f"it does serve: {sorted(paths_of(every_route(application)))}."
    )

    driven_here = {
        path
        for path in paths_of(routes)
        if "{" not in path
        and any(
            "GET" in (getattr(route, "methods", None) or set())
            for route in routes
            if getattr(route, "path", None) == path
        )
    }
    covered_elsewhere = {submit_route(report_door.tool)}
    uncovered = sorted(paths_of(routes) - driven_here - covered_elsewhere)
    assert not uncovered, (
        f"These student-visible routes are covered by nothing: {uncovered}. This sweep drives a "
        "parameterless GET; the submit path is driven by "
        "`test_the_payloads_a_student_meets_in_one_week_carry_no_benchmark_shaped_key` below. A "
        "route neither reaches is a student surface SPEC §4.1 item 1 is unasserted over, and the "
        "repair is a driver here in the change that adds the route — a skip would report a clean "
        "pass over a path nobody looked at (`docs/MISTAKES.md` entry 2)."
    )

    swept: list[str] = []
    for path in sorted(driven_here):
        answered = student.get(path)
        assert answered.status_code == 200, (
            f"`GET {path}` answered {answered.status_code} for a student enrolled in this world's "
            f"taught section. Body begins {answered.text[:300]!r}. A refusal carries no benchmark "
            "key either, so this sweep cannot be allowed to pass over one."
        )
        body = decoded(answered, f"`GET {path}`")
        assert str(student.taught_section_id) in response_surface(answered), (
            f"`GET {path}` answered 200 without naming the section this student is enrolled in "
            f"({student.taught_section_id}). Body begins {answered.text[:300]!r}. An answer that "
            "names nothing carries no benchmark either."
        )

        carried = benchmark_shaped(body)
        assert not carried, (
            f"`GET {path}` carries {len(carried)} benchmark-shaped key(s): {carried[:5]}.\n\n"
            "SPEC §4.1 item 1: students never see comparables, benchmarks, university averages or "
            "other sections, in any surface. §5.4 says it again for this one: a student sees their "
            "own section, and never comparison-set or university lines.\n\n"
            "The key is matched by the stems `benchmark`, `compar`, `university` and `cohort` as "
            "substrings, at any depth, so what is reported here is a member named for one of them "
            "— under whatever new spelling — rather than a member on a list."
        )
        swept.append(path)

    assert swept, (
        f"None of the student-visible routes {sorted(paths_of(routes))} was driven, so this test "
        "swept nothing at all. Item 1 is about what a student is shown, and a read path nothing "
        "reads is not evidence about it."
    )


def test_no_student_payload_carries_a_comparison_figure_the_instructor_is_served(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    student_session_in: Callable[..., StudentInTheReportWorld],
) -> None:
    """The value, not only the member name: the statistic itself is absent.

    A member name can be renamed and a figure can travel without one — under a
    generic `figures` list, inside a string, beside a label. So one comparison
    statistic is taken **off the instructor's own answer** rather than computed
    here (computing it would be holding the expectation in a second copy of the
    thing under test, `docs/MISTAKES.md` entry 19) and then searched for in the
    payload the student of that same section is served, as a number and as text.

    **The needle is required to be distinctive before it is searched for.** A
    statistic that happened to equal a week number, a count, a rating or one of
    the hero section's own reported workloads would be found in a clean payload,
    or would be absent from a leaking one by luck — entry 3 with a decimal point.
    So it is asserted to be non-integral and unequal to the hero's own hours
    before anything is scanned.

    **The canary comes first.** The spellings searched for are the ones that
    actually appear in the instructor's response text; if none of them appears
    there, the search is blind and this test says so rather than reporting the
    student's payload clean.

    **The mutation this kills:** a comparison figure reaching a student payload
    under a member name no stem catches — the sweep beside this one would pass and
    this one would not.

    **The near miss it must survive:** the numbers the student's own answer
    legitimately carries, which are whole numbers — week numbers, lengths,
    positions, bounds — and are ruled out by the non-integral guard rather than by
    hope.
    """
    benchmark_cohort(report_door, minimums=report_api_contract.minimums())
    body, answered = report_door.payload(course_week=REPORTED_WEEK)

    figure = workload_figures(body, COMPARISON_POPULATION, answered=answered)[MEAN_FIELD]
    values = sorted(set(numbers_of(figure)))
    assert len(values) == 1, (
        f"The comparison workload mean for course week {REPORTED_WEEK} is {figure!r}, which carries "
        f"{values} rather than one number. This test searches a student payload for a statistic, "
        "and it cannot do that until there is exactly one to search for."
    )
    needle = values[0]

    assert needle != int(needle), (
        f"The comparison workload mean is {needle}, a whole number. Every week number, length, "
        "count, rating and threshold a student payload carries is a whole number too, so a whole "
        "number is a needle that would be found in a clean payload — the plans this world plants "
        "have to make this statistic a value nothing else can equal (E5-11 work order, decision 5)."
    )
    collisions = sorted(
        hours for hours in (float(value) for value in HERO_WORKLOAD_HOURS) if hours == needle
    )
    assert not collisions, (
        f"The comparison workload mean is {needle}, which is also {collisions} — the hours the hero "
        "section's own respondents reported. A student payload could legitimately carry her "
        "section's own figure one day, so this needle cannot tell a comparison from an answer."
    )

    instructor_text = answered.text
    hitting = [spelling for spelling in spellings_of(needle) if spelling in instructor_text]
    assert hitting, (
        f"None of the spellings {spellings_of(needle)} appears in the instructor's own response "
        "text, which is the body this statistic was read out of. The search is therefore blind, "
        "and a clean student payload below would mean nothing (`docs/MISTAKES.md` entry 3's canary "
        f"rule). The response begins {instructor_text[:300]!r}."
    )

    student = student_session_in(report_door)
    student_body, read = the_student_reads_her_own_sections(student)
    surface = response_surface(read)

    found = [spelling for spelling in hitting if spelling in surface]
    assert not found, (
        f"The student's own read carries {found}, which is the comparison set's workload mean "
        f"({needle}) as it is spelled in the instructor's report. First occurrence: "
        f"{around(surface, found[0])!r}.\n\n"
        "SPEC §4.1 item 1 and §5.4: a student never sees a comparison-set figure. The statistic is "
        "the thing the rule is about — a member name is only how it usually travels."
    )
    numeric = [
        number for number in numbers_carried_by(student_body) if number == pytest.approx(needle)
    ]
    assert not numeric, (
        f"The student's own read carries the number {needle} as a value rather than as text: "
        f"{numeric}. That is the comparison set's workload mean, read off the instructor's answer "
        "in this same world. A figure that arrives as a bare number under an innocent member name "
        "is exactly what a key-name sweep alone would miss."
    )


# ---------------------------------------------------------------------------
# The sequence, not one payload (`docs/MISTAKES.md` entry 51).
# ---------------------------------------------------------------------------


def test_the_payloads_a_student_meets_in_one_week_carry_no_benchmark_shaped_key(
    open_submit_tool: Any,
    submit_world: Any,
    signed_in_student: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """Three consecutive payloads, driven the way the student meets them.

    `docs/MISTAKES.md` entry 51: a property proven over one response is a property
    about one response, and a reader who keeps the previous one is subtracting
    rather than reading. The student's week is three payloads — the survey read
    before submitting, the submit's own answer, and the survey read after — and
    all three are swept, with the second read required to **differ** from the
    first so that the sequence being swept is one that actually moved.

    **The submit path is a student-visible route and this is what drives it.** The
    sweep above names it as covered here; without this test it would be a student
    surface nothing sweeps, which is the disclosed-limit shape entry 53 is about.

    **The world is the submit world and not the benchmark world, which is a
    disclosed limit.** Only that world seeds §3.2's validity bounds on its
    question set, which is what a submission is judged against; the benchmark
    population is planted around a `ReportDoor` in the other one. What that costs
    is the instructor canary *between* these three reads, which the two tests
    above run against the planted world instead. What stands in for it here is a
    canary of the same kind: the sweep is re-run over the third payload with a
    benchmark member planted on it, and must find it — so a sweep gone blind on
    this payload's own shape says so.

    **The mutation this kills:** a benchmark member that appears only after a
    submission — a "now that you have answered, here is how your section compares"
    member on the submit response or on the read that follows it — which every
    single-payload sweep in this module passes over.

    **The near miss it must survive:** the student's own submitted hours, which
    the third payload must carry. An answer that returned nothing after a
    submission would satisfy every absence here.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )

    before = student.client.get(STUDENT_READ_PATH, headers=student.authorization)
    assert before.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {before.status_code} for a signed-in student inside an "
        f"open window. Body begins {before.text[:300]!r}."
    )
    before_body = decoded(before, f"`GET {STUDENT_READ_PATH}` before the submission")
    assert keys_in(before_body), (
        f"The first read carries no keys at all: {before.text[:300]!r}. An empty document satisfies "
        "every sweep in this test."
    )
    assert not benchmark_shaped(before_body), (
        f"The read before submitting carries {benchmark_shaped(before_body)[:5]}. SPEC §4.1 item 1: "
        "no benchmark, comparable, comparison or university member on a student surface, in any "
        "state of it."
    )

    submission = a_valid_submission(comment=None)
    submission[WORKLOAD_POSITION] = SUBMITTED_HOURS
    answered = student.submit(submission)
    accepted(answered, "A complete submission inside an open window")
    submit_body = decoded(answered, "The submit path's own answer")
    assert not benchmark_shaped(submit_body), (
        f"The submit path's answer carries {benchmark_shaped(submit_body)[:5]}. A member that "
        "arrives only in the answer to a write is a member every read-path sweep passes over."
    )

    after = student.client.get(STUDENT_READ_PATH, headers=student.authorization)
    assert after.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {after.status_code} after an accepted submission. Body "
        f"begins {after.text[:300]!r}."
    )
    after_body = decoded(after, f"`GET {STUDENT_READ_PATH}` after the submission")

    assert str(SUBMITTED_HOURS) in response_surface(after), (
        f"The read after submitting does not carry the {SUBMITTED_HOURS} hours just submitted. Body "
        f"begins {after.text[:300]!r}. These three payloads are being swept as a sequence, and a "
        "second read identical to the first is one payload read twice — which is the reading entry "
        "51 exists to stop."
    )
    assert not benchmark_shaped(after_body), (
        f"The read after submitting carries {benchmark_shaped(after_body)[:5]}. The difference "
        "between two consecutive views is the thing entry 51 is about: a member that appears once "
        "the student has answered is a comparison shown to a student, whatever triggered it."
    )

    planted = dict(after_body) if isinstance(after_body, dict) else {"body": after_body}
    planted[WORKLOAD_BENCHMARK_MEMBER] = {COMPARISON_POPULATION: PLANTED_FIGURE}
    assert benchmark_shaped(planted), (
        "The sweep found nothing on this payload with a benchmark member planted on it, so the "
        "three clean results above are a sweep that has gone blind rather than three clean "
        "payloads (`docs/MISTAKES.md` entry 3). A red here means this test is broken, not the "
        "read path."
    )
