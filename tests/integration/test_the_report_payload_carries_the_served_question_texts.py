"""The wording each histogram is titled with, served and versioned — ticket E5-02.

> 1. The payload carries both question texts and the close instant; the schema
>    types them and the route serves them.
> 2. A planted second question-set version changes the served titles for its weeks
>    only — the versioning proof, both sides.

SPEC §3.2 is why this is served rather than copied into the frontend:

> Question text is stored in a versioned `question_set` table even though v1 ships
> one fixed set — this is the extension point for the future feature where each
> oversight level can append its own questions.

A second copy of the wording in the client is correct exactly until the first
re-versioning, and then wrong in a way nobody looks for. So the payload carries
the served string, and every assertion here is *served equals planted* — never
served equals a constant this file holds, which would assert that the wording had
not changed rather than that the right wording was found
(`docs/MISTAKES.md` entry 19).

**Which set is "in force" for a reported week.** The spec settles the versioning
and not the lookup, and E5-02's work order rules it (ADR 0168): the served text is
read off the question rows the week's responses actually answered, falling back —
for a week nobody answered — to the newest set's matching question. That is two
rules, and this module poses a world where they disagree: three versions planted,
the **middle** one answered in one week. A read that always took the newest set
serves version 3's wording there and is red; a read that took the week's answers
serves version 2's and is green.

**Both sides, against planted strings** — the trap E5-02's work order names and
`docs/MISTAKES.md` entry 3 is the general case of. A proof that the newer version
changed a title says nothing unless the older weeks are shown keeping theirs, and
neither half may be asserted against "not the other one": both are equalities
against the exact strings this suite wrote.

**The two controls at the foot of this module must be green on every tree**,
before E5-02 is built and after. They assert the planting reached the database and
the world answered the weeks this module says it did. A red control means these
tests are broken, not that the code is wrong, and nothing above it can be read
until it is fixed.

**Which failure a red is, before E5-02 lands.** `report_api_contract`'s `member`
and `stream_member` are `pytest.fail` calls naming the missing payload member, so
the first red is a FAILED naming what is owed rather than a `KeyError` inside
somebody's setup (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.report_api import (
    FULL_WEEK,
    RESPONSES_IN_WEEK,
    SILENT_WEEK,
    ReportDoor,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

BOTH_STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)

# How many responses the world's second version plants into the week it answers.
# One is enough — the claim is about which questions were answered, not about how
# many people answered them — and the number is written down so the control at the
# foot of this module can assert it rather than infer it.
ONE_RESPONSE = 1


def served_wording(door: ReportDoor, contract: Any, *, course_week: int, stream: str) -> str:
    """One stream's served question text for one course week, as a string."""
    body, answered = door.payload(course_week=course_week)
    found = contract.stream_member(body, stream, contract.question_text_field, answered=answered)
    assert isinstance(found, str) and found.strip(), (
        f"`streams.{contract.payload_stream_key[stream]}.{contract.question_text_field}` for course "
        f"week {course_week} came back as {found!r}. E5-02 serves the text of that stream's rating "
        "question, and an empty string is a member the read left unpopulated rather than a wording."
    )
    return found


def expected_wording(door: ReportDoor, wording: Any, *, version: int, stream: str) -> str:
    """The string this suite planted for one stream's rating question in one version."""
    position = wording.rating_position(door.world, version=version, stream=stream)
    return wording.wording(version=version, position=position)


def assert_the_planted_strings_are_all_different(planted: dict[str, str]) -> None:
    """No two expectations in this module are the same string.

    Without this, "the instructor stream served the instructor question of version
    1" could be satisfied by a read that served any of the four planted strings,
    and a world whose wordings collided would make every equality below true for a
    reason that has nothing to do with the lookup.
    """
    assert len(set(planted.values())) == len(planted), (
        f"Two of this test's planted wordings are the same string: {planted}. Each is written per "
        "version and per position by `planted_wording` in tests/fixtures/report_question_text.py "
        "precisely so that no wrong answer is also a right one."
    )


def a_re_versioned_world(door: ReportDoor, wording: Any) -> None:
    """Three question-set versions over one section, the middle one answered.

    Version 1 is the set every week of `build_report_world` was answered through,
    re-worded here so the wording is this suite's. Version 2 is planted and
    answered in the otherwise-silent last week. Version 3 is planted and answered
    by nobody, which is what makes "the newest set" and "the set this week's
    responses answered" two different answers for the same week.
    """
    wording.plant_first(door)
    wording.plant_further(
        door, version=wording.second_version, answered_course_weeks=(SILENT_WEEK,)
    )
    wording.plant_further(door, version=wording.third_version)


