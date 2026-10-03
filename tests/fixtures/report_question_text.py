"""E5-02 — the question wording a week's report serves, planted so a test can recognise it.

E5-02 puts each stream's rating question text on the report payload, and SPEC
§3.2 makes that wording **versioned**: "Question text is stored in a versioned
`question_set` table". The ticket's second criterion is the consequence — "a
planted second question-set version changes the served titles for its weeks only"
— and a test can only assert that against wording it planted itself. Comparing a
served string against a constant copied from the spec or from the mockup would
assert that the wording had not changed, which is the opposite claim
(`docs/MISTAKES.md` entry 19).

**What this module writes, and what it refuses to decide.**

  - **The wording.** `planted_wording` is one distinct string per (version,
    position), deliberately unlike SPEC §3.2's sentences and unlike the mockup's
    histogram titles, so a payload serving a hard-coded string is red rather than
    plausible and a failure message shows at a glance which question answered.

  - **Which column holds it is *not* decided here.** E5-02's work order settles
    the member (`question_text`) and leaves the source column conditional —
    "`Question.name` … verify against the survey component before trusting; if
    the survey renders `prompt`, serve `prompt`". So this module plants the same
    string into **every** free-text column the `question` table carries out of a
    named candidate set, and a test asserts served-equals-planted. That way the
    implementer's choice between the two columns is still the implementer's, and
    a fixture has not answered an open interface question by picking one
    (`tests/fixtures/report_views.py` takes the same line with the validity
    service's signature). A `question` table carrying none of the candidates is a
    failure naming them, never a silent skip.

  - **Which position is a stream's rating question** is read off the layout the
    world planted (`ReportWorld.shape_of` and `stream_of`), not off a constant, so
    a version planted with a different order is asked the same question correctly.
    The **comment** question of the same stream is planted with wording of its
    own, which is what makes "the rating question's text" an assertion rather than
    a description: a service serving the stream's comment question passes every
    shape check and fails the equality.

**Every guard is a `pytest.fail` a test body reaches through one of these
functions, never a fixture** (`docs/MISTAKES.md` entry 44): on a tree where
E5-02 is unbuilt the modules that use this go red as FAILEDs naming the missing
member, not as errors in somebody's setup. The planting itself touches only rows
this suite seeded, so it is an input like every other value in
`tests/fixtures/report_api.py`'s world.
"""

from collections.abc import Sequence
from typing import Any

import pytest
from sqlalchemy import String, select, update

from fixtures.report_api import TAUGHT_COHORT, TERM_WEEK_OF_COURSE_WEEK
from fixtures.report_views import (
    COURSE_STREAM,
    FIRST_VERSION,
    INSTRUCTOR_STREAM,
    SECOND_VERSION,
    SPEC_QUESTION_LAYOUT,
)
from fixtures.submit import QUESTION_TABLE
from fixtures.supervision import require_table, single_primary_key

# A third version, for the one case two cannot pose: whether the wording served
# for a week comes from the rows that week's responses **answered** or from
# whichever set is newest. With three versions planted and the middle one
# answered, the two rules give different answers and the test can name which one
# it got (E5-02's work order, decision 2).
THIRD_VERSION = 3

# The columns a question's served text might live in. A candidate set rather than
# one name, for the reason this module's docstring gives: the work order leaves
# the choice between `name` and `prompt` to the implementer, and a fixture that
# planted into one of them would decide it. Enumerated columns (the shape column
# E2-05 ships) are excluded by type below rather than by name.
QUESTION_TEXT_COLUMN_CANDIDATES = ("name", "prompt", "text", "wording", "label", "title", "body")

# The two ratings a planted version's response carries, one per stream. Different
# numbers so that a mixed-up stream is visible in a distribution too, and neither
# is read back by anything in this module.
A_RATING = {INSTRUCTOR_STREAM: 5, COURSE_STREAM: 2}

NO_TEXT_COLUMN = (
    f"`{QUESTION_TABLE}` carries none of the free-text columns a question's served wording could "
    f"sit in ({list(QUESTION_TEXT_COLUMN_CANDIDATES)}). E5-02 serves 'the exact string the student "
    "survey renders as the rating question's heading' on the report payload, so there is a column "
    "holding it; if it is spelled some other way, `QUESTION_TEXT_COLUMN_CANDIDATES` in "
    "tests/fixtures/report_question_text.py is the one line that changes."
)


def planted_wording(*, version: int, position: int) -> str:
    """The wording this suite writes for one question of one version.

    Distinct per version and position, and deliberately unlike both SPEC §3.2's
    sentences and the mockup's histogram titles: a payload that served a constant
    from either place answers this with a string that is not this one.
    """
    return f"E5-02 planted v{version} q{position} wording"


def question_text_columns(world: Any) -> tuple[str, ...]:
    """Every free-text column on `question` this module plants wording into."""
    table = require_table(world.tables, QUESTION_TABLE)
    found = tuple(
        name
        for name in QUESTION_TEXT_COLUMN_CANDIDATES
        if name in table.c
        and isinstance(table.c[name].type, String)
        and not list(getattr(table.c[name].type, "enums", ()) or [])
    )
    if not found:
        pytest.fail(NO_TEXT_COLUMN)
    return found


