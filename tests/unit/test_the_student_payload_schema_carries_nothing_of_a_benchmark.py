"""SPEC §4.1 item 1, structurally — ticket E5-11, acceptance criterion 1.

Item 1 reads: "Students never see comparables, benchmarks, university averages,
or other sections — in charts, text, tooltips, exports, or aria labels", and §5.4
says it again for the surface this contract serves: "Students **never** see
comparison-set or university lines". E5 is the epic that gives the rule something
new to refuse — benchmark figures now exist and flow to instructors — so the
exclusion has to be shown to be non-vacuous rather than true by absence of data.

**This module is the structural half.** Not "the student payload has no benchmark
member today", which is a fact about today, but "a student payload schema does
not *admit* one": the planted member is refused at construction, so a service
that tried to fill one fails where it is written rather than where it is read.
The ticket's own sentence for it — "a member that exists-but-empty is one route
bug away from filled; a member the type system never admits is not" — is
`docs/MISTAKES.md` entry 2's rule about asserting the forbidden state.

**The inventory is the module's own, not a list kept here** (`docs/MISTAKES.md`
entry 53). Every `pydantic.BaseModel` declared in `app.schemas.student` is
planted on, so a sixth or a seventh model added tomorrow is inside this sweep the
day it is declared. A discovery that came back empty would make every assertion
below disappear rather than fail, so its non-emptiness is asserted first, by a
control of its own.

**The two controls, and what a red in one means.** A test that plants a member
and demands a refusal is satisfied by a schema layer that refuses everything, and
by a library that refuses everything; so beside the refusals sit (a) the student
view constructed *without* the planted member, which must still build, and (b) a
model declared in this file with no configuration at all, which must still accept
an unknown member — because pydantic's default for an unrecognised keyword is to
drop it silently, which is the state this ticket is changing. **A red in either
control means these tests are broken, not that the code is.** They are about the
instrument: the first says the schema still admits its own members, the second
says the refusal being measured belongs to `app.schemas.student` rather than to
pydantic in general.

**The mutation this module exists to kill:** the student schemas' refusal of
unknown members removed — whatever mechanism carries it — after which planting
`benchmark=...` on `StudentSurveyView` constructs cleanly and the member is one
service change away from being served. The near miss it must spare is a schema
that still constructs from its own declared members, asserted beside it.

**The marker sits at module level**, in the list form, because
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
requires it of any module whose name matches a denial shape — this one matches
`carries_nothing` — and refuses a module marked per test.
"""

import importlib
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

pytestmark = [pytest.mark.invariant]

# Where the student's own weekly survey contract lives (E2-09's module layout).
STUDENT_SCHEMA_MODULE = "app.schemas.student"

# And the instructor's, which is the other side of the same sentence: the members
# named there are the ones a student payload may not carry.
REPORT_SCHEMA_MODULE = "app.schemas.report"

# The one model the route declares as its `response_model`, named because the
# controls need a model whose members this file can fill.
STUDENT_VIEW = "StudentSurveyView"

# The benchmark member the instructor report carries, from E5-05's payload sketch.
INSTRUCTOR_BENCHMARK_MEMBER = "workload_benchmark"

# The members planted on every student model. Two spellings rather than one: the
# top-level member a benchmark would arrive as, and the nested population name
# E5-05 puts inside it (`StreamBenchmark.comparison`), so a schema that refused
# one name in particular rather than unknown members in general is visible here.
PLANTED_MEMBERS = ("benchmark", "comparison")

# What is planted in them: the wire shape `tests/fixtures/report_benchmarks.py`
# documents, so what is being refused is the thing that would actually arrive
# rather than a sentinel nothing resembles.
PLANTED_VALUE: dict[str, Any] = {
    "comparison": {"points": [{"course_week": 1, "mean": {"suppressed": False, "figure": 4.2}}]},
    "university": {"points": []},
}

# The name stems no student payload schema may declare a member under. Substrings
# rather than an enumeration of today's spellings, for the reason the route sweep
# beside this one gives (`docs/MISTAKES.md` entry 53): a member called
# `course_benchmark_v2` has to defeat a sweep rather than be forgotten from a list.
#
# **`compar` and not `comparison`**, which is the same rule applied to the
# vocabulary rather than to the suffix. SPEC §4.1 item 1's own sentence opens
# "Students never see **comparables**, benchmarks, university averages" — so a
# member called `comparable_sections` is exactly what the item forbids, and a stem
# spelled `comparison` would walk past it. The shorter stem covers both words.
BENCHMARK_STEMS = ("benchmark", "compar", "university", "cohort")

# A timezone name for the control's construction. Any valid string does; the
# member's content is not this module's subject.
A_TIMEZONE = "America/New_York"