def test_each_streams_question_text_is_that_streams_own_rating_question(
    report_door: ReportDoor, report_api_contract: Any, question_wording: Any
) -> None:
    """Criterion 1's route half: the member arrives, per stream, holding the right question.

    **The mutation this kills:** one wording served for the whole report — the
    first rating question found, repeated under both streams — which renders two
    histograms with the same title and passes every check that is about a shape.
    **The near miss it excludes:** the stream's *comment* question, which is
    planted with wording of its own here and is the neighbouring row in the same
    question set, reached by the same join with one predicate dropped.
    """
    planted = question_wording.plant_first(report_door)
    first = question_wording.first_version
    ratings = {
        stream: expected_wording(report_door, question_wording, version=first, stream=stream)
        for stream in BOTH_STREAMS
    }
    comments = {
        stream: planted[
            question_wording.comment_position(report_door.world, version=first, stream=stream)
        ]
        for stream in BOTH_STREAMS
    }
    assert_the_planted_strings_are_all_different(
        {**ratings, **{f"{stream}-comment": text for stream, text in comments.items()}}
    )

    for stream in BOTH_STREAMS:
        served = served_wording(
            report_door, report_api_contract, course_week=FULL_WEEK, stream=stream
        )
        assert served == ratings[stream], (
            f"The {stream} stream's `{report_api_contract.question_text_field}` is {served!r}. This "
            f"world planted {ratings[stream]!r} as that stream's rating question, "
            f"{comments[stream]!r} as its comment question, and "
            f"{ratings[BOTH_STREAMS[1 - BOTH_STREAMS.index(stream)]]!r} as the other stream's "
            "rating question. E5-02 serves the rating question of the stream the member sits under."
        )


def test_a_week_answered_under_the_newer_version_serves_that_versions_wording(
    report_door: ReportDoor, report_api_contract: Any, question_wording: Any
) -> None:
    """Criterion 2, the changing side — and the half that tells the two lookup rules apart.

    The last course week is answered through version 2 while version 3 is planted
    and answered by nobody, so the newest set and the answered set are different
    sets for this one week.

    **The mutation this kills:** the wording read off the newest question set
    rather than off the rows the week's responses answered, which serves version
    3's string here. **The other mutation:** the wording read off whichever set is
    lowest-versioned or first-created, which serves version 1's.
    """
    a_re_versioned_world(report_door, question_wording)
    second = question_wording.second_version

    expected = {
        stream: expected_wording(report_door, question_wording, version=second, stream=stream)
        for stream in BOTH_STREAMS
    }
    others = {
        f"v{version}-{stream}": expected_wording(
            report_door, question_wording, version=version, stream=stream
        )
        for version in (question_wording.first_version, question_wording.third_version)
        for stream in BOTH_STREAMS
    }
    assert_the_planted_strings_are_all_different({**expected, **others})

    for stream in BOTH_STREAMS:
        served = served_wording(
            report_door, report_api_contract, course_week=SILENT_WEEK, stream=stream
        )
        assert served == expected[stream], (
            f"Course week {SILENT_WEEK} was answered through question-set version {second} and its "
            f"{stream} stream serves {served!r}. The wording planted for that version is "
            f"{expected[stream]!r}; the other versions' are {others}. A week's served wording comes "
            "from the question rows its own responses answered (E5-02's ADR 0168), which is why a "
            "newer set existing does not change it."
        )


def test_an_earlier_week_still_serves_the_first_versions_wording_after_a_re_version(
    report_door: ReportDoor, report_api_contract: Any, question_wording: Any
) -> None:
    """Criterion 2, the unchanged side — the half a one-sided proof leaves out.

    Course week 1 was answered through version 1, and versions 2 and 3 are planted
    over the same section afterwards. §3.2's versioning is only worth anything if
    that week keeps its own title: a report of an October week showing December's
    wording is a chart labelled with a question nobody in it was asked.

    **The mutation this kills:** the wording read off the newest question set,
    which would change every historical week's title the moment a second set
    ships, and which the changing side of this pair cannot detect on its own.
    """
    a_re_versioned_world(report_door, question_wording)
    first = question_wording.first_version

    expected = {
        stream: expected_wording(report_door, question_wording, version=first, stream=stream)
        for stream in BOTH_STREAMS
    }
    newer = {
        f"v{version}-{stream}": expected_wording(
            report_door, question_wording, version=version, stream=stream
        )
        for version in (question_wording.second_version, question_wording.third_version)
        for stream in BOTH_STREAMS
    }
    assert_the_planted_strings_are_all_different({**expected, **newer})

    for stream in BOTH_STREAMS:
        served = served_wording(
            report_door, report_api_contract, course_week=FULL_WEEK, stream=stream
        )
        assert served == expected[stream], (
            f"Course week {FULL_WEEK} was answered through question-set version {first} and its "
            f"{stream} stream serves {served!r}, where this world planted {expected[stream]!r}. The "
            f"wordings of the two later versions planted over the same section are {newer}; serving "
            "one of those is a report titling an answered week with a question its respondents "
            "were never asked."
        )