def plant_wording_for(world: Any, *, version: int) -> dict[int, str]:
    """Write this suite's own wording over every question of one planted version.

    Answers the wording by position, so a test names its expectation as
    `planted[rating_position(...)]` rather than rebuilding the string.
    """
    table = require_table(world.tables, QUESTION_TABLE)
    key = single_primary_key(table)
    columns = question_text_columns(world)
    if version not in world.questions:
        pytest.fail(
            f"No question set at version {version} has been planted in this world; it holds "
            f"{sorted(world.questions)}. `plant_wording_for` writes over rows `plant_question_set` "
            "has already seeded."
        )

    planted: dict[int, str] = {}
    for position, row in world.questions[version].items():
        wording = planted_wording(version=version, position=position)
        values = dict.fromkeys(columns, wording)
        world.session.execute(update(table).where(table.c[key] == row[key]).values(**values))
        planted[position] = wording
    world.session.flush()
    return planted


def stored_wording(world: Any, *, version: int, position: int) -> dict[str, Any]:
    """What the database holds for one question, by column — the planting's own canary.

    Read back rather than assumed: an `UPDATE` that matched no row exits happily
    and leaves every later assertion measuring the walker's invented value
    instead of this suite's (`docs/MISTAKES.md` entry 3).
    """
    table = require_table(world.tables, QUESTION_TABLE)
    key = single_primary_key(table)
    columns = question_text_columns(world)
    row = world.questions[version][position]
    statement = select(*[table.c[name] for name in columns]).where(table.c[key] == row[key])
    found = world.session.execute(statement).mappings().one()
    return dict(found)


def _one_position(world: Any, *, version: int, shape: str, stream: str) -> int:
    """The single position of one version carrying `shape` for `stream`."""
    if version not in world.shape_of:
        pytest.fail(
            f"This world planted no question set at version {version}; it holds "
            f"{sorted(world.shape_of)}."
        )
    found = [
        position
        for position, planted_shape in world.shape_of[version].items()
        if planted_shape == shape and world.stream_of[version][position] == stream
    ]
    if len(found) != 1:
        pytest.fail(
            f"Version {version} of this world's question set carries {len(found)} {shape} questions "
            f"for the {stream} stream ({found}); SPEC §3.2 gives each stream exactly one of each. "
            "The layout planted is `SPEC_QUESTION_LAYOUT` in tests/fixtures/report_views.py."
        )
    return found[0]


def rating_position(world: Any, *, version: int, stream: str) -> int:
    """Which position is one stream's rating question in one planted version."""
    return _one_position(world, version=version, shape="rating", stream=stream)


def comment_position(world: Any, *, version: int, stream: str) -> int:
    """Which position is one stream's comment question — the near miss a test excludes."""
    return _one_position(world, version=version, shape="comment", stream=stream)


def plant_the_first_versions_wording(door: Any) -> dict[int, str]:
    """This suite's wording over the question set the report world was built with, committed.

    The world's first version is seeded by `build_report_world` with values the
    seeding walker invented, and every week of that world was answered through it.
    Writing over those rows leaves the answers pointing at the same questions —
    which is the state SPEC §3.2's versioning is about, and what makes "the weeks
    answered under version 1 still serve version 1's wording" assertable.
    """
    planted = plant_wording_for(door.world, version=FIRST_VERSION)
    door.commit()
    return planted


def plant_a_further_version(
    door: Any, *, version: int = SECOND_VERSION, answered_course_weeks: Sequence[int] = ()
) -> dict[int, str]:
    """A further question-set version with wording of its own, answered in the weeks named.

    The layout is SPEC §3.2's own order, so the versions differ in their wording
    and in nothing else — a served string that came from the right position of the
    wrong version is then the only way to be wrong, which is exactly the claim
    criterion 2 makes.

    Each named course week gets one response of its own, by a student seeded for
    it: E2-05 holds one response per student per section-week, so a week already
    answered by this world's five respondents is answered here by a sixth person.
    """
    world = door.world
    world.plant_question_set(version=version, layout=SPEC_QUESTION_LAYOUT)
    planted = plant_wording_for(world, version=version)

    for course_week in answered_course_weeks:
        student = world.respondent(cohort=TAUGHT_COHORT)
        world.submit(
            term_week=TERM_WEEK_OF_COURSE_WEEK[course_week],
            ratings={
                rating_position(world, version=version, stream=stream): rating
                for stream, rating in A_RATING.items()
            },
            cohort=TAUGHT_COHORT,
            version=version,
            student=student,
        )
    door.commit()
    return planted


@pytest.fixture
def question_wording() -> Any:
    """The planting machinery E5-02's versioning proof is written over.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module in this suite gives: importing a fixtures module by name depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class QuestionWording:
        first_version = FIRST_VERSION
        second_version = SECOND_VERSION
        third_version = THIRD_VERSION
        text_column_candidates = QUESTION_TEXT_COLUMN_CANDIDATES

        wording = staticmethod(planted_wording)
        columns = staticmethod(question_text_columns)
        stored = staticmethod(stored_wording)
        rating_position = staticmethod(rating_position)
        comment_position = staticmethod(comment_position)
        plant_first = staticmethod(plant_the_first_versions_wording)
        plant_further = staticmethod(plant_a_further_version)

    return QuestionWording()