def student_models() -> list[type[BaseModel]]:
    """Every payload model `app.schemas.student` declares, by name.

    Declared *there* and not merely imported there: a model this module pulled in
    from `app.schemas.report` because the student module imports it would be
    planted on and refused, and the refusal would say nothing about the student
    contract.
    """
    module = importlib.import_module(STUDENT_SCHEMA_MODULE)
    found = {
        value.__name__: value
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, BaseModel)
        and value is not BaseModel
        and value.__module__ == module.__name__
    }
    return [found[name] for name in sorted(found)]


STUDENT_MODELS = student_models()
MODEL_NAMES = [model.__name__ for model in STUDENT_MODELS]


def complaints_about(model: type[BaseModel], planted: str) -> list[dict[str, Any]]:
    """What this model says when it is handed a member it does not declare.

    The errors rather than the exception, because the exception alone proves
    nothing here: a model with required members refuses *any* incomplete
    construction today, so `pytest.raises(ValidationError)` around this would pass
    against the tree as it stands and assert nothing about the planted member
    (`docs/MISTAKES.md` entry 3 in its exact shape). What the caller asks is
    narrower and is the criterion: is one of the complaints **about the planted
    key**.
    """
    try:
        model(**{planted: PLANTED_VALUE})
    except ValidationError as refused:
        return list(refused.errors())
    return []


# ---------------------------------------------------------------------------
# The controls on the instrument, run before the contract is judged with it.
# ---------------------------------------------------------------------------


def test_the_student_schema_module_declares_the_models_this_sweep_plants_on() -> None:
    """The inventory is not empty, and the route's own response model is in it.

    Every assertion below is parametrised over `STUDENT_MODELS`. A discovery that
    came back empty would collect **zero** tests, and a suite that collects
    nothing reports the same green as a suite that refused everything
    (`docs/MISTAKES.md` entry 3, and the collection-floor discipline the E4
    boundary's denial-inventory entry carries).

    **The mutation it kills:** a discovery narrowed until it matches nothing — a
    changed module path, a `__module__` comparison that stops holding, a base
    class renamed — after which this file is silent rather than red.

    **A red here means these tests are broken, not the code.**
    """
    assert STUDENT_MODELS, (
        f"`{STUDENT_SCHEMA_MODULE}` declares no `pydantic.BaseModel` this sweep can plant on, so "
        "every test in this module was parametrised over nothing and collected zero cases. That is "
        "not a pass: it is indistinguishable from one."
    )
    assert STUDENT_VIEW in MODEL_NAMES, (
        f"`{STUDENT_VIEW}` is not among the models found in `{STUDENT_SCHEMA_MODULE}` "
        f"({MODEL_NAMES}). It is the model `GET /student/survey` declares as its `response_model`, "
        "so a sweep that does not reach it does not reach the student payload at all."
    )


def test_the_student_view_still_constructs_from_the_members_it_declares() -> None:
    """The near miss: refusing an unknown member is not refusing everything.

    Without this, a schema layer that refused every construction would satisfy
    every refusal below, and the contract would be unusable in exactly the way
    nothing here would notice (`docs/MISTAKES.md` entry 2: assert the forbidden
    state *and* the permitted one).

    **The mutation it kills:** a refusal written so wide that the route can no
    longer build its own answer.

    **A red here means these tests are broken, not the code** — most likely that
    `StudentSurveyView`'s own members have moved, and this control is the place to
    follow them.
    """
    module = importlib.import_module(STUDENT_SCHEMA_MODULE)
    view = getattr(module, STUDENT_VIEW)

    built = view(sections=[], institution_timezone=A_TIMEZONE)

    assert list(built.sections) == [], (
        f"`{STUDENT_VIEW}` constructed from its own declared members and came back carrying "
        f"{built.sections!r} under `sections`. This control exists to show the contract still "
        "builds; if its members have moved, follow them here rather than loosening the refusals."
    )
    assert built.institution_timezone == A_TIMEZONE, (
        f"`{STUDENT_VIEW}` was built with `institution_timezone={A_TIMEZONE!r}` and carries "
        f"{built.institution_timezone!r}."
    )


def test_a_model_that_forbids_nothing_still_swallows_an_unknown_member() -> None:
    """The refusal being measured is this project's, not the library's.

    Pydantic 2's default for an unrecognised keyword is `extra="ignore"`: the
    value is dropped and construction succeeds. So a test elsewhere in this file
    that watched a planted member be refused could be watching either a
    deliberate contract or a library default that changed under it, and only one
    of those is a guarantee this project holds. This control pins which by
    building a model declared **here**, configured with nothing at all.

    **The mutation it kills:** nothing in the application — this is the
    instrument's own calibration, and it is what makes criterion 1's refusals
    attributable to `app.schemas.student`.

    **A red here means these tests are broken, not the code** — it means the
    pinned pydantic's default changed, and the refusals below are then measuring
    the library rather than the contract.
    """

    class NothingIsForbiddenHere(BaseModel):
        declared: int

    built = NothingIsForbiddenHere(declared=1, **{PLANTED_MEMBERS[0]: PLANTED_VALUE})

    assert built.declared == 1, (
        "A model declared in this file with no `model_config` refused a member it does not "
        "declare. On the pinned pydantic the default is `extra='ignore'`, so an unknown keyword is "
        "dropped and construction succeeds — and the refusals in this module are only a statement "
        "about `app.schemas.student` while that stays true."
    )
    assert not hasattr(built, PLANTED_MEMBERS[0]), (
        f"The unknown member `{PLANTED_MEMBERS[0]}` survived onto a model that never declared it: "
        f"{built!r}. That is a third behaviour, neither ignoring nor forbidding, and every "
        "assertion in this module is written against the two."
    )