def test_a_week_no_response_answered_serves_the_newest_sets_wording(
    report_door: ReportDoor, report_api_contract: Any, question_wording: Any
) -> None:
    """The fallback half of E5-02's lookup rule, on the one week that can pose it.

    A published week nobody answered has no answered question rows to read, and
    the ticket still has to title its two empty histograms. The work order's rule
    (ADR 0168) is the newest set's matching question — the same highest-version
    rule a submission uses to decide which set a student is answering.

    Only two versions are planted here, and the newer one is answered nowhere, so
    "the newest set" is the only source that can produce its wording.

    **The mutation this kills:** an empty string, a `None` or the stream label
    served for a week with no responses — the fallback left unwritten, which shows
    up as a blank histogram title on exactly the weeks a quiet section has most of.
    """
    question_wording.plant_first(report_door)
    question_wording.plant_further(report_door, version=question_wording.second_version)

    assert RESPONSES_IN_WEEK[SILENT_WEEK] == 0, (
        f"This module's fallback case rests on course week {SILENT_WEEK} being answered by nobody, "
        f"and `RESPONSES_IN_WEEK` says {RESPONSES_IN_WEEK[SILENT_WEEK]}."
    )
    assert report_door.rows.responses_in(SILENT_WEEK) == 0, (
        f"The database holds {report_door.rows.responses_in(SILENT_WEEK)} responses for course week "
        f"{SILENT_WEEK}, and this test is about a week with none."
    )

    second = question_wording.second_version
    expected = {
        stream: expected_wording(report_door, question_wording, version=second, stream=stream)
        for stream in BOTH_STREAMS
    }
    older = {
        f"v1-{stream}": expected_wording(
            report_door, question_wording, version=question_wording.first_version, stream=stream
        )
        for stream in BOTH_STREAMS
    }
    assert_the_planted_strings_are_all_different({**expected, **older})

    for stream in BOTH_STREAMS:
        served = served_wording(
            report_door, report_api_contract, course_week=SILENT_WEEK, stream=stream
        )
        assert served == expected[stream], (
            f"Nobody answered course week {SILENT_WEEK}, and its {stream} stream serves {served!r}. "
            f"The newest question set planted over this section words that stream's rating question "
            f"{expected[stream]!r}; version 1's wordings are {older}."
        )


def test_the_planted_wording_is_what_the_database_holds(
    report_door: ReportDoor, question_wording: Any
) -> None:
    """A control, green on every tree: the planting reached the rows it names.

    Every assertion above compares a served string against a string this suite
    says it planted. An `UPDATE` that matched no row, or a candidate column list
    that found the wrong column, leaves those rows holding the seeding walker's
    invented values — and each of those comparisons then fails for a reason that
    has nothing to do with E5-02.

    **A red here means these tests are broken, not that the code is wrong.** It is
    a statement about `tests/fixtures/report_question_text.py` and about nothing
    the implementer wrote.
    """
    a_re_versioned_world(report_door, question_wording)
    world = report_door.world

    columns = question_wording.columns(world)
    assert columns, (
        "No free-text column on `question` was planted into; see `question_text_columns` in "
        "tests/fixtures/report_question_text.py."
    )

    seen: list[str] = []
    for version in (
        question_wording.first_version,
        question_wording.second_version,
        question_wording.third_version,
    ):
        for position in sorted(world.shape_of[version]):
            expected = question_wording.wording(version=version, position=position)
            stored = question_wording.stored(world, version=version, position=position)
            assert set(stored.values()) == {expected}, (
                f"Version {version}'s question at position {position} holds {stored} in the "
                f"database, and this suite planted {expected!r} into every one of {list(columns)}."
            )
            seen.append(expected)

    assert len(set(seen)) == len(seen), (
        f"The planted wordings are not all distinct: {seen}. Every equality in this module depends "
        "on a wrong answer being a different string from the right one."
    )


def test_the_world_answers_the_weeks_this_module_says_it_does(
    report_door: ReportDoor, question_wording: Any
) -> None:
    """The second control: the versioning proof's world is the world it is described as.

    Course week 1 carries this world's five version-1 responses and course week 6
    carries exactly the one version-2 response the planting adds. If the second
    response never landed, the "answered under the newer version" test above would
    be asking about a week with no answers at all — and would then pass on the
    fallback rule while claiming to prove the answered-rows one, which is the
    quietest way for this module to be wrong.

    **A red here means these tests are broken, not that the code is wrong.**
    """
    assert report_door.rows.responses_in(SILENT_WEEK) == 0, (
        f"Before anything is planted, course week {SILENT_WEEK} holds "
        f"{report_door.rows.responses_in(SILENT_WEEK)} responses; `build_report_world` leaves it "
        "silent, which is what makes it available as the newer version's week."
    )

    a_re_versioned_world(report_door, question_wording)
    report_door.refresh()

    assert report_door.rows.responses_in(SILENT_WEEK) == ONE_RESPONSE, (
        f"Course week {SILENT_WEEK} holds {report_door.rows.responses_in(SILENT_WEEK)} responses "
        f"after the planting, and `plant_further` submits {ONE_RESPONSE} there."
    )
    assert report_door.rows.responses_in(FULL_WEEK) == RESPONSES_IN_WEEK[FULL_WEEK], (
        f"Course week {FULL_WEEK} holds {report_door.rows.responses_in(FULL_WEEK)} responses and "
        f"this world plants {RESPONSES_IN_WEEK[FULL_WEEK]}. Every one of them answered version 1, "
        "which is what the unchanged side of the versioning pair reads."
    )