def test_the_instructor_report_declares_the_benchmark_member_the_student_schemas_may_not() -> None:
    """The positive control: these member names exist, on the other side of §4.1 item 1.

    An absence is only evidence when the thing absent exists somewhere. E5-05 put
    `workload_benchmark` on `InstructorReport`, so the name this module refuses on
    the student contract is a name the system really serves — to instructors — and
    "no student schema declares one" is a scoping statement rather than a fact
    about a word nobody uses.

    **The mutation it kills:** a student schema growing a benchmark-stemmed member
    of its own. The stems are matched as substrings, so `course_benchmark_v2` is
    caught by the same line that catches `benchmark` (`docs/MISTAKES.md` entry
    53).

    **The near miss it must spare:** the instructor report itself, which declares
    exactly such a member and must go on doing so.
    """
    report = importlib.import_module(REPORT_SCHEMA_MODULE)
    instructor_report = getattr(report, "InstructorReport", None)
    assert instructor_report is not None, (
        f"`{REPORT_SCHEMA_MODULE}` declares no `InstructorReport`, so this control cannot show that "
        "the member names refused on the student side are names the system serves anywhere. "
        "Without it, every refusal in this module is satisfied by a vocabulary nobody uses."
    )
    assert INSTRUCTOR_BENCHMARK_MEMBER in instructor_report.model_fields, (
        f"`InstructorReport` declares no `{INSTRUCTOR_BENCHMARK_MEMBER}`; it declares "
        f"{sorted(instructor_report.model_fields)}. E5-05 puts the workload comparison figures "
        "there, and this control is what makes the student-side absence mean something."
    )

    declared = sorted(
        (model.__name__, name)
        for model in STUDENT_MODELS
        for name in model.model_fields
        if any(stem in name.lower() for stem in BENCHMARK_STEMS)
    )
    assert not declared, (
        f"These student payload models declare benchmark-shaped members: {declared}. SPEC §4.1 item "
        "1 and §5.4 keep comparison, university and cohort figures off every student surface, and a "
        "declared member is a member a service can fill and a client can render."
    )


# ---------------------------------------------------------------------------
# SPEC §4.1 item 1, criterion 1: the planted member is refused at construction.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("planted", PLANTED_MEMBERS)
@pytest.mark.parametrize("model", STUDENT_MODELS, ids=MODEL_NAMES)
def test_a_planted_benchmark_member_is_refused_by_every_student_payload_schema(
    model: type[BaseModel], planted: str
) -> None:
    """A student payload schema does not admit a member it never declared.

    Criterion 1: "the schema-structural test fails when a benchmark member is
    planted on a student schema". Every model the student contract declares is
    planted on, at the top level and under a nested population name, with the wire
    shape E5-05 actually serves.

    **What is asserted is a complaint about the planted key**, not merely that
    something was refused. Every model here has required members, so handing it
    one unknown keyword raises `ValidationError` *today* — for the members that
    are missing — and a test written as `pytest.raises(ValidationError)` would
    pass against a contract that silently drops the planted member. It would be
    green on the day the defect ships, which is `docs/MISTAKES.md` entry 3 exactly.
    So the complaints are read, and one of them has to name the planted key.

    **The mutation this kills:** the student schemas' refusal of unknown members
    removed or narrowed — a model left unconfigured, a configuration that names
    one spelling rather than unknown members in general — after which
    `StudentSurveyView(benchmark=...)` constructs, the member is dropped in
    silence today, and is served the day a service fills it.

    **The near misses it must spare**, both asserted by controls above: a contract
    that still builds from its own members, and a library that would have refused
    this anyway.
    """
    complaints = complaints_about(model, planted)
    about_the_planted_key = [
        complaint for complaint in complaints if tuple(complaint.get("loc", ())) == (planted,)
    ]

    assert about_the_planted_key, (
        f"`{model.__name__}` was handed a member called `{planted}` carrying E5-05's own benchmark "
        f"shape, and said nothing about it. What it did say: "
        f"{[(complaint.get('type'), complaint.get('loc')) for complaint in complaints]}.\n\n"
        "SPEC §4.1 item 1 and §5.4: a student payload carries no comparison, benchmark or "
        "university figure. A schema that drops an unknown member rather than refusing it is a "
        "schema that would carry this one the day any service passes it — and the drop is silent, "
        "so nothing fails until a student is looking at the page.\n\n"
        f"The model declares {sorted(model.model_fields)}. `{planted}` is not among them and must "
        "not be admitted as an extra."
    )
